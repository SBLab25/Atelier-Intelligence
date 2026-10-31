# Spec 12 — Versioned Backend API (`/api/v1`): Requirements

Source: `kiro_upgrade_prompts.md`, Prompt 11 ("Create the first stable /api/v1 backend contract for the Next.js
frontend"); guide row "12 Backend API" and §10 "Spec 12". Builds on Spec 03 (domain contracts), Spec 04 (settings,
service registry), Spec 05 (repositories), Spec 07 (collector request ids, rate limiter), Spec 09 (durable workflow),
Spec 10 (safe reports) and Spec 11 (package `cji`, `CJI_HOME`).

**Status:** written 2026-10-28; approved (defaults OD-108 to OD-127); **implemented** 2026-10-28, gate passed (record and deviations D-1 to D-8 in tasks.md).

## 1. Current state (surveyed after Spec 11)

The only HTTP service is the collector (`cji.collector.api`, port 8000): `GET /health`, `/health/live`,
`/health/ready`, `/tracker.js`, `POST /collect/batch` (tracker keys), `GET /live/stats` and `POST /admin/api-keys`
(one shared admin key). Everything the frontend needs is reachable today only through the CLI (`cji --status`), the
Streamlit dashboard (direct SQL and `data/last_run.json`) or the MCP servers. There is no frontend code in the
repository; the service registry already reserves `frontend` (port 3000).

Evidence: `evidence/survey/` (`survey.py`/`survey.txt`: routes, public functions, data sources, versions;
`probe_errors.py`/`probe_errors.txt`: error bodies the current FastAPI app returns).

### Findings

| ID | Finding | Evidence |
|---|---|---|
| F-57 | **Error bodies are inconsistent and leak input.** The collector answers `{"status": "rejected", "request_id", "detail"}` for its own errors, FastAPI's `{"detail": "..."}` for `HTTPException` (403, 429, 503, 500) and unknown routes, and FastAPI's default 422 list for validation errors. The 422 body echoes the submitted value (`"input": "xxxx…"`), and body validation runs before the admin-key check, so an unauthenticated caller gets field-level detail. Only collector responses carry `X-Request-ID`. | probe_errors.txt |
| F-58 | **No read authentication or roles.** Tracker keys can only write events for one journey; the admin key is one shared secret for two admin routes. Nothing authenticates a person or limits what they may read. | survey.txt (collector), `collector/security.py` |
| F-59 | **Runs cannot be listed.** `Workflow` looks a run up by id only (`status(run_id)`); checkpoints are keyed by LangGraph thread id; the journey of a run is only inside its state. Nothing answers "the runs of journey X" or "the latest completed run". | `workflow/runtime.py` |
| F-60 | **Read logic lives inside MCP tools or the dashboard.** Step metrics and the funnel are in the repositories (reusable). Friction scoring exists only as `@mcp.tool` functions in `mcp_servers/friction_engine_server.py`. Insights exist in run state (and in Chroma for semantic search). Reports exist only as files named `cji_report_<journey slug>_<run id>.html`. The dashboard's KPIs are its own SQL. | survey.txt |
| F-61 | **Events have no paging.** `EventRepository.events(journey, limit, step_id, event_type)` returns the first `limit` rows with no ordering contract and no cursor, in both repositories. | `repositories/base.py` |
| F-62 | **Approval runs the rest of the workflow inside the call.** `Workflow.approve` updates the state and then drives the report step, which can take up to `CJI_WORKFLOW_STEP_TIMEOUT_S` (900 s by default). `status()` returns `lease_owner` = `<hostname>:<pid>:<suffix>`. | `workflow/runtime.py` |
| F-63 | **No schema tooling for OpenAPI.** FastAPI 0.162 generates OpenAPI 3.1. `jsonschema` 4.26.0 is installed (transitive, in the lock) but not declared; `openapi-spec-validator`, `schemathesis` and `hypothesis` are not installed. | survey.txt |

Not findings: the repositories, `domain/*` TypedDicts, `RateLimiter`, `resolve_request_id` and the reports module
are reusable as they are; every response type the API needs already exists as a domain contract.

## 2. Decisions (defaults; confirm or change before implementation)

| ID | Decision | Default | Alternatives (rejected by default) |
|---|---|---|---|
| OD-108 | Where the API runs | New FastAPI app **`cji.api`** (package `src/cji/api/`), console script **`cji-api`**, its own registry service `api` (port **8006**, HTTP). All routes under `/api/v1`. The collector is unchanged. | Mount `/api/v1` in the collector (mixes public tracker ingestion with authenticated reads in one process and one CORS policy). |
| OD-109 | Authentication | **Bearer tokens**: `Authorization: Bearer cji_api_<random>`. Only the SHA-256 of each token is stored, in a token file (`CJI_API_TOKENS_FILE`, default `<CJI_HOME>/data/api_tokens.json`, gitignored) with label, role, journeys, created and optional expiry. Managed by a new CLI `cji-api-token create/list/revoke` (prints a new token once). Lookup in constant time; the file is re-read when it changes. Spec 13's Next.js server holds the token (never the browser bundle). | OIDC/JWT from an identity provider (no provider exists yet; can be added later as a second authenticator producing the same principal). Session cookies with a user table and passwords (needs a user store and CSRF handling). Tokens in an environment variable (no expiry or revocation without a restart). |
| OD-110 | Authorization | Three roles: **viewer** (journeys, metrics, friction, insights, reports, runs, health details), **operator** (viewer + raw events + approval), **admin** (operator; reserved for later admin routes). Each token also lists the journeys it may see (`["*"]` = all). Missing or bad token → 401; valid token without the role or the journey → 403. A run or report whose journey cannot be determined is visible only to `*` tokens. | Per-route scopes chosen by each token (more flexible, more to get wrong in v1). One role for everyone. |
| OD-111 | Journeys resource | `GET /journeys` lists the configured journey definitions (today one: `JOURNEY_NAME` with `JOURNEY_CONFIG` steps), filtered by the token's journeys. Paginated, so more journeys can be added without a contract change. | Discover journeys from event data (`DISTINCT journey_id`: unbounded, and step order is unknown). Rename to "projects" (no project concept exists yet). |
| OD-112 | Metrics and friction | Computed **in the API process** from the configured repository (same mode as the other services): `GET /journeys/{id}/metrics` (step metrics + funnel) and `/journeys/{id}/friction` (scores). The scoring code moves from the friction MCP server to a pure module `cji.analytics.friction`; the server imports it, so scores are identical (golden comparison). No MCP server is needed for reads. | Call the MCP servers from the API (needs them running; slower; another failure mode). Serve only the friction of the last run. |
| OD-113 | Insights | From **run state** in the checkpoint store: `GET /journeys/{id}/insights?run_id=` (default: the latest run of the journey that has insights) and the same list in run detail. Chroma is not read in v1. | Chroma search endpoint (semantic, global across runs, needs an embedding model). |
| OD-114 | Reports | `GET /reports` (metadata), `GET /reports/{report_id}` (metadata), `GET /reports/{report_id}/content` (the HTML file, `text/html`, `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`). `report_id` = the run id in the file name (pattern-checked; the resolved path must be a direct child of the reports directory). Journey comes from the run index; size is already bounded at 1 MiB (Spec 10). | Serve report HTML as JSON strings. Expose file paths. |
| OD-115 | Run index | New table `run_index` in the checkpoint database (next to `run_leases`): run id, journey, mode, status, created/updated, report present. Written by `Workflow` on every run status change (the place that already audits them). On API start, runs present in the checkpoints but missing from the index are indexed once (read-only, parameter-free query on the checkpoint table, then `Workflow.status`). `GET /runs?journey_id=&status=` reads the index. | Parse `data/audit/workflow.jsonl` (audit can be off; not an index). Scan every checkpoint thread on each request (slow; couples to LangGraph tables). |
| OD-116 | Workflow endpoints | `GET /runs`, `GET /runs/{run_id}` (status, steps, failure, approval, report id, insight count, `active` flag instead of the lease owner) and **`POST /runs/{run_id}/approval`**. Approval marks the run approved under the run lease and returns **202** with the run; the report step continues in a background task of the API process (status is polled). If the API process stops, the run stays `approved` and `cji --resume` (or a later API endpoint) continues it. Starting and resuming runs over HTTP are not in v1. | Run the report step inside the request (up to 900 s). Add start/resume endpoints now (needs the MCP servers from the API; not asked for). |
| OD-117 | Idempotency | Every mutation (v1: approval) requires `Idempotency-Key` (8–64 of `A-Za-z0-9._-`). The API stores key + token + route + request hash + response for 24 h in `<CJI_HOME>/data/api_state.db`. Same key and same request → the stored response again with `Idempotent-Replayed: true`; same key, different request → 409 `idempotency_key_reused`; same key still in progress → 409 `request_in_progress`. Approval is also idempotent by state: approving an approved or completed run returns 200 with `already_approved: true`. | Optional key (clients that forget it get no replay protection). State-based idempotency only (no defined behaviour for retried requests across a timeout). |
| OD-118 | Error envelope | **RFC 9457** `application/problem+json` for every non-2xx response: `type` (`urn:cji:problem:<code>`), `title`, `status`, `detail`, plus `code`, `request_id` and, for validation, `errors: [{location, field, reason}]` (no submitted values). Stable codes (design §5). Authentication runs before body validation, so unauthenticated callers never see field detail. | A custom `{"error": {...}}` object. FastAPI defaults (F-57). |
| OD-119 | Pagination and bounds | Lists return `{"data": [...], "page": {"limit": n, "next_cursor": str \| null}}`. `limit` 1–200, default 50. Cursors are opaque (base64url JSON of the keyset position, signed with an HMAC key from `CJI_API_CURSOR_SECRET` or a per-process random key) so they cannot be edited; a bad or foreign cursor is a 422. Events use keyset order `(timestamp desc, event_id desc)` (new repository method); runs `(updated_at desc, run_id)`; reports `(modified desc, report_id)`. No total counts. Windows: `days` 1–365, `minutes` 1–43 200. Request bodies ≤ 16 KiB. | Offset/limit (unstable under inserts, unbounded cost on deep pages). Unsigned cursors. |
| OD-120 | Request ids | The collector's request-id middleware (accept a well-formed `X-Request-ID`, else a UUID4) moves to a shared module `cji.http` and is used by both apps. Every response, including errors and 404s, carries `X-Request-ID`; every problem body repeats it; log lines include it. | — |
| OD-121 | Rate limits | Token buckets (existing `RateLimiter`): `CJI_API_RATE_PER_TOKEN` (default 120/min) per token, and `CJI_API_RATE_PER_IP` (default 60/min) per client address for requests without a valid token (counted before the token check, so guessing is limited). 429 problem with `Retry-After`. Per process, as for the collector. | No limit. Shared store (Redis) — not available. |
| OD-122 | Validation and response models | Every route has typed parameters and a `response_model` built from the domain contracts, with `extra="forbid"` on request bodies; responses are validated by FastAPI before they are sent. Unknown query parameters are a 422. | — |
| OD-123 | OpenAPI | FastAPI generates OpenAPI 3.1 at `GET /api/v1/openapi.json` (docs UI at `/api/v1/docs` only when `CJI_ENV=development`). Every route declares its error responses with the problem schema. A committed snapshot `cji_agent/openapi/v1.json` must equal the generated document (test). Contract tests validate **every** response they receive (success and error) against the schema in the document with `jsonschema`, so the document matches actual responses. The document itself is checked with `openapi-spec-validator`. | Hand-written OpenAPI (drifts). No snapshot (changes go unnoticed). |
| OD-124 | Test dependencies | Add `jsonschema` (already in the lock, 4.26.0) and `openapi-spec-validator` (new) to the `test` group; regenerate `requirements.lock` with `make_lock.py` (only additions allowed in `lock-diff.txt`). No new runtime dependency. | Skip document validation (the snapshot would only be compared with itself). |
| OD-125 | Adapters for CLI and Streamlit | A service layer **`cji.services`** (journeys, metrics, friction, insights, reports, runs) holds the read logic; the API routes are thin HTTP adapters over it. The CLI's `--status`/`--approve` and the dashboard's report list and last-run panel call the same services, with today's output unchanged (existing tests plus new ones). Other dashboard SQL stays until Spec 14 (parity). | API-only logic (CLI and dashboard drift from it). Rewrite the dashboard on the API now (that is Spec 14). |
| OD-126 | CORS and headers | `CJI_API_CORS_ORIGINS` (explicit list; default the `frontend` registry URL in `development`, empty otherwise); methods GET/POST; headers `Authorization`, `Content-Type`, `Idempotency-Key`, `X-Request-ID`; no credentials. All responses: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`. Startup refuses production without `CJI_API_TOKENS_FILE` content and without https origins (new role `api` in `settings.roles`). | — |
| OD-127 | Failure hygiene | One exception handler turns anything unexpected into a 500 problem `internal_error` with only the request id; storage failures become 503 `storage_unavailable`, configuration errors 503 `service_misconfigured`, a busy run 409 `run_busy`. Logs get the exception type and a scrubbed message (`integrations.audit.scrub` with the configured secrets), never the token. Tests inject failures whose messages contain sentinel secrets, driver text and file paths and assert none reaches the client. | — |

## 3. Requirements

**R1 Endpoints.** Under `/api/v1`: `GET /health` (public: `ok`/`degraded`, version, mode), `GET /health/details`
(viewer: repository, checkpoint store, reports directory), `GET /me` (the caller's label, role, journeys),
`GET /journeys`, `GET /journeys/{journey_id}`, `GET /journeys/{journey_id}/events` (operator),
`GET /journeys/{journey_id}/metrics`, `GET /journeys/{journey_id}/friction`, `GET /journeys/{journey_id}/insights`,
`GET /reports`, `GET /reports/{report_id}`, `GET /reports/{report_id}/content`, `GET /runs`, `GET /runs/{run_id}`,
`POST /runs/{run_id}/approval` (operator).

**R2 Authentication and authorization.** As OD-109, OD-110. 401 (no or bad token) and 403 (valid token, missing
role or journey) are distinct. Journey ids are configuration, not secrets: a journey outside the token's list
answers 403 whether or not it exists; an unknown journey inside the list (or with `*`) answers 404. Runs and
reports of journeys the caller may not see answer 404, exactly like ids that do not exist, so their existence is not
revealed; a missing role on a visible run (a viewer approving) answers 403.

**R3 Validation.** As OD-122: path, query and body parameters are typed and bounded; identifiers use the domain
`Identifier` rules; run and report ids match `[A-Za-z0-9-]{1,64}`.

**R4 Pagination and bounded sizes.** As OD-119. No endpoint returns more than 200 items or more than 1 MiB.

**R5 Errors.** As OD-118, OD-127, with the codes in design §5.

**R6 Request ids.** As OD-120.

**R7 Idempotency.** As OD-117.

**R8 Rate limits.** As OD-121.

**R9 OpenAPI.** As OD-123: accurate, snapshotted, validated, and used to validate every contract-test response.

**R10 Adapters.** As OD-125: CLI commands and the Streamlit dashboard keep their behaviour; the shared services are
the only implementation of the read logic the API exposes.

**R11 Operations.** `cji-api` console script; registry service `api`; settings keys (`CJI_API_TOKENS_FILE`,
`CJI_API_RATE_PER_TOKEN`, `CJI_API_RATE_PER_IP`, `CJI_API_CORS_ORIGINS`, `CJI_API_CURSOR_SECRET`) in the settings
model, `.env.example` and the README; `cji-settings check --role api`.

## 4. Non-goals

- The Next.js frontend (Spec 13) and Streamlit parity (Spec 14).
- Starting or resuming runs, ingestion uploads and token management over HTTP (CLI only in v1).
- User accounts, OIDC, sessions or cookies (OD-109 keeps the principal model open for them).
- Semantic insight search (Chroma) and dashboard-only KPIs (revenue, audience, heatmap).
- Changing the collector's public contract (it keeps its own response shapes; only the request-id code moves).
- Distributed rate limiting or multi-process idempotency beyond one SQLite file.

## 5. Acceptance criteria (Prompt 11)

| Criterion | How it is shown |
|---|---|
| Contract tests cover success, validation, unauthorized, forbidden, not-found, conflict, rate-limit and server-error cases | `tests/test_api_contract.py`: a case matrix per endpoint (design §8), each asserting status, `application/problem+json` shape, `code`, `X-Request-ID`, and schema validity. |
| OpenAPI matches actual responses | Every response in the contract tests is validated against the response schema the generated OpenAPI declares for that path, method and status; the snapshot equals the generated document; `openapi-spec-validator` passes. The gate also runs the API process and fetches the live document. |
| Internal exceptions and secrets never reach clients | Injected failures (repository, checkpoint store, report read, unexpected exceptions) with sentinel secrets, driver messages and paths: no sentinel, stack trace, file path, SQL or token in any body or header; 422 bodies never contain submitted values. |
| CLI and Streamlit keep working | Existing CLI, workflow and dashboard tests pass unchanged; the Spec 11 gate pipelines (old and new commands) pass; new tests show the CLI and dashboard read through `cji.services`. |
| Bounded results, pagination, idempotency, request ids | Contract tests for limits, cursors (round trip, tampered, foreign), replay and key reuse, request-id echo and generation. |
