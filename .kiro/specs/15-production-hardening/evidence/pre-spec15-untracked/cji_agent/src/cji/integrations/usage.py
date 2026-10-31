"""Run-level LLM usage and budget bookkeeping for workers (Spec 08, OD-59)."""
from __future__ import annotations

from typing import Any

from .types import RunBudget, RunContext

EMPTY_USAGE: dict[str, Any] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


def add_usage(total: dict[str, Any] | None, info: dict[str, Any] | None) -> dict[str, Any]:
    """New running total after one LLM tool result. Only calls that reached the provider count."""
    out = {**EMPTY_USAGE, **(total or {})}
    if not isinstance(info, dict) or int(info.get("attempts") or 0) < 1:
        return out
    out["calls"] += 1
    out["input_tokens"] += int(info.get("input_tokens") or 0)
    out["output_tokens"] += int(info.get("output_tokens") or 0)
    if isinstance(info.get("cost_usd"), int | float):
        out["cost_usd"] = round(out["cost_usd"] + float(info["cost_usd"]), 6)
    return out


def remaining_budget(total: dict[str, Any] | None) -> RunBudget:
    """What is left of the configured per-run budget after `total`."""
    from cji.settings import get_settings

    limits = get_settings().llm.run_budget
    used = {**EMPTY_USAGE, **(total or {})}
    cost_left = None
    if limits.max_cost_usd is not None:
        cost_left = max(0.0, limits.max_cost_usd - float(used["cost_usd"]))
    return RunBudget(
        calls_left=max(0, limits.max_calls - int(used["calls"])),
        tokens_left=max(0, limits.max_tokens - int(used["input_tokens"]) - int(used["output_tokens"])),
        cost_left_usd=cost_left,
    )


def run_context_arg(ctx: RunContext, total: dict[str, Any] | None) -> dict[str, Any]:
    """The `run_context` argument for an LLM tool: correlation id, worker and remaining budget."""
    return ctx.model_copy(update={"budget": remaining_budget(total)}).model_dump()
