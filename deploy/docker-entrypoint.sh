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
export CJI_THREADED_SERVERS="1"
export MALLOC_ARENA_MAX="2"
export PYTHONNODEBUGRANGES="1"
export PORT="${PORT:-10000}"

mkdir -p "$CJI_HOME/data" "$CJI_HOME/reports" "$CJI_HOME/data/audit"

# 1. Sanitize DATABASE_URL: auto-encode unescaped '@' characters in database password
if [ -n "$DATABASE_URL" ]; then
    FIXED_DB_URL=$(python3 - << 'EOF'
import os, urllib.parse

url = os.environ.get("DATABASE_URL", "").strip()
prefix = ""
for scheme in ("postgresql://", "postgres://"):
    if url.startswith(scheme):
        prefix = scheme
        url = url[len(scheme):]
        break

if prefix and "@" in url:
    parts = url.rsplit("@", 1)
    if len(parts) == 2 and ":" in parts[0]:
        user, pwd = parts[0].split(":", 1)
        pwd = urllib.parse.quote(urllib.parse.unquote(pwd), safe="")
        user = urllib.parse.quote(urllib.parse.unquote(user), safe=".")
        print(f"{prefix}{user}:{pwd}@{parts[1]}")
    else:
        print(prefix + url)
else:
    print(prefix + url if prefix else url)
EOF
)
    if [ -n "$FIXED_DB_URL" ]; then
        export DATABASE_URL="$FIXED_DB_URL"
    fi
fi

# 2. Sanitize CORS origins: remove '*' / trailing slashes and ensure non-empty for collector in production
eval "$(python3 - << 'EOF'
import os

for key in ("CJI_CORS_ORIGINS", "CJI_API_CORS_ORIGINS"):
    val = os.environ.get(key, "").strip()
    cleaned = []
    if val:
        for item in val.split(","):
            item = item.strip()
            if not item or item == "*":
                continue
            item = item.rstrip("/")
            cleaned.append(item)
    
    # In production, collector requires at least one HTTPS origin
    if key == "CJI_CORS_ORIGINS" and not cleaned:
        cleaned = ["https://render.com", "https://vercel.app"]

    if cleaned:
        print(f"export {key}='{','.join(cleaned)}'")
    else:
        print(f"unset {key}")
EOF
)"

# 3. Apply any pending database migrations automatically
if [ -n "$DATABASE_URL" ]; then
    echo "Checking and applying database migrations on PostgreSQL..."
    python -m cji.ops.db_cli migrate up || echo "Warning: Migration check encountered an issue, proceeding..."
fi

# 4. Provision initial admin token for Cockpit UI if not already created
TOKEN_FILE="$CJI_HOME/data/api_tokens.json"
if [ ! -f "$TOKEN_FILE" ]; then
    echo "=========================================================="
    echo "🔑 CREATING INITIAL PRODUCTION COCKPIT API TOKEN:"
    python -m cji.api.tokens_cli create --label production-cockpit --role admin --journey '*' || echo "Warning: Failed to create token"
    echo "Save this token to sign in to your Next.js Cockpit UI."
    echo "=========================================================="
fi

# 5. Start the 5 MCP Microservices in threaded low-memory mode (:8001-8005)
echo "Starting 5 MCP microservices in single-process threaded mode (ports 8001-8005)..."
python -m cji.run_servers --threaded &
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
