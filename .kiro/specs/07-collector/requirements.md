# Spec 07 — Durable, Authenticated Collector: Requirements
**Source:** `kiro_upgrade_prompts.md` Prompt 6. **Findings addressed:** `refactoring.md` R-09 (writes reported before
persistence, duplicates counted as accepted), F-07 (per-row insert inside one transaction), F-14 and F-17 (snippet
generator), plus three found by the survey probe (F-19 to F-21).
**Branch:** `phase-02-security` (no commits; patch files are the rollback points, as in Specs 02–06).
**Status:** written 2026-10-28; OD-41 to OD-52 approved as defaults ("implement spec 07"); implemented 2026-10-28. One deviation from OD-50 is recorded in `tasks.md`.

## 1. Current state (surveyed after Spec 06)
A probe ran the current `collector/api.py` with a fake engine (no network).

| Concern | Today | Problem |
|---|---|---|
| Write path | `POST /collect/batch` checks the key, schedules `write_events` as a background task, returns `{"status": "queued", "accepted": len(events), "rejected": 0}` | The response is sent before anything is stored. A database failure is only logged. `accepted` counts every event, including ones that later fail or already exist (R-09). |
| Inserts | One transaction, one `INSERT … ON CONFLICT (event_id) DO NOTHING` per event, each in `try/except` | After the first failure PostgreSQL aborts the transaction and every later insert fails, but each is still counted (F-07). A conflict-skipped duplicate counts as accepted. |
| Idempotency | `live_events.event_id` is the primary key; tracker event ids are UUIDs | Retries cannot create duplicate rows, but the response never says an event was a duplicate. `event_id` is global, not per journey (F-20). |
| Validation | `EventBatch` (domain contract): 1–100 events; one invalid event rejects the whole batch with 422 | No per-event result. No size limits: **a 2 MB `metadata` object was accepted**. No request-body limit. |
| `sendBeacon` | The tracker sends `abandon` batches with `navigator.sendBeacon`, which uses `Content-Type: text/plain` | **Probe: 422** ("Input should be a valid dictionary"). Every abandon event sent by beacon is lost today (F-19). |
| Authentication | Body `api_key` (required) or `X-CJI-Key`, looked up in `api_keys` | Body and header may disagree; the header is ignored when the body has a key. No authorization: any active key can write events for any journey. Keys are stored in plain text (F-21). |
| Development key | Seeded only when `CJI_ENV=development` (Spec 02), for journey `'onboarding'` | The default journey is `user_onboarding`, so the seeded key does not match the tracker's journey. |
| `/live/stats` | Per-step event counts, **no credentials** (probe: 200) | Leaks traffic data to anyone. |
| `/admin/api-keys` | Admin key, constant-time comparison; generic database errors (Spec 06) | No rate limit; `journey_name` is not validated. |
| CORS | Explicit origins, no credentials (Spec 02); allows `X-CJI-Admin-Key` from browsers | Admin calls are server-to-server and need no browser access. Production origins may be plain `http`. |
| Rate limiting | None | One client can exhaust the database. |
| Correlation | None | Logs cannot be tied to a request. |
| Health | `GET /health` runs `SELECT COUNT(*) FROM live_events` (full scan) and raises 500 when the database is down | No separate liveness and readiness. |
| Logging | `Error inserting event {event_id}: {e}` | Logs event identifiers and raw driver errors. |
| Snippets | `tracker/snippet_generator.py` invents an unregistered `cji_live_…` key (F-17); `snippets/verify_tracker.py` has an unused import and a broad catch (F-14) | Generated snippets get 401. |

## 2. Decisions (defaults; confirm or change before implementation)
| ID | Question | Default | Alternatives considered |
|---|---|---|---|
| OD-41 | Write semantics | **Synchronous and transactional.** Valid events are written in one transaction with one multi-row `INSERT … ON CONFLICT (event_id) DO NOTHING RETURNING event_id`; the response is sent only after commit. Any database error rolls back the whole batch and returns 503 with `accepted: 0`. Nothing is reported as stored unless it was committed. | Background task plus a durable outbox table: a schema change and a worker; the browser does not wait for the response anyway. Per-row best effort: F-07. |
| OD-42 | Idempotency | **`event_id` is the idempotency key** (already the `live_events` primary key; the tracker sends UUIDs). Retrying a batch with the same events stores nothing twice; the retry reports them as `duplicates`. Duplicates inside one batch are collapsed before the insert. | An `Idempotency-Key` header with a stored response table: a schema change and no extra safety at event level. Per-journey composite key: changes the `live_events` primary key (F-20). |
| OD-43 | Partial batches | **Envelope errors reject the request; event errors are per event.** Envelope: not JSON, wrong content type, body too large, missing or invalid `api_key`, 0 or more than 100 events → 400/413/415/422/401, nothing stored. Each event is validated on its own; valid events are stored even if others are rejected. Response: `received`, `accepted` (newly stored), `duplicates` (already stored), `rejected`, and `errors` (`index`, `event_id` when present, `reason`, `fields`; input values are not echoed). HTTP 200 when no event was rejected, 207 when some were, 422 when all were. | All-or-nothing on any invalid event: today's behaviour, loses good events. Always 200: clients cannot tell a full reject. |
| OD-44 | Authentication and authorization | **A tracker key authorizes events for its own journey only.** `api_key` (body) is required; `X-CJI-Key`, when sent, must equal it, else 401. Unknown or inactive key → 401. Events whose `journey_id` differs from the key's `journey_name` are rejected with `journey_not_authorized`. `/live/stats` requires the admin key. Admin `journey_name` must be a valid journey id. The development key is seeded only in `CJI_ENV=development`, for `JOURNEY_NAME`. | Keep cross-journey writes: one leaked key pollutes every journey. Hash keys at rest: a schema and migration change (F-21, later Spec). |
| OD-45 | Limits | Request body ≤ `CJI_COLLECTOR_MAX_BODY_BYTES` (default 262144); 1–100 events (unchanged); per event: `metadata` ≤ 8192 bytes as JSON, `url` ≤ 2048, `element_selectors` ≤ 512 characters, added to the domain `TrackerEvent`. | Body limit only: one huge event can still fill a batch. |
| OD-46 | Rate limiting | **In-process token buckets**: per tracker key (default 120 requests/minute), per client address (default 300/minute), admin endpoints per address (10/minute); 429 with `Retry-After`. The client address is the socket peer unless `CJI_COLLECTOR_TRUSTED_PROXY_HOPS` > 0 (then `X-Forwarded-For`, counted from the right). Limits are per process: documented. | Redis or database counters: new infrastructure. No limit: fails the Prompt. |
| OD-47 | Correlation | `X-Request-ID` is accepted when it matches `^[A-Za-z0-9._-]{8,64}$`, otherwise a UUID4 is generated; echoed in the response header and the `request_id` field; attached to every collector log record. | Trust any client value: log injection. |
| OD-48 | Health | `GET /health/live` (process up, no database, always 200) and `GET /health/ready` (database reachable and `live_events` and `api_keys` present; 503 otherwise; no error text). `GET /health` stays for compatibility (README, keep-alive) and becomes readiness with its old `live_events_count` field. | Remove `/health`: breaks the documented keep-alive URL. |
| OD-49 | `sendBeacon` bodies (F-19) | Accept JSON with `Content-Type: application/json` or `text/plain` (what `sendBeacon` sends); other types → 415. The body is read with the size limit before parsing. | Change the tracker to send a JSON `Blob`: a public-script change; old deployed trackers would keep losing events. |
| OD-50 | Logging | Never log API keys, user or session ids, event ids, URLs or metadata. Log the request id, a key fingerprint (first 8 hex digits of SHA-256), the journey, counts, status and error type. Enforced by a test that captures log records. | Redact by pattern after the fact: misses new fields. |
| OD-51 | Test database | Move the Spec 05 `pg_url` fixture (pgserver on a temporary directory, or loopback-only `CJI_TEST_DATABASE_URL`) to `tests/conftest.py` so collector and repository tests share it. | Fakes only: cannot show transaction behaviour. |
| OD-52 | Snippet generator (F-17, F-14) | `--api-key` is required (a key from `POST /admin/api-keys`); the generator no longer invents keys. `verify_tracker.py` template: no unused import, catches `requests.RequestException`. Regenerated snippets are not committed. | Leave: generated snippets keep failing with 401. |

## 3. Requirements
| ID | Requirement | Intended behaviour change |
|---|---|---|
| CO-01 | Events SHALL be validated with the domain `TrackerEvent`/`EventBatch` contract; the stored row SHALL come from `to_live_events_row` (unchanged mapping). | Size limits (OD-45) |
| CO-02 | Authentication and authorization per OD-44. | Cross-journey writes rejected; `/live/stats` needs the admin key |
| CO-03 | CORS: explicit origins only, no credentials, methods `GET, POST, OPTIONS`, request headers `Content-Type, X-CJI-Key, X-Request-ID`, exposed headers `X-Request-ID, Retry-After`; in production every origin SHALL be `https` unless loopback (startup check). Development defaults only when `CJI_ENV=development`. | Admin header no longer allowed from browsers |
| CO-04 | Request and batch limits per OD-45; 413 with a JSON body for oversize requests. | — |
| CO-05 | Rate limits per OD-46, configurable; 429 with `Retry-After`. | New |
| CO-06 | Idempotency per OD-42. | Duplicates reported |
| CO-07 | Responses per OD-43 with `accepted`, `duplicates`, `rejected`, `received`, `errors`, `request_id`; `status` is `stored`, `partial`, `rejected` or `failed` (never `queued`). | Response shape extended; `"queued"` removed |
| CO-08 | Durable writes per OD-41: 2xx only after commit; database failure → 503, `accepted: 0`, `retryable: true`, `Retry-After`, no driver text. | Synchronous |
| CO-09 | Correlation ids per OD-47. | New header |
| CO-10 | Health endpoints per OD-48. | New routes |
| CO-11 | `text/plain` JSON accepted per OD-49. | Beacon events stored |
| CO-12 | Logging per OD-50. | — |
| CO-13 | Development behaviour (dev key, dev CORS origins, relaxed startup checks) only with `CJI_ENV=development`; tests prove production refuses each. | Dev key journey fixed |
| CO-14 | New settings in `settings/` (typed, documented in `.env.example` and README): `CJI_COLLECTOR_MAX_BODY_BYTES`, `CJI_COLLECTOR_RATE_PER_KEY`, `CJI_COLLECTOR_RATE_PER_IP`, `CJI_COLLECTOR_ADMIN_RATE_PER_IP`, `CJI_COLLECTOR_TRUSTED_PROXY_HOPS`. | — |
| CO-15 | Snippet generator per OD-52. | `--api-key` required |

## 4. Non-goals
Changing the meaning of public events (taxonomy, field names, `to_live_events_row` mapping, tracker wire format).
Schema changes to `live_events` or `api_keys` (hashing keys, composite keys: F-20, F-21). Distributed rate limiting.
Outbox or queue infrastructure. Changing `tracker.js`. Dashboard, MCP servers and the pipeline.

## 5. Acceptance criteria (Prompt 6)
1. **Failed persistence is never reported as successful storage**: tests force failures at connect, at insert and at
   commit against a real PostgreSQL; each returns 503 with `accepted: 0` and leaves the table unchanged.
2. **Retries do not duplicate events**: sending the same batch twice (and a batch with repeated events) stores each
   `event_id` once; the second response reports them as `duplicates`.
3. **Collector integration tests pass with a temporary test database** (pgserver on a temporary directory): auth,
   authorization, limits, rate limits, duplicates, partial batches, database failures, beacon bodies, health,
   correlation ids, log redaction. Full suite fails only F-01; ruff and mypy no worse; no changed file worse.
