# Stage B2: rerun the checks whose harness was wrong in Stage B.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\01-baseline\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$sum  = Join-Path $ev "stage-b2-summary.txt"
"Stage B2 started $(Get-Date -Format s)" | Set-Content $sum

function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-40} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum
}
Set-Location $app

# Clean constraints: keep only name==version lines.
$cons = Join-Path $ev "constraints-baseline-2026-10-27.txt"
Get-Content (Join-Path $ev "a5-freeze.log") | Where-Object { $_ -match '^[A-Za-z0-9_.\-\[\]]+==\S+$' } | Set-Content $cons -Encoding ascii
"constraints lines: $((Get-Content $cons).Count)" | Add-Content $sum

Step "pip-audit (pinned app deps)" "b1-pip-audit.log" {
    & $py -m pip_audit -r $cons --no-deps --disable-pip --progress-spinner off
}

# Offline, dummy credentials from here on.
$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
$env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:CJI_ADMIN_KEY = "baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE = "1"

$junit = Join-Path $ev "b3-pytest-junit.xml"
Step "pytest not-integration (continue on collect err)" "b3-pytest-run.log" {
    & $py -m pytest tests -p no:cacheprovider -m "not integration" -rfE "--continue-on-collection-errors" "--junitxml=$junit"
}
Step "pytest integration only (dummy keys, offline)" "b3b-pytest-integration.log" {
    & $py -m pytest tests -p no:cacheprovider -m "integration" -rfE "--continue-on-collection-errors"
}
Step "ruff --show-settings (config source)" "b4-ruff-settings.log" { & $py -m ruff check . --show-settings }
Step "ruff check --isolated --statistics" "b4-ruff-isolated-stats.log" { & $py -m ruff check . --isolated --no-cache --statistics }
Step "bandit -r . (json)" "b6-bandit.json.log" { & $py -m bandit -r . -x "./.venv" -f json -q }

"--- pytest tail ---" | Add-Content $sum
Get-Content (Join-Path $ev "b3-pytest-run.log") -Tail 30 | Add-Content $sum
"--- integration tail ---" | Add-Content $sum
Get-Content (Join-Path $ev "b3b-pytest-integration.log") -Tail 6 | Add-Content $sum
"--- junit totals ---" | Add-Content $sum
if (Test-Path $junit) {
    [xml]$x = Get-Content $junit
    foreach ($s in $x.testsuites.testsuite) { "tests={0} failures={1} errors={2} skipped={3} time={4}" -f $s.tests, $s.failures, $s.errors, $s.skipped, $s.time | Add-Content $sum }
}
"--- ruff config source ---" | Add-Content $sum
Select-String -Path (Join-Path $ev "b4-ruff-settings.log") -Pattern "Settings path|Resolved settings for" | Select-Object -First 3 | ForEach-Object { $_.Line.Trim() } | Add-Content $sum
"--- ruff isolated ---" | Add-Content $sum
Get-Content (Join-Path $ev "b4-ruff-isolated-stats.log") -Tail 12 | Add-Content $sum
"--- bandit totals ---" | Add-Content $sum
$bj = (Get-Content (Join-Path $ev "b6-bandit.json.log") -Raw)
$start = $bj.IndexOf("{")
if ($start -ge 0) {
    $b = $bj.Substring($start) | ConvertFrom-Json
    $t = $b.metrics._totals
    "HIGH={0} MEDIUM={1} LOW={2} loc={3}" -f $t.'SEVERITY.HIGH', $t.'SEVERITY.MEDIUM', $t.'SEVERITY.LOW', $t.loc | Add-Content $sum
    $b.results | Group-Object test_id | Sort-Object Count -Descending | ForEach-Object { "  {0} x{1} ({2})" -f $_.Name, $_.Count, $_.Group[0].issue_severity } | Add-Content $sum
}
"--- pip-audit ---" | Add-Content $sum
Get-Content (Join-Path $ev "b1-pip-audit.log") | Where-Object { $_ -notmatch 'NativeCommandError|CategoryInfo|At C:|^\s*\+|^\s*~' } | Select-Object -Last 30 | Add-Content $sum
git -C $repo status --short *> (Join-Path $ev "b7-git-status-after.log")
"git status unchanged vs start: $((Get-Content (Join-Path $ev 'b0-git-status-before.log') -Raw) -eq (Get-Content (Join-Path $ev 'b7-git-status-after.log') -Raw))" | Add-Content $sum
"Stage B2 finished $(Get-Date -Format s)" | Add-Content $sum
