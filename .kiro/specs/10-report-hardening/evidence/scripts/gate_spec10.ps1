# Spec 10 gate (T7). Spec 09 gate plus report checks. Offline, dummy credentials, dead proxy and database URLs (Supabase is live).
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\10-report-hardening\evidence"
$ev09 = Join-Path $repo ".kiro\specs\09-durable-workflow\evidence"
$ev01 = Join-Path $repo ".kiro\specs\01-baseline\evidence"
$ev02 = Join-Path $repo ".kiro\specs\02-p0-security\evidence"
$ev07 = Join-Path $repo ".kiro\specs\07-collector\evidence"
$ev08 = Join-Path $repo ".kiro\specs\08-ai-gateway\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$sum  = Join-Path $ev "gate-results.txt"
$tmp  = "C:\Users\sovan\.kiro\s10_gate_tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
"Spec 10 gate started $(Get-Date -Format s)" | Set-Content $sum -Encoding utf8

$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
$env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:CJI_ADMIN_KEY = "baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE = "1"; $env:JOURNEY_NAME = "user_onboarding"; $env:PYTHONIOENCODING = "utf-8"
$env:LLM_MODEL = "openai/gpt-oss-120b"; $env:CJI_LLM_PROVIDER = "groq"
# Gate checkpoints in a scratch file (the real data/cji_checkpoints.db keeps older runs untouched).
$env:CJI_CHECKPOINTS_DB = Join-Path $tmp "gate_checkpoints.db"
Remove-Item Env:CJI_TEST_DATABASE_URL -ErrorAction SilentlyContinue

function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-48} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum -Encoding utf8
}
function Note($text) { $text | Add-Content $sum -Encoding utf8 }
function ThreadId($logName) {
    $m = Select-String -Path (Join-Path $ev $logName) -Pattern "Thread ID: ([0-9a-f-]{36})" | Select-Object -First 1
    if ($m) { return $m.Matches[0].Groups[1].Value } else { return "" }
}
function Listening($ports) {
    $l = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    ($ports | ForEach-Object { $p = $_; "{0}:{1}" -f $p, $(if ($l | Where-Object LocalPort -eq $p) { "LISTEN" } else { "-" }) }) -join "  "
}
function KillTree($p) { if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F *> $null } }
function StartServers($tag) {
    $s = Start-Process -FilePath $py -ArgumentList "run_servers.py" -WorkingDirectory $app -PassThru -WindowStyle Hidden `
         -RedirectStandardOutput "$ev\gate-servers-$tag.out.log" -RedirectStandardError "$ev\gate-servers-$tag.err.log"
    for ($i = 0; $i -lt 30; $i++) { Start-Sleep 2; if (((Listening @(8001,8002,8003,8004,8005)) -split 'LISTEN').Count -eq 6) { break } }
    Note "servers ($tag): $(Listening @(8001,8002,8003,8004,8005))"
    return $s
}

Set-Location $app
$parquet = Join-Path $app "data\events.parquet"
$hashBefore = (Get-FileHash $parquet).Hash
$audit = Join-Path $app "data\audit"
if (Test-Path $audit) { Remove-Item -Recurse -Force $audit }      # generated, gitignored: inspect this run only
$reportsBefore = @(Get-ChildItem (Join-Path $app "reports") -Filter "*.html" -ErrorAction SilentlyContinue).Count
$gateStart = [DateTimeOffset]::Now.ToUnixTimeSeconds()

$junitFull = "--junitxml=" + (Join-Path $ev "gate-pytest-junit.xml")
$junitNew = "--junitxml=" + (Join-Path $ev "gate-new-tests-junit.xml")
Step "pytest full (not integration)" "gate-pytest-full.log" {
    & $py -m pytest tests -p no:cacheprovider -m "not integration" -rfEs $junitFull
}
Step "pytest Spec 10 tests" "gate-new-tests.log" {
    & $py -m pytest tests/test_reports.py tests/test_workflow.py tests/test_p0_security.py tests/test_contracts.py `
        tests/test_cleanup.py tests/test_docs.py tests/test_dashboard_smoke.py `
        -p no:cacheprovider -m "not integration" -rfEs $junitNew
}
Step "collector smoke (Spec 07 regression)" "gate-collector-smoke.log" { & $py (Join-Path $ev07 "scripts\collector_smoke.py") }
Step "golden snapshot" "gate-golden.log" { & $py (Join-Path $ev02 "scripts\golden.py") (Join-Path $ev "golden-after.json") }
$g9 = (Get-FileHash (Join-Path $ev09 "golden-after.json")).Hash
$g10 = (Get-FileHash (Join-Path $ev "golden-after.json")).Hash
Note "golden identical to Spec 09: $($g9 -eq $g10)"

Step "ruff check . (full list)" "gate-ruff.log" { & $py -m ruff check . --no-cache --output-format concise }
Step "ruff check new code" "gate-ruff-new.log" {
    & $py -m ruff check reporting tests/test_reports.py tests/_report_checks.py --no-cache --output-format concise
}
Step "mypy ." "gate-mypy.log" { & $py -m mypy . --exclude "(^|/)\.venv/" --cache-dir "C:\Users\sovan\.kiro\s10_mypy_cache" }
# --follow-imports=silent: check the new modules strictly without reporting legacy modules they import.
Step "mypy --strict workflow domain/runs.py" "gate-mypy-workflow-strict.log" { & $py -m mypy workflow domain/runs.py --strict --follow-imports=silent --cache-dir "C:\Users\sovan\.kiro\s10_mypy_cache" }
Step "mypy --strict reporting" "gate-mypy-reporting-strict.log" { & $py -m mypy reporting --strict --follow-imports=silent --cache-dir "C:\Users\sovan\.kiro\s10_mypy_cache" }
Step "mypy --strict integrations" "gate-mypy-integrations-strict.log" { & $py -m mypy integrations --strict --cache-dir "C:\Users\sovan\.kiro\s10_mypy_cache" }
Step "mypy --strict repositories" "gate-mypy-repositories-strict.log" { & $py -m mypy repositories --strict --cache-dir "C:\Users\sovan\.kiro\s10_mypy_cache" }
Step "bandit -r . (json)" "gate-bandit.json.log" { & $py -m bandit -r . -x "./.venv" -f json -q }
Step "bandit workflow (text)" "gate-bandit-workflow.log" { & $py -m bandit -r workflow -q }
Step "bandit reporting (text)" "gate-bandit-reporting.log" { & $py -m bandit -r reporting -q }
Step "static compare vs Spec 01" "gate-static-compare.log" {
    & $py (Join-Path $ev02 "scripts\compare_static.py") $ev01 $ev `
        main.py graph.py dashboard.py state.py collector/api.py collector/models.py generate_diverse.py `
        mcp_servers/journey_data_server.py mcp_servers/ingestion_intelligence_server.py mcp_servers/insight_server.py `
        mcp_servers/report_server.py mcp_servers/friction_engine_server.py agents/supervisor.py `
        agents/workers.py agents/ingestion_worker.py tools/mcp_client.py tools/ingest_json.py tools/synthetic_data.py `
        repositories/duckdb_parquet.py settings/roles.py guardrails/output_validator.py tracker/snippet_generator.py `
        tests/conftest.py tests/test_agent_layer.py tests/test_collector_models.py tests/test_friction_engine.py `
        tests/test_supervisor.py tests/test_synthetic_data.py tests/test_ingestion_intelligence.py
}

Step "main.py --help" "gate-help-main.log" { & $py main.py --help }
Step "run_servers.py --help" "gate-help-run-servers.log" { & $py run_servers.py --help }
Step "python -m settings check (cli)" "gate-settings-check.log" { & $py -m settings check --no-dotenv }
Step "settings check: step timeout below MCP call timeout" "gate-settings-step-timeout.log" {
    $env:CJI_WORKFLOW_STEP_TIMEOUT_S = "60"; & $py -m settings check --no-dotenv; Remove-Item Env:CJI_WORKFLOW_STEP_TIMEOUT_S
}
Step "CLI refuses unknown thread (--status/--approve/--resume)" "gate-cli-unknown.log" {
    & $py main.py --status --thread-id no-such-run; $a = $LASTEXITCODE
    & $py main.py --approve --thread-id no-such-run; $b = $LASTEXITCODE
    & $py main.py --resume --thread-id no-such-run; $c = $LASTEXITCODE
    "exit codes: status=$a approve=$b resume=$c"; $global:LASTEXITCODE = [int]($a -ne 1 -or $b -ne 1 -or $c -ne 1)
}

# Pipeline 1: LLM disabled. Dashboard call, then pause -> status -> approve -> approve again -> status.
$env:CJI_LLM_PROVIDER = "none"
$srv = StartServers "none"
Step "demo pipeline --run --auto-approve (dashboard call)" "gate-demo-pipeline-none.log" { & $py main.py --mode demo --run --auto-approve }
Step "pause: --run without --auto-approve" "gate-pause.log" { & $py main.py --mode demo --run }
$paused = ThreadId "gate-pause.log"
Note "paused thread: $paused"
Step "status of the paused run" "gate-status-paused.log" { & $py main.py --status --thread-id $paused }
Step "--resume of a paused run is refused (exit 1)" "gate-resume-paused.log" { & $py main.py --resume --thread-id $paused }
Step "approve" "gate-approve.log" { & $py main.py --approve --thread-id $paused }
Step "approve again (no-op)" "gate-approve-again.log" { & $py main.py --approve --thread-id $paused }
Step "status after approval" "gate-status-approved.log" { & $py main.py --status --thread-id $paused }
$reportsForPaused = @(Get-ChildItem (Join-Path $app "reports") -Filter "*$paused*.html" -ErrorAction SilentlyContinue).Count
Note "report files for the approved run: $reportsForPaused"
KillTree $srv; Start-Sleep 2
$env:CJI_LLM_PROVIDER = "groq"

# Pipeline 2: groq with a dummy key behind a dead proxy (slow insight step: LLM retries), killed in insight_worker.
$srv = StartServers "groq"
Step "demo pipeline (groq, dummy key, offline)" "gate-demo-pipeline.log" { & $py main.py --mode demo --run --auto-approve }
Step "kill during insight_worker, then resume" "gate-kill-resume.log" {
    $wf = Join-Path $audit "workflow.jsonl"
    $before = if (Test-Path $wf) { (Get-Content $wf).Count } else { 0 }
    $env:PYTHONUNBUFFERED = "1"
    $p = Start-Process -FilePath $py -ArgumentList "main.py --mode demo --run --auto-approve" -WorkingDirectory $app -PassThru `
         -WindowStyle Hidden -RedirectStandardOutput "$tmp\kill.out.log" -RedirectStandardError "$tmp\kill.err.log"
    $killed = $false
    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Milliseconds 500
        $new = if (Test-Path $wf) { Get-Content $wf | Select-Object -Skip $before } else { @() }
        if ($new | Where-Object { $_ -match '"worker": "friction_worker"' -and $_ -match '"outcome": "ok"' }) {
            Start-Sleep -Milliseconds 1500; KillTree $p; $killed = $true; break
        }
    }
    "killed during insight step: $killed"
    Get-Content "$tmp\kill.out.log"
    Remove-Item Env:PYTHONUNBUFFERED
    # The run id comes from the killed run's step records (stdout of a killed process may be incomplete).
    $rec = Get-Content $wf | Select-Object -Skip $before | Where-Object { $_ -match '"kind": "step"' } | Select-Object -First 1
    $tid = if ($rec) { ($rec | ConvertFrom-Json).run_id } else { "" }
    "thread: $tid"
    "---- status after kill"; & $py main.py --status --thread-id $tid
    "---- resume"; & $py main.py --resume --thread-id $tid; $code = $LASTEXITCODE
    "---- status after resume"; & $py main.py --status --thread-id $tid
    $global:LASTEXITCODE = $code
}
"event_name,page_location,ga_session_id,user_pseudo_id,event_timestamp`npage_view,https://example.test/signup,s1,u1,2026-01-01T00:00:00Z" | Set-Content "$tmp\probe.csv"
Step "ingest probe" "gate-ingest-probe.log" {
    & $py main.py --mode demo --ingest --file "$tmp\probe.csv" --source-hint "baseline probe" --run --auto-approve
}
$env:DATABASE_URL = "postgresql://u@127.0.0.1:1/x"
Step "mode mismatch (realtime CLI, demo servers; exit 1)" "gate-mode-mismatch.log" { & $py main.py --mode realtime --run --auto-approve }
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
KillTree $srv
Start-Sleep 2
Note "ports after stop: $(Listening @(8001,8002,8003,8004,8005))"
Step "audit files: fields, secrets, correlation (Spec 08)" "gate-audit-check.log" { & $py (Join-Path $ev08 "scripts\audit_check.py") }
Step "workflow audit: steps, runs, kill/resume" "gate-audit-workflow.log" { & $py (Join-Path $ev09 "scripts\audit_workflow_check.py") }
Step "report contract and inertness (gate reports)" "gate-report-contract.log" { & $py (Join-Path $ev "scripts\report_contract_check.py") $gateStart }
Note "new report files in reports/: $(@(Get-ChildItem (Join-Path $app 'reports') -Filter '*.html').Count - $reportsBefore)"

Step "git diff --check (cr-at-eol)" "gate-diff-check.log" { git -C $repo -c core.whitespace=cr-at-eol diff --check }
Step "git diff --stat" "gate-diff-stat.log" { git -C $repo diff --stat }
Step "git status (tracked)" "gate-git-status.log" { git -C $repo status --porcelain --untracked-files=no }
Note "tracked events.parquet unchanged: $($hashBefore -eq (Get-FileHash $parquet).Hash)"
Copy-Item $env:CJI_CHECKPOINTS_DB (Join-Path $ev "gate-checkpoints.db") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $tmp
Note "Spec 10 gate finished $(Get-Date -Format s)"
