import json
import uuid
import logging
from typing import Union
from fastmcp import FastMCP
import chromadb

from cji.config import CHROMA_DIR

from cji.guardrails.sanitiser import sanitise_for_llm
from cji.guardrails.output_validator import validate_llm_output
from cji.integrations import GatewayError, LLMGateway, LLMRequest, RunContext, new_correlation_id

logger = logging.getLogger(__name__)

# Initialise FastMCP
mcp = FastMCP("cji-insight")

# ChromaDB Client Singleton
_chroma_client = None
_collection = None

def get_collection():
    global _chroma_client, _collection
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR.resolve()))
        # Ensure we use cosine similarity
        _collection = _chroma_client.get_or_create_collection(
            name="cji_insights",
            metadata={"hnsw:space": "cosine"}
        )
    return _collection


# LLM access goes through the gateway only (Spec 08): one provider, timeouts, retries, budgets, audit.
_llm: LLMGateway | None = None


def llm_gateway() -> LLMGateway:
    global _llm
    if _llm is None:
        _llm = LLMGateway.from_settings("cji-insight")
    return _llm


def _fallback_insight(step_id: str, friction_score: dict) -> dict:
    """Deterministic insight used whenever the LLM result is unavailable (unchanged since before Spec 08)."""
    return {
        "insight_id": str(uuid.uuid4()),
        "step_id": step_id,
        "title": f"Friction at {step_id}",
        "root_cause": "LLM analysis unavailable. Manual investigation required.",
        "category": "unknown",
        "evidence": friction_score.get("signals", []),
        "suggested_fix": "Review metrics manually.",
        "fix_effort": "medium"
    }


@mcp.tool()
async def generate_insight(friction_score: dict, run_context: dict | None = None) -> dict:
    """
    Generates LLM root cause analysis for a critical friction score.

    Returns {"insight": {...}, "llm": call metadata}. `run_context` carries the correlation id and the
    remaining run budget (Spec 08); without it a fresh correlation id and no run budget are used.
    """
    step_id = friction_score.get("step_id", "unknown")
    sanitised_score = sanitise_for_llm(friction_score)
    
    system_prompt = """
You are CJI, a customer journey analytics AI. Analyse the provided step metrics 
and return a JSON insight. Respond ONLY with valid JSON, no markdown, no explanation.

Required JSON schema:
{
  "title":        "Max 8 words describing the core issue",
  "root_cause":   "2-3 sentences explaining WHY this friction exists",
  "category":     "UX" | "data" | "system" | "process" | "unknown",
  "evidence":     ["list", "of", "supporting", "data", "points"],
  "suggested_fix": "1-2 sentences of actionable recommendation",
  "fix_effort":   "low" | "medium" | "high"
}

Categories:
  UX      → interface design, usability, form complexity
  data    → data quality, missing fields, validation logic
  system  → backend errors, timeouts, infrastructure
  process → business process, user task mismatch
  unknown → insufficient data to determine
"""
    
    # Render user prompt based on sanitised friction score
    user_prompt = f"""
Step: {step_id}
Signals: {", ".join(sanitised_score.get("signals", []))}
Abandon rate: {sanitised_score.get("drop_off_rate", sanitised_score.get("abandon_rate_pct", 0.0))}%
Error rate: {sanitised_score.get("error_rate_pct", 0.0)}%
Average dwell time: {sanitised_score.get("avg_dwell_ms", 0)}ms ({sanitised_score.get("avg_dwell_ms", 0) / 60000:.2f} minutes)
Rage clicks: {sanitised_score.get("rage_click_rate", sanitised_score.get("rage_clicks", 0.0))} per user
Retries: {sanitised_score.get("retry_count", sanitised_score.get("retries", 0.0))} per user
Confidence: {sanitised_score.get("confidence", 0.0)}
"""

    ctx = RunContext.from_arg(run_context, new_correlation_id())
    request = LLMRequest(purpose="insight", system=system_prompt, user=user_prompt, response_format="json")
    try:
        result = await llm_gateway().complete(request, ctx)
    except GatewayError as exc:
        logger.warning("insight for step %s: LLM result unavailable (%s); using the fallback insight",
                       step_id, exc.code)
        info = exc.info.model_copy(update={"outcome": "fallback"}).model_dump() if exc.info else {
            "outcome": "fallback", "code": exc.code}
        return {"insight": _fallback_insight(step_id, friction_score), "llm": info}

    insight = dict(result.data or {})
    insight["insight_id"] = str(uuid.uuid4())
    insight = validate_llm_output(insight, step_id)      # post-LLM guardrail (unchanged)
    return {"insight": insight, "llm": result.info.model_dump()}

@mcp.tool()
def prioritise_fix(insight: dict, unique_users: int) -> dict:
    """Computes priority ranking for an insight based on effort and impact."""
    effort_map = {"low": 1, "medium": 2, "high": 4}
    
    # Try getting score from insight, else default
    score = insight.get("score", 100)
    fix_effort = insight.get("fix_effort", "medium").lower()
    
    effort = effort_map.get(fix_effort, 2)
    impact = float(score) * unique_users
    
    # Priority score: Higher is more urgent/valuable
    priority_score = round(impact / effort, 1)
    
    # Map priority ranks 1 (highest) to 5 (lowest) roughly
    # We will compute a comparative rank later in rank_all_fixes, 
    # but for now we allocate a dummy default if absolute priority is needed.
    priority = 1
    if priority_score < 5000:
        priority = 5
    elif priority_score < 15000:
        priority = 4
    elif priority_score < 30000:
        priority = 3
    elif priority_score < 60000:
        priority = 2

    # Returns the updated insight with priority calculations
    result = dict(insight)
    result["priority"] = priority
    result["priority_score"] = priority_score
    return result

@mcp.tool()
def save_insight(insight: Union[str, dict]) -> dict:
    """
    Saves an insight to ChromaDB for semantic search. Upserts by insight_id (Spec 09, OD-73): saving the
    same insight again replaces it, so a retried or resumed workflow step never duplicates insights.
    """
    if isinstance(insight, str):
        try:
            insight = json.loads(insight)
        except json.JSONDecodeError:
            return {"status": "error", "error": "Invalid JSON string provided."}
            
    collection = get_collection()
    
    # Build the searchable document
    title = insight.get("title", "")
    root_cause = insight.get("root_cause", "")
    suggested_fix = insight.get("suggested_fix", "")
    document_string = f"{title}. {root_cause}. {suggested_fix}"
    
    # Build metadata (MUST ALL BE STRINGS for ChromaDB)
    # Ensure evidence is stored as a stringified list if needed, 
    # but we will serialize evidence to json str to fit in metadata.
    metadata = {
        "step_id": str(insight.get("step_id", "unknown")),
        "category": str(insight.get("category", "unknown")),
        "priority": str(insight.get("priority", "3")),
        "score": str(insight.get("score", "0")),
        "fix_effort": str(insight.get("fix_effort", "medium")),
        "evidence": json.dumps(insight.get("evidence", [])),
        "priority_score": str(insight.get("priority_score", "0.0")),
        "title": str(insight.get("title", "")),
        "root_cause": str(insight.get("root_cause", "")),
        "suggested_fix": str(insight.get("suggested_fix", "")),
        "run_id": str(insight.get("run_id", "")),
    }
    
    insight_id = insight.get("insight_id", str(uuid.uuid4()))
    
    try:
        collection.upsert(
            documents=[document_string],
            metadatas=[metadata],
            ids=[insight_id]
        )
        return {"status": "success", "insight_id": insight_id}
    except Exception as e:  # broad-except: vector-store boundary: structured error result
        logger.error(f"Failed to save insight to ChromaDB: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

@mcp.tool()
def search_insights(query: str, n_results: int = 5) -> dict:
    """Searches ChromaDB for previously generated insights."""
    collection = get_collection()
    
    count = collection.count()
    if count == 0:
        return {"results": [], "query": query, "error": "No insights stored yet"}
        
    actual_n = min(n_results, count)
    
    try:
        results = collection.query(
            query_texts=[query],
            n_results=actual_n,
            include=["documents", "metadatas", "distances"]
        )
        
        # Package the results nicely
        formatted_results = []
        if results and results.get("ids") and len(results["ids"]) > 0:
            for i in range(len(results["ids"][0])):
                meta = results["metadatas"][0][i] or {}
                # Recover original data from metadata string
                formatted_results.append({
                    "insight_id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "step_id": meta.get("step_id"),
                    "category": meta.get("category"),
                    "priority": int(meta.get("priority", "3")),
                    "score": int(meta.get("score", "0")),
                    "fix_effort": meta.get("fix_effort"),
                    "distance": results["distances"][0][i] if "distances" in results else None
                })
        
        return {
            "query": query,
            "results": formatted_results,
            "count": len(formatted_results)
        }
    except Exception as e:  # broad-except: vector-store boundary: structured error result
        logger.error(f"ChromaDB search failed: {e}", exc_info=True)
        return {"error": str(e), "results": []}

@mcp.tool()
def rank_all_fixes(run_id: str = "") -> dict:
    """
    Reads stored insights from ChromaDB and sorts by priority_score. With `run_id`, only that run's
    insights are ranked (Spec 09); without it, every stored insight is ranked (as before).
    """
    collection = get_collection()
    count = collection.count()
    
    if count == 0:
        return {"ranked_fixes": [], "total": 0}
        
    try:
        if run_id:
            all_results = collection.get(where={"run_id": run_id}, include=["metadatas", "documents"])
        else:
            all_results = collection.get(include=["metadatas", "documents"])
        
        fixes = []
        for i, insight_id in enumerate(all_results["ids"]):
            meta = all_results["metadatas"][i]
            priority_score = float(meta.get("priority_score", "0.0"))
            fixes.append({
                "insight_id": insight_id,
                "step_id": meta.get("step_id", "unknown"),
                "title": meta.get("title", ""),
                "root_cause": meta.get("root_cause", ""),
                "suggested_fix": meta.get("suggested_fix", ""),
                "priority_score": priority_score,
                "priority": int(meta.get("priority", "3")),
                "fix_effort": meta.get("fix_effort", "medium"),
                "category": meta.get("category", "unknown")
            })
            
        # Sort descending by priority_score
        fixes.sort(key=lambda x: x["priority_score"], reverse=True)
        
        return {
            "ranked_fixes": fixes,
            "total": len(fixes)
        }
    except Exception as e:  # broad-except: vector-store boundary: structured error result
        logger.error(f"Failed to rank fixes: {e}", exc_info=True)
        return {"error": str(e), "ranked_fixes": []}

if __name__ == "__main__":
    from cji.mcp_servers._serve import serve

    serve(mcp, "cji-insight")
