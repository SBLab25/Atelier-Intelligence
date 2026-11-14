# Multi-stage production container for Atelier Intelligence Backend & Collector
FROM caddy:2-alpine AS caddy_stage

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000 \
    CJI_HOME=/app/cji_agent \
    MALLOC_ARENA_MAX=2 \
    PYTHONNODEBUGRANGES=1 \
    CJI_THREADED_SERVERS=1

# Install essential system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Caddy reverse proxy from official alpine stage
COPY --from=caddy_stage /usr/bin/caddy /usr/bin/caddy

WORKDIR /app

# Copy locked dependencies and install
COPY cji_agent/requirements.lock /app/cji_agent/requirements.lock
RUN pip install --no-cache-dir -r /app/cji_agent/requirements.lock

# Copy cji_agent source code and install editable package
COPY cji_agent/ /app/cji_agent/
RUN pip install --no-deps -e /app/cji_agent

# Create runtime directories for data, SQLite checkpoints, and reports
RUN mkdir -p /app/cji_agent/data /app/cji_agent/reports /app/cji_agent/data/audit

# Copy Caddy configuration and startup entrypoint
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY deploy/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

EXPOSE 10000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
