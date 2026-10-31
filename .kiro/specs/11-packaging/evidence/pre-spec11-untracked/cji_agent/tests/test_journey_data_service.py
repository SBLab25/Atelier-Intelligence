"""
Spec 05 — journey-data service, ingestion writes and the data worker use the repository.
Offline: demo repositories on temporary Parquet files; realtime only with a fake engine.
"""
import ast
import asyncio
import contextlib
import inspect
import re
from pathlib import Path

import pandas as pd
import pytest

from repositories import (
    DuckDbParquetRepository,
    PostgresEventRepository,
    use_repository,
)
from settings import make_test_settings, override_settings
from tests.test_repositories import (
    EXPECTED_FUNNEL,
    EXPECTED_METRICS,
    STEPS,
    fixture_frame,
    load_parquet,
)

APP_ROOT = Path(__file__).resolve().parent.parent
JOURNEY_CONFIG = {"name": "user_onboarding", "steps": STEPS}


def run(value):
    return asyncio.run(value) if inspect.isawaitable(value) else value


@pytest.fixture
def j(monkeypatch):
    from mcp_servers import journey_data_server as module

    monkeypatch.setattr(module, "JOURNEY_CONFIG", JOURNEY_CONFIG)
    return module


@pytest.fixture
def demo(tmp_path):
    repo = DuckDbParquetRepository(load_parquet(tmp_path / "events.parquet", fixture_frame()))
    with use_repository(repo):
        yield repo
    repo.close()


def test_service_has_no_mode_branches():
    source = (APP_ROOT / "mcp_servers" / "journey_data_server.py").read_text(encoding="utf-8")
    names = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    assert "CJI_MODE" not in names          # the demo reply text still mentions it, as before
    assert not re.search(r"""==\s*["'](demo|realtime)["']""", source)
    tree = ast.parse(source)
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"duckdb", "sqlalchemy", "pandas"}       # storage lives in repositories/
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    assert not defined & {"get_from_clause", "execute_query", "execute_demo_query", "get_pg_engine", "get_demo_conn"}


def test_system_info_shape(j, demo):
    res = run(j.get_system_info())
    assert set(res) == {"mode", "data_source", "duckdb_path", "journey_id", "journey_steps", "status"}
    assert (res["status"], res["mode"], res["data_source"]) == ("ok", "demo", "parquet")


def test_system_info_demo_missing_parquet(j, tmp_path):
    with use_repository(DuckDbParquetRepository(tmp_path / "missing.parquet")):
        res = run(j.get_system_info())
    assert res == {"status": "error", "error": "events.parquet not found — run --generate-data"}


def test_system_info_realtime_unreachable(j):
    with use_repository(PostgresEventRepository("postgresql://cji:pw-42-secret@127.0.0.1:1/cji")):
        res = run(j.get_system_info())
    assert res["status"] == "error" and "pw-42-secret" not in res["error"]


def test_step_metrics_shape(j, demo):
    res = run(j.get_step_metrics(days_back=30))
    assert res == {"journey_id": "user_onboarding", "window_days": 30, "window_minutes": None,
                   "step_metrics": EXPECTED_METRICS, "total_steps": 3}


def test_funnel_shape(j, demo):
    res = run(j.get_funnel_dropoff())
    assert res == {"journey_id": "user_onboarding", "funnel": EXPECTED_FUNNEL, "overall_completion_pct": 25.0}


def test_query_events_shape(j, demo):
    res = run(j.query_events(limit=3, step_id="landing_page"))
    assert set(res) == {"events", "count", "step_id_filter", "event_type_filter"}
    assert res["count"] == 3 and res["step_id_filter"] == "landing_page" and res["event_type_filter"] is None


def test_empty_store_shapes(j, tmp_path):
    with use_repository(DuckDbParquetRepository(load_parquet(tmp_path / "e.parquet", fixture_frame([])))):
        assert run(j.get_step_metrics())["step_metrics"] == []
        assert run(j.get_funnel_dropoff()) == {"journey_id": "user_onboarding", "funnel": [],
                                               "overall_completion_pct": 100.0}
        assert run(j.query_events())["count"] == 0


@pytest.mark.parametrize("call, error_keys", [
    (lambda j: j.query_events(limit=0), {"error", "events", "count"}),
    (lambda j: j.query_events(limit=1001), {"error", "events", "count"}),
    (lambda j: j.query_events(step_id="s" * 129), {"error", "events", "count"}),
    (lambda j: j.get_step_metrics(days_back=-1), {"error", "step_metrics", "total_steps"}),
    (lambda j: j.get_step_metrics(minutes_back=43201), {"error", "step_metrics", "total_steps"}),
    (lambda j: j.get_funnel_dropoff(days_back=99999), {"error", "funnel"}),
    (lambda j: j.get_live_snapshot(minutes=0), {"error"}),
])
def test_invalid_arguments_are_rejected_before_any_query(j, demo, monkeypatch, call, error_keys):
    def no_query(*args, **kwargs):
        raise AssertionError("repository called with invalid arguments")

    for name in ("step_metrics", "funnel", "events", "live_snapshot"):
        monkeypatch.setattr(demo, name, no_query)
    res = run(call(j))
    assert set(res) == error_keys and "must be" in res["error"]


def test_live_snapshot_in_demo_keeps_its_message(j, demo):
    assert run(j.get_live_snapshot()) == {
        "error": "get_live_snapshot is only available in realtime mode",
        "mode": "demo",
        "message": "Switch to CJI_MODE=realtime to use this tool",
    }


def test_storage_failure_keeps_error_shapes(j, tmp_path):
    with use_repository(DuckDbParquetRepository(tmp_path / "missing.parquet")):
        assert set(run(j.get_step_metrics())) == {"error", "step_metrics", "total_steps"}
        assert set(run(j.get_funnel_dropoff())) == {"error", "funnel"}
        assert set(run(j.query_events())) == {"error", "events", "count"}


# ── Ingestion writes ──────────────────────────────────────────────────────────

def _csv(tmp_path):
    path = tmp_path / "upload.csv"
    pd.DataFrame({
        "event_id": ["imp-00000001", "imp-00000002", "imp-00000003"],
        "event_name": ["page_view", "click", "abandon"],
        "user": ["u1", "u2", "u3"],
        "ts": ["2026-01-01T00:00:00Z"] * 3,
        "step": ["landing_page"] * 3,
    }).to_csv(path, index=False)
    return path, {"field_mapping": {"event_name": "event_type", "user": "user_id", "ts": "timestamp", "step": "step_id"}}


def test_ingest_writes_through_the_repository_idempotently(tmp_path):
    from mcp_servers import ingestion_intelligence_server as ing

    path, mapping = _csv(tmp_path)
    target = tmp_path / "store" / "events.parquet"
    with override_settings(make_test_settings(tmp_path)), use_repository(DuckDbParquetRepository(target)):
        first = ing.ingest_to_store(str(path), mapping, mode="demo")
        second = ing.ingest_to_store(str(path), mapping, mode="demo")
    assert first["status"] == "success" and first["records_written"] == 3 and first["records_duplicate"] == 0
    assert second["records_written"] == 0 and second["records_duplicate"] == 3
    assert first["destination"] == str(target)
    assert len(pd.read_parquet(target)) == 3


def test_ingest_refuses_a_different_mode(tmp_path):
    from mcp_servers import ingestion_intelligence_server as ing

    path, mapping = _csv(tmp_path)
    target = tmp_path / "events.parquet"
    with override_settings(make_test_settings(tmp_path)), use_repository(DuckDbParquetRepository(target)):
        res = ing.ingest_to_store(str(path), mapping, mode="realtime")
    assert res["status"] == "error" and "configured for demo" in res["error"] and res["records_written"] == 0
    assert not target.exists()


def test_ingest_reports_storage_failures(tmp_path):
    from mcp_servers import ingestion_intelligence_server as ing

    path, mapping = _csv(tmp_path)
    with override_settings(make_test_settings(tmp_path, CJI_MODE="realtime", DATABASE_URL="postgresql://u@127.0.0.1:1/x")), \
         use_repository(PostgresEventRepository("postgresql://cji:pw-77@127.0.0.1:1/cji")):
        res = ing.ingest_to_store(str(path), mapping, mode="realtime")
    assert res["status"] == "error" and res["records_written"] == 0 and "pw-77" not in res["error"]


# ── Data worker ───────────────────────────────────────────────────────────────

def _fake_mcp(monkeypatch, module, responses, calls):
    @contextlib.asynccontextmanager
    async def fake_session(name):
        yield object()

    async def fake_call_tool(session, tool, arguments=None):
        calls.append((tool, dict(arguments or {})))
        return responses.get(tool, {})

    monkeypatch.setattr(module, "mcp_session", fake_session)
    monkeypatch.setattr(module, "call_tool", fake_call_tool)


def test_data_worker_refuses_a_server_in_another_mode(monkeypatch):
    import agents.workers as w

    calls = []
    _fake_mcp(monkeypatch, w, {"get_system_info": {"status": "ok", "mode": "demo"}}, calls)
    out = run(w.data_worker({"mode": "realtime"}))
    assert out["event_summary"] == {} and out["worker_statuses"][0]["status"] == "error"
    assert "demo" in out["errors"][0]["error"] and "realtime" in out["errors"][0]["error"]
    assert [c[0] for c in calls] == ["get_system_info"]


def test_data_worker_sends_both_window_arguments(monkeypatch):
    import agents.workers as w

    calls = []
    _fake_mcp(monkeypatch, w, {"get_system_info": {"status": "ok", "mode": "demo"}}, calls)
    run(w.data_worker({"mode": "demo", "analysis_window_days": 7, "analysis_window_mins": 15}))
    sent = dict(calls)
    assert sent["get_step_metrics"] == {"days_back": 7, "minutes_back": 15}
    assert sent["get_funnel_dropoff"] == {"days_back": 7, "minutes_back": 15}
    source = inspect.getsource(w.data_worker)
    assert 'if mode == "demo"' not in source
