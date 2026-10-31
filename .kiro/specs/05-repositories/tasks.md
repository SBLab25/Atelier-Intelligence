# Spec 05 — Repository and Data-Access Isolation: Tasks
Sequential. `[x]` means evidence exists. No commits or pushes: each step is recorded as a patch file in `evidence/`.
**Environment:** protected environment (both `DATABASE_URL` and `SUPABASE_DATABASE_URL` point at a dead local port;
the Supabase database is live). PostgreSQL tests use only a local disposable server (OD-32).
**Status:** Spec written 2026-10-28; OD-29 to OD-33 approved with defaults; **implemented and gated 2026-10-28**
(gate run 01:52:30–01:56:32).

## Tasks
- [x] **T0 Prepare.** `evidence/pre-spec05-tracked.patch` saved. Golden snapshot and full suite matched Spec 04
  (344/355, F-01 only). `pgserver==0.1.4` (PostgreSQL 16.2) installed into the baseline venv with fasteners 0.20
  and psutil 7.2.2.
- [x] **T1 Failing tests first.** `tests/test_repositories.py` and `tests/test_journey_data_service.py` written
  first: 42/65 passed before migration, 23 failed (`evidence/before-tests.log`, `before-tests-junit.xml`).
  The realtime probe (`evidence/t1-realtime-probe.txt`, `scripts/probe_realtime_before.py`) ran today's realtime
  code against local PostgreSQL 16.2 and confirmed F-08 and F-06 (below). `read_sql` returns float64/int64,
  not `Decimal`, so no type conversion was needed. Spec 02/03 tests that patched module globals:
  `test_p0_security.py` R-02 and R-04, `test_contracts.py` (`CJI_MODE` monkeypatch).
- [x] **T2 `repositories/` package.** `base.py`, `queries.py`, `duckdb_parquet.py`, `postgres.py`, `__init__.py`
  (factory `event_repository(settings)`, `get_repository()`, `reset_repository()`, `use_repository()`).
  `mypy --strict repositories`: no issues in 5 files.
- [x] **T3 Journey-data service.** `mcp_servers/journey_data_server.py` calls the repository only; no mode branches
  (checked by AST in `test_service_has_no_mode_branches`); argument validation (limit 1–1000, minutes 0–43200,
  days 0–3650, filters ≤128 characters); result shapes unchanged; demo SQL text unchanged.
- [x] **T4 Ingestion writes.** `ingest_to_store` writes through `append_events` (OD-29, OD-30, OD-31), refuses a
  mode mismatch (OD-33), reports true counts and a new `records_duplicate` key.
- [x] **T5 Workers.** `data_worker` sends `days_back` and `minutes_back` to both tools and raises `ModeMismatch`
  when the server mode differs from the run mode.
- [x] **T6 Existing tests.** R-02/R-04 in `test_p0_security.py` moved to `use_repository` plus `engine_factory`;
  `test_contracts.py` no longer patches `CJI_MODE`. Assertions unchanged. Applied by `scripts/apply_spec05.py`.
- [x] **T7 Gate.** Results below; `evidence/spec05-tracked.patch` and `evidence/spec05-new-files/` saved.

## Gate results (`evidence/gate-results.txt`, `evidence/final-numbers.txt`)
| Check | Result | Evidence |
|---|---|---|
| Full suite (not integration) | 409/420 pass; the 11 failures are exactly the F-01 set (none new, none fixed) | `gate-pytest-full.log`, `gate-pytest-junit.xml` |
| Spec 05 tests | 65/65 pass, 0 skipped (before migration 42/65); 22 run against local PostgreSQL 16.2 | `gate-new-tests.log`, `gate-new-tests-junit.xml` |
| Golden snapshot | identical to Spec 04 | `gate-golden.log`, `golden-after.json` |
| ruff, whole repo | 233 findings (Spec 04: 246, baseline 266) | `gate-ruff.log` |
| ruff, new code | all checks passed | `gate-ruff-new.log` |
| mypy, whole repo | 46 errors in 18 files (Spec 04: 46, baseline 52) | `gate-mypy.log` |
| mypy `--strict repositories` | no issues in 5 files | `gate-mypy-repositories-strict.log` |
| bandit medium+ per changed file | `journey_data_server.py` B608 ×9 → 0; no changed file worse | `gate-bandit.json.log`, `gate-static-compare.log` |
| Demo pipeline (servers in demo mode) | 8 step metrics, 50 events, 4 critical steps, report written | `gate-demo-pipeline.log` |
| Ingest probe | 4 posts to 8005, 0 × 404, file flagged | `gate-ingest-probe.log` |
| Mode mismatch (realtime CLI, demo servers) | `ModeMismatch` raised; no metrics collected | `gate-mode-mismatch.log` |
| Ports after stop | 8001–8005 all free | `gate-results.txt` |
| `git diff --check` | clean (0 bytes) | `gate-diff-check.log` |
| Tracked `events.parquet` | unchanged | `gate-results.txt` |

The B608 finding in `repositories/queries.py` (`realtime_source` union of two module constants) carries
`# nosec B608 - fixed module constants only`. The `step_metrics_sql` template already had a `nosec` with the same
reason. Every value is a bound parameter.

## Acceptance criteria (requirements §5)
1. **Demo health works without PostgreSQL:** met. Tests use an engine factory that fails if called; the gate's demo
   pipeline ran with both database URLs pointing at a dead port.
2. **Realtime never uses demo storage:** met. The realtime repository has no Parquet reference; isolation tests pass
   a Parquet path that must stay unread; mode mismatches fail closed (OD-33).
3. **Empty, invalid and database-failure cases:** met, for both implementations (`test_repositories.py`,
   `test_journey_data_service.py`).
4. **Parity:** met. Both implementations return identical results on the shared fixture.
5. **Regression:** met. Golden identical, only F-01 failures, ruff and mypy no worse, no changed file worse.

## Findings
| ID | Finding | Status / owner |
|---|---|---|
| F-01 | 11 obsolete tests in `test_supervisor.py` | Open: Spec 09, or delete |
| F-02 | `errors` has no reducer | Open: Spec 09 |
| F-03 | Step rates exceed 100 % | Open: Analytics Spec |
| F-04 | Collector/dashboard ports bound by their own launch commands | Open: Spec 11 |
| F-05 | Possible old `cji_live_…` key in Supabase `api_keys` | Open: owner |
| F-06 | Realtime `ingest_to_store` inserted columns `live_events` lacks; probe: 0 of 3 rows inserted (`UndefinedColumn journey_id`, then `InFailedSqlTransaction`) while reporting all written. | **Fixed:** writes go to `tracking_events` in one transaction, idempotent on `event_id`, true counts. |
| F-07 | Collector `write_events` uses per-row try inside one transaction; one bad row aborts the rest while counts say "accepted". | Open: Spec 07 |
| F-08 | Realtime step metrics applied `->>` to `metadata::text`; PostgreSQL rejected it, so realtime metrics always errored (confirmed by probe). | **Fixed:** `CAST(NULLIF((metadata::jsonb)->>'retry_count','') AS NUMERIC)`; covered by PostgreSQL tests. |
| F-09 | `tools/ingest_json.py` (dashboard upload) writes `tracking_events` with `if_exists="replace"` unless `append=True`: an upload replaces the whole table in the configured database, now the live Supabase. | Open: Spec 06; owner caution now |
| F-10 | Demo queries ignore `days_back`; realtime `query_events` ignores `minutes_back` (fixed 60 minutes). | Kept to preserve results (window arguments are now passed through); Analytics Spec |
| F-11 | `pgserver` is a test-only dependency installed in the baseline venv but not listed in `requirements.txt`. Without it (and without `CJI_TEST_DATABASE_URL`) the 22 PostgreSQL tests skip. | Open: decide in the CI/packaging Spec |

## Rollback
No commits exist; restore from the evidence files. Run from the repository root with servers stopped.
1. Tracked files: `git apply -R .kiro/specs/05-repositories/evidence/spec05-tracked.patch`, then
   `git apply .kiro/specs/05-repositories/evidence/pre-spec05-tracked.patch` (the patch is against `HEAD`; the
   second step restores the Spec 04 state).
2. Untracked files changed by this Spec: copy `evidence/pre-spec05-untracked/domain/runs.py`,
   `.../tests/test_p0_security.py` and `.../tests/test_contracts.py` over the files in `cji_agent/`. These were
   rebuilt by reversing the edits in `scripts/apply_spec05.py`; `runs.py` and `test_contracts.py` match the
   Spec 03 copies byte for byte.
3. New files: delete `cji_agent/repositories/`, `cji_agent/tests/test_repositories.py` and
   `cji_agent/tests/test_journey_data_service.py` (copies in `evidence/spec05-new-files/`).
4. Test dependency: `uv pip uninstall --python C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe pgserver`
   (fasteners and psutil were installed with it).
5. Verify: golden snapshot and full suite should match Spec 04 (344/355, F-01 only).
