"""Request and response models of /api/v1 (Spec 12, design §4). Field names are part of the contract."""
from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from cji.domain.metrics import FrictionScore, FunnelStep, StepMetrics

T = TypeVar("T")
RunStatus = Literal["running", "awaiting_approval", "approved", "completed", "failed"]


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageInfo(_Out):
    limit: int = Field(ge=1, le=200)
    next_cursor: str | None = Field(description="Pass as `cursor` to get the next page; null on the last page")


class Page(_Out, Generic[T]):  # noqa: UP046 - pydantic generic model
    data: list[T]
    page: PageInfo


class Health(_Out):
    status: Literal["ok"]
    version: str
    mode: Literal["demo", "realtime"]


class Component(_Out):
    name: Literal["repository", "checkpoints", "reports"]
    status: Literal["ok", "unavailable"]
    code: str | None = Field(description="Problem code when unavailable")


class HealthDetails(_Out):
    status: Literal["ok", "degraded"]
    version: str
    mode: Literal["demo", "realtime"]
    components: list[Component]


class Me(_Out):
    token_id: str
    label: str
    role: Literal["viewer", "operator", "admin"]
    journeys: list[str]


class Journey(_Out):
    journey_id: str
    steps: list[str] = Field(max_length=64)
    mode: Literal["demo", "realtime"]


class Event(_Out):
    event_id: str
    user_id: str | None
    session_id: str | None
    step_id: str | None
    event_type: str | None
    timestamp: str = Field(description="RFC 3339, UTC")
    duration_ms: int | None
    url: str | None


class Window(_Out):
    days: int | None
    minutes: int | None


class Metrics(_Out):
    journey_id: str
    window: Window
    steps: list[StepMetrics]
    funnel: list[FunnelStep]
    overall_completion_pct: float


class Friction(_Out):
    journey_id: str
    window: Window
    threshold: int
    scores: list[FrictionScore]
    critical_steps: list[str]


class Insight(BaseModel):
    """An insight as stored in the run (fields beyond the required ones may be absent in older runs)."""

    model_config = ConfigDict(extra="ignore")

    insight_id: str
    step_id: str
    title: str
    root_cause: str | None = None
    category: str | None = None
    evidence: list[str] = Field(default_factory=list)
    suggested_fix: str | None = None
    fix_effort: str | None = None
    priority: int | None = None
    priority_score: float | None = None
    score: int | None = None


class Insights(_Out):
    journey_id: str
    run_id: str | None
    insights: list[Insight]


class Report(_Out):
    report_id: str
    run_id: str | None
    journey_id: str | None
    size_bytes: int
    created_at: str
    content_url: str


class Step(_Out):
    status: str | None = None
    attempts: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    code: str | None = None


class Failure(_Out):
    worker: str
    code: str
    message: str
    retryable: bool
    attempts: int


class RunSummary(_Out):
    run_id: str
    journey_id: str
    mode: str
    status: RunStatus
    created_at: str
    updated_at: str
    report_id: str | None


class Run(RunSummary):
    human_approved: bool
    active: bool = Field(description="A process currently holds the run")
    steps: dict[str, Step]
    failure: Failure | None
    insight_count: int
    errors_total: int


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=500, description="Recorded in the server log only")


class Approval(_Out):
    run: Run
    already_approved: bool
