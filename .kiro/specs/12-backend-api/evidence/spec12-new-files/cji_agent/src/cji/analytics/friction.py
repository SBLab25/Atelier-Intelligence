"""
Deterministic friction scoring (moved from mcp_servers/friction_engine_server.py in Spec 12, OD-112).

Pure Python: no I/O, no settings. The threshold is passed in by the caller (FRICTION_SCORE_THRESHOLD).
The friction MCP server re-exports these names; its tools return exactly what these functions return.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

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


def _compute_score(step_metrics: Mapping[str, Any]) -> tuple[int, list[str], float]:
    """
    Compute (score, signals, confidence) from a step_metrics dict.

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


def score_step(step_metrics: Mapping[str, Any], *, threshold: int) -> dict[str, Any]:
    """Friction score for one step: {step_id, score, drop_off_rate, avg_dwell_ms, retry_count, rage_click_rate,
    signals, confidence, is_critical}. Missing fields default to 0."""
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
        "is_critical":     score >= threshold,
    }


def score_steps(all_step_metrics: Sequence[Mapping[str, Any]], *, threshold: int) -> dict[str, Any]:
    """All steps sorted by score (descending) with aggregate statistics:
    {scores, critical_steps, total_steps, avg_score, threshold}."""
    if not all_step_metrics:
        return {"scores": [], "critical_steps": [], "total_steps": 0, "avg_score": 0.0, "threshold": threshold}
    scored = [score_step(m, threshold=threshold) for m in all_step_metrics]
    scored.sort(key=lambda x: x["score"], reverse=True)  # descending by score
    scores_list = [s["score"] for s in scored]
    return {
        "scores":         scored,
        "critical_steps": [s["step_id"] for s in scored if s["is_critical"]],
        "total_steps":    len(scored),
        "avg_score":      round(sum(scores_list) / len(scores_list), 2),
        "threshold":      threshold,
    }
