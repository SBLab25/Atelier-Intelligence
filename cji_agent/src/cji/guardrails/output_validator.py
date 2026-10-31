"""Output validation layer to guarantee LLM JSON meets semantic and structural requirements."""
from cji.config import JOURNEY_CONFIG
from cji.domain.insights import FIX_EFFORTS, INSIGHT_CATEGORIES
from cji.domain.journeys import journey_from_config

VALID_STEPS = set(journey_from_config(JOURNEY_CONFIG).steps)
VALID_CATEGORIES = INSIGHT_CATEGORIES   # single definition in domain/insights.py
VALID_EFFORTS = FIX_EFFORTS

def validate_llm_output(insight: dict, step_id: str) -> dict:
    """Validates and enforces schemas on the parsed LLM JSON insight."""
    if not isinstance(insight, dict):
        return _fallback(step_id, "Response was not a JSON dictionary.")
    
    # Check title
    title = insight.get("title", "")
    if not isinstance(title, str) or not title.strip():
        insight["title"] = f"Friction detected at {step_id}"
    elif len(title.split()) > 15: # loosely enforce max 8 words
        insight["title"] = " ".join(title.split()[:8]) + "..."
        
    # Validations
    if insight.get("category") not in VALID_CATEGORIES:
        insight["category"] = "unknown"
        
    if insight.get("fix_effort") not in VALID_EFFORTS:
        insight["fix_effort"] = "medium"
        
    if not isinstance(insight.get("root_cause"), str) or not insight["root_cause"].strip():
        insight["root_cause"] = "Root cause details were not provided."
        
    if not isinstance(insight.get("suggested_fix"), str) or not insight["suggested_fix"].strip():
        insight["suggested_fix"] = "Review metrics manually."
        
    if not isinstance(insight.get("evidence"), list):
        insight["evidence"] = []
        
    insight["step_id"] = step_id
    return insight

def _fallback(step_id: str, message: str) -> dict:
    return {
        "title": f"Friction at {step_id}",
        "root_cause": f"Validation failed: {message}",
        "category": "unknown",
        "evidence": [],
        "suggested_fix": "Review metrics manually.",
        "fix_effort": "medium",
        "step_id": step_id
    }
