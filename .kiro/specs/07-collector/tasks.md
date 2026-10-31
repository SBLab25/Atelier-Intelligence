# Spec 07 — Durable, Authenticated Collector: Tasks
Sequential. `[x]` means evidence exists. No commits or pushes: each step is recorded as a patch file in `evidence/`.
**Environment:** protected environment (both database URLs point at a dead local port; the Supabase database is
live). PostgreSQL tests and the uvicorn smoke use only local disposable servers (pgserver, OD-51).
**Status:** Implemented 2026-10-28 with the default decisions OD-41 to OD-52 (approved: "implement spec 07").
Gate run 2026-10-28T04:22–04:29 (`evidence/gate-results.txt`, `evidence/final-numbers.txt`).

## Tasks
- [x] **T0 Prepare.** `pre-spec07-tracked.patch` (326,972 bytes), `pre-spec07-untracked/` (30 files); survey probe
  moved to `evidence/survey-probe.*` (beacon 422, 2 MB metadata accepted, open `/live/stats`).
- [x] **T1 Failing tests first.** `tests/test_collector.py` (73 tests) against the pre-Spec-07 collector: 7 passed,
  66 failed or errored (`before-tests-junit.xml`, `before-tests.log`). The 7 that passed: 4 envelope cases the old
  `EventBatch` already rejected (missing/short key, 0 or 101 events) and 3 `collector.security` unit tests that ran
  after `security.py` had been written; re-run with the module absent they fail (`before-tests-security-junit.xml`).
  Shared `pg_url` fixture moved from `test_repositories.py` to `conftest.py` (all 43 repository tests still pass).
- [x] **T2 Settings.** `CollectorSettings` with the five `CJI_COLLECTOR_*` keys (`KNOWN_KEYS`, `describe()`,
  `.env.example`, README); production check "CJI_CORS_ORIGINS must use https" (loopback http allowed); development
  key seeded for `JOURNEY_NAME` instead of `'onboarding'`.
- [x] **T3 Domain limits.** `TrackerEvent`: `url` ≤ 2048 after the query string is removed, `element_selectors`
  ≤ 512, `metadata` ≤ 8192 bytes of compact JSON. Boundary tests in `test_collector.py`.
- [x] **T4 Collector modules.** `collector/middleware.py` (request id, body limit), `security.py` (authenticate,
  fingerprint, token buckets, client address), `ingest.py` (envelope, per-event validation, one
  `INSERT … ON CONFLICT DO NOTHING RETURNING`), `models.py` (`CollectResult`, `EventError`, `HealthStatus`).
- [x] **T5 Routes.** `/collect/batch` synchronous and transactional; `/health/live`, `/health/ready`, `/health`
  (compat); `/live/stats` and `/admin/api-keys` behind the admin key with a per-address limit; CORS without the
  admin header, with `X-Request-ID`/`Retry-After` exposed; engine `hide_parameters=True`.
- [x] **T6 Existing tests and snippets.** `test_p0_security` live-stats case sends the admin key;
  `test_contracts` collector case moved to PostgreSQL (20 distinct event ids); `test_collector_models` tests the
  new response models; snippet generator requires `--api-key` (OD-52); `snippets/verify_tracker.py` lint (F-14);
  README routes, response contract, settings.
- [x] **T7 Gate.** Below. Change set: `spec07-tracked.patch` (353,972 bytes) and `spec07-new-files/` (12 untracked
  files with `MANIFEST.txt`).

## Gate (2026-10-28, protected environment)
| Check | Result | Spec 06 |
|---|---|---|
| Full suite (`-m "not integration"`) | 583/594 pass; the 11 failures are the F-01 set, identical | 510/521 |
| Tests added / removed | +75 / −2 (the two inactive response-model tests, replaced) | |
| Spec 07 test set (8 files incl. settings, cleanup, docs, repositories) | 433/433 | |
| `test_collector.py` before the change | 7/73 (see T1) | |
| Collector smoke: uvicorn, `CJI_ENV=production`, pgserver | 16/16 checks over HTTP, incl. no keys/ids/URLs/metadata in the server log | |
| Golden snapshot | identical to Spec 06 | identical |
| ruff (whole tree) | 120 findings | 135 |
| ruff on new/changed code | All checks passed | |
| mypy (whole tree) | Found 42 errors in 15 files (checked 70 source files) | 43 in 16 (66) |
| mypy `--strict` new collector modules / repositories | no issues (4 files) / no issues (5 files) | |
| bandit collector | no findings (`collector/api.py` B608 1 → 0) | |
| Static compare vs Spec 01 | no changed file worse than baseline | |
| Demo pipeline, ingest probe, mode mismatch, `--help` smokes, `settings check` | as before | |
| Snippet generator | without `--api-key`: exit 2 with usage; with a key: files written | |
| `git diff --check` | clean | clean |
| Tracked `data/events.parquet` | unchanged | unchanged |

Post-gate fix: the generated `verify_tracker.py` used `timezone.utc` (ruff UP017). Fixed to `datetime.UTC`;
re-checked in `gate-recheck-snippet.log` (generator exit 0, ruff clean on the generated file and the generator,
`test_settings`/`test_cleanup`/`test_docs` exit 0).

## Acceptance criteria (Prompt 6)
| # | Criterion | Evidence |
|---|---|---|
| 1 | Failed persistence is never reported as successful storage | `test_unreachable_database_is_503`, `test_unconfigured_database_is_503`, `test_insert_failure_is_503_and_stores_nothing`, `test_missing_table_is_503`, `test_commit_failure_is_503_and_stores_nothing` (deferred constraint trigger): 503, `status: failed`, `accepted: 0`, no rows |
| 2 | Retries do not duplicate events | `test_retrying_a_batch_stores_each_event_once`, `test_repeats_inside_one_batch_are_duplicates`, `test_mixed_batch_…` (second post), smoke "retry is duplicates" |
| 3 | Collector integration tests pass with a temporary test database | 433/433 on pgserver; smoke 16/16 |

## Decisions applied, and one deviation
OD-41 to OD-52 as written, with one change to OD-50 / design §6: database failures log the exception type and
SQLSTATE but **not** `exc_info`. PostgreSQL error text can contain row values (for example a CHECK violation's
"Failing row contains (…)" detail, which includes user and session ids), and `hide_parameters` does not remove
that. `test_logs_never_contain_identifiers_or_payload` covers this case.

## Behaviour changes callers can see
- `POST /collect/batch` answers after the commit: 200 `stored`, 207 `partial`, 422 `rejected`, 503 `failed`;
  never `queued`. Identical events in one batch are now one row plus duplicates (before: one row, counted as
  accepted N times).
- A key may only write its own journey (`journey_not_authorized` per event).
- `GET /live/stats` requires `X-CJI-Admin-Key`; database errors there return 503 instead of 500.
- `POST /admin/api-keys` without the header returns 403 (was 422); `journey_name` must be a valid identifier.
- Browsers can no longer send `X-CJI-Admin-Key` (CORS).
- `text/plain` beacon batches are stored (F-19 fixed).

## Findings
| ID | Finding | Status |
|---|---|---|
| F-01 | 11 obsolete tests in `test_supervisor.py` | Open (Spec 09, or delete) |
| F-05 | Possible old `cji_live_…` key in Supabase `api_keys` | Open (owner) |
| F-07 | Collector per-row insert inside one transaction | **Fixed** (OD-41) |
| F-14 | `snippets/verify_tracker.py` template lint | **Fixed** (OD-52) |
| F-17 | Snippet generator writes an unregistered key | **Fixed** (OD-52) |
| F-19 | `sendBeacon` batches rejected with 422 | **Fixed** (OD-49) |
| F-20 | `live_events.event_id` is a global key across journeys | Open (later schema Spec) |
| F-21 | Tracker keys stored in plain text | Open (later schema Spec) |
| F-22 | Existing `api_keys` rows whose `journey_name` differs from the tracker's `journey_name` now get `journey_not_authorized` for every event | New; owner checks Supabase `api_keys` before deploying |
| F-23 | The committed `snippets/verify_tracker.py` posts with `cji_dev_localtest` to the deployed collector; that key exists only when the collector runs with `CJI_ENV=development` | New; regenerate with `--api-key` |
| F-24 | Rate limits are per process | Documented (README); shared store only if several workers are deployed |

## Rollback
1. `git apply -R .kiro/specs/07-collector/evidence/spec07-tracked.patch`, then
   `git apply .kiro/specs/07-collector/evidence/pre-spec07-tracked.patch` (restores the pre-Spec-07 tracked state).
2. Copy the files in `evidence/pre-spec07-untracked/` back over their paths (settings, domain, tests).
3. Delete the files listed as `new` in `evidence/spec07-new-files/MANIFEST.txt`
   (`collector/ingest.py`, `collector/middleware.py`, `collector/security.py`, `tests/test_collector.py`).
No schema or data migration was made, so nothing in PostgreSQL needs to be undone.
