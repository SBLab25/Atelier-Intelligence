"""
Workflow-run contracts (Spec 03, RC-07/RC-11): worker names and statuses, errors,
ingestion results and the approval state. Pure module.

Spec 09 adds the typed run record (`RunRecord`, `StepRecord`, `Failure`), the allowed status transitions and
the state reducer `merge_run`, which applies every status change through `transition()`.
"""
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, NotRequired, get_args

from pydantic import TypeAdapter
from typing_extensions import TypedDict

WorkerName = Literal[
    "ingestion_worker",
    "data_worker",
    "friction_worker",
    "insight_worker",
    "report_worker",
]
# Every target route() may return. Must equal graph.py's conditional edge map
# (enforced by tests/test_p0_security.py::test_u4_valid_workers_matches_graph_edges).
VALID_WORKERS: frozenset[str] = frozenset({*get_args(WorkerName), "__end__"})

WorkerStatusValue = Literal["success", "error", "skipped", "partial"]
ErrorSource = Literal[
    "supervisor",
    "ingestion_worker",
    "data_worker",
    "friction_worker",
    "insight_worker",
    "report_worker",
]

# Approval gate (semantics unchanged: CJIState.human_approved is the input).
ApprovalState = Literal["awaiting_approval", "approved"]

# Run and step lifecycle (Spec 09, OD-70 / OD-71).
RunStatus = Literal["running", "awaiting_approval", "approved", "completed", "failed"]
StepStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]
RUN_STATUSES: tuple[str, ...] = get_args(RunStatus)
RUN_TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({"running"}),
    "running": frozenset({"awaiting_approval", "approved", "failed"}),
    "awaiting_approval": frozenset({"approved"}),
    "approved": frozenset({"completed", "failed"}),
    "failed": frozenset({"running", "approved"}),        # resume (keeps an earlier approval)
    "completed": frozenset(),
}
STEP_TRANSITIONS: dict[str | None, frozenset[str]] = {
    None: frozenset({"pending", "running", "succeeded", "failed", "skipped"}),
    "pending": frozenset({"running", "succeeded", "failed", "skipped"}),
    "running": frozenset({"succeeded", "failed"}),
    "failed": frozenset({"pending", "running", "succeeded"}),
    "succeeded": frozenset(),
    "skipped": frozenset(),
}
STOPPED_STATUSES: frozenset[str] = frozenset({"awaiting_approval", "completed", "failed"})


class WorkerStatus(TypedDict):
    """Status record appended by each worker after it runs."""

    worker: WorkerName
    status: WorkerStatusValue
    message: str     # human-readable summary, e.g. "Analysed 6 steps, 2 critical"
    run_id: NotRequired[str]       # Spec 09
    step_id: NotRequired[str]
    attempts: NotRequired[int]


class WorkflowError(TypedDict):
    """One entry of CJIState.errors."""

    worker: ErrorSource
    error: str
    ts: str          # ISO-8601 UTC
    run_id: NotRequired[str]       # Spec 09
    step_id: NotRequired[str]
    code: NotRequired[str]


class StepRecord(TypedDict, total=False):
    """One worker's progress in a run (Spec 09). `step_id` = f"{run_id}:{worker}:{attempts}"."""

    worker: str
    status: StepStatus
    attempts: int
    step_id: str
    started_at: str
    finished_at: str
    code: str | None


class Failure(TypedDict):
    """Why a run stopped (Spec 09, OD-72)."""

    step_id: str
    worker: str
    code: str
    message: str
    retryable: bool
    attempts: int


class RunRecord(TypedDict, total=False):
    """The run's typed record in CJIState.run (Spec 09, OD-70)."""

    run_id: str
    status: RunStatus
    created_at: str
    updated_at: str
    steps: dict[str, StepRecord]
    failure: Failure | None


class IngestionResult(TypedDict):
    """Result record from the Smart Ingestion Intelligence MCP (Server 0)."""

    ingest_id: str          # e.g. "ingest_20260422_143200"
    source_file: str
    detected_source: str    # e.g. "GA4 Clickstream Export"
    confidence: float       # 0.0-1.0 mapping confidence
    records_written: int
    records_skipped: int
    destination: str        # Parquet path (demo) or "postgresql://tracking_events" (realtime)
    cached_mapping: bool    # True if the mapping was reused from the registry
    status: str             # "success" | "error" | "pending_review"


WORKER_STATUS: TypeAdapter[WorkerStatus] = TypeAdapter(WorkerStatus)
WORKFLOW_ERROR: TypeAdapter[WorkflowError] = TypeAdapter(WorkflowError)
WORKFLOW_ERRORS: TypeAdapter[list[WorkflowError]] = TypeAdapter(list[WorkflowError])


def workflow_error(worker: ErrorSource, error: str) -> WorkflowError:
    """Build an errors entry stamped with the current UTC time."""
    return WorkflowError(worker=worker, error=error, ts=datetime.now(UTC).isoformat())


def approval_state(state: dict[str, Any]) -> ApprovalState:
    """Describe the approval gate for a CJIState-shaped mapping."""
    return "approved" if state.get("human_approved", False) else "awaiting_approval"


class IllegalTransition(ValueError):
    """A run or step status change that the transition table does not allow."""


def transition(current: str | None, new: str) -> str:
    """The new run status, or IllegalTransition. Staying in the same status is always allowed."""
    if new not in RUN_STATUSES:
        raise IllegalTransition(f"unknown run status {new!r}")
    if current == new or new in RUN_TRANSITIONS.get(current, frozenset()):
        return new
    raise IllegalTransition(f"run status {current!r} -> {new!r} is not allowed")


def step_transition(current: str | None, new: str) -> str:
    """The new step status, or IllegalTransition (a failed step may fail again on resume)."""
    if current == new or new in STEP_TRANSITIONS.get(current, frozenset()):
        return new
    raise IllegalTransition(f"step status {current!r} -> {new!r} is not allowed")


def merge_run(current: RunRecord | None, update: RunRecord | None) -> RunRecord:
    """
    State reducer for CJIState.run: merges step records per worker and applies status changes through
    `transition()`. Other keys (failure, timestamps) are replaced. The run id never changes.
    """
    merged: dict[str, Any] = dict(current or {})
    change: dict[str, Any] = dict(update or {})
    if not change:
        return merged  # type: ignore[return-value]
    old_id, new_id = merged.get("run_id"), change.get("run_id")
    if old_id and new_id and old_id != new_id:
        raise IllegalTransition(f"run id {old_id!r} cannot change to {new_id!r}")
    steps: dict[str, Any] = dict(merged.get("steps") or {})
    for worker, record in (change.pop("steps", None) or {}).items():
        previous = steps.get(worker) or {}
        if "status" in record:
            step_transition(previous.get("status"), record["status"])
        steps[worker] = {**previous, **record}
    status = change.pop("status", None)
    merged.update(change)
    merged["steps"] = steps
    if status is not None:
        merged["status"] = transition(merged.get("status"), status)
    return merged  # type: ignore[return-value]


def new_run_record(run_id: str, now: str | None = None) -> RunRecord:
    stamp = now or datetime.now(UTC).isoformat()
    return RunRecord(run_id=run_id, status="running", created_at=stamp, updated_at=stamp, steps={}, failure=None)


def insight_id_for(run_id: str, step_id: str) -> str:
    """Stable insight id for one journey step in one run (Spec 09, OD-73): reruns upsert, never duplicate."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cji:{run_id}:{step_id}"))
