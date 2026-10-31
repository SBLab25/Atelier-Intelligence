"""
Stub workers for the Spec 09 workflow tests.

Deterministic workers with the real `@step` wrapper. Their side effects go to a small JSON store that stands
in for ChromaDB (insights by id, upsert), the reports directory (one entry per file name) and a call log.
`FAULTS` injects exceptions in-process; `WORKFLOW_STUB_CRASH=<worker>:<before|after>` kills the process with
`os._exit(9)` before or after the worker's side effect (used in a subprocess).
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cji.domain.runs import insight_id_for
from cji.integrations.context import current_run
from cji.workflow.step import step

FAULTS: dict[str, list[BaseException]] = {}       # worker -> exceptions raised by the next calls, in order
WARNINGS: dict[str, str] = {}                     # worker -> non-fatal error entry added to a success


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"calls": [], "insights": {}, "reports": {}}

    def update(self, fn: Callable[[dict[str, Any]], None]) -> None:
        data = self.load()
        fn(data)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.path)


def _store() -> Store:
    return Store(Path(os.environ["WORKFLOW_STUB_STORE"]))


def _enter(worker: str) -> None:
    _store().update(lambda d: d["calls"].append(worker))
    queue = FAULTS.get(worker)
    if queue:
        raise queue.pop(0)
    if os.environ.get("WORKFLOW_STUB_CRASH") == f"{worker}:before":
        os._exit(9)


def _after(worker: str) -> None:
    if os.environ.get("WORKFLOW_STUB_CRASH") == f"{worker}:after":
        os._exit(9)


def _status(worker: str, message: str = "ok") -> list[dict[str, Any]]:
    return [{"worker": worker, "status": "success", "message": message}]


def _warnings(worker: str) -> dict[str, Any]:
    text = WARNINGS.get(worker)
    return {"errors": [{"worker": worker, "error": text, "ts": "2026-01-01T00:00:00+00:00"}]} if text else {}


@step("data_worker", fallback=lambda: {"event_summary": {}, "raw_events": [], "live_event_count": 0})
async def data_worker(state: dict[str, Any]) -> dict[str, Any]:
    _enter("data_worker")
    _after("data_worker")
    return {"event_summary": {"step_metrics": [{"step_id": "s1"}, {"step_id": "s2"}], "funnel": []},
            "next_worker": "supervisor", "worker_statuses": _status("data_worker"), **_warnings("data_worker")}


@step("friction_worker", fallback=lambda: {"friction_scores": [], "critical_steps": []})
async def friction_worker(state: dict[str, Any]) -> dict[str, Any]:
    _enter("friction_worker")
    _after("friction_worker")
    scores = [{"step_id": "s1", "score": 80, "is_critical": True}, {"step_id": "s2", "score": 20, "is_critical": False}]
    return {"friction_scores": scores, "critical_steps": ["s1"], "next_worker": "supervisor",
            "worker_statuses": _status("friction_worker")}


@step("insight_worker", fallback=lambda: {"insights": [], "prioritized_fixes": []})
async def insight_worker(state: dict[str, Any]) -> dict[str, Any]:
    _enter("insight_worker")
    ctx = current_run()
    run_id = ctx.correlation_id if ctx else "no-run"
    insights = [{"insight_id": insight_id_for(run_id, s["step_id"]), "step_id": s["step_id"], "title": "T"}
                for s in state.get("friction_scores", []) if s.get("is_critical")]

    def save(d: dict[str, Any]) -> None:
        for ins in insights:
            d["insights"][ins["insight_id"]] = ins           # upsert by id, like ChromaDB upsert

    _store().update(save)
    _after("insight_worker")
    return {"insights": insights, "prioritized_fixes": insights, "next_worker": "supervisor",
            "worker_statuses": _status("insight_worker")}


@step("report_worker", fallback=lambda: {"report_path": "", "narrative": ""})
async def report_worker(state: dict[str, Any]) -> dict[str, Any]:
    _enter("report_worker")
    ctx = current_run()
    name = f"cji_report_j_{ctx.correlation_id if ctx else 'x'}.html"

    def save(d: dict[str, Any]) -> None:
        d["reports"][name] = d["reports"].get(name, 0) + 1   # writes per file name (same name = overwrite)

    _store().update(save)
    _after("report_worker")
    return {"report_path": f"/reports/{name}", "narrative": "N", "next_worker": "supervisor",
            "worker_statuses": _status("report_worker")}


@step("ingestion_worker")
async def ingestion_worker(state: dict[str, Any]) -> dict[str, Any]:
    _enter("ingestion_worker")
    return {"ingestion_pending_files": [], "next_worker": "data_worker",
            "worker_statuses": [{"worker": "ingestion_worker", "status": "skipped", "message": "none"}]}


def nodes() -> dict[str, Any]:
    return {"ingestion_worker": ingestion_worker, "data_worker": data_worker, "friction_worker": friction_worker,
            "insight_worker": insight_worker, "report_worker": report_worker}


def crash_main(db: str, run_id: str) -> None:
    """Subprocess entry: start an auto-approved run that crashes where WORKFLOW_STUB_CRASH says."""
    import asyncio

    from cji.graph import build_graph
    from cji.workflow.runtime import Workflow, initial_state

    wf = Workflow(Path(db), graph=build_graph(nodes=nodes()))      # default owner: host:pid:token
    state = initial_state(mode="demo", journey_name="j", journey_steps=["s1", "s2"], auto_approve=True)
    asyncio.run(wf.start(state, run_id=run_id))
