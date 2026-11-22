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

from cji.repositories import (
    PostgresEventRepository,
    RepositoryError,
    use_repository,
)
from cji.settings import make_test_settings, override_settings
from tests.test_repositories import (
    EXPECTED_FUNNEL,
    EXPECTED_METRICS,
    STEPS,
    fixture_frame,
)

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src" / "cji"                       # the package sources (Spec 11)
JOURNEY_CONFIG = {"name": "user_onboarding", "steps": STEPS}


def run(value):
    return asyncio.run(value) if inspect.isawaitable(value) else value


class FakeRepo:
    mode = "realtime"
    data_source = "live_events"

    def health(self):
        pass

    def window_fields(self, window):
        return None, 60

    def step_metrics(self, j_id, window, **kw):
        return EXPECTED_METRICS

    def funnel(self, j_id, steps, window, **kw):
        return EXPECTED_FUNNEL

    def events(self, j_id, limit=100, step_id=None, event_type=None, **kw):
        return [{"event_id": f"evt-{i}", "user_id": f"u{i}", "session_id": "s1", "journey_id": j_id, "step_id": step_id or "landing_page", "event_type": event_type or "page_view", "timestamp": "2026-04-22T14:32:00Z", "duration_ms": 1000, "url": "", "metadata": "{}"} for i in range(limit)]

    def live_snapshot(self, minutes):
        from cji.repositories.base import LiveSnapshot
        return LiveSnapshot(steps=[{"step_id": "landing_page", "event_count": 5}], total_events=5, snapshot_at="2026-04-22T14:32:00Z")

    def append_events(self, records):
        from cji.repositories.base import WriteResult
        return WriteResult(len(records), 0, "postgresql://tracking_events")

    def close(self):
        pass


@pytest.fixture
def j(monkeypatch):
    from cji.mcp_servers import journey_data_server as module

    monkeypatch.setattr(module, "JOURNEY_CONFIG", JOURNEY_CONFIG)
    return module


@pytest.fixture
def repo():
    r = FakeRepo()
    with use_repository(r):
        yield r


def test_service_has_no_mode_branches():
    source = (SRC / "mcp_servers" / "journey_data_server.py").read_text(encoding="utf-8")
    names = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    assert "CJI_MODE" not in names
    assert not re.search(r"""==\s*["'](demo|realtime)["']""", source)
    tree = ast.parse(source)
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"duckdb", "sqlalchemy", "pandas"}       # storage lives in repositories/
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}
    assert not defined & {"get_from_clause", "execute_query", "execute_demo_query", "get_pg_engine", "get_demo_conn"}


def test_system_info_shape(j, repo):
    res = run(j.get_system_info())
    assert set(res) == {"mode", "data_source", "journey_id", "journey_steps", "status"}
    assert (res["status"], res["mode"], res["data_source"]) == ("ok", "realtime", "live_events")


def test_system_info_realtime_unreachable(j):
    with use_repository(PostgresEventRepository("postgresql://cji:pw-42-secret@127.0.0.1:1/cji")):
        res = run(j.get_system_info())
    assert res["status"] == "error" and "pw-42-secret" not in res["error"]


def test_step_metrics_shape(j, repo):
    res = run(j.get_step_metrics(minutes_back=60))
    assert res == {"journey_id": "user_onboarding", "window_days": None, "window_minutes": 60,
                   "step_metrics": EXPECTED_METRICS, "total_steps": 3}


def test_funnel_shape(j, repo):
    res = run(j.get_funnel_dropoff())
    assert res == {"journey_id": "user_onboarding", "funnel": EXPECTED_FUNNEL, "overall_completion_pct": 25.0}


def test_query_events_shape(j, repo):
    res = run(j.query_events(limit=3, step_id="landing_page"))
    assert set(res) == {"events", "count", "step_id_filter", "event_type_filter"}
    assert res["count"] == 3 and res["step_id_filter"] == "landing_page" and res["event_type_filter"] is None


class EmptyRepo(FakeRepo):
    def step_metrics(self, j_id, window, **kw): return []
    def funnel(self, j_id, steps, window, **kw): return []
    def events(self, j_id, limit=100, step_id=None, event_type=None, **kw): return []


def test_empty_store_shapes(j):
    with use_repository(EmptyRepo()):
        assert run(j.get_step_metrics())["step_metrics"] == []
        assert run(j.get_funnel_dropoff()) == {"journey_id": "user_onboarding", "funnel": [],
                                               "overall_completion_pct": 100.0}
        assert run(j.query_events(limit=0))["count"] == 0


@pytest.mark.parametrize("call, error_keys", [
    (lambda j: j.query_events(limit=0), {"error", "events", "count"}),
    (lambda j: j.query_events(limit=1001), {"error", "events", "count"}),
    (lambda j: j.query_events(step_id="s" * 129), {"error", "events", "count"}),
    (lambda j: j.get_step_metrics(days_back=-1), {"error", "step_metrics", "total_steps"}),
    (lambda j: j.get_step_metrics(minutes_back=43201), {"error", "step_metrics", "total_steps"}),
    (lambda j: j.get_funnel_dropoff(days_back=99999), {"error", "funnel"}),
    (lambda j: j.get_live_snapshot(minutes=0), {"error"}),
])
def test_invalid_arguments_are_rejected_before_any_query(j, repo, monkeypatch, call, error_keys):
    def no_query(*args, **kwargs):
        raise AssertionError("repository called with invalid arguments")

    for name in ("step_metrics", "funnel", "events", "live_snapshot"):
        monkeypatch.setattr(repo, name, no_query)
    res = run(call(j))
    assert set(res) == error_keys and "must be" in res["error"]


def test_live_snapshot_returns_snapshot(j, repo):
    res = run(j.get_live_snapshot(minutes=15))
    assert res["window_mins"] == 15 and res["total_events"] == 5 and "steps" in res


class FailingRepo(FakeRepo):
    def step_metrics(self, j_id, window, **kw):
        raise RepositoryError("step_metrics", "connection lost")
    def funnel(self, j_id, steps, window, **kw):
        raise RepositoryError("funnel", "connection lost")
    def events(self, j_id, limit=100, step_id=None, event_type=None, **kw):
        raise RepositoryError("events", "connection lost")


def test_storage_failure_keeps_error_shapes(j):
    with use_repository(FailingRepo()):
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


def test_ingest_writes_through_the_repository(tmp_path):
    from cji.mcp_servers import ingestion_intelligence_server as ing

    path, mapping = _csv(tmp_path)
    with override_settings(make_test_settings(tmp_path, CJI_MODE="realtime", DATABASE_URL="postgresql://u@127.0.0.1:1/x")), use_repository(FakeRepo()):
        first = ing.ingest_to_store(str(path), mapping)
    assert first["status"] == "success" and first["records_written"] == 3
    assert first["destination"] == "postgresql://tracking_events"


def test_ingest_reports_storage_failures(tmp_path):
    from cji.mcp_servers import ingestion_intelligence_server as ing

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


def test_data_worker_sends_window_arguments(monkeypatch):
    import cji.agents.workers as w

    calls = []
    _fake_mcp(monkeypatch, w, {"get_system_info": {"status": "ok", "mode": "realtime"}}, calls)
    run(w.data_worker({"mode": "realtime", "analysis_window_days": 7, "analysis_window_mins": 15}))
    sent = dict(calls)
    assert sent["get_step_metrics"] == {"days_back": 7, "minutes_back": 15}
    assert sent["get_funnel_dropoff"] == {"days_back": 7, "minutes_back": 15}
    source = inspect.getsource(w.data_worker)
    assert 'if mode == "demo"' not in source
