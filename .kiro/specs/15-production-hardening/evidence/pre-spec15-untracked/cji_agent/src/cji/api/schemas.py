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
    active_runs: int = Field(ge=0, description="Runs this API process is driving now (Spec 14)")


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


# ── Spec 14: run start, results with provenance, ingestion (OD-144..OD-148) ─────────────────────────────

class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journey_id: str = Field(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f/]+$")
    auto_approve: bool = Field(default=False, description="Skip the approval gate (the CLI's --auto-approve)")
    window_days: int | None = Field(default=None, ge=1, le=365, description="Demo window (default 30)")
    window_minutes: int | None = Field(default=None, ge=1, le=43200, description="Realtime window (default 60)")


class Provenance(_Out):
    source: Literal["llm", "fallback", "not_recorded"]
    model: str | None = Field(description="Model that wrote the text (LLM results only)")
    provider: str | None
    reason: str | None = Field(description="Gateway code that caused the fallback")
    generated_at: str | None


class RunInsight(Insight):
    provenance: Provenance


class Fix(BaseModel):
    model_config = ConfigDict(extra="ignore")

    insight_id: str | None = None
    step_id: str
    title: str | None = None
    suggested_fix: str | None = None
    fix_effort: str | None = None
    priority: int | None = None
    priority_score: float | None = None
    category: str | None = None
    root_cause: str | None = None


class RunFrictionScore(BaseModel):
    """A friction score as stored in the run (older runs and partial results may lack fields)."""

    model_config = ConfigDict(extra="ignore")

    step_id: str
    score: float
    is_critical: bool = False
    signals: list[str] = Field(default_factory=list)
    confidence: float | None = None
    drop_off_rate: float | None = None
    avg_dwell_ms: float | None = None
    retry_count: float | None = None
    rage_click_rate: float | None = None


class LlmUsage(_Out):
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class RunIngestionResult(_Out):
    file_name: str
    detected_source: str | None
    confidence: float | None
    records_written: int
    records_skipped: int
    status: str | None
    cached_mapping: bool


class PendingReview(_Out):
    file_name: str
    detected_source: str | None
    confidence: float | None
    flagged_at: str | None


class RunError(_Out):
    worker: str
    message: str
    ts: str | None


class RunResults(_Out):
    run_id: str
    journey_id: str
    status: RunStatus
    narrative: str | None
    narrative_provenance: Provenance
    friction_scores: list[RunFrictionScore]
    critical_steps: list[str]
    insights: list[RunInsight]
    prioritized_fixes: list[Fix]
    llm_usage: LlmUsage
    ingestion_results: list[RunIngestionResult]
    ingestion_pending_review: list[PendingReview]
    errors: list[RunError] = Field(description="Newest 50 error entries")


class IngestionRows(_Out):
    parsed: int = Field(description="Rows extracted from the file")
    accepted: int = Field(description="Rows that would be written")
    dropped_event_type: int = Field(description="Rows skipped: event type outside the CJI taxonomy")
    repaired_timestamp: int = Field(description="Rows whose unparseable timestamp would be set to the write time")


class StepCount(_Out):
    step_id: str
    rows: int
    in_journey: bool


class EventTypeCount(_Out):
    event_type: str
    rows: int


class SampleRow(_Out):
    step_id: str
    event_type: str
    timestamp: str
    duration_ms: int
    url: str


class IngestionValidation(_Out):
    validation_id: str
    filename: str
    format: str
    rows: IngestionRows
    steps_found: list[StepCount]
    journey_steps_missing: list[str]
    event_types: list[EventTypeCount]
    samples: list[SampleRow] = Field(description="Up to 5 rows, without user and session ids")
    database_configured: bool = Field(description="False: the file can be validated but not written")
    expires_at: str


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    validation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{24}$")
    write_mode: Literal["append", "replace"] = Field(description="replace needs the admin role")


class Ingestion(_Out):
    validation_id: str
    write_mode: Literal["append", "replace"]
    rows_written: int
    rows_already_stored: int
    destination: Literal["tracking_events"]
