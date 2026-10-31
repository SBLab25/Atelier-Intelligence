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

from cji.config import FRICTION_SCORE_THRESHOLD

# ── Constants (EXACT — tests import and depend on these values) ────────────────
WEIGHTS: dict[str, float] = {
    "abandon_rate_pct": 0.35,
    "error_rate_pct":   0.25,
    "avg_dwell_ms":     0.15,
    "avg_retries":      0.15,
    "avg_rage_clicks":  0.10,
}

BASELINES: dict[str, float] = {
    "abandon_rate_pct": 10.0,
    "error_rate_pct":   5.0,
    "avg_dwell_ms":     15000.0,
    "avg_retries":      0.1,
    "avg_rage_clicks":  0.05,
}

# Signal detection rules: (variable_key, threshold, signal_name)
# Order matters — tests verify signal names exactly.
SIGNAL_THRESHOLDS: list[tuple[str, float, str]] = [
    ("abandon", 30,     "high_drop_off"),
    ("abandon", 50,     "critical_drop_off"),
    ("error",   15,     "frequent_errors"),
    ("dwell",   60000,  "extended_hesitation"),
    ("dwell",   120000, "severe_confusion"),
    ("retries", 1.0,    "repeated_retries"),
    ("rclicks", 0.5,    "rage_clicks_detected"),
]

# ── MCP Server Instance ────────────────────────────────────────────────────────
mcp = FastMCP("cji-friction-engine")


# ── Private Computation (importable by tests) ──────────────────────────────────

def _normalise(value: float, baseline: float) -> float:
    """
    Normalise value against baseline.

    Formula: min(value / max(baseline, 0.001), 3.0) / 3.0
    Result range: 0.0 to 1.0
      - At baseline:    1/3 ≈ 0.333
      - At 3× baseline: 1.0 (capped)
      - Above 3×:       still 1.0 (capped — prevents any single metric dominating)
    """
    return min(value / max(baseline, 0.001), 3.0) / 3.0


def _compute_score(step_metrics: dict) -> tuple[int, list[str], float]:
    """
    Compute (score, signals, confidence) from a step_metrics dict.

    Internal function — used by score_friction() and importable by tests.

    Returns:
        score:      int 0–100 (higher = more friction)
        signals:    list of triggered signal names
        confidence: float 0.50–0.98 (higher = more data evidence)
    """
    # Step 1: Read inputs with .get() → default 0 (missing fields never crash)
    abandon = float(step_metrics.get("abandon_rate_pct", 0))
    error   = float(step_metrics.get("error_rate_pct",   0))
    dwell   = float(step_metrics.get("avg_dwell_ms",     0))
    retries = float(step_metrics.get("avg_retries",      0))
    rclicks = float(step_metrics.get("avg_rage_clicks",  0))

    # Step 2: Weighted composite score
    raw = (
        _normalise(abandon, BASELINES["abandon_rate_pct"]) * WEIGHTS["abandon_rate_pct"]
      + _normalise(error,   BASELINES["error_rate_pct"])   * WEIGHTS["error_rate_pct"]
      + _normalise(dwell,   BASELINES["avg_dwell_ms"])     * WEIGHTS["avg_dwell_ms"]
      + _normalise(retries, BASELINES["avg_retries"])      * WEIGHTS["avg_retries"]
      + _normalise(rclicks, BASELINES["avg_rage_clicks"])  * WEIGHTS["avg_rage_clicks"]
    )

    # Step 3: Convert to integer (truncate, not round, as specified)
    score = min(100, int(raw * 100))

    # Step 4: Detect named signals
    vals: dict[str, float] = {
        "abandon": abandon, "error": error, "dwell": dwell,
        "retries": retries, "rclicks": rclicks,
    }
    signals: list[str] = []
    for var, threshold, signal_name in SIGNAL_THRESHOLDS:
        if vals[var] > threshold:
            signals.append(signal_name)

    # Step 5: Confidence based on signal evidence count
    # 0 signals=0.50, 1=0.60, 2=0.70, 3=0.80, 4=0.90, 5+=0.98 (capped)
    confidence = min(0.5 + len(signals) * 0.1, 0.98)

    return score, signals, confidence


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
    score, signals, confidence = _compute_score(step_metrics)
    return {
        "step_id":         step_metrics.get("step_id", "unknown"),
        "score":           score,
        "drop_off_rate":   step_metrics.get("abandon_rate_pct", 0) / 100.0,
        "avg_dwell_ms":    int(step_metrics.get("avg_dwell_ms", 0)),
        "retry_count":     float(step_metrics.get("avg_retries", 0)),
        "rage_click_rate": float(step_metrics.get("avg_rage_clicks", 0)),
        "signals":         signals,
        "confidence":      confidence,
        "is_critical":     score >= FRICTION_SCORE_THRESHOLD,
    }


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
    if not all_step_metrics:
        return {
            "scores":         [],
            "critical_steps": [],
            "total_steps":    0,
            "avg_score":      0.0,
            "threshold":      FRICTION_SCORE_THRESHOLD,
        }

    scored = [score_friction(m) for m in all_step_metrics]
    scored.sort(key=lambda x: x["score"], reverse=True)  # descending by score

    scores_list = [s["score"] for s in scored]
    avg = round(sum(scores_list) / len(scores_list), 2)

    return {
        "scores":         scored,
        "critical_steps": [s["step_id"] for s in scored if s["is_critical"]],
        "total_steps":    len(scored),
        "avg_score":      avg,
        "threshold":      FRICTION_SCORE_THRESHOLD,
    }


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
