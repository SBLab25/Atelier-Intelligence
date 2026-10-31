# Spec 14 gate (T11, design §8). Phase A installs packages and audits (network). From phase B on the protected
# environment applies: dead proxy and database URLs, dummy LLM keys, LLM provider "none" (fallback outcomes).
# The real SUPABASE_DATABASE_URL in cji_agent/.env is never read: both database variables are set to a dead URL.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$web  = Join-Path $repo "frontend"
$ev   = Join-Path $repo ".kiro\specs\14-frontend-parity\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$scripts = Split-Path $py
$sum  = Join-Path $ev "gate-results.txt"
$tmp  = "C:\Users\sovan\.kiro\s14_gate_tmp"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
"Spec 14 gate started $(Get-Date -Format s)" | Set-Content $sum -Encoding utf8
function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-66} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum -Encoding utf8
}
function Note($text) { $text | Add-Content $sum -Encoding utf8 }
function Npm([string[]]$a) { & npm.cmd @a }
function Outcome($logName) {
    $lines = Select-String -Path (Join-Path $ev $logName) -Pattern '^\s*\d+ (passed|failed|skipped|flaky)' | ForEach-Object { $_.Line.Trim() }
    return ($lines -join ", ")
}
function KillTree($p) { if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F *> $null } }
function Listening($ports) {
    $l = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    ($ports | ForEach-Object { $p = $_; "{0}:{1}" -f $p, $(if ($l | Where-Object LocalPort -eq $p) { "LISTEN" } else { "-" }) }) -join "  "
}
function WaitPorts($ports, $seconds) {
    for ($i = 0; $i -lt $seconds; $i += 2) {
        Start-Sleep 2
        if (((Listening $ports) -split 'LISTEN').Count -eq ($ports.Count + 1)) { return }
    }
}
Set-Location $web
$env:NEXT_TELEMETRY_DISABLED = "1"; $env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"

# == Phase A: clean install from the lockfile, audit (network) ===============================================
Step "npm ci (package-lock.json)" "gate-npm-ci.log" { Npm @("ci", "--no-fund") }
Step "npm audit (all dependencies)" "gate-npm-audit.log" { Npm @("audit") }

# == Protected environment from here on =======================================================================
$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"; $env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"; $env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:PYTHONIOENCODING = "utf-8"; $env:CI = "1"
$env:LLM_MODEL = "openai/gpt-oss-120b"; $env:CJI_LLM_PROVIDER = "none"; $env:JOURNEY_NAME = "user_onboarding"
$env:CJI_ADMIN_KEY = "baseline-local-only"
Remove-Item Env:CJI_HOME, Env:PYTHONPATH, Env:CJI_TEST_DATABASE_URL, Env:CJI_CHECKPOINTS_DB -ErrorAction SilentlyContinue

# == Phase B: frontend checks against the fixture API (offline) ==============================================
Step "api:check (types = cji_agent/openapi/v1.json)" "gate-api-check.log" { Npm @("run", "api:check") }
Step "typecheck (tsc --noEmit, strict)" "gate-typecheck.log" { Npm @("run", "typecheck") }
Step "lint (eslint, max-warnings 0)" "gate-lint.log" { Npm @("run", "lint") }
$junit = Join-Path $ev "gate-vitest-junit.xml"
Step "unit and component tests (vitest)" "gate-vitest.log" { & npx.cmd vitest run --reporter=default --reporter=junit --outputFile.junit=$junit }
$env:CJI_SESSION_SECRET = "gate-only-session-secret-" + [guid]::NewGuid().ToString("N")
$env:CJI_API_BASE_URL = "http://127.0.0.1:18006"
Step "next build (production)" "gate-build.log" { & node node_modules/next/dist/bin/next build }
Step "bundle scan (.next/static: no secret, server variable, token)" "gate-bundle-scan.log" { Npm @("run", "bundle:scan") }
Step "browser tests (fixture API: smoke + feature specs)" "gate-e2e-fixture.log" { & npx.cmd playwright test }
Note "fixture browser tests: $(Outcome "gate-e2e-fixture.log")"

# == Phase C: live parity (real cji-api, MCP servers, demo data, offline LLM) ================================
$home14 = Join-Path $tmp "home"; New-Item -ItemType Directory -Force -Path (Join-Path $home14 "data") | Out-Null
Copy-Item (Join-Path $app "data\events.parquet") (Join-Path $home14 "data\events.parquet")
$env:CJI_HOME = $home14
$env:CJI_CHECKPOINTS_DB = Join-Path $home14 "data\checkpoints.db"
$env:CJI_API_TOKENS_FILE = Join-Path $home14 "data\api_tokens.json"
$env:CJI_API_CORS_ORIGINS = "https://app.example.test"
$env:CJI_API_CURSOR_SECRET = "gate-only-cursor-secret-" + [guid]::NewGuid().ToString("N")
$servers = Start-Process -FilePath (Join-Path $scripts "cji-servers.exe") -WorkingDirectory $tmp -PassThru -WindowStyle Hidden `
           -RedirectStandardOutput "$tmp\servers.out.log" -RedirectStandardError "$tmp\servers.err.log"
WaitPorts @(8001,8002,8003,8004,8005) 80
Note "MCP servers: $(Listening @(8001,8002,8003,8004,8005))"
Step "cli run: cji --run --auto-approve (writes last_run.json)" "gate-cli-run.log" {
    Push-Location $tmp; & (Join-Path $scripts "cji.exe") --mode demo --run --auto-approve; $c = $LASTEXITCODE; Pop-Location; $global:LASTEXITCODE = $c
}
$cliRun = (Select-String -Path (Join-Path $ev "gate-cli-run.log") -Pattern "Thread ID:\s*([0-9a-f-]{36})" | Select-Object -First 1).Matches[0].Groups[1].Value
Note "cli run id: $cliRun"
$tokens = @{}
foreach ($role in "viewer", "operator") {
    Step "cji-api-token create ($role)" "gate-live-token-$role.log" {
        & (Join-Path $scripts "cji-api-token.exe") --file $env:CJI_API_TOKENS_FILE create --label "gate-$role" --role $role --journey user_onboarding
    }
    $log = Join-Path $ev "gate-live-token-$role.log"
    $tokens[$role] = (Select-String -Path $log -Pattern "^\s*(cji_api_\S+)" | Select-Object -First 1).Matches[0].Groups[1].Value
    (Get-Content $log) -replace "cji_api_\S+", "cji_api_<redacted>" | Set-Content $log
}
$api = Start-Process -FilePath (Join-Path $scripts "cji-api.exe") -WorkingDirectory $tmp -PassThru -WindowStyle Hidden `
       -RedirectStandardOutput "$tmp\cji-api.out.log" -RedirectStandardError "$tmp\cji-api.err.log"
for ($i = 0; $i -lt 40; $i++) { Start-Sleep 1; & curl.exe -s --noproxy "*" -o NUL -w "%{http_code}" http://127.0.0.1:8006/api/v1/health | Set-Variable code; if ($code -eq "200") { break } }
Note "cji-api health: $code"
$env:CJI_API_BASE_URL = "http://127.0.0.1:8006"
$env:E2E_LIVE_API_URL = "http://127.0.0.1:8006"; $env:E2E_LIVE_TOKEN = $tokens["viewer"]; $env:E2E_LIVE_OPERATOR_TOKEN = $tokens["operator"]
Step "browser tests (live cji-api: smoke + live.spec)" "gate-e2e-live.log" { & npx.cmd playwright test smoke.spec.ts live.spec.ts }
Note "live browser tests: $(Outcome "gate-e2e-live.log")"
Step "runs after the live tests (API)" "gate-live-runs.log" {
    & curl.exe -s --noproxy "*" -H "Authorization: Bearer $($tokens['operator'])" "http://127.0.0.1:8006/api/v1/runs?limit=20"
}
$runs = (Get-Content (Join-Path $ev "gate-live-runs.log") -Raw | ConvertFrom-Json).data
$apiRun = ($runs | Where-Object { $_.status -eq "completed" -and $_.run_id -ne $cliRun } | Select-Object -First 1).run_id
Note "api run id (started and approved in the browser): $apiRun"
Set-Location $app
Step "parity check (API = CLI = checkpoint = last_run.json; API = engine)" "gate-parity.log" {
    & $py (Join-Path $ev "scripts\parity_check.py") --api http://127.0.0.1:8006 --token $tokens["operator"] --run $apiRun `
        --cli-run $cliRun --out (Join-Path $ev "parity")
}
Note "parity: $((Get-Content (Join-Path $ev 'parity\parity.txt') -ErrorAction SilentlyContinue | Select-Object -Last 1))"
Remove-Item Env:E2E_LIVE_API_URL, Env:E2E_LIVE_TOKEN, Env:E2E_LIVE_OPERATOR_TOKEN
KillTree $api; KillTree $servers; Start-Sleep 2
Note "ports after live phase: $(Listening @(3100, 8006, 8001, 8002, 8003, 8004, 8005))"
$apiLog = (Get-Content "$tmp\cji-api.out.log", "$tmp\cji-api.err.log" -ErrorAction SilentlyContinue) -join "`n"
Note "cji-api log holds a token: $($apiLog.Contains($tokens['viewer']) -or $apiLog.Contains($tokens['operator']))"
$apiLog | Set-Content (Join-Path $ev "gate-live-api-server.log") -Encoding utf8
Note "uploads left in CJI_HOME/data/ingestion_uploads: $(@(Get-ChildItem (Join-Path $home14 'data\ingestion_uploads') -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike '*.meta.json' }).Count) data file(s)"
Remove-Item Env:CJI_HOME, Env:CJI_CHECKPOINTS_DB, Env:CJI_API_TOKENS_FILE, Env:CJI_API_CORS_ORIGINS, Env:CJI_API_CURSOR_SECRET, Env:CJI_SESSION_SECRET, Env:CJI_API_BASE_URL

# == Phase D: Python suite and static checks ==================================================================
Set-Location $app
$env:CJI_CHECKPOINTS_DB = Join-Path $tmp "pytest_checkpoints.db"
$junitPy = "--junitxml=" + (Join-Path $ev "gate-pytest-junit.xml")
Step "pytest (Python suite, not integration)" "gate-pytest.log" { & $py -m pytest -p no:cacheprovider -m "not integration" -rfEs $junitPy }
Step "ruff check" "gate-ruff.log" { & $py -m ruff check --no-cache --output-format concise }
Step "mypy (project config)" "gate-mypy.log" { & $py -m mypy --cache-dir "$tmp\mypy_cache" }
Step "mypy --strict (api, services, analytics, http, workflow index)" "gate-mypy-strict.log" {
    & $py -m mypy src/cji/api src/cji/services src/cji/analytics src/cji/http src/cji/workflow/index.py --strict --follow-imports=silent --cache-dir "$tmp\mypy_cache"
}
Step "bandit -c pyproject.toml -r src" "gate-bandit.log" { & $py -m bandit -c pyproject.toml -r src -q }
Step "OpenAPI snapshot matches the API" "gate-openapi-snapshot.log" { & $py -m cji.api.openapi_snapshot --check }
Step "Streamlit SQL vs engine (report only)" "gate-streamlit-diff.log" { & $py (Join-Path $ev "scripts\streamlit_diff.py") --out (Join-Path $ev "parity") }
Step "cji-dashboard --help (Streamlit kept)" "gate-dashboard-help.log" { & (Join-Path $scripts "cji-dashboard.exe") --help }
Step "cji --help (CLI kept)" "gate-cli-help.log" { & (Join-Path $scripts "cji.exe") --help }
Set-Location $repo
Step "git diff --check (cr-at-eol)" "gate-diff-check.log" { git -C $repo -c core.whitespace=cr-at-eol diff --check }
Step "git status (tracked)" "gate-git-status.log" { git -C $repo status --porcelain --untracked-files=no }
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Note "Spec 14 gate finished $(Get-Date -Format s)"
