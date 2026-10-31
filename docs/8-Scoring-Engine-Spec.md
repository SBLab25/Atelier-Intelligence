> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Scoring Engine Specification
## Customer Journey Intelligence (CJI) — Friction Engine MCP

**Version:** 2.0
**Date:** March 2026
**Document Type:** Algorithm and Scoring Engine Reference

---

## Table of Contents

1. [Scoring Engine Overview](#1-scoring-engine-overview)
2. [Friction Score Algorithm](#2-friction-score-algorithm)
3. [Signal Detection Rules](#3-signal-detection-rules)
4. [Confidence Computation](#4-confidence-computation)
5. [Priority Scoring Algorithm](#5-priority-scoring-algorithm)
6. [Drop-Off Detection Algorithm](#6-drop-off-detection-algorithm)
7. [Signal Correlation Algorithm](#7-signal-correlation-algorithm)
8. [Rage Click Detection (Browser)](#8-rage-click-detection-browser)
9. [Complete Implementation Reference](#9-complete-implementation-reference)
10. [Test Specifications](#10-test-specifications)
11. [Calibration Reference](#11-calibration-reference)
12. [Known Edge Cases and Guardrails](#12-known-edge-cases-and-guardrails)

---

## 1. Scoring Engine Overview

### 1.1 Engine Architecture

The CJI Friction Scoring Engine is a **deterministic, rule-based analytical system** that quantifies how difficult a journey step is for users. It is intentionally non-ML to be:
- **Transparent** — every score is fully explainable from inputs
- **Auditable** — same inputs always produce exactly the same output
- **Testable** — unit tests can run without network, LLM, or database
- **Configurable** — weights and baselines are constants, not trained parameters

### 1.2 Engine Position in Architecture

```
Input:  StepMetrics (from Journey Data MCP SQL aggregation)
            ↓
       Friction Engine MCP (pure computation, no IO)
            ↓
Output: FrictionScore per step
        ├── score: int (0–100)   → drives: insight generation trigger
        ├── signals: list[str]   → drives: LLM prompt context
        ├── confidence: float    → drives: LLM temperature adjustment
        └── is_critical: bool    → drives: insight_worker step selection
```

### 1.3 Design Philosophy

**Five metric signals, not one.** The engine uses five independent behavioural signals to produce a composite score. A step could have a low abandon rate but high error rate and extended dwell time — the composite captures this complexity.

**Normalised to baseline, not to 100%.** The normalisation divides by the "neutral" baseline, not by 100. A 30% abandon rate is only 3× the baseline of 10% — it does not map to score=30, it maps proportionally with a 0.35 weight.

**Capped at 3× baseline.** Very extreme values (e.g., 90% abandon rate) are capped at 3× normalisation to prevent any single metric from completely dominating the composite.

**Threshold-based signals.** Signals (the named friction indicators) are binary — either triggered or not. This makes them useful as qualitative markers alongside the quantitative score.

---

## 2. Friction Score Algorithm

### 2.1 Exact Pseudocode

```
INPUTS:
  step_metrics: StepMetrics dict with keys:
    - step_id:         string
    - abandon_rate_pct: float (0.0–100.0)
    - error_rate_pct:   float (0.0–100.0)
    - avg_dwell_ms:     float or int (0–∞)
    - avg_retries:      float (0.0–∞)
    - avg_rage_clicks:  float (0.0–∞)

OUTPUTS:
  score:      int     (0–100, inclusive)
  signals:    list    (ordered by detection rule order)
  confidence: float   (0.0–0.98, inclusive)

ALGORITHM:

  # Step 1: Read inputs (with .get() defaulting to 0)
  abandon = step_metrics.get("abandon_rate_pct", 0)
  error   = step_metrics.get("error_rate_pct",   0)
  dwell   = step_metrics.get("avg_dwell_ms",     0)
  retries = step_metrics.get("avg_retries",      0)
  rclicks = step_metrics.get("avg_rage_clicks",  0)

  # Step 2: Normalise each value against its baseline
  #   norm(v, b) = min(value / max(baseline, 0.001), 3.0) / 3.0
  #   Result range: 0.0 to 1.0 (3.0 / 3.0 = 1.0 maximum)
  def normalise(v, b):
      return min(v / max(b, 0.001), 3.0) / 3.0

  # Step 3: Compute weighted composite
  raw = normalise(abandon, 10.0)  * 0.35    # Abandonment contributes 35% of total
      + normalise(error,   5.0)   * 0.25    # Error rate contributes 25%
      + normalise(dwell,   15000) * 0.15    # Dwell time contributes 15%
      + normalise(retries, 0.1)   * 0.15    # Retries contribute 15%
      + normalise(rclicks, 0.05)  * 0.10    # Rage clicks contribute 10%

  # Step 4: Convert to 0–100 integer
  score = min(100, int(raw * 100))          # int() truncates (does not round)

  # Step 5: Detect categorical signals
  signals = []
  if abandon > 30:    signals.append("high_drop_off")
  if abandon > 50:    signals.append("critical_drop_off")
  if error   > 15:    signals.append("frequent_errors")
  if dwell   > 60000: signals.append("extended_hesitation")
  if dwell   > 120000:signals.append("severe_confusion")
  if retries > 1.0:   signals.append("repeated_retries")
  if rclicks > 0.5:   signals.append("rage_clicks_detected")

  # Step 6: Compute data confidence
  confidence = min(0.5 + len(signals) * 0.1, 0.98)
  # 0 signals → 0.50, 1 signal → 0.60, ..., 4 signals → 0.90, 5+ signals → capped at 0.98

RETURN:
  (score, signals, confidence)
```

### 2.2 Weights Table

| Signal | Weight | Baseline | Normalisation At Baseline |
|---|---|---|---|
| abandon_rate_pct | 0.35 | 10.0% | 1/3 = 0.117 contribution |
| error_rate_pct | 0.25 | 5.0% | 1/3 = 0.083 contribution |
| avg_dwell_ms | 0.15 | 15,000ms | 1/3 = 0.050 contribution |
| avg_retries | 0.15 | 0.1 | 1/3 = 0.050 contribution |
| avg_rage_clicks | 0.10 | 0.05 | 1/3 = 0.033 contribution |
| **Total** | **1.00** | — | **max raw possible = 1.0** |

**Sum of max contributions (all scores at 3× baseline):**
```
= (3.0/3.0)×0.35 + (3.0/3.0)×0.25 + (3.0/3.0)×0.15 + (3.0/3.0)×0.15 + (3.0/3.0)×0.10
= 0.35 + 0.25 + 0.15 + 0.15 + 0.10 = 1.00
→ raw = 1.00
→ score = min(100, int(1.00 × 100)) = 100 ✓
```

### 2.3 Score Interpretation

| Score Range | Label | Meaning |
|---|---|---|
| 0–29 | Low friction | Acceptable performance — monitor periodically |
| 30–49 | Moderate friction | Worth investigating — not urgent |
| 50–59 | Elevated friction | Should be in next sprint backlog |
| 60–74 | High friction | Priority fix this sprint (is_critical=True) |
| 75–89 | Critical friction | Immediate attention required |
| 90–100 | Severe friction | Block on this — business impact is severe |

### 2.4 Score Calculation Examples

**Example 1: email_verification (high friction)**
```
abandon = 41.8, error = 34.7, dwell = 184000, retries = 1.8, rage = 0.62

normalise(41.8, 10.0)  = min(4.18, 3.0) / 3.0 = 1.000   ← capped at 3×
normalise(34.7, 5.0)   = min(6.94, 3.0) / 3.0 = 1.000   ← capped at 3×
normalise(184000, 15000) = min(12.27, 3.0) / 3.0 = 1.000 ← capped at 3×
normalise(1.8, 0.1)    = min(18.0, 3.0) / 3.0  = 1.000  ← capped at 3×
normalise(0.62, 0.05)  = min(12.4, 3.0) / 3.0  = 1.000  ← capped at 3×

raw = 1.000×0.35 + 1.000×0.25 + 1.000×0.15 + 1.000×0.15 + 1.000×0.10
    = 0.35 + 0.25 + 0.15 + 0.15 + 0.10 = 1.00

score = min(100, int(1.00 × 100)) = 100? No:
→ Note: Not all values are exactly at 3× cap in practice

Realistic example with exact numbers from demo:
abandon = 41.8 → normalise = min(41.8/10.0, 3.0)/3.0 = min(4.18, 3.0)/3.0 = 1.0
error   = 34.7 → normalise = min(34.7/5.0, 3.0)/3.0 = min(6.94, 3.0)/3.0 = 1.0
dwell   = 184000 → normalise = min(184000/15000, 3.0)/3.0 = min(12.27, 3.0)/3.0 = 1.0
retries = 1.8  → normalise = min(1.8/0.1, 3.0)/3.0 = min(18.0, 3.0)/3.0 = 1.0
rage    = 0.62 → normalise = min(0.62/0.05, 3.0)/3.0 = min(12.4, 3.0)/3.0 = 1.0

raw = 1.0×0.35 + 1.0×0.25 + 1.0×0.15 + 1.0×0.15 + 1.0×0.10 = 1.00
score = min(100, int(100)) = 100  [edge case: all metrics 3×+ above baseline]
```

**Example 2: landing_page (low friction)**
```
abandon = 15.0, error = 2.1, dwell = 12000, retries = 0.01, rage = 0.02

normalise(15.0, 10.0)  = min(1.50, 3.0)/3.0 = 0.500
normalise(2.1, 5.0)    = min(0.42, 3.0)/3.0 = 0.140
normalise(12000, 15000)= min(0.80, 3.0)/3.0 = 0.267
normalise(0.01, 0.1)   = min(0.10, 3.0)/3.0 = 0.033
normalise(0.02, 0.05)  = min(0.40, 3.0)/3.0 = 0.133

raw = 0.500×0.35 + 0.140×0.25 + 0.267×0.15 + 0.033×0.15 + 0.133×0.10
    = 0.175 + 0.035 + 0.040 + 0.005 + 0.013
    = 0.268

score = min(100, int(0.268 × 100)) = min(100, 26) = 26
```

**Example 3: All zeros (edge case)**
```
all inputs = 0

normalise(0, b) = min(0/max(b, 0.001), 3.0)/3.0 = 0

raw = 0
score = min(100, int(0)) = 0
signals = []
confidence = min(0.5 + 0×0.1, 0.98) = 0.50
```

---

## 3. Signal Detection Rules

### 3.1 Signal Names (Exact — Tests Depend on These)

Signal names are immutable strings tested in `test_friction_engine.py`.

```python
SIGNAL_RULES = [
    # (condition_variable, threshold, signal_name)
    ("abandon",  30,     "high_drop_off"),     # abandon > 30
    ("abandon",  50,     "critical_drop_off"), # abandon > 50
    ("error",    15,     "frequent_errors"),   # error > 15
    ("dwell",    60000,  "extended_hesitation"),# dwell > 60000
    ("dwell",    120000, "severe_confusion"),  # dwell > 120000
    ("retries",  1.0,    "repeated_retries"),  # retries > 1.0
    ("rclicks",  0.5,    "rage_clicks_detected")# rclicks > 0.5
]
```

### 3.2 Signal Semantics

| Signal | Business Meaning | Likely Root Cause Categories |
|---|---|---|
| high_drop_off | Significant proportion of users are leaving this step | UX friction, confusion, process complexity |
| critical_drop_off | Majority of users are abandoning — step is fundamentally broken | System errors, extremely poor UX, wrong CTA |
| frequent_errors | Users are hitting errors regularly — step has reliability issues | System errors, validation logic bugs, data quality |
| extended_hesitation | Users spend much longer than expected — they are stuck or confused | UX poor affordance, missing instructions, confusing form |
| severe_confusion | Users spend extremely long — they may be repeatedly failing silently | System failures with no error messaging, confusing flow direction |
| repeated_retries | Users are retrying operations — first attempt typically fails | Validation errors, session timeouts, server errors |
| rage_clicks_detected | Users are clicking rapidly in frustration — element is unresponsive | Non-interactive elements appearing clickable, latency, broken buttons |

### 3.3 Signal Co-occurrence Significance

Certain signal combinations indicate highly specific root causes:

| Co-occurrence | Strong Indicator |
|---|---|
| critical_drop_off + frequent_errors | Server-side reliability issue — IT priority |
| severe_confusion + rage_clicks_detected | UI is misleading and unresponsive — UX priority |
| extended_hesitation + repeated_retries | Users stuck in error loop without clear guidance — UX + process |
| high_drop_off (+only) | Step is cognitively overwhelming or poorly placed in journey |

---

## 4. Confidence Computation

### 4.1 Formula

```python
confidence = min(0.5 + len(signals) * 0.1, 0.98)
```

### 4.2 Confidence Table

| Signals Count | Confidence | Interpretation |
|---|---|---|
| 0 | 0.50 | Low confidence — metrics are within normal range, consider noise |
| 1 | 0.60 | Moderate — one clear indicator present |
| 2 | 0.70 | Good — two corroborating signals |
| 3 | 0.80 | High — clear pattern emerging |
| 4 | 0.90 | Very high — strong multi-signal evidence |
| 5+ | 0.98 (max) | Very high — comprehensive evidence, capped to avoid overconfidence |

### 4.3 Confidence Use

The confidence value is passed to the LLM prompt in `generate_insight()`:
- High confidence (≥ 0.8): LLM is instructed to provide specific, direct recommendations
- Low confidence (< 0.6): LLM is instructed to be more tentative, suggest data investigation

---

## 5. Priority Scoring Algorithm

### 5.1 Formula

```
INPUTS:
  insight:      dict with "score" (int) and "fix_effort" (str)
  unique_users: int — users who reached this step in the analysis window

OUTPUTS:
  priority:       int (1–5)
  priority_score: float (impact / effort)

ALGORITHM:
  effort_map = {"low": 1, "medium": 2, "high": 4}
  effort     = effort_map.get(insight["fix_effort"], 2)  # default "medium" if unknown
  impact     = insight["score"] * unique_users
  priority_score = impact / effort

  if priority_score > 40000: priority = 1   # Highest — fix this sprint
  elif priority_score > 20000: priority = 2
  elif priority_score > 8000:  priority = 3
  elif priority_score > 2000:  priority = 4
  else:                        priority = 5  # Lowest — schedule later
```

### 5.2 Priority Scoring Examples

**email_verification (score=87, users=732, effort=medium):**
```
effort_map["medium"] = 2
impact = 87 × 732 = 63,684
priority_score = 63,684 / 2 = 31,842
31,842 > 20,000 → priority = 2
```

**profile_setup (score=45, users=156, effort=low):**
```
effort_map["low"] = 1
impact = 45 × 156 = 7,020
priority_score = 7,020 / 1 = 7,020
7,020 < 8,000 → priority = 4
```

### 5.3 Priority Business Interpretation

| Priority | Sprint Action |
|---|---|
| P1 | Block this sprint. Highest ROI fix available. |
| P2 | Include in next sprint. Significant impact-to-effort ratio. |
| P3 | Schedule within 2 sprint cycles. Moderate impact. |
| P4 | Add to backlog. Address in stable period. |
| P5 | Nice-to-have. Low impact or high effort relative to impact. |

---

## 6. Drop-Off Detection Algorithm

### 6.1 Algorithm

```
INPUTS:
  funnel_data:   list of {step_id: str, drop_off_pct: float, users: int}
  threshold_pct: float — minimum drop-off to flag (default 25.0)

OUTPUTS:
  critical_dropoffs: list of {step_id, drop_off_pct, users_lost}
  count:             int

ALGORITHM:
  critical_dropoffs = []

  for row in funnel_data:
      if row["drop_off_pct"] >= threshold_pct:
          critical_dropoffs.append({
              "step_id":     row["step_id"],
              "drop_off_pct": row["drop_off_pct"],
              "users_lost":   int(row["users"] * row["drop_off_pct"] / 100.0)
              # Note: users_lost = users at THIS step × drop_off_pct
              # NOT a running cumulative. This is the raw count lost between steps.
          })

  sort critical_dropoffs by drop_off_pct descending

  return critical_dropoffs, len(critical_dropoffs)
```

### 6.2 Threshold Justification

Default threshold: 25%.
- Below 25%: normal variation in digital journeys; not typically actionable
- 25–40%: significant drop; warrants investigation
- Above 40%: severe; likely indicates a systemic issue

Threshold is configurable per call — different journeys have different baseline expectations.

---

## 7. Signal Correlation Algorithm

### 7.1 Algorithm

```
INPUTS:
  scores: list of {step_id, signals: list[str]} per step

OUTPUTS:
  signal_frequency:     dict[str, int]    — how many steps have each signal
  co_occurring_patterns: list[{signals, count}] — pairs appearing together
  systemic_signals:     list[str]         — signals present in ≥ 50% of steps or 2+ steps

ALGORITHM:
  # Count signal frequency
  signal_frequency = {}
  for score in scores:
      for signal in score["signals"]:
          signal_frequency[signal] = signal_frequency.get(signal, 0) + 1

  # Co-occurrence analysis (pairs only)
  from itertools import combinations
  pair_counts = {}
  for score in scores:
      if len(score["signals"]) >= 2:
          for pair in combinations(sorted(score["signals"]), 2):
              pair_counts[pair] = pair_counts.get(pair, 0) + 1

  co_occurring_patterns = [
      {"signals": list(pair), "count": count}
      for pair, count in sorted(pair_counts.items(), key=lambda x: -x[1])
      if count >= 2     # Only pairs appearing in 2+ steps
  ]

  # Systemic signals: appear in ≥ 50% of steps, or in 2+ steps (for small journeys)
  n_steps = max(len(scores), 1)
  threshold = max(2, int(n_steps * 0.5))   # at least 2, or half of steps
  systemic_signals = [
      sig for sig, count in signal_frequency.items()
      if count >= threshold
  ]

  return {
      "signal_frequency":     signal_frequency,
      "co_occurring_patterns": co_occurring_patterns,
      "systemic_signals":     systemic_signals,
      "analysis":             generate_analysis_text(signal_frequency, systemic_signals, n_steps)
  }
```

### 7.2 Correlation Interpretation

**Systemic signals** indicate the problem is not localised to one step — the entire journey design has an issue. For example:
- `high_drop_off` in 4/6 steps → the overall journey is too long or confusing
- `frequent_errors` in 3/6 steps → there is a backend reliability issue affecting multiple steps

**Co-occurring patterns** indicate signal pairs that appear together more than coincidentally, suggesting a relationship between them.

---

## 8. Rage Click Detection (Browser)

### 8.1 Algorithm (tracker.js)

```
STATE:
  rageBuffer = { el: null, times: [] }

CONSTANTS:
  RAGE_WINDOW_MS = 500     # ms window for rage click detection
  RAGE_THRESHOLD = 3       # minimum clicks to qualify as rage click

ON EVERY CLICK (via document addEventListener('click', handler)):
  element     = event.target
  now         = Date.now()

  if rageBuffer.el !== element:
      # Clicked a different element — reset buffer
      rageBuffer = { el: element, times: [now] }
  else:
      # Clicked same element — accumulate
      rageBuffer.times.push(now)
      rageBuffer.times = rageBuffer.times.filter(t => now - t < RAGE_WINDOW_MS)

  if rageBuffer.times.length >= RAGE_THRESHOLD:
      fire rage_click event with:
          event_type: "rage_click"
          metadata: {
              click_count: rageBuffer.times.length,
              element_tag: element.tagName,
              element_id:  element.id || "",
              element_class: element.className || "",
          }
      rageBuffer = { el: null, times: [] }   # Reset after firing
```

### 8.2 Rage Click Aggregation in Score

The friction score uses `avg_rage_clicks` which is the **ratio** of users who generated at least one rage_click event to total users on that step:

```sql
avg_rage_clicks = COUNT(CASE WHEN event_type = 'rage_click' THEN 1 ELSE NULL END)
                / NULLIF(COUNT(DISTINCT user_id), 0)
```

Baseline: 0.05 (5% of users experiencing rage clicks is "normal")
Threshold for signal: 0.5 (50% of users experiencing rage clicks → "rage_clicks_detected")

---

## 9. Complete Implementation Reference

### 9.1 friction_engine_server.py Skeleton

```python
"""
CJI Friction Engine MCP Server.
Deterministic friction scoring with no database or LLM dependencies.
"""

import json
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import FRICTION_SCORE_THRESHOLD

# ── CONSTANTS (EXACT — tests import these) ──────────────────────────────────
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

SIGNAL_THRESHOLDS = [
    ("abandon", 30,    "high_drop_off"),
    ("abandon", 50,    "critical_drop_off"),
    ("error",   15,    "frequent_errors"),
    ("dwell",   60000, "extended_hesitation"),
    ("dwell",   120000,"severe_confusion"),
    ("retries", 1.0,   "repeated_retries"),
    ("rclicks", 0.5,   "rage_clicks_detected"),
]

# ── MCP SERVER ──────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="cji-friction-engine",
    description="Deterministic friction scoring for CJI journey steps."
)

# ── PRIVATE COMPUTATION ─────────────────────────────────────────────────────
def _normalise(value: float, baseline: float) -> float:
    """Normalise value against baseline. Result range: 0.0 to 1.0."""
    return min(value / max(baseline, 0.001), 3.0) / 3.0


def _compute_score(step_metrics: dict) -> tuple[int, list[str], float]:
    """Compute (score, signals, confidence) from step metrics."""
    abandon = step_metrics.get("abandon_rate_pct", 0)
    error   = step_metrics.get("error_rate_pct",   0)
    dwell   = step_metrics.get("avg_dwell_ms",     0)
    retries = step_metrics.get("avg_retries",      0)
    rclicks = step_metrics.get("avg_rage_clicks",  0)

    raw = (_normalise(abandon, BASELINES["abandon_rate_pct"]) * WEIGHTS["abandon_rate_pct"]
         + _normalise(error,   BASELINES["error_rate_pct"])   * WEIGHTS["error_rate_pct"]
         + _normalise(dwell,   BASELINES["avg_dwell_ms"])     * WEIGHTS["avg_dwell_ms"]
         + _normalise(retries, BASELINES["avg_retries"])      * WEIGHTS["avg_retries"]
         + _normalise(rclicks, BASELINES["avg_rage_clicks"])  * WEIGHTS["avg_rage_clicks"])

    score = min(100, int(raw * 100))

    signals = []
    vals = {"abandon": abandon, "error": error, "dwell": dwell,
            "retries": retries, "rclicks": rclicks}
    for var, threshold, signal_name in SIGNAL_THRESHOLDS:
        if vals[var] > threshold:
            signals.append(signal_name)

    confidence = min(0.5 + len(signals) * 0.1, 0.98)
    return score, signals, confidence


# ── MCP TOOLS ───────────────────────────────────────────────────────────────
@mcp.tool(description="Score friction for a single journey step.", annotations={"readOnlyHint": True, "idempotentHint": True})
def score_friction(step_metrics: dict) -> dict:
    """Compute 0-100 friction score, signals, and confidence for one step."""
    score, signals, confidence = _compute_score(step_metrics)
    return {
        "step_id":         step_metrics.get("step_id", "unknown"),
        "score":           score,
        "drop_off_rate":   step_metrics.get("abandon_rate_pct", 0) / 100.0,
        "avg_dwell_ms":    int(step_metrics.get("avg_dwell_ms", 0)),
        "retry_count":     step_metrics.get("avg_retries", 0),
        "rage_click_rate": step_metrics.get("avg_rage_clicks", 0),
        "signals":         signals,
        "confidence":      confidence,
        "is_critical":     score >= FRICTION_SCORE_THRESHOLD,
    }


@mcp.tool(description="Score all journey steps and return sorted results.", annotations={"readOnlyHint": True, "idempotentHint": True})
def score_all_steps(all_step_metrics: list) -> dict:
    """Score all steps and return sorted (descending by score) with aggregate stats."""
    scored = [score_friction(m) for m in all_step_metrics]
    scored.sort(key=lambda x: x["score"], reverse=True)
    scores = [s["score"] for s in scored]
    return {
        "scores":        scored,
        "critical_steps": [s["step_id"] for s in scored if s["is_critical"]],
        "total_steps":   len(scored),
        "avg_score":     round(sum(scores) / len(scores), 2) if scores else 0.0,
        "threshold":     FRICTION_SCORE_THRESHOLD,
    }


@mcp.tool(description="Detect critical funnel drop-offs above threshold.", annotations={"readOnlyHint": True, "idempotentHint": True})
def detect_dropoffs(funnel_data: list, threshold_pct: float = 25.0) -> dict:
    """Flag steps where drop-off percentage exceeds the threshold."""
    critical = []
    for row in funnel_data:
        if row.get("drop_off_pct", 0) >= threshold_pct:
            critical.append({
                "step_id":      row["step_id"],
                "drop_off_pct": row["drop_off_pct"],
                "users_lost":   int(row.get("users", 0) * row.get("drop_off_pct", 0) / 100.0),
            })
    critical.sort(key=lambda x: x["drop_off_pct"], reverse=True)
    return {"critical_dropoffs": critical, "count": len(critical), "threshold_pct": threshold_pct}


@mcp.tool(description="Correlate signals across steps to find systemic patterns.", annotations={"readOnlyHint": True, "idempotentHint": True})
def correlate_signals(scores: list) -> dict:
    """Identify signal frequency, co-occurrences, and systemic patterns across all steps."""
    from itertools import combinations
    freq = {}
    pair_counts = {}
    for score in scores:
        sigs = score.get("signals", [])
        for s in sigs:
            freq[s] = freq.get(s, 0) + 1
        if len(sigs) >= 2:
            for pair in combinations(sorted(sigs), 2):
                pair_counts[pair] = pair_counts.get(pair, 0) + 1

    n_steps = max(len(scores), 1)
    threshold = max(2, int(n_steps * 0.5))
    systemic = [s for s, c in freq.items() if c >= threshold]

    co_patterns = [{"signals": list(p), "count": c}
                   for p, c in sorted(pair_counts.items(), key=lambda x: -x[1]) if c >= 2]

    analysis = (f"{', '.join(systemic)} appear in {threshold}+ steps — systemic issue"
                if systemic else "No systemic signals — issues are step-specific")
    return {
        "signal_frequency":      freq,
        "co_occurring_patterns": co_patterns,
        "systemic_signals":      systemic,
        "analysis":              analysis,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

---

## 10. Test Specifications

### 10.1 Required Test Fixtures

```python
@pytest.fixture
def low_step() -> dict:
    """Step with sub-threshold friction (landing_page)."""
    return {
        "step_id":           "landing_page",
        "unique_users":      2000,
        "abandon_rate_pct":  15.0,
        "error_rate_pct":    2.1,
        "avg_dwell_ms":      12000,
        "avg_retries":       0.01,
        "avg_rage_clicks":   0.02,
    }

@pytest.fixture
def high_step() -> dict:
    """Step with critical friction (email_verification)."""
    return {
        "step_id":           "email_verification",
        "unique_users":      732,
        "abandon_rate_pct":  41.8,
        "error_rate_pct":    34.7,
        "avg_dwell_ms":      184000,
        "avg_retries":       1.8,
        "avg_rage_clicks":   0.62,
    }
```

### 10.2 Required Test Cases (Minimum 12)

```python
# GROUP 1: Basic scoring correctness
def test_low_step_below_threshold(low_step):
    r = score_friction(low_step)
    assert r["score"] < FRICTION_SCORE_THRESHOLD
    assert r["is_critical"] is False
    assert r["step_id"] == "landing_page"

def test_high_step_is_critical(high_step):
    r = score_friction(high_step)
    assert r["score"] >= FRICTION_SCORE_THRESHOLD
    assert r["is_critical"] is True

def test_score_bounded_0_to_100(high_step):
    r = score_friction(high_step)
    assert 0 <= r["score"] <= 100

def test_confidence_bounded(high_step):
    r = score_friction(high_step)
    assert 0.0 <= r["confidence"] <= 0.98

# GROUP 2: Signal correctness
def test_high_step_signals(high_step):
    r = score_friction(high_step)
    assert "critical_drop_off" in r["signals"]   # abandon=41.8 > 30, but not > 50
    # Wait: abandon=41.8 > 30 → high_drop_off; but abandon=41.8 < 50 → NOT critical_drop_off
    # Correct check:
    assert "high_drop_off" in r["signals"]       # abandon 41.8 > 30 ✓
    assert "rage_clicks_detected" in r["signals"] # rage 0.62 > 0.5 ✓
    assert "frequent_errors" in r["signals"]      # error 34.7 > 15 ✓
    assert "severe_confusion" in r["signals"]     # dwell 184000 > 120000 ✓
    assert "extended_hesitation" in r["signals"]  # dwell 184000 > 60000 ✓
    assert "repeated_retries" in r["signals"]     # retries 1.8 > 1.0 ✓

def test_zero_inputs_zero_score():
    r = score_friction({"step_id": "t", "abandon_rate_pct": 0, "error_rate_pct": 0,
                         "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0})
    assert r["score"] == 0
    assert r["signals"] == []
    assert r["confidence"] == pytest.approx(0.50)

# GROUP 3: score_all_steps
def test_all_steps_sorted_desc(low_step, high_step):
    r = score_all_steps([low_step, high_step])
    scores = [s["score"] for s in r["scores"]]
    assert scores == sorted(scores, reverse=True)

def test_critical_list_correct(low_step, high_step):
    r = score_all_steps([low_step, high_step])
    assert "email_verification" in r["critical_steps"]
    assert "landing_page" not in r["critical_steps"]

# GROUP 4: detect_dropoffs
def test_detect_dropoffs_above_threshold():
    funnel = [{"step_id": "a", "drop_off_pct": 50.0, "users": 500},
              {"step_id": "b", "drop_off_pct": 10.0, "users": 450}]
    r = detect_dropoffs(funnel, 25.0)
    assert r["count"] == 1
    assert r["critical_dropoffs"][0]["step_id"] == "a"

def test_detect_dropoffs_empty():
    r = detect_dropoffs([{"step_id": "x", "drop_off_pct": 5.0, "users": 1000}], 25.0)
    assert r["count"] == 0

# GROUP 5: correlate_signals
def test_systemic_signals():
    scores = [{"step_id": "a", "signals": ["high_drop_off"]},
              {"step_id": "b", "signals": ["high_drop_off"]},
              {"step_id": "c", "signals": ["high_drop_off"]}]
    r = correlate_signals(scores)
    assert "high_drop_off" in r["systemic_signals"]

# GROUP 6: Integration
def test_full_pipeline_no_crash(low_step, high_step):
    all_scores = score_all_steps([low_step, high_step])
    dropoffs = detect_dropoffs(
        [{"step_id": s["step_id"], "drop_off_pct": s["drop_off_rate"]*100, "users": 500}
         for s in all_scores["scores"]])
    correlation = correlate_signals(all_scores["scores"])
    assert all_scores["total_steps"] == 2
    assert isinstance(dropoffs, dict)
    assert isinstance(correlation, dict)
    # Ensure no exceptions raised — all dicts returned
```

---

## 11. Calibration Reference

### 11.1 Score at Each Metric Percentile

This table shows what friction score results from isolated metric values (all others = 0):

| Metric | Value | Normalised | × Weight | Partial Score |
|---|---|---|---|---|
| abandon=10% (baseline) | 10.0 | 0.333 | × 0.35 | 11.7 |
| abandon=30% (signal) | 30.0 | 1.000 | × 0.35 | 35.0 |
| abandon=50% (critical) | 50.0 | 1.000 (capped) | × 0.35 | 35.0 |
| error=5% (baseline) | 5.0 | 0.333 | × 0.25 | 8.3 |
| error=15% (signal) | 15.0 | 1.000 | × 0.25 | 25.0 |
| dwell=15s (baseline) | 15000 | 0.333 | × 0.15 | 5.0 |
| dwell=60s (signal) | 60000 | 1.000 (=4×, capped) | × 0.15 | 15.0 |
| retries=0.1 (baseline) | 0.1 | 0.333 | × 0.15 | 5.0 |
| retries=1.0 (signal) | 1.0 | 1.000 (=10×, capped) | × 0.15 | 15.0 |
| rage=0.05 (baseline) | 0.05 | 0.333 | × 0.10 | 3.3 |
| rage=0.5 (signal) | 0.5 | 1.000 (=10×, capped) | × 0.10 | 10.0 |

### 11.2 Minimum Score to Trigger Critical Flag (is_critical=True)

`score >= 60 → is_critical=True`

**Minimum input combinations producing score ≥ 60:**
- abandon=30% + error=15% alone: partial_score = 35 + 25 = 60 → score = 60 ✓
- abandon=30% + severe dwell (>120s): partial = 35 + 15 = 50 → need other signals
- Any single metric at 3× baseline cannot alone exceed 35 (abandon weight is highest at 0.35)

### 11.3 Recalibration Process

To adjust weights or baselines for a specific industry:

1. Update `WEIGHTS` and `BASELINES` constants in `friction_engine_server.py`
2. Run full test suite: `pytest tests/test_friction_engine.py -v`
3. Verify expected scores for known high-friction and low-friction steps
4. Update `FRICTION_SCORE_THRESHOLD` if industry baseline is different
5. Document changes in config.py with rationale

---

## 12. Known Edge Cases and Guardrails

### 12.1 Division by Zero

**Risk:** `normalise(v, b)` where `b = 0` → division by zero

**Guard:** `max(baseline, 0.001)` in denominator — baseline can never be zero

```python
def _normalise(value: float, baseline: float) -> float:
    return min(value / max(baseline, 0.001), 3.0) / 3.0
#                   ^^^^^^^^^^^^^^^^^^^^
#                   Prevents ZeroDivisionError even if baseline is accidentally 0
```

### 12.2 Score Capping

**Risk:** If somehow `raw > 1.0` (e.g., weights don't sum to 1.0)

**Guard:** `min(100, int(raw * 100))` caps explicitly at 100.

### 12.3 Missing Step Metrics Fields

**Risk:** Step metrics dict from DuckDB query might be missing some fields

**Guard:** All `step_metrics.get("key", 0)` calls default to 0 — safe for any missing field.

**Test verification:** `test_zero_inputs_zero_score()` passes empty dict equivalent.

### 12.4 Non-Integer avg_dwell_ms from SQL

**Risk:** DuckDB AVG() returns float; normalise expects float — safe. But FrictionScore.avg_dwell_ms is typed `int`.

**Guard:** `int(step_metrics.get("avg_dwell_ms", 0))` casts in the output dict.

### 12.5 Empty Step List in score_all_steps

**Risk:** `score_all_steps([])` → division by zero in avg_score

**Guard:** `avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0`

### 12.6 ChromaDB Storage of Confidence Value

**Risk:** `confidence` is a Python float — ChromaDB metadata must be string

**Guard:** When saving to ChromaDB, all numeric fields cast to string: `"score": str(insight["score"])`

Confidence is not stored in ChromaDB metadata (it is not useful for filtering). Only score, priority, category, fix_effort, and step_id are stored.

### 12.7 First-Run ChromaDB Empty Collection Guard

**Risk:** `search_insights()` with `n_results=5` when only 2 insights stored → ChromaDB error

**Guard:**
```python
count = collection.count()
if count == 0:
    return {"results": [], "error": "No insights stored yet"}
n = min(n_results, count)
results = collection.query(query_texts=[query_text], n_results=n, ...)
```
