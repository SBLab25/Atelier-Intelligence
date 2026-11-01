"""Spec 14 (OD-147): the insight and report workers record where each LLM-backed result came from."""
from __future__ import annotations

import contextlib

from cji.integrations import ToolGateway
from cji.integrations import tools as tools_module
from cji.integrations.testing import FakeToolSession, MemoryAuditSink
from tests.test_gateway import run

CONFIG = {"configurable": {"thread_id": "thread-prov-1"}}


def _session(monkeypatch, handlers):
    import cji.agents.workers as w

    session = FakeToolSession(handlers)
    tools_module.reset_tool_gateway(ToolGateway(audit=MemoryAuditSink()))

    @contextlib.asynccontextmanager
    async def fake_session(name):
        yield session

    monkeypatch.setattr(w, "mcp_session", fake_session)
    return w


def _insight(step, llm):
    out = {"insight": {"insight_id": f"i-{step}", "step_id": step, "title": "T", "root_cause": "R",
                       "category": "UX", "evidence": [], "suggested_fix": "F", "fix_effort": "low"}}
    if llm is not None:
        out["llm"] = llm
    return out


def test_provenance_from_gateway_metadata():
    from cji.agents.workers import _provenance

    ok = _provenance({"outcome": "ok", "model": "m-1", "provider": "groq", "attempts": 1}, "2026-01-01T00:00:00Z")
    assert ok == {"source": "llm", "model": "m-1", "provider": "groq", "reason": None,
                  "generated_at": "2026-01-01T00:00:00Z"}
    fb = _provenance({"outcome": "fallback", "model": "m-1", "provider": "groq", "code": "llm_timeout"})
    assert fb["source"] == "fallback" and fb["model"] is None and fb["provider"] is None
    assert fb["reason"] == "llm_timeout" and fb["generated_at"]
    assert _provenance(None)["source"] == "not_recorded"
    assert _provenance({"outcome": "error"})["source"] == "not_recorded"


def test_insight_worker_records_provenance_per_insight(monkeypatch):
    calls = {"n": 0}

    def generate(args):
        calls["n"] += 1
        step = args["friction_score"]["step_id"]
        if step == "a":
            return _insight(step, {"outcome": "ok", "provider": "groq", "model": "m-x", "attempts": 1,
                                   "input_tokens": 1, "output_tokens": 1})
        if step == "b":
            return _insight(step, {"outcome": "fallback", "code": "llm_disabled", "attempts": 0})
        return _insight(step, None)["insight"]                     # an older server: no metadata

    w = _session(monkeypatch, {
        "generate_insight": generate,
        "prioritise_fix": lambda args: {**args["insight"], "priority": 1, "priority_score": 1.0},
        "save_insight": lambda args: {"status": "success"},
        "rank_all_fixes": lambda args: {"ranked_fixes": [], "total": 0},
    })
    state = {"friction_scores": [{"step_id": s, "score": 90, "is_critical": True} for s in ("a", "b", "c")],
             "event_summary": {"step_metrics": []}}
    out = run(w.insight_worker(state, CONFIG))
    prov = out["insight_provenance"]
    by_step = {ins["step_id"]: prov[ins["insight_id"]] for ins in out["insights"]}
    assert by_step["a"]["source"] == "llm" and by_step["a"]["model"] == "m-x" and by_step["a"]["provider"] == "groq"
    assert by_step["b"]["source"] == "fallback" and by_step["b"]["reason"] == "llm_disabled"
    assert by_step["c"]["source"] == "not_recorded"
    assert all("provenance" not in ins for ins in out["insights"])      # insight dicts unchanged (ChromaDB, report)


def test_insight_worker_without_critical_steps_records_empty_provenance(monkeypatch):
    w = _session(monkeypatch, {})
    out = run(w.insight_worker({"friction_scores": [{"step_id": "a", "score": 10, "is_critical": False}]}, CONFIG))
    assert out["insight_provenance"] == {} and out["insights"] == []


def test_report_worker_records_narrative_provenance(monkeypatch):
    w = _session(monkeypatch, {
        "generate_narrative": lambda args: {"narrative": "N", "generated_at": "2026-10-28T00:00:00Z",
                                            "llm": {"outcome": "ok", "attempts": 1, "model": "m-n",
                                                    "provider": "anthropic"}},
        "export_report": lambda args: {"report_path": "/tmp/r.html", "file_size_kb": 1.0},
    })
    out = run(w.report_worker({"insights": [], "friction_scores": []}, CONFIG))
    assert out["narrative_provenance"] == {"source": "llm", "model": "m-n", "provider": "anthropic", "reason": None,
                                           "generated_at": "2026-10-28T00:00:00Z"}


def test_initial_state_has_the_provenance_keys():
    from cji.state import CJIState
    from cji.workflow.runtime import initial_state

    state = initial_state(mode="demo", journey_name="j", journey_steps=["a"], auto_approve=False)
    assert state["insight_provenance"] == {} and state["narrative_provenance"] == {}
    assert set(CJIState.__annotations__) - {"run"} == set(state)
