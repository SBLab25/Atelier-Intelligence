"""
Analytics contracts (Spec 03, RC-07/RC-08): step metrics, funnel and friction scores.

TypedDicts so runtime values stay plain dicts (LangGraph state and MCP JSON are
unchanged); the TypeAdapters are the validators. Pure module.
"""
from typing import Annotated, NotRequired

from pydantic import Field, TypeAdapter
from typing_extensions import TypedDict

from .journeys import JourneyId, StepId

NonNegInt = Annotated[int, Field(ge=0)]
NonNegFloat = Annotated[float, Field(ge=0)]
# Rates are event counts per unique user, so they are not capped at 100 %:
# the tracked demo data has completion_rate_pct of 114.98 and 100.43 on two steps
# (Spec 03 finding F-03; the metric definition belongs to the analytics Spec).
RatePct = NonNegFloat
Fraction = Annotated[float, Field(ge=0, le=1)]


class StepMetrics(TypedDict):
    """Per-step analytics from the Journey Data MCP (get_step_metrics)."""

    step_id: StepId
    unique_users: NonNegInt
    completion_rate_pct: RatePct
    abandon_rate_pct: RatePct
    error_rate_pct: RatePct
    avg_dwell_ms: NonNegFloat      # DuckDB returns an average, so a float
    avg_rage_clicks: NonNegFloat
    avg_retries: NonNegFloat


class FunnelStep(TypedDict):
    step_id: StepId
    users: NonNegInt
    drop_off_pct: float            # can be negative when a later step sees more users


class FunnelResult(TypedDict):
    """Output of get_funnel_dropoff."""

    journey_id: JourneyId
    funnel: list[FunnelStep]
    overall_completion_pct: float
    error: NotRequired[str]


class FrictionScore(TypedDict):
    """Friction Engine output for one step."""

    step_id: StepId
    score: Annotated[int, Field(ge=0, le=100)]   # higher = more friction
    drop_off_rate: NonNegFloat                  # abandon_rate_pct / 100 (not capped, see RatePct)
    avg_dwell_ms: NonNegInt
    retry_count: NonNegFloat
    rage_click_rate: NonNegFloat
    signals: list[str]                          # named friction indicators
    confidence: Fraction                        # 0.50-0.98 in practice
    is_critical: bool                           # score >= FRICTION_SCORE_THRESHOLD


STEP_METRICS: TypeAdapter[StepMetrics] = TypeAdapter(StepMetrics)
STEP_METRICS_LIST: TypeAdapter[list[StepMetrics]] = TypeAdapter(list[StepMetrics])
FUNNEL_STEPS: TypeAdapter[list[FunnelStep]] = TypeAdapter(list[FunnelStep])
FUNNEL_RESULT: TypeAdapter[FunnelResult] = TypeAdapter(FunnelResult)
FRICTION_SCORES: TypeAdapter[list[FrictionScore]] = TypeAdapter(list[FrictionScore])
