#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "🚀 Initializing Atelier Intelligence Production Container"
echo "=========================================================="

export CJI_HOME="${CJI_HOME:-/app/cji_agent}"
export CJI_SERVICE_HOST="127.0.0.1"
export CJI_LOG_FORMAT="${CJI_LOG_FORMAT:-json}"
export CJI_ENV="${CJI_ENV:-production}"
export CJI_MODE="${CJI_MODE:-realtime}"
export PORT="${PORT:-10000}"

mkdir -p "$CJI_HOME/data" "$CJI_HOME/reports" "$CJI_HOME/data/audit"

# 1. Apply any pending database migrations automatically
if [ -n "$DATABASE_URL" ]; then
    echo "Checking and applying database migrations on PostgreSQL..."
    python -m cji.ops.db_cli migrate up || echo "Warning: Migration check encountered an issue, proceeding..."
fi

# 2. Provision initial admin token for Cockpit UI if not already created
TOKEN_FILE="$CJI_HOME/data/api_tokens.json"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "Creating initial production API token for Next.js Cockpit..."
    INITIAL_TOKEN=$(python -m cji.api.tokens_cli create --label production-cockpit --role admin --journey '*' || true)
    echo "=========================================================="
    echo "🔑 INITIAL PRODUCTION COCKPIT API TOKEN:"
    echo "$INITIAL_TOKEN"
    echo "Save this token to sign in to your Next.js Cockpit UI."
    echo "=========================================================="
fi

# 3. Start the 5 MCP Microservices (:8001-8005)
echo "Starting 5 MCP microservices (ports 8001-8005)..."
python -m cji.run_servers &
MCP_PID=$!

# Wait briefly for MCP servers to initialize
sleep 2

# 4. Start the FastAPI Backend API (:8006)
echo "Starting FastAPI Backend API (port 8006)..."
python -m cji.api.serve &
API_PID=$!

# 5. Start the Telemetry Collector (:8000)
echo "Starting Telemetry Collector (port 8000)..."
python -m uvicorn cji.collector.api:app --host 127.0.0.1 --port 8000 &
COLLECTOR_PID=$!

# Graceful termination handler
cleanup() {
    echo "Received termination signal. Shutting down gracefully..."
    kill -TERM "$COLLECTOR_PID" "$API_PID" "$MCP_PID" 2>/dev/null || true
    wait
    echo "All processes terminated."
    exit 0
}
trap cleanup SIGTERM SIGINT

# 6. Start Caddy Reverse Proxy on Render's $PORT
echo "Starting Caddy reverse proxy on port $PORT..."
exec caddy run --config /etc/caddy/Caddyfile
