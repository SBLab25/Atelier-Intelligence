# Spec 03 gate (T7). Offline, dummy credentials, dead DATABASE_URL. Writes logs to ..\
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\03-canonical-contracts\evidence"
$ev01 = Join-Path $repo ".kiro\specs\01-baseline\evidence"
$ev02 = Join-Path $repo ".kiro\specs\02-p0-security\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$sum  = Join-Path $ev "gate-results.txt"
$tmp  = "C:\Users\sovan\.kiro\s03_gate_tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
"Spec 03 gate started $(Get-Date -Format s)" | Set-Content $sum -Encoding utf8

$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
$env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:CJI_ADMIN_KEY = "baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE = "1"; $env:JOURNEY_NAME = "user_onboarding"; $env:PYTHONIOENCODING = "utf-8"

function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-36} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum -Encoding utf8
}
function Listening($ports) {
    $l = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    ($ports | ForEach-Object { $p = $_; "{0}:{1}" -f $p, $(if ($l | Where-Object LocalPort -eq $p) { "LISTEN" } else { "-" }) }) -join "  "
}
function KillTree($p) { if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F *> $null } }

Set-Location $app
$parquet = Join-Path $app "data\events.parquet"
$hashBefore = (Get-FileHash $parquet).Hash

$junitFull = "--junitxml=" + (Join-Path $ev "gate-pytest-junit.xml")
$junitContracts = "--junitxml=" + (Join-Path $ev "after-contracts-junit.xml")
Step "pytest full (not integration)" "gate-pytest-full.log" {
    & $py -m pytest tests -p no:cacheprovider -m "not integration" -rfE $junitFull
}
Step "pytest test_contracts.py" "after-contracts.log" {
    & $py -m pytest tests/test_contracts.py -p no:cacheprovider -rfE $junitContracts
}
Step "golden snapshot" "gate-golden.log" { & $py (Join-Path $ev02 "scripts\golden.py") (Join-Path $ev "golden-after.json") }
$g2 = (Get-FileHash (Join-Path $ev02 "golden-after.json")).Hash
$g3 = (Get-FileHash (Join-Path $ev "golden-after.json")).Hash
"golden identical to Spec 02: $($g2 -eq $g3)" | Add-Content $sum -Encoding utf8

Step "ruff check . (full list)" "gate-ruff.log" { & $py -m ruff check . --no-cache --output-format concise }
Step "ruff check domain" "gate-ruff-domain.log" { & $py -m ruff check domain --no-cache --output-format concise }
Step "mypy ." "gate-mypy.log" {
    & $py -m mypy . --exclude "(^|/)\.venv/" --cache-dir "C:\Users\sovan\.kiro\s03_mypy_cache"
}
Step "mypy domain" "gate-mypy-domain.log" { & $py -m mypy domain --cache-dir "C:\Users\sovan\.kiro\s03_mypy_cache" }
Step "mypy --strict domain (info)" "gate-mypy-domain-strict.log" { & $py -m mypy domain --strict --cache-dir "C:\Users\sovan\.kiro\s03_mypy_cache" }
Step "bandit -r . (json)" "gate-bandit.json.log" { & $py -m bandit -r . -x "./.venv" -f json -q }
Copy-Item (Join-Path $ev "gate-ruff.log") (Join-Path $tmp "gate-ruff.log")
Step "static compare vs Spec 01" "gate-static-compare.log" {
    & $py (Join-Path $ev02 "scripts\compare_static.py") $ev01 $ev `
        collector/models.py collector/api.py mcp_servers/ingestion_intelligence_server.py tools/ingest_json.py `
        state.py guardrails/output_validator.py agents/supervisor.py agents/workers.py agents/ingestion_worker.py config.py tests/test_agent_layer.py `
        domain/__init__.py domain/events.py domain/journeys.py domain/metrics.py domain/insights.py domain/runs.py domain/validation.py
}

# Smoke: MCP servers, demo pipeline, ingest probe
$srv = Start-Process -FilePath $py -ArgumentList "run_servers.py" -WorkingDirectory $app -PassThru -WindowStyle Hidden `
       -RedirectStandardOutput "$ev\gate-servers.out.log" -RedirectStandardError "$ev\gate-servers.err.log"
$ok = $false
for ($i = 0; $i -lt 30; $i++) { Start-Sleep 2; if (((Listening @(8001,8002,8003,8004,8005)) -split 'LISTEN').Count -eq 6) { $ok = $true; break } }
"servers: $(Listening @(8001,8002,8003,8004,8005))" | Add-Content $sum -Encoding utf8
if ($ok) {
    Step "demo pipeline" "gate-demo-pipeline.log" { & $py main.py --mode demo --run --auto-approve }
    "event_name,page_location,ga_session_id,user_pseudo_id,event_timestamp`npage_view,https://example.test/signup,s1,u1,2026-01-01T00:00:00Z" | Set-Content "$tmp\probe.csv"
    Step "ingest probe" "gate-ingest-probe.log" {
        & $py main.py --mode demo --ingest --file "$tmp\probe.csv" --source-hint "baseline probe" --run --auto-approve
    }
} else { "demo pipeline / ingest probe NOT RUN: servers did not start" | Add-Content $sum -Encoding utf8 }
KillTree $srv
Start-Sleep 2
"ports after stop: $(Listening @(8001,8002,8003,8004,8005))" | Add-Content $sum -Encoding utf8

Step "git diff --check (cr-at-eol)" "gate-diff-check.log" { git -C $repo -c core.whitespace=cr-at-eol diff --check }
Step "git diff --stat" "gate-diff-stat.log" { git -C $repo diff --stat }
Step "git status --short" "gate-git-status.log" { git -C $repo status --short }
"tracked events.parquet unchanged: $($hashBefore -eq (Get-FileHash $parquet).Hash)" | Add-Content $sum -Encoding utf8
Remove-Item -Recurse -Force $tmp
"Spec 03 gate finished $(Get-Date -Format s)" | Add-Content $sum -Encoding utf8
