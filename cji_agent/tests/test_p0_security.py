"""
Regression tests for Spec 02 (P0 correctness and security).

Covers refactoring.md R-01..R-05 and baseline items U-4, U-5.
All tests run offline: no database, no network, no LLM.
"""
import asyncio
import contextlib
import importlib
import inspect
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
import pytest

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src" / "cji"                       # the package sources (Spec 11)


def run(value):
    """Await coroutines; pass plain values through."""
    return asyncio.run(value) if inspect.isawaitable(value) else value


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeResult:
    def fetchall(self):
        return []

    def fetchone(self):
        return None


class FakeConn:
    def __init__(self, log):
        self.log = log

    def execute(self, statement, params=None):
        self.log.append((str(statement), dict(params or {})))
        return FakeResult()


class FakeEngine:
    """Records every statement instead of talking to PostgreSQL."""

    def __init__(self):
        self.log = []

    @contextlib.contextmanager
    def begin(self):
        yield FakeConn(self.log)

    connect = begin

    def dispose(self):
        pass


@pytest.fixture
def collector_api():
    """Import the collector the way the documented command does (flat layout)."""
    return importlib.import_module("cji.collector.api")


# ═════════════════════════════════════════════════════════════════════════════
# U-5 — collector imports with the documented layout and declared driver
# ═════════════════════════════════════════════════════════════════════════════

def test_u5_collector_imports_with_flat_layout(collector_api):
    assert hasattr(collector_api, "app")


# ═════════════════════════════════════════════════════════════════════════════
# U-4 — VALID_WORKERS matches what route() and the graph can produce
# ═════════════════════════════════════════════════════════════════════════════

ROUTE_STATES = [
    {},
    {"ingestion_pending_files": [{"file_path": "x.csv"}]},
    {"event_summary": {"a": 1}},
    {"event_summary": {"a": 1}, "friction_scores": [{"s": 1}]},
    {"event_summary": {"a": 1}, "friction_scores": [{"s": 1}], "insights": [{"i": 1}]},
    {"event_summary": {"a": 1}, "friction_scores": [{"s": 1}], "insights": [{"i": 1}],
     "human_approved": True},
    {"event_summary": {"a": 1}, "friction_scores": [{"s": 1}], "insights": [{"i": 1}],
     "human_approved": True, "report_path": "r.html"},
    {"next_worker": "__end__"},
]


def test_u4_valid_workers_matches_graph_edges():
    from cji.agents.supervisor import VALID_WORKERS
    from cji.graph import build_graph

    ends = build_graph().branches["supervisor"]["route"].ends
    assert isinstance(VALID_WORKERS, frozenset)
    assert VALID_WORKERS == frozenset(ends.keys())


@pytest.mark.parametrize("state", ROUTE_STATES)
def test_u4_every_route_result_is_a_valid_worker(state):
    from cji.agents.supervisor import VALID_WORKERS, route

    assert route(state) in VALID_WORKERS


# ═════════════════════════════════════════════════════════════════════════════
# R-01 — ingestion worker uses the shared MCP client and never loops
# ═════════════════════════════════════════════════════════════════════════════

def test_r01_worker_source_has_no_endpoint_literals():
    src = (SRC / "agents" / "ingestion_worker.py").read_text(encoding="utf-8")
    for literal in ("localhost", "127.0.0.1", ":800", "import requests"):
        assert literal not in src, f"endpoint literal still present: {literal!r}"


def _fake_mcp(monkeypatch, module, tool_impl):
    calls = []

    @contextlib.asynccontextmanager
    async def fake_session(name):
        calls.append(("session", name))
        yield object()

    async def fake_call_tool(session, tool, arguments=None):
        calls.append(("tool", tool))
        return tool_impl(tool)

    monkeypatch.setattr(module, "mcp_session", fake_session, raising=False)
    monkeypatch.setattr(module, "call_tool", fake_call_tool, raising=False)
    return calls


def _ingest_state(tmp_path):
    src = tmp_path / "input.csv"
    src.write_text("a,b\n1,2\n", encoding="utf-8")
    return {
        "mode": "demo",
        "ingestion_pending_files": [{"file_path": str(src), "source_hint": ""}],
        "ingestion_results": [],
        "ingestion_pending_review": [],
        "worker_statuses": [],
        "errors": [],
    }


def test_r01_ingestion_uses_ingestion_service(monkeypatch, tmp_path):
    import cji.agents.ingestion_worker as iw

    def tool_impl(tool):
        if tool == "detect_schema":
            return {"confidence": 0.95, "detected_source": "ga4", "cached": False}
        return {"ingest_id": "i1", "records_written": 1, "records_skipped": 0,
                "destination": "parquet", "status": "success"}

    calls = _fake_mcp(monkeypatch, iw, tool_impl)
    result = run(iw.ingestion_worker(_ingest_state(tmp_path)))

    assert ("session", "cji-ingestion-intelligence") in calls
    assert [c[1] for c in calls if c[0] == "tool"] == ["detect_schema", "ingest_to_store"]
    assert len(result["ingestion_results"]) == 1
    assert result["ingestion_pending_files"] == []


def test_r01_failed_ingest_does_not_loop(monkeypatch, tmp_path):
    import cji.agents.ingestion_worker as iw
    from cji.agents.supervisor import route

    def tool_impl(tool):
        raise RuntimeError("ingestion server unavailable")

    _fake_mcp(monkeypatch, iw, tool_impl)
    state = _ingest_state(tmp_path)
    result = run(iw.ingestion_worker(state))

    assert len(result["errors"]) == 1
    assert result["ingestion_pending_files"] == []
    assert route({**state, **result}) != "ingestion_worker"


def test_r01_low_confidence_is_flagged_not_looped(monkeypatch, tmp_path):
    import cji.agents.ingestion_worker as iw
    from cji.agents.supervisor import route

    _fake_mcp(monkeypatch, iw, lambda tool: {"confidence": 0.1, "detected_source": "x"})
    state = _ingest_state(tmp_path)
    result = run(iw.ingestion_worker(state))

    assert len(result["ingestion_pending_review"]) == 1
    assert result["ingestion_pending_files"] == []
    assert route({**state, **result}) != "ingestion_worker"


# ═════════════════════════════════════════════════════════════════════════════
# R-02 — demo health check never touches PostgreSQL
# ═════════════════════════════════════════════════════════════════════════════

def _no_postgres(*args, **kwargs):
    raise AssertionError("PostgreSQL engine requested in demo mode")


def test_r02_demo_system_info_is_ok_without_postgres(monkeypatch):
    import sqlalchemy

    from cji.mcp_servers import journey_data_server as j
    from cji.repositories import event_repository, use_repository
    from cji.settings import get_settings

    monkeypatch.setattr(sqlalchemy, "create_engine", _no_postgres)
    with use_repository(event_repository(get_settings())):        # demo, chosen from settings
        res = run(j.get_system_info())
    assert res["status"] == "ok", res
    assert res["data_source"] == "parquet"


def test_r02_demo_system_info_reports_missing_parquet(monkeypatch, tmp_path):
    import sqlalchemy

    from cji.mcp_servers import journey_data_server as j
    from cji.repositories import DuckDbParquetRepository, use_repository

    monkeypatch.setattr(sqlalchemy, "create_engine", _no_postgres)
    with use_repository(DuckDbParquetRepository(tmp_path / "missing.parquet")):
        res = run(j.get_system_info())
    assert res["status"] == "error"
    assert "events.parquet not found" in res["error"]


# ═════════════════════════════════════════════════════════════════════════════
# R-04 — SQL values are bound, never interpolated
# ═════════════════════════════════════════════════════════════════════════════

def test_r04_demo_step_filter_is_not_injectable():
    from cji.mcp_servers import journey_data_server as j

    res = run(j.query_events(limit=100, step_id="x' OR '1'='1"))
    assert "error" not in res, res
    assert res["count"] == 0


def test_r04_demo_quotes_in_config_values_do_not_break_sql(monkeypatch):
    from cji.mcp_servers import journey_data_server as j

    monkeypatch.setattr(j, "JOURNEY_CONFIG", {"name": "o'brien", "steps": ["a'b", "c"]})
    for res in (run(j.get_step_metrics()), run(j.get_funnel_dropoff()), run(j.query_events(limit=5))):
        assert "error" not in res, res


def test_r04_realtime_values_are_bound_parameters(monkeypatch):
    from cji.mcp_servers import journey_data_server as j

    captured = []

    def fake_read_sql(sql, con, params=None, **kw):
        captured.append((str(sql), dict(params or {})))
        return pd.DataFrame()

    from cji.repositories import PostgresEventRepository, use_repository
    from cji.repositories import postgres as pg_module

    realtime = PostgresEventRepository("postgresql://u@127.0.0.1:1/x", engine_factory=lambda *a, **k: FakeEngine())
    monkeypatch.setattr(j, "JOURNEY_CONFIG", {"name": "evil_journey'", "steps": ["evil_step_a'", "b"]})
    monkeypatch.setattr(pg_module.pd, "read_sql", fake_read_sql)

    with use_repository(realtime):
        run(j.get_step_metrics(minutes_back=7))
        run(j.get_funnel_dropoff(minutes_back=7))
        run(j.query_events(limit=5, step_id="evil_step_x'", event_type="evil_type'"))
        run(j.get_live_snapshot(minutes=9))

    assert len(captured) == 4
    for sql, params in captured:
        assert "evil" not in sql, sql
        assert "'7 minutes'" not in sql and "'9 minutes'" not in sql, sql
        assert params, f"no bound parameters for: {sql[:80]}"
    bound = [v for _, p in captured for v in p.values()]
    for expected in ("evil_journey'", "evil_step_x'", "evil_type'", 7, 9):
        assert expected in bound, expected


@pytest.mark.parametrize("minutes", [0, -5, 10**9])
def test_r04_live_stats_rejects_out_of_range_minutes(collector_api, monkeypatch, minutes):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(collector_api, "engine", FakeEngine())
    client = TestClient(collector_api.app, raise_server_exceptions=False)
    assert client.get(f"/live/stats?minutes={minutes}").status_code == 422


def test_r04_live_stats_binds_minutes(collector_api, monkeypatch):
    from fastapi.testclient import TestClient

    fake = FakeEngine()
    monkeypatch.setattr(collector_api, "engine", fake)
    monkeypatch.setattr(collector_api, "CJI_ADMIN_KEY", GOOD_KEY)       # admin only since Spec 07 (OD-44)
    client = TestClient(collector_api.app, raise_server_exceptions=False)
    assert client.get("/live/stats?minutes=30", headers={"X-CJI-Admin-Key": GOOD_KEY}).status_code == 200
    sql, params = fake.log[-1]
    assert "30 minutes" not in sql
    assert params.get("minutes") == 30


# ═════════════════════════════════════════════════════════════════════════════
# R-03 — CORS, admin credential, and seeded keys
# ═════════════════════════════════════════════════════════════════════════════

GOOD_KEY = "k" * 40


def test_r03_settings_development_allows_local_defaults(collector_api):
    collector_api.validate_collector_settings("development", "change-me-in-production", [])


@pytest.mark.parametrize("env", ["production", "test", "staging", ""])
@pytest.mark.parametrize("key", ["", "change-me-in-production", "short-key"])
def test_r03_settings_fail_closed_on_bad_admin_key(collector_api, env, key):
    with pytest.raises(RuntimeError, match="CJI_ADMIN_KEY"):
        collector_api.validate_collector_settings(env, key, ["https://app.example"])


def test_r03_settings_fail_closed_without_origins(collector_api):
    with pytest.raises(RuntimeError, match="CJI_CORS_ORIGINS"):
        collector_api.validate_collector_settings("production", GOOD_KEY, [])


def test_r03_settings_production_passes_when_configured(collector_api):
    collector_api.validate_collector_settings("production", GOOD_KEY, ["https://app.example"])


def test_r03_cors_never_allows_credentials_or_unlisted_origins(collector_api):
    from fastapi.testclient import TestClient

    client = TestClient(collector_api.app, raise_server_exceptions=False)
    res = client.options(
        "/collect/batch",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert res.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")
    assert res.headers.get("access-control-allow-credentials") != "true"

    cors = [m for m in collector_api.app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert len(cors) == 1
    assert cors[0].kwargs["allow_credentials"] is False
    assert "*" not in cors[0].kwargs["allow_origins"]


def test_r03_admin_endpoint_rejects_default_key(collector_api, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(collector_api, "engine", FakeEngine())
    monkeypatch.setattr(collector_api, "CJI_ADMIN_KEY", "change-me-in-production")
    client = TestClient(collector_api.app, raise_server_exceptions=False)
    res = client.post(
        "/admin/api-keys",
        json={"journey_name": "j", "description": "d"},
        headers={"X-CJI-Admin-Key": "change-me-in-production"},
    )
    assert res.status_code == 403


def test_r03_admin_endpoint_accepts_strong_key(collector_api, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(collector_api, "engine", FakeEngine())
    monkeypatch.setattr(collector_api, "CJI_ADMIN_KEY", GOOD_KEY)
    client = TestClient(collector_api.app, raise_server_exceptions=False)
    ok = client.post("/admin/api-keys", json={"journey_name": "j", "description": "d"},
                     headers={"X-CJI-Admin-Key": GOOD_KEY})
    bad = client.post("/admin/api-keys", json={"journey_name": "j", "description": "d"},
                      headers={"X-CJI-Admin-Key": GOOD_KEY[:-1] + "x"})
    assert ok.status_code == 200 and ok.json()["api_key"].startswith("cji_live_")
    assert bad.status_code == 403


@pytest.mark.parametrize("env, dev_key_expected", [("production", False), ("development", True)])
def test_r03_startup_never_seeds_live_key(collector_api, monkeypatch, env, dev_key_expected):
    fake = FakeEngine()
    monkeypatch.setattr(collector_api, "engine", fake)
    monkeypatch.setattr(collector_api, "CJI_ENV", env)
    collector_api._create_tables()

    statements = " ".join(sql for sql, _ in fake.log)
    seeded = " ".join(str(v) for _, p in fake.log for v in p.values())
    assert "cji_live_" not in statements + seeded
    assert ("cji_dev_localtest" in statements + seeded) is dev_key_expected


# ═════════════════════════════════════════════════════════════════════════════
# R-05 — report HTML and embedded script data are escaped
# ═════════════════════════════════════════════════════════════════════════════

XSS = "<script>alert(1)</script>"
ATTR = '"><img src=x onerror=alert(1)>'
BREAKOUT = "</script><script>alert(2)</script>"


def _report(monkeypatch, tmp_path, **overrides):
    from cji.mcp_servers import report_server as rs

    monkeypatch.setattr(rs, "REPORTS_DIR", tmp_path)
    args = {
        "journey_name": "j1",
        "narrative": XSS,
        "friction_scores": [],
        # Spec 10: priority is an integer in the report contract; the attack strings go in the text fields.
        "insights": [{"priority": 1, "step_id": XSS, "title": ATTR,
                      "root_cause": XSS, "suggested_fix": 'back\\slash "quote" \u00fc\u2028'}],
        "funnel_data": [{"step_id": BREAKOUT, "users": 3}],
        "mode": "demo",
    }
    args.update(overrides)
    res = rs.export_report(**args)
    return Path(res["report_path"]).read_text(encoding="utf-8")


def test_r05_report_escapes_untrusted_text(monkeypatch, tmp_path):
    html = _report(monkeypatch, tmp_path)
    assert XSS not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in html


def test_r05_report_script_data_cannot_break_out(monkeypatch, tmp_path):
    html = _report(monkeypatch, tmp_path)
    assert BREAKOUT not in html
    assert "\\u003c/script\\u003e" in html


def test_r05_report_mode_is_allow_listed(monkeypatch, tmp_path):
    html = _report(monkeypatch, tmp_path, mode='demo" onclick="x')
    assert 'onclick="x' not in html
    assert 'class="badge unknown"' in html


def test_r05_report_escapes_journey_name(monkeypatch, tmp_path):
    html = _report(monkeypatch, tmp_path, journey_name="a&b")
    assert "CJI Report - a&amp;b" in html
