"""
Spec 09 — durable workflow (design §8): typed run state, step wrapper (guard, retries, timeouts), failure
stop, approval, resume after exceptions and process death, leases, audit, idempotent side effects.

Workers are the stubs in `_workflow_stubs.py` (real `@step` wrapper, JSON side-effect store) or the real
workers with fake MCP sessions. Checkpoints are SQLite files in tmp_path. No servers, network or databases.
"""
import asyncio
import contextlib
import inspect
import itertools
import json
import os
import subprocess
import sys
import typing
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parent.parent
RUN_STATUSES = ("running", "awaiting_approval", "approved", "completed", "failed")
ALLOWED = {
    (None, "running"),
    ("running", "awaiting_approval"), ("running", "approved"), ("running", "failed"),
    ("awaiting_approval", "approved"),
    ("approved", "completed"), ("approved", "failed"),
    ("failed", "running"), ("failed", "approved"),
}


def run(value):
    return asyncio.run(value) if inspect.isawaitable(value) else value


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────────

class Env:
    def __init__(self, tmp_path, settings, audit):
        self.tmp = tmp_path
        self.db = tmp_path / "checkpoints.db"
        self.store_path = tmp_path / "store.json"
        self.settings = settings
        self.audit = audit

    def store(self):
        return json.loads(self.store_path.read_text(encoding="utf-8")) if self.store_path.exists() else {
            "calls": [], "insights": {}, "reports": {}}

    def calls(self):
        return self.store()["calls"]

    def workflow(self, owner="test-owner", **kw):
        from graph import build_graph
        from tests import _workflow_stubs as stubs
        from workflow.runtime import Workflow

        return Workflow(self.db, graph=build_graph(nodes=stubs.nodes()), owner=owner, **kw)

    def state(self, auto_approve=False):
        from workflow.runtime import initial_state

        return initial_state(mode="demo", journey_name="j", journey_steps=["s1", "s2"], auto_approve=auto_approve)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from integrations.testing import MemoryAuditSink
    from settings import make_test_settings, override_settings

    settings = make_test_settings(tmp_path, CJI_WORKFLOW_RETRY_BACKOFF_S="0",
                                  CJI_CHECKPOINTS_DB=str(tmp_path / "checkpoints.db"))
    monkeypatch.setenv("WORKFLOW_STUB_STORE", str(tmp_path / "store.json"))
    monkeypatch.delenv("WORKFLOW_STUB_CRASH", raising=False)
    audit = MemoryAuditSink()
    with override_settings(settings):
        import workflow.step as step_module
        from tests import _workflow_stubs as stubs

        stubs.FAULTS.clear()
        stubs.WARNINGS.clear()
        monkeypatch.setattr(step_module, "AUDIT", audit)
        yield Env(tmp_path, settings, audit)
        stubs.FAULTS.clear()
        stubs.WARNINGS.clear()


def tool_failed(msg="MCP tool 'x' failed: RuntimeError (tool_failed)"):
    from integrations import ToolFailed
    return ToolFailed(msg)


def tool_timeout():
    from integrations import ToolTimeout
    return ToolTimeout("MCP tool 'x' timed out after 150s (tool_timeout)")


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# F-32 (Spec 08 defect)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_error_text_handles_gateway_errors():
    import agents.workers as w
    from integrations import ToolFailed

    assert w._error_text(ToolFailed("MCP tool 't' failed (tool_failed)")) == "MCP tool 't' failed (tool_failed)"


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Typed state (OD-70 / OD-71)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("old, new", list(itertools.product((None, *RUN_STATUSES), RUN_STATUSES)))
def test_run_transition_table(old, new):
    from domain.runs import IllegalTransition, transition

    if old == new or (old, new) in ALLOWED:
        assert transition(old, new) == new
    else:
        with pytest.raises(IllegalTransition):
            transition(old, new)


def test_step_transitions():
    from domain.runs import IllegalTransition, step_transition

    for old, new in [(None, "succeeded"), (None, "failed"), ("pending", "succeeded"), ("failed", "pending"),
                     ("failed", "failed"), ("failed", "succeeded"), ("succeeded", "succeeded")]:
        assert step_transition(old, new) == new
    for old, new in [("succeeded", "failed"), ("succeeded", "pending")]:
        with pytest.raises(IllegalTransition):
            step_transition(old, new)


def test_merge_run_merges_steps_and_checks_status():
    from domain.runs import IllegalTransition, merge_run

    rec = merge_run({}, {"run_id": "r1", "status": "running", "steps": {}, "failure": None})
    rec = merge_run(rec, {"steps": {"data_worker": {"worker": "data_worker", "status": "succeeded", "attempts": 1}}})
    rec = merge_run(rec, {"steps": {"friction_worker": {"worker": "friction_worker", "status": "failed",
                                                        "attempts": 2}}, "status": "failed",
                          "failure": {"worker": "friction_worker", "code": "tool_failed"}})
    assert set(rec["steps"]) == {"data_worker", "friction_worker"} and rec["status"] == "failed"
    assert rec["failure"]["code"] == "tool_failed"
    with pytest.raises(IllegalTransition):
        merge_run(rec, {"status": "completed"})
    with pytest.raises(IllegalTransition):
        merge_run(rec, {"run_id": "another"})


def test_state_lists_append_and_run_merges():
    import operator

    from domain.runs import merge_run
    from state import CJIState

    hints = typing.get_type_hints(CJIState, include_extras=True)
    for key in ("errors", "worker_statuses"):
        assert hints[key].__metadata__[0] is operator.add, key
    assert hints["run"].__metadata__[0] is merge_run


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Graph shape (R1 / R11 / OD-75)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_build_graph_has_no_persistence_switch():
    from graph import build_graph

    assert list(inspect.signature(build_graph).parameters) == ["nodes"]


def test_graph_is_sequential_with_one_successor_per_worker():
    from graph import WORKER_NODES, build_graph

    g = build_graph()
    for worker in WORKER_NODES:
        assert [e for e in g.edges if e[0] == worker] == [(worker, "supervisor")]
    for rel in ("graph.py", "agents/supervisor.py", "agents/workers.py", "agents/ingestion_worker.py",
                "workflow/runtime.py", "workflow/step.py"):
        src = (APP_ROOT / rel).read_text(encoding="utf-8")
        assert "Send(" not in src and "asyncio.gather" not in src, rel


def test_worker_order_is_unchanged(env):
    out = run(env.workflow().start(env.state(auto_approve=True)))
    assert out.status == "completed"
    assert env.calls() == ["data_worker", "friction_worker", "insight_worker", "report_worker"]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Step wrapper (OD-69 / OD-73 / OD-76)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_step_records_run_and_step_ids(env):
    out = run(env.workflow().start(env.state(auto_approve=True), run_id="run-ids-1"))
    statuses = out.values["worker_statuses"]
    assert [s["step_id"] for s in statuses] == [f"run-ids-1:{w}:1" for w in
                                                ("data_worker", "friction_worker", "insight_worker", "report_worker")]
    assert all(s["run_id"] == "run-ids-1" for s in statuses)
    steps = out.values["run"]["steps"]
    assert {w: s["status"] for w, s in steps.items()} == {w: "succeeded" for w in steps}
    assert steps["data_worker"]["started_at"] <= steps["data_worker"]["finished_at"]


def test_succeeded_step_is_not_run_again(env):
    from tests import _workflow_stubs as stubs

    state = {"run": {"run_id": "r-guard", "status": "running", "failure": None,
                     "steps": {"data_worker": {"worker": "data_worker", "status": "succeeded", "attempts": 1}}}}
    assert run(stubs.data_worker(state)) == {}
    assert env.calls() == []
    assert env.audit.of_kind("step")[-1]["outcome"] == "skipped"


def test_retryable_error_is_retried(env):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["data_worker"] = [tool_timeout()]
    out = run(env.workflow().start(env.state(auto_approve=True)))
    assert out.status == "completed"
    assert out.values["run"]["steps"]["data_worker"]["attempts"] == 2
    assert env.calls().count("data_worker") == 2
    data = [r for r in env.audit.of_kind("step") if r.get("worker") == "data_worker"]
    assert [(r["attempt"], r["outcome"]) for r in data] == [(1, "error"), (2, "ok")]
    assert data[0]["code"] == "tool_timeout" and data[0]["retryable"] is True


def test_non_retryable_error_fails_at_once(env):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["data_worker"] = [tool_failed()]
    out = run(env.workflow().start(env.state(auto_approve=True)))
    assert out.status == "failed" and env.calls() == ["data_worker"]
    assert out.values["run"]["steps"]["data_worker"] == {**out.values["run"]["steps"]["data_worker"],
                                                         "status": "failed", "attempts": 1, "code": "tool_failed"}


def test_attempts_are_bounded(env):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["friction_worker"] = [tool_timeout() for _ in range(10)]
    out = run(env.workflow().start(env.state(auto_approve=True)))
    assert out.status == "failed"
    assert env.calls().count("friction_worker") == env.settings.workflow.step_attempts == 2


def test_step_timeout_is_a_retryable_failure(env, monkeypatch):
    from settings import override_settings
    from workflow.step import step

    calls = []

    @step("data_worker")
    async def slow(state):
        calls.append(1)
        await asyncio.sleep(5)
        return {}

    fast = env.settings.model_copy(update={"workflow": env.settings.workflow.model_copy(
        update={"step_timeout_s": 0.05})})
    with override_settings(fast):
        out = run(slow({"run": {"run_id": "r-timeout", "status": "running", "steps": {}, "failure": None}}))
    assert len(calls) == 2
    assert out["run"]["failure"]["code"] == "step_timeout" and out["run"]["failure"]["retryable"] is True


def test_cancellation_propagates(env):
    from workflow.step import step

    @step("data_worker")
    async def cancelled(state):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        run(cancelled({"run": {"run_id": "r-cancel", "status": "running", "steps": {}, "failure": None}}))


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Structured failures (OD-72 / R8)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_data_failure_stops_the_run_with_a_structured_error(env):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["data_worker"] = [tool_failed("MCP tool 'get_step_metrics' failed (tool_failed)")]
    out = run(env.workflow().start(env.state(auto_approve=True), run_id="run-fail-1"))
    failure = out.values["run"]["failure"]
    assert failure == {"step_id": "run-fail-1:data_worker:1", "worker": "data_worker", "code": "tool_failed",
                       "message": "MCP tool 'get_step_metrics' failed (tool_failed)", "retryable": False,
                       "attempts": 1}
    assert env.calls() == ["data_worker"]                    # no data <-> friction loop (F-34)
    assert out.values["iteration"] < 3
    [error] = out.values["errors"]
    assert error["code"] == "tool_failed" and error["step_id"] == "run-fail-1:data_worker:1"


def test_every_error_of_the_run_is_kept_in_order(env):
    from tests import _workflow_stubs as stubs

    stubs.WARNINGS["data_worker"] = "contract warning: step metrics"
    stubs.FAULTS["friction_worker"] = [tool_failed()]
    out = run(env.workflow().start(env.state(auto_approve=True)))
    assert [e["worker"] for e in out.values["errors"]] == ["data_worker", "friction_worker"]
    assert [s["worker"] for s in out.values["worker_statuses"]] == ["data_worker", "friction_worker"]


def test_iteration_cutoff_fails_the_run(env, monkeypatch):
    import agents.supervisor as sup

    monkeypatch.setattr(sup, "MAX_AGENT_ITERATIONS", 2)
    out = run(env.workflow().start(env.state(auto_approve=True)))
    assert out.status == "failed" and out.values["run"]["failure"]["code"] == "iteration_limit"


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Failure injection at the real worker boundaries (fake MCP sessions)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def _responses():
    return {
        "get_system_info": {"status": "ok", "mode": "demo", "total_events": 5},
        "get_step_metrics": {"step_metrics": [{"step_id": "s1", "unique_users": 10}]},
        "get_funnel_dropoff": {"funnel": []},
        "query_events": {"events": []},
        "score_all_steps": {"scores": [{"step_id": "s1", "score": 80, "is_critical": True}]},
        "generate_insight": {"insight": {"step_id": "s1", "title": "T", "root_cause": "R", "category": "UX",
                                         "suggested_fix": "F", "fix_effort": "low", "evidence": []},
                             "llm": {"attempts": 0, "outcome": "fallback"}},
        "save_insight": {"status": "success"},
        "rank_all_fixes": {"ranked_fixes": []},
        "generate_narrative": {"narrative": "N", "generated_at": "2026-01-01T00:00:00Z"},
        "export_report": {"report_path": "/reports/r.html", "file_size_kb": 1.0},
    }


def _fake_mcp(monkeypatch, faults=(), overrides=None):
    """Patch agents.workers' MCP helpers. `faults` are raised by the first tool calls, in order."""
    import agents.workers as w

    pending = list(faults)
    calls = []
    responses = {**_responses(), **(overrides or {})}

    @contextlib.asynccontextmanager
    async def fake_session(name):
        yield object()

    async def fake_call_tool(session, tool, arguments=None):
        calls.append((tool, dict(arguments or {})))
        if pending:
            raise pending.pop(0)
        if tool == "prioritise_fix":
            return {**arguments["insight"], "priority": 1, "priority_score": 1.0}
        return responses[tool]

    monkeypatch.setattr(w, "mcp_session", fake_session)
    monkeypatch.setattr(w, "call_tool", fake_call_tool)
    return calls


def _tracked_state(worker, run_id="run-real-1"):
    status = "approved" if worker == "report_worker" else "running"
    return {
        "mode": "demo", "journey_name": "j", "human_approved": True,
        "event_summary": {"step_metrics": [{"step_id": "s1", "unique_users": 10}], "funnel": []},
        "friction_scores": [{"step_id": "s1", "score": 80, "is_critical": True}],
        "insights": [{"step_id": "s1", "title": "T"}], "llm_usage": {},
        "run": {"run_id": run_id, "status": status, "steps": {}, "failure": None},
    }


REAL_WORKERS = ["data_worker", "friction_worker", "insight_worker", "report_worker"]


@pytest.mark.parametrize("worker", REAL_WORKERS)
def test_real_worker_retries_a_transient_tool_failure(env, monkeypatch, worker):
    import agents.workers as w

    _fake_mcp(monkeypatch, faults=[tool_timeout()])
    out = run(getattr(w, worker)(_tracked_state(worker)))
    record = out["run"]["steps"][worker]
    assert record["status"] == "succeeded" and record["attempts"] == 2
    assert out["worker_statuses"][-1]["status"] == "success"


@pytest.mark.parametrize("worker", REAL_WORKERS)
def test_real_worker_failure_is_structured(env, monkeypatch, worker):
    import agents.workers as w

    _fake_mcp(monkeypatch, faults=[tool_failed()])
    out = run(getattr(w, worker)(_tracked_state(worker)))
    assert out["run"]["status"] == "failed"
    assert out["run"]["failure"]["worker"] == worker and out["run"]["failure"]["code"] == "tool_failed"
    assert out["worker_statuses"][-1]["status"] == "error" and out["errors"][-1]["code"] == "tool_failed"


def test_mode_mismatch_is_not_retried(env, monkeypatch):
    import agents.workers as w

    calls = _fake_mcp(monkeypatch, overrides={"get_system_info": {"status": "ok", "mode": "realtime"}})
    out = run(w.data_worker(_tracked_state("data_worker")))
    assert out["run"]["failure"]["code"] == "mode_mismatch" and len(calls) == 1


def test_no_step_metrics_fails_friction(env, monkeypatch):
    import agents.workers as w

    _fake_mcp(monkeypatch)
    state = {**_tracked_state("friction_worker"), "event_summary": {"step_metrics": []}}
    out = run(w.friction_worker(state))
    assert out["run"]["failure"]["code"] == "no_step_metrics"


def test_insight_ids_are_run_scoped_and_stable(env, monkeypatch):
    import agents.workers as w
    from domain.runs import insight_id_for

    first = _fake_mcp(monkeypatch)
    run(w.insight_worker(_tracked_state("insight_worker")))
    second = _fake_mcp(monkeypatch)
    run(w.insight_worker(_tracked_state("insight_worker")))
    saved = [[a["insight"]["insight_id"] for t, a in c if t == "save_insight"] for c in (first, second)]
    assert saved[0] == saved[1] == [insight_id_for("run-real-1", "s1")]
    assert [a for t, a in first if t == "rank_all_fixes"] == [{"run_id": "run-real-1"}]


def test_report_is_named_by_run_and_a_missing_file_fails_the_step(env, monkeypatch):
    import agents.workers as w

    calls = _fake_mcp(monkeypatch)
    run(w.report_worker(_tracked_state("report_worker")))
    assert [a["run_id"] for t, a in calls if t == "export_report"] == ["run-real-1"]
    _fake_mcp(monkeypatch, overrides={"export_report": {"report_path": None, "error": "disk full",
                                                       "file_size_kb": 0}})
    out = run(w.report_worker(_tracked_state("report_worker")))
    assert out["run"]["failure"]["code"] == "report_export_failed"


@pytest.mark.parametrize("code, expected, retryable", [
    ("report_invalid_input", "report_invalid_input", False),
    ("report_too_large", "report_too_large", False),
    ("report_write_failed", "report_write_failed", True),
    ("made_up_code", "report_export_failed", False),
])
def test_report_error_codes_fail_the_step_with_that_code(env, monkeypatch, code, expected, retryable):
    """Spec 10 (OD-90): the server's code is the step's failure code; only a write failure is retried."""
    import agents.workers as w

    calls = _fake_mcp(monkeypatch, overrides={"export_report": {"report_path": None, "error": "boom",
                                                               "file_size_kb": 0, "code": code}})
    out = run(w.report_worker(_tracked_state("report_worker")))
    failure = out["run"]["failure"]
    assert failure["code"] == expected and failure["retryable"] is retryable
    assert failure["attempts"] == (2 if retryable else 1)
    assert sum(1 for t, _ in calls if t == "export_report") == failure["attempts"]


def test_report_worker_passes_provenance_to_the_report(env, monkeypatch):
    import agents.workers as w

    calls = _fake_mcp(monkeypatch, overrides={"generate_narrative": {
        "narrative": "N", "generated_at": "2026-01-01T00:00:00Z", "llm": {"attempts": 1, "outcome": "ok",
                                                                         "model": "m-1"}}})
    run(w.report_worker(_tracked_state("report_worker")))
    args = next(a for t, a in calls if t == "export_report")
    assert (args["generated_at"], args["narrative_source"], args["narrative_model"]) == (
        "2026-01-01T00:00:00Z", "llm", "m-1")


def test_fallback_narrative_records_no_model(env, monkeypatch):
    import agents.workers as w

    calls = _fake_mcp(monkeypatch, overrides={"generate_narrative": {
        "narrative": "N", "generated_at": "2026-01-01T00:00:00Z",
        "llm": {"attempts": 3, "outcome": "fallback", "code": "provider_unavailable", "model": "m-1"}}})
    run(w.report_worker(_tracked_state("report_worker")))
    args = next(a for t, a in calls if t == "export_report")
    assert (args["narrative_source"], args["narrative_model"]) == ("fallback", "")


def test_report_worker_output_passes_the_real_report_contract(env, monkeypatch, tmp_path):
    """The insights the insight worker produces satisfy the report input contract (design §10, first risk)."""
    import agents.workers as w
    from mcp_servers import report_server as srv

    monkeypatch.setattr(srv, "REPORTS_DIR", tmp_path / "reports")
    calls = _fake_mcp(monkeypatch)
    insight_out = run(w.insight_worker(_tracked_state("insight_worker")))
    state = {**_tracked_state("report_worker"), "insights": insight_out["insights"],
             "friction_scores": [{"step_id": "s1", "score": 80, "is_critical": True}],
             "event_summary": {"funnel": [{"step_id": "s1", "users": 10, "drop_off_pct": -2.5}]}}
    calls = _fake_mcp(monkeypatch)
    run(w.report_worker(state))
    args = next(a for t, a in calls if t == "export_report")
    res = srv.export_report(**args)
    assert res["report_path"], res


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Resume after process death (subprocess with os._exit at the worker boundary)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def _crash(env, run_id, where):
    code = f"from tests import _workflow_stubs as s; s.crash_main({str(env.db)!r}, {run_id!r})"
    proc_env = {**os.environ, "WORKFLOW_STUB_CRASH": where, "WORKFLOW_STUB_STORE": str(env.store_path),
                "CJI_ENV": "test", "CJI_DATA_DIR": str(env.tmp / "data"), "CJI_REPORTS_DIR": str(env.tmp / "reports"),
                "CJI_CHECKPOINTS_DB": str(env.db), "CJI_WORKFLOW_RETRY_BACKOFF_S": "0",
                "PYTHONPATH": str(APP_ROOT)}
    proc = subprocess.run([sys.executable, "-c", code], cwd=APP_ROOT, env=proc_env, capture_output=True,
                          text=True, timeout=180, check=False)
    assert proc.returncode == 9, proc.stderr[-1500:]


@pytest.mark.parametrize("where", ["data_worker:after", "friction_worker:before", "insight_worker:after",
                                   "report_worker:after"])
def test_resume_after_process_death_reruns_only_the_interrupted_step(env, where):
    worker = where.split(":")[0]
    run_id = f"run-crash-{worker}"
    _crash(env, run_id, where)
    assert env.calls()[-1] == worker
    out = run(env.workflow(owner="resumer").resume(run_id))
    assert out.status == "completed"
    calls = env.calls()
    for w in ("data_worker", "friction_worker", "insight_worker", "report_worker"):
        assert calls.count(w) == (2 if w == worker else 1), (w, calls)
    store = env.store()
    assert len(store["insights"]) == 1                       # upsert by run-scoped id: no duplicate insight
    assert list(store["reports"]) == [f"cji_report_j_{run_id}.html"]   # one report file for the run


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Approval (OD-74 / R9)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_pause_then_approve_runs_only_the_report(env):
    wf = env.workflow()
    paused = run(wf.start(env.state(), run_id="run-approve-1"))
    assert paused.status == "awaiting_approval" and not paused.values.get("report_path")
    assert env.calls() == ["data_worker", "friction_worker", "insight_worker"]
    done = run(env.workflow().approve("run-approve-1"))
    assert done.status == "completed" and done.values["report_path"]
    assert env.calls() == ["data_worker", "friction_worker", "insight_worker", "report_worker"]


def test_approve_twice_is_a_no_op(env):
    run(env.workflow().start(env.state(), run_id="run-approve-2"))
    run(env.workflow().approve("run-approve-2"))
    again = run(env.workflow().approve("run-approve-2"))
    assert again.already and again.status == "completed"
    assert env.calls().count("report_worker") == 1


def test_approve_unknown_run_is_refused(env):
    from workflow.errors import RunNotFound

    with pytest.raises(RunNotFound):
        run(env.workflow().approve("never-ran"))
    assert env.calls() == []


def test_approve_legacy_run_is_refused(env):
    from graph import build_graph
    from tests import _workflow_stubs as stubs
    from workflow.errors import LegacyRun
    from workflow.runtime import open_checkpointer

    async def legacy():
        async with open_checkpointer(env.db) as cp:
            graph = build_graph(nodes=stubs.nodes()).compile(checkpointer=cp)
            state = {k: v for k, v in env.state().items() if k != "run"}
            await graph.ainvoke(state, {"configurable": {"thread_id": "run-legacy"}, "recursion_limit": 60})

    run(legacy())
    with pytest.raises(LegacyRun):
        run(env.workflow().approve("run-legacy"))


def test_approve_failed_run_is_refused(env):
    from tests import _workflow_stubs as stubs
    from workflow.errors import RunNotResumable

    stubs.FAULTS["data_worker"] = [tool_failed()]
    run(env.workflow().start(env.state(), run_id="run-approve-failed"))
    with pytest.raises(RunNotResumable):
        run(env.workflow().approve("run-approve-failed"))


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Resume (OD-74 / R7) and leases (OD-77)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_resume_a_failed_run_after_the_cause_is_fixed(env):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["friction_worker"] = [tool_failed()]
    failed = run(env.workflow().start(env.state(auto_approve=True), run_id="run-resume-1"))
    assert failed.status == "failed"
    done = run(env.workflow().resume("run-resume-1"))
    assert done.status == "completed" and done.values["run"]["failure"] is None
    assert done.values["run"]["steps"]["friction_worker"]["attempts"] == 2
    assert env.calls() == ["data_worker", "friction_worker", "friction_worker", "insight_worker", "report_worker"]


def test_resume_after_approval_failure_keeps_the_approval(env):
    from tests import _workflow_stubs as stubs

    run(env.workflow().start(env.state(), run_id="run-resume-2"))
    stubs.FAULTS["report_worker"] = [tool_failed()]
    assert run(env.workflow().approve("run-resume-2")).status == "failed"
    done = run(env.workflow().resume("run-resume-2"))
    assert done.status == "completed" and env.calls().count("report_worker") == 2


@pytest.mark.parametrize("prepare, message", [("completed", "completed"), ("paused", "--approve")])
def test_resume_refuses_completed_and_paused_runs(env, prepare, message):
    from workflow.errors import RunNotResumable

    run(env.workflow().start(env.state(auto_approve=prepare == "completed"), run_id=f"run-{prepare}"))
    with pytest.raises(RunNotResumable, match=message):
        run(env.workflow().resume(f"run-{prepare}"))


def test_resume_unknown_run_is_refused(env):
    from workflow.errors import RunNotFound

    with pytest.raises(RunNotFound):
        run(env.workflow().resume("never-ran"))


def test_a_leased_run_is_refused(env):
    from tests import _workflow_stubs as stubs
    from workflow.errors import RunLeased
    from workflow.runtime import Lease

    stubs.FAULTS["friction_worker"] = [tool_failed()]
    run(env.workflow().start(env.state(auto_approve=True), run_id="run-lease-1"))
    Lease(env.db).acquire("run-lease-1", "other-process", ttl_s=600)
    with pytest.raises(RunLeased, match="other-process"):
        run(env.workflow().resume("run-lease-1"))
    assert env.calls().count("friction_worker") == 1


def test_a_lease_of_a_dead_local_process_is_taken_over(env):
    import socket

    from tests import _workflow_stubs as stubs
    from workflow.runtime import Lease, owner_id, owner_is_dead

    dead = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True,
                          check=True).stdout.strip()
    dead_owner = f"{socket.gethostname()}:{dead}:abcdef"
    assert owner_is_dead(dead_owner) and not owner_is_dead(owner_id()) and not owner_is_dead("other-process")
    stubs.FAULTS["friction_worker"] = [tool_failed()]
    run(env.workflow().start(env.state(auto_approve=True), run_id="run-lease-3"))
    Lease(env.db).acquire("run-lease-3", dead_owner, ttl_s=600)
    assert Lease(env.db).holder("run-lease-3") is None
    assert run(env.workflow().resume("run-lease-3")).status == "completed"


def test_an_expired_lease_is_taken_over(env):
    from tests import _workflow_stubs as stubs
    from workflow.runtime import Lease

    stubs.FAULTS["friction_worker"] = [tool_failed()]
    run(env.workflow().start(env.state(auto_approve=True), run_id="run-lease-2"))
    Lease(env.db).acquire("run-lease-2", "crashed-process", ttl_s=-1)
    assert run(env.workflow().resume("run-lease-2")).status == "completed"
    assert Lease(env.db).holder("run-lease-2") is None       # released at the end


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Diagnostics, CLI and dashboard data (R12 / OD-74)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_status_describes_a_partial_run(env):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["insight_worker"] = [tool_failed()]
    run(env.workflow().start(env.state(auto_approve=True), run_id="run-status-1"))
    status = run(env.workflow().status("run-status-1"))
    assert status["status"] == "failed" and status["failure"]["worker"] == "insight_worker"
    assert {w: s["status"] for w, s in status["steps"].items()} == {
        "data_worker": "succeeded", "friction_worker": "succeeded", "insight_worker": "failed"}
    assert status["errors_total"] == 1 and json.dumps(status)


def _cli(env, *args):
    proc_env = {**os.environ, "CJI_ENV": "test", "CJI_DATA_DIR": str(env.tmp / "data"),
                "CJI_REPORTS_DIR": str(env.tmp / "reports"), "CJI_CHECKPOINTS_DB": str(env.db)}
    return subprocess.run([sys.executable, "main.py", *args], cwd=APP_ROOT, env=proc_env, capture_output=True,
                          text=True, timeout=180, check=False)


def test_cli_status(env):
    run(env.workflow().start(env.state(), run_id="run-cli-1"))
    ok = _cli(env, "--status", "--thread-id", "run-cli-1")
    assert ok.returncode == 0, ok.stderr[-1500:]
    assert json.loads(ok.stdout[ok.stdout.index("{"):])["status"] == "awaiting_approval"
    missing = _cli(env, "--status", "--thread-id", "no-such-run")
    assert missing.returncode == 1 and "no-such-run" in missing.stderr


def test_cli_resume_and_approve_refuse_unknown_runs(env):
    for flag in ("--resume", "--approve"):
        proc = _cli(env, flag, "--thread-id", "no-such-run")
        assert proc.returncode == 1 and "no-such-run" in proc.stderr, (flag, proc.stderr[-800:])


def test_last_run_file_is_written_atomically_with_the_old_keys(env, tmp_path):
    from workflow.runtime import write_last_run

    path = tmp_path / "data" / "last_run.json"
    write_last_run(path, {"report_path": "/r.html", "narrative": "N", "friction_scores": [], "critical_steps": [],
                          "insights": [], "prioritized_fixes": []}, mode="demo", journey_name="j")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"timestamp", "mode", "journey_name", "report_path", "narrative", "friction_scores",
                         "critical_steps", "insights", "prioritized_fixes"}
    assert not list(path.parent.glob("*.tmp"))


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Workflow audit (OD-78)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_step_and_run_audit_records(env):
    from integrations.audit import AUDIT_FIELDS

    run(env.workflow().start(env.state(), run_id="run-audit-1"))
    run(env.workflow().approve("run-audit-1"))
    steps, runs = env.audit.of_kind("step"), env.audit.of_kind("run")
    assert [r["worker"] for r in steps] == ["data_worker", "friction_worker", "insight_worker", "report_worker"]
    assert all(r["run_id"] == "run-audit-1" and r["correlation_id"] == "run-audit-1" for r in steps + runs)
    assert [(r.get("from_status"), r["to_status"]) for r in runs] == [
        (None, "running"), ("running", "awaiting_approval"), ("awaiting_approval", "approved"),
        ("approved", "completed")]
    for record in steps + runs:
        assert set(record) <= set(AUDIT_FIELDS)
        assert "insight" not in json.dumps(record).replace("insight_worker", "")


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Idempotent side effects at the servers (OD-73)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

class _Embedding:
    """Offline embedding function for a test collection (Chroma's default would download a model)."""

    def __call__(self, input):      # Chroma calls it with this parameter name
        return [[float(len(text) % 7), 1.0, 0.5] for text in input]

    @staticmethod
    def name():
        return "cji-test"

    def is_legacy(self):
        return True


def test_save_insight_upserts_and_ranks_one_run(monkeypatch):
    import chromadb

    from domain.runs import insight_id_for
    from mcp_servers import insight_server as srv

    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(f"t{os.getpid()}", embedding_function=_Embedding())
    monkeypatch.setattr(srv, "_chroma_client", client)
    monkeypatch.setattr(srv, "_collection", collection)
    for run_id in ("run-a", "run-a", "run-b"):
        insight = {"insight_id": insight_id_for(run_id, "s1"), "run_id": run_id, "step_id": "s1", "title": "T",
                   "root_cause": "R", "suggested_fix": "F", "priority_score": 5.0}
        assert srv.save_insight(insight)["status"] == "success"
    assert collection.count() == 2
    assert [f["insight_id"] for f in srv.rank_all_fixes(run_id="run-a")["ranked_fixes"]] == [
        insight_id_for("run-a", "s1")]
    assert srv.rank_all_fixes()["total"] == 2


def test_export_report_twice_writes_one_file(monkeypatch, tmp_path):
    from mcp_servers import report_server as srv

    monkeypatch.setattr(srv, "REPORTS_DIR", tmp_path)
    args = {"journey_name": "j", "narrative": "N", "friction_scores": [], "insights": [], "funnel_data": [],
            "mode": "demo", "run_id": "run-report-1"}
    first, second = srv.export_report(**args), srv.export_report(**args)
    assert first["report_path"] == second["report_path"]
    assert [p.name for p in tmp_path.iterdir()] == ["cji_report_j_run-report-1.html"]


def test_missing_event_ids_are_deterministic(tmp_path):
    from mcp_servers import ingestion_intelligence_server as srv

    path = tmp_path / "events.csv"
    path.write_text("user_id,event_name,ts\nu1,click,2026-01-01T00:00:00Z\nu1,click,2026-01-01T00:00:00Z\n"
                    "u2,view,2026-01-01T00:00:01Z\n", encoding="utf-8")
    mapping = {"field_mapping": {"event_name": "event_type", "ts": "timestamp"}}

    def ids():
        out = srv.apply_mapping(str(path), mapping)
        records = out.get("_records_internal") or out["sample_output"]
        return [r["event_id"] for r in records]

    first = ids()
    assert first == ids() and len(set(first)) == 3           # stable; identical rows still get distinct ids


def test_friction_scores_are_deterministic_on_rerun(high_step, low_step):
    from mcp_servers.friction_engine_server import score_all_steps

    assert score_all_steps([high_step, low_step]) == score_all_steps([high_step, low_step])


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Settings (design §7)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_workflow_settings(tmp_path):
    from settings import ConfigError, load_settings

    s = load_settings({"CJI_ENV": "test"}, dotenv_path=None)
    assert (s.workflow.step_timeout_s, s.workflow.step_attempts, s.workflow.retry_backoff_s) == (900.0, 2, 5.0)
    assert s.storage.checkpoints_db == s.storage.data_dir / "cji_checkpoints.db"
    custom = load_settings({"CJI_ENV": "test", "CJI_CHECKPOINTS_DB": str(tmp_path / "cp.db")}, dotenv_path=None)
    assert custom.storage.checkpoints_db == tmp_path / "cp.db"
    with pytest.raises(ConfigError, match="CJI_WORKFLOW_STEP_TIMEOUT_S"):
        load_settings({"CJI_ENV": "test", "CJI_WORKFLOW_STEP_TIMEOUT_S": "60"}, dotenv_path=None)
    with pytest.raises(ConfigError, match="CJI_WORKFLOW_STEP_ATTEMPTS"):
        load_settings({"CJI_ENV": "test", "CJI_WORKFLOW_STEP_ATTEMPTS": "9"}, dotenv_path=None)
