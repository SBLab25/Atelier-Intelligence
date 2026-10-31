"""Journeys and their events, metrics, friction and insights (OD-111..OD-113, OD-119)."""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import ValidationError

from cji.services import analytics, journeys
from cji.services.runs import insights_of

from ..errors import ApiError
from ..schemas import (
    Event,
    Friction,
    Insight,
    Insights,
    Journey,
    Metrics,
    Page,
    PageInfo,
    Window,
)
from ._deps import (
    DEFAULT_PAGE,
    Caller,
    Ctx,
    Cursor,
    JourneyId,
    Limit,
    errors,
    next_cursor,
    only_query,
    page_after,
    visible_journey,
)

router = APIRouter(tags=["journeys"])
logger = logging.getLogger("cji.api")

Days = Annotated[int, Query(ge=1, le=365, description="Window in days (demo data)")]
Minutes = Annotated[int | None, Query(ge=1, le=43200, description="Window in minutes (realtime data)")]
StepFilter = Annotated[str | None, Query(min_length=1, max_length=128, description="Only events of this step")]
TypeFilter = Annotated[str | None, Query(min_length=1, max_length=64, description="Only events of this type")]
_SHORT_OFFSET = re.compile(r"([+-]\d\d)$")


def _journey(ctx: Ctx, journey: Any) -> Journey:
    return Journey(journey_id=journey.name, steps=list(journey.steps), mode=ctx.settings.app.mode)


@router.get("/journeys", response_model=Page[Journey], summary="Journeys visible to the token",
            operation_id="listJourneys", responses=errors(422), dependencies=[only_query("limit", "cursor")])
def list_journeys(ctx: Ctx, caller: Caller, limit: Limit = DEFAULT_PAGE, cursor: Cursor = None) -> Page[Journey]:
    filters: dict[str, Any] = {"resource": "journeys"}
    after = page_after(ctx, cursor, filters)
    found = sorted((j for j in journeys.list_journeys(ctx.settings) if caller.can_see(j.name)), key=lambda j: j.name)
    if after:
        found = [j for j in found if j.name > str(after[0])]
    rows = found[:limit]
    more = len(found) > limit
    return Page[Journey](data=[_journey(ctx, j) for j in rows],
                         page=PageInfo(limit=limit, next_cursor=next_cursor(ctx, more, lambda: [rows[-1].name],
                                                                             filters)))


@router.get("/journeys/{journey_id}", response_model=Journey, summary="One journey", operation_id="getJourney",
            responses=errors(403, 404, 422), dependencies=[only_query()])
def get_journey(ctx: Ctx, caller: Caller, journey_id: JourneyId) -> Journey:
    return _journey(ctx, visible_journey(ctx, caller, journey_id))


@router.get("/journeys/{journey_id}/metrics", response_model=Metrics, summary="Step metrics and funnel",
            operation_id="getJourneyMetrics", responses=errors(403, 404, 422, 503),
            dependencies=[only_query("days", "minutes")])
def get_metrics(ctx: Ctx, caller: Caller, journey_id: JourneyId, days: Days = 30, minutes: Minutes = None) -> Metrics:
    journey = visible_journey(ctx, caller, journey_id)
    result = analytics.journey_metrics(ctx.repository, journey, analytics.window_for(days, minutes))
    return Metrics(journey_id=journey.name, window=Window(days=result.window_days, minutes=result.window_minutes),
                   steps=result.steps, funnel=result.funnel, overall_completion_pct=result.overall_completion_pct)


@router.get("/journeys/{journey_id}/friction", response_model=Friction, summary="Friction scores",
            operation_id="getJourneyFriction", responses=errors(403, 404, 422, 503),
            dependencies=[only_query("days", "minutes")])
def get_friction(ctx: Ctx, caller: Caller, journey_id: JourneyId, days: Days = 30,
                 minutes: Minutes = None) -> Friction:
    journey = visible_journey(ctx, caller, journey_id)
    window = analytics.window_for(days, minutes)
    threshold = ctx.settings.budgets.friction_score_threshold
    result = analytics.journey_friction(ctx.repository, journey, window, threshold)
    window_days, window_minutes = ctx.repository.window_fields(window)
    return Friction(journey_id=journey.name, window=Window(days=window_days, minutes=window_minutes),
                    threshold=threshold, scores=result["scores"], critical_steps=result["critical_steps"])


def _utc(text: str) -> str:
    """Database timestamp text (local offset, e.g. `+05:30` or `+00`) as RFC 3339 UTC with microseconds."""
    value = datetime.fromisoformat(_SHORT_OFFSET.sub(r"\1:00", text.strip()))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _event(row: dict[str, Any]) -> Event:
    return Event(event_id=str(row["event_id"]), user_id=row.get("user_id"), session_id=row.get("session_id"),
                 step_id=row.get("step_id"), event_type=row.get("event_type"), timestamp=_utc(str(row["timestamp"])),
                 duration_ms=None if row.get("duration_ms") is None else int(row["duration_ms"]), url=row.get("url"))


@router.get("/journeys/{journey_id}/events", response_model=Page[Event], summary="Events, newest first (operator)",
            operation_id="listJourneyEvents", responses=errors(403, 404, 422, 503),
            dependencies=[only_query("limit", "cursor", "step_id", "event_type")])
def list_events(ctx: Ctx, caller: Caller, journey_id: JourneyId, limit: Limit = DEFAULT_PAGE, cursor: Cursor = None,
                step_id: StepFilter = None, event_type: TypeFilter = None) -> Page[Event]:
    journey = visible_journey(ctx, caller, journey_id, role="operator")
    filters = {"resource": "events", "journey_id": journey.name, "step_id": step_id, "event_type": event_type}
    after = page_after(ctx, cursor, filters)
    if after is not None and (len(after) != 2 or not all(isinstance(v, str) for v in after)):
        raise ApiError(422, "invalid_cursor")
    rows = analytics.event_page(ctx.repository, journey, limit=limit + 1,
                                after=(after[0], after[1]) if after else None, step_id=step_id, event_type=event_type)
    page, more = rows[:limit], len(rows) > limit
    return Page[Event](data=[_event(r) for r in page],
                       page=PageInfo(limit=limit, next_cursor=next_cursor(
                           ctx, more, lambda: [str(page[-1]["timestamp"]), str(page[-1]["event_id"])], filters)))


@router.get("/journeys/{journey_id}/insights", response_model=Insights, summary="Insights of the latest run",
            operation_id="getJourneyInsights", responses=errors(403, 404, 422, 503),
            dependencies=[only_query("run_id")])
async def get_insights(ctx: Ctx, caller: Caller, journey_id: JourneyId,
                       run_id: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9-]{1,64}$",
                                                           description="A run of this journey")] = None) -> Insights:
    journey = visible_journey(ctx, caller, journey_id)
    if run_id is not None:
        indexed, _status, values = await ctx.runs.get(run_id)
        if indexed.journey_id != journey.name:
            raise ApiError(404, "run_not_found")
        found: tuple[str | None, list[dict[str, Any]]] = (run_id, insights_of(values))
    else:
        found = await ctx.runs.latest_with_insights(journey.name)
    return Insights(journey_id=journey.name, run_id=found[0], insights=_insights(found[1]))


def _insights(raw: list[dict[str, Any]]) -> list[Insight]:
    out = []
    for item in raw:
        try:
            out.append(Insight.model_validate(item))
        except ValidationError:
            logger.info("insight skipped: missing required fields")
    return out

