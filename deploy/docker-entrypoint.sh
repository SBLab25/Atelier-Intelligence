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

# Sanitize CORS origins to prevent fail-closed validation crashes on wildcard '*' or trailing slashes
eval "$(python3 - << 'EOF'
import os

for key in ("CJI_CORS_ORIGINS", "CJI_API_CORS_ORIGINS"):
    val = os.environ.get(key, "").strip()
    if not val:
        continue
    cleaned = []
    for item in val.split(","):
        item = item.strip()
        if not item or item == "*":
            continue
        item = item.rstrip("/")
        cleaned.append(item)
    if cleaned:
        print(f"export {key}='{','.join(cleaned)}'")
    else:
        print(f"unset {key}")
EOF
)"

# 1. Apply any pending database migrations automatically
if [ -n "$DATABASE_URL" ]; then
    echo "Checking and applying database migrations on PostgreSQL..."
    python -m cji.ops.db_cli migrate up || echo "Warning: Migration check encountered an issue, proceeding..."
fi

# 2. Provision initial admin token for Cockpit UI if not already created
TOKEN_FILE="$CJI_HOME/data/api_tokens.json"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "=========================================================="
    echo "🔑 CREATING INITIAL PRODUCTION COCKPIT API TOKEN:"
    python -m cji.api.tokens_cli create --label production-cockpit --role admin --journey '*' || echo "Warning: Failed to create token"
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

# Wait for internal services to respond before binding Caddy to public port
echo "Waiting for Telemetry Collector to be ready on port 8000..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8000/health/ready > /dev/null 2>&1; then
        echo "✅ Telemetry Collector is up and healthy."
        break
    fi
    sleep 0.5
done

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
