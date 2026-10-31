"""
CJI Supervisor (Synchronous)
=============================
The supervisor node and route function for LangGraph conditional edges.

CRITICAL RULES:
  1. Both `supervisor()` and `route()` MUST be plain `def` — NOT `async def`.
     LangGraph uses sync functions for routing decisions.
  2. The route() function returns a STRING matching a node name or "__end__".
  3. MAX_AGENT_ITERATIONS is imported from config.py as a safety cutoff.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from cji.config import MAX_AGENT_ITERATIONS
from cji.domain.runs import STOPPED_STATUSES, VALID_WORKERS, workflow_error

logger = logging.getLogger("cji.supervisor")

# VALID_WORKERS (every target route() may return) is defined in domain/runs.py
# and re-exported here; it must equal graph.py's conditional edge map.
__all__ = ["VALID_WORKERS", "route", "supervisor"]


def _run(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("run") or {}


def _step_done(state: dict[str, Any], worker: str) -> bool:
    """A worker finished in this run (Spec 09 run record)."""
    return ((_run(state).get("steps") or {}).get(worker) or {}).get("status") in ("succeeded", "skipped")


def _next_status(state: dict[str, Any]) -> str | None:
    """Run status after the last worker (Spec 09): approval gate after insights, completed after the report."""
    status = _run(state).get("status")
    if status == "running" and _step_done(state, "insight_worker"):
        return "approved" if state.get("human_approved", False) else "awaiting_approval"
    if status == "approved" and _step_done(state, "report_worker"):
        return "completed"
    return None


def supervisor(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Increments the iteration counter, records the run timestamp and moves the run record
    to its next status (Spec 09). Guards against infinite loops via MAX_AGENT_ITERATIONS:
    the cutoff fails the run with code iteration_limit.

    Returns a partial state dict that merges into CJIState.
    """
    iteration = state.get("iteration", 0) + 1
    now = datetime.now(timezone.utc).isoformat()
    run = _run(state)

    logger.info(f"Supervisor iteration {iteration} at {now}")

    if iteration > MAX_AGENT_ITERATIONS:
        logger.warning(f"Max iterations ({MAX_AGENT_ITERATIONS}) exceeded - halting.")
        message = f"Max iterations ({MAX_AGENT_ITERATIONS}) exceeded"
        out: dict[str, Any] = {
            "iteration":   iteration,
            "last_run_at": now,
            "next_worker": "__end__",
            "errors": [workflow_error("supervisor", message)],
        }
        if run.get("status") in ("running", "approved"):
            out["run"] = {"status": "failed", "updated_at": now, "failure": {
                "step_id": f"{run.get('run_id')}:supervisor:{iteration}", "worker": "supervisor",
                "code": "iteration_limit", "message": message, "retryable": False, "attempts": iteration - 1}}
        return out

    out = {"iteration": iteration, "last_run_at": now}
    status = _next_status(state)
    if status:
        logger.info(f"Run status -> {status}")
        out["run"] = {"status": status, "updated_at": now}
    return out


def route(state: Dict[str, Any]) -> str:
    """
    Conditional edge function for LangGraph.

    Routing order (first match wins):
      1. No event_summary        → data_worker
      2. No friction_scores      → friction_worker
      3. No insights             → insight_worker
      4. insights + not approved → __end__ (PAUSE for human approval)
      5. approved + no report    → report_worker
      6. Otherwise               → __end__ (COMPLETE)
    """
    # Stopped runs (Spec 09): failed, paused for approval, or completed
    if _run(state).get("status") in STOPPED_STATUSES:
        return "__end__"

    # Safety cutoff check
    if state.get("next_worker") == "__end__":
        return "__end__"

    event_summary = state.get("event_summary", {})
    friction_scores = state.get("friction_scores", [])
    insights = state.get("insights", [])
    human_approved = state.get("human_approved", False)
    report_path = state.get("report_path", "")

    # Helper to check if a worker has run: the run record when there is one (Spec 09: a failed step
    # reset to pending by --resume runs again), else any status entry (states without a run record).
    worker_statuses = state.get("worker_statuses", [])
    def has_run(worker_name: str) -> bool:
        if _run(state):
            return _step_done(state, worker_name)
        return any(s.get("worker") == worker_name for s in worker_statuses)

    # 0. Ingestion phase
    if state.get("ingestion_pending_files") and not state.get("ingestion_results"):
        logger.info("Route → ingestion_worker (files pending)")
        return "ingestion_worker"

    # 1. Data phase
    if not event_summary and not has_run("data_worker"):
        logger.info("Route → data_worker (no event_summary)")
        return "data_worker"

    # 2. Friction phase
    if not friction_scores and not has_run("friction_worker"):
        logger.info("Route → friction_worker (no friction_scores)")
        return "friction_worker"

    # 3. Insight phase
    if not insights and not has_run("insight_worker"):
        logger.info("Route → insight_worker (no insights)")
        return "insight_worker"

    # 4. Human approval gate
    if not human_approved:
        logger.info("Route → __end__ (PAUSE — awaiting human approval)")
        return "__end__"

    # 5. Report phase
    if not report_path and not has_run("report_worker"):
        logger.info("Route → report_worker (approved, generating report)")
        return "report_worker"

    # 6. All done
    logger.info("Route → __end__ (COMPLETE)")
    return "__end__"
