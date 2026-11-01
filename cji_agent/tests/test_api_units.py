"""
Spec 12 — building blocks of /api/v1 (design §8): friction module, keyset paging, run index, approval split,
tokens, cursors, idempotency, settings, shared request ids and the CLI/dashboard adapters.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests._api_harness import copy_demo_data

JOURNEY = "user_onboarding"


# ── friction and funnel modules (OD-112) ─────────────────────────────────────────────────────────────

def test_friction_module_matches_the_mcp_tool_on_the_demo_data(tmp_path):
    from cji.analytics import friction
    from cji.mcp_servers import friction_engine_server as server
    from cji.repositories import DuckDbParquetRepository, TimeWindow

    repo = DuckDbParquetRepository(copy_demo_data(tmp_path))
    try:
        metrics = repo.step_metrics(JOURNEY, TimeWindow())
    finally:
        repo.close()
    tool = getattr(server.score_all_steps, "fn", server.score_all_steps)
    assert friction.score_steps(metrics, threshold=60) == tool(metrics)
    assert server.WEIGHTS is friction.WEIGHTS and server.BASELINES is friction.BASELINES
    assert server._compute_score is friction._compute_score


def test_friction_module_is_pure():
    code = ("import sys, cji.analytics.friction, cji.analytics.funnel; "
            "print(sorted(m for m in sys.modules if m.startswith('cji.') and not m.startswith('cji.analytics')))")
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True, timeout=120, check=False)
    assert out.returncode == 0, out.stderr[-800:]
    assert out.stdout.strip() == "[]"


def test_overall_completion_is_shared_with_the_journey_data_server():
    from cji.analytics.funnel import overall_completion_pct
    from cji.mcp_servers import journey_data_server as j

    funnel = [{"step_id": "a", "users": 200, "drop_off_pct": 10.0}, {"step_id": "b", "users": 50, "drop_off_pct": 0.0}]
    assert overall_completion_pct(funnel) == j._overall_completion_pct(funnel) == 25.0
    assert overall_completion_pct([]) == 100.0


# ── keyset paging (OD-119) ───────────────────────────────────────────────────────────────────────────

def test_events_page_walks_every_matching_event_once(tmp_path):
    from cji.repositories import DuckDbParquetRepository

    repo = DuckDbParquetRepository(copy_demo_data(tmp_path))
    try:
        seen, after = [], None
        while True:
            rows = repo.events_page(JOURNEY, limit=500, after=after, step_id="onboarding_done", event_type=None)
            seen += [(r["timestamp"], r["event_id"]) for r in rows]
            if len(rows) < 500:
                break
            after = (rows[-1]["timestamp"], rows[-1]["event_id"])
        total = repo._query("count", "SELECT COUNT(*) AS n FROM events WHERE journey_id = $j AND step_id = $s",
                            {"j": JOURNEY, "s": "onboarding_done"})["n"].iloc[0]
    finally:
        repo.close()
    assert len(seen) == len(set(seen)) == int(total) > 500


def test_events_page_sql_binds_every_value():
    from cji.repositories.queries import (
        DUCKDB,
        POSTGRES,
        events_page_sql,
        realtime_page_source,
    )

    for sql in (events_page_sql(DUCKDB, "events"), events_page_sql(POSTGRES, realtime_page_source(JOURNEY))):
        assert "ORDER BY timestamp DESC, event_id DESC" in sql
        for name in ("journey_id", "step_id", "event_type", "after_ts", "after_id", "limit"):
            assert name in sql
        assert JOURNEY not in sql


# ── run index and approval split (OD-115, OD-116) ────────────────────────────────────────────────────

@pytest.fixture
def wf(tmp_path, monkeypatch):
    from cji.graph import build_graph
    from cji.settings import make_test_settings, override_settings
    from cji.workflow.runtime import Workflow
    from tests import _workflow_stubs as stubs

    monkeypatch.setenv("WORKFLOW_STUB_STORE", str(tmp_path / "store.json"))
    stubs.FAULTS.clear()
    settings = make_test_settings(tmp_path, CJI_CHECKPOINTS_DB=str(tmp_path / "cp.db"), CJI_WORKFLOW_RETRY_BACKOFF_S="0")
    with override_settings(settings):
        yield lambda: Workflow(tmp_path / "cp.db", graph=build_graph(nodes=stubs.nodes()), owner="unit-owner")
    stubs.FAULTS.clear()


def _state(auto):
    from cji.workflow.runtime import initial_state

    return initial_state(mode="demo", journey_name=JOURNEY, journey_steps=["s1", "s2"], auto_approve=auto)


def test_the_workflow_keeps_the_run_index_current(wf, tmp_path):
    from cji.workflow.index import RunIndex

    done = asyncio.run(wf().start(_state(True))).run_id
    paused = asyncio.run(wf().start(_state(False))).run_id
    index = RunIndex(tmp_path / "cp.db")
    rows = {r.run_id: r for r in index.page(journeys=None, journey_id=None, status=None, limit=10, after=None)}
    assert rows[done].status == "completed" and rows[done].report_file == f"cji_report_j_{done}.html"
    assert rows[paused].status == "awaiting_approval" and rows[paused].journey_id == JOURNEY
    assert rows[done].mode == "demo" and rows[done].created_at <= rows[done].updated_at


def test_mark_approved_changes_state_only(wf, tmp_path):
    from cji.workflow.errors import RunNotResumable
    from cji.workflow.index import RunIndex

    paused = asyncio.run(wf().start(_state(False))).run_id
    calls_before = json.loads((tmp_path / "store.json").read_text())["calls"]
    outcome = asyncio.run(wf().mark_approved(paused))
    assert outcome.status == "approved" and not outcome.already
    assert json.loads((tmp_path / "store.json").read_text())["calls"] == calls_before      # no worker ran
    assert RunIndex(tmp_path / "cp.db").get(paused).status == "approved"
    assert asyncio.run(wf().mark_approved(paused)).already
    final = asyncio.run(wf().resume(paused))
    assert final.status == "completed"
    done = asyncio.run(wf().start(_state(True))).run_id
    assert asyncio.run(wf().mark_approved(done)).already
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["data_worker"] = [RuntimeError("x")] * 5
    failed = asyncio.run(wf().start(_state(False))).run_id
    with pytest.raises(RunNotResumable):
        asyncio.run(wf().mark_approved(failed))


def test_backfill_indexes_runs_written_before_the_index(wf, tmp_path):
    import sqlite3

    from cji.workflow.index import RunIndex

    run_id = asyncio.run(wf().start(_state(True))).run_id
    with sqlite3.connect(tmp_path / "cp.db") as conn:
        conn.execute("DELETE FROM run_index")
    index = RunIndex(tmp_path / "cp.db")
    assert index.get(run_id) is None
    assert asyncio.run(index.backfill(wf())) == 1
    assert index.get(run_id).status == "completed"
    assert asyncio.run(index.backfill(wf())) == 0


def test_cli_status_goes_through_the_service_and_is_unchanged(wf):
    from cji.services.runs import cli_status

    run_id = asyncio.run(wf().start(_state(True))).run_id
    assert asyncio.run(cli_status(wf(), run_id)) == asyncio.run(wf().status(run_id))


# ── tokens (OD-109) ─────────────────────────────────────────────────────────────────────────────────

def test_token_store_stores_only_hashes_and_reloads(tmp_path):
    from cji.api.auth import TokenStore, create_token, revoke_token, token_id_for

    path = tmp_path / "tokens.json"
    token = create_token(path, label="ui", role="viewer", journeys=[JOURNEY])
    assert token.startswith("cji_api_") and len(token) >= 40
    assert token not in path.read_text(encoding="utf-8")
    store = TokenStore(path)
    principal = store.authenticate(token)
    assert principal and principal.role == "viewer" and principal.journeys == (JOURNEY,)
    assert principal.token_id == token_id_for(token)
    assert store.authenticate(token + "x") is None and store.authenticate("") is None
    time.sleep(0.01)
    revoke_token(path, principal.token_id)
    assert store.authenticate(token) is None                       # file change picked up
    expired = create_token(path, label="old", role="viewer", journeys=["*"], expires_days=-1)
    assert store.authenticate(expired) is None


def test_token_store_rejects_a_malformed_file(tmp_path):
    from cji.api.auth import TokenFileError, TokenStore

    path = tmp_path / "tokens.json"
    path.write_text('{"version": 1, "tokens": [{"sha256": "x", "role": "root"}]}', encoding="utf-8")
    with pytest.raises(TokenFileError):
        TokenStore(path).authenticate("cji_api_anything")


def test_principal_permissions():
    from cji.api.auth import Principal

    viewer = Principal("tok_1", "v", "viewer", (JOURNEY,))
    admin = Principal("tok_2", "a", "admin", ("*",))
    assert viewer.can_see(JOURNEY) and not viewer.can_see("other") and admin.can_see("anything")
    assert viewer.has_role("viewer") and not viewer.has_role("operator") and admin.has_role("operator")


def test_token_cli_creates_lists_and_revokes(tmp_path):
    path = tmp_path / "tokens.json"
    base = [sys.executable, "-m", "cji.api.tokens_cli", "--file", str(path)]
    created = subprocess.run([*base, "create", "--label", "ui", "--role", "operator", "--journey", JOURNEY],
                             capture_output=True, text=True, timeout=120, check=False)
    assert created.returncode == 0, created.stderr
    token = next(line.split()[-1] for line in created.stdout.splitlines() if "cji_api_" in line)
    listed = subprocess.run([*base, "list"], capture_output=True, text=True, timeout=120, check=False)
    assert listed.returncode == 0 and "ui" in listed.stdout and token not in listed.stdout
    token_id = next(word for word in listed.stdout.split() if word.startswith("tok_"))
    revoked = subprocess.run([*base, "revoke", token_id], capture_output=True, text=True, timeout=120, check=False)
    assert revoked.returncode == 0
    assert json.loads(path.read_text(encoding="utf-8"))["tokens"][0]["revoked"] is True


# ── cursors and idempotency (OD-117, OD-119) ────────────────────────────────────────────────────────

def test_cursor_round_trip_and_tampering():
    from cji.api.errors import ApiError
    from cji.api.pagination import CursorCodec

    codec = CursorCodec(b"k" * 32)
    cursor = codec.encode(["2026-01-01 00:00:00+00:00", "e1"], {"step_id": "a"})
    assert codec.decode(cursor, {"step_id": "a"}) == ["2026-01-01 00:00:00+00:00", "e1"]
    for bad, filters in ((cursor, {"step_id": "b"}), (cursor[:-1] + ("A" if cursor[-1] != "A" else "B"),
                                                      {"step_id": "a"}), ("garbage", {}), ("", {})):
        with pytest.raises(ApiError) as exc:
            codec.decode(bad, filters)
        assert exc.value.code == "invalid_cursor"
    assert CursorCodec(b"other-key" * 4).encode(["x"], {}) != CursorCodec(b"k" * 32).encode(["x"], {})


def test_idempotency_store_lifecycle(tmp_path):
    from cji.api.errors import ApiError
    from cji.api.idempotency import IdempotencyStore

    store = IdempotencyStore(tmp_path / "state.db", ttl_s=3600)
    h1, h2 = store.request_hash("POST /x", b"{}"), store.request_hash("POST /x", b'{"a":1}')
    assert store.begin("tok_a", "key-00000001", "POST /x", h1) is None
    with pytest.raises(ApiError) as exc:
        store.begin("tok_a", "key-00000001", "POST /x", h1)
    assert exc.value.code == "request_in_progress"
    store.finish("tok_a", "key-00000001", 202, {"ok": True})
    assert store.begin("tok_a", "key-00000001", "POST /x", h1) == (202, {"ok": True})
    with pytest.raises(ApiError) as exc:
        store.begin("tok_a", "key-00000001", "POST /x", h2)
    assert exc.value.code == "idempotency_key_reused"
    assert store.begin("tok_b", "key-00000001", "POST /x", h2) is None             # keys are per token
    store.abandon("tok_b", "key-00000001")
    assert store.begin("tok_b", "key-00000001", "POST /x", h2) is None
    assert store.purge(now=time.time() + 7200) >= 2


# ── settings, request ids, adapters (OD-120, OD-125, OD-126) ────────────────────────────────────────

def test_api_settings_and_registry(tmp_path):
    from cji.settings import KNOWN_KEYS, make_test_settings

    s = make_test_settings(tmp_path)
    assert s.services.get("api").port == 8006 and s.services.get("api").kind == "http"
    assert s.api.rate_per_token == 120 and s.api.rate_per_ip == 60
    assert s.api.tokens_file == s.storage.data_dir / "api_tokens.json"
    for key in ("CJI_API_TOKENS_FILE", "CJI_API_RATE_PER_TOKEN", "CJI_API_RATE_PER_IP", "CJI_API_CORS_ORIGINS",
                "CJI_API_CURSOR_SECRET", "CJI_API_PORT", "CJI_API_URL"):
        assert key in KNOWN_KEYS
    assert "set (40 chars)" in json.dumps(make_test_settings(tmp_path, CJI_API_CURSOR_SECRET="s" * 40).describe())


def test_api_role_fails_closed_in_production(tmp_path):
    from cji.settings import ConfigError, load_settings, require

    base = {"CJI_ENV": "production", "CJI_MODE": "demo", "CJI_DATA_DIR": str(tmp_path / "d"),
            "CJI_REPORTS_DIR": str(tmp_path / "r")}
    with pytest.raises(ConfigError) as exc:
        require(load_settings({**base, "CJI_API_CORS_ORIGINS": "http://app.example.com"}, dotenv_path=None), "api")
    text = str(exc.value)
    assert "CJI_API_CURSOR_SECRET" in text and "https" in text
    ok = load_settings({**base, "CJI_API_CORS_ORIGINS": "https://app.example.com", "CJI_API_CURSOR_SECRET": "s" * 40},
                       dotenv_path=None)
    assert require(ok, "api") is ok
    with pytest.raises(ConfigError):
        load_settings({**base, "CJI_API_CORS_ORIGINS": "*"}, dotenv_path=None)


def test_request_id_code_is_shared_with_the_collector():
    from cji.collector import middleware
    from cji.http import request_id

    assert middleware.resolve_request_id is request_id.resolve_request_id
    assert middleware.current_request_id is request_id.current_request_id
    assert request_id.resolve_request_id("good-id-0001") == "good-id-0001"
    assert len(request_id.resolve_request_id("bad id")) == 36


def test_dashboard_report_list_uses_the_service(tmp_path):
    import os

    from cji.services.reports import list_report_files

    old = tmp_path / "cji_report_j_a.html"
    new = tmp_path / "cji_report_j_b.html"
    old.write_text("a")
    new.write_text("b")
    os.utime(old, (1, 1))
    (tmp_path / "notes.txt").write_text("x")
    assert list_report_files(tmp_path) == [new, old]
    assert list_report_files(tmp_path / "missing") == []
    source = (Path(__file__).resolve().parent.parent / "src" / "cji" / "dashboard.py").read_text(encoding="utf-8")
    assert "list_report_files(REPORTS_DIR)" in source


def test_api_command_help():
    out = subprocess.run([sys.executable, "-m", "cji.api.serve", "--help"], capture_output=True, text=True,
                         timeout=120, check=False)
    assert out.returncode == 0 and "usage" in out.stdout.lower()
