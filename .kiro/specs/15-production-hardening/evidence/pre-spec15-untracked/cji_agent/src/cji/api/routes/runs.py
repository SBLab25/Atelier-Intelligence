"""
Workflow runs: list, detail and approval (OD-115..OD-117); start, resume and results (Spec 14, OD-144..OD-147).

Approval only marks the run approved (state change under the run lease) and answers 202; the report step runs in a
background task of the API process. Replays of an Idempotency-Key return the stored response.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from collections.abc import Coroutine
from pathlib import PurePath
from typing import Annotated, Any, get_args

from fastapi import APIRouter, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from cji.services.reports import report_id_for
from cji.services.runs import insights_of
from cji.workflow.errors import RunLeased, RunNotFound, RunNotResumable
from cji.workflow.index import IndexedRun, report_file_name

from ..app import ApiContext
from ..auth import Principal
from ..errors import ApiError
from ..schemas import (
    Approval,
    ApprovalRequest,
    Failure,
    Fix,
    LlmUsage,
    Page,
    PageInfo,
    PendingReview,
    Provenance,
    Run,
    RunError,
    RunFrictionScore,
    RunIngestionResult,
    RunInsight,
    RunResults,
    RunStatus,
    RunSummary,
    StartRunRequest,
    Step,
)
from ._deps import (
    API_PREFIX,
    DEFAULT_PAGE,
    Caller,
    Ctx,
    Cursor,
    Limit,
    RunId,
    check_idempotency_key,
    errors,
    json_body,
    next_cursor,
    only_query,
    page_after,
    require_filter,
    require_role,
    visible_journey,
)

router = APIRouter(tags=["runs"])
write_router = APIRouter(tags=["runs"])     # Spec 14 (CJI_API_WRITE_OPERATIONS)
logger = logging.getLogger("cji.api")

RUN_STATUSES = frozenset(get_args(RunStatus))
IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9._-]{8,64}")
JSON_TYPES = ("application/json",)
StatusFilter = Annotated[RunStatus | None, Query(description="Only runs with this status")]
JourneyFilter = Annotated[str | None, Query(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f/]+$",
                                            description="Only runs of this journey")]


def _status(value: Any, fallback: str = "running") -> Any:
    return value if value in RUN_STATUSES else (fallback if fallback in RUN_STATUSES else "running")


def _report_id(report_file: str | None) -> str | None:
    return report_id_for(report_file) if report_file else None


def _summary(row: IndexedRun) -> RunSummary:
    return RunSummary(run_id=row.run_id, journey_id=row.journey_id, mode=row.mode, status=_status(row.status),
                      created_at=row.created_at, updated_at=row.updated_at, report_id=_report_id(row.report_file))


def _failure(raw: Any) -> Failure | None:
    if not isinstance(raw, dict):
        return None
    attempts = raw.get("attempts")
    return Failure(worker=str(raw.get("worker") or ""), code=str(raw.get("code") or "unexpected_error"),
                   message=str(raw.get("message") or ""), retryable=bool(raw.get("retryable")),
                   attempts=attempts if isinstance(attempts, int) else 0)


def _steps(raw: Any) -> dict[str, Step]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Step] = {}
    for worker, step in raw.items():
        if isinstance(step, dict):
            attempts = step.get("attempts")
            out[str(worker)] = Step(status=_text(step.get("status")),
                                    attempts=attempts if isinstance(attempts, int) else None,
                                    started_at=_text(step.get("started_at")),
                                    finished_at=_text(step.get("finished_at")), code=_text(step.get("code")))
    return out


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _run(row: IndexedRun, status: dict[str, Any], values: dict[str, Any]) -> Run:
    report_file = report_file_name(status.get("report_path")) or row.report_file
    return Run(
        run_id=row.run_id, journey_id=row.journey_id, mode=row.mode,
        status=_status(status.get("status"), row.status),
        created_at=str(status.get("created_at") or row.created_at),
        updated_at=str(status.get("updated_at") or row.updated_at),
        report_id=_report_id(report_file),
        human_approved=bool(status.get("human_approved")),
        active=status.get("lease_owner") is not None,
        steps=_steps(status.get("steps")),
        failure=_failure(status.get("failure")),
        insight_count=len(insights_of(values)),
        errors_total=int(status.get("errors_total") or 0),
    )


async def _visible_run(ctx: ApiContext, caller: Principal, run_id: str) -> tuple[Run, dict[str, Any]]:
    """The run, or 404 run_not_found with the same body whether it is missing or outside the token."""
    row, status, values = await ctx.runs.get(run_id)
    if not caller.can_see(row.journey_id):
        raise ApiError(404, "run_not_found")
    return _run(row, status, values), status


@router.get("/runs", response_model=Page[RunSummary], summary="Runs, most recently updated first",
            operation_id="listRuns", responses=errors(403, 422, 503),
            dependencies=[only_query("journey_id", "status", "limit", "cursor")])
def list_runs(ctx: Ctx, caller: Caller, journey_id: JourneyFilter = None, status: StatusFilter = None,
              limit: Limit = DEFAULT_PAGE, cursor: Cursor = None) -> Page[RunSummary]:
    require_filter(caller, journey_id)
    filters: dict[str, Any] = {"resource": "runs", "journey_id": journey_id, "status": status}
    after = page_after(ctx, cursor, filters)
    if after is not None and (len(after) != 2 or not all(isinstance(v, str) for v in after)):
        raise ApiError(422, "invalid_cursor")
    rows = ctx.runs.page(journeys=caller.visible_journeys(), journey_id=journey_id, status=status, limit=limit + 1,
                         after=(after[0], after[1]) if after else None)
    page, more = rows[:limit], len(rows) > limit
    return Page[RunSummary](data=[_summary(r) for r in page],
                            page=PageInfo(limit=limit, next_cursor=next_cursor(
                                ctx, more, lambda: [page[-1].updated_at, page[-1].run_id], filters)))


@router.get("/runs/{run_id}", response_model=Run, summary="One run", operation_id="getRun",
            responses=errors(404, 422, 503), dependencies=[only_query()])
async def get_run(ctx: Ctx, caller: Caller, run_id: RunId) -> Run:
    run, _status = await _visible_run(ctx, caller, run_id)
    return run


def _check_key(key: str | None) -> str:
    if key is None or key == "":
        raise ApiError(400, "idempotency_key_required")
    if not IDEMPOTENCY_KEY.fullmatch(key):
        raise ApiError(400, "idempotency_key_invalid")
    return key


def _parse_body(request: Request, raw: bytes) -> ApprovalRequest:
    if not raw.strip():
        return ApprovalRequest()
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media not in JSON_TYPES and not media.endswith("+json"):
        raise ApiError(415, "unsupported_media_type")
    try:
        return ApprovalRequest.model_validate_json(raw)
    except ValidationError as exc:
        raise RequestValidationError([
            {"type": e["type"], "loc": ("body", *e["loc"]), "msg": e["msg"]}
            for e in exc.errors(include_input=False, include_url=False)[:20]
        ]) from None


async def _continue(ctx: ApiContext, run_id: str) -> None:
    ctx.active_runs.add(run_id)
    try:
        outcome = await ctx.runs.continue_run(run_id)
        logger.info("approved run %s continued: %s", run_id, outcome.status)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001  # broad-except: background task; the run's state records the failure
        logger.error("approved run %s could not continue: %s", run_id, type(exc).__name__)
    finally:
        ctx.active_runs.discard(run_id)


@router.post(
    "/runs/{run_id}/approval", response_model=Approval, status_code=202, summary="Approve a run awaiting approval",
    operation_id="approveRun", dependencies=[only_query()],
    responses={200: {"model": Approval, "description": "The run was already approved; nothing changed"},
               **errors(400, 403, 404, 409, 413, 415, 422, 503)},
    openapi_extra={"requestBody": {"required": False, "content": {
        "application/json": {"schema": {"$ref": "#/components/schemas/ApprovalRequest"}}}}},
)
async def approve_run(
    request: Request, ctx: Ctx, caller: Caller, run_id: RunId,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key",
                                                  description="8-64 of A-Z a-z 0-9 . _ -; replays return the "
                                                              "stored response for 24 h")] = None,
) -> JSONResponse:
    key = _check_key(idempotency_key)
    raw = await request.body()
    body = _parse_body(request, raw)
    require_role(caller, "operator")
    _run_now, status = await _visible_run(ctx, caller, run_id)

    route = f"POST {API_PREFIX}/runs/{run_id}/approval"
    store = ctx.idempotency
    replay = store.begin(caller.token_id, key, route, store.request_hash(route, raw))
    if replay is not None:
        code, stored = replay
        return JSONResponse(stored, status_code=code, headers={"Idempotent-Replayed": "true"})
    try:
        try:
            outcome = await ctx.runs.mark_approved(run_id)
        except RunNotResumable:
            current = _status(status.get("status"), "failed")
            raise ApiError(409, "run_not_awaiting_approval",
                           f"The run is {current}; only a run awaiting approval can be approved.") from None
        row, after, values = await ctx.runs.get(run_id)
        result = Approval(run=_run(row, after, values), already_approved=outcome.already)
        code = 200 if outcome.already else 202
        payload = result.model_dump(mode="json")
        store.finish(caller.token_id, key, code, payload)
    except BaseException:  # broad-except: free the key on any failure so the client can retry; re-raised
        store.abandon(caller.token_id, key)
        raise
    if body.comment:
        logger.info("run %s approved by %s, comment=%r", run_id, caller.token_id, body.comment)
    if not outcome.already:
        task = asyncio.create_task(_continue(ctx, run_id))
        ctx.tasks.add(task)
        task.add_done_callback(ctx.tasks.discard)
    return JSONResponse(payload, status_code=code)


# ── Spec 14: start, resume, results ──────────────────────────────────────────────────────────────────────
START_WAIT_S = 10.0
MAX_ERRORS = 50
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key",
                                              description="8-64 of A-Z a-z 0-9 . _ -; replays return the stored "
                                                          "response for 24 h")]


def _launch(ctx: ApiContext, run_id: str, work: Coroutine[Any, Any, Any], what: str) -> asyncio.Task[Any]:
    """Drive a run in a background task of this process (OD-144, OD-157); the run's state records failures."""
    ctx.active_runs.add(run_id)

    async def runner() -> None:
        try:
            outcome = await work
            logger.info("run %s %s: %s", run_id, what, getattr(outcome, "status", None))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001  # broad-except: background task; the run's state records the failure
            logger.error("run %s could not %s: %s", run_id, what, type(exc).__name__)
        finally:
            ctx.active_runs.discard(run_id)

    task = asyncio.create_task(runner())
    ctx.tasks.add(task)
    task.add_done_callback(ctx.tasks.discard)
    return task


def _capacity(ctx: ApiContext) -> None:
    if len(ctx.active_runs) >= ctx.settings.api.max_active_runs:
        raise ApiError(409, "run_capacity_reached", headers={"Retry-After": "30"})


async def _preflight(ctx: ApiContext) -> None:
    """The CLI's MCP check before any run work (`ping_all_servers`); 503 without naming hosts or ports."""
    check = ctx.preflight
    if check is None:
        from cji.tools.mcp_client import ping_all_servers

        check = ping_all_servers
    try:
        await check()
    except (RuntimeError, OSError) as exc:
        logger.warning("preflight failed: %s", type(exc).__name__)
        raise ApiError(503, "services_unavailable", headers={"Retry-After": "10"}) from None


async def _started(ctx: ApiContext, run_id: str, task: asyncio.Task[Any]) -> Run:
    """The new run once its first checkpoint is stored (the workflow stores it before any worker runs)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + START_WAIT_S
    while loop.time() < deadline:
        if ctx.runs.index.get(run_id) is not None:
            run = await _stored_run(ctx, run_id)
            if run is not None:
                return run
        if task.done():
            break
        await asyncio.sleep(0.05)
    logger.error("run %s: no checkpoint after start", run_id)
    raise ApiError(503, "storage_unavailable", headers={"Retry-After": "5"})


async def _stored_run(ctx: ApiContext, run_id: str) -> Run | None:
    """The run once its first checkpoint exists; None while only the index row is written."""
    try:
        row, status, values = await ctx.runs.get(run_id)
    except RunNotFound:
        logger.debug("run %s: checkpoint not stored yet", run_id)
        return None
    return _run(row, status, values)


@write_router.post(
    "/runs", response_model=Run, status_code=202, summary="Start a run (operator)", operation_id="startRun",
    dependencies=[only_query()], responses=errors(400, 403, 404, 409, 413, 415, 422, 503),
    openapi_extra={"requestBody": {"required": True, "content": {
        "application/json": {"schema": {"$ref": "#/components/schemas/StartRunRequest"}}}}},
)
async def start_run(request: Request, ctx: Ctx, caller: Caller, idempotency_key: IdempotencyKey = None) -> JSONResponse:
    key = check_idempotency_key(idempotency_key)
    raw = await request.body()
    body = json_body(request, raw, StartRunRequest)
    if body.window_days is not None and body.window_minutes is not None:
        raise RequestValidationError([{"type": "one_window", "loc": ("body", "window_minutes"),
                                       "msg": "Send window_days or window_minutes, not both"}])
    journey = visible_journey(ctx, caller, body.journey_id, role="operator")
    route = f"POST {API_PREFIX}/runs"
    store = ctx.idempotency
    replay = store.begin(caller.token_id, key, route, store.request_hash(route, raw))
    if replay is not None:
        code, stored = replay
        return JSONResponse(stored, status_code=code, headers={"Idempotent-Replayed": "true"})
    try:
        _capacity(ctx)
        await _preflight(ctx)
        from cji.workflow.runtime import initial_state

        settings = ctx.settings
        state = initial_state(
            mode=settings.app.mode, journey_name=journey.name, journey_steps=list(journey.steps),
            auto_approve=body.auto_approve, window_days=body.window_days or 30,
            window_mins=body.window_minutes or settings.budgets.realtime_window_minutes,
            collector_url=settings.services.get("collector").url,
        )
        run_id = str(uuid.uuid4())
        task = _launch(ctx, run_id, ctx.runs.workflow().start(state, run_id=run_id), "start")
        run = await _started(ctx, run_id, task)
        payload = run.model_dump(mode="json")
        store.finish(caller.token_id, key, 202, payload)
    except BaseException:  # broad-except: free the key on any failure so the client can retry; re-raised
        store.abandon(caller.token_id, key)
        raise
    logger.info("run %s started by %s (journey %s, auto_approve=%s)", run_id, caller.token_id, journey.name,
                body.auto_approve)
    return JSONResponse(payload, status_code=202)


@write_router.post(
    "/runs/{run_id}/resume", response_model=Run, status_code=202,
    summary="Resume a failed or orphaned run (operator)", operation_id="resumeRun", dependencies=[only_query()],
    responses=errors(400, 403, 404, 409, 422, 503),
)
async def resume_run(ctx: Ctx, caller: Caller, run_id: RunId, idempotency_key: IdempotencyKey = None) -> JSONResponse:
    key = check_idempotency_key(idempotency_key)
    require_role(caller, "operator")
    run, status = await _visible_run(ctx, caller, run_id)
    route = f"POST {API_PREFIX}/runs/{run_id}/resume"
    store = ctx.idempotency
    replay = store.begin(caller.token_id, key, route, store.request_hash(route, b""))
    if replay is not None:
        code, stored = replay
        return JSONResponse(stored, status_code=code, headers={"Idempotent-Replayed": "true"})
    try:
        if run.status == "completed":
            raise ApiError(409, "run_not_resumable", "The run is completed; nothing to resume.")
        if run.status == "awaiting_approval":
            raise ApiError(409, "run_not_resumable", "The run is awaiting approval; approve it instead.")
        if status.get("lease_owner") is not None or run_id in ctx.active_runs:
            raise ApiError(409, "run_active", headers={"Retry-After": "5"})
        _capacity(ctx)
        await _preflight(ctx)
        _launch(ctx, run_id, _resume(ctx, run_id), "resume")
        payload = run.model_dump(mode="json")
        store.finish(caller.token_id, key, 202, payload)
    except BaseException:  # broad-except: free the key on any failure so the client can retry; re-raised
        store.abandon(caller.token_id, key)
        raise
    logger.info("run %s resumed by %s", run_id, caller.token_id)
    return JSONResponse(payload, status_code=202)


async def _resume(ctx: ApiContext, run_id: str) -> Any:
    try:
        return await ctx.runs.continue_run(run_id)
    except (RunNotResumable, RunLeased) as exc:
        logger.info("run %s not resumed: %s", run_id, type(exc).__name__)
        return None


def _provenance(raw: Any) -> Provenance:
    if not isinstance(raw, dict) or raw.get("source") not in ("llm", "fallback", "not_recorded"):
        return Provenance(source="not_recorded", model=None, provider=None, reason=None, generated_at=None)
    return Provenance(source=raw["source"], model=_text(raw.get("model")), provider=_text(raw.get("provider")),
                      reason=_text(raw.get("reason")), generated_at=_text(raw.get("generated_at")))


def _lenient(model: Any, items: Any) -> list[Any]:
    out = []
    for item in items if isinstance(items, list) else []:
        try:
            out.append(model.model_validate(item))
        except ValidationError:
            logger.info("results: %s entry skipped (missing required fields)", model.__name__)
    return out


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _count(value: Any) -> int:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


def _results(row: IndexedRun, status: dict[str, Any], values: dict[str, Any]) -> RunResults:
    raw_provenance = values.get("insight_provenance")
    by_id: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
    insights = []
    for item in insights_of(values):
        try:
            insights.append(RunInsight.model_validate({**item, "provenance": _provenance(by_id.get(
                str(item.get("insight_id")))).model_dump()}))
        except ValidationError:
            logger.info("results: insight skipped (missing required fields)")
    raw_usage = values.get("llm_usage")
    usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
    ingested = [RunIngestionResult(
        file_name=PurePath(str(r.get("source_file") or "")).name, detected_source=_text(r.get("detected_source")),
        confidence=_number(r.get("confidence")), records_written=_count(r.get("records_written")),
        records_skipped=_count(r.get("records_skipped")), status=_text(r.get("status")),
        cached_mapping=bool(r.get("cached_mapping")))
        for r in values.get("ingestion_results") or [] if isinstance(r, dict)]
    pending = [PendingReview(
        file_name=PurePath(str(r.get("file_path") or "")).name,
        detected_source=_text((r.get("mapping_config") or {}).get("detected_source")
                              if isinstance(r.get("mapping_config"), dict) else None),
        confidence=_number(r.get("confidence")), flagged_at=_text(r.get("flagged_at")))
        for r in values.get("ingestion_pending_review") or [] if isinstance(r, dict)]
    errs = [RunError(worker=str(e.get("worker") or "unknown"), message=str(e.get("error") or "")[:300],
                     ts=_text(e.get("ts")))
            for e in (values.get("errors") or [])[-MAX_ERRORS:] if isinstance(e, dict)]
    narrative = values.get("narrative")
    return RunResults(
        run_id=row.run_id, journey_id=row.journey_id, status=_status(status.get("status"), row.status),
        narrative=str(narrative) if narrative else None,
        narrative_provenance=_provenance(values.get("narrative_provenance")),
        friction_scores=_lenient(RunFrictionScore, values.get("friction_scores")),
        critical_steps=[str(s) for s in values.get("critical_steps") or []],
        insights=insights, prioritized_fixes=_lenient(Fix, values.get("prioritized_fixes")),
        llm_usage=LlmUsage(calls=_count(usage.get("calls")), input_tokens=_count(usage.get("input_tokens")),
                           output_tokens=_count(usage.get("output_tokens")),
                           cost_usd=_number(usage.get("cost_usd")) or 0.0),
        ingestion_results=ingested, ingestion_pending_review=pending, errors=errs,
    )


@router.get("/runs/{run_id}/results", response_model=RunResults, summary="A run's results and provenance",
            operation_id="getRunResults", responses=errors(404, 422, 503), dependencies=[only_query()])
async def get_run_results(ctx: Ctx, caller: Caller, run_id: RunId) -> RunResults:
    row, status, values = await ctx.runs.get(run_id)
    if not caller.can_see(row.journey_id):
        raise ApiError(404, "run_not_found")
    return _results(row, status, values)
