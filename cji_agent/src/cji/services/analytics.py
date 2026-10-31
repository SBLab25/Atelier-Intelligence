"""Journey metrics, friction and event pages from the configured repository (Spec 12, OD-112)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cji.analytics.friction import score_steps
from cji.analytics.funnel import overall_completion_pct
from cji.domain.journeys import JourneyDefinition
from cji.domain.metrics import FunnelStep, StepMetrics
from cji.repositories import EventRepository, TimeWindow


@dataclass(frozen=True)
class JourneyMetrics:
    journey_id: str
    window_days: int | None
    window_minutes: int | None
    steps: list[StepMetrics]
    funnel: list[FunnelStep]
    overall_completion_pct: float


def window_for(days: int, minutes: int | None) -> TimeWindow:
    return TimeWindow(days_back=days, minutes_back=minutes or 0)


def journey_metrics(repo: EventRepository, journey: JourneyDefinition, window: TimeWindow, table: str | None = None, account_id: str | None = None) -> JourneyMetrics:
    try:
        steps = repo.step_metrics(journey.name, window, table=table, account_id=account_id)  # type: ignore[call-arg]
        funnel = repo.funnel(journey.name, list(journey.steps), window, table=table, account_id=account_id)  # type: ignore[call-arg]
    except TypeError:
        try:
            steps = repo.step_metrics(journey.name, window, table=table)  # type: ignore[call-arg]
            funnel = repo.funnel(journey.name, list(journey.steps), window, table=table)  # type: ignore[call-arg]
        except TypeError:
            steps = repo.step_metrics(journey.name, window)
            funnel = repo.funnel(journey.name, list(journey.steps), window)
    days, minutes = repo.window_fields(window)
    return JourneyMetrics(journey.name, days, minutes, steps, funnel, overall_completion_pct(funnel))


def journey_friction(repo: EventRepository, journey: JourneyDefinition, window: TimeWindow,
                     threshold: int, table: str | None = None, account_id: str | None = None) -> dict[str, Any]:
    """score_steps() of the journey's step metrics: {scores, critical_steps, total_steps, avg_score, threshold}."""
    try:
        metrics = repo.step_metrics(journey.name, window, table=table, account_id=account_id)  # type: ignore[call-arg]
    except TypeError:
        try:
            metrics = repo.step_metrics(journey.name, window, table=table)  # type: ignore[call-arg]
        except TypeError:
            metrics = repo.step_metrics(journey.name, window)
    return score_steps(metrics, threshold=threshold)


def event_page(repo: EventRepository, journey: JourneyDefinition, *, limit: int, after: tuple[str, str] | None,
               step_id: str | None, event_type: str | None, table: str | None = None, account_id: str | None = None) -> list[dict[str, Any]]:
    try:
        return repo.events_page(journey.name, limit=limit, after=after, step_id=step_id, event_type=event_type, table=table, account_id=account_id)  # type: ignore[call-arg]
    except TypeError:
        try:
            return repo.events_page(journey.name, limit=limit, after=after, step_id=step_id, event_type=event_type, table=table)  # type: ignore[call-arg]
        except TypeError:
            return repo.events_page(journey.name, limit=limit, after=after, step_id=step_id, event_type=event_type)
