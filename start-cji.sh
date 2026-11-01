#!/usr/bin/env bash
# Starts CJI MCP Servers (ports 8001-8005), CJI backend API (port 8006), and Next.js frontend (port 3000).
# Stop them with ./stop-cji.sh or Ctrl+C.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Checking for stale processes on CJI ports (8001-8006, 3000)..."
for port in 8001 8002 8003 8004 8005 8006 3000; do
  pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  if [ -n "$pids" ]; then
    kill -9 $pids 2>/dev/null || true
    echo "Freed port $port"
  fi
done

# Python virtual environment detection
VENV_BIN="$ROOT_DIR/cji_agent/.venv/bin"
if [ ! -f "$VENV_BIN/python" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PY="python3"
  else
    echo "Error: Python not found." >&2
    exit 1
  fi
else
  PY="$VENV_BIN/python"
fi

echo "Starting CJI MCP Servers (:8001-8005)..."
(cd "$ROOT_DIR/cji_agent" && "$PY" -m cji.run_servers) &
SERVERS_PID=$!

echo "Starting CJI API (:8006)..."
(cd "$ROOT_DIR/cji_agent" && "$PY" -m cji.api.serve) &
API_PID=$!

echo "Starting Next.js Cockpit (:3000)..."
(cd "$ROOT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

echo "MCP:      http://127.0.0.1:8001..8005/sse (5 MCP servers)"
echo "API:      http://127.0.0.1:8006/api/v1"
echo "Frontend: http://localhost:3000"

wait
