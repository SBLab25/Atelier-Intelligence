$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$py   = Join-Path $app ".venv\Scripts\python.exe"
$env:PYTHONDONTWRITEBYTECODE = "1"

function Run($label, [scriptblock]$cmd, $where) {
    Push-Location $where
    "=== $label"
    "cwd: $where"
    $out = & $cmd 2>&1 | ForEach-Object { "$_" }
    "exit: $LASTEXITCODE"
    $out | Select-Object -Last 12 | ForEach-Object { "  | $_" }
    Pop-Location
}

Run "venv python --version" { & $py --version } $app
Run "venv pip --version" { & $py -m pip --version } $app
Run "pytest (CI-safe subset)" { & $py -m pytest tests -p no:cacheprovider -m "not integration" } $app
Run "ruff check ." { & $py -m ruff check . } $app
Run "mypy ." { & $py -m mypy . } $app
Run "pyright" { & $py -m pyright } $app
Run "bandit -r ." { & $py -m bandit -r . } $app
Run "pip-audit" { & $py -m pip_audit } $app
Run "python syntax parse (ast, no bytecode)" { & $py "C:\Users\sovan\.kiro\baseline_ast.py" } $app
Run "node --version" { node --version } $app
Run "npm --version" { cmd /c "npm --version" } $app
Run "node --check tracker/tracker.js" { node --check tracker/tracker.js } $app
Run "node --check snippets/useCJITracker.js" { node --check snippets/useCJITracker.js } $app
Run "git diff --check" { git diff --check } $repo
Run "py launcher interpreters" { cmd /c "py -0p" } $repo
"=== tracked-file facts"
Push-Location $repo
"Dataset tracked files: " + (git ls-files -- Dataset | Measure-Object).Count
"cji_agent/reports tracked files: " + (git ls-files -- cji_agent/reports | Measure-Object).Count
"cji_agent/data tracked files: " + ((git ls-files -- cji_agent/data) -join ', ')
"graphify-out ignored? " + [bool](git check-ignore graphify-out)
Pop-Location
"=== done"
