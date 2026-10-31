# Deploying CJI on one host

Spec 15 (production hardening). The supported release is **one host** running each CJI process once, behind a TLS
reverse proxy, with PostgreSQL on Supabase. Limits, secrets and runbooks: `docs/operations.md`. What has been
verified: `docs/release-checklist.md`.

## 1. Topology

| Process | Command | Binds | Reached through the proxy |
|---|---|---|---|
| Next.js | `npm start` in `frontend/` (after `npm ci && npm run build`) | 127.0.0.1:3000 | yes: `https://cji.example.com/` |
| Backend API | `cji-api` | 127.0.0.1:8006 | yes: `https://cji.example.com/api/v1/` (only if other clients than Next.js need it) |
| Collector (realtime) | `cji-collector` | 127.0.0.1:8000 | yes: `https://collect.example.com/collect/batch`, `/tracker.js` |
| MCP servers | `cji-servers` (five processes) | 127.0.0.1:8001–8005 | **never** |
| Streamlit (optional fallback) | `cji-dashboard` | 127.0.0.1:8501 | optional, behind proxy authentication |

Only the proxy listens on a public address (443). Set `CJI_SERVICE_HOST=127.0.0.1`. The health paths for
monitoring are in `cji-ops status` (`/api/v1/health/ready`, `/health/ready`, `/health` on MCP, `/readyz`).

Proxy example (Caddy):

```
cji.example.com {
    reverse_proxy /api/v1/* 127.0.0.1:8006
    reverse_proxy 127.0.0.1:3000
}
collect.example.com {
    reverse_proxy /collect/* 127.0.0.1:8000
    reverse_proxy /tracker.js 127.0.0.1:8000
}
```

nginx: one `server` per name with `proxy_pass http://127.0.0.1:PORT;`, `proxy_set_header X-Forwarded-For
$proxy_add_x_forwarded_for;` and TLS certificates. Behind exactly one proxy set `CJI_COLLECTOR_TRUSTED_PROXY_HOPS=1`,
`CJI_FRONTEND_TRUSTED_PROXY_HOPS=1` and `CJI_API_TRUSTED_PROXY_HOPS=1` (the API then trusts the address Next.js
forwards). Never set the hops above 0 for a process that is reachable without the proxy.

Supervision: run each command as a service of an unprivileged account that owns `CJI_HOME` (Windows: NSSM or a
scheduled task "at startup"; Linux: one systemd unit per process with `Restart=on-failure`). Logs go to stdout and
stderr; let the supervisor rotate them.

## 2. Files and permissions

`CJI_HOME` holds `.env`, `data/` (Parquet, SQLite stores, token file, audit files, uploads, Chroma) and `reports/`.
Only the service account may read it. `data/api_tokens.json` is written with owner-only permissions where the OS
supports them. Backups contain the same data (not encrypted): store them with the same protection.

## 3. Environment per process

Common: `CJI_ENV=production`, `CJI_MODE=realtime` (or `demo` explicitly), `CJI_HOME`, `CJI_LOG_FORMAT=json`,
`DATABASE_URL` (realtime), `CJI_SERVICE_HOST=127.0.0.1`.

| Process | Also needs |
|---|---|
| `cji-api` | `CJI_API_CURSOR_SECRET` (32+ characters), `CJI_API_CORS_ORIGINS` (https; empty when only Next.js calls it), `CJI_API_TRUSTED_PROXY_HOPS`, a token file with an admin token |
| `cji-collector` | `CJI_ADMIN_KEY` (32+), `CJI_CORS_ORIGINS` (https), `CJI_COLLECTOR_TRUSTED_PROXY_HOPS` |
| MCP servers | `GROQ_API_KEY` or `ANTHROPIC_API_KEY` with `CJI_LLM_PROVIDER`; LLM prices if a cost budget is set |
| Next.js | `CJI_API_BASE_URL=http://127.0.0.1:8006`, `CJI_SESSION_SECRET` (32+), optionally `CJI_SESSION_SECRET_PREVIOUS` during rotation, `CJI_FRONTEND_TRUSTED_PROXY_HOPS` |

Check before starting anything:

```
cji-settings check --role production         # every rule (no network)
cji-db migrate status --require-current        # connects to the database; exit 1 if the schema is behind
cd frontend && npm run check:env               # the Next.js variables
```

Each exits non-zero and names the problem.

## 4. Start order

1. PostgreSQL reachable; `cji-db migrate status` shows the required version.
2. `cji-servers` (MCP), wait until `cji-ops status --only cji-journey-data cji-friction-engine cji-insight cji-report
   cji-ingestion-intelligence` is ready.
3. `cji-api` and `cji-collector`; then Next.js.
4. `cji-ops status` (all ready) and a sign-in through the proxy.

## 5. First deployment

1. Install: `pip install -r requirements.lock` and the wheel (`pip install --no-deps cji_agent-0.15.0-py3-none-any.whl`)
   into a virtual environment; `npm ci && npm run build` in `frontend/`.
2. Write `.env` (section 3). `cji-settings check --role production`.
3. **Backup first**, even of an existing database: `cji-backup create --out BACKUP_DIR`.
4. `cji-db migrate up`. On an existing Supabase database this adopts the tables (0001) and adds indexes and a
   unique `event_id` index (0002). If 0002 reports duplicated event ids, follow the runbook in
   `docs/operations.md`.
5. `cji-api-token create --label ops --role admin --journey '*'` and a token for Next.js
   (`--role operator --journey <journey>`).
6. Start (section 4).

## 6. Upgrade

1. `cji-backup create --out BACKUP_DIR` and `cji-backup verify BACKUP_DIR/cji-backup-*`.
2. Stop Next.js, the API, the collector and the MCP servers.
3. Install the new wheel and the new frontend build.
4. `cji-db migrate up`; `cji-db migrate status`.
5. Start in order; `cji-ops status`.

## 7. Rollback

The rollback drill in the Spec 15 gate runs exactly these steps (`evidence/rollback-drill.md`).

1. Stop the services.
2. `cji-db migrate down --to N`, where N is the schema version the previous release requires (0.11.0: none, use 1).
3. Reinstall the previous wheel and frontend build.
4. Start; `cji-ops status`.
5. If data must go back too: restore the backup taken before the upgrade into a new database and home, check its
   report, and point the services at it (runbook in `docs/operations.md`).

Configuration-only rollback of the write features: `CJI_API_WRITE_OPERATIONS=false` and restart `cji-api`.

## 8. Backups

Daily `cji-backup create --out BACKUP_DIR` (with `--include-audit` weekly), kept for 30 days, copied off the host.
Monthly restore drill into a scratch database and home (`cji-backup restore ... --confirm-database NAME`); the
JSON report must say `"matches": true`. Supabase's own backups depend on the project's plan: check them in the
Supabase dashboard (an owner item in the release checklist).

## 9. Not covered

Containers, more than one instance of a service, hosted CI, a secrets vault and OpenTelemetry export are not part of
this release (`.kiro/specs/15-production-hardening/requirements.md` §5).
