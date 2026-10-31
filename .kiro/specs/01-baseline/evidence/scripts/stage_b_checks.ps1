# Stage B: static checks + test suite. Report-only; changes no tracked file.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\01-baseline\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$sum  = Join-Path $ev "stage-b-summary.txt"
"Stage B started $(Get-Date -Format s)" | Set-Content $sum

function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-34} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum
}

Set-Location $app
git -C $repo status --short *> (Join-Path $ev "b0-git-status-before.log")

# Needs network: dependency advisory lookup sends package names/versions only.
Step "pip-audit (pinned app deps)" "b1-pip-audit.log" {
    & $py -m pip_audit -r (Join-Path $ev "constraints-baseline-2026-10-27.txt") --no-deps --disable-pip --progress-spinner off
}

# Everything below runs offline with dummy credentials.
$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
$env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:CJI_ADMIN_KEY = "baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE = "1"
"protected env applied: proxy=127.0.0.1:9, dummy keys, dead DATABASE_URL" | Add-Content $sum

Step "pytest --collect-only" "b2-pytest-collect.log" {
    & $py -m pytest tests -p no:cacheprovider --collect-only -q
}
Step "pytest -m 'not integration'" "b3-pytest-run.log" {
    & $py -m pytest tests -p no:cacheprovider -m "not integration" -rfE --junitxml=(Join-Path $ev "b3-pytest-junit.xml")
}
Step "ruff check --statistics" "b4-ruff-stats.log" { & $py -m ruff check . --no-cache --statistics }
Step "ruff check (full list)" "b4-ruff-full.log" { & $py -m ruff check . --no-cache --output-format concise }
Step "mypy ." "b5-mypy.log" {
    & $py -m mypy . --exclude "(^|/)\.venv/" --cache-dir "C:\Users\sovan\.kiro\mypy_cache_baseline"
}
Step "bandit -r ." "b6-bandit.log" { & $py -m bandit -r . -x "./.venv" -f txt }

git -C $repo status --short *> (Join-Path $ev "b7-git-status-after.log")
"git status unchanged: $((Get-Content (Join-Path $ev 'b0-git-status-before.log') -Raw) -eq (Get-Content (Join-Path $ev 'b7-git-status-after.log') -Raw))" | Add-Content $sum
"--- pytest tail ---" | Add-Content $sum
Get-Content (Join-Path $ev "b3-pytest-run.log") -Tail 25 | Add-Content $sum
"--- collect tail ---" | Add-Content $sum
Get-Content (Join-Path $ev "b2-pytest-collect.log") -Tail 3 | Add-Content $sum
"--- ruff stats ---" | Add-Content $sum
Get-Content (Join-Path $ev "b4-ruff-stats.log") | Select-Object -Last 40 | Add-Content $sum
"--- mypy tail ---" | Add-Content $sum
Get-Content (Join-Path $ev "b5-mypy.log") -Tail 3 | Add-Content $sum
"--- bandit totals ---" | Add-Content $sum
Select-String -Path (Join-Path $ev "b6-bandit.log") -Pattern "Total lines|Low:|Medium:|High:|Undefined:" | ForEach-Object { $_.Line.Trim() } | Add-Content $sum
"--- pip-audit tail ---" | Add-Content $sum
Get-Content (Join-Path $ev "b1-pip-audit.log") -Tail 30 | Add-Content $sum
"Stage B finished $(Get-Date -Format s)" | Add-Content $sum
