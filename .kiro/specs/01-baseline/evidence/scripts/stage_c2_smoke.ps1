# Stage C2: corrected smoke checks. Offline, dummy credentials, no tracked-file changes.
$ErrorActionPreference = "Continue"
$repo = "C:\Users\sovan\Documents\Projects\TCS-CJI"
$app  = Join-Path $repo "cji_agent"
$ev   = Join-Path $repo ".kiro\specs\01-baseline\evidence"
$py   = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
$sum  = Join-Path $ev "stage-c2-summary.txt"
$tmp  = "C:\Users\sovan\.kiro\stage_c2_tmp"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
"Stage C2 started $(Get-Date -Format s)" | Set-Content $sum

$env:HTTPS_PROXY = "http://127.0.0.1:9"; $env:HTTP_PROXY = "http://127.0.0.1:9"
$env:NO_PROXY = "localhost,127.0.0.1"
$env:DATABASE_URL = "postgresql://baseline:baseline@127.0.0.1:1/baseline"
$env:SUPABASE_DATABASE_URL = $env:DATABASE_URL
$env:GROQ_API_KEY = "baseline-offline-dummy"; $env:ANTHROPIC_API_KEY = "baseline-offline-dummy"
$env:OPENAI_API_KEY = "baseline-offline-dummy"; $env:LANGCHAIN_API_KEY = "baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2 = "false"; $env:CJI_MODE = "demo"; $env:CJI_ADMIN_KEY = "baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE = "1"

function Listening($ports) {
    $l = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $ports -contains $_.LocalPort }
    ($ports | ForEach-Object { $p = $_; "{0}:{1}" -f $p, $(if ($l | Where-Object LocalPort -eq $p) { "LISTEN" } else { "-" }) }) -join "  "
}
function KillTree($p) { if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F *> $null } }
$parquet = Join-Path $app "data\events.parquet"
$hashBefore = (Get-FileHash $parquet).Hash
$repBefore = @(Get-ChildItem (Join-Path $app "reports") -File -ErrorAction SilentlyContinue | ForEach-Object Name)

# C1 imports, with PYTHONPATH like run_servers.py uses
Set-Location $app
$env:PYTHONPATH = $app
$imp = "import importlib`nfor m in ['config','state','graph','agents.supervisor','agents.workers','agents.ingestion_worker','collector.models','collector.api','tools.mcp_client','mcp_servers.friction_engine_server','mcp_servers.journey_data_server','mcp_servers.insight_server','mcp_servers.report_server','mcp_servers.ingestion_intelligence_server']:`n    try:`n        importlib.import_module(m); print('IMPORT OK  ', m)`n    except Exception as e:`n        print('IMPORT FAIL', m, type(e).__name__, str(e)[:140])"
Set-Content -Path "$tmp\imp.py" -Value $imp
& $py "$tmp\imp.py" *> "$ev\c1-imports.log"
"C1 imports (cwd=cji_agent, PYTHONPATH=cji_agent):" | Add-Content $sum
Get-Content "$ev\c1-imports.log" | Where-Object { $_ -match '^IMPORT' } | ForEach-Object { "   $_" } | Add-Content $sum
Remove-Item Env:PYTHONPATH

# C3b demo pipeline with JOURNEY_NAME matching the tracked parquet (config override only)
$env:JOURNEY_NAME = "user_onboarding"
$srv = Start-Process -FilePath $py -ArgumentList "run_servers.py" -WorkingDirectory $app -PassThru -WindowStyle Hidden `
       -RedirectStandardOutput "$ev\c3b-run-servers.out.log" -RedirectStandardError "$ev\c3b-run-servers.err.log"
$ok = $false
for ($i = 0; $i -lt 30; $i++) { Start-Sleep 2; if (((Listening @(8001,8002,8003,8004,8005)) -split 'LISTEN').Count -eq 6) { $ok = $true; break } }
"servers (JOURNEY_NAME=user_onboarding): $(Listening @(8001,8002,8003,8004,8005))" | Add-Content $sum
if ($ok) {
    $t0 = Get-Date
    & $py main.py --mode demo --run --auto-approve *> "$ev\c3b-demo-pipeline.log"
    "C3b main.py --mode demo --run --auto-approve (JOURNEY_NAME=user_onboarding) exit=$LASTEXITCODE $([int]((Get-Date)-$t0).TotalSeconds)s" | Add-Content $sum
    Select-String -Path "$ev\c3b-demo-pipeline.log" -Pattern '\[OK\]|\[FAIL\]|\[WARN\]|\[DONE\]|Report|report_path|Max iterations' | ForEach-Object { $_.Line.Trim() } | Select-Object -Unique | Select-Object -First 20 | ForEach-Object { "   | $_" } | Add-Content $sum

    # C4b ingest path probe (D-01) with --run
    "event_name,page_location,ga_session_id,user_pseudo_id,event_timestamp`npage_view,https://example.test/signup,s1,u1,2026-01-01T00:00:00Z" | Set-Content "$tmp\probe.csv"
    $t0 = Get-Date
    & $py main.py --mode demo --ingest --file "$tmp\probe.csv" --source-hint "baseline probe" --run --auto-approve *> "$ev\c4b-ingest-probe.log"
    "C4b main.py --ingest --file probe.csv --run --auto-approve exit=$LASTEXITCODE $([int]((Get-Date)-$t0).TotalSeconds)s" | Add-Content $sum
    Select-String -Path "$ev\c4b-ingest-probe.log" -Pattern 'ingestion|8004|8005|404|405|tools/' | ForEach-Object { $_.Line.Trim() } | Select-Object -Unique | Select-Object -First 12 | ForEach-Object { "   | $_" } | Add-Content $sum
} else { "C3b/C4b NOT RUN: servers did not start" | Add-Content $sum }
KillTree $srv
Remove-Item Env:JOURNEY_NAME
Start-Sleep 2
"ports after stop: $(Listening @(8001,8002,8003,8004,8005))" | Add-Content $sum

# C5b collector, package-style import from the repo root (dead DB)
$col = Start-Process -FilePath $py -ArgumentList "-m","uvicorn","cji_agent.collector.api:app","--port","8000" -WorkingDirectory $repo -PassThru -WindowStyle Hidden `
       -RedirectStandardOutput "$ev\c5b-collector.out.log" -RedirectStandardError "$ev\c5b-collector.err.log"
Start-Sleep 15
$alive = -not $col.HasExited
$health = try { (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/health" -TimeoutSec 5).StatusCode } catch { "no-response" }
"C5b uvicorn cji_agent.collector.api:app from repo root: alive=$alive /health=$health" | Add-Content $sum
KillTree $col
Get-Content "$ev\c5b-collector.err.log" | Where-Object { $_ -match 'Error|error:|startup|refused|ModuleNotFound' } | Select-Object -Last 6 | ForEach-Object { "   | $_" } | Add-Content $sum

# Side effects
$hashAfter = (Get-FileHash $parquet).Hash
"tracked events.parquet unchanged: $($hashBefore -eq $hashAfter)" | Add-Content $sum
$repAfter = @(Get-ChildItem (Join-Path $app "reports") -File -ErrorAction SilentlyContinue | ForEach-Object Name)
"new reports (gitignored): $(@($repAfter | Where-Object { $repBefore -notcontains $_ }) -join ', ')" | Add-Content $sum
git -C $repo status --short *> "$ev\c8-git-status-after.log"
"git status unchanged vs Stage B start: $((Get-Content (Join-Path $ev 'b0-git-status-before.log') -Raw) -eq (Get-Content (Join-Path $ev 'c8-git-status-after.log') -Raw))" | Add-Content $sum
"ports at end: $(Listening @(8000,8001,8002,8003,8004,8005,8501))" | Add-Content $sum
Remove-Item -Recurse -Force $tmp
"Stage C2 finished $(Get-Date -Format s)" | Add-Content $sum
