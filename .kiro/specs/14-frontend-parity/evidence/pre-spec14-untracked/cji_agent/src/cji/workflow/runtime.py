"""
Durable driver for the CJI workflow (Spec 09, design §4). Used by `main.py --run/--approve/--resume/--status`.

- One checkpoint store: SQLite at `CJI_CHECKPOINTS_DB` (WAL, synchronous=FULL), opened here only.
- LangGraph 0.2.28 writes checkpoints in the background. The graph is therefore compiled with
  `interrupt_after` every worker and driven one worker at a time: leaving `astream` waits for the pending
  write, so each finished step is stored before the next worker starts (OD-68, survey exp5). A new run
  first stops before its first supervisor step, so the initial state (with the run record) is stored
  before any worker runs.
- One process per run: a lease row in the checkpoint database, renewed after every step (OD-77).
- Run status changes are audited (`kind=run`); step attempts are audited by `cji.workflow.step`.
- Every stored step and status change also updates the run index (`cji.workflow.index`, Spec 12, OD-115).
- `mark_approved` records an approval without running the report step (the API continues the run in the
  background with `resume`, Spec 12, OD-116).
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import socket
import sqlite3
import sys
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from cji.domain.runs import STOPPED_STATUSES, new_run_record

from .errors import LegacyRun, RunLeased, RunNotFound, RunNotResumable
from .index import RunIndex
from .step import utc_now, write_audit

logger = logging.getLogger("cji.workflow")

EventHandler = Callable[[dict[str, Any], bool], None]   # (state values, is_baseline)


@contextlib.asynccontextmanager
async def open_checkpointer(path: Path | str) -> AsyncIterator[AsyncSqliteSaver]:
    """The workflow's checkpoint store (WAL journal, full fsync on commit)."""
    db = Path(path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(db))
    try:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=FULL")
        await conn.commit()
        yield AsyncSqliteSaver(conn)
    finally:
        await conn.close()


def _pid_alive(pid: int) -> bool:
    """Whether a process with this id exists on this machine (never sends a signal)."""
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259                              # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def owner_id() -> str:
    """Lease owner: host, process id and a random suffix (one per Workflow)."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def owner_is_dead(owner: str) -> bool:
    """True only for an owner on this host whose process no longer exists (a crashed run)."""
    parts = owner.split(":")
    if len(parts) != 3 or parts[0] != socket.gethostname() or not parts[1].isdigit():
        return False
    return not _pid_alive(int(parts[1]))


class Lease:
    """
    One live owner per run, stored next to the checkpoints (table run_leases). A lease is free when it
    expired or when its owner is a process on this machine that no longer exists (crash, kill).
    """

    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.execute("CREATE TABLE IF NOT EXISTS run_leases "
                     "(run_id TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL)")
        return conn

    def acquire(self, run_id: str, owner: str, ttl_s: float) -> None:
        """Take or renew the lease; RunLeased if another owner holds an unexpired one."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT owner, expires_at FROM run_leases WHERE run_id = ?", (run_id,)).fetchone()
            now = time.time()
            if row and row[0] != owner and row[1] > now and not owner_is_dead(row[0]):
                conn.execute("ROLLBACK")
                raise RunLeased(f"run {run_id} is active in process {row[0]} (lease expires in "
                                f"{row[1] - now:.0f}s); wait for it to finish or stop it first")
            conn.execute("INSERT INTO run_leases (run_id, owner, expires_at) VALUES (?, ?, ?) "
                         "ON CONFLICT(run_id) DO UPDATE SET owner = excluded.owner, expires_at = excluded.expires_at",
                         (run_id, owner, now + ttl_s))
            conn.execute("COMMIT")
        finally:
            conn.close()

    def release(self, run_id: str, owner: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM run_leases WHERE run_id = ? AND owner = ?", (run_id, owner))
        finally:
            conn.close()

    def holder(self, run_id: str) -> str | None:
        """The owner of an unexpired lease, else None."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT owner, expires_at FROM run_leases WHERE run_id = ?", (run_id,)).fetchone()
        finally:
            conn.close()
        return row[0] if row and row[1] > time.time() and not owner_is_dead(row[0]) else None


@dataclass
class RunOutcome:
    run_id: str
    status: str | None
    values: dict[str, Any]
    already: bool = False           # approve of a run that was approved before: nothing ran

    @property
    def report_path(self) -> str:
        return str(self.values.get("report_path") or "")

    @property
    def failure(self) -> dict[str, Any] | None:
        return (self.values.get("run") or {}).get("failure")


def initial_state(
    *,
    mode: str,
    journey_name: str,
    journey_steps: list[str],
    auto_approve: bool,
    window_days: int = 30,
    window_mins: int = 60,
    collector_url: str = "",
    pending_files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Every CJIState key except `run` (added by Workflow.start)."""
    return {
        "mode": mode, "journey_name": journey_name, "journey_steps": list(journey_steps),
        "analysis_window_days": window_days, "analysis_window_mins": window_mins, "collector_url": collector_url,
        "iteration": 0, "next_worker": "supervisor", "human_approved": auto_approve, "last_run_at": "",
        "messages": [HumanMessage(content=f"Analyse {mode} journey")],
        "ingestion_pending_files": list(pending_files or []), "ingestion_results": [], "ingestion_pending_review": [],
        "raw_events": [], "event_summary": {}, "live_event_count": 0, "friction_scores": [], "critical_steps": [],
        "insights": [], "prioritized_fixes": [], "report_path": "", "narrative": "", "llm_usage": {},
        "worker_statuses": [], "errors": [],
    }


def write_last_run(path: Path, values: dict[str, Any], *, mode: str, journey_name: str) -> Path:
    """`data/last_run.json` for the dashboard (same keys as before Spec 09), written atomically."""
    from datetime import datetime

    data = {
        "timestamp": datetime.now().isoformat(), "mode": mode, "journey_name": journey_name,
        "report_path": values.get("report_path") or "", "narrative": values.get("narrative", ""),
        "friction_scores": values.get("friction_scores", []), "critical_steps": values.get("critical_steps", []),
        "insights": values.get("insights", []), "prioritized_fixes": values.get("prioritized_fixes", []),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return path


def _only_input_stored(snap: Any) -> bool:
    """The thread has only its input checkpoint (the process died before the first step was stored)."""
    metadata = getattr(snap, "metadata", None) or {}
    return metadata.get("source") == "input" and bool(snap.next)


def _done(run: dict[str, Any], worker: str) -> bool:
    return ((run.get("steps") or {}).get(worker) or {}).get("status") in ("succeeded", "skipped")


class Workflow:
    """Start, approve, resume and inspect runs. `graph` is an uncompiled StateGraph (default: build_graph())."""

    def __init__(self, db_path: Path | str | None = None, *, graph: Any = None, owner: str | None = None,
                 on_event: EventHandler | None = None) -> None:
        from cji.settings import get_settings

        settings = get_settings()
        self.db_path = Path(db_path) if db_path is not None else settings.storage.checkpoints_db
        self._graph = graph
        self.owner = owner or owner_id()
        self.on_event = on_event

    # ── plumbing ──────────────────────────────────────────────────────────────────────────────────────
    def _base(self) -> Any:
        if self._graph is None:
            from cji.graph import build_graph

            self._graph = build_graph()
        return self._graph

    @staticmethod
    def _config(run_id: str) -> dict[str, Any]:
        from cji.settings import get_settings

        return {"configurable": {"thread_id": run_id}, "recursion_limit": get_settings().budgets.recursion_limit}

    @staticmethod
    def _lease_s() -> float:
        from cji.settings import get_settings

        return get_settings().workflow.lease_s

    @contextlib.asynccontextmanager
    async def _graph_session(self, run_id: str, *, lease: bool) -> AsyncIterator[Any]:
        from cji.graph import WORKER_NODES

        async with open_checkpointer(self.db_path) as checkpointer:
            graph = self._base().compile(checkpointer=checkpointer, interrupt_after=list(WORKER_NODES))
            if not lease:
                yield graph
                return
            leases = Lease(self.db_path)
            leases.acquire(run_id, self.owner, self._lease_s())
            try:
                yield graph
            finally:
                leases.release(run_id, self.owner)

    def _record(self, run_id: str, values: dict[str, Any]) -> None:
        """Update the run index; an index failure never stops the workflow (the checkpoint is the truth)."""
        try:
            RunIndex(self.db_path).record(run_id, values)
        except sqlite3.Error as exc:
            logger.warning("run index update failed for %s: %s", run_id, type(exc).__name__)

    def _audit_run(self, run_id: str, old: str | None, new: str | None, code: str | None = None) -> None:
        if new is None or old == new:
            return
        write_audit(kind="run", correlation_id=run_id, run_id=run_id, from_status=old, to_status=new, code=code)

    async def _load(self, graph: Any, run_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
        snap = await graph.aget_state(self._config(run_id))
        values = dict(snap.values or {})
        run = values.get("run")
        if not run and _only_input_stored(snap):
            # Killed before the first step was stored: only the input is saved; resuming applies it.
            return snap, values, {"run_id": run_id, "status": "running", "steps": {}}
        if not values:
            raise RunNotFound(f"run {run_id} not found in {self.db_path}")
        if not run:
            raise LegacyRun(f"run {run_id} was created before Spec 09 (no run record); start a new run")
        return snap, values, dict(run)

    async def _drive(self, graph: Any, run_id: str, first_input: dict[str, Any] | None, status: str | None,
                     baseline: dict[str, Any]) -> RunOutcome:
        config = self._config(run_id)
        leases = Lease(self.db_path)
        if self.on_event:
            self.on_event(baseline, True)
        payload = first_input
        if payload is not None:
            # Store the initial state before any worker runs (stop before the first supervisor step).
            async for _ in graph.astream(payload, config=config, stream_mode="values",
                                         interrupt_before=["supervisor"]):
                pass
            payload = None
        while True:
            async for values in graph.astream(payload, config=config, stream_mode="values"):
                if self.on_event:
                    self.on_event(values, False)
            payload = None
            snap = await graph.aget_state(config)
            values = dict(snap.values or {})
            run = values.get("run") or {}
            new = run.get("status")
            self._audit_run(run_id, status, new, ((run.get("failure") or {}).get("code") if new == "failed" else None))
            self._record(run_id, values)
            status = new
            leases.acquire(run_id, self.owner, self._lease_s())          # renew after every step
            if not snap.next or status in STOPPED_STATUSES:
                return RunOutcome(run_id, status, values)

    # ── public API ────────────────────────────────────────────────────────────────────────────────────
    async def start(self, state: dict[str, Any], *, run_id: str | None = None) -> RunOutcome:
        run_id = run_id or str(uuid.uuid4())
        async with self._graph_session(run_id, lease=True) as graph:
            snap = await graph.aget_state(self._config(run_id))
            if snap.values:
                raise RunNotResumable(f"run {run_id} already exists; use --resume or --approve")
            initial = {**state, "run": new_run_record(run_id)}
            self._audit_run(run_id, None, "running")
            self._record(run_id, initial)
            return await self._drive(graph, run_id, initial, "running", {})

    async def approve(self, run_id: str) -> RunOutcome:
        async with self._graph_session(run_id, lease=True) as graph:
            _snap, values, run = await self._load(graph, run_id)
            status = run.get("status")
            if status in ("approved", "completed"):
                return RunOutcome(run_id, status, values, already=True)
            if status != "awaiting_approval":
                hint = " Use --resume to continue it." if status in ("failed", "running") else ""
                raise RunNotResumable(f"run {run_id} is {status}; only a run awaiting approval can be approved.{hint}")
            await graph.aupdate_state(self._config(run_id), {"human_approved": True,
                                                              "run": {"status": "approved", "updated_at": utc_now()}},
                                      as_node="supervisor")
            self._audit_run(run_id, status, "approved")
            self._record(run_id, dict((await graph.aget_state(self._config(run_id))).values or {}))
            return await self._drive(graph, run_id, None, "approved", values)

    async def mark_approved(self, run_id: str) -> RunOutcome:
        """Approve a run awaiting approval without running further steps (continue it with `resume`).
        Approved or completed runs return `already=True`; other statuses raise RunNotResumable."""
        async with self._graph_session(run_id, lease=True) as graph:
            _snap, values, run = await self._load(graph, run_id)
            status = run.get("status")
            if status in ("approved", "completed"):
                return RunOutcome(run_id, status, values, already=True)
            if status != "awaiting_approval":
                raise RunNotResumable(f"run {run_id} is {status}; only a run awaiting approval can be approved.")
            await graph.aupdate_state(self._config(run_id), {"human_approved": True,
                                                              "run": {"status": "approved", "updated_at": utc_now()}},
                                      as_node="supervisor")
            self._audit_run(run_id, status, "approved")
            after = dict((await graph.aget_state(self._config(run_id))).values or {})
            self._record(run_id, after)
            return RunOutcome(run_id, "approved", after)

    async def resume(self, run_id: str) -> RunOutcome:
        async with self._graph_session(run_id, lease=True) as graph:
            snap, values, run = await self._load(graph, run_id)
            status = run.get("status")
            if status == "completed":
                raise RunNotResumable(f"run {run_id} is completed; nothing to resume")
            if status == "awaiting_approval":
                raise RunNotResumable(f"run {run_id} is awaiting approval; use --approve")
            config = self._config(run_id)
            if status == "failed":
                failure = run.get("failure") or {}
                target = "approved" if values.get("human_approved") and _done(run, "insight_worker") else "running"
                update: dict[str, Any] = {"status": target, "failure": None, "updated_at": utc_now()}
                worker = failure.get("worker")
                if worker in (run.get("steps") or {}):
                    update["steps"] = {worker: {"status": "pending"}}
                await graph.aupdate_state(config, {"run": update}, as_node="supervisor")
                self._audit_run(run_id, status, target)
                status = target
            elif not snap.next:
                await graph.aupdate_state(config, {"run": {"updated_at": utc_now()}}, as_node="supervisor")
            return await self._drive(graph, run_id, None, status, values)

    async def status(self, run_id: str) -> dict[str, Any]:
        status, _values = await self.inspect(run_id)
        return status

    async def inspect(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        """(the `status()` dict, the run's state values). Read-only, no lease."""
        async with self._graph_session(run_id, lease=False) as graph:
            snap, values, run = await self._load(graph, run_id)
        errors = values.get("errors") or []
        return {
            "run_id": run_id, "status": run.get("status"), "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"), "human_approved": bool(values.get("human_approved")),
            "iteration": values.get("iteration", 0), "next": list(snap.next or ()),
            "steps": run.get("steps") or {}, "failure": run.get("failure"),
            "report_path": values.get("report_path") or "", "errors_total": len(errors),
            "last_errors": errors[-5:], "lease_owner": Lease(self.db_path).holder(run_id),
        }, values
