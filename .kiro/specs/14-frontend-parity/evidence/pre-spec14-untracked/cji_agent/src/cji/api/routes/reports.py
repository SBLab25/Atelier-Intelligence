"""Report metadata and content (OD-114). A report is visible when its run's journey is visible to the token."""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, Response

from cji.services.reports import ReportFile, find_report, list_reports, read_report

from ..errors import ApiError, problem_responses
from ..schemas import Page, PageInfo, Report
from ._deps import (
    API_PREFIX,
    COMMON,
    DEFAULT_PAGE,
    Caller,
    Ctx,
    Cursor,
    Limit,
    ReportId,
    errors,
    next_cursor,
    only_query,
    page_after,
    require_filter,
)

router = APIRouter(tags=["reports"])
logger = logging.getLogger("cji.api")

CONTENT_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
    "Content-Disposition": "inline",
    "X-Content-Type-Options": "nosniff",
}
JourneyFilter = Annotated[str | None, Query(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f/]+$",
                                            description="Only reports of this journey")]


def _journey_of(ctx: Ctx, report: ReportFile) -> str | None:
    if report.run_id is None:
        return None
    indexed = ctx.runs.index.get(report.run_id)
    return indexed.journey_id if indexed else None


def _report(report: ReportFile, journey_id: str | None) -> Report:
    return Report(report_id=report.report_id, run_id=report.run_id, journey_id=journey_id,
                  size_bytes=report.size_bytes, created_at=report.created_at,
                  content_url=f"{API_PREFIX}/reports/{report.report_id}/content")


def _visible(ctx: Ctx, caller: Caller, report_id: str) -> tuple[ReportFile, str | None]:
    report = find_report(ctx.settings.storage.reports_dir, report_id)
    journey_id = _journey_of(ctx, report) if report else None
    if report is None or not caller.can_see(journey_id):
        raise ApiError(404, "report_not_found")
    return report, journey_id


@router.get("/reports", response_model=Page[Report], summary="Reports, newest first", operation_id="listReports",
            responses=errors(403, 422, 503), dependencies=[only_query("journey_id", "limit", "cursor")])
def get_reports(ctx: Ctx, caller: Caller, journey_id: JourneyFilter = None, limit: Limit = DEFAULT_PAGE,
                cursor: Cursor = None) -> Page[Report]:
    require_filter(caller, journey_id)
    filters: dict[str, Any] = {"resource": "reports", "journey_id": journey_id}
    after = page_after(ctx, cursor, filters)
    if after is not None and (len(after) != 2 or not isinstance(after[0], int | float)
                              or not isinstance(after[1], str)):
        raise ApiError(422, "invalid_cursor")
    rows: list[tuple[ReportFile, str | None]] = []
    for report in list_reports(ctx.settings.storage.reports_dir):
        if after is not None and (report.modified, report.report_id) >= (float(after[0]), after[1]):
            continue
        owner = _journey_of(ctx, report)
        if not caller.can_see(owner) or (journey_id is not None and owner != journey_id):
            continue
        rows.append((report, owner))
        if len(rows) > limit:
            break
    page, more = rows[:limit], len(rows) > limit
    return Page[Report](data=[_report(r, j) for r, j in page],
                        page=PageInfo(limit=limit, next_cursor=next_cursor(
                            ctx, more, lambda: [page[-1][0].modified, page[-1][0].report_id], filters)))


@router.get("/reports/{report_id}", response_model=Report, summary="Report metadata", operation_id="getReport",
            responses=errors(404, 422), dependencies=[only_query()])
def get_report(ctx: Ctx, caller: Caller, report_id: ReportId) -> Report:
    report, journey_id = _visible(ctx, caller, report_id)
    return _report(report, journey_id)


@router.get("/reports/{report_id}/content", response_class=HTMLResponse, summary="Report HTML",
            operation_id="getReportContent", dependencies=[only_query()],
            responses={200: {"description": "The report document (sandboxed by Content-Security-Policy)",
                             "content": {"text/html": {"schema": {"type": "string"}}}},
                       **problem_responses(*sorted({*COMMON, 404, 422}))})
def get_report_content(ctx: Ctx, caller: Caller, report_id: ReportId) -> Response:
    report, _journey_id = _visible(ctx, caller, report_id)
    try:
        data = read_report(report)
    except ValueError:
        logger.error("report %s exceeds the report size limit", report.report_id)
        raise ApiError(500, "internal_error") from None
    return Response(content=data, media_type="text/html; charset=utf-8", headers=CONTENT_HEADERS)

