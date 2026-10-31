# Spec 13 gate (T8, design §8): the frontend checks offline, the smoke test against the fixture API and against a
# real cji-api, then the Python suite (no Python change expected). Phase A installs packages (npm registry reachable);
# phase B runs in the protected environment: dead proxy and database URLs, dummy keys (Supabase is never contacted).
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$web  = Join-Path $repo "frontend"
$ev   = Join-Path $repo ".kiro\specs\13-nextjs-foundation\evidence"
$ev12 = Join-Path $repo ".kiro\specs\12-backend-api\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$scripts = Split-Path $py
$sum  = Join-Path $ev "gate-results.txt"
$tmp  = "C:\Users\sovan\.kiro\s13_gate_tmp"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
"Spec 13 gate started $(Get-Date -Format s)" | Set-Content $sum -Encoding utf8

function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-60} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum -Encoding utf8
}
function Note($text) { $text | Add-Content $sum -Encoding utf8 }
function Npm([string[]]$a) { & npm.cmd @a }
function Outcome($logName) {
    # Playwright's summary lines ("1 passed", "1 skipped", "1 failed"); a skipped smoke test is not a pass.
    $lines = Select-String -Path (Join-Path $ev $logName) -Pattern '^\s*\d+ (passed|failed|skipped|flaky)' | ForEach-Object { $_.Line.Trim() }
    return ($lines -join ", ")
}
function KillTree($p) { if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F *> $null } }
function Listening($ports) {
    $l = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    ($ports | ForEach-Object { $p = $_; "{0}:{1}" -f $p, $(if ($l | Where-Object LocalPort -eq $p) { "LISTEN" } else { "-" }) }) -join "  "
}

Set-Location $web
$env:NEXT_TELEMETRY_DISABLED = "1"; $env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
# ══ Phase A: clean install from the lockfile, audit (network) ══════════════════════════════════════════════════
Step "npm ci (package-lock.json)" "gate-npm-ci.log" { Npm @("ci", "--no-fund") }
Step "npm audit --omit=dev (runtime dependencies)" "gate-npm-audit-runtime.log" { Npm @("audit", "--omit=dev") }
Step "npm audit (all dependencies, json)" "gate-npm-audit.json.log" { Npm @("audit", "--json") }
Step "npm ls --omit=dev (runtime tree)" "gate-npm-ls-runtime.log" { Npm @("ls", "--omit=dev", "--depth=0") }

# ══ Protected environment from here on ═════════════════════════════════════════════════════════════════════════
$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"; $env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"; $env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:PYTHONIOENCODING = "utf-8"; $env:CI = "1"
$env:LLM_MODEL = "openai/gpt-oss-120b"; $env:CJI_LLM_PROVIDER = "none"; $env:JOURNEY_NAME = "user_onboarding"
Remove-Item Env:CJI_HOME, Env:PYTHONPATH, Env:CJI_TEST_DATABASE_URL -ErrorAction SilentlyContinue

# ══ Phase B: frontend checks (offline) ═════════════════════════════════════════════════════════════════════════
Step "api:check (types = cji_agent/openapi/v1.json)" "gate-api-check.log" { Npm @("run", "api:check") }
Step "typecheck (tsc --noEmit, strict)" "gate-typecheck.log" { Npm @("run", "typecheck") }
Step "lint (eslint, max-warnings 0)" "gate-lint.log" { Npm @("run", "lint") }
$junit = Join-Path $ev "gate-vitest-junit.xml"
Step "unit and component tests (vitest)" "gate-vitest.log" {
    & npx.cmd vitest run --reporter=default --reporter=junit --outputFile.junit=$junit
}
$env:CJI_SESSION_SECRET = "gate-only-session-secret-" + [guid]::NewGuid().ToString("N")
$env:CJI_API_BASE_URL = "http://127.0.0.1:18006"
Step "next build (production)" "gate-build.log" { & node node_modules/next/dist/bin/next build }
Step "bundle scan (.next/static: no secret, server variable, token)" "gate-bundle-scan.log" { Npm @("run", "bundle:scan") }
Step "browser smoke test (fixture API, installed Chrome)" "gate-e2e-fixture.log" { & npx.cmd playwright test }
Note "fixture smoke outcome: $(Outcome "gate-e2e-fixture.log")"
Note "ports after fixture smoke: $(Listening @(3100, 18006))"

# ══ Phase C: the same smoke test against a real cji-api (demo data, Spec 12 gate runs and reports) ═══════════
$apiHome = Join-Path $tmp "api"; New-Item -ItemType Directory -Force -Path $apiHome | Out-Null
Copy-Item (Join-Path $ev12 "gate-checkpoints.db") (Join-Path $apiHome "checkpoints.db")
$env:CJI_CHECKPOINTS_DB = Join-Path $apiHome "checkpoints.db"
$env:CJI_API_TOKENS_FILE = Join-Path $apiHome "api_tokens.json"
$env:CJI_API_CORS_ORIGINS = "https://app.example.test"
$env:CJI_API_CURSOR_SECRET = "gate-only-cursor-secret-" + [guid]::NewGuid().ToString("N")
Step "cji-api-token create (viewer, user_onboarding)" "gate-live-token.log" {
    & (Join-Path $scripts "cji-api-token.exe") --file $env:CJI_API_TOKENS_FILE create --label gate-frontend --role viewer --journey user_onboarding
}
$token = (Select-String -Path (Join-Path $ev "gate-live-token.log") -Pattern "^\s*(cji_api_\S+)" | Select-Object -First 1).Matches[0].Groups[1].Value
(Get-Content (Join-Path $ev "gate-live-token.log")) -replace "cji_api_\S+", "cji_api_<redacted>" | Set-Content (Join-Path $ev "gate-live-token.log")
$api = Start-Process -FilePath (Join-Path $scripts "cji-api.exe") -WorkingDirectory $app -PassThru -WindowStyle Hidden `
       -RedirectStandardOutput "$tmp\cji-api.out.log" -RedirectStandardError "$tmp\cji-api.err.log"
for ($i = 0; $i -lt 40; $i++) { Start-Sleep 1; & curl.exe -s --noproxy "*" -o NUL -w "%{http_code}" http://127.0.0.1:8006/api/v1/health | Set-Variable code; if ($code -eq "200") { break } }
Note "cji-api health before live smoke: $code"
$env:CJI_API_BASE_URL = "http://127.0.0.1:8006"
$env:E2E_LIVE_API_URL = "http://127.0.0.1:8006"; $env:E2E_LIVE_TOKEN = $token
Step "browser smoke test (live cji-api; fault step skipped)" "gate-e2e-live.log" { & npx.cmd playwright test }
Note "live smoke outcome: $(Outcome "gate-e2e-live.log")"
Remove-Item Env:E2E_LIVE_API_URL, Env:E2E_LIVE_TOKEN
KillTree $api; Start-Sleep 2
Note "ports after live smoke: $(Listening @(3100, 8006))"
$apiLog = (Get-Content "$tmp\cji-api.out.log", "$tmp\cji-api.err.log" -ErrorAction SilentlyContinue) -join "`n"
Note "cji-api log holds the token: $($apiLog.Contains($token))"
$apiLog | Set-Content (Join-Path $ev "gate-live-api-server.log") -Encoding utf8
Remove-Item Env:CJI_CHECKPOINTS_DB, Env:CJI_API_TOKENS_FILE, Env:CJI_API_CORS_ORIGINS, Env:CJI_API_CURSOR_SECRET, Env:CJI_SESSION_SECRET, Env:CJI_API_BASE_URL

# ══ Phase D: Python app unchanged; Streamlit kept ══════════════════════════════════════════════════════════════
Set-Location $app
$env:CJI_CHECKPOINTS_DB = Join-Path $tmp "pytest_checkpoints.db"
$junitPy = "--junitxml=" + (Join-Path $ev "gate-pytest-junit.xml")
Step "pytest (Python suite, not integration)" "gate-pytest.log" { & $py -m pytest -p no:cacheprovider -m "not integration" -rfEs $junitPy }
Step "ruff check" "gate-ruff.log" { & $py -m ruff check --no-cache --output-format concise }
Step "OpenAPI snapshot matches the API" "gate-openapi-snapshot.log" { & $py -m cji.api.openapi_snapshot --check }
Step "cji-dashboard --help (Streamlit kept)" "gate-dashboard-help.log" { & (Join-Path $scripts "cji-dashboard.exe") --help }

Set-Location $repo
Step "git diff --check (cr-at-eol)" "gate-diff-check.log" { git -C $repo -c core.whitespace=cr-at-eol diff --check }
Step "git status (tracked)" "gate-git-status.log" { git -C $repo status --porcelain --untracked-files=no }
Step "untracked frontend files (not ignored)" "gate-frontend-files.log" { git -C $repo ls-files --others --exclude-standard -- frontend }
Remove-Item -Recurse -Force $tmp
Note "Spec 13 gate finished $(Get-Date -Format s)"
