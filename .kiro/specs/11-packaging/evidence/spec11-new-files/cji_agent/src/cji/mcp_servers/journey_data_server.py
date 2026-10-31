"""
CJI MCP Server 1 — Journey Data
================================
Tools read journey events through the configured EventRepository (Spec 05). The
repository is chosen once from settings (demo: DuckDB over Parquet; realtime:
PostgreSQL); no tool branches on the mode. Arguments are validated before any query.
"""
import logging
from typing import Any

from fastmcp import FastMCP

from cji.config import DUCKDB_PATH, JOURNEY_CONFIG
from cji.repositories import (
    EventRepository,
    NotSupported,
    RepositoryError,
    TimeWindow,
    get_repository,
)
from cji.settings import ConfigError

logger = logging.getLogger(__name__)

MAX_LIMIT = 1000
MAX_MINUTES = 43200          # 30 days, as the collector's /live/stats
MAX_DAYS = 3650
MAX_FILTER_LENGTH = 128
DEMO_SNAPSHOT_REPLY = {
    "error": "get_live_snapshot is only available in realtime mode",
    "mode": "demo",
    "message": "Switch to CJI_MODE=realtime to use this tool",
}


class InvalidArgument(ValueError):
    """A tool argument is out of range; reported in the tool's error shape."""


def _whole_number(name: str, value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise InvalidArgument(f"{name} must be a whole number from {low} to {high}")
    return value


def _text_filter(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_FILTER_LENGTH:
        raise InvalidArgument(f"{name} must be text of at most {MAX_FILTER_LENGTH} characters")
    return value


def _window(days_back: Any, minutes_back: Any) -> TimeWindow:
    return TimeWindow(
        days_back=_whole_number("days_back", days_back, 0, MAX_DAYS),
        minutes_back=_whole_number("minutes_back", minutes_back, 0, MAX_MINUTES),
    )


def _repository() -> EventRepository:
    try:
        return get_repository()
    except ConfigError as exc:
        raise RepositoryError("configure", "; ".join(exc.problems)) from exc


def _overall_completion_pct(funnel: list[dict[str, Any]]) -> float:
    overall_pct = 0.0
    if funnel and funnel[0]["users"] > 0:
        overall_pct = round((funnel[0]["users"] - funnel[-1]["users"]) * 100.0 / funnel[0]["users"], 2)
    return 100.0 - overall_pct


# Initialise the FastMCP server
mcp = FastMCP("cji-journey-data")

@mcp.tool()
async def get_system_info() -> dict:
    """Returns mode, data source, and connection status (readiness of the configured store)."""
    try:
        repo = _repository()
        repo.health()
    except RepositoryError as e:
        return {"status": "error", "error": e.message}
    return {
        "mode": repo.mode,
        "data_source": repo.data_source,
        "duckdb_path": str(DUCKDB_PATH),
        "journey_id": JOURNEY_CONFIG["name"],
        "journey_steps": JOURNEY_CONFIG["steps"],
        "status": "ok"
    }

@mcp.tool()
def get_funnel_steps() -> dict:
    """Returns ordered list of journey step IDs."""
    return {
        "journey_id": JOURNEY_CONFIG["name"],
        "steps": JOURNEY_CONFIG["steps"],
        "step_count": len(JOURNEY_CONFIG["steps"])
    }

@mcp.tool()
async def get_step_metrics(days_back: int = 30, minutes_back: int = 0) -> dict:
    """Returns aggregated metrics per step."""
    journey_id = JOURNEY_CONFIG["name"]
    try:
        window = _window(days_back, minutes_back)
        repo = _repository()
        metrics = repo.step_metrics(journey_id, window)
    except (InvalidArgument, RepositoryError) as e:
        logger.error(f"Error querying step metrics: {e}")
        return {"error": str(e), "step_metrics": [], "total_steps": 0}
    window_days, window_minutes = repo.window_fields(window)
    return {
        "journey_id": journey_id,
        "window_days": window_days,
        "window_minutes": window_minutes,
        "step_metrics": metrics,
        "total_steps": len(metrics),
    }

@mcp.tool()
async def get_funnel_dropoff(days_back: int = 30, minutes_back: int = 0) -> dict:
    """Returns sequential funnel drop-off percentages."""
    journey_id = JOURNEY_CONFIG["name"]
    steps = list(JOURNEY_CONFIG["steps"])
    try:
        funnel = _repository().funnel(journey_id, steps, _window(days_back, minutes_back))
    except (InvalidArgument, RepositoryError) as e:
        logger.error(f"Funnel error: {e}")
        return {"error": str(e), "funnel": []}
    return {"journey_id": journey_id, "funnel": funnel, "overall_completion_pct": _overall_completion_pct(funnel)}

@mcp.tool()
async def query_events(limit: int = 100, step_id: str | None = None, event_type: str | None = None) -> dict:
    """Returns a sample of raw events with optional filters."""
    journey_id = JOURNEY_CONFIG["name"]
    try:
        events = _repository().events(
            journey_id,
            limit=_whole_number("limit", limit, 1, MAX_LIMIT),
            step_id=_text_filter("step_id", step_id),
            event_type=_text_filter("event_type", event_type),
        )
    except (InvalidArgument, RepositoryError) as e:
        return {"error": str(e), "events": [], "count": 0}
    return {"events": events, "count": len(events), "step_id_filter": step_id, "event_type_filter": event_type}


@mcp.tool()
async def get_live_snapshot(minutes: int = 15) -> dict:
    """Realtime mode only. Returns rolling event counts for the last N minutes."""
    try:
        minutes = _whole_number("minutes", minutes, 1, MAX_MINUTES)
        snapshot = _repository().live_snapshot(minutes)
    except NotSupported:
        return dict(DEMO_SNAPSHOT_REPLY)
    except (InvalidArgument, RepositoryError) as e:
        return {"error": str(e)}
    return {
        "window_mins": minutes,
        "steps": snapshot.steps,
        "total_events": snapshot.total_events,
        "snapshot_at": snapshot.snapshot_at,
    }

if __name__ == "__main__":
    from cji.mcp_servers._serve import serve

    serve(mcp, "cji-journey-data")
