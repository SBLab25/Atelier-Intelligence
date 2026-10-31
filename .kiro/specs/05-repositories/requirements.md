# Spec 05 — Repository and Data-Access Isolation: Requirements

**Source:** `kiro_upgrade_prompts.md` Prompt 4. **Findings addressed:** `refactoring.md` R-02 (repository abstraction;
demo health without PostgreSQL), the data-access part of R-04 (bound values), and the ingestion-write part of R-09.
**Branch:** `phase-02-security` (no commits; patch files are the rollback points, as in Specs 02–04).
**Status:** written 2026-10-28; OD-29 to OD-33 approved with defaults; implemented and gated 2026-10-28 (see tasks.md).

## 1. Current state (surveyed after Spec 04)

| Concern | Today (`mcp_servers/journey_data_server.py` unless stated) | Problem |
|---|---|---|
| Implementation choice | `if CJI_MODE == "demo"` inside 5 of 6 tools; module globals `_demo_conn`, `_pg_engine` | Branching repeated per query; tests patch module globals |
| Health | `get_system_info`: demo checks the Parquet file and DuckDB; realtime runs `SELECT 1` | Demo is already PostgreSQL-free (Spec 02, R-02); realtime does not check that the tables it reads exist |
| Step metrics / funnel / events | Two near-identical SQL texts per tool (DuckDB `?`, PostgreSQL `:name`), plus a string rewrite of the JSON expression | Two copies of each query; the rewrite is fragile |
| Realtime source | `get_from_clause()`: `tracking_events UNION ALL live_events`, metadata cast to `text`; two journey labels from the dashboard select one table | The retry expression `metadata->>'retry_count'` is applied to the `text` column. On PostgreSQL that operator needs `json`/`jsonb`, so realtime step metrics are **suspected to always fail**. Never run against a real database (confirm in T1). |
| Numeric types | Demo rows: `int` counts, `float` rates. PostgreSQL `ROUND(numeric)` returns `Decimal` through psycopg2 | Realtime result types are unverified |
| Windows | Demo ignores `days_back` (echoed only). Realtime: `minutes_back` or 60; `query_events` always 60 minutes | Semantics to preserve, not fix (F-10) |
| Live snapshot | Realtime only, `live_events` only, all journeys; demo returns a fixed error dict | Keep |
| Ingestion writes (`ingestion_intelligence_server.ingest_to_store`) | Demo: read the whole Parquet, concatenate, drop duplicates, rewrite the file in place. Realtime: per-record `INSERT INTO live_events (… journey_id, duration_ms …)` inside **one** transaction, each wrapped in `try/except` | `live_events` has no `journey_id` or `duration_ms` columns. The first insert fails and PostgreSQL aborts the transaction, so every later insert fails too. The tool still reports `records_written = len(records)` (F-06). The demo rewrite is not atomic. |
| Callers | `agents/workers.py data_worker` chooses `days_back` or `minutes_back` by state mode; `agents/ingestion_worker.py` passes `mode` per call | The server's configured mode and the CLI's mode can differ silently; realtime analysis could read demo data |
| Out of scope but related | Collector `write_events` (same per-row-in-one-transaction pattern, F-07); `tools/ingest_json.py` `to_sql(..., if_exists="replace")` on `tracking_events` (F-09); dashboard SQL | Specs 07, 06, 14 |

## 2. Decisions (defaults; confirm or change before implementation)

| ID | Question | Default | Alternatives considered |
|---|---|---|---|
| OD-29 | Realtime target for file ingestion | **`tracking_events`**: its columns are exactly the stored `EventRecord` (pandas `to_sql` layout written by `ingest_json`), the realtime read model already requires it (`UNION ALL`), and it keeps `duration_ms` and `journey_id`. No DDL: a missing table is an actionable error. `destination` becomes `postgresql://tracking_events`. | `live_events` with `journey_id→journey_name` and `duration_ms` dropped: the table always exists where the collector ran, but imported durations are lost and file imports mix with browser events. |
| OD-30 | Idempotency key | `event_id`. Demo: existing rows win, duplicates inside a batch collapse to the first. PostgreSQL: `INSERT … SELECT … WHERE NOT EXISTS (… event_id = :event_id)`, because `tracking_events` has no unique constraint and the schema stays as it is. | Add a unique index: a schema change (excluded by the Prompt). |
| OD-31 | Transaction behaviour for writes | **All or nothing per batch.** PostgreSQL: one transaction; any failure rolls back everything and raises. Demo: write a temporary file next to the Parquet, then `os.replace`. Result: `written`, `duplicates`, `destination`. | Per-row best effort: what the code tries today, and it cannot work inside one PostgreSQL transaction. |
| OD-32 | PostgreSQL for tests | **`pgserver`** (PostgreSQL 16 in a pip wheel; a `cp312-win_amd64` wheel exists for 0.1.4) installed into the baseline venv as a test-only dependency, started on a temporary directory per test session. Fallback: `CJI_TEST_DATABASE_URL` pointing at a disposable local server, e.g. Docker Desktop (installed; daemon not running). The harness refuses any non-loopback URL, so tests can never reach Supabase. | Fake engines only: they cannot show whether the SQL runs. Live Supabase: never. |
| OD-33 | Mode mismatch between CLI and server | **Fail closed.** `data_worker` compares `get_system_info().mode` with the run's mode and records an error instead of analysing the wrong store. `ingest_to_store(mode=…)` that differs from the server's configured mode returns an error. | Warn and continue: realtime runs could silently analyse demo data. |

## 3. Requirements

| ID | Requirement | Intended behaviour change |
|---|---|---|
| RP-01 | An `EventRepository` interface SHALL cover health/readiness, step metrics, funnel drop-off, event queries/samples, live snapshot, and event writes. | — |
| RP-02 | Two implementations: `DuckDbParquetRepository` (demo; in-memory DuckDB over the configured Parquet) and `PostgresEventRepository` (realtime; SQLAlchemy engine on the configured database). | — |
| RP-03 | The implementation SHALL be chosen once, from `Settings.app.mode` (Spec 04), by one factory; tests inject a repository through the same seam. | — |
| RP-04 | Service functions (`journey_data_server` tools) SHALL contain no mode branching: they validate arguments, call the repository and shape the result. | — |
| RP-05 | Every value (journey, steps, filters, limits, windows, records) SHALL be a bound parameter. The only text composed into SQL is fixed, allow-listed fragments (realtime source selection; the Parquet path, escaped, as in Spec 02). | — |
| RP-06 | Result shapes and numeric semantics SHALL be preserved: the same keys, the demo golden snapshot byte-identical, realtime numbers normalised to the demo types (`int` counts, `float` rates). The existing windows, `fillna(0.0)` and ordering are kept. | Realtime numbers become plain `int`/`float` (not `Decimal`) |
| RP-07 | Realtime queries SHALL run on PostgreSQL as written. Any SQL that cannot (e.g. the suspected `text ->> 'retry_count'`) is corrected to compute the same value as the demo query. | Realtime step metrics work (if T1 confirms they fail today) |
| RP-08 | Writes: idempotent by `event_id` (OD-30), all or nothing per batch (OD-31), returning `written` and `duplicates`. `ingest_to_store` reports what was written. | Realtime ingestion writes to `tracking_events` and reports true counts (F-06 fixed) |
| RP-09 | Readiness: demo = Parquet present and readable; realtime = database reachable **and** `tracking_events` and `live_events` exist. Demo never builds a database engine; realtime never opens the Parquet file. | Realtime health reports missing tables |
| RP-10 | Arguments SHALL be validated before any query: `limit` 1–1000, `minutes`/`minutes_back` 0–43200, `days_back` 0–3650, filters ≤ 128 characters. Invalid input gives the tool's existing error shape with a clear message. | Out-of-range input is rejected instead of reaching the database |
| RP-11 | Storage failures SHALL surface as one `RepositoryError` type with the operation and a message that contains no credentials; services keep returning their existing error shapes. | — |
| RP-12 | Directly dependent workers SHALL stop branching on mode: `data_worker` sends both window arguments and checks the server's mode (OD-33); `ingestion_worker` relies on the server's configured repository. | Mismatched modes are reported |
| RP-13 | Tests: one contract suite run against both implementations, implementation-specific tests, and parity tests that load the same fixture into both and require equal results. They cover empty, invalid and database-failure cases. | — |

## 4. Non-goals

- Concurrency, connection pooling tuning, async drivers, batching performance (Prompt: do not optimise).
- Schema changes: no new tables, columns, indexes or constraints. The PostgreSQL test fixture creates tables
  exactly as production code does today (collector DDL for `live_events`/`api_keys`; pandas `to_sql` of
  `EventRecord` rows for `tracking_events`).
- Collector writes and response semantics (F-07) → Spec 07. `ingest_json`'s table replace (F-09) and the duplicate
  ingestion paths → Spec 06. Dashboard SQL → Spec 14.
- Changing window semantics (demo ignores `days_back`; realtime `query_events` fixed at 60 minutes): recorded as
  F-10, kept to preserve results.

## 5. Acceptance criteria (Prompt 4)

1. **Demo health works without PostgreSQL**: tests with an engine factory that fails if called, and the gate's demo
   smoke run with dead database URLs.
2. **Realtime never uses demo storage**: the realtime repository has no Parquet reference (tests pass a path that
   fails on access); the factory selects it only for `realtime`; mode mismatch is reported (OD-33).
3. **Empty, invalid and database-failure cases** are tested for both implementations: empty store, invalid
   arguments, injection strings, missing Parquet, corrupt Parquet, unreachable database, missing tables,
   failed write (rolled back).
4. Parity: identical results from both implementations on the shared fixture.
5. Regression: golden snapshot identical to Spec 04; full suite has no failures beyond F-01; mypy/ruff no worse
   on changed files; `repositories/` mypy `--strict` clean; demo pipeline and ingest probe match Spec 04.
