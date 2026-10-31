# Spec 11 gate (T6/T7): build and clean-install proof (design §7, OD-106), then the Spec 10 gate on the packaged code.
# Phase A installs packages (PyPI reachable, no application code runs). Phase B and C run offline: dummy credentials,
# dead proxy and database URLs (Supabase is live and never contacted).
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\11-packaging\evidence"
$ev10 = Join-Path $repo ".kiro\specs\10-report-hardening\evidence"
$ev07 = Join-Path $repo ".kiro\specs\07-collector\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$uv   = "C:\Users\sovan\AppData\Local\hermes\bin\uv.EXE"
$sum  = Join-Path $ev "gate-results.txt"
$tmp  = "C:\Users\sovan\.kiro\s11_gate_tmp"
$clean = Join-Path $tmp "clean-venv"
$cpy  = Join-Path $clean "Scripts\python.exe"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
"Spec 11 gate started $(Get-Date -Format s)" | Set-Content $sum -Encoding utf8

function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-56} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum -Encoding utf8
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
function WaitServers($tag) {
    for ($i = 0; $i -lt 40; $i++) { Start-Sleep 2; if (((Listening @(8001,8002,8003,8004,8005)) -split 'LISTEN').Count -eq 6) { break } }
    Note "servers ($tag): $(Listening @(8001,8002,8003,8004,8005))"
}
function StartServers($tag) {
    $s = Start-Process -FilePath $py -ArgumentList "run_servers.py" -WorkingDirectory $app -PassThru -WindowStyle Hidden `
         -RedirectStandardOutput "$ev\gate-servers-$tag.out.log" -RedirectStandardError "$ev\gate-servers-$tag.err.log"
    WaitServers $tag
    return $s
}

Set-Location $app
# setuptools reuses build/lib: remove generated build output so the wheel holds only the current sources.
function CleanBuildOutput { foreach ($d in "build", "src\cji_agent.egg-info") { $p = Join-Path $app $d; if (Test-Path $p) { Remove-Item -Recurse -Force $p } } }
CleanBuildOutput
# ══ Phase A: build, clean virtual environment, audit (network for package downloads only) ══════════════════════
Step "uv build --wheel" "gate-build.log" { & $uv build --wheel --out-dir "$tmp\dist" $app }
$wheel = Get-ChildItem "$tmp\dist" -Filter "cji_agent-*.whl" | Select-Object -First 1
Note "wheel: $($wheel.Name) ($($wheel.Length) bytes)"
if ($wheel) { Copy-Item $wheel.FullName (Join-Path $ev $wheel.Name) }
CleanBuildOutput      # build/lib would otherwise be scanned by `bandit -r .` below (gate finding G-2)
Step "wheel contents" "gate-wheel-check.log" { & $py (Join-Path $ev "scripts\wheel_check.py") $wheel.FullName }
Step "uv venv (clean, Python 3.12)" "gate-clean-venv.log" { & $uv venv $clean --python 3.12 }
Step "uv pip sync requirements.lock (hash-checked)" "gate-clean-sync.log" { & $uv pip sync (Join-Path $app "requirements.lock") --python $cpy }
Step "uv pip install --no-deps <wheel>" "gate-clean-install.log" { & $uv pip install --no-deps $wheel.FullName --python $cpy }
Step "uv pip check (clean venv)" "gate-clean-check.log" { & $uv pip check --python $cpy }
Step "uv pip freeze (clean venv)" "gate-clean-freeze.log" { & $uv pip freeze --python $cpy }
Step "pip-audit -r requirements.lock" "gate-pip-audit.log" {
    & $py -m pip_audit -r (Join-Path $app "requirements.lock") --disable-pip --require-hashes --progress-spinner off -f json -o (Join-Path $ev "gate-pip-audit.json")
    & $py -m pip_audit -r (Join-Path $app "requirements.lock") --disable-pip --require-hashes --progress-spinner off
}

# ══ Protected environment from here on ═════════════════════════════════════════════════════════════════════════
$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
$env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:CJI_ADMIN_KEY = "baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE = "1"; $env:JOURNEY_NAME = "user_onboarding"; $env:PYTHONIOENCODING = "utf-8"
$env:LLM_MODEL = "openai/gpt-oss-120b"; $env:CJI_LLM_PROVIDER = "groq"
$env:CJI_CHECKPOINTS_DB = Join-Path $tmp "gate_checkpoints.db"
Remove-Item Env:CJI_TEST_DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:CJI_HOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

# ══ Phase B: the clean virtual environment (installed wheel) ═══════════════════════════════════════════════════
$junitClean = "--junitxml=" + (Join-Path $ev "gate-clean-pytest-junit.xml")
Step "clean venv: full suite against the wheel" "gate-clean-pytest.log" {
    # Not a CJI_* name: settings reject unknown CJI_* variables when CJI_ENV=test (gate finding G-1).
    $env:TEST_EXPECT_INSTALLED = "wheel"
    & $cpy -m pytest tests -p no:cacheprovider -m "not integration" -rfEs $junitClean
    $c = $LASTEXITCODE; Remove-Item Env:TEST_EXPECT_INSTALLED; $global:LASTEXITCODE = $c
}
Step "clean venv: cji is the installed wheel" "gate-clean-location.log" {
    Push-Location $tmp; & $cpy -c "import cji, importlib.metadata as m; print(cji.__file__); print(m.version('cji-agent')); print(m.distribution('cji-agent').read_text('direct_url.json'))"; $c = $LASTEXITCODE; Pop-Location; $global:LASTEXITCODE = $c
}
$outside = Join-Path $tmp "outside"; New-Item -ItemType Directory -Force -Path $outside | Out-Null
Step "clean venv: every console script --help (outside the project)" "gate-clean-scripts-help.log" {
    Push-Location $outside
    $bad = 0
    foreach ($s in "cji","cji-servers","cji-settings","cji-dashboard","cji-collector","cji-ingest-json","cji-snippet","cji-generate-diverse") {
        "---- $s --help"; & (Join-Path $clean "Scripts\$s.exe") --help; "exit=$LASTEXITCODE"; if ($LASTEXITCODE -ne 0) { $bad++ }
    }
    Pop-Location
    "failures: $bad"; $global:LASTEXITCODE = $bad
}
$home11 = Join-Path $tmp "home"; New-Item -ItemType Directory -Force -Path (Join-Path $home11 "data") | Out-Null
Copy-Item (Join-Path $app "data\events.parquet") (Join-Path $home11 "data\events.parquet")
Step "clean venv: cji-settings check (CJI_HOME)" "gate-clean-settings-check.log" {
    $env:CJI_HOME = $home11; Push-Location $outside; & (Join-Path $clean "Scripts\cji-settings.exe") check --no-dotenv; $c = $LASTEXITCODE; Pop-Location
    Remove-Item Env:CJI_HOME; $global:LASTEXITCODE = $c
}
Step "clean venv: demo pipeline outside the project (CJI_HOME)" "gate-clean-pipeline.log" {
    $env:CJI_HOME = $home11; $env:CJI_LLM_PROVIDER = "none"
    $s = Start-Process -FilePath (Join-Path $clean "Scripts\cji-servers.exe") -WorkingDirectory $outside -PassThru -WindowStyle Hidden `
         -RedirectStandardOutput "$ev\gate-clean-servers.out.log" -RedirectStandardError "$ev\gate-clean-servers.err.log"
    WaitServers "clean"
    Push-Location $outside
    & (Join-Path $clean "Scripts\cji.exe") --mode demo --run --auto-approve; $c = $LASTEXITCODE
    Pop-Location
    KillTree $s; Start-Sleep 2
    "---- files in CJI_HOME"; Get-ChildItem -Recurse $home11 -File | ForEach-Object { $_.FullName.Substring($home11.Length) }
    "---- files in the working directory"; Get-ChildItem -Recurse $outside -File | ForEach-Object { $_.FullName.Substring($outside.Length) }
    Remove-Item Env:CJI_HOME; $env:CJI_LLM_PROVIDER = "groq"; $global:LASTEXITCODE = $c
}
Note "clean pipeline report in CJI_HOME/reports: $(@(Get-ChildItem (Join-Path $home11 'reports') -Filter '*.html' -ErrorAction SilentlyContinue).Count)"
Note "ports after clean pipeline: $(Listening @(8001,8002,8003,8004,8005))"

# ══ Phase C: Spec 10 gate on the packaged code (baseline venv, editable install, old commands) ═════════════════
$parquet = Join-Path $app "data\events.parquet"
$hashBefore = (Get-FileHash $parquet).Hash
$audit = Join-Path $app "data\audit"
if (Test-Path $audit) { Remove-Item -Recurse -Force $audit }      # generated, gitignored: inspect this run only
$reportsBefore = @(Get-ChildItem (Join-Path $app "reports") -Filter "*.html" -ErrorAction SilentlyContinue).Count
$gateStart = [DateTimeOffset]::Now.ToUnixTimeSeconds()

$junitFull = "--junitxml=" + (Join-Path $ev "gate-pytest-junit.xml")
$junitNew = "--junitxml=" + (Join-Path $ev "gate-new-tests-junit.xml")
Step "pytest (editable install; README command)" "gate-pytest-full.log" { & $py -m pytest -p no:cacheprovider -m "not integration" -rfEs $junitFull }
Step "pytest Spec 11 tests" "gate-new-tests.log" {
    & $py -m pytest tests/test_packaging.py tests/test_cleanup.py tests/test_docs.py tests/test_settings.py tests/test_contracts.py `
        tests/test_dashboard_smoke.py tests/test_workflow.py -p no:cacheprovider -m "not integration" -rfEs $junitNew
}
Step "collector smoke (Spec 07; uvicorn collector.api:app launcher)" "gate-collector-smoke.log" { & $py (Join-Path $ev07 "scripts\collector_smoke.py") }
Step "golden snapshot (cji.mcp_servers)" "gate-golden.log" { & $py (Join-Path $ev "scripts\golden.py") (Join-Path $ev "golden-after.json") }
$g10 = (Get-FileHash (Join-Path $ev10 "golden-after.json")).Hash
$g11 = (Get-FileHash (Join-Path $ev "golden-after.json")).Hash
Note "golden identical to Spec 10: $($g10 -eq $g11)"

Step "ruff check (README command)" "gate-ruff.log" { & $py -m ruff check --no-cache --output-format concise }
Step "ruff check --statistics" "gate-ruff-stats.log" { & $py -m ruff check --no-cache --statistics }
Step "ruff check new code" "gate-ruff-new.log" {
    & $py -m ruff check --no-cache --output-format concise _cji_launcher.py main.py run_servers.py dashboard.py generate_diverse.py `
        tools/ingest_json.py tracker/snippet_generator.py settings collector src/cji/logs.py src/cji/dashboard_launcher.py `
        src/cji/collector/serve.py src/cji/__init__.py src/cji/tracker/__init__.py tests/test_packaging.py
}
Step "mypy (README command; strict overrides)" "gate-mypy.log" { & $py -m mypy --cache-dir "C:\Users\sovan\.kiro\s11_mypy_cache" }
Step "mypy --strict new modules" "gate-mypy-new-strict.log" {
    & $py -m mypy src/cji/logs.py src/cji/dashboard_launcher.py src/cji/collector/serve.py src/cji/settings/load.py --strict --follow-imports=silent --cache-dir "C:\Users\sovan\.kiro\s11_mypy_cache"
}
Step "mypy --strict workflow domain/runs.py" "gate-mypy-workflow-strict.log" { & $py -m mypy src/cji/workflow src/cji/domain/runs.py --strict --follow-imports=silent --cache-dir "C:\Users\sovan\.kiro\s11_mypy_cache" }
Step "mypy --strict reporting" "gate-mypy-reporting-strict.log" { & $py -m mypy src/cji/reporting --strict --follow-imports=silent --cache-dir "C:\Users\sovan\.kiro\s11_mypy_cache" }
Step "mypy --strict integrations" "gate-mypy-integrations-strict.log" { & $py -m mypy src/cji/integrations --strict --cache-dir "C:\Users\sovan\.kiro\s11_mypy_cache" }
Step "mypy --strict repositories" "gate-mypy-repositories-strict.log" { & $py -m mypy src/cji/repositories --strict --cache-dir "C:\Users\sovan\.kiro\s11_mypy_cache" }
Step "bandit -c pyproject.toml -r src (README command)" "gate-bandit.log" { & $py -m bandit -c pyproject.toml -r src -q }
Step "bandit -c pyproject.toml -r src (json)" "gate-bandit.json.log" { & $py -m bandit -c pyproject.toml -r src -f json -q }
Step "bandit -r . (Spec 10 scope, json)" "gate-bandit-all.json.log" { & $py -m bandit -r . -x "./.venv" -f json -q }

Step "old commands --help (launchers, from cji_agent/)" "gate-help-launchers.log" {
    $bad = 0
    foreach ($c in @("main.py", "run_servers.py", "generate_diverse.py", "tools/ingest_json.py", "tracker/snippet_generator.py")) {
        "---- python $c --help"; & $py $c --help; "exit=$LASTEXITCODE"; if ($LASTEXITCODE -ne 0) { $bad++ }
    }
    "---- python -m settings --help"; & $py -m settings --help; "exit=$LASTEXITCODE"; if ($LASTEXITCODE -ne 0) { $bad++ }
    "failures: $bad"; $global:LASTEXITCODE = $bad
}
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
Step "audit files: fields, secrets, correlation (Spec 08)" "gate-audit-check.log" { & $py (Join-Path $ev "scripts\audit_check.py") }
Step "workflow audit: steps, runs, kill/resume" "gate-audit-workflow.log" { & $py (Join-Path $ev "scripts\audit_workflow_check.py") }
Step "report contract and inertness (gate reports)" "gate-report-contract.log" { & $py (Join-Path $ev "scripts\report_contract_check.py") $gateStart }
Note "new report files in reports/: $(@(Get-ChildItem (Join-Path $app 'reports') -Filter '*.html').Count - $reportsBefore)"

Step "git diff --check (cr-at-eol)" "gate-diff-check.log" { git -C $repo -c core.whitespace=cr-at-eol diff --check }
Step "git diff --stat" "gate-diff-stat.log" { git -C $repo diff --stat }
Step "git status (tracked)" "gate-git-status.log" { git -C $repo status --porcelain --untracked-files=no }
Note "tracked events.parquet unchanged: $($hashBefore -eq (Get-FileHash $parquet).Hash)"
Copy-Item $env:CJI_CHECKPOINTS_DB (Join-Path $ev "gate-checkpoints.db") -ErrorAction SilentlyContinue
Copy-Item (Join-Path $home11 "reports") (Join-Path $ev "gate-clean-home-reports") -Recurse -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $tmp
CleanBuildOutput
Note "Spec 11 gate finished $(Get-Date -Format s)"
