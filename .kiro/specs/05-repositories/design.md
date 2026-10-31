# Spec 05 — Repository and Data-Access Isolation: Design

## 1. Package layout

```text
cji_agent/repositories/
  __init__.py        event_repository(settings) factory; use_repository() for tests
  base.py            EventRepository protocol, TimeWindow, WriteResult, LiveSnapshot, RepositoryError, normalise helpers
  queries.py         the shared SQL fragments (one definition per query; dialect differences are explicit parameters)
  duckdb_parquet.py  DuckDbParquetRepository
  postgres.py        PostgresEventRepository
```

Imports: stdlib, pandas, duckdb, SQLAlchemy, `domain/`, `settings/`. No FastMCP, no workers.

## 2. Interface

```python
class EventRepository(Protocol):
    mode: Mode                    # "demo" | "realtime"
    data_source: str              # "parquet" | "live_events"   (existing get_system_info values)

    def health(self) -> None                                        # raises RepositoryError when not ready
    def step_metrics(self, journey_id: str, window: TimeWindow) -> list[StepMetrics]
    def funnel(self, journey_id: str, steps: Sequence[str], window: TimeWindow) -> list[FunnelStep]
    def events(self, journey_id: str, *, limit: int, step_id: str | None,
               event_type: str | None) -> list[dict[str, Any]]
    def live_snapshot(self, minutes: int) -> LiveSnapshot          # demo: raises NotSupported
    def append_events(self, records: Sequence[EventRecord]) -> WriteResult
```

- `TimeWindow(days_back, minutes_back)`: each implementation applies its existing semantics (demo: none;
  realtime: `minutes_back or 60`). Services pass both values, so they need no mode check.
- `WriteResult(written: int, duplicates: int, destination: str)`.
- `RepositoryError(operation, message)`: the message never contains a URL or password (the SQLAlchemy URL is rendered
  with `hide_password=True`, and driver messages are stripped of connection strings).
- `NotSupported(RepositoryError)` for the demo live snapshot. The service maps it to today's demo dict
  (`{"error": "get_live_snapshot is only available in realtime mode", "mode": "demo", "message": …}`).

## 3. Implementations

| Operation | DuckDB / Parquet (demo) | PostgreSQL (realtime) |
|---|---|---|
| Connection | one in-memory DuckDB connection per repository, `PRAGMA threads=1`, temp view over the escaped Parquet path (unchanged) | engine created lazily from `Settings.database`; `pool_pre_ping=True` (unchanged) |
| `health` | Parquet exists → `SELECT 1` on the view; never touches an engine | `SELECT 1`; then `to_regclass('public.tracking_events')` and `…live_events` both non-null |
| Source | `events` view | `get_from_clause` logic moved here unchanged: `tracking_events UNION ALL live_events`, or one table for the two dashboard labels |
| `step_metrics` | existing SQL | same SQL text from `queries.py`; retry expression `CAST(NULLIF((metadata::jsonb)->>'retry_count', '') AS NUMERIC)` evaluated only for `event_type = 'error'` rows (fixes the suspected `text ->>` failure); window `NOW() - (:window * INTERVAL '1 minute')` |
| `funnel` | `list_position(?, step_id)` | `array_position(CAST(:steps AS TEXT[]), …)` |
| `events` | existing filters, `ORDER BY timestamp DESC LIMIT ?` | same; 60-minute window (existing) |
| `live_snapshot` | `NotSupported` | existing query on `live_events` |
| Result rows | `fillna(0.0)`, timestamps as `str` (unchanged) | same, then counts → `int`, rates → `float` (`Decimal` removed) |
| `append_events` | dedupe batch by `event_id`; drop rows already in the file; write `<name>.tmp-<pid>` then `os.replace` (atomic on the same volume); `destination` = Parquet path (unchanged) | one `engine.begin()` transaction; per record `INSERT INTO tracking_events (…) SELECT … WHERE NOT EXISTS (SELECT 1 FROM tracking_events WHERE event_id = :event_id)`; `rowcount` gives written vs duplicates; any error → rollback → `RepositoryError`; missing table → actionable error naming `tracking_events` |

`queries.py` holds each query once, with explicit dialect slots (placeholder style, JSON expression, list
position, window clause). The DuckDB and PostgreSQL texts are rendered from it and pinned by tests, so the two
copies cannot drift.

## 4. Selection and services

```python
# repositories/__init__.py
def event_repository(settings: Settings) -> EventRepository:
    return DuckDbParquetRepository(settings.storage.events_parquet) if settings.app.mode == "demo" \
        else PostgresEventRepository(settings.database)          # ConfigError if no database URL

_current: EventRepository | None        # created on first use; use_repository(repo) context manager for tests
```

`journey_data_server` tools become: validate arguments (RP-10) → `repo()` → call → shape. `get_system_info` keeps
its keys (`mode`, `data_source`, `duckdb_path`, `journey_id`, `journey_steps`, `status`) and the demo missing-file
message (`events.parquet not found — run --generate-data`). `get_step_metrics` keeps `window_days`/`window_minutes`
as today (demo: `days_back`, `None`; realtime: `None`, effective minutes). The `overall_completion_pct` arithmetic
moves into one helper used by both modes.

`ingest_to_store`: `apply_mapping` unchanged, then `repo().append_events(records)`; `records_written = written`,
new additive key `records_duplicate`; a mode argument different from the server's mode returns
`{"status": "error", "error": "server is configured for <mode> …"}` (OD-33). Mapping-registry save unchanged.

Workers: `data_worker` sends `{"days_back": days, "minutes_back": mins}` to both metric tools. After
`get_system_info` it compares `sys_info["mode"]` with `state["mode"]`; on mismatch it returns the existing error
shape with `errors=[workflow_error("data_worker", "journey-data server runs in <x> mode; this run is <y>")]` and no
metrics. `ingestion_worker` is unchanged apart from reading `records_duplicate` into its log line.

## 5. Tests

| File | Content |
|---|---|
| `tests/repositories/conftest.py` | Fixture events (8 steps, timestamps within the last 10 minutes, known counts); `demo_repo` (Parquet in `tmp_path`); `pg_url` (pgserver on a temp dir, session scope; or `CJI_TEST_DATABASE_URL`, loopback only); `pg_repo` (tables created by the collector DDL and by pandas `to_sql`, as production does) |
| `test_contract.py` | Parametrised over `demo_repo` and `pg_repo`: health; step metrics, funnel and events against hand-computed expected values; filters, limit, order; injection strings; empty store; idempotent append (twice → second call writes 0); batch with one invalid record writes nothing |
| `test_parity.py` | Same fixture into both → `step_metrics`, `funnel`, `events` equal after normalisation (timestamps compared as instants) |
| `test_duckdb_parquet.py` | Missing file, corrupt file, never builds an engine (factory that fails), atomic write (failure before `os.replace` leaves the old file intact), `NotSupported` live snapshot |
| `test_postgres.py` | Unreachable database (dead port) → `RepositoryError` without credentials; missing tables → health error naming them; `Decimal` → `float`; never opens the Parquet path (a path that raises if touched); live snapshot; rendered SQL contains no values |
| `tests/test_journey_data_service.py` | Tool outputs keep their keys and shapes for both repositories (injected); argument validation; no `CJI_MODE ==` branches (AST); demo health with a failing engine factory; `ingest_to_store` mode mismatch and write counts |
| Updated | `test_p0_security.py` R-02/R-04 and `test_contracts.py` journey tests switch from patching module globals (`CJI_MODE`, `get_pg_engine`, `pd.read_sql`) to injecting repositories; each keeps its original assertion |
| Workers | `data_worker` mode mismatch → recorded error, no metrics; both window arguments sent |

The PostgreSQL tests are skipped with a stated reason **only** if neither pgserver nor `CJI_TEST_DATABASE_URL` is
available. The gate requires them to run.

## 6. Risks

| Risk | Mitigation |
|---|---|
| pgserver does not start on this machine | Fallback to Docker Desktop via `CJI_TEST_DATABASE_URL`; otherwise stop and ask before claiming parity |
| Fixing the realtime SQL changes realtime numbers | There are no trusted realtime numbers today (suspected failure). Parity with demo defines the expected values. |
| Moving to `tracking_events` (OD-29) surprises anyone reading `live_events` for imports | Nothing reads imports from `live_events` separately; the realtime read model unions both tables |
| Updating Spec 02/03 tests weakens them | Each keeps its assertion; only the seam changes; reviewed in T1 |
| Golden snapshot drift | Demo SQL text is unchanged; gate compares byte-for-byte |

## 7. Rollback

`evidence/pre-spec05-tracked.patch` before T1; `evidence/spec05-tracked.patch` and new-file copies after the gate.
Reverting to Spec 04 needs the owner's approval (rewrites the working tree). Removing pgserver from the venv:
`uv pip uninstall pgserver`.
