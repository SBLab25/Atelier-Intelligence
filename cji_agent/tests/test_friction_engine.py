"""
Unit Tests: Friction Engine
============================
Tests the friction_engine_server module directly (no subprocess, no network, no LLM).
Provides 100% function coverage of all public and private functions.

Run:
  pytest tests/test_friction_engine.py -v

All tests must pass with zero network, zero API key, in < 5 seconds.
"""

import pytest

from cji.mcp_servers.friction_engine_server import (
    BASELINES,
    FRICTION_SCORE_THRESHOLD,
    WEIGHTS,
    _compute_score,
    _normalise,
    correlate_signals,
    detect_dropoffs,
    score_all_steps,
    score_friction,
)


# ── Fixtures (Shared fixtures now in conftest.py) ──────────────────────────────────────────────────────────────


# ── Tests: _normalise ─────────────────────────────────────────────────────────

def test_normalise_at_baseline():
    """Value at baseline → returns 1/3 ≈ 0.3333."""
    result = _normalise(10.0, 10.0)
    assert abs(result - 1 / 3) < 0.001, f"Expected ≈0.333, got {result}"


def test_normalise_at_three_times_baseline():
    """Value at exactly 3× baseline → returns 1.0 (at cap)."""
    result = _normalise(30.0, 10.0)
    assert result == pytest.approx(1.0), f"Expected 1.0, got {result}"


def test_normalise_above_three_times_baseline_caps_at_1():
    """Value at 10× baseline → still returns 1.0 (capped at 3×)."""
    result = _normalise(100.0, 10.0)
    assert result == pytest.approx(1.0), f"Expected 1.0 (capped), got {result}"


def test_normalise_zero_value_returns_zero():
    """Zero value → 0.0 (regardless of baseline)."""
    assert _normalise(0.0, 10.0) == 0.0
    assert _normalise(0.0, 0.05) == 0.0


def test_normalise_zero_baseline_does_not_raise():
    """Zero baseline uses max(b, 0.001) guard — no ZeroDivisionError."""
    result = _normalise(5.0, 0.0)
    # 5.0 / 0.001 = 5000 >> 3.0, so capped → 1.0
    assert result == pytest.approx(1.0)


def test_normalise_below_baseline():
    """Value below baseline → result between 0 and 1/3."""
    result = _normalise(5.0, 10.0)   # half of baseline
    assert 0.0 < result < 1 / 3


def test_normalise_constants_used_correctly():
    """Verify WEIGHTS and BASELINES dict values haven't been accidentally changed."""
    assert WEIGHTS["abandon_rate_pct"] == pytest.approx(0.35)
    assert WEIGHTS["error_rate_pct"]   == pytest.approx(0.25)
    assert WEIGHTS["avg_dwell_ms"]     == pytest.approx(0.15)
    assert WEIGHTS["avg_retries"]      == pytest.approx(0.15)
    assert WEIGHTS["avg_rage_clicks"]  == pytest.approx(0.10)
    assert sum(WEIGHTS.values())       == pytest.approx(1.00)

    assert BASELINES["abandon_rate_pct"] == pytest.approx(10.0)
    assert BASELINES["error_rate_pct"]   == pytest.approx(5.0)
    assert BASELINES["avg_dwell_ms"]     == pytest.approx(15000.0)
    assert BASELINES["avg_retries"]      == pytest.approx(0.1)
    assert BASELINES["avg_rage_clicks"]  == pytest.approx(0.05)


# ── Tests: score_friction — basic correctness ─────────────────────────────────

def test_low_step_score_below_threshold(low_step):
    """Landing page characteristics → score below critical threshold."""
    r = score_friction(low_step)
    assert r["score"] < FRICTION_SCORE_THRESHOLD, (
        f"Expected score < {FRICTION_SCORE_THRESHOLD}, got {r['score']}"
    )
    assert r["is_critical"] is False


def test_high_step_score_at_or_above_threshold(high_step):
    """Email verification characteristics → score at or above critical threshold."""
    r = score_friction(high_step)
    assert r["score"] >= FRICTION_SCORE_THRESHOLD, (
        f"Expected score >= {FRICTION_SCORE_THRESHOLD}, got {r['score']}"
    )
    assert r["is_critical"] is True


def test_score_bounded_0_to_100(high_step):
    """Score is always in [0, 100] range."""
    r = score_friction(high_step)
    assert 0 <= r["score"] <= 100


def test_confidence_bounded(high_step):
    """Confidence is always in [0.0, 0.98] range."""
    r = score_friction(high_step)
    assert 0.0 <= r["confidence"] <= 0.98


def test_score_zero_step_returns_zero(zero_step):
    """All-zero inputs → score 0."""
    r = score_friction(zero_step)
    assert r["score"] == 0


def test_score_zero_step_no_signals(zero_step):
    """All-zero inputs → empty signals list."""
    r = score_friction(zero_step)
    assert r["signals"] == []


def test_score_zero_step_minimum_confidence(zero_step):
    """All-zero inputs → minimum confidence 0.50."""
    r = score_friction(zero_step)
    assert r["confidence"] == pytest.approx(0.50)


def test_step_id_preserved_in_result(low_step):
    """step_id from input is reflected in output."""
    r = score_friction(low_step)
    assert r["step_id"] == "landing_page"


def test_missing_all_fields_returns_zero():
    """Dict with only step_id → all metrics default to 0, no KeyError."""
    r = score_friction({"step_id": "sparse_step"})
    assert r["score"] == 0
    assert r["is_critical"] is False
    assert r["signals"] == []


def test_missing_no_step_id_returns_unknown():
    """Empty dict → step_id becomes 'unknown', no crash."""
    r = score_friction({})
    assert r["step_id"] == "unknown"
    assert r["score"] == 0


def test_drop_off_rate_is_fraction(low_step):
    """drop_off_rate = abandon_rate_pct / 100 (fraction, not percent)."""
    r = score_friction(low_step)
    assert r["drop_off_rate"] == pytest.approx(15.0 / 100.0)


def test_avg_dwell_ms_is_integer(high_step):
    """avg_dwell_ms in output is an integer."""
    r = score_friction(high_step)
    assert isinstance(r["avg_dwell_ms"], int)


def test_baseline_step_score_approx_33(baseline_step):
    """All metrics at baseline → raw ≈ 1/3, score ≈ 33."""
    r = score_friction(baseline_step)
    # raw = 5 * (1/3 * weight) = 1/3 * (0.35+0.25+0.15+0.15+0.10) = 1/3
    # score = int(1/3 * 100) = 33
    assert r["score"] == 33, f"Expected 33 at baseline, got {r['score']}"


# ── Tests: Signal Detection ───────────────────────────────────────────────────

def test_high_step_expected_signals(high_step):
    """Email verification with high friction triggers all 6 expected signals."""
    r = score_friction(high_step)
    signals = r["signals"]
    # abandon=41.8: > 30 → high_drop_off ✓; NOT > 50 → critical_drop_off ✗
    assert "high_drop_off" in signals,        f"Missing high_drop_off. Got: {signals}"
    assert "critical_drop_off" not in signals, f"critical_drop_off should NOT fire at 41.8"
    # error=34.7 > 15 → frequent_errors ✓
    assert "frequent_errors" in signals,      f"Missing frequent_errors. Got: {signals}"
    # dwell=184000 > 60000 → extended_hesitation ✓
    assert "extended_hesitation" in signals,  f"Missing extended_hesitation. Got: {signals}"
    # dwell=184000 > 120000 → severe_confusion ✓
    assert "severe_confusion" in signals,     f"Missing severe_confusion. Got: {signals}"
    # retries=1.8 > 1.0 → repeated_retries ✓
    assert "repeated_retries" in signals,     f"Missing repeated_retries. Got: {signals}"
    # rclicks=0.62 > 0.5 → rage_clicks_detected ✓
    assert "rage_clicks_detected" in signals, f"Missing rage_clicks_detected. Got: {signals}"


def test_critical_drop_off_requires_abandon_above_50():
    """critical_drop_off fires only when abandon_rate_pct > 50 (strict)."""
    exactly_50 = {
        "step_id": "t",
        "abandon_rate_pct": 50.0,
        "error_rate_pct": 0, "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0,
    }
    above_50 = {**exactly_50, "abandon_rate_pct": 50.1}

    r_50  = score_friction(exactly_50)
    r_51  = score_friction(above_50)

    assert "critical_drop_off" not in r_50["signals"], "Should NOT fire at exactly 50"
    assert "critical_drop_off" in r_51["signals"],     "Should fire above 50"


def test_high_drop_off_requires_abandon_above_30():
    """high_drop_off fires only when abandon_rate_pct > 30 (strict)."""
    exactly_30 = {
        "step_id": "t",
        "abandon_rate_pct": 30.0,
        "error_rate_pct": 0, "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0,
    }
    above_30 = {**exactly_30, "abandon_rate_pct": 30.1}

    r_30 = score_friction(exactly_30)
    r_31 = score_friction(above_30)

    assert "high_drop_off" not in r_30["signals"], "Should NOT fire at exactly 30"
    assert "high_drop_off" in r_31["signals"],     "Should fire above 30"


def test_extended_hesitation_requires_dwell_above_60000():
    """extended_hesitation fires only when avg_dwell_ms > 60000."""
    step_60 = {
        "step_id": "t",
        "abandon_rate_pct": 0, "error_rate_pct": 0,
        "avg_dwell_ms": 60000, "avg_retries": 0, "avg_rage_clicks": 0,
    }
    step_61 = {**step_60, "avg_dwell_ms": 60001}
    assert "extended_hesitation" not in score_friction(step_60)["signals"]
    assert "extended_hesitation" in score_friction(step_61)["signals"]


def test_severe_confusion_requires_dwell_above_120000():
    """severe_confusion fires only when avg_dwell_ms > 120000."""
    step_120 = {
        "step_id": "t",
        "abandon_rate_pct": 0, "error_rate_pct": 0,
        "avg_dwell_ms": 120000, "avg_retries": 0, "avg_rage_clicks": 0,
    }
    step_121 = {**step_120, "avg_dwell_ms": 120001}
    assert "severe_confusion" not in score_friction(step_120)["signals"]
    assert "severe_confusion" in score_friction(step_121)["signals"]


def test_low_step_no_critical_signals(low_step):
    """Landing page does not trigger high-severity signals."""
    r = score_friction(low_step)
    signals = r["signals"]
    assert "critical_drop_off"    not in signals
    assert "severe_confusion"     not in signals
    assert "rage_clicks_detected" not in signals


def test_confidence_increases_with_more_signals():
    """More signals → higher confidence, capped at 0.98."""
    step_0_sigs = {
        "step_id": "t",
        "abandon_rate_pct": 0, "error_rate_pct": 0,
        "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0,
    }
    # This step triggers: high_drop_off (40>30), frequent_errors (20>15),
    # extended_hesitation (130000>60000), severe_confusion (130000>120000),
    # repeated_retries (1.5>1.0), rage_clicks_detected (0.6>0.5)
    step_6_sigs = {
        "step_id": "t",
        "abandon_rate_pct": 40, "error_rate_pct": 20,
        "avg_dwell_ms": 130000, "avg_retries": 1.5, "avg_rage_clicks": 0.6,
    }
    r0 = score_friction(step_0_sigs)
    r6 = score_friction(step_6_sigs)

    assert r0["confidence"] < r6["confidence"]
    assert r6["confidence"] <= 0.98


def test_confidence_at_5_plus_signals_capped():
    """5 or more signals → confidence capped at 0.98."""
    # Construct a step that triggers all 7 signals:
    # abandon > 50, error > 15, dwell > 120000, retries > 1.0, rclicks > 0.5
    step_all = {
        "step_id": "t",
        "abandon_rate_pct": 51,
        "error_rate_pct": 20,
        "avg_dwell_ms": 130000,
        "avg_retries": 1.5,
        "avg_rage_clicks": 0.6,
    }
    r = score_friction(step_all)
    assert r["confidence"] == pytest.approx(0.98)


# ── Tests: score_all_steps ─────────────────────────────────────────────────────

def test_all_steps_sorted_descending(low_step, high_step):
    """Results are sorted by score descending (highest score first)."""
    r = score_all_steps([low_step, high_step])
    scores = [s["score"] for s in r["scores"]]
    assert scores == sorted(scores, reverse=True)


def test_all_steps_critical_list_correct(low_step, high_step):
    """critical_steps contains only steps meeting the threshold."""
    r = score_all_steps([low_step, high_step])
    assert "email_verification" in r["critical_steps"]
    assert "landing_page" not in r["critical_steps"]


def test_all_steps_empty_list_returns_safe_defaults():
    """Empty input list → zeros, empty lists, no crash."""
    r = score_all_steps([])
    assert r["scores"] == []
    assert r["critical_steps"] == []
    assert r["total_steps"] == 0
    assert r["avg_score"] == pytest.approx(0.0)


def test_all_steps_total_steps_count(low_step, high_step):
    """total_steps equals the number of input steps."""
    r = score_all_steps([low_step, high_step])
    assert r["total_steps"] == 2


def test_all_steps_avg_score_is_positive(low_step, high_step):
    """Average score is > 0 when any step has non-zero metrics."""
    r = score_all_steps([low_step, high_step])
    assert r["avg_score"] > 0


def test_all_steps_threshold_value_in_result():
    """threshold key in response matches FRICTION_SCORE_THRESHOLD constant."""
    r = score_all_steps([{"step_id": "x"}])
    assert r["threshold"] == FRICTION_SCORE_THRESHOLD


# ── Tests: detect_dropoffs ────────────────────────────────────────────────────

def test_detect_dropoffs_flags_above_threshold():
    """Steps above threshold are returned; steps below are excluded."""
    funnel = [
        {"step_id": "step_a", "drop_off_pct": 50.0, "users": 500},
        {"step_id": "step_b", "drop_off_pct": 10.0, "users": 450},
    ]
    r = detect_dropoffs(funnel, 25.0)
    assert r["count"] == 1
    assert r["critical_dropoffs"][0]["step_id"] == "step_a"


def test_detect_dropoffs_users_lost_calculation():
    """users_lost = int(users × drop_off_pct / 100)."""
    funnel = [{"step_id": "x", "drop_off_pct": 40.0, "users": 1000}]
    r = detect_dropoffs(funnel, 25.0)
    assert r["critical_dropoffs"][0]["users_lost"] == 400


def test_detect_dropoffs_all_below_threshold_returns_empty():
    """No steps above threshold → count=0, empty list."""
    funnel = [{"step_id": "x", "drop_off_pct": 5.0, "users": 1000}]
    r = detect_dropoffs(funnel, 25.0)
    assert r["count"] == 0
    assert r["critical_dropoffs"] == []


def test_detect_dropoffs_sorted_by_pct_desc():
    """Results sorted by drop_off_pct descending (worst step first)."""
    funnel = [
        {"step_id": "low",  "drop_off_pct": 30.0, "users": 500},
        {"step_id": "high", "drop_off_pct": 60.0, "users": 400},
    ]
    r = detect_dropoffs(funnel, 25.0)
    assert r["critical_dropoffs"][0]["step_id"] == "high"


def test_detect_dropoffs_at_exactly_threshold_included():
    """Step with drop_off_pct exactly equal to threshold IS included (>=)."""
    funnel = [{"step_id": "exact", "drop_off_pct": 25.0, "users": 100}]
    r = detect_dropoffs(funnel, 25.0)
    assert r["count"] == 1


def test_detect_dropoffs_empty_input():
    """Empty funnel_data → count=0, no crash."""
    r = detect_dropoffs([], 25.0)
    assert r["count"] == 0
    assert r["critical_dropoffs"] == []


def test_detect_dropoffs_default_threshold():
    """Default threshold is 25.0."""
    r = detect_dropoffs([{"step_id": "x", "drop_off_pct": 25.0, "users": 100}])
    assert r["threshold_pct"] == 25.0


# ── Tests: correlate_signals ──────────────────────────────────────────────────

def test_correlate_systemic_signal():
    """Signal appearing in 3/3 steps is systemic."""
    scores = [
        {"step_id": "a", "signals": ["high_drop_off"]},
        {"step_id": "b", "signals": ["high_drop_off"]},
        {"step_id": "c", "signals": ["high_drop_off"]},
    ]
    r = correlate_signals(scores)
    assert "high_drop_off" in r["systemic_signals"]


def test_correlate_isolated_signal_not_systemic():
    """Signal appearing in only 1 of 4 steps is NOT systemic."""
    scores = [
        {"step_id": "a", "signals": ["rage_clicks_detected"]},
        {"step_id": "b", "signals": ["high_drop_off"]},
        {"step_id": "c", "signals": ["high_drop_off"]},
        {"step_id": "d", "signals": []},
    ]
    r = correlate_signals(scores)
    # threshold = max(2, int(4*0.5)) = max(2,2) = 2
    # rage_clicks_detected appears in 1 step → not systemic
    assert "rage_clicks_detected" not in r["systemic_signals"]
    # high_drop_off appears in 2 steps → systemic
    assert "high_drop_off" in r["systemic_signals"]


def test_correlate_empty_list_returns_safe_defaults():
    """Empty scores list → empty results, no crash."""
    r = correlate_signals([])
    assert r["systemic_signals"] == []
    assert r["signal_frequency"] == {}
    assert r["co_occurring_patterns"] == []


def test_correlate_signal_frequency_counts():
    """Signal frequency counts are accurate."""
    scores = [
        {"step_id": "a", "signals": ["high_drop_off", "frequent_errors"]},
        {"step_id": "b", "signals": ["high_drop_off"]},
    ]
    r = correlate_signals(scores)
    assert r["signal_frequency"]["high_drop_off"]   == 2
    assert r["signal_frequency"]["frequent_errors"] == 1


def test_correlate_co_occurring_patterns():
    """Pairs co-occurring in 2+ steps appear in co_occurring_patterns."""
    scores = [
        {"step_id": "a", "signals": ["high_drop_off", "frequent_errors"]},
        {"step_id": "b", "signals": ["high_drop_off", "frequent_errors"]},
        {"step_id": "c", "signals": ["high_drop_off"]},
    ]
    r = correlate_signals(scores)
    # ("frequent_errors", "high_drop_off") appears in steps a and b → count=2
    pairs = [tuple(sorted(p["signals"])) for p in r["co_occurring_patterns"]]
    assert ("frequent_errors", "high_drop_off") in pairs


def test_correlate_analysis_text_present():
    """analysis field is always a non-empty string."""
    r = correlate_signals([{"step_id": "x", "signals": []}])
    assert isinstance(r["analysis"], str)
    assert len(r["analysis"]) > 0


# ── Tests: Integration (end-to-end pipeline) ──────────────────────────────────

def test_full_pipeline_no_crash(low_step, high_step):
    """Full score → dropoff → correlate pipeline runs without exceptions."""
    # Step 1: Score all steps
    all_scores = score_all_steps([low_step, high_step])
    assert all_scores["total_steps"] == 2

    # Step 2: Detect drop-offs from score results
    funnel = [
        {
            "step_id":      s["step_id"],
            "drop_off_pct": s["drop_off_rate"] * 100,
            "users":        500,
        }
        for s in all_scores["scores"]
    ]
    dropoffs = detect_dropoffs(funnel)
    assert isinstance(dropoffs, dict)
    assert "count" in dropoffs

    # Step 3: Correlate signals
    correlation = correlate_signals(all_scores["scores"])
    assert isinstance(correlation, dict)
    assert "systemic_signals" in correlation


def test_score_all_steps_then_filter_critical(low_step, high_step):
    """score_all_steps correctly identifies critical vs non-critical steps."""
    r = score_all_steps([low_step, high_step])
    # email_verification is critical
    email_result = next(s for s in r["scores"] if s["step_id"] == "email_verification")
    landing_result = next(s for s in r["scores"] if s["step_id"] == "landing_page")
    assert email_result["is_critical"] is True
    assert landing_result["is_critical"] is False


def test_compute_score_private_function_matches_public(high_step):
    """_compute_score produces results consistent with score_friction output."""
    score, signals, confidence = _compute_score(high_step)
    public_result = score_friction(high_step)
    assert score       == public_result["score"]
    assert signals     == public_result["signals"]
    assert confidence  == public_result["confidence"]
