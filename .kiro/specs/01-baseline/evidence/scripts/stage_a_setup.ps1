# Stage A: branch + reproducible Python 3.12 environment (outside the repo).
# Changes no tracked file. Logs go to the Spec evidence folder.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\01-baseline\evidence"
$venv = "C:\Users\sovan\.venvs\cji-baseline-312"
$py   = Join-Path $venv "Scripts\python.exe"
$sum  = Join-Path $ev "stage-a-summary.txt"
"Stage A started $(Get-Date -Format s)" | Set-Content $sum

function Step($label, $logName, [scriptblock]$cmd) {
    $log = Join-Path $ev $logName
    $t0 = Get-Date
    & $cmd *> $log
    $code = $LASTEXITCODE
    "{0,-48} exit={1,-4} {2,6:N0}s  log={3}" -f $label, $code, ((Get-Date)-$t0).TotalSeconds, $logName | Add-Content $sum
    return $code
}

Set-Location $repo
Step "git switch -c phase-01-baseline" "a1-git-branch.log" { git switch -c phase-01-baseline } | Out-Null
"branch now: $(git branch --show-current)  HEAD: $(git rev-parse --short HEAD)" | Add-Content $sum

Step "uv python install 3.12" "a2-uv-python-install.log" { uv python install 3.12 } | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $venv) | Out-Null
Step "uv venv --python 3.12 --seed" "a3-uv-venv.log" { uv venv $venv --python 3.12 --seed } | Out-Null
"venv python: $(& $py --version 2>&1)" | Add-Content $sum

Set-Location $app
$rc = Step "uv pip install -r requirements.txt -r requirements-dev.txt" "a4-install-app-deps.log" {
    uv pip install --python $py -r requirements.txt -r requirements-dev.txt
}
Step "uv pip freeze (app deps only)" "a5-freeze.log" { uv pip freeze --python $py } | Out-Null
Copy-Item (Join-Path $ev "a5-freeze.log") (Join-Path $ev "constraints-baseline-2026-10-27.txt")
"installed packages: $((Get-Content (Join-Path $ev 'a5-freeze.log') | Where-Object { $_ -match '==' }).Count)" | Add-Content $sum

Step "uv pip install ruff mypy bandit pip-audit (tools)" "a6-install-tools.log" {
    uv pip install --python $py ruff mypy bandit pip-audit
} | Out-Null
"tool versions:" | Add-Content $sum
foreach ($t in "ruff","mypy","bandit","pip_audit") {
    "  $t : $(& $py -m $t --version 2>&1 | Select-Object -First 1)" | Add-Content $sum
}
"Stage A finished $(Get-Date -Format s)" | Add-Content $sum
