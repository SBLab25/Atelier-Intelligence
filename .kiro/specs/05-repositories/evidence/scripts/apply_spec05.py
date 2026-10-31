"""
Spec 05 patch script: journey-data service, ingestion writes and the data worker use the
event repository; Spec 02/03 tests move to the repository seam (assertions unchanged).
Every anchor must match the stated number of times before anything is written; files keep
their newline style and UTF-8.
"""
import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
EDITS: dict[str, list[tuple[str, str, int]]] = {}
REWRITES: dict[str, str] = {}
POST: dict[str, list[tuple[str, str]]] = {}


def edit(rel: str, old: str, new: str, count: int = 1) -> None:
    EDITS.setdefault(rel, []).append((old, new, count))


def drop_import_if_unused(rel: str, import_line: str, usage: str) -> None:
    POST.setdefault(rel, []).append((import_line, usage))


# ─────────────────────────────── journey_data_server.py ───────────────────────
REWRITES["mcp_servers/journey_data_server.py"] = '''"""
CJI MCP Server 1 — Journey Data
================================
Tools read journey events through the configured EventRepository (Spec 05). The
repository is chosen once from settings (demo: DuckDB over Parquet; realtime:
PostgreSQL); no tool branches on the mode. Arguments are validated before any query.
"""
import logging
from typing import Any

from fastmcp import FastMCP

from config import DUCKDB_PATH, JOURNEY_CONFIG
from repositories import EventRepository, NotSupported, RepositoryError, TimeWindow, get_repository
from settings import ConfigError

logger = logging.getLogger(__name__)

MAX_LIMIT = 1000
MAX_MINUTES = 43200          # 30 days, as the collector's /live/stats
MAX_DAYS = 3650
MAX_FILTER_LENGTH = 128
DEMO_SNAPSHOT_REPLY = {
    "error": "get_live_snapshot is only available in realtime mode",
    "mode": "demo",
    "message": "Switch to CJI_MODE=realtime to use this tool",
}


class InvalidArgument(ValueError):
    """A tool argument is out of range; reported in the tool's error shape."""


def _whole_number(name: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise InvalidArgument(f"{name} must be a whole number from {low} to {high}")
    return value


def _text_filter(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_FILTER_LENGTH:
        raise InvalidArgument(f"{name} must be text of at most {MAX_FILTER_LENGTH} characters")
    return value


def _window(days_back: Any, minutes_back: Any) -> TimeWindow:
    return TimeWindow(
        days_back=_whole_number("days_back", days_back, 0, MAX_DAYS),
        minutes_back=_whole_number("minutes_back", minutes_back, 0, MAX_MINUTES),
    )


def _repository() -> EventRepository:
    try:
        return get_repository()
    except ConfigError as exc:
        raise RepositoryError("configure", "; ".join(exc.problems)) from exc


def _overall_completion_pct(funnel: list[dict[str, Any]]) -> float:
    overall_pct = 0.0
    if funnel and funnel[0]["users"] > 0:
        overall_pct = round((funnel[0]["users"] - funnel[-1]["users"]) * 100.0 / funnel[0]["users"], 2)
    return 100.0 - overall_pct


# Initialise the FastMCP server
mcp = FastMCP("cji-journey-data")

@mcp.tool()
def test_dummy(val: int = 10) -> dict:
    return {"val": val, "worked": True}

@mcp.tool()
async def get_system_info() -> dict:
    """Returns mode, data source, and connection status (readiness of the configured store)."""
    try:
        repo = _repository()
        repo.health()
    except RepositoryError as e:
        return {"status": "error", "error": e.message}
    return {
        "mode": repo.mode,
        "data_source": repo.data_source,
        "duckdb_path": str(DUCKDB_PATH),
        "journey_id": JOURNEY_CONFIG["name"],
        "journey_steps": JOURNEY_CONFIG["steps"],
        "status": "ok"
    }

@mcp.tool()
def get_funnel_steps() -> dict:
    """Returns ordered list of journey step IDs."""
    return {
        "journey_id": JOURNEY_CONFIG["name"],
        "steps": JOURNEY_CONFIG["steps"],
        "step_count": len(JOURNEY_CONFIG["steps"])
    }

@mcp.tool()
async def get_step_metrics(days_back: int = 30, minutes_back: int = 0) -> dict:
    """Returns aggregated metrics per step."""
    journey_id = JOURNEY_CONFIG["name"]
    try:
        window = _window(days_back, minutes_back)
        repo = _repository()
        metrics = repo.step_metrics(journey_id, window)
    except (InvalidArgument, RepositoryError) as e:
        logger.error(f"Error querying step metrics: {e}")
        return {"error": str(e), "step_metrics": [], "total_steps": 0}
    window_days, window_minutes = repo.window_fields(window)
    return {
        "journey_id": journey_id,
        "window_days": window_days,
        "window_minutes": window_minutes,
        "step_metrics": metrics,
        "total_steps": len(metrics),
    }

@mcp.tool()
async def get_funnel_dropoff(days_back: int = 30, minutes_back: int = 0) -> dict:
    """Returns sequential funnel drop-off percentages."""
    journey_id = JOURNEY_CONFIG["name"]
    steps = list(JOURNEY_CONFIG["steps"])
    try:
        funnel = _repository().funnel(journey_id, steps, _window(days_back, minutes_back))
    except (InvalidArgument, RepositoryError) as e:
        logger.error(f"Funnel error: {e}")
        return {"error": str(e), "funnel": []}
    return {"journey_id": journey_id, "funnel": funnel, "overall_completion_pct": _overall_completion_pct(funnel)}

@mcp.tool()
async def query_events(limit: int = 100, step_id: str = None, event_type: str = None) -> dict:
    """Returns a sample of raw events with optional filters."""
    journey_id = JOURNEY_CONFIG["name"]
    try:
        events = _repository().events(
            journey_id,
            limit=_whole_number("limit", limit, 1, MAX_LIMIT),
            step_id=_text_filter("step_id", step_id),
            event_type=_text_filter("event_type", event_type),
        )
    except (InvalidArgument, RepositoryError) as e:
        return {"error": str(e), "events": [], "count": 0}
    return {"events": events, "count": len(events), "step_id_filter": step_id, "event_type_filter": event_type}


@mcp.tool()
async def get_live_snapshot(minutes: int = 15) -> dict:
    """Realtime mode only. Returns rolling event counts for the last N minutes."""
    try:
        minutes = _whole_number("minutes", minutes, 1, MAX_MINUTES)
        snapshot = _repository().live_snapshot(minutes)
    except NotSupported:
        return dict(DEMO_SNAPSHOT_REPLY)
    except (InvalidArgument, RepositoryError) as e:
        return {"error": str(e)}
    return {
        "window_mins": minutes,
        "steps": snapshot.steps,
        "total_events": snapshot.total_events,
        "snapshot_at": snapshot.snapshot_at,
    }

if __name__ == "__main__":
    from mcp_servers._serve import serve

    serve(mcp, "cji-journey-data")
'''

# ─────────────────────────────── ingestion server ─────────────────────────────
ING = "mcp_servers/ingestion_intelligence_server.py"
edit(ING, "from settings import ConfigError, get_settings\n",
     "from repositories import RepositoryError, get_repository\nfrom settings import ConfigError, get_settings\n")
edit(ING, '''    start_ms = datetime.now().timestamp() * 1000
    target_mode = mode if mode in ("demo", "realtime") else CJI_MODE
    log.info(f"ingest_to_store: mode={target_mode}, file={file_path}")
''', '''    start_ms = datetime.now().timestamp() * 1000
    # The store is chosen once from the server's settings (Spec 05); a request for the
    # other mode is refused instead of writing to the wrong store (OD-33).
    try:
        repo = get_repository()
    except ConfigError as exc:
        return {"status": "error", "error": "; ".join(exc.problems), "records_written": 0, "records_skipped": 0}
    if mode in ("demo", "realtime") and mode != repo.mode:
        return {
            "status":          "error",
            "error":           (f"this server is configured for {repo.mode} mode but the request asked for "
                                f"{mode}. Start the MCP servers with --mode {mode}, or run the analysis in "
                                f"{repo.mode} mode."),
            "records_written": 0,
            "records_skipped": 0,
        }
    log.info(f"ingest_to_store: mode={repo.mode}, file={file_path}")
''')
edit(ING, '''    records  = transform_result["_records_internal"]
    df_clean = pd.DataFrame(records)

    # Write to store
    destination = ""
    if target_mode == "demo":
        # Merge with existing Parquet or create new
        destination = str(EVENTS_PARQUET)
        if EVENTS_PARQUET.exists():
            existing = pd.read_parquet(EVENTS_PARQUET)
            df_merged = pd.concat([existing, df_clean], ignore_index=True)
            df_merged = df_merged.drop_duplicates(subset=["event_id"])
        else:
            df_merged = df_clean
        df_merged.to_parquet(EVENTS_PARQUET, index=False)

    else:
        # Realtime — write to Supabase live_events
        from sqlalchemy import create_engine, text
        destination = "supabase://live_events"
        url = get_settings().database.url_value()
        if not url:
            raise ConfigError([database_missing("Realtime ingestion")],
                              role="mcp:cji-ingestion-intelligence")
        engine = create_engine(url, pool_pre_ping=True)
        with engine.begin() as conn:
            for record in records:
                try:
                    conn.execute(
                        text("""
                            INSERT INTO live_events
                                (event_id, user_id, session_id, journey_id, step_id,
                                 event_type, timestamp, duration_ms, url, metadata)
                            VALUES
                                (:event_id, :user_id, :session_id, :journey_id, :step_id,
                                 :event_type, :timestamp, :duration_ms, :url, :metadata)
                            ON CONFLICT (event_id) DO NOTHING
                        """),
                        record,
                    )
                except Exception as e:
                    log.warning(f"Skipped record {record.get('event_id')}: {e}")
''', '''    records = transform_result["_records_internal"]

    # Write through the repository: one all-or-nothing batch, idempotent by event_id
    # (demo: atomic Parquet replace; realtime: tracking_events in one transaction).
    try:
        written = repo.append_events(records)
    except RepositoryError as exc:
        log.error(f"ingest_to_store failed, nothing written: {exc.message}")
        return {
            "status":          "error",
            "error":           exc.message,
            "records_written": 0,
            "records_skipped": transform_result["records_failed"],
            "records_coerced": transform_result["records_coerced"],
        }
    destination = written.destination
''')
edit(ING, '''    log.info(f"ingest_to_store complete: {len(records)} records → {destination} in {duration}ms")

    return {
        "status":          "success",
        "records_written": len(records),
        "records_skipped": transform_result["records_failed"],
''', '''    log.info(f"ingest_to_store complete: {written.written} written, {written.duplicates} already stored "
             f"→ {destination} in {duration}ms")

    return {
        "status":          "success",
        "records_written": written.written,
        "records_duplicate": written.duplicates,
        "records_skipped": transform_result["records_failed"],
''')
drop_import_if_unused(ING, "from settings.roles import database_missing\n", r"\bdatabase_missing\b")
drop_import_if_unused(ING, "    EVENTS_PARQUET,\n", r"\bEVENTS_PARQUET\b")
drop_import_if_unused(ING, "    CJI_MODE,\n", r"\bCJI_MODE\b")

# ─────────────────────────────── agents/workers.py ────────────────────────────
W = "agents/workers.py"
edit(W, '''logger = logging.getLogger("cji.workers")
''', '''logger = logging.getLogger("cji.workers")


class ModeMismatch(RuntimeError):
    """The journey-data server reads a different store than this run asked for (Spec 05, OD-33)."""
''')
edit(W, '''            # 2. Step metrics
            step_args = {"days_back": days} if mode == "demo" else {"minutes_back": mins}
            step_metrics = await call_tool(session, "get_step_metrics", step_args)

            # 3. Funnel drop-off
            funnel_args = {"days_back": days} if mode == "demo" else {"minutes_back": mins}
            funnel = await call_tool(session, "get_funnel_dropoff", funnel_args)
''', '''            # Never analyse a store other than the one this run asked for (Spec 05).
            server_mode = sys_info.get("mode")
            if server_mode and server_mode != mode:
                raise ModeMismatch(
                    f"journey-data server runs in {server_mode} mode; this run is {mode}. "
                    f"Restart the servers with: python run_servers.py --mode {mode}"
                )

            # The server's repository applies its own window semantics; send both values.
            window_args = {"days_back": days, "minutes_back": mins}

            # 2. Step metrics
            step_metrics = await call_tool(session, "get_step_metrics", window_args)

            # 3. Funnel drop-off
            funnel = await call_tool(session, "get_funnel_dropoff", window_args)
''')

# ─────────────────────────────── Spec 02/03 tests: new seam ───────────────────
P0 = "tests/test_p0_security.py"
edit(P0, '''def _no_postgres():
    raise AssertionError("PostgreSQL engine requested in demo mode")


def test_r02_demo_system_info_is_ok_without_postgres(monkeypatch):
    from mcp_servers import journey_data_server as j

    monkeypatch.setattr(j, "CJI_MODE", "demo")
    monkeypatch.setattr(j, "get_pg_engine", _no_postgres)
    res = run(j.get_system_info())
    assert res["status"] == "ok", res
    assert res["data_source"] == "parquet"


def test_r02_demo_system_info_reports_missing_parquet(monkeypatch, tmp_path):
    from mcp_servers import journey_data_server as j

    monkeypatch.setattr(j, "CJI_MODE", "demo")
    monkeypatch.setattr(j, "get_pg_engine", _no_postgres)
    monkeypatch.setattr(j, "EVENTS_PARQUET", tmp_path / "missing.parquet")
    res = run(j.get_system_info())
    assert res["status"] == "error"
    assert "events.parquet not found" in res["error"]
''', '''def _no_postgres(*args, **kwargs):
    raise AssertionError("PostgreSQL engine requested in demo mode")


def test_r02_demo_system_info_is_ok_without_postgres(monkeypatch):
    import sqlalchemy

    from mcp_servers import journey_data_server as j
    from repositories import event_repository, use_repository
    from settings import get_settings

    monkeypatch.setattr(sqlalchemy, "create_engine", _no_postgres)
    with use_repository(event_repository(get_settings())):        # demo, chosen from settings
        res = run(j.get_system_info())
    assert res["status"] == "ok", res
    assert res["data_source"] == "parquet"


def test_r02_demo_system_info_reports_missing_parquet(monkeypatch, tmp_path):
    import sqlalchemy

    from mcp_servers import journey_data_server as j
    from repositories import DuckDbParquetRepository, use_repository

    monkeypatch.setattr(sqlalchemy, "create_engine", _no_postgres)
    with use_repository(DuckDbParquetRepository(tmp_path / "missing.parquet")):
        res = run(j.get_system_info())
    assert res["status"] == "error"
    assert "events.parquet not found" in res["error"]
''')
edit(P0, '''    monkeypatch.setattr(j, "CJI_MODE", "realtime")
    monkeypatch.setattr(j, "JOURNEY_CONFIG", {"name": "evil_journey'", "steps": ["evil_step_a'", "b"]})
    monkeypatch.setattr(j, "get_pg_engine", lambda: FakeEngine())
    monkeypatch.setattr(j.pd, "read_sql", fake_read_sql)

    run(j.get_step_metrics(minutes_back=7))
    run(j.get_funnel_dropoff(minutes_back=7))
    run(j.query_events(limit=5, step_id="evil_step_x'", event_type="evil_type'"))
    run(j.get_live_snapshot(minutes=9))
''', '''    from repositories import PostgresEventRepository, use_repository
    from repositories import postgres as pg_module

    realtime = PostgresEventRepository("postgresql://u@127.0.0.1:1/x", engine_factory=lambda *a, **k: FakeEngine())
    monkeypatch.setattr(j, "JOURNEY_CONFIG", {"name": "evil_journey'", "steps": ["evil_step_a'", "b"]})
    monkeypatch.setattr(pg_module.pd, "read_sql", fake_read_sql)

    with use_repository(realtime):
        run(j.get_step_metrics(minutes_back=7))
        run(j.get_funnel_dropoff(minutes_back=7))
        run(j.query_events(limit=5, step_id="evil_step_x'", event_type="evil_type'"))
        run(j.get_live_snapshot(minutes=9))
''')
CT = "tests/test_contracts.py"
edit(CT, '''    monkeypatch.setattr(j, "CJI_MODE", "demo")
    monkeypatch.setattr(j, "JOURNEY_CONFIG", {"name": "user_onboarding", "steps": JOURNEY_CONFIG["steps"]})
''', '''    # Demo is the configured mode in tests; the repository is chosen from settings (Spec 05).
    monkeypatch.setattr(j, "JOURNEY_CONFIG", {"name": "user_onboarding", "steps": JOURNEY_CONFIG["steps"]})
''')

# domain doc string for the realtime destination
edit("domain/runs.py", '    destination: str        # "data/events.parquet" or "supabase://live_events"',
     '    destination: str        # Parquet path (demo) or "postgresql://tracking_events" (realtime)')


def main() -> int:
    planned: dict[pathlib.Path, tuple[str, str]] = {}
    problems: list[str] = []
    for rel, new_text in REWRITES.items():
        path = APP / rel
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        planned[path] = (raw, new_text.replace("\n", nl))
    for rel, pairs in EDITS.items():
        path = APP / rel
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw
        for old, new, count in pairs:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            found = text.count(o)
            if found != count:
                problems.append(f"{rel}: anchor found {found}x (want {count}): {old[:80]!r}")
                continue
            text = text.replace(o, n)
        for import_line, usage in POST.get(rel, []):
            line = import_line.replace("\n", nl)
            rest = text.replace(line, "", 1)
            if text.count(line) == 1 and not re.search(usage, rest):
                text = rest
        planned[path] = (raw, text)
    if problems:
        print("NOT APPLIED:\n" + "\n".join(problems))
        return 1
    for path, (old, new) in planned.items():
        if old != new:
            path.write_bytes(new.encode("utf-8"))
            print(f"patched {path.relative_to(APP)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
