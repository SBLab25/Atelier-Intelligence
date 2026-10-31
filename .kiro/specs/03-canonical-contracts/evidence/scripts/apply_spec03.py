"""
Spec 03 patch script. Every anchor must match exactly once (or the stated count)
before anything is written; files keep their existing newline style and UTF-8.
Run from anywhere:  python apply_spec03.py
"""
import pathlib
import sys

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
EDITS: dict[str, list[tuple[str, str]]] = {}
REWRITES: dict[str, str] = {}


def edit(rel: str, old: str, new: str) -> None:
    EDITS.setdefault(rel, []).append((old, new))


# ───────────────────────────── collector/models.py (full rewrite) ─────────────
REWRITES["collector/models.py"] = '''"""
CJI Collector - validation models
=================================
The browser event contracts are defined once in domain/events.py (Spec 03) and
re-exported here so existing imports keep working:

    ALLOWED_EVENT_TYPES, TrackerEvent, EventBatch

The response models below are not used by collector/api.py yet. The collector
response contract belongs to Spec 07; they are kept, inactive, until then.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from domain.events import ALLOWED_EVENT_TYPES, EventBatch, TrackerEvent

__all__ = [
    "ALLOWED_EVENT_TYPES",
    "TrackerEvent",
    "EventBatch",
    "CollectResponse",
    "HealthResponse",
    "LiveStepStats",
    "LiveStatsResponse",
]


# ── Response models (inactive until Spec 07) ──────────────────────────────────

class CollectResponse(BaseModel):
    """Response for POST /collect/batch."""
    accepted:  int = Field(..., description="Number of events successfully stored")
    rejected:  int = Field(default=0, description="Number of events rejected (duplicates)")
    errors:    int = Field(default=0, description="Number of events that caused errors")
    message:   str = Field(default="OK")


class HealthResponse(BaseModel):
    """Response for GET /health."""
    status:            str  = Field(..., description="'ok' or 'error'")
    mode:              str  = Field(..., description="'demo' or 'realtime'")
    live_events_count: int  = Field(default=0, description="Total events in live_events table")
    version:           str  = Field(default="2.0")


class LiveStepStats(BaseModel):
    """Per-step event counts for one step in the live feed."""
    step_id:     str
    event_count: int
    user_count:  int


class LiveStatsResponse(BaseModel):
    """Response for GET /live/stats."""
    steps:        list[LiveStepStats]
    total_events: int
    window_mins:  int
'''

# ───────────────────────────── collector/api.py ───────────────────────────────
edit("collector/api.py", "from typing import List, Optional, Tuple\n", "from typing import Optional\n")
edit("collector/api.py",
     "    ROOT,\n)\n",
     "    ROOT,\n)\nfrom domain.events import EventBatch, to_live_events_row\n")
edit("collector/api.py", '''# ─── MODELS ───────────────────────────────────────────────────────────────
class EventItem(BaseModel):
    timestamp: str
    event_id: str
    session_id: str
    user_id: str
    journey_name: str
    step_id: str
    event_type: str
    url: str
    element_selectors: Optional[str] = None
    metadata: dict

class BatchPayload(BaseModel):
    api_key: str
    events: List[EventItem]

class AdminKeyCreate(BaseModel):''', '''# ─── MODELS ───────────────────────────────────────────────────────────────
# Browser events are validated with domain.events.EventBatch / TrackerEvent (Spec 03).
class AdminKeyCreate(BaseModel):''')
edit("collector/api.py", "def write_events(payload: BatchPayload):", "def write_events(payload: EventBatch):")
edit("collector/api.py", '''                    conn.execute(query, {
                        "timestamp": event.timestamp,
                        "event_id": event.event_id,
                        "session_id": event.session_id,
                        "user_id": event.user_id,
                        "journey_name": event.journey_name,
                        "step_id": event.step_id,
                        "event_type": event.event_type,
                        "url": event.url,
                        "element_selectors": event.element_selectors,
                        "metadata": json.dumps(event.metadata)
                    })''', '''                    conn.execute(query, to_live_events_row(event))''')
edit("collector/api.py",
     "def collect_batch(payload: BatchPayload, background_tasks",
     "def collect_batch(payload: EventBatch, background_tasks")
edit("collector/api.py", "import json\nimport logging\n", "import logging\n")

# ───────────────────────────── ingestion_intelligence_server.py ───────────────
ING = "mcp_servers/ingestion_intelligence_server.py"
edit(ING, "    logger,\n)\n\n# ── Server setup", '''    logger,
)
from domain.events import ALLOWED_EVENT_TYPES, EVENT_RECORD, EventType, sanitise_url

# ── Server setup''')
edit(ING, "from typing import Any\n", "from typing import Any, get_args\n")
edit(ING, '''    "allowed_event_types": [
        "page_view", "click", "form_submit", "error",
        "rage_click", "abandon", "step_complete", "identify",
    ],''', '''    # Taxonomy from domain/events.py, in declaration order (Spec 03, RC-04).
    "allowed_event_types": list(get_args(EventType)),''')
edit(ING, '''ALLOWED_EVENT_TYPES = set(CANONICAL_SCHEMA["allowed_event_types"])

# ── Pydantic validation model (mirrors collector/models.py) ───────────────────
class CanonicalEvent(BaseModel):''', '''# ALLOWED_EVENT_TYPES is re-exported from domain.events (single definition).

# ── File-ingestion adapter (Spec 03, design §4) ───────────────────────────────
# Third-party files use their own event names, so this adapter coerces unknown
# event types to "page_view" (documented behaviour) instead of rejecting them.
# apply_mapping() counts every coercion (records_coerced) and checks each output
# record against domain.events.EventRecord. Replaced by repositories in Spec 05.
class CanonicalEvent(BaseModel):''')
edit(ING, '''    """Strip query params and fragments from URL — mirrors collector guardrail."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(str(url))
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    except Exception:
        return ""''', '''    """Strip query params and fragments from URL (domain.events.sanitise_url)."""
    if not url:
        return ""
    return sanitise_url(str(url))''')
edit(ING, '''    # event_type — coerce unrecognised values
    if "event_type" in df.columns:
        df["event_type"] = df["event_type"].astype(str).apply(
            lambda v: v if v in ALLOWED_EVENT_TYPES else "page_view"
        )
    else:
        df["event_type"] = "page_view"''', '''    # event_type — coerce unrecognised values (documented adapter behaviour), counted
    records_coerced = 0
    if "event_type" in df.columns:
        raw_types = df["event_type"].astype(str)
        unknown = ~raw_types.isin(ALLOWED_EVENT_TYPES)
        records_coerced = int(unknown.sum())
        df["event_type"] = raw_types.where(~unknown, "page_view")
    else:
        df["event_type"] = "page_view"''')
edit(ING, '''            evt = CanonicalEvent(**{k: row.get(k, "") for k in CANONICAL_SCHEMA["canonical_fields"]})
            records_passed.append(evt.model_dump())''', '''            evt = CanonicalEvent(**{k: row.get(k, "") for k in CANONICAL_SCHEMA["canonical_fields"]})
            record = evt.model_dump()
            EVENT_RECORD.validate_python(record)   # adapter output must be a stored EventRecord
            records_passed.append(record)''')
edit(ING, '''    log.info(f"apply_mapping: {len(records_passed)} passed, {len(records_failed)} failed")

    return {
        "records_total":    len(df),
        "records_passed":   len(records_passed),
        "records_failed":   len(records_failed),''', '''    log.info(f"apply_mapping: {len(records_passed)} passed, {len(records_failed)} failed, "
             f"{records_coerced} event types coerced to page_view")

    return {
        "records_total":    len(df),
        "records_passed":   len(records_passed),
        "records_failed":   len(records_failed),
        "records_coerced":  records_coerced,''')
edit(ING, '''        "records_skipped": transform_result["records_failed"],
        "destination":     destination,''', '''        "records_skipped": transform_result["records_failed"],
        "records_coerced": transform_result["records_coerced"],
        "destination":     destination,''')

# ───────────────────────────── tools/ingest_json.py ───────────────────────────
IJ = "tools/ingest_json.py"
edit(IJ, "from sqlalchemy import create_engine\n", "from sqlalchemy import create_engine\n\nfrom domain.events import ALLOWED_EVENT_TYPES\nfrom domain.journeys import journey_from_config\n")
edit(IJ, '''VALID_EVENT_TYPES = frozenset({
    "page_view", "click", "form_submit", "error",
    "rage_click", "abandon", "step_complete", "identify", "drop_off",
    "session_start", "session_end", "scroll",
})''', '''# The domain taxonomy is the only list of event types (Spec 03, RC-05).
VALID_EVENT_TYPES = ALLOWED_EVENT_TYPES

# Source-specific event names with a canonical equivalent. Any other type outside
# the taxonomy is skipped (and counted in the log) by _finalise().
EVENT_TYPE_ALIASES: dict[str, str] = {
    "drop_off":      "abandon",
    "session_start": "page_view",
}''')
edit(IJ, 'JOURNEY_DEFAULT = JOURNEY_CONFIG["name"]', 'JOURNEY_DEFAULT = journey_from_config(JOURNEY_CONFIG).name')
edit(IJ, '''    df["event_type"]  = df["event_type"].astype(str)
''', '''    df["event_type"]  = df["event_type"].astype(str).str.strip().str.lower().replace(EVENT_TYPE_ALIASES)
    unknown_type = ~df["event_type"].isin(VALID_EVENT_TYPES)
    if unknown_type.any():
        logger.warning(f"{int(unknown_type.sum()):,} rows had event types outside the CJI taxonomy — skipped")
        df = df.loc[~unknown_type].reset_index(drop=True)
''')

# ───────────────────────────── state.py ───────────────────────────────────────
edit("state.py", '''Rules:
  - Import ONLY stdlib + langchain_core here (NO project imports).''', '''Rules:
  - Import ONLY stdlib, langchain_core/langgraph and the pure domain/ package.''')
edit("state.py", '''from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
''', '''from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from domain.events import EventRecord
from domain.insights import Insight
from domain.metrics import FrictionScore, StepMetrics
from domain.runs import IngestionResult, WorkerStatus, WorkflowError
''')


def _between(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


STATE_SUBTYPES_START = "# ── Sub-types"
STATE_SUBTYPES_END = "# ── Main State"
STATE_SUBTYPES_NEW = '''# ── Sub-types ──────────────────────────────────────────────────────────────────
# Defined once in domain/ (Spec 03) and re-exported under their old names.
JourneyEvent = EventRecord      # a stored event (tracker, Parquet, file ingestion)

__all__ = [
    "CJIState", "JourneyEvent", "StepMetrics", "FrictionScore", "Insight",
    "WorkerStatus", "IngestionResult", "WorkflowError",
]


'''
edit("state.py", "    errors:          list[dict]             # {\"worker\": str, \"error\": str, \"ts\": str}",
                 "    errors:          list[WorkflowError]    # {\"worker\": str, \"error\": str, \"ts\": str}")

# ───────────────────────────── guardrails/output_validator.py ─────────────────
OV = "guardrails/output_validator.py"
edit(OV, '''from config import JOURNEY_CONFIG

VALID_STEPS = set(JOURNEY_CONFIG.get("steps", []))
VALID_CATEGORIES = {"UX", "data", "system", "process", "unknown"}
VALID_EFFORTS = {"low", "medium", "high"}''', '''from config import JOURNEY_CONFIG
from domain.insights import FIX_EFFORTS, INSIGHT_CATEGORIES
from domain.journeys import journey_from_config

VALID_STEPS = set(journey_from_config(JOURNEY_CONFIG).steps)
VALID_CATEGORIES = INSIGHT_CATEGORIES   # single definition in domain/insights.py
VALID_EFFORTS = FIX_EFFORTS''')

# ───────────────────────────── agents/supervisor.py ───────────────────────────
SUP = "agents/supervisor.py"
edit(SUP, '''from config import MAX_AGENT_ITERATIONS

logger = logging.getLogger("cji.supervisor")

# Every target route() may return. Must equal graph.py's conditional edge map
# (enforced by tests/test_p0_security.py::test_u4_valid_workers_matches_graph_edges).
VALID_WORKERS: frozenset = frozenset({
    "ingestion_worker",
    "data_worker",
    "friction_worker",
    "insight_worker",
    "report_worker",
    "__end__",
})
''', '''from config import MAX_AGENT_ITERATIONS
from domain.runs import VALID_WORKERS, workflow_error

logger = logging.getLogger("cji.supervisor")

# VALID_WORKERS (every target route() may return) is defined in domain/runs.py
# and re-exported here; it must equal graph.py's conditional edge map.
__all__ = ["VALID_WORKERS", "route", "supervisor"]
''')
edit(SUP, '''            "errors": [
                f"supervisor: Max iterations ({MAX_AGENT_ITERATIONS}) exceeded"
            ],''', '''            "errors": [
                workflow_error("supervisor", f"Max iterations ({MAX_AGENT_ITERATIONS}) exceeded")
            ],''')

# ───────────────────────────── agents/workers.py ──────────────────────────────
W = "agents/workers.py"
edit(W, '''  - worker_statuses is always appended (never overwritten).
"""''', '''  - worker_statuses is always appended (never overwritten).
  - MCP results are checked against domain/ contracts in check-only mode
    (Spec 03, RC-10): values pass through unchanged; a violation becomes an
    `errors` entry instead of an exception.
"""''')
edit(W, '''from tools.mcp_client import mcp_session, call_tool
''', '''from domain.insights import INSIGHTS, NARRATIVE, RANKED_FIXES, REPORT_RESULT
from domain.metrics import FRICTION_SCORES, FUNNEL_STEPS, STEP_METRICS_LIST
from domain.runs import WorkflowError
from domain.validation import check
from tools.mcp_client import mcp_session, call_tool
''')
edit(W, '''logger = logging.getLogger("cji.workers")
''', '''logger = logging.getLogger("cji.workers")


def _contract_errors(*found: WorkflowError | None) -> Dict[str, Any]:
    """{"errors": [...]} for contract violations found at a worker boundary, else {}."""
    errors = [e for e in found if e is not None]
    for e in errors:
        logger.warning(f"{e['worker']}: {e['error']}")
    return {"errors": errors} if errors else {}
''')
edit(W, '''            "messages": [AIMessage(
                content=f"[data_worker] Collected metrics for {n_steps} steps "
                        f"({total_events} events, {mode} mode)"
            )],
        }''', '''            "messages": [AIMessage(
                content=f"[data_worker] Collected metrics for {n_steps} steps "
                        f"({total_events} events, {mode} mode)"
            )],
            **_contract_errors(
                check(STEP_METRICS_LIST, event_summary["step_metrics"], "data_worker", "step metrics"),
                check(FUNNEL_STEPS, event_summary["funnel"], "data_worker", "funnel"),
            ),
        }''')
edit(W, '''            "messages": [AIMessage(
                content=f"[friction_worker] {len(scores)} steps scored, "
                        f"{len(critical)} above threshold: {critical}"
            )],
        }''', '''            "messages": [AIMessage(
                content=f"[friction_worker] {len(scores)} steps scored, "
                        f"{len(critical)} above threshold: {critical}"
            )],
            **_contract_errors(check(FRICTION_SCORES, scores, "friction_worker", "friction scores")),
        }''')
edit(W, '''            "messages": [AIMessage(
                content=f"[insight_worker] {len(prioritised)} insights generated and stored"
            )],
        }''', '''            "messages": [AIMessage(
                content=f"[insight_worker] {len(prioritised)} insights generated and stored"
            )],
            **_contract_errors(
                check(INSIGHTS, prioritised, "insight_worker", "insights"),
                check(RANKED_FIXES, ranked_fixes, "insight_worker", "ranked fixes"),
            ),
        }''')
edit(W, '''            report_path = report_result.get("report_path", "")
            file_size = report_result.get("file_size_kb", 0)
''', '''            report_path = report_result.get("report_path", "")
            file_size = report_result.get("file_size_kb", 0)

        contract = _contract_errors(
            check(NARRATIVE, narrative_result, "report_worker", "narrative"),
            check(REPORT_RESULT, report_result, "report_worker", "report result"),
        )
''')
edit(W, '''            "messages": [AIMessage(
                content=f"[report_worker] HTML report generated → {report_path}"
            )],
        }''', '''            "messages": [AIMessage(
                content=f"[report_worker] HTML report generated → {report_path}"
            )],
            **contract,
        }''')

# ───────────────────────────── config.py / .env.example ───────────────────────
edit("config.py", 'JOURNEY_NAME: str = os.getenv("JOURNEY_NAME", "onboarding")',
                  'JOURNEY_NAME: str = os.getenv("JOURNEY_NAME", "user_onboarding")  # matches data/events.parquet (Spec 03, OD-9b)')

# ───────────────────────────── tests/test_agent_layer.py ──────────────────────
edit("tests/test_agent_layer.py",
     'assert any("Max iterations" in e for e in result.get("errors", []))',
     'assert any("Max iterations" in e["error"] for e in result.get("errors", []))  # WorkflowError dicts (Spec 03, RC-11)')


def main() -> int:
    planned: dict[pathlib.Path, tuple[str, str]] = {}
    problems: list[str] = []
    for rel, new_text in REWRITES.items():
        path = APP / rel
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        planned[path] = (raw, new_text.replace("\n", nl))
    for rel, pairs in EDITS.items():
        path = APP / rel
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw
        for old, new in pairs:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            count = text.count(o)
            if count != 1:
                problems.append(f"{rel}: anchor found {count}x: {old[:70]!r}")
                continue
            text = text.replace(o, n)
        if rel == "state.py":
            start, end = STATE_SUBTYPES_START, STATE_SUBTYPES_END
            if text.count(start) == 1 and text.count(end) == 1:
                text = text.replace(_between(text, start, end), STATE_SUBTYPES_NEW.replace("\n", nl))
            else:
                problems.append("state.py: sub-type block anchors not unique")
        planned[path] = (raw, text)
    env_example = APP / ".env.example"
    raw = env_example.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    hits = [i for i, line in enumerate(lines) if line.startswith("JOURNEY_NAME=")]
    if len(hits) != 1:
        problems.append(f".env.example: JOURNEY_NAME lines = {len(hits)}")
    else:
        lines[hits[0]] = "JOURNEY_NAME=user_onboarding"
        planned[env_example] = (raw, nl.join(lines))
    if problems:
        print("NOT APPLIED:\n" + "\n".join(problems))
        return 1
    for path, (old, new) in planned.items():
        if old != new:
            path.write_bytes(new.encode("utf-8"))
            print(f"patched {path.relative_to(APP)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
