"""
CJI Agent State Definition
===========================
CJIState is the single shared state structure for all LangGraph graph nodes.

Rules:
  - Import ONLY stdlib, langchain_core/langgraph and the pure domain/ package.
  - This module must be importable without config.py, database, or LLM.
  - All keys in CJIState must be present in the initial_state dict
    passed to graph.stream().
  - The `messages` field uses the add_messages reducer (append-only).
  - `errors` and `worker_statuses` are append-only (Spec 09, F-33): nodes return only their new entries.
  - `run` is the typed run record; its reducer applies status changes through domain.runs.transition().
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from cji.domain.events import EventRecord
from cji.domain.insights import Insight
from cji.domain.metrics import FrictionScore, StepMetrics
from cji.domain.runs import IngestionResult, RunRecord, WorkerStatus, WorkflowError, merge_run


# ── Sub-types ──────────────────────────────────────────────────────────────────
# Defined once in domain/ (Spec 03) and re-exported under their old names.
JourneyEvent = EventRecord      # a stored event (tracker, Parquet, file ingestion)

__all__ = [
    "CJIState",
    "FrictionScore",
    "IngestionResult",
    "Insight",
    "JourneyEvent",
    "RunRecord",
    "StepMetrics",
    "WorkerStatus",
    "WorkflowError",
]


# ── Main State ────────────────────────────────────────────────────────────────
class CJIState(TypedDict):
    """
    Shared state for all LangGraph graph nodes.

    Written by:
      - Initial call of graph.stream(): all IDENTITY and CONFIGURATION keys
      - supervisor:      iteration, next_worker
      - ingestion_worker:  ingestion_results, ingestion_pending_review
      - data_worker:     raw_events, event_summary, live_event_count
      - friction_worker: friction_scores, critical_steps
      - insight_worker:  insights, prioritized_fixes
      - report_worker:   report_path, narrative
      - insight_worker, report_worker: llm_usage (Spec 08)
      - All workers:     messages (via add_messages), worker_statuses, errors (appended)
      - cji.workflow.step / supervisor / cji.workflow.runtime: run (Spec 09)
    """

    # ── IDENTITY (set once at graph.stream() init) ──────────────────────────
    mode:          str          # "demo" | "realtime"
    journey_name:  str          # e.g. "onboarding"
    journey_steps: list[str]    # ordered list of step_ids

    # ── CONFIGURATION (set once at graph.stream() init) ─────────────────────
    analysis_window_days: int   # how many days back (demo mode)
    analysis_window_mins: int   # how many minutes back (realtime mode)
    collector_url:        str   # e.g. "http://localhost:8000"

    # ── ORCHESTRATION (updated by supervisor on every call) ──────────────────
    iteration:      int         # monotonically increasing (safety cutoff guard)
    next_worker:    str         # routing target — read by route() function
    human_approved: bool        # approval gate — set True to resume after pause
    last_run_at:    str         # ISO-8601 timestamp of last supervisor execution

    # ── COMMUNICATION (append-only via add_messages reducer) ─────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── INGESTION PHASE (written by ingestion_worker — runs before data_worker) ───
    ingestion_results:        list[IngestionResult]  # one per file ingested this run
    ingestion_pending_review: list[dict]             # low-confidence mappings awaiting human approval
    ingestion_pending_files:  list[dict]

    # ── DATA PHASE (written by data_worker) ──────────────────────────────────
    raw_events:       list[JourneyEvent]   # sample of raw events for debugging
    event_summary:    dict                 # {step_metrics, funnel, system_info}
    live_event_count: int                  # realtime: total events in window

    # ── ANALYSIS PHASE (written by friction_worker) ───────────────────────────
    friction_scores: list[FrictionScore]
    critical_steps:  list[str]             # step_ids above FRICTION_SCORE_THRESHOLD

    # ── INSIGHT PHASE (written by insight_worker) ─────────────────────────────
    insights:         list[Insight]
    prioritized_fixes: list[dict]          # ranked list from rank_all_fixes

    # ── DELIVERY PHASE (written by report_worker) ─────────────────────────────
    report_path: str    # absolute path to generated HTML report (empty = not yet generated)
    narrative:   str    # CIO-level 3-paragraph summary text

    # ── LLM USAGE (Spec 08; written by insight_worker and report_worker) ─────
    llm_usage: dict     # {calls, input_tokens, output_tokens, cost_usd} for this run's budget

    # ── OPERATIONS (append-only by convention) ─────────────────────────────────
    worker_statuses: Annotated[list[WorkerStatus], operator.add]   # append-only (Spec 09)
    errors:          Annotated[list[WorkflowError], operator.add]  # {"worker", "error", "ts", ...}

    # RUN RECORD (Spec 09): run_id, status, steps, failure
    run: Annotated[RunRecord, merge_run]
