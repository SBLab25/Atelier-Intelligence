"""
Workflow-run contracts (Spec 03, RC-07/RC-11): worker names and statuses, errors,
ingestion results and the approval state. Pure module.
"""
from datetime import UTC, datetime
from typing import Any, Literal, get_args

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


class WorkerStatus(TypedDict):
    """Status record appended by each worker after it runs."""

    worker: WorkerName
    status: WorkerStatusValue
    message: str     # human-readable summary, e.g. "Analysed 6 steps, 2 critical"


class WorkflowError(TypedDict):
    """One entry of CJIState.errors."""

    worker: ErrorSource
    error: str
    ts: str          # ISO-8601 UTC


class IngestionResult(TypedDict):
    """Result record from the Smart Ingestion Intelligence MCP (Server 0)."""

    ingest_id: str          # e.g. "ingest_20260422_143200"
    source_file: str
    detected_source: str    # e.g. "GA4 Clickstream Export"
    confidence: float       # 0.0-1.0 mapping confidence
    records_written: int
    records_skipped: int
    destination: str        # "data/events.parquet" or "supabase://live_events"
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
