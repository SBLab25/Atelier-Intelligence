> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# System Design Document
## Customer Journey Intelligence (CJI) — Complete Implementation Contract

**Version:** 2.0  
**Date:** March 2026  
**Document Type:** Implementation System Design  
**Audience:** Claude Code — use this to build the complete system with zero ambiguity

---

## Table of Contents

1. [Builder's Guide](#1-builders-guide)
2. [Complete File Manifest](#2-complete-file-manifest)
3. [File-by-File Implementation Contracts](#3-file-by-file-implementation-contracts)
4. [Data Models — All Schemas](#4-data-models--all-schemas)
5. [API Contracts — All Interfaces](#5-api-contracts--all-interfaces)
6. [Database Design — All Tables](#6-database-design--all-tables)
7. [Algorithm Specifications](#7-algorithm-specifications)
8. [tracker.js Implementation Spec](#8-trackerjs-implementation-spec)
9. [LangGraph Graph Spec](#9-langgraph-graph-spec)
10. [Error Handling Contracts](#10-error-handling-contracts)
11. [Configuration System](#11-configuration-system)
12. [Build Verification Sequence](#12-build-verification-sequence)
13. [Test Specifications](#13-test-specifications)
14. [Integration Contracts](#14-integration-contracts)
15. [Code Quality Rules](#15-code-quality-rules)
16. [Critical Pitfalls Reference](#16-critical-pitfalls-reference)

---

## 1. Builder's Guide

### 1.1 What You Are Building

A Python + JavaScript application with:
- 1 JavaScript file (tracker.js — browser tracking)
- 19 Python files (collector, MCP servers, agents, tools, dashboard, CLI)
- 3 test files
- Config and setup files

The system has two operating modes controlled by `CJI_MODE` env var:
- `demo`: uses synthetic Faker data → Parquet → DuckDB VIEW
- `realtime`: uses browser events → tracker.js → FastAPI → DuckDB live_events table

The LangGraph agent system, 4 MCP servers, and all analytical logic are identical in both modes.

### 1.2 Build Order (Strict Dependency Chain)

```
STEP 1:  config.py                         no dependencies
STEP 2:  state.py                          no dependencies
STEP 3:  collector/models.py               pydantic only
STEP 4:  collector/api.py                  models + fastapi + duckdb
STEP 5:  tracker/tracker.js               no dependencies
STEP 6:  tracker/snippet_generator.py    stdlib only
STEP 7:  mcp_servers/friction_engine_server.py  config only
STEP 8:  tools/synthetic_data.py           faker + pandas + config
STEP 9:  mcp_servers/journey_data_server.py duckdb + config
STEP 10: mcp_servers/insight_server.py    litellm + chromadb + config
STEP 11: mcp_servers/report_server.py     litellm + config
STEP 12: tools/mcp_client.py              mcp SDK
STEP 13: agents/workers.py               mcp_client + state + config
STEP 14: agents/supervisor.py            state + config + litellm
STEP 15: graph.py                         all agents + langgraph
STEP 16: main.py                          graph + config + argparse
STEP 17: dashboard.py                    graph + streamlit + requests
STEP 18: tests/test_friction_engine.py   friction server
STEP 19: tests/test_collector_models.py  collector models
STEP 20: tests/test_synthetic_data.py    synthetic data
```

### 1.3 Non-Negotiable Implementation Rules

1. NEVER import from `mcp_servers/` in `agents/` — only through `tools/mcp_client.py`
2. NEVER call `anthropic.Anthropic()` directly — always `litellm.completion()`
3. NEVER mutate state in-place — return partial dict from workers
4. NEVER use `asyncio.run()` inside Streamlit — use `graph.stream()` directly
5. ALWAYS catch all exceptions in workers — never let workers raise
6. ALWAYS strip JSON markdown fences from LLM output
7. ALWAYS make DuckDB and ChromaDB connections module-level singletons
8. ALWAYS use `secrets.token_hex(16)` for API key generation — never random
9. ALWAYS include ALL CJIState keys in initial_state dict
10. ALWAYS pass `as_node="supervisor"` in `graph.update_state()` for human approval

---

## 2. Complete File Manifest

### 2.1 All Required Files

```
cji_agent/
├── config.py                          REQUIRED - all env vars and settings
├── state.py                           REQUIRED - CJIState TypedDict
├── graph.py                           REQUIRED - LangGraph compilation
├── main.py                            REQUIRED - CLI entry point
├── dashboard.py                       REQUIRED - Streamlit UI
│
├── tracker/
│   ├── tracker.js                     REQUIRED - browser tracking script
│   └── snippet_generator.py          REQUIRED - generates client embed code
│
├── collector/
│   ├── __init__.py                    REQUIRED - empty
│   ├── api.py                         REQUIRED - FastAPI collector
│   └── models.py                     REQUIRED - Pydantic schemas
│
├── mcp_servers/
│   ├── __init__.py                    REQUIRED - empty
│   ├── journey_data_server.py        REQUIRED - MCP 1, mode-aware
│   ├── friction_engine_server.py     REQUIRED - MCP 2, pure logic
│   ├── insight_server.py             REQUIRED - MCP 3, LLM + ChromaDB
│   └── report_server.py              REQUIRED - MCP 4, HTML reports
│
├── agents/
│   ├── __init__.py                    REQUIRED - empty
│   ├── supervisor.py                 REQUIRED - routing supervisor
│   └── workers.py                    REQUIRED - 4 worker functions
│
├── tools/
│   ├── __init__.py                    REQUIRED - empty
│   ├── mcp_client.py                 REQUIRED - MCP client wrapper
│   └── synthetic_data.py             REQUIRED - Faker generator
│
├── tests/
│   ├── __init__.py                    REQUIRED - empty
│   ├── test_friction_engine.py       REQUIRED - zero-dependency tests
│   ├── test_collector_models.py      REQUIRED - Pydantic validation tests
│   └── test_synthetic_data.py        REQUIRED - generator tests
│
├── requirements.txt                   REQUIRED
├── .env.example                       REQUIRED
├── .gitignore                         REQUIRED
└── README.md                          REQUIRED
```

### 2.2 Auto-Created at Runtime (NOT committed to git)

```
data/events.parquet           demo mode synthetic events
data/cji.duckdb               DuckDB file (both modes)
data/cji_checkpoints.db       LangGraph SQLite checkpoints
data/chroma/                  ChromaDB vector store directory
reports/cji_report_*.html     generated HTML reports
```

### 2.3 .gitignore Required Contents

```
.env
data/
reports/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
venv/
.venv/
*.egg-info/
dist/
build/
.DS_Store
*.sqlite3
node_modules/
```

---

## 3. File-by-File Implementation Contracts

### 3.1 config.py

**Must implement exactly:**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent

# Mode validation
CJI_MODE: str = os.getenv("CJI_MODE", "demo").lower()
assert CJI_MODE in ("demo", "realtime"), f"Invalid CJI_MODE: {CJI_MODE}"

# LLM settings
LLM_MODEL:       str   = os.getenv("LLM_MODEL",       "claude-sonnet-4-6")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0"))
LLM_MAX_TOKENS:  int   = int(os.getenv("LLM_MAX_TOKENS",   "4096"))

# API keys
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY:    str = os.getenv("OPENAI_API_KEY",    "")

# LangSmith
LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "true")
LANGCHAIN_API_KEY:    str = os.getenv("LANGCHAIN_API_KEY",    "")
LANGCHAIN_PROJECT:    str = os.getenv("LANGCHAIN_PROJECT",    "cji-poc")

# Paths (mkdir called here)
DATA_DIR       = ROOT / "data";   DATA_DIR.mkdir(exist_ok=True)
EVENTS_PARQUET = DATA_DIR / "events.parquet"
DUCKDB_PATH    = DATA_DIR / "cji.duckdb"
CHROMA_DIR     = DATA_DIR / "chroma"; CHROMA_DIR.mkdir(exist_ok=True)
(ROOT / "reports").mkdir(exist_ok=True)

# Collector
COLLECTOR_HOST:    str = os.getenv("COLLECTOR_HOST",    "http://localhost:8000")
COLLECTOR_PORT:    int = int(os.getenv("COLLECTOR_PORT", "8000"))
CJI_ADMIN_KEY:     str = os.getenv("CJI_ADMIN_KEY",    "changeme-set-in-prod")
COLLECTOR_API_KEY: str = os.getenv("COLLECTOR_API_KEY", "cji_dev_localtest")

# Agent
MAX_AGENT_ITERATIONS:     int = int(os.getenv("MAX_AGENT_ITERATIONS",     "20"))
FRICTION_SCORE_THRESHOLD: int = int(os.getenv("FRICTION_SCORE_THRESHOLD", "60"))
REALTIME_WINDOW_MINUTES:  int = int(os.getenv("REALTIME_WINDOW_MINUTES",  "60"))
REALTIME_AUTO_RUN_INTERVAL: int = int(os.getenv("REALTIME_AUTO_RUN_INTERVAL", "0"))

# Journey
JOURNEY_CONFIG: dict = {
    "name": os.getenv("JOURNEY_NAME", "onboarding"),
    "steps": ["landing_page","sign_up_form","email_verification","profile_setup","first_action","completion"],
}
```

### 3.2 state.py

```python
from __future__ import annotations
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class JourneyEvent(TypedDict):
    event_id: str; user_id: str; journey_id: str; step_id: str
    event_type: str; timestamp: str; duration_ms: int; metadata: dict[str, Any]

class FrictionScore(TypedDict):
    step_id: str; score: int; drop_off_rate: float; avg_dwell_ms: int
    retry_count: float; rage_click_rate: float; signals: list[str]
    confidence: float; is_critical: bool

class Insight(TypedDict):
    insight_id: str; step_id: str; title: str; root_cause: str
    category: str; evidence: list[str]; priority: int; fix_effort: str
    suggested_fix: str; score: int; priority_score: float

class WorkerStatus(TypedDict):
    worker: str; status: str; message: str

class CJIState(TypedDict):
    messages:             Annotated[list, add_messages]  # appends
    mode:                 str
    journey_name:         str
    journey_steps:        list[str]
    analysis_window_days: int
    analysis_window_mins: int
    live_event_count:     int
    collector_url:        str
    last_run_at:          str
    raw_events:           list[JourneyEvent]
    event_summary:        dict[str, Any]
    friction_scores:      list[FrictionScore]
    critical_steps:       list[str]
    insights:             list[Insight]
    prioritized_fixes:    list[dict]
    report_path:          str
    narrative:            str
    next_worker:          str
    worker_statuses:      list[WorkerStatus]
    errors:               list[str]
    iteration:            int
    human_approved:       bool
```

### 3.3 collector/models.py

**Must have field validators for:**
- `event_type`: must be in allowed set, raise ValueError if not
- `timestamp`: must parse as ISO-8601, raise ValueError if not
- `user_id`, `session_id`, `event_id`: min length 8, raise ValueError if shorter
- `url`: strip query params and fragments using urllib.parse.urlparse

**Three models required:**
- `TrackerEvent(BaseModel)` — single event
- `EventBatch(BaseModel)` — api_key + list[TrackerEvent] (max 100)
- `CollectorResponse(BaseModel)` — accepted + rejected + errors

### 3.4 collector/api.py

**Application setup:**
```python
app = FastAPI(title="CJI Event Collector", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["POST","GET","OPTIONS"], allow_headers=["*"])
```

**Database singleton:**
```python
_conn: duckdb.DuckDBPyConnection | None = None

def get_db() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(DUCKDB_PATH))
        _create_tables(_conn)
    return _conn
```

**Required routes with exact signatures:**
```python
@app.get("/tracker.js")                    → FileResponse(tracker.js, Cache-Control: 3600)
@app.post("/collect/batch")                → validate key, background write, CollectorResponse
@app.post("/collect/event")               → validate key, write, CollectorResponse
@app.get("/live/stats")                    → per-step counts, API key in header
@app.get("/live/feed")                     → SSE StreamingResponse, API key in header
@app.post("/admin/api-keys")              → create key, CJI_ADMIN_KEY in header
@app.get("/health")                        → {"status": "ok", "live_events_count": int}
```

**write_events return type:** `tuple[int, int, list[str]]` = (accepted, rejected, error_messages)

### 3.5 tracker/tracker.js

**Must be a self-contained IIFE wrapping all code:**
```javascript
(function(window, document) {
  'use strict';
  // all code here
}(window, document));
```

**Required config keys checked at startup:**
```javascript
if (!API_KEY || !ENDPOINT) {
    console.warn('[CJI] tracker: apiKey and endpoint are required');
    return;  // exit IIFE early — do not throw
}
```

**genId() function must produce UUID v4 without crypto.randomUUID() dependency** (fallback for older browsers):
```javascript
function genId() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}
```

**localStorage with try/catch fallback (private browsing):**
```javascript
try {
    userId = localStorage.getItem('_cji_uid') || genId();
    localStorage.setItem('_cji_uid', userId);
} catch(e) {
    userId = genId();  // private browsing — still works, just not persisted
}
```

### 3.6 mcp_servers/friction_engine_server.py

**Module-level constants (exact values, not approximate):**
```python
WEIGHTS  = {"abandon_rate": 0.35, "error_rate": 0.25, "avg_dwell_ms": 0.15, "avg_retries": 0.15, "avg_rage_clicks": 0.10}
BASELINES = {"abandon_rate": 10.0, "error_rate": 5.0, "avg_dwell_ms": 15_000, "avg_retries": 0.1, "avg_rage_clicks": 0.05}
```

**_normalise private function:**
```python
def _normalise(value: float, baseline: float) -> float:
    return min(value / max(baseline, 0.001), 3.0) / 3.0
```

**_compute_score return type:** `tuple[int, list[str], float]` = (score, signals, confidence)

**score_friction must call _compute_score and return dict with ALL keys:**
```python
return {
    "step_id": step_id, "score": score, "signals": signals,
    "confidence": confidence, "is_critical": score >= FRICTION_SCORE_THRESHOLD,
    "drop_off_rate": metrics.get("abandon_rate_pct", 0) / 100,
    "avg_dwell_ms": int(metrics.get("avg_dwell_ms", 0)),
    "retry_count": metrics.get("avg_retries", 0),
    "rage_click_rate": metrics.get("avg_rage_clicks", 0),
}
```

### 3.7 mcp_servers/journey_data_server.py

**_setup_views must branch on CJI_MODE:**
```python
def _setup_views(conn):
    if CJI_MODE == "demo":
        if not EVENTS_PARQUET.exists():
            raise FileNotFoundError(f"Run: python main.py --mode demo --generate-data")
        conn.execute(f"CREATE OR REPLACE VIEW events AS SELECT ... FROM read_parquet('{EVENTS_PARQUET}')")
    else:  # realtime
        conn.execute("CREATE TABLE IF NOT EXISTS live_events (...)")
        conn.execute("CREATE OR REPLACE VIEW events AS SELECT ... FROM live_events")
```

**_window_clause must branch on CJI_MODE:**
```python
def _window_clause(days_back=30, minutes_back=0):
    if CJI_MODE == "demo":
        return f"timestamp >= NOW() - INTERVAL '{days_back} days'"
    else:
        mins = minutes_back or REALTIME_WINDOW_MINUTES
        return f"timestamp >= NOW() - INTERVAL '{mins} minutes'"
```

**get_step_metrics core SQL must return these exact column names:**
`step_id, unique_users, completion_rate_pct, abandon_rate_pct, error_rate_pct, avg_dwell_ms, avg_rage_clicks, avg_retries`

**get_live_snapshot must return early in demo mode:**
```python
if CJI_MODE == "demo":
    return {"error": "get_live_snapshot is only available in realtime mode", "mode": "demo"}
```

### 3.8 mcp_servers/insight_server.py

**LiteLLM setup at module level:**
```python
import litellm
from config import ANTHROPIC_API_KEY, OPENAI_API_KEY
litellm.anthropic_key = ANTHROPIC_API_KEY
litellm.openai_key    = OPENAI_API_KEY
```

**generate_insight system prompt must:**
1. Start with role statement: "You are a senior UX analyst..."
2. Include "Respond ONLY with valid JSON"
3. Define exact JSON schema with all required fields
4. Specify constraints (max 8 words for title, etc.)

**JSON fallback is MANDATORY after every LLM call:**
```python
raw = raw.strip().replace("```json","").replace("```","").strip()
try:
    result = json.loads(raw)
    if not {"title","root_cause","category","evidence","suggested_fix","fix_effort"}.issubset(result.keys()):
        raise ValueError("missing fields")
except (json.JSONDecodeError, ValueError):
    result = {
        "title": f"Friction at {step_id}",
        "root_cause": raw[:300] if raw else "Analysis unavailable",
        "category": "unknown", "evidence": [],
        "suggested_fix": "Manual investigation required.", "fix_effort": "medium",
    }
result["step_id"] = step_id
result["score"]   = score
```

### 3.9 mcp_servers/report_server.py

**Report HTML structure (required sections in order):**
1. `<head>` with Chart.js CDN from jsdelivr
2. Header bar: dark background, journey name, mode badge (DEMO/LIVE), timestamp
3. Two-column chart grid: funnel bar chart + friction score bar chart
4. Executive narrative section
5. Prioritised findings table: step, issue, category, priority, effort, fix
6. Footer: model name, generated timestamp

**Chart colours (exact hex values):**
```
friction bar: score >= 70 → #e24b4a (red)
             score 50-69  → #ef9f27 (amber)
             score < 50   → #1d9e75 (green)
funnel bar:                → #378add (blue, always)
```

**Mode badge in report HTML:**
```html
<span class="mode-badge mode-{mode}">{mode.upper()}</span>
```

### 3.10 agents/supervisor.py

**supervisor must be a plain synchronous function:**
```python
def supervisor(state: CJIState) -> dict:
    # NOT async def
```

**route function (used in graph.add_conditional_edges):**
```python
def route(state: CJIState) -> str:
    return state.get("next_worker", "END")
```

**LLM fallback must always sanitise:**
```python
raw = response.choices[0].message.content.strip()
return raw if raw in VALID_NEXT else "END"
```

### 3.11 agents/workers.py

**data_worker mode-aware params:**
```python
if CJI_MODE == "realtime":
    kwargs = {"minutes_back": state.get("analysis_window_mins", REALTIME_WINDOW_MINUTES)}
else:
    kwargs = {"days_back": state.get("analysis_window_days", 30)}
```

**insight_worker target selection:**
```python
targets = [s for s in scores if s["step_id"] in critical or s.get("score", 0) > 50]
if not targets:
    return {"insights": [], "messages": [...], "next_worker": "supervisor"}
```

**users_by_step lookup must be built from step_metrics:**
```python
users_by_step = {m["step_id"]: m.get("unique_users", 1000) for m in step_metrics}
```

### 3.12 graph.py

**build_graph function signature:**
```python
def build_graph(use_persistence: bool = True) -> CompiledGraph:
```

**Checkpoint path must derive from DUCKDB_PATH:**
```python
checkpoint_path = str(DUCKDB_PATH).replace(".duckdb", "_checkpoints.db")
```

**Singleton getter:**
```python
_graph = None

def get_graph(use_persistence: bool = True):
    global _graph
    if _graph is None:
        _graph = build_graph(use_persistence)
    return _graph
```

### 3.13 main.py

**Mode must be applied to os.environ BEFORE any graph imports:**
```python
os.environ["CJI_MODE"] = args.mode
# Import graph AFTER this line
from graph import get_graph
```

**Initial state template (ALL keys required):**
```python
{
    "messages": [], "mode": mode,
    "journey_name": journey, "journey_steps": JOURNEY_CONFIG["steps"],
    "analysis_window_days": days, "analysis_window_mins": mins,
    "live_event_count": 0, "collector_url": os.getenv("COLLECTOR_HOST","http://localhost:8000"),
    "last_run_at": datetime.utcnow().isoformat() + "Z",
    "raw_events": [], "event_summary": {}, "friction_scores": [], "critical_steps": [],
    "insights": [], "prioritized_fixes": [], "report_path": "", "narrative": "",
    "next_worker": "", "worker_statuses": [], "errors": [], "iteration": 0,
    "human_approved": auto_approve,
}
```

### 3.14 dashboard.py

**Session state must be initialised before any st.* call:**
```python
for key, default in [
    ("thread_id",   None),
    ("state_snap",  {}),
    ("mode",        CJI_MODE),
    ("live_events", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default
```

**Mode change must reset state and rerun:**
```python
if selected_mode != st.session_state.mode:
    os.environ["CJI_MODE"] = selected_mode
    st.session_state.mode       = selected_mode
    st.session_state.thread_id  = None
    st.session_state.state_snap = {}
    st.rerun()
```

**CRITICAL — Never use asyncio.run() in Streamlit:**
```python
# WRONG:
asyncio.run(some_async_function())

# CORRECT:
for event in graph.stream(initial_state, config=config, stream_mode="values"):
    st.session_state.state_snap = event
```

---

## 4. Data Models — All Schemas

### 4.1 TrackerEvent (exact schema from browser)

```json
{
  "event_id":    "uuid-v4-string",
  "user_id":     "uuid-v4-string",
  "session_id":  "uuid-v4-string",
  "journey_id":  "onboarding",
  "step_id":     "email_verification",
  "event_type":  "page_view",
  "timestamp":   "2026-03-15T14:30:00.123Z",
  "duration_ms": 0,
  "url":         "https://example.com/verify-email",
  "metadata":    {"source": "organic"}
}
```

**Allowed event_type values:**
`page_view`, `click`, `form_submit`, `error`, `rage_click`, `abandon`, `step_complete`, `identify`

### 4.2 StepMetrics (from DuckDB get_step_metrics)

```json
{
  "step_id":             "email_verification",
  "unique_users":        847,
  "completion_rate_pct": 58.3,
  "abandon_rate_pct":    41.7,
  "error_rate_pct":      34.2,
  "avg_dwell_ms":        187432.0,
  "avg_rage_clicks":     1.23,
  "avg_retries":         2.87
}
```

### 4.3 FrictioScore (output of score_friction)

```json
{
  "step_id":         "email_verification",
  "score":           87,
  "drop_off_rate":   0.417,
  "avg_dwell_ms":    187432,
  "retry_count":     2.87,
  "rage_click_rate": 1.23,
  "signals":         ["critical_drop_off", "frequent_errors", "extended_hesitation", "repeated_retries", "rage_clicks_detected"],
  "confidence":      0.98,
  "is_critical":     true
}
```

### 4.4 Insight (output of generate_insight + prioritise_fix)

```json
{
  "insight_id":    "uuid-v4",
  "step_id":       "email_verification",
  "title":         "Email token expires before users act",
  "root_cause":    "The email verification token expires after 5 minutes, which is insufficient time for users who check email in a separate app or tab. This causes repeated failed verification attempts and high abandonment.",
  "category":      "system",
  "evidence":      ["Token expiry errors in 35% of sessions", "Avg dwell time 187s exceeds 5-min token lifetime", "Repeated retry rate of 2.87 per session"],
  "priority":      1,
  "fix_effort":    "medium",
  "suggested_fix": "Extend token expiry to 30 minutes and send a resend link after 3 minutes of inactivity.",
  "score":         87,
  "priority_score": 73529.0
}
```

### 4.5 WorkerStatus

```json
{
  "worker":  "friction_worker",
  "status":  "done",
  "message": "3 critical / 6 steps, avg=67"
}
```

**status values:** `"pending"`, `"running"`, `"done"`, `"error"`

### 4.6 EventBatch (POST /collect/batch body)

```json
{
  "api_key": "cji_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "events": [
    { ...TrackerEvent... },
    { ...TrackerEvent... }
  ]
}
```

---

## 5. API Contracts — All Interfaces

### 5.1 Collector API Routes

#### GET /tracker.js
- Response: JavaScript file content
- Headers: `Content-Type: application/javascript`, `Cache-Control: public, max-age=3600`
- Error: 404 if tracker.js file not found on server

#### POST /collect/batch
- Body: `EventBatch` JSON
- Response 200: `CollectorResponse {accepted, rejected, errors}`
- Response 401: `{detail: "Invalid API key"}` — if api_key not in active api_keys table
- Response 422: Pydantic validation error detail
- Note: writes happen in background task — response is immediate

#### GET /live/stats
- Query: `journey_id=string`, `minutes=int` (default 60)
- Headers: `x-cji-key: {api_key}`
- Response 200: `{stats: [{step_id, event_type, count}], window_minutes: int}`
- Response 401: invalid API key

#### GET /live/feed
- Query: `journey_id=string`
- Headers: `x-cji-key: {api_key}`
- Response: `text/event-stream` — SSE stream
- Each event: `data: {"event_id", "user_id" (truncated), "step_id", "event_type", "timestamp"}\n\n`
- Polls DuckDB every 2 seconds for new events

#### POST /admin/api-keys
- Query: `client_name=string`, `journey_id=string`
- Headers: `x-admin-key: {CJI_ADMIN_KEY}`
- Response 200: `{api_key, journey_id, client_name}`
- Response 403: invalid admin key

#### GET /health
- Response 200: `{status: "ok", live_events_count: int}`

### 5.2 MCP Tool Contracts (all 14 tools)

#### Journey Data MCP (6 tools)

```
get_system_info()
  → {mode, journey, steps, event_count, data_source, window}

get_funnel_steps()
  → {journey, steps: list[str], count, mode}

query_events(step_id="", days_back=30, limit=500)
  → {summary: list[dict], sample_events: list[dict], total_filtered, mode}

get_step_metrics(days_back=30, minutes_back=0)
  → {metrics: list[StepMetrics], window, mode}

get_funnel_dropoff(days_back=30, minutes_back=0)
  → {funnel: list[{step_id, users, drop_off_pct}], mode}

get_live_snapshot(minutes=15)
  → {snapshot: list[dict], window_mins, total_events, unique_users, mode}
  → OR {error: "not available in demo mode", mode: "demo"}
```

#### Friction Engine MCP (4 tools)

```
score_friction(step_metrics: dict)
  → FrictionScore dict (see Section 4.3)

score_all_steps(all_step_metrics: list[dict])
  → {scores: list[FrictionScore] sorted desc, critical_steps: list[str],
     avg_score: float, total_steps: int, critical_count: int}

detect_dropoffs(funnel_data: list[dict], threshold_pct=25.0)
  → {critical_dropoffs: list[{step_id, drop_off_pct, users_lost}],
     threshold_pct, count}

correlate_signals(scores: list[dict])
  → {signal_frequency: dict[str,int] top 10,
     co_occurring_patterns: dict[str,int],
     systemic_signals: list[str]}
```

#### Insight MCP (5 tools)

```
generate_insight(friction_score: dict)
  → Insight dict (with JSON fallback — never raises)

prioritise_fix(insight: dict, unique_users=1000)
  → insight dict + {priority: int 1-5, priority_score: float}

save_insight(insight: dict)
  → {insight_id: str (UUID), saved: True}

search_insights(query: str, n_results=5)
  → {results: list[{document, metadata, distance}], query}

rank_all_fixes(insights: list[dict])
  → {ranked_insights: list[dict] sorted by priority,
     action_plan: str (LLM-generated executive text)}
```

#### Report MCP (2 tools)

```
generate_narrative(insights, journey_name, avg_score, critical_count, mode)
  → {narrative: str (3 paragraphs), generated_at: ISO-8601 str}

export_report(journey_name, narrative, friction_scores, insights, funnel_data, mode)
  → {report_path: str (full path to HTML file), file_size_kb: float}
```

### 5.3 LangGraph Public API

```python
graph = get_graph()                              # get singleton compiled graph
config = {"configurable": {"thread_id": str}}   # required for all calls

# Start analysis
for event in graph.stream(initial_state, config=config, stream_mode="values"):
    state: dict = event   # full CJIState after each node

# Get current state
snapshot = graph.get_state(config)
state: dict    = snapshot.values   # full CJIState
next_nodes: tuple = snapshot.next  # ("report_worker",) if paused, () if END

# Approve and resume
graph.update_state(config, {"human_approved": True}, as_node="supervisor")
for event in graph.stream(None, config=config, stream_mode="values"):
    state: dict = event
```

---

## 6. Database Design — All Tables

### 6.1 DuckDB Schema

**events VIEW (demo mode — over Parquet):**
```sql
CREATE OR REPLACE VIEW events AS
SELECT
    event_id    VARCHAR,
    user_id     VARCHAR,
    journey_id  VARCHAR,
    step_id     VARCHAR,
    event_type  VARCHAR,
    timestamp   TIMESTAMPTZ,
    duration_ms BIGINT,
    metadata    VARCHAR     -- JSON string
FROM read_parquet('/path/to/events.parquet')
```

**live_events TABLE (realtime mode):**
```sql
CREATE TABLE IF NOT EXISTS live_events (
    event_id    VARCHAR PRIMARY KEY,
    user_id     VARCHAR NOT NULL,
    session_id  VARCHAR NOT NULL,
    journey_id  VARCHAR NOT NULL,
    step_id     VARCHAR NOT NULL,
    event_type  VARCHAR NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL,
    duration_ms BIGINT DEFAULT 0,
    url         VARCHAR DEFAULT '',
    metadata    VARCHAR DEFAULT '{}',
    received_at TIMESTAMPTZ DEFAULT NOW()
)
```

**events VIEW (realtime mode — over live_events):**
```sql
CREATE OR REPLACE VIEW events AS
SELECT
    event_id, user_id, journey_id, step_id,
    event_type, timestamp, duration_ms, metadata
FROM live_events
```

**api_keys TABLE:**
```sql
CREATE TABLE IF NOT EXISTS api_keys (
    api_key     VARCHAR PRIMARY KEY,
    journey_id  VARCHAR NOT NULL,
    client_name VARCHAR NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    active      BOOLEAN DEFAULT TRUE
)
```

**Dev key inserted on first startup:**
```sql
INSERT OR IGNORE INTO api_keys (api_key, journey_id, client_name)
VALUES ('cji_dev_localtest', 'onboarding', 'Local Development')
```

### 6.2 ChromaDB Collection

```
Collection name:    cji_insights
Distance metric:    cosine
Embedding model:    all-MiniLM-L6-v2 (auto-downloaded by sentence-transformers)

Document format:    "{title}. {root_cause}. {suggested_fix}"

Metadata (all str): {
    step_id:    str,
    category:   str,   "UX"|"data"|"system"|"process"|"unknown"
    priority:   str,   "1" through "5"
    score:      str,   integer as string
    fix_effort: str,   "low"|"medium"|"high"
}
```

### 6.3 SQLite Checkpoint (LangGraph managed)

File: `data/cji_checkpoints.db`  
Do not access directly — only via LangGraph API.

The checkpoint stores full CJIState JSON serialised by LangGraph. Each node execution creates a checkpoint. The `thread_id` in config links checkpoints to analysis runs.

---

## 7. Algorithm Specifications

### 7.1 Friction Score (exact pseudocode)

```
INPUTS: step_metrics (StepMetrics dict)
OUTPUTS: (score: int, signals: list[str], confidence: float)

abandon = step_metrics.get("abandon_rate_pct", 0)
error   = step_metrics.get("error_rate_pct",   0)
dwell   = step_metrics.get("avg_dwell_ms",     0)
retries = step_metrics.get("avg_retries",      0)
rclicks = step_metrics.get("avg_rage_clicks",  0)

norm(v, b) = min(v / max(b, 0.001), 3.0) / 3.0

raw = norm(abandon, 10.0)  * 0.35
    + norm(error,   5.0)   * 0.25
    + norm(dwell,   15000) * 0.15
    + norm(retries, 0.1)   * 0.15
    + norm(rclicks, 0.05)  * 0.10

score = min(100, int(raw * 100))

signals = []
if abandon > 30:    signals.append("high_drop_off")
if abandon > 50:    signals.append("critical_drop_off")
if error > 15:      signals.append("frequent_errors")
if dwell > 60000:   signals.append("extended_hesitation")
if dwell > 120000:  signals.append("severe_confusion")
if retries > 1.0:   signals.append("repeated_retries")
if rclicks > 0.5:   signals.append("rage_clicks_detected")

confidence = min(0.5 + len(signals) * 0.1, 0.98)
```

### 7.2 Priority Score (exact formula)

```
INPUTS: insight (dict with score and fix_effort), unique_users (int)
OUTPUTS: priority (int 1-5), priority_score (float)

effort_map = {"low": 1, "medium": 2, "high": 4}
effort = effort_map.get(insight["fix_effort"], 2)
impact = insight["score"] * unique_users
priority_score = impact / effort

if priority_score > 40000: priority = 1
elif priority_score > 20000: priority = 2
elif priority_score > 8000: priority = 3
elif priority_score > 2000: priority = 4
else: priority = 5
```

### 7.3 Drop-Off Detection

```
INPUTS: funnel_data (list of {step_id, users, drop_off_pct}), threshold_pct (float)
OUTPUTS: critical_dropoffs list

for row in funnel_data:
    if row["drop_off_pct"] >= threshold_pct:
        critical_dropoffs.append({
            "step_id": row["step_id"],
            "drop_off_pct": row["drop_off_pct"],
            "users_lost": int(row["users"])
        })

sort by drop_off_pct descending
```

### 7.4 Rage Click Detection (tracker.js)

```
INPUTS: element (DOM node), click timestamp
STATE:  rageBuffer = {el: null, times: []}

if rageBuffer.el !== element:
    rageBuffer = {el: element, times: [now]}
else:
    rageBuffer.times.push(now)
    rageBuffer.times = filter(times where now - t < RAGE_WINDOW_MS=500)

if rageBuffer.times.length >= RAGE_THRESHOLD=3:
    fire "rage_click" event with click_count = rageBuffer.times.length
    rageBuffer = {el: null, times: []}  # reset
```

---

## 8. tracker.js Implementation Spec

### 8.1 Event Object Factory

Every event must be created with makeEvent():

```javascript
function makeEvent(type, meta) {
    return {
        event_id:    genId(),
        user_id:     userId,
        session_id:  sessionId,
        journey_id:  JOURNEY_ID,
        step_id:     currentStep,
        event_type:  type,
        timestamp:   new Date().toISOString(),
        duration_ms: 0,
        url:         sanitiseUrl(window.location.href),
        metadata:    meta || {},
    };
}
```

### 8.2 URL Sanitiser

```javascript
function sanitiseUrl(url) {
    try {
        var parsed = new URL(url);
        return parsed.protocol + '//' + parsed.host + parsed.pathname;
    } catch(e) {
        return url.split('?')[0].split('#')[0];
    }
}
```

### 8.3 SPA Navigation Handling

```javascript
var _origPush    = history.pushState;
var _origReplace = history.replaceState;

history.pushState = function() {
    _origPush.apply(history, arguments);
    onNavigation();
};
history.replaceState = function() {
    _origReplace.apply(history, arguments);
    onNavigation();
};
window.addEventListener('popstate', onNavigation);

function onNavigation() {
    var prevStep  = currentStep;
    var dwell     = Date.now() - pageStart;
    // Record dwell on previous step
    if (prevStep && prevStep !== 'unknown_step') {
        var ev = makeEvent('step_complete', {dwell_reason: 'spa_navigate'});
        ev.step_id     = prevStep;
        ev.duration_ms = dwell;
        push(ev);
    }
    // New page view after URL updates
    setTimeout(trackPageView, 50);
}
```

### 8.4 sendBeacon Fallback

```javascript
window.addEventListener('beforeunload', function() {
    var dwell = Date.now() - pageStart;
    var ev    = makeEvent('abandon', {dwell_reason: 'page_unload'});
    ev.duration_ms = dwell;
    queue.push(ev);

    if (navigator.sendBeacon) {
        var blob = new Blob([JSON.stringify({api_key: API_KEY, events: queue})],
                            {type: 'application/json'});
        navigator.sendBeacon(ENDPOINT + '/batch', blob);
    } else {
        // Synchronous XHR fallback (not recommended but works)
        fetch(ENDPOINT + '/batch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CJI-Key': API_KEY},
            body: JSON.stringify({api_key: API_KEY, events: queue}),
            keepalive: true
        });
    }
    queue = [];
});
```

---

## 9. LangGraph Graph Spec

### 9.1 Complete Node and Edge Definitions

```python
builder = StateGraph(CJIState)

# Nodes (order matters for documentation, not execution)
builder.add_node("supervisor",      supervisor)      # sync function
builder.add_node("data_worker",     data_worker)     # async function
builder.add_node("friction_worker", friction_worker) # async function
builder.add_node("insight_worker",  insight_worker)  # async function
builder.add_node("report_worker",   report_worker)   # async function

# Entry
builder.add_edge(START, "supervisor")

# Supervisor routes conditionally
builder.add_conditional_edges(
    "supervisor",
    route,  # reads state["next_worker"]
    {
        "data_worker":     "data_worker",
        "friction_worker": "friction_worker",
        "insight_worker":  "insight_worker",
        "report_worker":   "report_worker",
        "END":             END,
    },
)

# All workers return to supervisor
for worker in ["data_worker","friction_worker","insight_worker","report_worker"]:
    builder.add_edge(worker, "supervisor")
```

### 9.2 Compilation

```python
checkpoint_db = str(DUCKDB_PATH).replace(".duckdb", "_checkpoints.db")
checkpointer = SqliteSaver.from_conn_string(checkpoint_db) if use_persistence else MemorySaver()
graph = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["report_worker"],
)
```

### 9.3 Streaming

```python
# Start analysis
for event in graph.stream(initial_state, config=config, stream_mode="values"):
    # event is the full CJIState dict after each node execution
    # May be called up to N times where N = number of nodes that execute
    pass

# Resume after human approval
graph.update_state(config, {"human_approved": True}, as_node="supervisor")
for event in graph.stream(None, config=config, stream_mode="values"):
    # stream(None) resumes from checkpoint — does not restart
    pass
```

---

## 10. Error Handling Contracts

### 10.1 Worker Error Contract (mandatory pattern)

```python
async def any_worker(state: CJIState) -> dict:
    try:
        # ... worker logic
        return {"output_key": result, "next_worker": "supervisor", ...}
    except Exception as e:
        # MUST include next_worker: "supervisor" — graph must not hang
        # MUST NOT include output keys that would overwrite good data
        return {
            "errors":   state.get("errors", []) + [f"{worker_name}: {type(e).__name__}: {str(e)}"],
            "messages": [AIMessage(content=f"[{worker_name}] Error: {e}")],
            "next_worker": "supervisor",
        }
```

### 10.2 LLM Output Handling (mandatory)

```python
# Step 1: Get LLM response
raw = response.choices[0].message.content.strip()

# Step 2: Strip markdown fences (ALWAYS — even if system prompt says not to use them)
raw = raw.replace("```json", "").replace("```", "").strip()

# Step 3: Parse with fallback (NEVER let JSONDecodeError propagate)
try:
    result = json.loads(raw)
    # Step 4: Validate required fields
    required = {"title", "root_cause", "category", "evidence", "suggested_fix", "fix_effort"}
    if not required.issubset(result.keys()):
        raise ValueError(f"LLM response missing fields: {required - result.keys()}")
except (json.JSONDecodeError, ValueError) as e:
    # Step 5: Fallback — always return valid structure
    result = {
        "title":        f"Friction at {step_id}",
        "root_cause":   raw[:300] if raw else "LLM analysis unavailable.",
        "category":     "unknown",
        "evidence":     signals if signals else [],
        "suggested_fix": "Manual investigation required.",
        "fix_effort":   "medium",
    }
```

### 10.3 MCP Connection Error Contract

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
        # Re-raise as RuntimeError so worker's outer try/except catches it
        raise RuntimeError(f"MCP tool '{tool_name}' failed: {type(e).__name__}: {e}") from e
```

### 10.4 Collector Event Write Contract

```python
def write_events(events: list[dict]) -> tuple[int, int, list[str]]:
    accepted, rejected, errors = 0, 0, []
    for ev in events:
        try:
            conn.execute("INSERT OR IGNORE INTO live_events (...) VALUES (...)", [...])
            accepted += 1
        except Exception as e:
            rejected += 1
            errors.append(f"{ev.get('event_id','?')}: {str(e)[:100]}")
    return accepted, rejected, errors
# Individual event failures never crash the batch
```

---

## 11. Configuration System

### 11.1 Environment Variable Loading Order

1. `os.environ` — system environment variables
2. `.env` file — loaded by `python-dotenv`'s `load_dotenv()`
3. `config.py` defaults — fallback values in `os.getenv("KEY", "default")`

Priority: system env > .env file > hardcoded default

### 11.2 Mode Switching at Runtime

For CLI (main.py):
```python
# MUST set before importing graph or config
os.environ["CJI_MODE"] = args.mode
from graph import get_graph  # imports AFTER mode is set
```

For Dashboard (dashboard.py):
```python
os.environ["CJI_MODE"] = selected_mode
# Force session reset
st.session_state.mode       = selected_mode
st.session_state.thread_id  = None
st.session_state.state_snap = {}
st.rerun()  # script re-runs from top, config re-reads CJI_MODE
```

---

## 12. Build Verification Sequence

Run these in order after building. Each step must pass before proceeding.

```bash
# Step 1: Imports
python -c "from config import CJI_MODE, DUCKDB_PATH; print(f'Config OK: mode={CJI_MODE}')"
python -c "from state import CJIState; print('State OK')"
python -c "from collector.models import EventBatch; print('Models OK')"

# Step 2: Friction engine unit tests (zero deps)
pytest tests/test_friction_engine.py -v
# Expected: 12+ tests PASSED

# Step 3: Data generation (demo mode)
python main.py --mode demo --generate-data
# Expected: "Generated X,XXX events → data/events.parquet"

# Step 4: MCP server standalone test
python -c "
import subprocess, sys, json
p = subprocess.Popen([sys.executable, 'mcp_servers/friction_engine_server.py'],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)
p.stdin.write(b'{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"params\":{},\"id\":1}\n')
p.stdin.flush()
line = p.stdout.readline()
assert b'cji-friction-engine' in line, f'Unexpected: {line}'
p.terminate()
print('MCP server OK')
"

# Step 5: Full pipeline (demo)
python main.py --mode demo --run --auto-approve
# Expected: "Report generated: reports/cji_report_*.html"

# Step 6: Report file check
import glob
reports = glob.glob('reports/cji_report_*.html')
assert len(reports) > 0, 'No report generated'
print(f'Report: {reports[-1]}')

# Step 7: Collector API (realtime)
uvicorn collector.api:app --port 8000 &
curl http://localhost:8000/health
# Expected: {"status":"ok","live_events_count":0}
pkill -f uvicorn

# Step 8: Dashboard
# streamlit run dashboard.py   (manual verification — opens browser)
```

---

## 13. Test Specifications

### 13.1 tests/test_friction_engine.py

All tests must pass with zero imports requiring: network, API keys, DuckDB, ChromaDB.

```python
import sys; sys.path.insert(0, "..")
import pytest
from mcp_servers.friction_engine_server import (
    score_friction, score_all_steps, detect_dropoffs, correlate_signals,
    _normalise, _compute_score, WEIGHTS, BASELINES, FRICTION_SCORE_THRESHOLD
)
```

**Required test functions:**

```python
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

def test_high_step_signals(high_step):
    r = score_friction(high_step)
    assert "critical_drop_off" in r["signals"]
    assert "rage_clicks_detected" in r["signals"]

def test_zero_inputs_zero_score():
    r = score_friction({"step_id": "t", "abandon_rate_pct": 0, "error_rate_pct": 0,
                        "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0})
    assert r["score"] == 0
    assert r["signals"] == []

def test_all_steps_sorted_desc(low_step, high_step):
    r = score_all_steps([low_step, high_step])
    scores = [s["score"] for s in r["scores"]]
    assert scores == sorted(scores, reverse=True)

def test_critical_list_correct(low_step, high_step):
    r = score_all_steps([low_step, high_step])
    assert "email_verification" in r["critical_steps"]
    assert "landing_page" not in r["critical_steps"]

def test_detect_dropoffs_above_threshold():
    funnel = [{"step_id": "a", "drop_off_pct": 50.0, "users": 500},
              {"step_id": "b", "drop_off_pct": 10.0, "users": 450}]
    r = detect_dropoffs(funnel, 25.0)
    assert r["count"] == 1
    assert r["critical_dropoffs"][0]["step_id"] == "a"

def test_detect_dropoffs_empty():
    r = detect_dropoffs([{"step_id": "x", "drop_off_pct": 5.0, "users": 1000}], 25.0)
    assert r["count"] == 0

def test_systemic_signals():
    scores = [{"step_id": "a", "signals": ["high_drop_off"]},
              {"step_id": "b", "signals": ["high_drop_off"]},
              {"step_id": "c", "signals": ["high_drop_off"]}]
    r = correlate_signals(scores)
    assert "high_drop_off" in r["systemic_signals"]

def test_full_pipeline_no_crash(low_step, high_step):
    all_scores   = score_all_steps([low_step, high_step])
    dropoffs     = detect_dropoffs(
        [{"step_id": s["step_id"], "drop_off_pct": s["drop_off_rate"]*100, "users": 500}
         for s in all_scores["scores"]])
    correlation  = correlate_signals(all_scores["scores"])
    assert all_scores["total_steps"] == 2
    assert isinstance(dropoffs, dict)
    assert isinstance(correlation, dict)
```

### 13.2 tests/test_collector_models.py

```python
import sys; sys.path.insert(0, "..")
import pytest
from pydantic import ValidationError
from collector.models import TrackerEvent, EventBatch

def test_valid_event():
    e = TrackerEvent(event_id="a"*8, user_id="b"*8, session_id="c"*8,
                     journey_id="onboarding", step_id="landing_page",
                     event_type="page_view", timestamp="2026-01-01T00:00:00Z",
                     url="https://example.com/page?token=abc")
    assert e.url == "https://example.com/page"  # query stripped

def test_invalid_event_type():
    with pytest.raises(ValidationError):
        TrackerEvent(event_id="a"*8, user_id="b"*8, session_id="c"*8,
                     journey_id="j", step_id="s", event_type="INVALID_TYPE",
                     timestamp="2026-01-01T00:00:00Z", url="")

def test_short_id_rejected():
    with pytest.raises(ValidationError):
        TrackerEvent(event_id="abc",  # too short (< 8)
                     user_id="b"*8, session_id="c"*8,
                     journey_id="j", step_id="s",
                     event_type="page_view", timestamp="2026-01-01T00:00:00Z", url="")

def test_url_fragment_stripped():
    e = TrackerEvent(event_id="a"*8, user_id="b"*8, session_id="c"*8,
                     journey_id="j", step_id="s",
                     event_type="page_view", timestamp="2026-01-01T00:00:00Z",
                     url="https://example.com/page#section")
    assert "#" not in e.url

def test_batch_accepts_valid():
    events = [{"event_id": "a"*8, "user_id": "b"*8, "session_id": "c"*8,
               "journey_id": "j", "step_id": "s", "event_type": "page_view",
               "timestamp": "2026-01-01T00:00:00Z", "url": ""} for _ in range(3)]
    batch = EventBatch(api_key="cji_live_" + "x"*20, events=events)
    assert len(batch.events) == 3
```

---

## 14. Integration Contracts

### 14.1 tracker.js → Collector

**Payload format (exact):**
```json
{
  "api_key": "cji_live_xxxx",
  "events": [
    {
      "event_id":    "uuid",
      "user_id":     "uuid",
      "session_id":  "uuid",
      "journey_id":  "onboarding",
      "step_id":     "landing_page",
      "event_type":  "page_view",
      "timestamp":   "2026-03-15T10:30:00.000Z",
      "duration_ms": 0,
      "url":         "https://example.com/",
      "metadata":    {"source": "organic"}
    }
  ]
}
```

**Headers:** `Content-Type: application/json`, `X-CJI-Key: {api_key}`

**Collector response:** `{"accepted": 1, "rejected": 0, "errors": []}`

### 14.2 Workers → MCP Tools (stdio)

```python
# In any worker:
async with mcp_session("friction_engine") as sess:
    result = await call_tool(sess, "score_all_steps", {
        "all_step_metrics": step_metrics  # list of StepMetrics dicts
    })
# result is a dict matching the score_all_steps return schema
```

### 14.3 LiteLLM Calls

**All LLM calls from insight_server.py and report_server.py:**
```python
response = litellm.completion(
    model=LLM_MODEL,           # from config — never hardcoded
    temperature=LLM_TEMPERATURE,
    max_tokens=LLM_MAX_TOKENS,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ],
)
text = response.choices[0].message.content.strip()
```

---

## 15. Code Quality Rules

### 15.1 Python Style

- Type annotations on all function parameters and return types
- One-line docstring on every public function
- Max 100 chars per line
- Imports: stdlib → third-party → local (blank line between groups)
- f-strings preferred over `.format()` or `%`
- No bare `except:` — always `except Exception as e:`

### 15.2 Naming

- Files: `snake_case.py`
- Variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE` at module level
- Classes: `PascalCase`
- Private functions: `_leading_underscore`
- MCP tools: `verb_noun` (e.g. `score_friction`, `generate_insight`)

### 15.3 MCP Tool Names (exact, immutable)

```
Journey Data MCP:  get_system_info, get_funnel_steps, query_events,
                   get_step_metrics, get_funnel_dropoff, get_live_snapshot
Friction MCP:      score_friction, score_all_steps, detect_dropoffs, correlate_signals
Insight MCP:       generate_insight, prioritise_fix, save_insight,
                   search_insights, rank_all_fixes
Report MCP:        generate_narrative, export_report
```

### 15.4 Signal Names (exact, immutable — tests depend on these)

```
"high_drop_off"        "critical_drop_off"    "frequent_errors"
"extended_hesitation"  "severe_confusion"     "repeated_retries"
"rage_clicks_detected"
```

---

## 16. Critical Pitfalls Reference

| # | Symptom | Root Cause | Fix |
|---|---|---|---|
| 1 | `FileNotFoundError: events.parquet` | Not generated | `python main.py --mode demo --generate-data` |
| 2 | `DuckDB IO Error: lock on file` | Two write connections to same file | Collector writes; MCP only reads. Both use same DUCKDB_PATH but different connection purposes |
| 3 | `LiteLLM AuthenticationError` | Missing or wrong API key | Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env |
| 4 | `json.JSONDecodeError` in generate_insight | LLM added markdown fences | Strip ```json ``` before json.loads() |
| 5 | `KeyError` on initial state | Missing CJIState key | Use full template — ALL keys required |
| 6 | Supervisor loops infinitely | iteration not incrementing | supervisor must return `"iteration": iteration + 1` |
| 7 | `ChromaDB ValueError: metadata type` | Non-string metadata value | Wrap all values in str() before saving |
| 8 | Human approval not resuming | Missing as_node | `graph.update_state(config, {...}, as_node="supervisor")` |
| 9 | `asyncio.run() RuntimeError` in Streamlit | Using async in sync context | Use `graph.stream()` directly — it's synchronous |
| 10 | MCP server exits immediately | Import error in server file | Test with `python mcp_servers/server.py` directly |
| 11 | `tracker.js CORS error` | Collector blocking browser origin | `allow_origins=["*"]` in CORSMiddleware |
| 12 | `sendBeacon` not sending abandon events | Privacy extension blocking | Expected in dev; not critical for demo |
| 13 | First-run pause (2 min) | sentence-transformers model download | Normal — model cached after first run |
| 14 | Collector returns 401 for valid key | Key not in api_keys table | Ensure collector has started (creates table with dev key) |
| 15 | `get_live_snapshot` in demo mode | Called wrong mode | Function returns error dict, not exception |
| 16 | Dashboard stale after run | Streamlit session not updated | Call `st.session_state.state_snap = event` in stream loop |
| 17 | CJI_MODE not changing in dashboard | Config imported before env set | Mode change must call `st.rerun()` to re-import config |
| 18 | report_worker not triggered | human_approved not set correctly | `graph.update_state(config, {"human_approved": True}, as_node="supervisor")` |
| 19 | No events in realtime mode | Collector not running | Start with `uvicorn collector.api:app --port 8000` |
| 20 | Wrong step_id in events | stepMap not configured in CJI_CONFIG | Set window.CJI_CONFIG.stepMap before tracker.js loads |
