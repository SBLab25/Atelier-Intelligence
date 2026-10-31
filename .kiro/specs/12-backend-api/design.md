# Spec 12 — Versioned Backend API (`/api/v1`): Design

Defaults from requirements §2 (OD-108 to OD-127). Changes if a decision changes.

## 1. Layout

```
src/cji/
  http/                     shared HTTP plumbing (moved out of collector/middleware.py)
    request_id.py           resolve_request_id, current_request_id, RequestIdFilter, RequestIdMiddleware (pure ASGI)
  analytics/
    friction.py             WEIGHTS, BASELINES, score_step(), score_steps() — moved from the friction MCP server
  services/                 the adapter boundary used by the API, the CLI and the dashboard (OD-125)
    journeys.py             list_journeys(), get_journey()
    metrics.py              step_metrics(), funnel()
    friction.py             friction_scores()
    runs.py                 RunIndex, list_runs(), get_run(), approve_run(), latest_run_with_insights()
    insights.py             insights_for(run_id | journey)
    reports.py              list_reports(), get_report(), report_content()
  api/
    __init__.py
    app.py                  create_app(settings) -> FastAPI; module-level `app` for uvicorn
    serve.py                cji-api: uvicorn on the registry endpoint `api`
    auth.py                 Principal, TokenStore (file, hashed), require(role, journey)
    tokens_cli.py           cji-api-token create | list | revoke
    errors.py               Problem model, ApiError(code, status, detail), exception handlers
    pagination.py           Page[T], Cursor (HMAC-signed keyset)
    idempotency.py          IdempotencyStore (SQLite, 24 h)
    limits.py               per-token / per-IP rate limits (collector's RateLimiter)
    schemas.py              response models (built from domain TypedDicts) and request models
    routes/                 health.py, me.py, journeys.py, reports.py, runs.py
cji_agent/openapi/v1.json   committed snapshot of the generated document
```

The collector imports the request-id code from `cji.http` (its responses are unchanged). The friction MCP server
re-exports `WEIGHTS`, `BASELINES`, `_normalise`, `_compute_score` from `cji.analytics.friction` (tests import them).

## 2. Request pipeline

```
RequestIdMiddleware (X-Request-ID in/out, contextvar)
 → BodyLimit (16 KiB, 413 problem)
 → CORS (explicit origins)
 → per-IP limiter for requests without a valid token (429)
 → authenticate (401) → per-token limiter (429) → role/journey check (403)
 → parameter/body validation (422, no values echoed)
 → route → service → response_model validation
 → exception handlers: ApiError → problem; RequestValidationError → 422 problem;
   StarletteHTTPException (404/405 of the router) → problem; RepositoryError → 503; ConfigError → 503;
   Exception → 500 internal_error
 → security headers (Cache-Control: no-store, X-Content-Type-Options: nosniff)
```

Authentication is a dependency on every protected route, declared before body parameters; the validation handler
also checks for a principal on the request scope and answers 401 instead of 422 when there is none (F-57).

## 3. Authentication and authorization (OD-109, OD-110)

Token format `cji_api_` + 32 bytes urlsafe base64 (43 characters). Token file (JSON, written atomically, mode 600
where supported):

```json
{"version": 1, "tokens": [{"id": "tok_3f2a9c1e", "sha256": "<hex>", "label": "nextjs-dev", "role": "operator",
  "journeys": ["user_onboarding"], "created_at": "2026-10-28T12:00:00Z", "expires_at": null, "revoked": false}]}
```

- Lookup: hash the presented token, compare against every stored hash with `hmac.compare_digest` (no early exit
  on the first byte); expired or revoked → 401 `invalid_token`.
- `Principal(token_id, label, role, journeys)`; `role_at_least("operator")`; `can_see(journey)`.
- Logs use `token_id`, never the token or its hash.
- `cji-api-token create --label L --role R --journey J [--journey …] [--expires-days N]` prints the token once;
  `list` prints ids, labels, roles, journeys, expiry; `revoke ID`.

| Endpoint | Role | Journey check |
|---|---|---|
| `GET /health` | none | – |
| `GET /health/details`, `GET /me` | viewer | – |
| `GET /journeys` | viewer | filters to visible journeys |
| `GET /journeys/{id}`, `/metrics`, `/friction`, `/insights` | viewer | 403 if not visible |
| `GET /journeys/{id}/events` | operator | 403 if not visible |
| `GET /reports`, `GET /runs` | viewer | filters; `journey_id` outside the list → 403 |
| `GET /reports/{id}`, `/content`, `GET /runs/{id}` | viewer | 404 if not visible |
| `POST /runs/{id}/approval` | operator | 404 if not visible |

## 4. Endpoints and response models

All JSON field names are snake_case; times are RFC 3339 UTC strings.

| Method and path | Query / body | 2xx body |
|---|---|---|
| `GET /health` | – | `{status: ok\|degraded, version, mode}` |
| `GET /health/details` | – | `{status, version, mode, components: [{name, status: ok\|unavailable, detail_code}]}` (repository, checkpoints, reports) |
| `GET /me` | – | `{token_id, label, role, journeys}` |
| `GET /journeys` | `limit`, `cursor` | `Page[Journey]`, `Journey = {journey_id, steps: [str], mode}` |
| `GET /journeys/{journey_id}` | – | `Journey` |
| `GET /journeys/{journey_id}/events` | `limit`, `cursor`, `step_id?`, `event_type?` | `Page[Event]`, `Event = {event_id, user_id, session_id, step_id, event_type, timestamp, duration_ms, url}` (no `metadata` in v1) |
| `GET /journeys/{journey_id}/metrics` | `days` (1–365, 30) or `minutes` (1–43 200, realtime) | `{journey_id, window: {days, minutes}, steps: [StepMetrics], funnel: [FunnelStep], overall_completion_pct}` |
| `GET /journeys/{journey_id}/friction` | same window | `{journey_id, window, threshold, scores: [FrictionScore], critical_steps: [str]}` |
| `GET /journeys/{journey_id}/insights` | `run_id?` | `{journey_id, run_id \| null, insights: [Insight]}` (empty list when no run has insights) |
| `GET /reports` | `journey_id?`, `limit`, `cursor` | `Page[Report]`, `Report = {report_id, run_id, journey_id \| null, size_bytes, created_at, content_url}` |
| `GET /reports/{report_id}` | – | `Report` |
| `GET /reports/{report_id}/content` | – | `text/html` (OD-114 headers) |
| `GET /runs` | `journey_id?`, `status?`, `limit`, `cursor` | `Page[RunSummary]`, `RunSummary = {run_id, journey_id, mode, status, created_at, updated_at, report_id \| null}` |
| `GET /runs/{run_id}` | – | `Run = RunSummary + {human_approved, active, steps: {worker: Step}, failure: Failure \| null, insight_count, errors_total}` |
| `POST /runs/{run_id}/approval` | header `Idempotency-Key`; body `{}` or `{"comment": str ≤ 500}` | 202 `{run: Run, already_approved: false}` or 200 `{run: Run, already_approved: true}` |

Bounds: `steps` ≤ 64 entries (journey definition limit added to `JourneyDefinition`); insights ≤ steps; run
`errors` are not returned (only `errors_total`); `failure.message` is the workflow's already-safe text cut to 300
characters.

## 5. Error codes (OD-118)

| Status | `code` | When |
|---|---|---|
| 400 | `idempotency_key_required`, `idempotency_key_invalid` | mutation without / with a malformed key |
| 401 | `missing_token`, `invalid_token` | no `Authorization: Bearer`, unknown/expired/revoked token |
| 403 | `insufficient_role`, `journey_forbidden` | role too low; journey outside the token's list |
| 404 | `not_found`, `journey_not_found`, `run_not_found`, `report_not_found` | unknown route; unknown or invisible resource |
| 405 | `method_not_allowed` | router |
| 409 | `run_not_awaiting_approval`, `run_busy`, `idempotency_key_reused`, `request_in_progress` | approval of a running/failed run; lease held elsewhere; key reuse |
| 413 | `request_too_large` | body over 16 KiB |
| 415 | `unsupported_media_type` | POST body not JSON |
| 422 | `validation_failed`, `invalid_cursor` | bad parameter or body (`errors[]` without values); tampered cursor |
| 429 | `rate_limited` | bucket empty; `Retry-After` header |
| 500 | `internal_error` | anything unexpected |
| 503 | `storage_unavailable`, `service_misconfigured` | repository/checkpoint failure; settings invalid for role `api` |

Problem body example:

```json
{"type": "urn:cji:problem:run_not_awaiting_approval", "title": "Run is not awaiting approval", "status": 409,
 "detail": "Run 3b09a363-… is failed; only a run awaiting approval can be approved.",
 "code": "run_not_awaiting_approval", "request_id": "c0ffee00-…"}
```

`detail` texts are fixed per code or built only from validated identifiers; exception messages are never copied in.

## 6. Pagination, idempotency, run index

**Cursor:** `base64url(json({"k": [...keyset], "q": hash(filters)})) + "." + base64url(hmac_sha256(secret, payload))[:22]`.
The filter hash ties a cursor to its query (`journey_id`, `status`, `step_id`, `event_type`), so a cursor from
another query is `invalid_cursor`. `next_cursor` is null on the last page (the service fetches `limit + 1`).

**Events keyset:** new `EventRepository.events_page(journey_id, *, limit, after: tuple[str, str] | None, step_id,
event_type)` ordered by `timestamp DESC, event_id DESC` with `WHERE (timestamp, event_id) < (?, ?)` (bound
parameters in DuckDB and PostgreSQL). The old `events()` stays for the MCP tool.

**Idempotency store** (`api_state.db`, table `idempotency`: `key, token_id, route, request_hash, status, response_json,
created_at`; primary key `(token_id, key)`): insert `in_progress` in a transaction before the work; on finish store
status and body; replay within 24 h; rows older than 24 h are deleted at startup and hourly.

**Run index** (`run_index` in the checkpoint database): `run_id PK, journey_id, mode, status, created_at, updated_at,
report_file`. `Workflow._audit_run` and the end of `_drive` upsert it (one small SQLite write per status change,
after the checkpoint). Backfill at API start: `SELECT DISTINCT thread_id FROM checkpoints` (if the table exists),
skip ids already indexed, `Workflow.status()` for the rest.

**Approval:** `services.runs.approve_run(run_id)` = `Workflow.mark_approved(run_id)` (new: lease, load, transition to
`approved` or return `already`, release) then, when it changed the state, `asyncio.create_task(Workflow.resume(run_id))`
with errors logged and the index updated by the workflow itself. The API keeps references to its tasks and cancels
them on shutdown (the run stays `approved`; `cji --resume` continues it). `RunLeased` → 409 `run_busy`.

## 7. Adapters (OD-125)

- `main.py --status` prints `services.runs.get_run_status(run_id)` (the same dict as today, including
  `lease_owner`, so the CLI output and its tests do not change; the API model drops it).
- `main.py --approve` keeps calling `Workflow.approve` (synchronous drive, as today) through
  `services.runs.approve_and_wait`.
- Dashboard: `load_reports()` → `services.reports.list_reports()` (same files, same order); `load_last_run()` stays on
  `data/last_run.json` (written by the CLI, unchanged). The dashboard's SQL KPIs stay (Spec 14).
- MCP servers: the friction server calls `cji.analytics.friction`; the journey-data server keeps its tools.

## 8. Tests

New `tests/test_api_contract.py` (offline, `TestClient`, `make_test_settings`, a temporary token file, the demo
Parquet, a fake workflow for runs) and `tests/test_api_units.py`:

| Case | Examples |
|---|---|
| success | every endpoint with a viewer/operator token; pages of 1, 2 and the last page; report content headers; approval 202, approval again 200 `already_approved` |
| validation | `limit=0`, `limit=201`, `days=0`, unknown query parameter, bad `run_id` pattern, body with an extra field, oversized body (413), non-JSON body (415); 422 bodies contain no submitted value |
| unauthorized | no header, wrong scheme, unknown token, revoked token, expired token; 401 never shows validation detail |
| forbidden | viewer → events and approval; token for journey A → journey B metrics; `GET /runs?journey_id=B` |
| not found | unknown journey (visible scope), unknown run, run of an invisible journey (404, same body as unknown), unknown report, unknown route |
| conflict | approve a `running`/`failed` run; lease held by another owner; same key + different body; same key while in progress |
| rate limit | per-token bucket exhausted (429, `Retry-After`); per-IP for bad tokens |
| server error | repository raises with a message containing a sentinel password and SQL; checkpoint store missing; unexpected `RuntimeError("/secret/path SENTINEL")`; report file unreadable — 500/503 problems contain only code, title, fixed detail and request id |
| request ids | client id echoed; malformed id replaced; present on 401/404/500 |
| idempotency | replay returns identical body and `Idempotent-Replayed: true`; keys are per token |
| cursors | round trip covers all items once; tampered signature, other query's cursor → `invalid_cursor` |
| OpenAPI | snapshot equals generated; `openapi-spec-validator`; every contract-test response validated against its declared schema (fixture wraps the client); every route declares 401/403/404/422/429/500 where applicable |
| adapters | CLI `--status` output unchanged (existing tests); dashboard report list via services (smoke test); friction scores from `cji.analytics.friction` equal the MCP tool's on the demo data |

## 9. Gate (T8)

The Spec 11 gate (clean venv, old and new commands, pipelines, golden, lint, types, bandit, pip-audit) plus:
`cji-api` started from a temporary directory with a token file; live checks with `httpx` (health, `/me`, journeys,
metrics, friction, runs after the demo pipeline, approval of a paused run and polling until `completed`, report
content headers, 401/403/404/429 on the live server); live `openapi.json` equals the snapshot; `cji-settings check
--role api`.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Approval background task dies with the API process | Run stays `approved` (durable); `cji --resume` continues; status shows `active: false`. |
| Token file edited by hand incorrectly | Loader validates with a pydantic model; invalid file → 503 `service_misconfigured` and a startup error from `cji-settings check --role api`. |
| Rate limits and idempotency are per process / per file | Documented; one API process in v1. |
| Run index misses a run written by an older process | Backfill at startup; `GET /runs/{id}` falls back to `Workflow.status` when the id is not indexed. |
| OpenAPI drift | Snapshot test plus response validation in every contract test. |

## 11. Rollback

Delete `src/cji/api`, `src/cji/services`, `src/cji/http`, `src/cji/analytics`, `openapi/`, the new tests and the
`cji-api`/`cji-api-token` scripts; reverse `spec12-tracked.patch`; drop the `run_index` table (the workflow ignores
it when absent).
