# Stage C: runtime smoke checks, offline, dummy credentials. Changes no tracked file.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\01-baseline\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$sum  = Join-Path $ev "stage-c-summary.txt"
$tmp  = "C:\Users\sovan\.kiro\stage_c_tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
"Stage C started $(Get-Date -Format s)" | Set-Content $sum

$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
$env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:CJI_ADMIN_KEY = "baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE = "1"
Set-Location $app

function Listening($ports) {
    $l = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    ($ports | ForEach-Object { $p = $_; "{0}:{1}" -f $p, $(if ($l | Where-Object LocalPort -eq $p) { "LISTEN" } else { "-" }) }) -join "  "
}
function KillTree($p) { if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F *> $null } }

$before = Get-ChildItem data, reports -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }
"ports before: $(Listening @(8000,8001,8002,8003,8004,8005,8501))" | Add-Content $sum

# C1 import smoke
$imp = "import importlib,sys`nfor m in ['config','state','graph','agents.supervisor','agents.workers','agents.ingestion_worker','collector.models','collector.api','tools.mcp_client','mcp_servers.friction_engine_server','mcp_servers.journey_data_server','mcp_servers.insight_server','mcp_servers.report_server','mcp_servers.ingestion_intelligence_server']:`n    try:`n        importlib.import_module(m); print('IMPORT OK  ', m)`n    except Exception as e:`n        print('IMPORT FAIL', m, type(e).__name__, str(e)[:160])"
Set-Content -Path "$tmp\imp.py" -Value $imp
& $py "$tmp\imp.py" *> "$ev\c1-imports.log"
"C1 imports exit=$LASTEXITCODE" | Add-Content $sum
Get-Content "$ev\c1-imports.log" | Where-Object { $_ -match '^IMPORT' } | Add-Content $sum

# C2 MCP servers
$srv = Start-Process -FilePath $py -ArgumentList "run_servers.py" -WorkingDirectory $app -PassThru -WindowStyle Hidden `
       -RedirectStandardOutput "$ev\c2-run-servers.out.log" -RedirectStandardError "$ev\c2-run-servers.err.log"
$ok = $false
for ($i = 0; $i -lt 30; $i++) { Start-Sleep 2; $s = Listening @(8001,8002,8003,8004,8005); if (($s -split 'LISTEN').Count -eq 6) { $ok = $true; break } }
"C2 run_servers.py after $([int](($i+1)*2))s: $(Listening @(8001,8002,8003,8004,8005))" | Add-Content $sum

if ($ok) {
    # C3 demo pipeline (LLM blocked -> expected fallback path)
    $t0 = Get-Date
    & $py main.py --mode demo --run --auto-approve *> "$ev\c3-demo-pipeline.log"
    "C3 main.py --mode demo --run --auto-approve exit=$LASTEXITCODE  $([int]((Get-Date)-$t0).TotalSeconds)s" | Add-Content $sum
    Get-Content "$ev\c3-demo-pipeline.log" | Where-Object { $_ -match 'Report|report_path|ERROR|Error|error|\[OK\]|complete|Traceback|fallback' } | Select-Object -Last 15 | ForEach-Object { "   | $_" } | Add-Content $sum

    # C4 ingest path probe (D-01): tiny synthetic CSV, no --run
    "event_name,page_location,ga_session_id,user_pseudo_id,event_timestamp`npage_view,https://example.test/signup,s1,u1,2026-01-01T00:00:00Z" | Set-Content "$tmp\probe.csv"
    $t0 = Get-Date
    & $py main.py --mode demo --ingest --file "$tmp\probe.csv" --source-hint "baseline probe" *> "$ev\c4-ingest-probe.log"
    "C4 main.py --ingest --file probe.csv exit=$LASTEXITCODE  $([int]((Get-Date)-$t0).TotalSeconds)s" | Add-Content $sum
    Get-Content "$ev\c4-ingest-probe.log" | Where-Object { $_ -match '8004|8005|ingestion|Ingest|ERROR|Error|404|405|Traceback' } | Select-Object -Last 12 | ForEach-Object { "   | $_" } | Add-Content $sum
} else {
    "C3/C4 NOT RUN: MCP servers did not all start" | Add-Content $sum
}
KillTree $srv
Start-Sleep 2
"ports after stopping servers: $(Listening @(8001,8002,8003,8004,8005))" | Add-Content $sum

# C5 collector with an unreachable database
$col = Start-Process -FilePath $py -ArgumentList "-m","uvicorn","collector.api:app","--port","8000" -WorkingDirectory $app -PassThru -WindowStyle Hidden `
       -RedirectStandardOutput "$ev\c5-collector.out.log" -RedirectStandardError "$ev\c5-collector.err.log"
Start-Sleep 15
$alive = -not $col.HasExited
$health = try { (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5).StatusCode } catch { "no-response ($($_.Exception.Message.Split([Environment]::NewLine)[0]))" }
"C5 uvicorn collector.api:app (dead DB): process_alive=$alive exit=$(if ($col.HasExited) { $col.ExitCode } else { 'n/a' }) /health=$health  ports: $(Listening @(8000))" | Add-Content $sum
KillTree $col
Get-Content "$ev\c5-collector.err.log" | Where-Object { $_ -match 'Error|error|Application startup|OperationalError|refused' } | Select-Object -Last 6 | ForEach-Object { "   | $_" } | Add-Content $sum

# C6 Streamlit server
$st = Start-Process -FilePath $py -ArgumentList "-m","streamlit","run","dashboard.py","--server.headless","true","--server.port","8501","--browser.gatherUsageStats","false" -WorkingDirectory $app -PassThru -WindowStyle Hidden `
      -RedirectStandardOutput "$ev\c6-streamlit.out.log" -RedirectStandardError "$ev\c6-streamlit.err.log"
$h = "no-response"
for ($i = 0; $i -lt 15; $i++) { Start-Sleep 2; try { $h = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8501/_stcore/health" -TimeoutSec 3).Content; break } catch {} }
"C6 streamlit run dashboard.py: /_stcore/health=$h (script body only executes when a browser session connects; not exercised)" | Add-Content $sum
KillTree $st

# C7 side effects
$after = Get-ChildItem data, reports -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { "$($_.FullName)|$($_.Length)|$($_.LastWriteTimeUtc.Ticks)" }
$new = Compare-Object $before $after | Where-Object SideIndicator -eq "=>" | ForEach-Object { ($_.InputObject -split '\|')[0].Replace("$app\", "") }
"C7 new/changed files under data/ and reports/ (gitignored): $($new.Count)" | Add-Content $sum
$new | ForEach-Object { "   + $_" } | Add-Content $sum
git -C $repo status --short *> "$ev\c7-git-status-after.log"
"git status unchanged vs Stage B start: $((Get-Content (Join-Path $ev 'b0-git-status-before.log') -Raw) -eq (Get-Content (Join-Path $ev 'c7-git-status-after.log') -Raw))" | Add-Content $sum
"ports at end: $(Listening @(8000,8001,8002,8003,8004,8005,8501))" | Add-Content $sum
Remove-Item -Recurse -Force $tmp
"Stage C finished $(Get-Date -Format s)" | Add-Content $sum
