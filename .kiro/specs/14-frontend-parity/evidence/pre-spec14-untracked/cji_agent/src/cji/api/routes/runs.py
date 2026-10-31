"""
Workflow runs: list, detail and approval (OD-115..OD-117).

Approval only marks the run approved (state change under the run lease) and answers 202; the report step runs in a
background task of the API process. Replays of an Idempotency-Key return the stored response.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Annotated, Any, get_args

from fastapi import APIRouter, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from cji.services.reports import report_id_for
from cji.services.runs import insights_of
from cji.workflow.errors import RunNotResumable
from cji.workflow.index import IndexedRun, report_file_name

from ..app import ApiContext
from ..auth import Principal
from ..errors import ApiError
from ..schemas import (
    Approval,
    ApprovalRequest,
    Failure,
    Page,
    PageInfo,
    Run,
    RunStatus,
    RunSummary,
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
    errors,
    next_cursor,
    only_query,
    page_after,
    require_filter,
    require_role,
)

router = APIRouter(tags=["runs"])
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
    try:
        outcome = await ctx.runs.continue_run(run_id)
        logger.info("approved run %s continued: %s", run_id, outcome.status)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001  # broad-except: background task; the run's state records the failure
        logger.error("approved run %s could not continue: %s", run_id, type(exc).__name__)


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
