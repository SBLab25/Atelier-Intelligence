import datetime
import logging

from fastmcp import FastMCP

from cji.config import REPORTS_DIR
from cji.guardrails.sanitiser import sanitise_for_llm
from cji.integrations import GatewayError, LLMGateway, LLMRequest, RunContext, new_correlation_id
from cji.reporting import SCHEMA, ReportInputError, ReportOutputError, parse_input, render, report_filename, write_report

logger = logging.getLogger(__name__)

# Initialise FastMCP
mcp = FastMCP("cji-report")

MAX_NARRATIVE_CHARS = 4000

# LLM access goes through the gateway only (Spec 08).
_llm: LLMGateway | None = None


def llm_gateway() -> LLMGateway:
    global _llm
    if _llm is None:
        _llm = LLMGateway.from_settings("cji-report")
    return _llm


@mcp.tool()
async def generate_narrative(insights: list, journey_name: str, avg_score: float, critical_count: int, mode: str,
                             run_context: dict | None = None) -> dict:
    """
    Generates a 3-paragraph CIO executive summary using LLM.

    Returns {"narrative", "generated_at", "llm"}; the deterministic paragraph is used whenever the LLM
    result is unavailable or empty. `run_context`: correlation id and remaining run budget (Spec 08).
    """
    
    system_prompt = """
You are a senior management consultant writing a 3-paragraph executive summary 
for a CIO. Use business language only. Do not use technical terms like 'score', 
'DuckDB', 'MCP', or 'API'. Focus on user impact, business cost, and strategic fix priority.

Required output: exactly 3 paragraphs:
1. Business impact — how friction affects completion, revenue, user trust
2. Root causes — what types of problems exist (UX/process/system/data), without jargon
3. Recommendations — top 3 prioritised actions with expected outcomes

Return ONLY plain text, no markdown, no json formatting.
"""

    # Pre-LLM guardrail: insights pass through the same sanitiser as friction scores (Spec 08, OD-63).
    safe_insights = [sanitise_for_llm(i) for i in insights if isinstance(i, dict)]
    user_prompt = f"""
Journey: {journey_name}
Analysis Mode: {mode}
Average Friction: {avg_score}/100
Critical Issues: {critical_count}

Identified Insights:
"""
    for idx, inc in enumerate(safe_insights[:5]): # Up to top 5
        user_prompt += f"{idx+1}. {inc.get('title', '')} (Category: {inc.get('category', 'unknown')})\n"
        user_prompt += f"   Cause: {inc.get('root_cause', '')}\n"
        user_prompt += f"   Recommendation: {inc.get('suggested_fix', '')}\n\n"

    generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fallback = f"This analysis of the {journey_name} journey identified {critical_count} critical friction point(s) with an average friction score of {avg_score:.1f}/100. We recommend immediate investigation of the top-priority findings detailed in the table below."

    ctx = RunContext.from_arg(run_context, new_correlation_id())
    request = LLMRequest(purpose="narrative", system=system_prompt, user=user_prompt, response_format="text")
    try:
        result = await llm_gateway().complete(request, ctx)
    except GatewayError as exc:
        logger.warning("narrative: LLM result unavailable (%s); using the fallback paragraph", exc.code)
        info = exc.info.model_copy(update={"outcome": "fallback"}).model_dump() if exc.info else {
            "outcome": "fallback", "code": exc.code}
        return {"narrative": fallback, "generated_at": generated_at, "llm": info}

    narrative = result.text.strip()[:MAX_NARRATIVE_CHARS]
    if not narrative:
        logger.warning("narrative: LLM returned empty text; using the fallback paragraph")
        info = result.info.model_copy(update={"outcome": "fallback", "code": "empty_response"}).model_dump()
        return {"narrative": fallback, "generated_at": generated_at, "llm": info}
    return {"narrative": narrative, "generated_at": generated_at, "llm": result.info.model_dump()}

def _failure(message: str, code: str) -> dict:
    return {"report_path": None, "file_size_kb": 0, "error": message, "code": code}


@mcp.tool()
def export_report(journey_name: str, narrative: str, friction_scores: list, insights: list, funnel_data: list,
                  mode: str, run_id: str = "", generated_at: str = "", narrative_source: str = "unknown",
                  narrative_model: str = "") -> dict:
    """
    Validates the input, renders the self-contained HTML report and writes it (Spec 10).

    All values are untrusted: they are checked against the report contract, cleaned, limited and escaped
    (reporting/). The file is `cji_report_{journey slug}_{run_id or input hash}.html` in the reports
    directory, written atomically; the same input gives the same bytes and the same file. Failures return
    report_path None with `code`: report_invalid_input, report_too_large or report_write_failed.
    """
    try:
        inp = parse_input({
            "journey_name": journey_name, "narrative": narrative, "friction_scores": friction_scores,
            "insights": insights, "funnel_data": funnel_data, "mode": mode, "run_id": run_id,
            "generated_at": generated_at, "narrative_source": narrative_source, "narrative_model": narrative_model,
        })
    except ReportInputError as exc:
        logger.warning("export_report: %s", exc)
        return _failure(str(exc), "report_invalid_input")
    try:
        path, digest, size = write_report(render(inp), REPORTS_DIR, report_filename(inp))
    except ReportOutputError as exc:
        logger.error("export_report: %s: %s", exc.code, exc)
        return _failure(str(exc), exc.code)
    return {"report_path": str(path), "file_size_kb": round(size / 1024, 2), "sha256": digest, "schema": SCHEMA}

if __name__ == "__main__":
    from cji.mcp_servers._serve import serve

    serve(mcp, "cji-report")
