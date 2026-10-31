$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
Set-Location $app
foreach ($t in "uv","pnpm","yarn","psql","docker","npx") {
    $c = Get-Command $t -ErrorAction SilentlyContinue
    if ($c) {
        $v = (& cmd /c "$t --version 2>&1" | Select-Object -First 1)
        "$t : present  $v"
    } else { "$t : NOT FOUND on PATH" }
}
"--- playwright (python) ---"
& .\.venv\Scripts\python.exe -c "import importlib.util as u; print('playwright python:', 'present' if u.find_spec('playwright') else 'absent')"
"--- cji_agent/data (names only) ---"
Get-ChildItem -Force data | ForEach-Object { "{0}{1}  {2}" -f $_.Name, ($(if ($_.PSIsContainer) {'/'} else {''})), $_.Length }
"--- cji_agent/reports (count + first 3 names) ---"
$r = Get-ChildItem -File reports -ErrorAction SilentlyContinue
"count: $($r.Count)"
$r | Select-Object -First 3 | ForEach-Object { $_.Name }
"--- report filename pattern in code ---"
Select-String -Path mcp_servers\report_server.py -Pattern 'cji_report' | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line.Trim() }
"--- output-mode flag anywhere? ---"
(Select-String -Path *.py, mcp_servers\*.py -Pattern 'output-mode|output_mode' -ErrorAction SilentlyContinue | Measure-Object).Count
"--- generate-data output path control ---"
Select-String -Path main.py -Pattern 'generate_demo_data\(' | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line.Trim() }
"--- useCJITracker.js first lines ---"
Get-Content snippets\useCJITracker.js -TotalCount 6
"=== done"
