> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# API Contracts
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** API Contract Reference

---

## Table of Contents

1. [Collector REST API](#1-collector-rest-api)
2. [MCP Server 1: Journey Data](#2-mcp-server-1-journey-data)
3. [MCP Server 2: Friction Engine](#3-mcp-server-2-friction-engine)
4. [MCP Server 3: Insight](#4-mcp-server-3-insight)
5. [MCP Server 4: Report](#5-mcp-server-4-report)
6. [LangGraph Public API](#6-langgraph-public-api)
7. [tracker.js Window API](#7-trackerjs-window-api)
8. [CLI Contract](#8-cli-contract)
9. [Dashboard Integration Contract](#9-dashboard-integration-contract)
10. [Data Schemas Reference](#10-data-schemas-reference)
11. [Error Response Contracts](#11-error-response-contracts)

---

## 1. Collector REST API

**Host:** `http://{COLLECTOR_HOST}:{COLLECTOR_PORT}` (default: `http://localhost:8000`)
**Framework:** FastAPI with uvicorn
**Authentication:** `X-CJI-Key` header or `api_key` in request body

### 1.1 GET /health

Health check for monitoring and dashboard status indicator.

**Request:**
```http
GET /health HTTP/1.1
Host: localhost:8000
```

**Response 200:**
```json
{
    "status": "ok",
    "mode": "realtime",
    "live_events_count": 1247,
    "uptime_seconds": 3600
}
```

**Notes:**
- `live_events_count` queries `SELECT COUNT(*) FROM live_events`
- No authentication required
- Used by dashboard to show "● Online / ✗ Offline" indicator

---

### 1.2 GET /tracker.js

Serves the tracker.js file for browser embedding.

**Request:**
```http
GET /tracker.js HTTP/1.1
Host: localhost:8000
```

**Response 200:**
```http
HTTP/1.1 200 OK
Content-Type: application/javascript
Cache-Control: public, max-age=3600

(function() { /* IIFE tracker code */ })();
```

**Notes:**
- No authentication required
- Cache-Control allows CDN caching in production
- `async` attribute on the `<script>` tag prevents blocking page render

---

### 1.3 POST /collect/batch

Receive a batch of browser events from tracker.js.

**Request:**
```http
POST /collect/batch HTTP/1.1
Host: localhost:8000
Content-Type: application/json
X-CJI-Key: cji_live_abc123...

{
    "api_key": "cji_live_abc123...",
    "events": [
        {
            "event_id":    "3f4e9a12b123456789abcdef01234567",
            "user_id":     "a1b2c3d4e5f6789012345678abcdef01",
            "session_id":  "deadbeef1234567890abcdef01234567",
            "journey_id":  "onboarding",
            "step_id":     "email_verification",
            "event_type":  "page_view",
            "timestamp":   "2026-03-15T14:30:00.123Z",
            "duration_ms": 0,
            "url":         "https://example.com/verify",
            "metadata":    {"referrer": "https://example.com/signup", "title": "Verify Email"}
        },
        {
            "event_id":    "feedcafe1234567890abcdef01234567",
            "user_id":     "a1b2c3d4e5f6789012345678abcdef01",
            "session_id":  "deadbeef1234567890abcdef01234567",
            "journey_id":  "onboarding",
            "step_id":     "email_verification",
            "event_type":  "error",
            "timestamp":   "2026-03-15T14:30:45.000Z",
            "duration_ms": 0,
            "url":         "https://example.com/verify",
            "metadata":    {"error_code": "TOKEN_EXPIRED", "retry_count": 2}
        }
    ]
}
```

**Response 200 OK (all accepted):**
```json
{
    "accepted": 2,
    "rejected": 0,
    "errors": [],
    "message": "OK"
}
```

**Response 207 Multi-Status (partial success):**
```json
{
    "accepted": 1,
    "rejected": 1,
    "errors": ["feedcafe...: UNIQUE constraint violation — event_id already exists"],
    "message": "Partial success"
}
```

**Response 401 Unauthorized:**
```json
{
    "detail": "Invalid or inactive API key"
}
```

**Response 422 Unprocessable Entity (schema error):**
```json
{
    "detail": [
        {
            "loc": ["body", "events", 0, "event_type"],
            "msg": "event_type 'INVALID' not allowed. Must be one of {...}",
            "type": "value_error"
        }
    ]
}
```

**Behaviour notes:**
- `api_key` accepted from either JSON body OR `X-CJI-Key` header (body takes precedence)
- Events with individual write errors are rejected (others still accepted)
- Duplicate `event_id` values are silently ignored (`INSERT OR IGNORE`)
- Response returned immediately; writes occur in FastAPI `BackgroundTasks`

---

### 1.4 GET /live/stats

Per-step event counts for dashboard live feed.

**Request:**
```http
GET /live/stats HTTP/1.1
Host: localhost:8000
X-CJI-Key: cji_dev_localtest
```

**Response 200:**
```json
{
    "steps": {
        "landing_page":       342,
        "sign_up_form":       287,
        "email_verification": 201,
        "profile_setup":      156,
        "first_action":       134,
        "completion":         112
    },
    "window_mins": 60,
    "total_events": 1232,
    "timestamp": "2026-03-15T14:31:00Z"
}
```

---

### 1.5 GET /live/feed (Server-Sent Events)

Real-time event stream for dashboard live feed panel.

**Request:**
```http
GET /live/feed HTTP/1.1
Host: localhost:8000
Accept: text/event-stream
```

**Response (SSE stream):**
```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

data: {"event_type": "page_view", "step_id": "landing_page", "received_at": "2026-03-15T14:31:05Z"}

data: {"event_type": "rage_click", "step_id": "email_verification", "received_at": "2026-03-15T14:31:07Z"}

data: {"event_type": "abandon", "step_id": "email_verification", "received_at": "2026-03-15T14:31:10Z"}
```

**Notes:**
- Events are emitted as they arrive from tracker.js
- Dashboard shows last 15 events in sidebar
- Connection terminates on client disconnect

---

### 1.6 POST /admin/api-keys

Create a new client API key. Admin-only endpoint.

**Request:**
```http
POST /admin/api-keys HTTP/1.1
Host: localhost:8000
X-CJI-Admin-Key: {CJI_ADMIN_KEY from env}
Content-Type: application/json

{
    "journey_id":  "onboarding",
    "client_name": "ACME Corp - Production"
}
```

**Response 201 Created:**
```json
{
    "api_key":     "cji_live_<redacted>",
    "journey_id":  "onboarding",
    "client_name": "ACME Corp - Production",
    "created_at":  "2026-03-15T14:31:00Z",
    "active":      true
}
```

**Response 403 Forbidden:**
```json
{
    "detail": "Invalid admin key"
}
```

---

## 2. MCP Server 1: Journey Data

**Server name:** `cji-journey-data`
**File:** `mcp_servers/journey_data_server.py`
**Transport:** stdio JSON-RPC
**Mode awareness:** YES — reads Parquet (demo) or live_events (realtime)

---

### get_system_info()

Returns mode, source, and connection status.

**Input:** (none)

**Output:**
```json
{
    "mode":         "demo",
    "data_source":  "parquet",
    "duckdb_path":  "/abs/path/to/data/cji.duckdb",
    "journey_id":   "onboarding",
    "journey_steps": ["landing_page", "sign_up_form", "email_verification",
                      "profile_setup", "first_action", "completion"],
    "llm_model":    "claude-sonnet-4-6",
    "status":       "ok"
}
```

**Edge cases:**
- Parquet file not found (demo mode): `{"status": "error", "error": "events.parquet not found — run --generate-data"}`
- live_events table empty (realtime mode): `{"status": "ok", "live_events_count": 0}` (not an error — valid state)

---

### get_funnel_steps()

Returns ordered list of journey step IDs.

**Input:** (none)

**Output:**
```json
{
    "journey_id": "onboarding",
    "steps": [
        "landing_page",
        "sign_up_form",
        "email_verification",
        "profile_setup",
        "first_action",
        "completion"
    ],
    "step_count": 6
}
```

---

### get_step_metrics()

Returns aggregated metrics per step.

**Input:**
```json
{
    "days_back":    30,    // demo mode: integer ≥ 1
    "minutes_back": 0     // realtime mode: integer ≥ 1 (0 = use REALTIME_WINDOW_MINUTES default)
}
```

**Output:**
```json
{
    "journey_id": "onboarding",
    "window_days": 30,
    "step_metrics": [
        {
            "step_id":            "email_verification",
            "unique_users":        732,
            "completion_rate_pct": 58.2,
            "abandon_rate_pct":    41.8,
            "error_rate_pct":      34.7,
            "avg_dwell_ms":        184000,
            "avg_rage_clicks":     0.62,
            "avg_retries":         1.8
        },
        {
            "step_id":            "landing_page",
            "unique_users":        2000,
            "completion_rate_pct": 85.0,
            "abandon_rate_pct":    15.0,
            "error_rate_pct":      2.1,
            "avg_dwell_ms":        12000,
            "avg_rage_clicks":     0.02,
            "avg_retries":         0.01
        }
    ],
    "total_steps": 6
}
```

**Edge cases:**
- Step with zero users: step row returned with zeros in all metric fields
- Division by zero: protected by `NULLIF` in SQL, returns 0.0
- Empty table (realtime, no events yet): returns empty `step_metrics: []`

---

### get_funnel_dropoff()

Returns sequential funnel drop-off percentages.

**Input:**
```json
{
    "days_back":    30,
    "minutes_back": 0
}
```

**Output:**
```json
{
    "journey_id": "onboarding",
    "funnel": [
        {"step_id": "landing_page",       "users": 2000, "drop_off_pct": 15.0},
        {"step_id": "sign_up_form",       "users": 1700, "drop_off_pct": 25.0},
        {"step_id": "email_verification", "users": 1275, "drop_off_pct": 42.5},
        {"step_id": "profile_setup",      "users":  733, "drop_off_pct": 20.0},
        {"step_id": "first_action",       "users":  586, "drop_off_pct": 12.0},
        {"step_id": "completion",         "users":  516, "drop_off_pct": 0.0}
    ],
    "overall_completion_pct": 25.8
}
```

---

### query_events()

Returns a sample of raw events with optional filters.

**Input:**
```json
{
    "step_id":    "email_verification",    // optional: filter by step
    "event_type": "error",                 // optional: filter by type
    "limit":      50                       // optional: max rows (default 100)
}
```

**Output:**
```json
{
    "events": [
        {
            "event_id":    "3f4e9a12b123...",
            "user_id":     "a1b2c3d4...",
            "journey_id":  "onboarding",
            "step_id":     "email_verification",
            "event_type":  "error",
            "timestamp":   "2026-03-15T14:30:45Z",
            "duration_ms": 0,
            "metadata":    "{\"error_code\": \"TOKEN_EXPIRED\", \"retry_count\": 2}"
        }
    ],
    "count": 50,
    "step_id_filter":  "email_verification",
    "event_type_filter": "error"
}
```

---

### get_live_snapshot()

**Realtime mode only.** Returns rolling event counts for the last N minutes.

**Input:**
```json
{
    "minutes": 15    // rolling window in minutes
}
```

**Output (realtime mode):**
```json
{
    "window_mins": 15,
    "steps": [
        {"step_id": "email_verification", "event_count": 47, "unique_users": 31},
        {"step_id": "sign_up_form",       "event_count": 38, "unique_users": 25}
    ],
    "total_events": 212,
    "snapshot_at": "2026-03-15T14:31:00Z"
}
```

**Output (demo mode — error response, not exception):**
```json
{
    "error":   "get_live_snapshot is only available in realtime mode",
    "mode":    "demo",
    "message": "Switch to CJI_MODE=realtime to use this tool"
}
```

---

## 3. MCP Server 2: Friction Engine

**Server name:** `cji-friction-engine`
**File:** `mcp_servers/friction_engine_server.py`
**Transport:** stdio JSON-RPC
**Mode awareness:** NO — works identically in both modes

---

### score_friction()

Computes friction score for a single journey step.

**Input:**
```json
{
    "step_metrics": {
        "step_id":            "email_verification",
        "unique_users":        732,
        "completion_rate_pct": 58.2,
        "abandon_rate_pct":    41.8,
        "error_rate_pct":      34.7,
        "avg_dwell_ms":        184000,
        "avg_rage_clicks":     0.62,
        "avg_retries":         1.8
    }
}
```

**Output:**
```json
{
    "step_id":        "email_verification",
    "score":          87,
    "drop_off_rate":  0.418,
    "avg_dwell_ms":   184000,
    "retry_count":    1.8,
    "rage_click_rate": 0.62,
    "signals":        ["critical_drop_off", "frequent_errors", "severe_confusion",
                       "repeated_retries", "rage_clicks_detected"],
    "confidence":     0.98,
    "is_critical":    true
}
```

**Algorithm (exact):**
```
normalise(v, b) = min(v / max(b, 0.001), 3.0) / 3.0

raw = normalise(abandon_rate_pct, 10.0) × 0.35
    + normalise(error_rate_pct, 5.0)    × 0.25
    + normalise(avg_dwell_ms, 15000)    × 0.15
    + normalise(avg_retries, 0.1)       × 0.15
    + normalise(avg_rage_clicks, 0.05)  × 0.10

score = min(100, int(raw × 100))

Signals:
  abandon > 30  → "high_drop_off"
  abandon > 50  → "critical_drop_off"
  error > 15    → "frequent_errors"
  dwell > 60000 → "extended_hesitation"
  dwell > 120000→ "severe_confusion"
  retries > 1.0 → "repeated_retries"
  rage > 0.5    → "rage_clicks_detected"

confidence = min(0.5 + len(signals) × 0.1, 0.98)
is_critical = score >= FRICTION_SCORE_THRESHOLD (default: 60)
```

**Edge cases:**
- All zeros input: score=0, signals=[], confidence=0.5, is_critical=False
- Maximum values: score=100 (capped by min(100, ...))
- Missing optional fields: treated as 0.0

---

### score_all_steps()

Scores multiple steps and returns sorted results.

**Input:**
```json
{
    "all_step_metrics": [
        {"step_id": "email_verification", "abandon_rate_pct": 41.8, ...},
        {"step_id": "landing_page",       "abandon_rate_pct": 15.0, ...}
    ]
}
```

**Output:**
```json
{
    "scores": [
        {
            "step_id": "email_verification", "score": 87, "is_critical": true,
            "signals": ["critical_drop_off", "frequent_errors", ...], "confidence": 0.98
        },
        {
            "step_id": "sign_up_form", "score": 52, "is_critical": false,
            "signals": ["high_drop_off"], "confidence": 0.60
        }
    ],
    "critical_steps": ["email_verification"],
    "total_steps":    6,
    "avg_score":      38.2,
    "threshold":      60
}
```

**Ordering:** Results are sorted descending by `score`. Ties broken by step_id alphabetically.

---

### detect_dropoffs()

Identifies steps with drop-off above a threshold.

**Input:**
```json
{
    "funnel_data": [
        {"step_id": "email_verification", "drop_off_pct": 42.5, "users": 1275},
        {"step_id": "sign_up_form",       "drop_off_pct": 25.0, "users": 1700}
    ],
    "threshold_pct": 25.0
}
```

**Output:**
```json
{
    "critical_dropoffs": [
        {"step_id": "email_verification", "drop_off_pct": 42.5, "users_lost": 541},
        {"step_id": "sign_up_form",       "drop_off_pct": 25.0, "users_lost": 425}
    ],
    "count":         2,
    "threshold_pct": 25.0
}
```

**Ordering:** Results sorted descending by `drop_off_pct`.

---

### correlate_signals()

Identifies systemic patterns across all steps.

**Input:**
```json
{
    "scores": [
        {"step_id": "sign_up_form",       "signals": ["high_drop_off"]},
        {"step_id": "email_verification", "signals": ["critical_drop_off", "high_drop_off",
                                                       "rage_clicks_detected"]},
        {"step_id": "profile_setup",      "signals": ["high_drop_off", "extended_hesitation"]}
    ]
}
```

**Output:**
```json
{
    "signal_frequency": {
        "high_drop_off":        3,
        "critical_drop_off":    1,
        "rage_clicks_detected": 1,
        "extended_hesitation":  1
    },
    "co_occurring_patterns": [
        {"signals": ["high_drop_off", "extended_hesitation"], "count": 1}
    ],
    "systemic_signals": ["high_drop_off"],
    "analysis": "high_drop_off appears in 3/3 steps — this is a systemic onboarding issue, not isolated to one step"
}
```

**systemic_signals rule:** A signal is systemic if it appears in ≥ 50% of steps (default) or 2+ steps (for small journey with ≤ 4 steps).

---

## 4. MCP Server 3: Insight

**Server name:** `cji-insight`
**File:** `mcp_servers/insight_server.py`
**Transport:** stdio JSON-RPC
**Mode awareness:** NO
**External dependencies:** LiteLLM (LLM calls), ChromaDB (vector storage)

---

### generate_insight()

Generates LLM root cause analysis for a critical friction score.

**Input:**
```json
{
    "friction_score": {
        "step_id":        "email_verification",
        "score":          87,
        "signals":        ["critical_drop_off", "frequent_errors", "severe_confusion"],
        "confidence":     0.98,
        "is_critical":    true,
        "abandon_rate_pct": 41.8,
        "error_rate_pct":   34.7,
        "avg_dwell_ms":     184000
    }
}
```

**LLM System Prompt:**
```
You are CJI, a customer journey analytics AI. Analyse the provided step metrics 
and return a JSON insight. Respond ONLY with valid JSON, no markdown, no explanation.

Required JSON schema:
{
  "title":        "Max 8 words describing the core issue",
  "root_cause":   "2-3 sentences explaining WHY this friction exists",
  "category":     "UX" | "data" | "system" | "process" | "unknown",
  "evidence":     ["list", "of", "supporting", "data", "points"],
  "suggested_fix": "1-2 sentences of actionable recommendation",
  "fix_effort":   "low" | "medium" | "high"
}

Categories:
  UX      → interface design, usability, form complexity
  data    → data quality, missing fields, validation logic
  system  → backend errors, timeouts, infrastructure
  process → business process, user task mismatch
  unknown → insufficient data to determine
```

**LLM User Prompt:**
```
Step: email_verification
Signals: critical_drop_off, frequent_errors, severe_confusion
Abandon rate: 41.8%
Error rate: 34.7%
Average dwell time: 184000ms (3.07 minutes)
Rage clicks: 0.62 per user
Retries: 1.8 per user
Confidence: 0.98
```

**Output (success):**
```json
{
    "insight_id":    "7d3f1a92-c4b8-4e0f-a123-...",
    "step_id":       "email_verification",
    "title":         "Expiring OTP tokens causing verification failures",
    "root_cause":    "Users are failing email verification because OTP tokens expire within 2 minutes, which is shorter than the time most mobile users take to switch apps and check email. The high retry rate (1.8) and dwell time (3+ minutes) confirm users are repeatedly requesting new codes rather than completing verification.",
    "category":      "UX",
    "evidence":      [
        "41.8% abandon rate — 2nd highest step",
        "34.7% error rate — predominantly TOKEN_EXPIRED",
        "3+ minute average dwell (6x longer than landing page)",
        "1.8 average retries per user",
        "0.62 rage clicks per user"
    ],
    "suggested_fix": "Extend OTP validity to 15 minutes, add a prominent resend button above the fold, and display a countdown timer showing time remaining.",
    "fix_effort":    "medium"
}
```

**Output (LLM failure — JSON fallback):**
```json
{
    "insight_id":    "7d3f1a92-...",
    "step_id":       "email_verification",
    "title":         "Friction at email_verification",
    "root_cause":    "[raw LLM output truncated to 300 chars, or 'LLM analysis unavailable.']",
    "category":      "unknown",
    "evidence":      ["critical_drop_off", "frequent_errors", "severe_confusion"],
    "suggested_fix": "Manual investigation required.",
    "fix_effort":    "medium"
}
```

---

### prioritise_fix()

Computes priority ranking for an insight.

**Input:**
```json
{
    "insight": {
        "step_id":   "email_verification",
        "score":     87,
        "fix_effort": "medium",
        "title":     "Expiring OTP tokens..."
    },
    "unique_users": 732
}
```

**Output:**
```json
{
    "step_id":       "email_verification",
    "score":         87,
    "fix_effort":    "medium",
    "title":         "Expiring OTP tokens...",
    "priority":      1,
    "priority_score": 31929.0
}
```

**Algorithm:**
```
effort_map = {"low": 1, "medium": 2, "high": 4}
effort = effort_map[fix_effort]         # 2 for medium
impact = score × unique_users           # 87 × 732 = 63,684
priority_score = impact / effort        # 63,684 / 2 = 31,842

Priority thresholds:
  priority_score > 40,000 → P1
  priority_score > 20,000 → P2
  priority_score > 8,000  → P3
  priority_score > 2,000  → P4
  else                    → P5
```

---

### save_insight()

Persists insight to ChromaDB for semantic search.

**Input:**
```json
{
    "insight": {
        "insight_id":   "7d3f1a92-...",
        "step_id":      "email_verification",
        "title":        "Expiring OTP tokens...",
        "root_cause":   "Users are failing...",
        "category":     "UX",
        "evidence":     ["41.8% abandon rate", ...],
        "suggested_fix": "Extend OTP validity...",
        "fix_effort":   "medium",
        "priority":     1,
        "score":        87
    }
}
```

**Output:**
```json
{
    "saved":      true,
    "insight_id": "7d3f1a92-...",
    "step_id":    "email_verification",
    "index":      3
}
```

**Document stored in ChromaDB:**
```
"Expiring OTP tokens causing verification failures. Users are failing email 
verification because OTP tokens expire within 2 minutes... Extend OTP validity 
to 15 minutes, add a prominent resend button above the fold..."
```

**Metadata stored (all strings):**
```json
{
    "step_id":    "email_verification",
    "category":   "UX",
    "priority":   "1",
    "score":      "87",
    "fix_effort": "medium"
}
```

**Edge cases:**
- Duplicate insight_id: `collection.add()` raises ChromaDB error → returns `{"saved": false, "error": "..."}`
- Non-string metadata values → caught, wrapped in str() before storage

---

### search_insights()

Semantic search across stored insights.

**Input:**
```json
{
    "query":     "email verification OTP token errors",
    "n_results": 3
}
```

**Output:**
```json
{
    "results": [
        {
            "document": "Expiring OTP tokens causing verification failures. ...",
            "metadata": {"step_id": "email_verification", "category": "UX", ...},
            "distance": 0.12
        }
    ],
    "query":     "email verification OTP token errors",
    "count":     1
}
```

**Edge cases:**
- Empty collection: `{"results": [], "query": "...", "error": "No insights stored yet"}`
- n_results > collection size: `n = min(n_results, collection.count())` (automatic guard)

---

### rank_all_fixes()

Ranks all insights and generates an executive action plan.

**Input:**
```json
{
    "insights": [
        {"step_id": "email_verification", "priority": 1, "priority_score": 31842, ...},
        {"step_id": "sign_up_form",       "priority": 3, "priority_score": 8500,  ...}
    ]
}
```

**Output:**
```json
{
    "ranked_insights": [
        {"rank": 1, "step_id": "email_verification", "priority": 1, ...},
        {"rank": 2, "step_id": "sign_up_form",        "priority": 3, ...}
    ],
    "action_plan": "Sprint 1 (High Impact): Extend OTP validity to 15 minutes on email_verification — this single change could recover 41.8% of users currently abandoning. Sprint 2: Simplify the sign_up_form validation to reduce error rate from 18% to target <5%."
}
```

---

## 5. MCP Server 4: Report

**Server name:** `cji-report`
**File:** `mcp_servers/report_server.py`
**Transport:** stdio JSON-RPC
**Mode awareness:** NO (mode label passed as parameter)
**External dependencies:** LiteLLM (narrative), file system (HTML write)

---

### generate_narrative()

Generates a 3-paragraph CIO executive summary using LLM.

**Input:**
```json
{
    "insights":       [{"step_id": "email_verification", "title": "...", "category": "UX", ...}],
    "journey_name":   "onboarding",
    "avg_score":      38.2,
    "critical_count": 1,
    "mode":           "demo"
}
```

**LLM System Prompt:**
```
You are a senior management consultant writing a 3-paragraph executive summary 
for a CIO. Use business language only. Do not use technical terms like 'score', 
'DuckDB', 'MCP', or 'API'. Focus on user impact, business cost, and strategic fix priority.

Required output: exactly 3 paragraphs:
1. Business impact — how friction affects completion, revenue, user trust
2. Root causes — what types of problems exist (UX/process/system/data), without jargon
3. Recommendations — top 3 prioritised actions with expected outcomes
```

**Output:**
```json
{
    "narrative":     "The onboarding journey is experiencing significant friction that...\n\nInvestigation reveals three distinct categories of underlying issues...\n\nWe recommend the following prioritised actions...",
    "generated_at":  "2026-03-15T14:35:00Z"
}
```

**Fallback (LLM unavailable):**
```json
{
    "narrative": "This analysis of the onboarding journey identified 1 critical friction point(s) with an average friction score of 38.2/100. The most impacted step is email_verification. We recommend immediate investigation of the top-priority findings detailed in the table below.",
    "generated_at": "2026-03-15T14:35:00Z"
}
```

---

### export_report()

Generates and saves the self-contained HTML report file.

**Input:**
```json
{
    "journey_name":   "onboarding",
    "narrative":      "The onboarding journey is experiencing...",
    "friction_scores": [
        {"step_id": "email_verification", "score": 87, "is_critical": true, ...}
    ],
    "insights": [
        {"step_id": "email_verification", "priority": 1, "category": "UX", ...}
    ],
    "funnel_data": [
        {"step_id": "landing_page", "users": 2000, "drop_off_pct": 15.0}
    ],
    "mode": "demo"
}
```

**Output:**
```json
{
    "report_path":  "/abs/path/to/reports/cji_report_onboarding_20260315_143500.html",
    "file_size_kb": 94.7
}
```

**Error (cannot write file):**
```json
{
    "report_path":  null,
    "error":        "Permission denied: /path/to/reports/",
    "file_size_kb": 0
}
```

---

## 6. LangGraph Public API

**Usage pattern:** `from graph import get_graph`

### 6.1 get_graph()

Returns the compiled LangGraph graph singleton.

```python
graph = get_graph()
# Returns: cached CompiledStateGraph[CJIState]
```

---

### 6.2 graph.stream() — Start Analysis

Streams state events through the graph.

```python
config = {"configurable": {"thread_id": str(uuid4())}}
initial_state = {
    "mode":                  "demo",
    "journey_name":          "onboarding",
    "journey_steps":         ["landing_page", ...],
    "analysis_window_days":  30,
    "analysis_window_mins":  60,
    "collector_url":         "http://localhost:8000",
    "iteration":             0,
    "next_worker":           "",
    "human_approved":        False,   # or True for --auto-approve
    "messages":              [],
    "raw_events":            [],
    "event_summary":         {},
    "live_event_count":      0,
    "friction_scores":       [],
    "critical_steps":        [],
    "insights":              [],
    "prioritized_fixes":     [],
    "report_path":           "",
    "narrative":             "",
    "last_run_at":           datetime.now(UTC).isoformat(),
    "worker_statuses":       [],
    "errors":                [],
}

for event in graph.stream(initial_state, config=config, stream_mode="values"):
    state: dict = event   # full CJIState after each node
    # event["report_path"] non-empty → analysis complete (or paused)
```

---

### 6.3 graph.get_state() — Check Pause Status

```python
snapshot = graph.get_state(config)
state:      dict  = snapshot.values  # full CJIState
next_nodes: tuple = snapshot.next    # ("report_worker",) if paused, () if END
is_paused = len(next_nodes) > 0 and next_nodes[0] == "report_worker"
```

---

### 6.4 graph.update_state() — Approve and Resume

```python
# MUST include as_node="supervisor" — required for correct checkpoint behaviour
graph.update_state(
    config,
    {"human_approved": True},
    as_node="supervisor"
)

# Resume from checkpoint:
for event in graph.stream(None, config=config, stream_mode="values"):
    state: dict = event
```

---

### 6.5 graph.stream(None) — Resume After Crash

```python
# Same thread_id as interrupted run:
config = {"configurable": {"thread_id": existing_thread_id}}
for event in graph.stream(None, config=config, stream_mode="values"):
    state: dict = event
# graph.stream(None) reads from last checkpoint
```

---

## 7. tracker.js Window API

### 7.1 Configuration Object

Must be set **before** the tracker script tag:

```html
<script>
window.CJI_CONFIG = {
    apiKey:    "cji_live_<redacted>",
    journeyId: "onboarding",
    endpoint:  "http://localhost:8000",
    stepMap:   {
        "/":              "landing_page",
        "/signup":        "sign_up_form",
        "/verify":        "email_verification",
        "/profile":       "profile_setup",
        "/get-started":   "first_action",
        "/welcome":       "completion"
    }
};
</script>
<script src="http://localhost:8000/tracker.js" async></script>
```

**Config field rules:**
- `apiKey`: Required. Must match an active row in api_keys table.
- `journeyId`: Required. Used for filtering in analysis queries.
- `endpoint`: Required. URL of the collector API (no trailing slash).
- `stepMap`: Required. Maps URL pathnames to step_ids. Partial matches accepted (prefix match).

**Default if missing:**
- `stepMap` not matching current URL: step_id = "unknown_step"
- Missing `apiKey`: tracker.js logs warning and falls back to "cji_dev_localtest" (dev only)

---

### 7.2 Manual Event Firing API

```javascript
// Available after tracker.js loads:
window.CJITracker.track("identify", {
    "account_type": "trial",   // NO PII — anonymised traits only
    "signup_method": "google"
});

window.CJITracker.track("form_submit", {
    "form_id": "profile-form"
});
```

**Rules:**
- First argument: event_type (must be in ALLOWED_EVENT_TYPES)
- Second argument: metadata object (optional)
- API is a no-op if tracker failed to initialise

---

### 7.3 SPA Integration (React Hook)

```javascript
// useCJITracker.js (generated by snippet_generator.py)
import { useEffect } from 'react';
import { useRouter } from 'next/router';

export function useCJITracker() {
    const router = useRouter();

    useEffect(() => {
        if (typeof window === 'undefined' || !window.CJITracker) return;

        const handleRouteChange = () => {
            // tracker.js handles pushState internally via history.pushState override
            // This hook is for Next.js which bypasses native pushState in some configurations
        };

        router.events.on('routeChangeComplete', handleRouteChange);
        return () => router.events.off('routeChangeComplete', handleRouteChange);
    }, [router]);
}
```

---

## 8. CLI Contract

### 8.1 Complete Flag Reference

```bash
python main.py \
    --mode        demo|realtime  \   # Mode selection (default: from CJI_MODE env)
    --generate-data               \   # Demo: generate synthetic events.parquet
    --generate-snippet            \   # Realtime: generate embed code + API key
    --run                         \   # Start analysis pipeline
    --approve                     \   # Approve insights and generate report
    --thread-id   <UUID>          \   # Thread to approve/resume (printed on --run)
    --auto-approve                \   # Skip human gate (sets human_approved=True at init)
    --days        N               \   # Demo analysis window in days (default: 30)
    --window-mins N               \   # Realtime analysis window in minutes (default: 60)
    --journey     NAME            \   # Journey to analyse (default: "onboarding")
    --host        URL                 # Collector host for snippet generation
```

### 8.2 Exit Codes

| Exit Code | Meaning |
|---|---|
| 0 | Success (analysis complete, report generated, --approve succeeded) |
| 1 | Configuration error (missing API key, missing data file) |
| 2 | Analysis error (all workers failed, no insights produced) |
| 3 | Interrupted by user (Ctrl+C) — state checkpointed |

### 8.3 Required Console Output

| Stage | Required Output |
|---|---|
| --generate-data | `Generated {N} events → data/events.parquet` |
| --run start | `Thread ID: {UUID} — save this for --approve` |
| data_worker complete | `✓ data_worker: Fetched metrics for {N} steps` |
| friction_worker complete | `✓ friction_worker: {N} critical / {M} steps, avg={X}` |
| insight_worker complete | `✓ insight_worker: {N} insights generated` |
| pause (no auto-approve) | `⏸ Waiting for approval. Run: python main.py --approve --thread-id {UUID}` |
| report complete | `✓ Report generated: {path}` |

---

## 9. Dashboard Integration Contract

### 9.1 Session State Keys

The dashboard stores all run state in `st.session_state`:

```python
st.session_state.mode         str    # "demo" | "realtime"
st.session_state.thread_id    str    # UUID of current analysis run
st.session_state.state_snap   dict   # Last CJIState from graph.stream()
st.session_state.graph        CompiledStateGraph  # Singleton graph instance
```

**Mode toggle must clear:**
```python
st.session_state.thread_id  = None
st.session_state.state_snap = {}
st.rerun()  # Forces script re-execution from top with new CJI_MODE env var
```

### 9.2 State Key Access Pattern

After analysis runs, dashboard reads state via `st.session_state.state_snap`:

```python
state = st.session_state.state_snap

# Metric cards:
steps_count    = len(state.get("friction_scores", []))
critical_count = len(state.get("critical_steps", []))
avg_score      = state.get("event_summary", {}).get("avg_friction_score", 0)
insights_count = len(state.get("insights", []))

# Charts:
friction_data = [(s["step_id"], s["score"]) for s in state.get("friction_scores", [])]
funnel_data   = state.get("event_summary", {}).get("funnel", [])

# Approval gate:
is_paused    = bool(state.get("insights")) and not state.get("report_path")
report_ready = bool(state.get("report_path"))
```

---

## 10. Data Schemas Reference

### 10.1 StepMetrics (input to Friction MCP)

```python
class StepMetrics(TypedDict):
    step_id:            str    # journey step identifier
    unique_users:       int    # distinct users in window
    completion_rate_pct: float # 0.0–100.0
    abandon_rate_pct:   float  # 0.0–100.0
    error_rate_pct:     float  # 0.0–100.0
    avg_dwell_ms:       int    # average time-on-step in ms
    avg_rage_clicks:    float  # ratio of users with rage_click
    avg_retries:        float  # average retries per user
```

### 10.2 FrictionScore (output from Friction MCP)

```python
class FrictionScore(TypedDict):
    step_id:        str         # journey step identifier
    score:          int         # 0–100 friction score
    drop_off_rate:  float       # 0.0–1.0
    avg_dwell_ms:   int
    retry_count:    float
    rage_click_rate: float
    signals:        list[str]   # e.g. ["high_drop_off", "severe_confusion"]
    confidence:     float       # 0.0–0.98
    is_critical:    bool        # True if score >= FRICTION_SCORE_THRESHOLD
```

### 10.3 Insight (output from Insight MCP)

```python
class Insight(TypedDict):
    insight_id:    str    # UUID string
    step_id:       str
    title:         str    # max 8 words
    root_cause:    str    # 2-3 sentences
    category:      str    # "UX"|"data"|"system"|"process"|"unknown"
    evidence:      list[str]
    suggested_fix: str    # 1-2 sentences
    fix_effort:    str    # "low"|"medium"|"high"
    priority:      int    # 1–5
    priority_score: float
    score:         int    # friction score that triggered this insight
```

### 10.4 WorkerStatus

```python
class WorkerStatus(TypedDict):
    worker:  str    # worker name: "data_worker" | "friction_worker" | ...
    status:  str    # "success" | "error"
    message: str    # human-readable completion summary
```

---

## 11. Error Response Contracts

### 11.1 HTTP Error Responses (Collector API)

| Code | Trigger | Response Body |
|---|---|---|
| 401 | Invalid or inactive API key | `{"detail": "Invalid or inactive API key"}` |
| 422 | Pydantic validation failure | Standard FastAPI validation error body |
| 500 | Unhandled server error | `{"detail": "Internal server error"}` |

**Note:** Individual event validation failures within a valid batch do not return 422 — they increment `rejected` count and return 200/207.

### 11.2 MCP Tool Error Contract

Workers must never re-raise MCP tool errors. The `call_tool()` helper pattern:

```python
async def call_tool(session, tool_name, arguments):
    try:
        result = await session.call_tool(tool_name, arguments=arguments)
        if result.content and result.content:
            text = result.content[0].text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
        return {}
    except Exception as e:
        # Re-raise as RuntimeError so worker outer try/except catches it
        raise RuntimeError(f"MCP tool '{tool_name}' failed: {type(e).__name__}: {e}") from e
```

Workers' outer try/except:
```python
async def any_worker(state: CJIState) -> dict:
    try:
        # ... tool calls ...
        return {"output_key": result, "next_worker": "supervisor", ...}
    except Exception as e:
        return {
            "errors":      state.get("errors", []) + [f"{worker_name}: {type(e).__name__}: {str(e)}"],
            "messages":    [AIMessage(content=f"[{worker_name}] Error: {e}")],
            "next_worker": "supervisor",   # MUST always be present
        }
        # NOTE: No output_key returned in error path — preserves good data from previous workers
```

### 11.3 LLM Fallback Contract

All five LLM calls (supervisor fallback, generate_insight, generate_narrative, rank_all_fixes) must:

1. Call `litellm.completion()` wrapped in `try/except`
2. Strip markdown fences from response: `raw.replace("```json", "").replace("```", "").strip()`
3. Parse JSON with `try/except json.JSONDecodeError`
4. On any failure, return a valid fallback dict with all required keys
5. Never propagate an exception to the caller

**Minimum required insight fallback dict:**
```python
{
    "title":        f"Friction at {step_id}",
    "root_cause":   raw[:300] if raw else "LLM analysis unavailable.",
    "category":     "unknown",
    "evidence":     signals if signals else [],
    "suggested_fix": "Manual investigation required.",
    "fix_effort":   "medium",
}
```
