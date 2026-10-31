"""
CJI Async Worker Nodes
=======================
Four async workers that connect to MCP servers via mcp_session()/call_tool().

Rules:
  - Every worker is `async def` (LangGraph calls them with asyncio).
  - Every worker returns a dict merging back into CJIState.
  - Every return dict includes `next_worker: "supervisor"`.
  - Since Spec 09 every worker is wrapped by `workflow.step.step`: the body raises on failure and the
    wrapper retries retryable errors, applies the step timeout, and records the failure (error status,
    error entry, fallback fields, run.failure). Successful bodies return only their new
    worker_statuses / errors entries (the state appends them).
  - MCP results are checked against domain/ contracts in check-only mode
    (Spec 03, RC-10): values pass through unchanged; a violation becomes an
    `errors` entry instead of an exception.
  - Side effects are idempotent per run (Spec 09, OD-73): insight ids are derived from the run and step,
    the report file is named by the run.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

from cji.domain.insights import INSIGHTS, NARRATIVE, RANKED_FIXES, REPORT_RESULT
from cji.domain.metrics import FRICTION_SCORES, FUNNEL_STEPS, STEP_METRICS_LIST
from cji.domain.runs import WorkflowError, insight_id_for
from cji.domain.validation import check
from cji.integrations import GatewayError
from cji.integrations.audit import configured_secrets, scrub
from cji.integrations.context import current_run, run_or_new
from cji.integrations.usage import add_usage, run_context_arg
from cji.tools.mcp_client import mcp_session, call_tool
from cji.workflow.errors import StepError
from cji.workflow.step import step, utc_now

logger = logging.getLogger("cji.workers")


class ModeMismatch(StepError):
    """The journey-data server reads a different store than this run asked for (Spec 05, OD-33)."""

    code = "mode_mismatch"


def _contract_errors(*found: WorkflowError | None) -> dict[str, Any]:
    """{"errors": [...]} for contract violations found at a worker boundary, else {}."""
    errors = [e for e in found if e is not None]
    for e in errors:
        logger.warning(f"{e['worker']}: {e['error']}")
    return {"errors": errors} if errors else {}


def _error_text(exc: BaseException) -> str:
    """Error text for workflow state (F-30): gateway and step messages are safe by construction; others are scrubbed."""
    if isinstance(exc, GatewayError | StepError):
        return str(exc)            # F-32: this returned _error_text(exc) and recursed forever (Spec 08 defect)
    return f"{type(exc).__name__}: {scrub(str(exc), configured_secrets())[:300]}"


def _run_id() -> str:
    ctx = current_run()
    return ctx.correlation_id if ctx else run_or_new("worker").correlation_id


def _unwrap_insight(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Spec 08 tools return {"insight": ..., "llm": ...}; older servers and test fakes return the insight."""
    if isinstance(result.get("insight"), dict):
        return dict(result["insight"]), result.get("llm")
    return result, None


def _provenance(info: dict[str, Any] | None, generated_at: str = "") -> dict[str, Any]:
    """Where an LLM-backed result came from (Spec 14, OD-147), from the gateway metadata of its call.
    The model and provider are kept only when the model wrote the result (as for narrative_model, Spec 10)."""
    outcome = (info or {}).get("outcome") if isinstance(info, dict) else None
    source = {"ok": "llm", "fallback": "fallback"}.get(str(outcome), "not_recorded")
    llm = source == "llm" and isinstance(info, dict)
    return {
        "source": source,
        "model": (str(info.get("model") or "") or None) if llm and info else None,
        "provider": (str(info.get("provider") or "") or None) if llm and info else None,
        "reason": (str(info.get("code") or "") or None) if source == "fallback" and info else None,
        "generated_at": generated_at or utc_now(),
    }


def _unwrap_narrative(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Narrative result without the gateway metadata (checked against domain contracts as before)."""
    body = dict(result)
    info = body.pop("llm", None)
    return body, info if isinstance(info, dict) else None


# -- DATA WORKER ---------------------------------------------------------------------------------------
@step("data_worker", describe=_error_text,
      fallback=lambda: {"event_summary": {}, "raw_events": [], "live_event_count": 0})
async def data_worker(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Connects to cji-journey-data MCP server and collects:
      - System info (health-check)
      - Per-step metrics
      - Funnel drop-off
      - Sample raw events
    """
    mode = state.get("mode", "demo")
    days = state.get("analysis_window_days", 30)
    mins = state.get("analysis_window_mins", 60)

    async with mcp_session("cji-journey-data") as session:
        # 1. System info
        sys_info = await call_tool(session, "get_system_info")
        logger.info(f"System info: {sys_info.get('mode', 'unknown')} mode, "
                    f"{sys_info.get('total_events', 0)} events")

        # Never analyse a store other than the one this run asked for (Spec 05).
        server_mode = sys_info.get("mode")
        if server_mode and server_mode != mode:
            raise ModeMismatch(
                f"journey-data server runs in {server_mode} mode; this run is {mode}. "
                f"Restart the servers with: python run_servers.py --mode {mode}"
            )

        # The server's repository applies its own window semantics; send both values.
        window_args = {"days_back": days, "minutes_back": mins}

        # 2. Step metrics
        step_metrics = await call_tool(session, "get_step_metrics", window_args)

        # 3. Funnel drop-off
        funnel = await call_tool(session, "get_funnel_dropoff", window_args)

        # 4. Sample raw events
        raw_result = await call_tool(session, "query_events", {"limit": 50})
        raw_events = raw_result.get("events", [])

    # Build event_summary
    event_summary = {
        "step_metrics": step_metrics.get("step_metrics", []),
        "funnel": funnel.get("funnel", []),
        "system_info": sys_info,
    }

    total_events = sys_info.get("total_events", len(raw_events))
    n_steps = len(event_summary["step_metrics"])

    return {
        "event_summary":    event_summary,
        "raw_events":       raw_events[:50],  # cap at 50
        "live_event_count": total_events,
        "next_worker":      "supervisor",
        "worker_statuses":  [{
            "worker":  "data_worker",
            "status":  "success",
            "message": f"Collected {n_steps} step metrics, {total_events} events"
        }],
        "messages": [AIMessage(
            content=f"[data_worker] Collected metrics for {n_steps} steps "
                    f"({total_events} events, {mode} mode)"
        )],
        **_contract_errors(
            check(STEP_METRICS_LIST, event_summary["step_metrics"], "data_worker", "step metrics"),
            check(FUNNEL_STEPS, event_summary["funnel"], "data_worker", "funnel"),
        ),
    }


# -- FRICTION WORKER -----------------------------------------------------------------------------------
@step("friction_worker", describe=_error_text, fallback=lambda: {"friction_scores": [], "critical_steps": []})
async def friction_worker(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Connects to cji-friction-engine MCP server and scores all steps.
    """
    event_summary = state.get("event_summary", {})
    step_metrics = event_summary.get("step_metrics", [])

    if not step_metrics:
        raise StepError("No step_metrics in event_summary", code="no_step_metrics")

    async with mcp_session("cji-friction-engine") as session:
        # score_all_steps expects the list of step metric dicts
        result = await call_tool(
            session, "score_all_steps",
            {"all_step_metrics": step_metrics}
        )

    scores = result.get("scores", [])
    critical = [s["step_id"] for s in scores if s.get("is_critical", False)]

    return {
        "friction_scores": scores,
        "critical_steps":  critical,
        "next_worker":     "supervisor",
        "worker_statuses": [{
            "worker":  "friction_worker",
            "status":  "success",
            "message": f"Scored {len(scores)} steps, {len(critical)} critical"
        }],
        "messages": [AIMessage(
            content=f"[friction_worker] {len(scores)} steps scored, "
                    f"{len(critical)} above threshold: {critical}"
        )],
        **_contract_errors(check(FRICTION_SCORES, scores, "friction_worker", "friction scores")),
    }


# -- INSIGHT WORKER ------------------------------------------------------------------------------------
@step("insight_worker", describe=_error_text,
      fallback=lambda: {"insights": [], "prioritized_fixes": [], "insight_provenance": {}})
async def insight_worker(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Connects to cji-insight MCP server to generate root-cause analysis
    for each critical friction score, then prioritises and stores them.
    Insight ids are derived from the run and the step, so a retried or resumed step upserts
    the same records and ranks only this run's fixes (Spec 09).
    """
    friction_scores = state.get("friction_scores", [])
    critical_scores = [s for s in friction_scores if s.get("is_critical", False)]

    if not critical_scores:
        return {
            "insights":          [],
            "prioritized_fixes": [],
            "insight_provenance": {},
            "next_worker":       "supervisor",
            "worker_statuses":   [{
                "worker":  "insight_worker",
                "status":  "success",
                "message": "No critical steps — no insights generated"
            }],
            "messages": [AIMessage(
                content="[insight_worker] No critical steps found, skipping"
            )],
        }

    run_id = _run_id()
    usage = dict(state.get("llm_usage") or {})
    async with mcp_session("cji-insight") as session:
        insights = []
        provenance: dict[str, dict[str, Any]] = {}

        # 1. Generate insight per critical step
        for fs in critical_scores:
            result = await call_tool(
                session, "generate_insight",
                {"friction_score": fs, "run_context": run_context_arg(run_or_new("insight_worker"), usage)}
            )
            insight, info = _unwrap_insight(result)
            usage = add_usage(usage, info)
            # Carry the friction score into the insight; run-scoped id (Spec 09, OD-73)
            insight["score"] = fs.get("score", 0)
            insight["insight_id"] = insight_id_for(run_id, str(fs.get("step_id", insight.get("step_id", ""))))
            insight["run_id"] = run_id
            insights.append(insight)
            provenance[insight["insight_id"]] = _provenance(info)      # Spec 14, OD-147

        # 2. Prioritise each insight
        event_summary = state.get("event_summary", {})
        step_metrics = event_summary.get("step_metrics", [])
        # Build a quick lookup for unique_users per step
        users_map = {
            sm["step_id"]: sm.get("unique_users", 100)
            for sm in step_metrics
        }

        prioritised = []
        for ins in insights:
            unique_users = users_map.get(ins.get("step_id", ""), 100)
            pri = await call_tool(
                session, "prioritise_fix",
                {"insight": ins, "unique_users": unique_users}
            )
            prioritised.append(pri)

        # 3. Save each insight to ChromaDB (upsert by insight_id)
        for ins in prioritised:
            await call_tool(session, "save_insight", {"insight": ins})

        # 4. Get the ranked list for this run
        ranked = await call_tool(session, "rank_all_fixes", {"run_id": run_id})
        ranked_fixes = ranked.get("ranked_fixes", [])

    return {
        "insights":          prioritised,
        "prioritized_fixes": ranked_fixes,
        "insight_provenance": provenance,
        "llm_usage":         usage,
        "next_worker":       "supervisor",
        "worker_statuses":   [{
            "worker":  "insight_worker",
            "status":  "success",
            "message": f"Generated {len(prioritised)} insights, ranked {len(ranked_fixes)} fixes"
        }],
        "messages": [AIMessage(
            content=f"[insight_worker] {len(prioritised)} insights generated and stored"
        )],
        **_contract_errors(
            check(INSIGHTS, prioritised, "insight_worker", "insights"),
            check(RANKED_FIXES, ranked_fixes, "insight_worker", "ranked fixes"),
        ),
    }


# -- REPORT WORKER -------------------------------------------------------------------------------------
_REPORT_ERROR_CODES = frozenset({"report_invalid_input", "report_too_large", "report_write_failed"})


@step("report_worker", describe=_error_text,
      fallback=lambda: {"report_path": "", "narrative": "", "narrative_provenance": {}})
async def report_worker(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Connects to cji-report MCP server to generate the executive narrative
    and export the self-contained HTML report (one file per run, Spec 09).
    """
    insights = state.get("insights", [])
    friction_scores = state.get("friction_scores", [])
    event_summary = state.get("event_summary", {})
    funnel_data = event_summary.get("funnel", [])
    journey_name = state.get("journey_name", "onboarding")
    mode = state.get("mode", "demo")

    # Compute avg score and critical count
    if friction_scores:
        avg_score = sum(s.get("score", 0) for s in friction_scores) / len(friction_scores)
    else:
        avg_score = 0.0
    critical_count = len([s for s in friction_scores if s.get("is_critical", False)])

    usage = dict(state.get("llm_usage") or {})
    async with mcp_session("cji-report") as session:
        # 1. Generate executive narrative
        narrative_result = await call_tool(
            session, "generate_narrative",
            {
                "insights":       insights,
                "journey_name":   journey_name,
                "avg_score":      round(avg_score, 1),
                "critical_count": critical_count,
                "mode":           mode,
                "run_context":    run_context_arg(run_or_new("report_worker"), usage),
            }
        )
        narrative_result, info = _unwrap_narrative(narrative_result)
        usage = add_usage(usage, info)
        narrative = narrative_result.get("narrative", "")
        outcome = (info or {}).get("outcome")
        narrative_source = {"ok": "llm", "fallback": "fallback"}.get(str(outcome), "unknown")
        narrative_provenance = _provenance(info, str(narrative_result.get("generated_at") or ""))

        # 2. Export HTML report (file named by run: a retry overwrites, never duplicates)
        report_result = await call_tool(
            session, "export_report",
            {
                "journey_name":   journey_name,
                "narrative":      narrative,
                "friction_scores": friction_scores,
                "insights":       insights,
                "funnel_data":    funnel_data,
                "mode":           mode,
                "run_id":         _run_id(),
                # Provenance (Spec 10, OD-88): when and how the narrative was produced.
                "generated_at":     str(narrative_result.get("generated_at") or ""),
                "narrative_source": narrative_source,
                # The model is recorded only when it wrote the narrative (not for the template fallback).
                "narrative_model":  str((info or {}).get("model") or "") if narrative_source == "llm" else "",
            }
        )
        report_path = report_result.get("report_path") or ""
        file_size = report_result.get("file_size_kb", 0)

    if not report_path:
        # Spec 10 (OD-90): the server's code says why; only a write failure is worth another attempt.
        code = str(report_result.get("code") or "")
        code = code if code in _REPORT_ERROR_CODES else "report_export_failed"
        raise StepError(f"report export failed ({code}): {str(report_result.get('error') or 'no report path')[:200]}",
                        code=code, retryable=code == "report_write_failed")

    contract = _contract_errors(
        check(NARRATIVE, narrative_result, "report_worker", "narrative"),
        check(REPORT_RESULT, report_result, "report_worker", "report result"),
    )

    return {
        "report_path": report_path,
        "narrative":   narrative,
        "narrative_provenance": narrative_provenance,
        "llm_usage":   usage,
        "next_worker": "supervisor",
        "worker_statuses": [{
            "worker":  "report_worker",
            "status":  "success",
            "message": f"Report exported ({file_size}KB) → {report_path}"
        }],
        "messages": [AIMessage(
            content=f"[report_worker] HTML report generated → {report_path}"
        )],
        **contract,
    }
