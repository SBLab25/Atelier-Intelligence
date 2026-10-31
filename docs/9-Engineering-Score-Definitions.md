> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Engineering Score Definitions
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** Engineering Metric Definitions Reference

---

## Table of Contents

1. [Overview: What "Score" Means in CJI](#1-overview-what-score-means-in-cji)
2. [Friction Score](#2-friction-score)
3. [Priority Score](#3-priority-score)
4. [Confidence Score](#4-confidence-score)
5. [Drop-Off Percentage](#5-drop-off-percentage)
6. [Average Dwell Time (avg_dwell_ms)](#6-average-dwell-time-avg_dwell_ms)
7. [Error Rate (error_rate_pct)](#7-error-rate-error_rate_pct)
8. [Abandon Rate (abandon_rate_pct)](#8-abandon-rate-abandon_rate_pct)
9. [Rage Click Rate (avg_rage_clicks)](#9-rage-click-rate-avg_rage_clicks)
10. [Retry Average (avg_retries)](#10-retry-average-avg_retries)
11. [Completion Rate (completion_rate_pct)](#11-completion-rate-completion_rate_pct)
12. [Signal Definitions](#12-signal-definitions)
13. [Insight Fields](#13-insight-fields)
14. [Metric Relationship Map](#14-metric-relationship-map)
15. [Metric Limits and Boundaries](#15-metric-limits-and-boundaries)

---

## 1. Overview: What "Score" Means in CJI

CJI produces multiple distinct numerical values that are all informally called "scores" but have very different meanings and uses. This document precisely defines every metric.

### 1.1 Score Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    FRICTION SCORE (0–100)                   │
│  Per-step composite metric. Main analytical output.         │
│  Computed: Friction Engine MCP → score_friction()           │
│  Used for: Triggering insights, chart colour-coding,        │
│            ranking in report                                │
├─────────────────────────────────────────────────────────────┤
│                    PRIORITY SCORE (float)                   │
│  Per-insight impact-to-effort ratio. Used for ranking only. │
│  Computed: Insight MCP → prioritise_fix()                   │
│  Used for: Determining priority 1–5 label only              │
│  NOT displayed to users directly                            │
├─────────────────────────────────────────────────────────────┤
│                    PRIORITY (1–5)                           │
│  Ordinal label derived from priority_score thresholds.      │
│  Displayed as: P1, P2, P3, P4, P5 in report table          │
├─────────────────────────────────────────────────────────────┤
│                    CONFIDENCE (0.0–0.98)                    │
│  Signal-count-based data quality indicator.                 │
│  Passed to: LLM prompt as context                           │
│  NOT displayed directly in dashboard or report              │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Aggregated Metrics (from SQL, Not Scored)

The following are computed SQL aggregations. They are **inputs** to the scoring engine, not outputs:
- `abandon_rate_pct` — from SQL COUNT(abandon events) / COUNT(distinct users)
- `error_rate_pct` — from SQL COUNT(error events) / COUNT(distinct users)
- `avg_dwell_ms` — from SQL AVG(duration_ms) of page_view and step_complete events
- `avg_retries` — from SQL AVG(retry_count field in error event metadata)
- `avg_rage_clicks` — from SQL ratio of users with rage_click events

---

## 2. Friction Score

### 2.1 Definition

**Type:** Integer  
**Range:** 0 to 100 (inclusive)  
**Unit:** Dimensionless (composite)  
**Direction:** Higher = more friction = worse user experience

A per-step composite score that quantifies how difficult a journey step is for users, based on five weighted behavioural signals.

### 2.2 What It Measures

The friction score measures the **aggregate difficulty** of completing a specific journey step. It is not a percentage, a satisfaction rating, or an NPS. It is an engineered estimate of step-level friction intensity based on observable user behaviour signals.

### 2.3 Computation

```
score = min(100, int(raw × 100))

raw = Σ (normalise(metric_i, baseline_i) × weight_i)

Where:
  normalise(v, b) = min(v / max(b, 0.001), 3.0) / 3.0
  
  Contributions:
    abandon_rate_pct: weight=0.35, baseline=10.0
    error_rate_pct:   weight=0.25, baseline=5.0
    avg_dwell_ms:     weight=0.15, baseline=15000
    avg_retries:      weight=0.15, baseline=0.1
    avg_rage_clicks:  weight=0.10, baseline=0.05
```

### 2.4 Scale Interpretation

| Score | Band | Business Meaning |
|---|---|---|
| 0–29 | Green: Low | Step performs well. Monitor with quarterly review. |
| 30–49 | Yellow: Moderate | Some friction present. Add to UX backlog. |
| 50–59 | Orange: Elevated | Friction impacting observable % of users. Plan in upcoming sprint. |
| 60–74 | Red: High | Significant friction. Stop-priority for product team. |
| 75–89 | Dark Red: Critical | Severe user struggling. Escalate to business leadership. |
| 90–100 | Black: Severe | Step is effectively broken. Immediate business impact. |

### 2.5 Critical Flag

`is_critical = (score >= FRICTION_SCORE_THRESHOLD)`

**Default threshold:** 60 (configurable via `config.FRICTION_SCORE_THRESHOLD`)

A step marked `is_critical=True` triggers:
1. `insight_worker` will call `generate_insight()` for this step
2. Step ID is added to `state["critical_steps"]`
3. Bar is coloured red (score ≥ 70) or amber (score 50–69) in charts

### 2.6 Properties

- **Deterministic:** Same inputs → same output, always, with no randomness
- **Bounded:** Never < 0, never > 100
- **Additive:** Combined signal effects accumulate linearly
- **Capped inputs:** No single metric can contribute more than its weight × 1.0 (3× normalisation cap)
- **Reproducible:** Frozen constants (weights, baselines, thresholds) ensure historical comparisons are valid

---

## 3. Priority Score

### 3.1 Definition

**Type:** Float  
**Range:** 0.0 to ∞ (theoretically unbounded)  
**Unit:** Impact-effort units (dimensionless)  
**Direction:** Higher = higher priority = fix sooner

A per-insight business value estimate that balances the friction score's impact against the engineering effort required to fix it.

### 3.2 What It Measures

Not how bad the problem is (that's the friction score), but **how much business value can be recovered per unit of engineering effort spent**. A moderate friction score on a high-traffic step with a low-effort fix can outrank a severe score on a low-traffic step with a complex fix.

### 3.3 Computation

```
effort_map = {"low": 1, "medium": 2, "high": 4}

effort         = effort_map[insight["fix_effort"]]
impact         = insight["score"] × unique_users
priority_score = impact / effort
```

**Priority thresholds:**
```
priority_score > 40,000 → priority = 1 (P1)
priority_score > 20,000 → priority = 2 (P2)
priority_score > 8,000  → priority = 3 (P3)
priority_score > 2,000  → priority = 4 (P4)
else                    → priority = 5 (P5)
```

### 3.4 Effort Multiplier Values

| fix_effort | Multiplier | Interpretation |
|---|---|---|
| "low" | 1 | Hours to days; clear fix path; no design review needed |
| "medium" | 2 | 1–2 weeks; requires design planning or backend work |
| "high" | 4 | 1+ month; complex architecture changes or multi-team effort |

**Why double for medium, quadruple for high?** The relationship between effort and cost is super-linear — high-effort fixes carry coordination overhead, risk of regressions, and opportunity cost. The 1:2:4 ratio reflects this non-linearity.

### 3.5 Priority Score Examples

| Step | Score | Users | Effort | Priority Score | Priority |
|---|---|---|---|---|---|
| email_verification | 87 | 732 | medium | 31,842 | P2 |
| sign_up_form | 52 | 1,700 | low | 88,400 | P1 |
| profile_setup | 45 | 156 | low | 7,020 | P4 |
| first_action | 35 | 134 | high | 1,173 | P5 |

**Insight:** Even though email_verification has a higher friction score (87 vs 52), sign_up_form (score=52, low effort, 1700 users) is actually the higher priority because more users are affected and the fix is cheap.

### 3.6 Properties

- **Float:** Not bounded or rounded — used purely for sorting
- **Relative:** Priority 1 vs Priority 2 is directionally correct but the absolute numbers have no external meaning
- **User-dependent:** Same friction score produces different priority on high-traffic vs low-traffic steps
- **Effort-dependent:** Two insights with identical impact scores rank differently based on fix_effort

---

## 4. Confidence Score

### 4.1 Definition

**Type:** Float  
**Range:** 0.50 to 0.98 (inclusive)  
**Unit:** Dimensionless  
**Direction:** Higher = more evidence = higher confidence in the score's accuracy

A data quality indicator reflecting how well-corroborated the friction score is by multiple independent signals.

### 4.2 What It Measures

It answers: "How sure are we that this friction score reflects a genuine user experience problem, as opposed to statistical noise in a small sample?" A step with 5 corroborating signals has much stronger evidence than a step with one borderline signal.

### 4.3 Computation

```
confidence = min(0.5 + len(signals) × 0.1, 0.98)
```

### 4.4 Confidence Scale

| Signals | Confidence | Assessment |
|---|---|---|
| 0 | 0.50 | Uncertain — no clear signal, not worth investigating |
| 1 | 0.60 | Weak — one indicator; review manually before acting |
| 2 | 0.70 | Moderate — two indicators; proceed with investigation |
| 3 | 0.80 | High — three corroborating signals; high confidence action |
| 4 | 0.90 | Very high — comprehensive evidence |
| 5+ | 0.98 | Maximum — overwhelming evidence (capped to avoid certainty bias) |

### 4.5 Use in LLM Prompt

Confidence is included in the `generate_insight()` user prompt so the LLM can calibrate its response:
- Confidence ≥ 0.80: LLM gives direct recommendations
- Confidence 0.60–0.79: LLM flags its analysis as tentative
- Confidence < 0.60: LLM suggests gathering more data first

**Why not display to end users?** Confidence is an internal quality metric. Showing it to CIOs or PMs adds complexity without decision-changing value. The LLM's language naturally expresses uncertainty from it.

---

## 5. Drop-Off Percentage

### 5.1 Definition

**Column name:** `drop_off_pct`  
**Type:** Float  
**Range:** 0.0 to 100.0  
**Unit:** Percentage of users who reached this step but did not reach the next  

### 5.2 What It Measures

The proportion of users who enter a step but fail to advance to the next step in the journey. A 40% drop-off means 40 users out of every 100 who land on this page do not proceed further.

### 5.3 Computation (SQL)

```sql
WITH funnel AS (
    SELECT step_id, COUNT(DISTINCT user_id) AS users_entered
    FROM events
    WHERE journey_id = 'onboarding' AND event_type = 'page_view'
      AND timestamp >= NOW() - INTERVAL '30 days'
    GROUP BY step_id
),
ordered AS (
    SELECT
        step_id,
        users_entered,
        LEAD(users_entered) OVER (
            ORDER BY ARRAY_POSITION(['landing_page','sign_up_form',...], step_id)
        ) AS next_step_users
    FROM funnel
)
SELECT
    step_id,
    users_entered AS users,
    CASE WHEN next_step_users IS NULL THEN 0.0
         ELSE ROUND((users_entered - next_step_users) / users_entered * 100.0, 2)
    END AS drop_off_pct
FROM ordered
```

**Notes on `drop_off_pct`:**
- Final step always has `drop_off_pct = 0.0` (LEAD returns NULL, treated as complete)
- `drop_off_pct = 0.0` for intermediate steps means ALL users who entered also advanced (not realistic but handles edge case)
- Uses `ARRAY_POSITION` to enforce journey order, not alphabetical sort

### 5.4 Relationship to abandon_rate_pct

`drop_off_pct` and `abandon_rate_pct` are NOT the same:

| Metric | What It Counts | Source |
|---|---|---|
| drop_off_pct | Users not advancing to next step (sequential funnel view) | Funnel query |
| abandon_rate_pct | Users who fired an `abandon` event (beforeunload) | Step metrics query |

- `drop_off_pct` is always ≤ `abandon_rate_pct + silent_exits`
- Users can leave a step without triggering `abandon` (e.g., closing laptop without closing tab)
- `drop_off_pct` is the funnel view; `abandon_rate_pct` is the event-driven view

---

## 6. Average Dwell Time (avg_dwell_ms)

### 6.1 Definition

**Column name:** `avg_dwell_ms`  
**Type:** Float → stored as Integer in FrictionScore  
**Range:** 0 to ∞  
**Unit:** Milliseconds  

### 6.2 What It Measures

The average time a user spends on a step before either advancing or abandoning. Measured from the `page_view` event's `duration_ms` field (set by tracker.js as time elapsed from `DOMContentLoaded` to either SPA navigation or `beforeunload`).

### 6.3 Computation (SQL)

```sql
AVG(CASE WHEN event_type IN ('page_view', 'step_complete') 
          THEN duration_ms 
          ELSE NULL  -- exclude other event types from average
END) AS avg_dwell_ms
```

### 6.4 Baseline and Signal Thresholds

| Value | Interpretation |
|---|---|
| 0–5,000ms (0–5s) | Likely bounced or visited incorrectly |
| 5,000–30,000ms (5–30s) | Low-friction step: navigating quickly |
| 15,000ms baseline | "Normal" — at baseline, no friction signal |
| 30,000–60,000ms (30s–1m) | Moderate engagement — reading content |
| 60,000ms (1m) | `extended_hesitation` signal triggered |
| 120,000ms (2m) | `severe_confusion` signal triggered |
| >300,000ms (5m+) | User is likely stuck, walked away, or left tab open |

### 6.5 Tracker.js Duration Measurement

```javascript
// page_view: duration set on SPA navigation away from step
var dwell = Date.now() - pageStart;   // milliseconds since DOMContentLoaded
ev.duration_ms = dwell;

// abandon: duration set in beforeunload handler
var dwell = Date.now() - pageStart;
ev.duration_ms = dwell;
```

**For non-SPA pages:** Only `abandon` events carry dwell time. `page_view` events have `duration_ms=0`.
**For SPA pages:** `step_complete` events carry dwell time for the departing step.

---

## 7. Error Rate (error_rate_pct)

### 7.1 Definition

**Column name:** `error_rate_pct`  
**Type:** Float  
**Range:** 0.0 to 100.0  
**Unit:** Percentage  

### 7.2 What It Measures

The percentage of user sessions on a step that included at least one `error` event. An `error` is:
- A JavaScript `window.onerror` event (unhandled JS exception)
- An `unhandledrejection` event (Promise rejection)
- A form validation failure (`input:invalid` event)

**Important:** This counts sessions with ≥ 1 error, not total error count. If a user gets 5 errors, they still contribute 1 to the numerator.

### 7.3 Computation (SQL)

```sql
ROUND(SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END)
          × 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS error_rate_pct
```

### 7.4 Baseline and Signal Threshold

| Value | Interpretation |
|---|---|
| 0–2% | Excellent — minimal error impact |
| 2–5% | Baseline range — acceptable |
| 5% | `error_rate_pct` baseline (normalisation base) |
| 5–15% | Elevated — investigate error types |
| 15% | `frequent_errors` signal triggered |
| 15–35% | High — backend or validation reliability issue |
| 35%+ | Severe — step has a systemic reliability problem |

### 7.5 Error Event Metadata

```json
{
    "error_code":    "TOKEN_EXPIRED",      // application error code
    "error_message": "Your session has...", // truncated to 200 chars
    "source_file":   "app.min.js",         // JS source file
    "line":          1                      // line number in source
}
```

Error codes from synthetic data: `["TIMEOUT", "VALIDATION_FAIL", "SERVER_500", "TOKEN_EXPIRED"]`

---

## 8. Abandon Rate (abandon_rate_pct)

### 8.1 Definition

**Column name:** `abandon_rate_pct`  
**Type:** Float  
**Range:** 0.0 to 100.0  
**Unit:** Percentage  

### 8.2 What It Measures

The percentage of user sessions that fired an `abandon` event on this step. An `abandon` event is:
- Fired by tracker.js `beforeunload` handler using `sendBeacon` or `fetch` with `keepalive: true`
- Indicates the user closed the tab, navigated away via browser button, or closed the browser

### 8.3 Computation (SQL)

```sql
ROUND(SUM(CASE WHEN event_type = 'abandon' THEN 1 ELSE 0 END)
          × 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS abandon_rate_pct
```

### 8.4 Baseline and Signal Thresholds

| Value | Interpretation |
|---|---|
| 0–10% | Low friction — most users proceed |
| 10% | Baseline — "normal" for journey steps |
| 10–30% | Moderate — worth monitoring |
| 30% | `high_drop_off` signal triggered |
| 30–50% | High — step is a significant bottleneck |
| 50% | `critical_drop_off` signal triggered |
| 50%+ | Severe — majority of users are leaving this step |

### 8.5 Measurement Limitations

- `sendBeacon` can be blocked by privacy browser extensions — reading `abandon_rate_pct = 0` could be false negative
- Mobile Safari delays `beforeunload` for background tab switching — some abandons may not register
- Private browsing mode may not send beacons

**Design response:** Friction score uses `abandon_rate_pct` with highest weight (0.35) but also uses `drop_off_pct` from the funnel query as cross-validation. If they differ significantly, the `analysis` text from `correlate_signals` should flag it.

---

## 9. Rage Click Rate (avg_rage_clicks)

### 9.1 Definition

**Column name:** `avg_rage_clicks`  
**Type:** Float  
**Range:** 0.0 to 1.0+ (ratio, not percentage)  
**Unit:** Ratio of users experiencing rage clicks per step  

### 9.2 What It Measures

The proportion of users who triggered a rage click event on this step. A rage click = 3+ clicks on the same DOM element within 500ms. It signals user frustration with an unresponsive or confusing UI element.

**Not:** total rage click events per user. The metric is sessions_with_rage_click / total_sessions.

### 9.3 Computation (SQL)

```sql
ROUND(SUM(CASE WHEN event_type = 'rage_click' THEN 1 ELSE 0 END)
          × 1.0 / NULLIF(COUNT(DISTINCT user_id), 0), 4) AS avg_rage_clicks
```

**Note:** This is `1.0` not `100.0` — `avg_rage_clicks` is a ratio (0.0–1.0+), NOT a percentage.

### 9.4 Baseline and Signal Threshold

| Value | Interpretation |
|---|---|
| 0.0–0.05 | Normal — some rage clicking on any interface |
| 0.05 | Baseline (5% of sessions) |
| 0.05–0.20 | Slightly elevated — review interaction design |
| 0.20–0.50 | High — specific element is causing frustration |
| 0.50 | `rage_clicks_detected` signal triggered |
| 0.50+ | Very high — element is prominently broken or confusing |

---

## 10. Retry Average (avg_retries)

### 10.1 Definition

**Column name:** `avg_retries`  
**Type:** Float  
**Range:** 0.0 to ∞  
**Unit:** Average retry count per user session  

### 10.2 What It Measures

The average number of times users retry an operation on a step. Retries are captured via the `retry_count` field in `error` event metadata — set by tracker.js based on how many times a form was resubmitted after a validation failure or server error.

### 10.3 Computation (SQL)

```sql
COALESCE(ROUND(AVG(CASE WHEN event_type = 'error'
    THEN CAST(json_extract_string(metadata, '$.retry_count') AS DOUBLE)
    ELSE NULL
END), 4), 0) AS avg_retries
```

**Notes:**
- `json_extract_string` + CAST to DOUBLE handles JSON string → numeric conversion
- `COALESCE(..., 0)` returns 0.0 if no error events exist (avoids NULL avg)
- Steps with no retry data return 0.0

### 10.4 Baseline and Signal Threshold

| Value | Interpretation |
|---|---|
| 0.0 | No retries — either no errors or errors not capturable |
| 0.1 | Baseline — 1 in 10 users retries once |
| 0.1–1.0 | Moderate retrying — some friction but finding their way |
| 1.0 | `repeated_retries` signal triggered — average of 1+ retry |
| 1.0–3.0 | High — users repeatedly failing; step has reliability issue |
| 3.0+ | Severe — users in retry loop; escalate |

---

## 11. Completion Rate (completion_rate_pct)

### 11.1 Definition

**Column name:** `completion_rate_pct`  
**Type:** Float  
**Range:** 0.0 to 100.0  
**Unit:** Percentage  

### 11.2 What It Measures

The percentage of users who fired a `step_complete` event on this step, indicating a successful SPA navigation to the next step. This is the inverse of `abandon_rate_pct` for SPA-tracked sites, but the two may not sum to 100% for multi-page apps where step_complete isn't fired.

### 11.3 Computation (SQL)

```sql
ROUND(SUM(CASE WHEN event_type = 'step_complete' THEN 1 ELSE 0 END)
          × 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS completion_rate_pct
```

### 11.4 Use in Scoring

`completion_rate_pct` is computed and stored in `step_metrics` but is **not used directly in the friction score formula**. It is available for:
- Information display in the step metrics summary
- LLM prompt context (via `event_summary["step_metrics"]`)
- Potential future correlation analysis

The friction score uses `abandon_rate_pct` (its complement) because abandon events are more reliably captured across both SPA and MPA architectures.

---

## 12. Signal Definitions

### 12.1 Complete Signal Reference

Each signal is a named categorical indicator. Signal names are immutable strings — tests hardcode them.

| Signal Name | Trigger Condition | Metric | Threshold | Business Meaning |
|---|---|---|---|---|
| `high_drop_off` | `abandon_rate_pct > 30` | abandon_rate_pct | 30.0 | Significant share of users leaving — step needs review |
| `critical_drop_off` | `abandon_rate_pct > 50` | abandon_rate_pct | 50.0 | Majority of users leaving — step may be fundamentally broken |
| `frequent_errors` | `error_rate_pct > 15` | error_rate_pct | 15.0 | Errors are common — likely backend or validation reliability issue |
| `extended_hesitation` | `avg_dwell_ms > 60,000` | avg_dwell_ms | 60,000ms | Users taking >1 minute — confused or lacking guidance |
| `severe_confusion` | `avg_dwell_ms > 120,000` | avg_dwell_ms | 120,000ms | Users taking >2 minutes — stuck or in silent error loop |
| `repeated_retries` | `avg_retries > 1.0` | avg_retries | 1.0 | Average user retries more than once — form/flow not intuitive |
| `rage_clicks_detected` | `avg_rage_clicks > 0.5` | avg_rage_clicks | 0.5 | Half of users rage-clicking — specific element is frustrating |

### 12.2 Signal Severities

| Signal | Severity | Typical Root Cause |
|---|---|---|
| critical_drop_off | Severe | System failure, missing content, wrong CTA |
| rage_clicks_detected | High | Broken interactive element, high latency |
| severe_confusion | High | Missing instructions, broken form flow, silent errors |
| frequent_errors | High | Backend unreliability, validation logic bugs |
| repeated_retries | Medium | Poor error messaging, complex validation |
| extended_hesitation | Medium | Poor affordance, verbose form, no progress indicator |
| high_drop_off | Low-Medium | Cognitive load, journey step out of order |

### 12.3 Signal-to-Category Mapping (LLM Guidance)

The insight LLM uses signals to determine the most likely category:

| Signal Combination | Likely Category |
|---|---|
| frequent_errors + repeated_retries | system or data |
| rage_clicks_detected + extended_hesitation | UX |
| severe_confusion (alone) | UX or process |
| critical_drop_off + frequent_errors | system |
| critical_drop_off (alone) | process or UX |
| repeated_retries (alone) | data or UX |

---

## 13. Insight Fields

### 13.1 Complete Insight Field Definitions

| Field | Type | Constraints | Definition |
|---|---|---|---|
| `insight_id` | str | UUID v4 | Unique identifier for this insight, generated with uuid4() |
| `step_id` | str | From journey_steps | Which journey step this insight analyzes |
| `title` | str | Max 8 words | Concise problem statement (LLM-generated) |
| `root_cause` | str | 2–3 sentences | LLM explanation of WHY friction exists |
| `category` | str | Enum | Problem category: UX / data / system / process / unknown |
| `evidence` | list[str] | Min 1 item | List of supporting data points from step metrics |
| `suggested_fix` | str | 1–2 sentences | Actionable recommendation (LLM-generated) |
| `fix_effort` | str | Enum | Engineering effort estimate: low / medium / high |
| `priority` | int | 1–5 | Sprint prioritisation (1 = highest, computed not LLM) |
| `priority_score` | float | ≥ 0 | Raw impact/effort ratio used to derive priority |
| `score` | int | 0–100 | Friction score that triggered this insight |

### 13.2 Category Definitions

| Category | Definition | Examples |
|---|---|---|
| UX | Interface design, usability, or user experience issue | Confusing form layout, unclear CTA, missing instructions, no progress indicator |
| data | Data quality, validation logic, or field requirements issue | Over-strict email validation, required fields not marked, default values wrong |
| system | Backend reliability, infrastructure, or timeout issue | API timeout, OTP token expiry too short, server 500 errors, missing error recovery |
| process | Business process or user task flow mismatch | Email verification before social login offered, profile required before seeing value |
| unknown | Insufficient signal or LLM unable to determine | Used only in fallback — not a useful category |

### 13.3 Fix Effort Definitions

| fix_effort | Definition | Typical Sprint Commitment |
|---|---|---|
| low | Simple configuration change, copy change, or CSS fix | < 1 day, single engineer |
| medium | Frontend changes, backend config, or product decision needed | 1–2 weeks, 1–2 engineers |
| high | Architecture change, multi-team coordination, or complex migration | 1+ month, cross-functional |

**LLM Prompt Guidance for fix_effort:**
- "low": changing a label, adjusting a timeout value, adding a resend button
- "medium": redesigning a form, adding backend retry logic, refactoring validation
- "high": migrating identity provider, redesigning the full onboarding flow, adding real-time messaging

---

## 14. Metric Relationship Map

```
INPUTS (from SQL on events table):
  ┌──────────────────────────────────────────────────────────┐
  │  Step Metrics (per step, per time window)                │
  │  ├── unique_users: int                                   │
  │  ├── completion_rate_pct: float (0–100)                  │
  │  ├── abandon_rate_pct: float (0–100) ──────────┐         │
  │  ├── error_rate_pct: float (0–100) ─────────────┤         │
  │  ├── avg_dwell_ms: float (0–∞) ────────────────┤         │
  │  ├── avg_retries: float (0–∞) ─────────────────┤ → friction score
  │  └── avg_rage_clicks: float (0–∞) ─────────────┘         │
  └──────────────────────────────────────────────────────────┘
                          │
                          ▼
FRICTION ENGINE MCP:
  ├── score:          int (0–100) ──────────────────┐
  ├── signals:        list[str] (0–7 items) ─────────┤ → LLM insight
  ├── confidence:     float (0.5–0.98) ───────────────┘
  └── is_critical:    bool ──────────────────────────── → trigger insight?

                          │ (if is_critical)
                          ▼
INSIGHT MCP:
  ├── title:          str
  ├── root_cause:     str
  ├── category:       str (UX|data|system|process|unknown)
  ├── evidence:       list[str]
  ├── suggested_fix:  str
  └── fix_effort:     str (low|medium|high)
  
  + score (from FrictionScore, passed through)
  + unique_users (from StepMetrics, passed through)
                          │
                          ▼
PRIORITY COMPUTATION:
  ├── priority_score: float = (score × unique_users) / effort_cost
  └── priority:       int (1–5) = threshold on priority_score

                          │
                          ▼
REPORT OUTPUT:
  ├── friction bar chart (step → score)
  ├── funnel chart (step → drop_off_pct)
  ├── insights table (step, issue, category, priority, effort, fix)
  └── narrative (executive summary)
```

---

## 15. Metric Limits and Boundaries

### 15.1 Hard Limits (Always Enforced in Code)

| Metric | Lower Bound | Upper Bound | Enforcement |
|---|---|---|---|
| score (friction) | 0 | 100 | `min(100, int(raw × 100))` |
| confidence | 0.50 | 0.98 | `min(0.5 + n×0.1, 0.98)` |
| priority | 1 | 5 | Threshold cascade in prioritise_fix() |
| abandon_rate_pct | 0.0 | 100.0 | SQL ROUND capped by COUNT logic |
| error_rate_pct | 0.0 | 100.0 | SQL ROUND capped by COUNT logic |
| avg_dwell_ms | 0 | ∞ | No upper cap (duration_ms has no cap client-side) |
| avg_retries | 0.0 | ∞ | No upper cap |
| avg_rage_clicks | 0.0 | ∞ | Theoretically >1.0 if multi-rage click per user |
| duration_ms (events) | 0 | ∞ | Non-negative enforced by Pydantic ge=0 |
| batch size (collector) | 1 | 100 | Pydantic EventBatch validator |

### 15.2 Soft Limits (Business Interpretation Guidelines)

| Metric | Extremely High Flag | Interpretation |
|---|---|---|
| avg_dwell_ms > 300,000 (5 min) | Consider data quality | User may have left tab open — not actual active dwell |
| avg_rage_clicks > 1.0 | Very unusual | Multiple rage click events per user — extremely frustrated |
| avg_retries > 5.0 | Very unusual | Retry loop — likely system is rejecting all submissions |
| abandon_rate_pct > 80.0 | Investigate data | Consider if step is actually presented to users correctly |
| unique_users < 30 | Low sample | Friction score accurate but confidence metrics may be noisy |

### 15.3 Sample Size Considerations

The friction score formula does not incorporate sample size directly (unlike statistical tests). Consider adding manual caveats:

| unique_users | Sample Quality |
|---|---|
| < 30 | Too small — score may not be reliable; do not act on it alone |
| 30–100 | Small — directionally useful; validate with qualitative data |
| 100–500 | Adequate — scores are actionable |
| 500+ | Large — high statistical confidence in metrics |

For the PoC (2,000 synthetic sessions), all 6 steps have > 500 users at the landing page, declining to ~100+ at completion. The analysis is statistically robust for demonstration purposes.
