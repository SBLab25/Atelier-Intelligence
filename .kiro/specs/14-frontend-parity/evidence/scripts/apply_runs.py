"""Spec 14 runs routes: start (OD-144), resume (OD-145), results with provenance (OD-146, OD-147)."""
from __future__ import annotations

from edit import ROOT, apply

RUNS = "cji_agent/src/cji/api/routes/runs.py"

apply(RUNS, [
    ('"""\nWorkflow runs: list, detail and approval (OD-115..OD-117).\n',
     '"""\nWorkflow runs: list, detail and approval (OD-115..OD-117); start, resume and results (Spec 14, OD-144..OD-147).\n'),
    ('import asyncio\nimport logging\nimport re\nfrom typing import Annotated, Any, get_args\n',
     'import asyncio\nimport logging\nimport re\nimport uuid\nfrom collections.abc import Coroutine\n'
     'from pathlib import PurePath\nfrom typing import Annotated, Any, get_args\n'),
    ('from cji.workflow.errors import RunNotResumable\n',
     'from cji.workflow.errors import RunLeased, RunNotFound, RunNotResumable\n'),
    ('from ..schemas import (\n    Approval,\n    ApprovalRequest,\n    Failure,\n    Page,\n    PageInfo,\n    Run,\n'
     '    RunStatus,\n    RunSummary,\n    Step,\n)\n',
     'from ..schemas import (\n    Approval,\n    ApprovalRequest,\n    Failure,\n    Fix,\n    LlmUsage,\n    Page,\n'
     '    PageInfo,\n    PendingReview,\n    Provenance,\n    Run,\n    RunError,\n    RunFrictionScore,\n'
     '    RunIngestionResult,\n    RunInsight,\n    RunResults,\n    RunStatus,\n    RunSummary,\n    StartRunRequest,\n'
     '    Step,\n)\n'),
    ('    errors,\n    next_cursor,\n    only_query,\n    page_after,\n    require_filter,\n    require_role,\n)\n',
     '    check_idempotency_key,\n    errors,\n    json_body,\n    next_cursor,\n    only_query,\n    page_after,\n'
     '    require_filter,\n    require_role,\n    visible_journey,\n)\n'),
    ('router = APIRouter(tags=["runs"])\n',
     'router = APIRouter(tags=["runs"])\nwrite_router = APIRouter(tags=["runs"])     # Spec 14 (CJI_API_WRITE_OPERATIONS)\n'),
    ('async def _continue(ctx: ApiContext, run_id: str) -> None:\n    try:\n',
     'async def _continue(ctx: ApiContext, run_id: str) -> None:\n    ctx.active_runs.add(run_id)\n    try:\n'),
    ('        logger.error("approved run %s could not continue: %s", run_id, type(exc).__name__)\n',
     '        logger.error("approved run %s could not continue: %s", run_id, type(exc).__name__)\n'
     '    finally:\n        ctx.active_runs.discard(run_id)\n'),
])

runs = ROOT / RUNS
runs.write_text(runs.read_text(encoding="utf-8") + '''

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
            try:
                run, _status = await _visible_run_any(ctx, run_id)
                return run
            except RunNotFound:
                pass
        if task.done():
            break
        await asyncio.sleep(0.05)
    logger.error("run %s: no checkpoint after start", run_id)
    raise ApiError(503, "storage_unavailable", headers={"Retry-After": "5"})


async def _visible_run_any(ctx: ApiContext, run_id: str) -> tuple[Run, dict[str, Any]]:
    row, status, values = await ctx.runs.get(run_id)
    return _run(row, status, values), status


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
    by_id = values.get("insight_provenance") if isinstance(values.get("insight_provenance"), dict) else {}
    insights = []
    for item in insights_of(values):
        try:
            insights.append(RunInsight.model_validate({**item, "provenance": _provenance(by_id.get(
                str(item.get("insight_id")))).model_dump()}))
        except ValidationError:
            logger.info("results: insight skipped (missing required fields)")
    usage = values.get("llm_usage") if isinstance(values.get("llm_usage"), dict) else {}
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
''', encoding="utf-8", newline="\n")
print("runs edits done")
