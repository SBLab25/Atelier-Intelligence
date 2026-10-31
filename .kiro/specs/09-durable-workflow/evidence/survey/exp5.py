"""Spec 09 experiment 5: does interrupt_after every worker make each step durable on LangGraph 0.2.28?"""
import asyncio
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, r"C:\Users\sovan\.kiro")
import s09_exp as E  # noqa: E402  (reuses stubs; its main block runs only for ROLE=main, so pass a role)

LOG = r"C:\Users\sovan\.kiro\s09_exp5.txt"
WORKERS = ["ingestion_worker", "data_worker", "friction_worker", "insight_worker", "report_worker"]


def log(*a):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


async def drive(graph, cfg, first_input):
    """Run step by step: every interrupt exits the loop, which waits for the pending checkpoint write."""
    inp = first_input
    while True:
        async for _ in graph.astream(inp, config=cfg, stream_mode="values"):
            pass
        inp = None
        snap = await graph.aget_state(cfg)
        if not snap.next:
            return snap


def slow_data(state):
    time.sleep(0)          # no delay: worst case for background checkpoint writes
    return E.ok_data(state)


async def child(db):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    base = E.build(slow_data, E.die)
    cfg = {"configurable": {"thread_id": "exp5"}, "recursion_limit": 100}
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        await drive(base.compile(checkpointer=cp, interrupt_after=WORKERS), cfg, E.initial(True))


async def resume(db):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    E.calls.clear()
    base = E.build(E.ok_data)
    cfg = {"configurable": {"thread_id": "exp5"}, "recursion_limit": 100}
    async with AsyncSqliteSaver.from_conn_string(db) as cp:
        g = base.compile(checkpointer=cp, interrupt_after=WORKERS)
        snap = await g.aget_state(cfg)
        log("exp5 after kill: next", snap.next, "| has event_summary", bool(snap.values.get("event_summary")),
            "| iteration", snap.values.get("iteration"))
        snap = await drive(g, cfg, None)
        log("exp5 resume: calls", E.calls, "| report", repr(snap.values.get("report_path")))


if __name__ == "__main__":
    if sys.argv[1:2] == ["c5"]:
        asyncio.run(child(sys.argv[2]))
        sys.exit(0)
    open(LOG, "w", encoding="utf-8").close()
    for trial in range(3):
        db = os.path.join(tempfile.mkdtemp(), "cp.db")
        rc = subprocess.run([sys.executable, __file__, "c5", db], capture_output=True, text=True).returncode
        log(f"trial {trial}: child exit", rc)
        asyncio.run(resume(db))
    log("done")
