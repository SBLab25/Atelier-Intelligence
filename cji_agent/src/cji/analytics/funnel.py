"""Funnel summary shared by the journey-data MCP server and the API (Spec 12). Pure module."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def overall_completion_pct(funnel: Sequence[Mapping[str, Any]]) -> float:
    """100 minus the drop from the first to the last funnel step, in percent of the first step's users."""
    overall_pct = 0.0
    if funnel and funnel[0]["users"] > 0:
        overall_pct = round((funnel[0]["users"] - funnel[-1]["users"]) * 100.0 / funnel[0]["users"], 2)
    return 100.0 - overall_pct
