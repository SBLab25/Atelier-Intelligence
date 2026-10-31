# Spec 06 gate (T7). Offline, dummy credentials, dead database URLs (Supabase is live).
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\06-cleanup\evidence"
$ev01 = Join-Path $repo ".kiro\specs\01-baseline\evidence"
$ev02 = Join-Path $repo ".kiro\specs\02-p0-security\evidence"
$ev05 = Join-Path $repo ".kiro\specs\05-repositories\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$sum  = Join-Path $ev "gate-results.txt"
$tmp  = "C:\Users\sovan\.kiro\s06_gate_tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
"Spec 06 gate started $(Get-Date -Format s)" | Set-Content $sum -Encoding utf8

$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
$env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:CJI_ADMIN_KEY = "baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE = "1"; $env:JOURNEY_NAME = "user_onboarding"; $env:PYTHONIOENCODING = "utf-8"
Remove-Item Env:CJI_TEST_DATABASE_URL -ErrorAction SilentlyContinue

function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-40} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum -Encoding utf8
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
$junitNew = "--junitxml=" + (Join-Path $ev "gate-new-tests-junit.xml")
Step "pytest full (not integration)" "gate-pytest-full.log" {
    & $py -m pytest tests -p no:cacheprovider -m "not integration" -rfEs $junitFull
}
Step "pytest Spec 06 tests" "gate-new-tests.log" {
    & $py -m pytest tests/test_cleanup.py tests/test_docs.py tests/test_dashboard_smoke.py -p no:cacheprovider -rfEs $junitNew
}
Step "golden snapshot" "gate-golden.log" { & $py (Join-Path $ev02 "scripts\golden.py") (Join-Path $ev "golden-after.json") }
$g5 = (Get-FileHash (Join-Path $ev05 "golden-after.json")).Hash
$g6 = (Get-FileHash (Join-Path $ev "golden-after.json")).Hash
"golden identical to Spec 05: $($g5 -eq $g6)" | Add-Content $sum -Encoding utf8
Step "seeded synthetic data" "gate-synthetic.log" { & $py (Join-Path $ev "scripts\synthetic_hash.py") }
"$((Get-Content (Join-Path $ev "gate-synthetic.log") | Select-String "SYNTH identical").Line) (deterministic columns, current vs pre-Spec-06 generator)" | Add-Content $sum -Encoding utf8

Step "ruff check . (full list)" "gate-ruff.log" { & $py -m ruff check . --no-cache --output-format concise }
Step "ruff unused/undefined names (no snippets)" "gate-ruff-names.log" {
    & $py -m ruff check . --select F401,F841,F811,F821,E722 --extend-exclude snippets --no-cache --output-format concise
}
Step "ruff check new code" "gate-ruff-new.log" {
    & $py -m ruff check tests/test_cleanup.py tests/test_docs.py tests/test_dashboard_smoke.py --no-cache --output-format concise
}
Step "mypy ." "gate-mypy.log" { & $py -m mypy . --exclude "(^|/)\.venv/" --cache-dir "C:\Users\sovan\.kiro\s06_mypy_cache" }
Step "mypy --strict repositories" "gate-mypy-repositories-strict.log" { & $py -m mypy repositories --strict --cache-dir "C:\Users\sovan\.kiro\s06_mypy_cache" }
Step "bandit -r . (json)" "gate-bandit.json.log" { & $py -m bandit -r . -x "./.venv" -f json -q }
Step "static compare vs Spec 01" "gate-static-compare.log" {
    & $py (Join-Path $ev02 "scripts\compare_static.py") $ev01 $ev `
        main.py graph.py dashboard.py collector/api.py generate_diverse.py `
        mcp_servers/journey_data_server.py mcp_servers/ingestion_intelligence_server.py mcp_servers/insight_server.py `
        mcp_servers/report_server.py mcp_servers/friction_engine_server.py `
        agents/workers.py agents/ingestion_worker.py tools/mcp_client.py tools/ingest_json.py tools/synthetic_data.py `
        repositories/duckdb_parquet.py settings/roles.py guardrails/output_validator.py tracker/snippet_generator.py `
        tests/conftest.py tests/test_agent_layer.py tests/test_collector_models.py tests/test_friction_engine.py `
        tests/test_supervisor.py tests/test_synthetic_data.py tests/test_ingestion_intelligence.py
}

# Entry-point smoke checks (CL-14)
Step "main.py --help" "gate-help-main.log" { & $py main.py --help }
Step "run_servers.py --help" "gate-help-run-servers.log" { & $py run_servers.py --help }
Step "tools/ingest_json.py --help" "gate-help-ingest-json.log" { & $py tools/ingest_json.py --help }
Step "tracker/snippet_generator.py --help" "gate-help-snippet.log" { & $py tracker/snippet_generator.py --help }
Step "python -m settings check (cli)" "gate-settings-check.log" { & $py -m settings check --no-dotenv }
Step "collector import (app routes)" "gate-collector-import.log" {
    & $py -c "from collector.api import app; print(sorted(r.path for r in app.routes))"
}

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
    $env:DATABASE_URL = "postgresql://u@127.0.0.1:1/x"
    Step "mode mismatch (realtime CLI, demo servers)" "gate-mode-mismatch.log" { & $py main.py --mode realtime --run --auto-approve }
    $env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
} else { "pipeline smoke NOT RUN: servers did not start" | Add-Content $sum -Encoding utf8 }
KillTree $srv
Start-Sleep 2
"ports after stop: $(Listening @(8001,8002,8003,8004,8005))" | Add-Content $sum -Encoding utf8

Step "git diff --check (cr-at-eol)" "gate-diff-check.log" { git -C $repo -c core.whitespace=cr-at-eol diff --check }
Step "git diff --stat" "gate-diff-stat.log" { git -C $repo diff --stat }
Step "git status (deleted files)" "gate-git-status.log" { git -C $repo status --porcelain --untracked-files=no }
"tracked events.parquet unchanged: $($hashBefore -eq (Get-FileHash $parquet).Hash)" | Add-Content $sum -Encoding utf8
Remove-Item -Recurse -Force $tmp
"Spec 06 gate finished $(Get-Date -Format s)" | Add-Content $sum -Encoding utf8
