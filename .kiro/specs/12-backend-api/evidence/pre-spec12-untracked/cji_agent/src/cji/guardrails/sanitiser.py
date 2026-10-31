BLOCKED_FIELDS = {"user_id", "session_id", "ip_address", "email", "verbatim", "event_id"}

def sanitise_for_llm(data: dict) -> dict:
    """Removes sensitive fields from data before prompting LLM."""
    if not isinstance(data, dict):
        return data
    return {k: v for k, v in data.items() if k not in BLOCKED_FIELDS}
