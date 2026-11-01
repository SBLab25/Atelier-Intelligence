# Starts the CJI MCP Servers (ports 8001-8005), CJI backend API (port 8006), and Next.js frontend (port 3000) in their own windows.
# Stop them with .\stop-cji.ps1, or press Ctrl+C in each window.
$root = $PSScriptRoot

# Clean up any stale processes listening on CJI ports first to prevent EADDRINUSE conflicts
Write-Host "Checking for stale processes on CJI ports (8001-8006, 3000)..."
foreach ($port in 8001, 8002, 8003, 8004, 8005, 8006, 3000) {
    $pids = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    if ($pids) {
        foreach ($p in $pids) {
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
            Write-Host "Freed port $port (terminated pid $p)"
        }
    }
}

# Determine the best Python environment: project venv first, then fallback to baseline venv
$localScripts = "$root\cji_agent\.venv\Scripts"
$baselineScripts = 'C:\Users\sovan\.venvs\cji-baseline-312\Scripts'

$pyScripts = if (Test-Path "$localScripts\python.exe") {
    $localScripts
} elseif (Test-Path "$baselineScripts\python.exe") {
    $baselineScripts
} else {
    Write-Error "No valid Python virtual environment found in $localScripts or $baselineScripts."
    exit 1
}

$activateScript = "$pyScripts\Activate.ps1"
$hasActivate = Test-Path $activateScript
$actPrefix = if ($hasActivate) { "& '$activateScript'; " } else { "" }

$serversCmd = if (Test-Path "$pyScripts\cji-servers.exe") {
    "${actPrefix}& '$pyScripts\cji-servers.exe'"
} else {
    "${actPrefix}& '$pyScripts\python.exe' -m cji.run_servers"
}

$apiCmd = if (Test-Path "$pyScripts\cji-api.exe") {
    "${actPrefix}& '$pyScripts\cji-api.exe'"
} else {
    "${actPrefix}& '$pyScripts\python.exe' -m cji.api.serve"
}

Start-Process powershell -WorkingDirectory "$root\cji_agent" -ArgumentList '-ExecutionPolicy', 'Bypass', '-NoExit', '-Command', "`$host.UI.RawUI.WindowTitle='CJI MCP Servers :8001-8005'; $serversCmd"
Start-Process powershell -WorkingDirectory "$root\cji_agent" -ArgumentList '-ExecutionPolicy', 'Bypass', '-NoExit', '-Command', "`$host.UI.RawUI.WindowTitle='CJI API :8006'; $apiCmd"
Start-Process powershell -WorkingDirectory "$root\frontend" -ArgumentList '-NoExit', '-Command', "`$host.UI.RawUI.WindowTitle='CJI frontend :3000'; npm.cmd run dev"

Write-Host 'MCP:      http://127.0.0.1:8001..8005/sse (5 MCP servers)'
Write-Host 'API:      http://127.0.0.1:8006/api/v1'
Write-Host 'Frontend: http://localhost:3000  (first page load compiles for ~20 s)'
