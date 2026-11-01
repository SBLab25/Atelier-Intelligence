#!/usr/bin/env bash
# Stops all running CJI processes and frees ports 8001-8006 and 3000.
echo "Releasing CJI ports (8001-8006, 3000)..."
for port in 8001 8002 8003 8004 8005 8006 3000; do
  pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    kill -9 $pids 2>/dev/null || true
    echo "Freed port $port"
  fi
done
echo "All CJI processes stopped."
