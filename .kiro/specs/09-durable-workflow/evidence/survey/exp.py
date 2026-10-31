"""Spec 09 survey experiments (in-process, stub workers, in-memory or temp-file checkpoints)."""
import asyncio
import os
import subprocess
import sys
import tempfile
import traceback

APP = r"c:\Users\sovan\Documents\Projects\TCS-CJI\cji_agent"
sys.path.insert(0, APP)
os.chdir(APP)
os.environ.setdefault("CJI_ENV", "test")
LOG = r"C:\Users\sovan\.kiro\s09_exp.txt"
ROLE = sys.argv[1] if len(sys.argv) > 1 else "main"
if ROLE == "main" and __name__ == "__main__":
    open(LOG, "w", encoding="utf-8").close()


def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


import agents.workers as W  # noqa: E402
from integrations.context import with_run  # noqa: E402

calls = []


def stub(name, result_fn):
    @with_run(name)
    async def node(state):
        calls.append(name)
        return result_fn(state)
    node.__name__ = name
    return node


def ok_data(state):
    return {"event_summary": {"step_metrics": [{"step_id": "s1"}], "funnel": []}, "next_worker": "supervisor",
            "worker_statuses": [{"worker": "data_worker", "status": "success", "message": "ok"}]}


def fail_data(state):
    return {"event_summary": {}, "next_worker": "supervisor",
            "worker_statuses": [{"worker": "data_worker", "status": "error", "message": "boom"}],
            "errors": [{"worker": "data_worker", "error": "boom", "ts": "t"}]}


def friction(state):
    if not state.get("event_summary", {}).get("step_metrics"):
        return {"friction_scores": [], "next_worker": "supervisor",
                "worker_statuses": [{"worker": "friction_worker", "status": "error", "message": "no metrics"}],
                "errors": [{"worker": "friction_worker", "error": "No step_metrics", "ts": "t"}]}
    return {"friction_scores": [{"step_id": "s1", "score": 80, "is_critical": True}], "next_worker": "supervisor",
            "worker_statuses": [{"worker": "friction_worker", "status": "success", "message": "ok"}]}


def die(state):
    log("exp4 child: friction_worker started; killing the process")
    os._exit(9)


def insight(state):
    return {"insights": [{"step_id": "s1", "title": "T"}], "next_worker": "supervisor",
            "worker_statuses": [{"worker": "insight_worker", "status": "success", "message": "ok"}]}


def report(state):
    return {"report_path": "/tmp/r.html", "next_worker": "supervisor",
            "worker_statuses": [{"worker": "report_worker", "status": "success", "message": "ok"}]}


def initial(approved=False):
    return {"mode": "demo", "journey_name": "j", "journey_steps": ["s1"], "analysis_window_days": 30,
            "analysis_window_mins": 60, "collector_url": "", "iteration": 0, "next_worker": "supervisor",
            "human_approved": approved, "last_run_at": "", "messages": [], "ingestion_pending_files": [],
            "ingestion_results": [], "ingestion_pending_review": [], "raw_events": [], "event_summary": {},
            "live_event_count": 0, "friction_scores": [], "critical_steps": [], "insights": [],
            "prioritized_fixes": [], "report_path": "", "narrative": "", "llm_usage": {},
            "worker_statuses": [], "errors": []}


def build(data_fn, friction_fn=friction):
    W.data_worker = stub("data_worker", data_fn)
    W.friction_worker = stub("friction_worker", friction_fn)
    W.insight_worker = stub("insight_worker", insight)
    W.report_worker = stub("report_worker", report)
    sys.modules.pop("graph", None)
    import graph
    return graph.build_graph()


def exp0():
    from agents.workers import _error_text
    from integrations import ToolFailed
    try:
        log("exp0 _error_text(ToolFailed) ->", _error_text(ToolFailed("MCP tool 't' failed (tool_failed)")))
    except RecursionError:
        log("exp0 _error_text(ToolFailed) -> RecursionError")


async def exp1():
    from langgraph.checkpoint.memory import MemorySaver
    calls.clear()
    g = build(fail_data).compile(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "exp1"}, "recursion_limit": 100}
    final = await g.ainvoke(initial(True), cfg)
    log("exp1 data fails: worker calls", len(calls), calls[:6], "...")
    log("exp1 iteration", final["iteration"], "| errors kept", len(final["errors"]), final["errors"])
    log("exp1 worker_statuses kept", len(final["worker_statuses"]))


async def exp2():
    """main.py without --auto-approve, then --approve (AsyncSqliteSaver on a temp file, as main.py does)."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    calls.clear()
    base = build(ok_data)
    db = os.path.join(tempfile.mkdtemp(), "cp.db")
    cfg = {"configurable": {"thread_id": "exp2"}, "recursion_limit": 100}
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        g = base.compile(checkpointer=cp, interrupt_before=["report_worker"])
        async for ev in g.astream(initial(False), config=cfg, stream_mode="values"):
            if ev.get("insights") and not ev.get("human_approved") and not ev.get("report_path"):
                break                                     # main.py breaks here
        snap = await g.aget_state(cfg)
        log("exp2 run: calls", calls, "| next", snap.next, "| iteration", snap.values.get("iteration"))
    for attempt in (1, 2):
        calls.clear()
        async with AsyncSqliteSaver.from_conn_string(db) as cp:
            g = base.compile(checkpointer=cp, interrupt_before=["report_worker"])
            await g.aupdate_state(cfg, {"human_approved": True})
            snap = await g.aget_state(cfg)
            nxt = snap.next
            async for _ in g.astream(None, config=cfg, stream_mode="values"):
                pass
            snap = await g.aget_state(cfg)
            log(f"exp2 approve #{attempt}: next after update", nxt, "| calls", calls,
                "| report_path", repr(snap.values.get("report_path")), "| next", snap.next)


async def exp3():
    from langgraph.checkpoint.memory import MemorySaver
    calls.clear()
    g = build(ok_data).compile(checkpointer=MemorySaver(), interrupt_before=["report_worker"])
    cfg = {"configurable": {"thread_id": "never-ran"}, "recursion_limit": 100}
    try:
        await g.aupdate_state(cfg, {"human_approved": True})
        async for _ in g.astream(None, config=cfg, stream_mode="values"):
            pass
        snap = await g.aget_state(cfg)
        log("exp3 approve unknown thread: calls", calls, "| state keys", sorted(snap.values))
    except Exception as exc:
        log("exp3 approve unknown thread raised", type(exc).__name__, str(exc)[:200])


async def exp4_child(db):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    base = build(ok_data, die)
    cfg = {"configurable": {"thread_id": "exp4"}, "recursion_limit": 100}
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        await base.compile(checkpointer=cp).ainvoke(initial(True), cfg)


async def exp4_resume(db):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    calls.clear()
    base = build(ok_data)
    cfg = {"configurable": {"thread_id": "exp4"}, "recursion_limit": 100}
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        g = base.compile(checkpointer=cp)
        snap = await g.aget_state(cfg)
        log("exp4 after kill: next", snap.next, "| has event_summary", bool(snap.values.get("event_summary")),
            "| iteration", snap.values.get("iteration"))
        final = await g.ainvoke(None, cfg)
        log("exp4 resume ainvoke(None): calls", calls, "| report", repr(final.get("report_path")))


if __name__ == "__main__":
    if ROLE == "child":
        asyncio.run(exp4_child(sys.argv[2]))
        sys.exit(0)

    for fn in (exp0, exp1, exp2, exp3):
        try:
            r = fn()
            if asyncio.iscoroutine(r):
                asyncio.run(r)
        except Exception:
            log(fn.__name__, "FAILED", traceback.format_exc()[-800:])
    try:
        db = os.path.join(tempfile.mkdtemp(), "cp.db")
        rc = subprocess.run([sys.executable, __file__, "child", db], capture_output=True, text=True).returncode
        log("exp4 child exit code", rc)
        asyncio.run(exp4_resume(db))
    except Exception:
        log("exp4 FAILED", traceback.format_exc()[-800:])
    log("done")
