# Spec 15 gate (T15, design §18). Phase A needs the network (npm ci, dependency scan). From phase B on the protected
# environment applies: dead proxy and database URLs, dummy LLM keys, LLM provider "none". The real
# SUPABASE_DATABASE_URL in cji_agent/.env is never read: both database variables are set to a dead URL, and every
# database the gate uses is a throwaway pgserver instance on loopback.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$web  = Join-Path $repo "frontend"
$ev   = Join-Path $repo ".kiro\specs\15-production-hardening\evidence"
$rel  = Join-Path $ev "release"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$scripts = Split-Path $py
$sum  = Join-Path $ev "gate-results.txt"
$tmp  = "C:\Users\sovan\.kiro\s15_gate_tmp"
foreach ($d in $tmp, $rel) { if (Test-Path $d) { Remove-Item -Recurse -Force $d } }
New-Item -ItemType Directory -Force -Path $tmp, (Join-Path $rel "ci") | Out-Null
"Spec 15 gate started $(Get-Date -Format s)" | Set-Content $sum -Encoding utf8
function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-66} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum -Encoding utf8
}
function Note($text) { $text | Add-Content $sum -Encoding utf8 }
function Last($logName, $n = 1) { (Get-Content (Join-Path $ev $logName) -ErrorAction SilentlyContinue | Where-Object { $_.Trim() } | Select-Object -Last $n) -join " / " }
Set-Location $repo
$env:NEXT_TELEMETRY_DISABLED = "1"; $env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = "1"
# == Phase A: clean install from the lockfile; dependency scan (network) =====================================
Set-Location $web
Step "npm ci (package-lock.json)" "gate-npm-ci.log" { & npm.cmd ci --no-fund }
Set-Location $repo
Step "dependency scan: pip-audit (requirements.lock) + npm audit" "gate-deps.log" { & $py ci\scans.py deps --out (Join-Path $rel "ci") }
Note "dependency scan: $(Last 'gate-deps.log')"
# == Protected environment from here on =======================================================================
$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"; $env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://gate:gate@127.0.0.1:1/gate"; $env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "gate-offline-dummy"; $env:ANTHROPIC_API_KEY = "gate-offline-dummy"
$env:OPENAI_API_KEY = "gate-offline-dummy"; $env:LANGCHAIN_API_KEY = "gate-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:PYTHONIOENCODING = "utf-8"; $env:CI = "1"
$env:LLM_MODEL = "openai/gpt-oss-120b"; $env:CJI_LLM_PROVIDER = "none"; $env:JOURNEY_NAME = "user_onboarding"
Remove-Item Env:CJI_HOME, Env:PYTHONPATH, Env:CJI_TEST_DATABASE_URL, Env:CJI_CHECKPOINTS_DB, Env:CJI_ADMIN_KEY -ErrorAction SilentlyContinue
# == Phase B: CI runner (format, lint, types, unit, integration incl. recovery suite, browser, secret scan) =======
Step "ci/run_ci.py (all stages)" "gate-ci.log" { & $py ci\run_ci.py }
Copy-Item -Recurse -Force (Join-Path $repo "ci\out\*") (Join-Path $rel "ci")
Copy-Item -Force (Join-Path $repo "ci\out\summary.md") (Join-Path $ev "ci-summary.md") -ErrorAction SilentlyContinue
Note "CI: $(Last 'gate-ci.log')"
if (Test-Path (Join-Path $rel "ci\recovery.jsonl")) {
    Copy-Item -Force (Join-Path $rel "ci\recovery.jsonl") (Join-Path $rel "recovery.jsonl")
    Step "recovery.md from the recovery suite's log" "gate-recovery-md.log" { & $py (Join-Path $ev "scripts\recovery_md.py") (Join-Path $rel "recovery.jsonl") (Join-Path $ev "recovery.md") }
}
# == Phase C: live deployment with canary markers ===============================================================
Step "live phase (logs, metrics, trace, audit, rotation, readiness, live browser tests)" "gate-live.log" {
    & $py (Join-Path $ev "scripts\live_spec15.py") --work (Join-Path $tmp "live") --out $rel
}
Copy-Item -Force (Join-Path $rel "live.md") (Join-Path $ev "live.md") -ErrorAction SilentlyContinue
Note "live: $(Last 'gate-live.log' 3)"
# == Phase C2: Spec 14 parity on the new code (demo data; CLI run and API run vs checkpoint, last_run.json, engine) ==
Step "parity check (Spec 14 script on 0.15.0)" "gate-parity.log" {
    & $py (Join-Path $ev "scripts\parity_spec15.py") --work (Join-Path $tmp "parity") --out $rel
}
Note "parity: $(Last 'gate-parity.log')"
# == Phase E: rollback drill (upgrade, configuration/schema/release rollback, restore, old frontend) =============
Step "ci/rollback_drill.py" "gate-rollback-drill.log" {
    & $py ci\rollback_drill.py --old-wheel (Join-Path $ev "wheels\cji_agent-0.11.0-py3-none-any.whl") `
        --old-frontend (Join-Path $ev "pre-spec15-frontend") --work (Join-Path $tmp "drill") --out $rel
}
Copy-Item -Force (Join-Path $rel "rollback-drill.md") (Join-Path $ev "rollback-drill.md") -ErrorAction SilentlyContinue
Note "rollback drill: $(Last 'gate-rollback-drill.log')"
# == Phase F: canary scan over the live phase's logs, audit, reports, databases, bundle, HTTP responses ==========
$paths = Get-Content (Join-Path $rel "canary-paths.txt") -ErrorAction SilentlyContinue | Where-Object { Test-Path $_ }
Step "canary scan (ci/sensitive_scan.py)" "gate-canary.log" {
    & $py ci\sensitive_scan.py --markers (Join-Path $rel "canary-markers.json") --paths @paths `
        --user-allowed "*/data/ingestion_uploads/*" --report (Join-Path $rel "canary.json")
}
Remove-Item -Force (Join-Path $rel "canary-markers.json") -ErrorAction SilentlyContinue   # throwaway values; not kept
Note "canary scan: $(Last 'gate-canary.log')"
# == Phase G: release check, contract and entry points, repository state =======================================
Step "release check (docs/release-checklist.md)" "gate-release-check.log" { & $py ci\release_check.py --evidence $rel --json (Join-Path $rel "release-check.json") }
Note "release check: $(Last 'gate-release-check.log')"
Set-Location $app
Step "OpenAPI snapshot matches the API" "gate-openapi-snapshot.log" { & $py -m cji.api.openapi_snapshot --check }
Step "cji --help (CLI kept)" "gate-cli-help.log" { & (Join-Path $scripts "cji.exe") --help }
Step "cji-dashboard --help (Streamlit kept)" "gate-dashboard-help.log" { & (Join-Path $scripts "cji-dashboard.exe") --help }
Set-Location $repo
Step "git diff --check (cr-at-eol)" "gate-diff-check.log" { git -C $repo -c core.whitespace=cr-at-eol diff --check }
Step "git status (tracked)" "gate-git-status.log" { git -C $repo status --porcelain --untracked-files=no }
Note "ports still listening (8000-8006, 3100): $((Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { @(8000,8001,8002,8003,8004,8005,8006,3100) -contains $_.LocalPort }).Count)"
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Note "Spec 15 gate finished $(Get-Date -Format s)"
