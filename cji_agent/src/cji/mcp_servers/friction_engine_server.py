"""
CJI Friction Engine MCP Server
================================
Deterministic, pure-Python friction scoring. No database. No LLM.

This server exposes 4 tools via the MCP stdio protocol:
  - score_friction:   Score a single step
  - score_all_steps:  Score all steps and return sorted results
  - detect_dropoffs:  Find steps with drop-off above threshold
  - correlate_signals: Find systemic signal patterns across all steps

Run standalone:
  python -m cji.mcp_servers.friction_engine_server

Design:
  - Constants (WEIGHTS, BASELINES) are importable by test suite.
  - Private functions (_normalise, _compute_score) are also importable.
  - No IO in any function — all computation is pure Python.
"""

from itertools import combinations

from fastmcp import FastMCP

# ── Scoring (Spec 12, OD-112: moved to cji.analytics.friction; re-exported for tests and callers) ──────
from cji.analytics.friction import (
    BASELINES,
    SIGNAL_THRESHOLDS,
    WEIGHTS,
    _compute_score,
    _normalise,
    score_step,
    score_steps,
)
from cji.config import FRICTION_SCORE_THRESHOLD

__all__ = ["BASELINES", "SIGNAL_THRESHOLDS", "WEIGHTS", "_compute_score", "_normalise", "mcp"]

# ── MCP Server Instance ────────────────────────────────────────────────────────
mcp = FastMCP("cji-friction-engine")


# ── MCP Tools ─────────────────────────────────────────────────────────────────

@mcp.tool
def score_friction(step_metrics: dict) -> dict:
    """
    Compute friction score for one step.

    Args:
        step_metrics: Dict with step_id, abandon_rate_pct, error_rate_pct,
                      avg_dwell_ms, avg_retries, avg_rage_clicks.
                      Missing fields default to 0 (no crash).

    Returns:
        {step_id, score, drop_off_rate, avg_dwell_ms, retry_count,
         rage_click_rate, signals, confidence, is_critical}
    """
    return score_step(step_metrics, threshold=FRICTION_SCORE_THRESHOLD)


@mcp.tool
def score_all_steps(all_step_metrics: list) -> dict:
    """
    Score all steps and return sorted results with aggregate statistics.

    Args:
        all_step_metrics: List of step_metrics dicts (one per step).

    Returns:
        {scores: list, critical_steps: list[str], total_steps: int,
         avg_score: float, threshold: int}
    """
    return score_steps(all_step_metrics, threshold=FRICTION_SCORE_THRESHOLD)


@mcp.tool
def detect_dropoffs(funnel_data: list, threshold_pct: float = 25.0) -> dict:
    """
    Flag and sort steps where drop-off rate exceeds the threshold.

    Args:
        funnel_data:   List of {step_id, drop_off_pct, users}.
        threshold_pct: Minimum drop-off % to flag (default 25.0).

    Returns:
        {critical_dropoffs: list, count: int, threshold_pct: float}
    """
    critical = []
    for row in funnel_data:
        drop_pct = float(row.get("drop_off_pct", 0))
        if drop_pct >= threshold_pct:
            users      = int(row.get("users", 0))
            users_lost = int(users * drop_pct / 100.0)
            critical.append({
                "step_id":      row["step_id"],
                "drop_off_pct": drop_pct,
                "users_lost":   users_lost,
            })

    # Sort by drop_off_pct descending (worst first)
    critical.sort(key=lambda x: x["drop_off_pct"], reverse=True)

    return {
        "critical_dropoffs": critical,
        "count":             len(critical),
        "threshold_pct":     threshold_pct,
    }


@mcp.tool
def get_thresholds() -> dict:
    """Returns the internal friction thresholds, baselines, and weights for the dashboard."""
    # Convert tuples in SIGNAL_THRESHOLDS to a list of dicts for JSON serialization
    signal_thresholds_json = [
        {"metric": var, "threshold": threshold, "signal_name": signal_name}
        for var, threshold, signal_name in SIGNAL_THRESHOLDS
    ]
    
    return {
        "weights": WEIGHTS,
        "baselines": BASELINES,
        "signal_thresholds": signal_thresholds_json,
        "friction_score_threshold": FRICTION_SCORE_THRESHOLD
    }

@mcp.tool
def correlate_signals(scores: list) -> dict:
    """
    Find systemic signals and co-occurrence patterns across all steps.

    Args:
        scores: List of score dicts from score_friction() or score_all_steps().
                Each must have {step_id, signals: list[str]}.

    Returns:
        {signal_frequency, co_occurring_patterns, systemic_signals, analysis}
    """
    if not scores:
        return {
            "signal_frequency":      {},
            "co_occurring_patterns": [],
            "systemic_signals":      [],
            "analysis":              "No scores provided.",
        }

    # Count signal frequency across all steps
    freq: dict[str, int] = {}
    pair_counts: dict[tuple, int] = {}

    for score in scores:
        sigs = score.get("signals", [])
        for s in sigs:
            freq[s] = freq.get(s, 0) + 1
        # Count all 2-signal co-occurrences within this step
        if len(sigs) >= 2:
            for pair in combinations(sorted(sigs), 2):
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

    # Systemic: signal appears in ≥ 50% of steps, minimum threshold = 2
    n_steps   = max(len(scores), 1)
    threshold = max(2, int(n_steps * 0.5))
    systemic  = [sig for sig, count in freq.items() if count >= threshold]

    # Co-occurring: pairs appearing together in 2+ steps
    co_patterns = [
        {"signals": list(pair), "count": count}
        for pair, count in sorted(pair_counts.items(), key=lambda x: -x[1])
        if count >= 2
    ]

    # Narrative analysis
    if systemic:
        analysis = (
            f"{', '.join(systemic)} appear in {threshold}+ steps — "
            f"indicates a systemic issue affecting the entire journey."
        )
    else:
        analysis = (
            "No systemic signals detected. Issues appear to be step-specific. "
            "Focus on individual step remediation."
        )

    return {
        "signal_frequency":      freq,
        "co_occurring_patterns": co_patterns,
        "systemic_signals":      systemic,
        "analysis":              analysis,
    }


# ── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from cji.mcp_servers._serve import serve

    serve(mcp, "cji-friction-engine")
