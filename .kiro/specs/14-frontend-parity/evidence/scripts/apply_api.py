"""Spec 14 API edits (design §2): schemas, problems, shared helpers, context, gate limit, routers."""
from __future__ import annotations

from edit import ROOT, apply

API = "cji_agent/src/cji/api"

# ── schemas ───────────────────────────────────────────────────────────────────────────────────────────
apply(f"{API}/schemas.py", [
    ('class HealthDetails(_Out):\n    status: Literal["ok", "degraded"]\n    version: str\n'
     '    mode: Literal["demo", "realtime"]\n    components: list[Component]\n',
     'class HealthDetails(_Out):\n    status: Literal["ok", "degraded"]\n    version: str\n'
     '    mode: Literal["demo", "realtime"]\n    components: list[Component]\n'
     '    active_runs: int = Field(ge=0, description="Runs this API process is driving now (Spec 14)")\n'),
])
schemas = ROOT / f"{API}/schemas.py"
schemas.write_text(schemas.read_text(encoding="utf-8") + '''

# ── Spec 14: run start, results with provenance, ingestion (OD-144..OD-148) ─────────────────────────────

class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journey_id: str = Field(min_length=1, max_length=128, pattern=r"^[^\\x00-\\x1f\\x7f/]+$")
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
''', encoding="utf-8", newline="\n")

# ── problems ──────────────────────────────────────────────────────────────────────────────────────────
apply(f"{API}/errors.py", [
    ('    "service_misconfigured": "Service misconfigured",\n}\n',
     '    "service_misconfigured": "Service misconfigured",\n'
     '    "run_capacity_reached": "Run capacity reached",\n'
     '    "run_not_resumable": "Run cannot be resumed",\n'
     '    "run_active": "Run is active",\n'
     '    "services_unavailable": "Analysis services unavailable",\n'
     '    "ingestion_unreadable": "File not readable",\n'
     '    "validation_not_found": "Validation not found",\n'
     '    "validation_used": "Validation already used",\n'
     '    "database_unavailable": "Database unavailable",\n}\n'),
    ('    "service_misconfigured": "The service configuration is incomplete; contact the operator.",\n}\n',
     '    "service_misconfigured": "The service configuration is incomplete; contact the operator.",\n'
     '    "run_capacity_reached": "This API process is already running the maximum number of runs; retry later.",\n'
     '    "run_not_resumable": "Only a failed run, or a run no process is working on, can be resumed.",\n'
     '    "run_active": "A process is working on this run; wait for it to finish.",\n'
     '    "services_unavailable": "The analysis services (MCP servers) are not reachable; start them and retry.",\n'
     '    "ingestion_unreadable": "No records could be read from the file; check its format.",\n'
     '    "validation_not_found": "No validation with this id for your token, or it expired; validate the file again.",\n'
     '    "validation_used": "This validation was already written.",\n'
     '    "database_unavailable": "No event database is configured or reachable for writing.",\n}\n'),
])

# ── shared helpers ────────────────────────────────────────────────────────────────────────────────────
apply(f"{API}/routes/_deps.py", [
    ('from collections.abc import Callable\nfrom typing import Annotated, Any\n\n'
     'from fastapi import Depends, Path, Query, Request\nfrom fastapi.exceptions import RequestValidationError\n',
     'import re\nfrom collections.abc import Callable\nfrom typing import Annotated, Any, TypeVar\n\n'
     'from fastapi import Depends, Path, Query, Request\nfrom fastapi.exceptions import RequestValidationError\n'
     'from pydantic import BaseModel, ValidationError\n'),
    ('DEFAULT_PAGE = DEFAULT_LIMIT\n',
     'DEFAULT_PAGE = DEFAULT_LIMIT\nIDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9._-]{8,64}")\n'
     'JSON_TYPES = ("application/json",)\nM = TypeVar("M", bound=BaseModel)\n'),
])
deps = ROOT / f"{API}/routes/_deps.py"
deps.write_text(deps.read_text(encoding="utf-8") + '''

def check_idempotency_key(key: str | None) -> str:
    """The Idempotency-Key rules of every POST (Spec 12, OD-117)."""
    if key is None or key == "":
        raise ApiError(400, "idempotency_key_required")
    if not IDEMPOTENCY_KEY.fullmatch(key):
        raise ApiError(400, "idempotency_key_invalid")
    return key


def json_body(request: Request, raw: bytes, model: type[M]) -> M:
    """Parse a JSON body read by the route (after the key check); 415 for other media types."""
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media not in JSON_TYPES and not media.endswith("+json"):
        raise ApiError(415, "unsupported_media_type")
    try:
        return model.model_validate_json(raw)
    except ValidationError as exc:
        raise RequestValidationError([
            {"type": e["type"], "loc": ("body", *e["loc"]), "msg": e["msg"]}
            for e in exc.errors(include_input=False, include_url=False)[:20]
        ]) from None
''', encoding="utf-8", newline="\n")

# ── OpenAPI components for bodies parsed by the routes ────────────────────────────────────────────────
apply(f"{API}/openapi.py", [
    ('from .schemas import ApprovalRequest\n', 'from .schemas import ApprovalRequest, IngestionRequest, StartRunRequest\n'),
    ('    for model in (Problem, FieldError, ApprovalRequest):\n',
     '    for model in (Problem, FieldError, ApprovalRequest, StartRunRequest, IngestionRequest):\n'),
    ('- `ApprovalRequest` is a component because the approval body is parsed by the route (to check the\n'
     '  Idempotency-Key and the content type first).\n',
     '- `ApprovalRequest`, `StartRunRequest` and `IngestionRequest` are components because their bodies are parsed by\n'
     '  the routes (to check the Idempotency-Key and the content type first).\n'),
])

# ── context, write-operation switch, upload limit ─────────────────────────────────────────────────────
apply(f"{API}/app.py", [
    ('    tasks: set[asyncio.Task[Any]] = field(default_factory=set)\n',
     '    tasks: set[asyncio.Task[Any]] = field(default_factory=set)\n'
     '    active_runs: set[str] = field(default_factory=set)              # Spec 14: runs driven by this process\n'
     '    preflight: Callable[[], Awaitable[None]] | None = None          # MCP check before start/resume\n'
     '    ingestion_engine: Callable[[], Any] | None = None              # tests: engine for ingestion writes\n'),
    ('from collections.abc import AsyncIterator, Callable\n',
     'from collections.abc import AsyncIterator, Awaitable, Callable\n'),
    ('def create_app(settings: Settings | None = None, *, workflow_factory: WorkflowFactory | None = None,\n'
     '               repository: EventRepository | None = None) -> FastAPI:\n',
     'def create_app(settings: Settings | None = None, *, workflow_factory: WorkflowFactory | None = None,\n'
     '               repository: EventRepository | None = None,\n'
     '               preflight: Callable[[], Awaitable[None]] | None = None,\n'
     '               ingestion_engine: Callable[[], Any] | None = None) -> FastAPI:\n'),
    ('            state["ctx"] = build_context(settings or get_settings(), workflow_factory, repository)\n',
     '            state["ctx"] = build_context(settings or get_settings(), workflow_factory, repository)\n'
     '            state["ctx"].preflight = preflight\n'
     '            state["ctx"].ingestion_engine = ingestion_engine\n'),
    ('            ctx.idempotency.purge()\n',
     '            ctx.idempotency.purge()\n'
     '            from cji.services.ingestion import UploadStore\n\n'
     '            UploadStore(ctx.settings.storage.data_dir / "ingestion_uploads").purge()\n'),
    ('    from .routes import router\n\n    app.include_router(router)\n',
     '    from .routes import router, write_router\n\n    app.include_router(router)\n'
     '    if (settings or get_settings()).api.write_operations:          # rollback switch (Spec 14, OD-155)\n'
     '        app.include_router(write_router)\n'),
])
apply(f"{API}/middleware.py", [
    ('2. body limit (16 KiB, 413);\n',
     '2. body limit (16 KiB, 413; the ingestion upload path uses CJI_API_MAX_UPLOAD_BYTES, Spec 14);\n'),
    ('PUBLIC_PATHS = frozenset(', 'UPLOAD_PATHS = frozenset({f"{API_PREFIX}/ingestions/validations"})\nPUBLIC_PATHS = frozenset('),
    ('        try:\n            declared = headers.get("content-length")\n'
     '            if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:\n'
     '                await reply(413, "request_too_large")\n                return\n'
     '            ctx = self.context()\n            path = scope.get("path", "")\n',
     '        try:\n            ctx = self.context()\n            path = scope.get("path", "")\n'
     '            limit = ctx.settings.api.max_upload_bytes if path in UPLOAD_PATHS else MAX_BODY_BYTES\n'
     '            declared = headers.get("content-length")\n'
     '            if declared is not None and declared.isdigit() and int(declared) > limit:\n'
     '                await reply(413, "request_too_large")\n                return\n'),
    ('                    if received > MAX_BODY_BYTES:\n', '                    if received > limit:\n'),
])
apply(f"{API}/routes/__init__.py", [
    ('from . import health, journeys, reports, runs\n', 'from . import health, ingestions, journeys, reports, runs\n'),
    ('for _module in (health, journeys, reports, runs):\n    router.include_router(_module.router)\n\n'
     '__all__ = ["router"]\n',
     'for _module in (health, journeys, reports, runs):\n    router.include_router(_module.router)\n\n'
     '# Write operations of Spec 14 (start, resume, ingestion): mounted unless CJI_API_WRITE_OPERATIONS=false.\n'
     'write_router = APIRouter(prefix=API_PREFIX)\n'
     'write_router.include_router(runs.write_router)\nwrite_router.include_router(ingestions.router)\n\n'
     '__all__ = ["router", "write_router"]\n'),
])

# ── health: active runs ───────────────────────────────────────────────────────────────────────────────
apply(f"{API}/routes/health.py", [
    ('    return HealthDetails(status=status, version=_version(), mode=ctx.settings.app.mode, components=components)\n',
     '    return HealthDetails(status=status, version=_version(), mode=ctx.settings.app.mode, components=components,\n'
     '                         active_runs=len(ctx.active_runs))\n'),
])

# ── reports: download disposition (OD-149) ────────────────────────────────────────────────────────────
apply(f"{API}/routes/reports.py", [
    ('import logging\nfrom typing import Annotated, Any\n', 'import logging\nimport re\nfrom typing import Annotated, Any, Literal\n'),
    ('JourneyFilter = Annotated[', 'SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,200}$")\n'
     'Disposition = Annotated[Literal["inline", "attachment"], Query(\n'
     '    description="`attachment` asks the browser to download the file (Spec 14)")]\nJourneyFilter = Annotated['),
    ('            operation_id="getReportContent", dependencies=[only_query()],\n',
     '            operation_id="getReportContent", dependencies=[only_query("disposition")],\n'),
    ('def get_report_content(ctx: Ctx, caller: Caller, report_id: ReportId) -> Response:\n',
     'def get_report_content(ctx: Ctx, caller: Caller, report_id: ReportId,\n'
     '                       disposition: Disposition = "inline") -> Response:\n'),
    ('    return Response(content=data, media_type="text/html; charset=utf-8", headers=CONTENT_HEADERS)\n',
     '    headers = dict(CONTENT_HEADERS)\n'
     '    name = report.path.name\n'
     '    if disposition == "attachment" and SAFE_NAME.fullmatch(name):\n'
     '        headers["Content-Disposition"] = f\'attachment; filename="{name}"\'\n'
     '    return Response(content=data, media_type="text/html; charset=utf-8", headers=headers)\n'),
])
print("api edits done")
