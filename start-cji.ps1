# Starts the CJI MCP Servers (ports 8001-8005), CJI backend API (port 8006), and Next.js frontend (port 3000) in their own windows.
# Stop them with .\stop-cji.ps1, or press Ctrl+C in each window.
$root = $PSScriptRoot
$py = if (Test-Path "$root\cji_agent\.venv\Scripts") { "$root\cji_agent\.venv\Scripts" } else { 'C:\Users\sovan\.venvs\cji-baseline-312\Scripts' }

Start-Process powershell -WorkingDirectory "$root\cji_agent" -ArgumentList '-NoExit', '-Command', "`$host.UI.RawUI.WindowTitle='CJI MCP Servers :8001-8005'; & '$py\cji-servers.exe'"
Start-Process powershell -WorkingDirectory "$root\cji_agent" -ArgumentList '-NoExit', '-Command', "`$host.UI.RawUI.WindowTitle='CJI API :8006'; & '$py\cji-api.exe'"
Start-Process powershell -WorkingDirectory "$root\frontend" -ArgumentList '-NoExit', '-Command', "`$host.UI.RawUI.WindowTitle='CJI frontend :3000'; npm.cmd run dev"

Write-Host 'MCP:      http://127.0.0.1:8001..8005/sse (5 MCP servers)'
Write-Host 'API:      http://127.0.0.1:8006/api/v1'
Write-Host 'Frontend: http://localhost:3000  (first page load compiles for ~20 s)'
