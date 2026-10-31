# Stops whatever listens on the CJI ports (8001-8006, 3000).
foreach ($port in 8001, 8002, 8003, 8004, 8005, 8006, 3000) {
    $pids = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    if (-not $pids) { Write-Host "port ${port}: nothing running"; continue }
    foreach ($p in $pids) { Stop-Process -Id $p -Force; Write-Host "port ${port}: stopped pid $p" }
}
