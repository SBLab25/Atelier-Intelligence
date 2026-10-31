"""
Insight and report contracts (Spec 03, RC-07/RC-08). Pure module.

Lifecycle: InsightDraft (guardrail output, optional insight_id)
           -> Insight (after prioritise_fix: priority, priority_score, score)
           -> RankedFix (rank_all_fixes, read back from the vector store).
"""
from typing import Annotated, Literal, NotRequired, get_args

from pydantic import Field, TypeAdapter
from typing_extensions import TypedDict

from .journeys import StepId

InsightCategory = Literal["UX", "data", "system", "process", "unknown"]
FixEffort = Literal["low", "medium", "high"]
INSIGHT_CATEGORIES: frozenset[str] = frozenset(get_args(InsightCategory))
FIX_EFFORTS: frozenset[str] = frozenset(get_args(FixEffort))

NonEmptyText = Annotated[str, Field(min_length=1)]
Priority = Annotated[int, Field(ge=1, le=5)]       # 1 = highest
PriorityScore = Annotated[float, Field(ge=0)]       # impact / effort


class _InsightFields(TypedDict):
    step_id: StepId
    title: NonEmptyText
    root_cause: str
    category: InsightCategory
    evidence: list[str]
    suggested_fix: str
    fix_effort: FixEffort


class InsightDraft(_InsightFields):
    """Output of guardrails.output_validator (and generate_insight, which adds insight_id)."""

    insight_id: NotRequired[str]


class Insight(_InsightFields):
    """An insight after prioritise_fix."""

    insight_id: NonEmptyText
    priority: Priority
    priority_score: PriorityScore
    score: Annotated[int, Field(ge=0, le=100)]   # friction score that triggered it


class RankedFix(TypedDict):
    insight_id: NonEmptyText
    step_id: StepId
    title: str
    root_cause: str
    suggested_fix: str
    priority_score: PriorityScore
    priority: Priority
    fix_effort: FixEffort
    category: InsightCategory


class Narrative(TypedDict):
    """Output of generate_narrative."""

    narrative: str
    generated_at: str


class ReportResult(TypedDict):
    """
    Output of export_report. On success: report_path, file_size_kb, sha256 and schema (Spec 10).
    On failure report_path is None, error is set and code is report_invalid_input, report_too_large or
    report_write_failed.
    """

    report_path: str | None
    file_size_kb: Annotated[float, Field(ge=0)]
    error: NotRequired[str]
    code: NotRequired[str]
    sha256: NotRequired[str]
    schema: NotRequired[str]


INSIGHT_DRAFT: TypeAdapter[InsightDraft] = TypeAdapter(InsightDraft)
INSIGHT: TypeAdapter[Insight] = TypeAdapter(Insight)
INSIGHTS: TypeAdapter[list[Insight]] = TypeAdapter(list[Insight])
RANKED_FIXES: TypeAdapter[list[RankedFix]] = TypeAdapter(list[RankedFix])
NARRATIVE: TypeAdapter[Narrative] = TypeAdapter(Narrative)
REPORT_RESULT: TypeAdapter[ReportResult] = TypeAdapter(ReportResult)
