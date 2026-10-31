# Spec 07 — Durable, Authenticated Collector: Design

## 1. Module layout
```text
cji_agent/collector/
  api.py         FastAPI app, routes, startup; module names tests patch stay (engine, CJI_ENV, CJI_ADMIN_KEY,
                 CJI_CORS_ORIGINS, UnconfiguredDatabase, _create_tables, _ping_keepalive, validate_collector_settings)
  models.py      response models (CollectResult, EventError, HealthStatus) — replaces the inactive Spec 03 models
  ingest.py      parse_body, validate_events, store_events (pure functions plus one database function)
  security.py    authenticate(key, conn) -> KeyGrant, key_fingerprint, RateLimiter (token buckets), client_address
  middleware.py  RequestContext (request id contextvar + log filter), body-size limit
```

## 2. Request flow for `POST /collect/batch`
```text
middleware: request id (OD-47) -> Content-Length / streamed size check (413)
route:
  1. content type application/json | text/plain, else 415            (OD-49)
  2. read body (bounded), json.loads -> 400 "invalid JSON"
  3. envelope: dict with api_key (str, 10..256) and events (list, 1..100) -> 422 envelope error
  4. X-CJI-Key present and != api_key -> 401
  5. rate limit by client address, then by key fingerprint -> 429 + Retry-After   (OD-46)
  6. with engine.begin() as conn:                                      (one transaction)
       grant = authenticate(api_key, conn)            -> 401 if unknown/inactive
       for i, raw in enumerate(events): TrackerEvent.model_validate(raw)
            invalid -> errors[i] = {"index", "event_id"?, "reason": "invalid", "fields": [...]}
            journey_id != grant.journey -> {"reason": "journey_not_authorized"}
       unique valid events (first occurrence wins; repeats count as duplicates)
       INSERT INTO live_events (...) VALUES (...), (...) ON CONFLICT (event_id) DO NOTHING RETURNING event_id
       accepted = len(returned); duplicates = valid - accepted (+ in-batch repeats)
     commit
  7. status: stored (no rejects) 200 | partial 207 | rejected 422 (nothing valid)
  any SQLAlchemyError / ConfigError in 6 -> rollback -> 503 {"status": "failed", "accepted": 0, "retryable": true}
```
The insert uses SQLAlchemy Core (`sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_nothing().returning()`)
against a `Table` that mirrors the existing DDL. Bind values come from `to_live_events_row` (unchanged).

Response body:
```json
{"status": "partial", "request_id": "…", "received": 3, "accepted": 1, "duplicates": 1, "rejected": 1,
 "errors": [{"index": 2, "event_id": "…", "reason": "invalid", "fields": ["event_type"]}]}
```
503 body: `{"status": "failed", "request_id": "…", "received": n, "accepted": 0, "duplicates": 0, "rejected": 0,
"retryable": true, "detail": "Events were not stored. Retry with the same event_id values."}`

## 3. Security details
- `authenticate`: `SELECT journey_name, is_active FROM api_keys WHERE api_key = :k` inside the write transaction.
  Keys are compared by the database index (no timing oracle beyond existence); the admin key keeps
  `secrets.compare_digest`.
- `key_fingerprint(key) = sha256(key)[:8]` — the only form of a key that reaches logs or rate-limit buckets.
- `RateLimiter`: dict of buckets `(capacity=rate, refill=rate/60 per s)`, monotonic clock injectable for tests,
  idle buckets pruned; `check(bucket_id) -> retry_after_s | None`.
- `client_address(request, hops)`: `request.client.host` when `hops == 0`; otherwise the `hops`-th address from the
  right of `X-Forwarded-For`, falling back to the peer.
- CORS per CO-03; startup check (`settings.roles.collector_problems`) adds "production origins must be https".

## 4. Validation limits (domain)
`TrackerEvent` gains `url: max_length 2048`, `element_selectors: max_length 512`, and a `metadata` validator
(serialised JSON ≤ 8192 bytes). Existing aliases, coercions and the taxonomy are unchanged; contract tests in
`tests/test_contracts.py` keep passing and gain boundary cases.

## 5. Health
| Route | Checks | 200 body | Failure |
|---|---|---|---|
| `/health/live` | none | `{"status": "ok"}` | — |
| `/health/ready` | `SELECT 1 FROM live_events LIMIT 1`, `SELECT 1 FROM api_keys LIMIT 1` | `{"status": "ready"}` | 503 `{"status": "not_ready"}` |
| `/health` (compat) | readiness plus `SELECT COUNT(*) FROM live_events` | `{"status": "ok", "live_events_count": n}` | 503 `{"status": "not_ready"}` |

## 6. Logging
A `logging.Filter` on the `collector` logger adds `request_id`. One summary line per batch:
`collect request_id=… key=ab12cd34 journey=user_onboarding received=3 accepted=1 duplicates=1 rejected=1 status=207`.
Database failures log `type(exc).__name__` and `exc_info`. SQLAlchemy error messages include bound parameters
by default, so the engine is created with `hide_parameters=True`; the log-redaction test covers a failing insert.

## 7. Tests (`tests/test_collector.py`, PostgreSQL-backed unless noted)
| Area | Cases |
|---|---|
| Authentication | missing key 422; unknown 401; inactive 401; header mismatch 401; dev key absent in production |
| Authorization | other-journey events rejected per event; `/live/stats` 403 without admin key, 200 with |
| Limits | body over limit 413 (Content-Length and streamed); 101 events 422; oversize metadata/url rejected per event |
| Rate limits | per key and per address 429 with `Retry-After` (fake clock); proxy hops (unit) |
| Content types | `text/plain` JSON stored; `text/html` 415; invalid JSON 400 |
| Idempotency | same batch twice: rows once, second response `duplicates`; repeats inside a batch |
| Partial | mix of valid, invalid, unauthorized: 207 with exact counts and indexes; all invalid 422, nothing stored |
| Durability | connect failure 503; insert failure (dropped table) 503 and no rows; commit failure (deferred constraint trigger) 503 and no rows; response never says stored |
| Health | live 200 without database; ready 200/503; `/health` compat |
| Correlation | valid id echoed; invalid id replaced; id in log records |
| Logging | captured records contain no key, user, session or event id, URL or metadata |
| CORS | allowed origin gets headers; unlisted origin none; admin header not allowed; production http origin refused at startup |
Unit (no database): envelope parsing, limiter, fingerprint, client address, response status mapping.

## 8. Risks
| Risk | Mitigation |
|---|---|
| Synchronous writes add latency to tracker requests | One multi-row statement per batch; the tracker does not wait on the response (`keepalive`, beacon) |
| Rate limits per process undercount with several workers | Documented; defaults sized for one worker |
| Journey authorization rejects existing keys whose `journey_name` differs from the tracker's journey | Rejections are per event with `journey_not_authorized`; README explains; owner can check `api_keys` (F-05) |
| Existing collector tests use a fake engine that cannot run multi-row RETURNING | Those cases move to the PostgreSQL-backed tests with the same assertions |

## 9. Rollback
`git apply -R evidence/spec07-tracked.patch`, then `git apply evidence/pre-spec07-tracked.patch`; restore untracked
files from `evidence/pre-spec07-untracked/`; delete the new collector modules and `tests/test_collector.py`.
