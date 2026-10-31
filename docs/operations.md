# Operating CJI: limits, AI budgets, secrets and runbooks

Spec 15 (production hardening). Use it together with `docs/deployment.md` (how to install and upgrade) and
`docs/release-checklist.md` (what has been verified for a release). Every limit below is checked against the
settings code by `cji_agent/tests/test_production_hardening.py` and `test_operations_doc.py`.

## Limits

All rate limits, run capacity and idempotency state live **in one process's memory**. They reset when the process
restarts, and a second instance of a service would allow the full rate again. One instance per service is the
supported deployment (`docs/deployment.md`).

| Setting | Default | Scope | What happens at the limit |
|---|---|---|---|
| `CJI_API_RATE_PER_TOKEN` | 120/min | per API token, per API process | 429 `rate_limited` with `Retry-After`; audit `auth.rate_limited` |
| `CJI_API_RATE_PER_IP` | 60/min | per client address without a valid token (and public paths) | 429 with `Retry-After` |
| `CJI_API_AUTH_FAILURES_PER_MIN` | 10/min | refused tokens per client address | 429 with `Retry-After`; audit `auth.rate_limited` |
| `CJI_API_MAX_ACTIVE_RUNS` | 1 | runs started or resumed by one API process | 409 `run_capacity_reached`, `Retry-After: 30` |
| `CJI_API_MAX_UPLOAD_BYTES` | 10 MiB | one ingestion validation upload | 413 `request_too_large` |
| `CJI_COLLECTOR_MAX_BODY_BYTES` | 256 KiB | one `/collect/batch` body | 413 |
| `CJI_COLLECTOR_RATE_PER_KEY` | 120/min | per tracker key | 429 with `Retry-After` |
| `CJI_COLLECTOR_RATE_PER_IP` | 300/min | per client address | 429 with `Retry-After` |
| `CJI_COLLECTOR_ADMIN_RATE_PER_IP` | 10/min | admin routes per client address | 429 |
| `CJI_MCP_CONNECT_TIMEOUT_S` | 5 s | one MCP connection attempt | connection retried, then the step fails `connect_failed` |
| `CJI_MCP_READ_TIMEOUT_S` | 300 s | MCP SSE read | step fails |
| `CJI_MCP_CALL_TIMEOUT_S` | 150 s | one MCP tool call | `tool_timeout`; the step may retry |
| `CJI_WORKFLOW_STEP_TIMEOUT_S` | 900 s | one workflow step attempt | `step_timeout`; retried up to the attempts |
| `CJI_WORKFLOW_STEP_ATTEMPTS` | 2 | attempts per workflow step | run `failed`; resumable |
| `MAX_AGENT_ITERATIONS` | 20 | supervisor iterations per run | run stops |
| `CJI_PIPELINE_TIMEOUT_S` | 180 s | the dashboard's blocking run button | the button reports a timeout |
| `CJI_LLM_TIMEOUT_S` | 30 s | one provider HTTP request | retried within the deadline |
| `CJI_LLM_DEADLINE_S` | 90 s | one LLM call including retries | fallback text with provenance `fallback` |
| `CJI_LLM_RETRY_ATTEMPTS` | 3 | attempts per LLM call | fallback |
| `CJI_LLM_RETRY_MAX_S` | 10 s | longest wait between LLM attempts | — |
| `CJI_LLM_RATE_PER_MIN` | 30/min | LLM calls per provider, per MCP server process | the call waits, or falls back when the wait does not fit the deadline |
| `LLM_MAX_TOKENS` | 2048 | output tokens per LLM call | provider truncates |
| `CJI_LLM_RUN_MAX_CALLS` | 20 | LLM calls per run (per calling process) | `budget_exceeded`; fallback text |
| `CJI_LLM_RUN_MAX_TOKENS` | 50,000 | LLM tokens per run (per calling process) | `budget_exceeded`; fallback text |
| `CJI_LLM_RUN_MAX_COST_USD` | none | LLM cost per run; enforced only with both prices set | `budget_exceeded`; fallback text |
| `CJI_AUDIT_RETENTION_DAYS` | 90 | audit lines kept by `cji-ops maintenance` | older lines deleted |

Fixed limits (not configurable): API request bodies 16 KiB (except uploads), idempotency keys kept 24 h, validated
uploads kept 1 h, 20 column-map entries per upload, 50 run errors in run results.

## AI budgets

- **Where LLM calls happen:** the insight and report MCP servers (insights and narrative) and the ingestion server
  (`cji --ingest` schema detection). Each process has its own per-run counters and its own provider rate.
- **Per run:** at most `CJI_LLM_RUN_MAX_CALLS` calls and `CJI_LLM_RUN_MAX_TOKENS` tokens per process. A run of
  the demo journey uses about one insight call per critical step plus one narrative call (4–6 calls).
- **Cost:** computed only when `CJI_LLM_PRICE_INPUT_PER_MTOK` and `CJI_LLM_PRICE_OUTPUT_PER_MTOK` (USD per million
  tokens) are set; then `CJI_LLM_RUN_MAX_COST_USD` is enforced. The production check refuses a cost budget without
  prices. Usage per run is in run results (`llm_usage`) and in `/metrics` (`cji_llm_tokens_total`,
  `cji_llm_cost_usd_total` on the MCP servers).
- **Monthly estimate:** runs per month × (input tokens × input price + output tokens × output price) / 1,000,000.
  Take the token counts from the `llm_usage` of a few real runs.
- **At a budget:** the call is not sent; the insight or narrative uses the rule-based fallback and records
  provenance `fallback` with the reason. The run still completes.
- **Not provided:** a daily or monthly ceiling across runs (F-97, open). Set provider-side spending limits in the
  provider account.

## Secrets

| Secret | Used by | Rotate | Overlap | If leaked | Tested by |
|---|---|---|---|---|---|
| API tokens (`cji_api_…`, hashes in `CJI_API_TOKENS_FILE`) | Next.js server, scripts | `cji-api-token rotate TOKEN_ID --overlap-hours 24`, update the client, then let the old one expire (or `revoke`) | yes, configurable | reads (viewer), runs and ingestion (operator), replace and metrics (admin) for the token's journeys | `test_rotation_overlaps_then_the_old_token_stops`, `test_rotate_cli_prints_the_value_once_and_audits` |
| `CJI_SESSION_SECRET` (Next.js) | Next.js session cookies | move the old value to `CJI_SESSION_SECRET_PREVIOUS`, set a new value, restart Next.js; remove the previous value after the session lifetime (8 h) | yes (previous key accepted, cookies re-issued) | forged sessions; still bounded by the API token inside | frontend `session-rotation` tests |
| `CJI_API_CURSOR_SECRET` | `cji-api` page cursors | set a new value, restart `cji-api` | no: open cursors answer 422 `invalid_cursor`; clients restart paging | forged cursors (page positions only; access checks still apply) | `test_cursor_rotation_invalidates_open_cursors` |
| `CJI_ADMIN_KEY` | collector admin routes, collector `/metrics` | set a new value, restart `cji-collector` | no | tracker key creation and revocation, live stats | collector tests |
| Tracker keys (`cji_live_…`) | browsers (public by design) | create a new key, deploy the snippet, then `POST /admin/api-keys/revoke` | yes (both work until revoked) | event injection for one journey | `test_revoked_tracker_key_is_refused` |
| `DATABASE_URL` / `SUPABASE_DATABASE_URL` | collector, API, MCP journey-data, ingestion | change the password in Supabase, update the variable for every process, restart them | no | full database access | runbook only (provider side) |
| `GROQ_API_KEY`, `ANTHROPIC_API_KEY` | MCP insight, report, ingestion servers | create a new key in the provider console, update, restart the MCP servers, delete the old key | provider dependent | LLM spend | runbook only (provider side) |
| `LANGCHAIN_API_KEY` | only with `LANGCHAIN_TRACING_V2=true` | as above | provider dependent | trace data at LangSmith | runbook only |
| `OPENAI_API_KEY` | read but unused (F-28) | remove it | — | — | — |

Secrets come from the process environment or `<CJI_HOME>/.env` (git-ignored). No vault is used; a vault would
replace the `.env` file and inject the same variables. Never pass a secret on a command line: the operations
commands read database URLs from settings or from a named variable (`--database-url-env NAME`).

## Development-only behaviour

Every branch in `cji_agent/src/` that compares with `"development"` is listed here, with the number of comparisons
per file; `test_every_development_branch_is_in_the_inventory` fails when one is added without updating this table.
`CJI_ENV` defaults to `production`, so none of these apply unless a host sets `CJI_ENV=development`.

| File | Comparisons | Behaviour in development only |
|---|---|---|
| `api/app.py` | 1 | `/api/v1/docs` (Swagger UI) is served |
| `collector/api.py` | 1 | the development tracker key `cji_dev_localtest` is seeded for `JOURNEY_NAME` |
| `settings/load.py` | 2 | API CORS origins default to the local Next.js origins; collector CORS defaults to local origins |
| `settings/roles.py` | 2 | the collector may start without an admin key and CORS origins; the API may use plain-http origins and a random cursor key |

Outside Python: Next.js relaxes its Content-Security-Policy for the development server only when
`NODE_ENV=development` (`frontend/src/proxy.ts`); `npm start` always runs with `NODE_ENV=production`.

Also changed in Spec 15: production no longer defaults `CJI_MODE` to `demo`; it must be set.

## Runbooks

**Rotate an API token.** `cji-api-token list`; `cji-api-token rotate TOKEN_ID --overlap-hours 24`; put the new
value into the client (Next.js: sign in again with it); after the overlap, `cji-api-token list` shows the old one
expired. Audit: `security.jsonl` has `token.rotate`.

**Restore from a backup.** Stop the services. `cji-backup verify DIR`. Restore into a new database and home first:
`cji-backup restore DIR --home NEW_HOME --database-url-env NEW_DB_URL --confirm-database NAME`; check the JSON
report (`matches: true`). Point the services at the new home and database, start them, check `cji-ops status`.

**Apply or roll back a migration.** `cji-backup create --out DIR` first. `cji-db migrate status`;
`cji-db migrate up`; `cji-ops status`. To roll back a release: `cji-db migrate down --to N` (N = the previous
release's required version, shown by its `cji-db migrate status`), reinstall the previous release, restart.
Version 1 is never reverted; restore a backup instead.

**Duplicated event ids stop migration 0002.** List them with
`SELECT event_id, count(*) FROM tracking_events GROUP BY 1 HAVING count(*) > 1;` and delete the extra rows
(they are identical copies from repeated `--replace`-less imports), then run `cji-db migrate up` again.

**Follow one request.** Take the `traceparent` response header or the `trace_id` of a log line;
`cji-trace show TRACE_ID` prints the request, the run it started, its steps, tool calls and LLM calls from every
process's audit file.

**First steps in an incident.** `cji-ops status`; the services' JSON logs filtered by `level` ERROR and by
`request_id`; `/api/v1/health/details` with an operator token; `/metrics` (admin) for 5xx and 429 counts;
`security.jsonl` for `auth.failed` bursts. Writes can be switched off without a redeploy:
`CJI_API_WRITE_OPERATIONS=false` and restart `cji-api`.
