> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# MVP Technical Documentation
## Customer Journey Intelligence (CJI) — Complete Build Reference

**Version:** 2.0  
**Date:** March 2026  
**Audience:** Claude Code and developers building the CJI system  
**Purpose:** Every implementation detail needed to build the system correctly, in one place

---

## Table of Contents

1. [Technology Stack](#1-technology-stack)
2. [Complete Repository Structure](#2-complete-repository-structure)
3. [Environment Setup](#3-environment-setup)
4. [Configuration Reference](#4-configuration-reference)
5. [Demo Mode — Data Layer](#5-demo-mode--data-layer)
6. [Realtime Mode — Tracking Layer](#6-realtime-mode--tracking-layer)
7. [MCP Server Specifications](#7-mcp-server-specifications)
8. [LangGraph Agent Specifications](#8-langgraph-agent-specifications)
9. [State Management](#9-state-management)
10. [LiteLLM Integration](#10-litellm-integration)
11. [Dashboard Implementation](#11-dashboard-implementation)
12. [CLI Implementation](#12-cli-implementation)
13. [Testing Specification](#13-testing-specification)
14. [Error Handling Patterns](#14-error-handling-patterns)
15. [Observability](#15-observability)
16. [Dependency Versions](#16-dependency-versions)
17. [Build Order and Verification](#17-build-order-and-verification)
18. [Critical Implementation Rules](#18-critical-implementation-rules)
19. [Common Failure Modes](#19-common-failure-modes)

---

## 1. Technology Stack

### 1.1 Full Stack Table

| Layer | Technology | Version | Role | Why |
|---|---|---|---|---|
| Agent orchestration | LangGraph | ≥0.2.0 | Multi-agent graph, checkpoints, interrupt | Native human-in-loop, typed state, LangSmith integration |
| LLM adapter | langchain-anthropic | ≥0.3.0 | Anthropic model adapter | Required by LangGraph for Anthropic models |
| LLM abstraction | LiteLLM | ≥1.40.0 | Provider-agnostic LLM calls | Swap Claude/GPT-4o/Ollama with 1 env var |
| MCP framework | FastMCP | ≥0.4.0 | MCP server builder | Decorator-based, minimal boilerplate |
| MCP protocol | mcp | ≥1.0.0 | MCP client/server | Official Anthropic MCP SDK |
| Event storage | DuckDB | ≥0.10.0 | Analytics SQL engine | In-process, reads Parquet, fast aggregations |
| Vector store | ChromaDB | ≥0.5.0 | Insight persistence | Local persistent, no external service |
| Data frames | Pandas | ≥2.0.0 | DataFrame operations | Standard tabular data manipulation |
| Parquet I/O | PyArrow | ≥14.0.0 | Parquet format | Required by Pandas and DuckDB |
| Synthetic data | Faker | ≥24.0.0 | Realistic fake events | Produces believable sessions |
| Collector API | FastAPI | ≥0.111.0 | HTTP event receiver | Async, Pydantic v2, CORS, SSE |
| ASGI server | Uvicorn | ≥0.30.0 | Runs collector API | Production-grade async server |
| Validation | Pydantic | ≥2.0.0 | Event schema validation | Type safety, auto-validation |
| HTTP client | httpx | ≥0.27.0 | Async HTTP (MCP HTTP future) | Required for HTTP MCP transport |
| HTTP client sync | requests | ≥2.31.0 | Dashboard → Collector stats | Sync calls from Streamlit |
| Retry logic | tenacity | ≥8.2.0 | LLM call retry with backoff | Handles transient API errors |
| Observability | LangSmith | ≥0.1.0 | Agent trace logging | Zero-code integration with LangGraph |
| Dashboard | Streamlit | ≥1.35.0 | Demo UI | Python-native, fastest path to working UI |
| Charts | Plotly | ≥5.20.0 | Interactive charts | Native Streamlit integration |
| Config | python-dotenv | ≥1.0.0 | .env loading | Standard 12-factor app config |

### 1.2 Python Version

**Minimum:** Python 3.11. **Recommended:** Python 3.12.

### 1.3 LLM Provider Priority

```
1. claude-sonnet-4-6  (default)  → ANTHROPIC_API_KEY
2. gpt-4o                         → OPENAI_API_KEY
3. ollama/llama3.1   (offline)   → local Ollama, no key needed
```

**Rule:** ALL LLM calls go through `litellm.completion()`. Direct `anthropic.Anthropic()` imports are forbidden in production code.

---

## 2. Complete Repository Structure

```
cji_agent/
│
├── config.py                        # All settings, env vars, paths — loaded once
├── state.py                         # CJIState TypedDict + sub-types
├── graph.py                         # LangGraph graph compilation
├── main.py                          # CLI entry point
├── dashboard.py                     # Streamlit dashboard
│
├── tracker/
│   ├── tracker.js                   # Browser tracking script (single file, no deps)
│   └── snippet_generator.py        # Generates client embed code + API key
│
├── collector/
│   ├── __init__.py
│   ├── api.py                       # FastAPI collector server
│   └── models.py                   # Pydantic v2 event models
│
├── mcp_servers/
│   ├── __init__.py
│   ├── journey_data_server.py      # MCP 1: journey events (mode-aware)
│   ├── friction_engine_server.py   # MCP 2: deterministic scoring
│   ├── insight_server.py           # MCP 3: LLM insights + ChromaDB
│   └── report_server.py            # MCP 4: HTML report generation
│
├── agents/
│   ├── __init__.py
│   ├── supervisor.py               # Routing supervisor (sync function)
│   └── workers.py                  # 4 worker async functions
│
├── tools/
│   ├── __init__.py
│   ├── mcp_client.py               # MCP client wrapper
│   └── synthetic_data.py           # Faker event generator
│
├── tests/
│   ├── __init__.py
│   ├── test_friction_engine.py     # Unit tests (zero network/API needed)
│   ├── test_synthetic_data.py      # Generator tests
│   └── test_collector_models.py    # Pydantic validation tests
│
├── data/                            # Auto-created at runtime — not committed
│   ├── events.parquet               # Demo mode synthetic events
│   ├── cji.duckdb                   # DuckDB (demo VIEW + realtime live_events table)
│   ├── cji_checkpoints.db           # LangGraph SQLite checkpoints
│   └── chroma/                      # ChromaDB vector store
│
├── reports/                         # Auto-created at runtime — not committed
│   └── cji_report_*.html            # Generated HTML reports
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

### 2.1 File Rules

- `config.py`: no side effects at import except `load_dotenv()` and `mkdir`
- `mcp_servers/*.py`: each must be independently runnable as `__main__`
- `tests/*.py`: must have `sys.path.insert(0, "..")` at top
- `tracker/tracker.js`: pure browser JavaScript, no modules, no build step
- `collector/__init__.py`: empty
- `agents/__init__.py`: empty
- `mcp_servers/__init__.py`: empty
- `tools/__init__.py`: empty

---

## 3. Environment Setup

### 3.1 Installation

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set LLM_MODEL and API key
```

### 3.2 Verification Script

```bash
python -c "
import langgraph, fastmcp, duckdb, chromadb, litellm, fastapi, streamlit
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite import SqliteSaver
print('All imports OK')
"
```

### 3.3 First-Run Sequence (Demo Mode)

```bash
python main.py --mode demo --generate-data        # → data/events.parquet created
python mcp_servers/friction_engine_server.py      # → starts, Ctrl+C to stop
pytest tests/ -v                                   # → all tests pass
python main.py --mode demo --run --auto-approve    # → reports/cji_report_*.html created
streamlit run dashboard.py                         # → http://localhost:8501
```

### 3.4 First-Run Sequence (Realtime Mode)

```bash
# Terminal 1
uvicorn collector.api:app --host 0.0.0.0 --port 8000

# Terminal 2
python tracker/snippet_generator.py --journey onboarding --host http://localhost:8000
# → creates client_setup/ with embed snippet and API key

# Embed tracker.js on your test site using embed_snippet.html
# Run verify_tracker.py to confirm events are received

# Terminal 3
CJI_MODE=realtime python main.py --run --window-mins 30
```

---

## 4. Configuration Reference

### 4.1 config.py — All Variables

```python
# Mode
CJI_MODE: str                    # "demo" | "realtime" — from env CJI_MODE, default "demo"

# LLM
LLM_MODEL: str                   # e.g. "claude-sonnet-4-6" — from env LLM_MODEL
LLM_TEMPERATURE: float           # 0.0 — from env LLM_TEMPERATURE, default 0
LLM_MAX_TOKENS: int              # 4096 — from env LLM_MAX_TOKENS

# API Keys
ANTHROPIC_API_KEY: str           # from env ANTHROPIC_API_KEY
OPENAI_API_KEY: str              # from env OPENAI_API_KEY

# LangSmith
LANGCHAIN_TRACING_V2: str        # "true" — from env
LANGCHAIN_API_KEY: str           # from env
LANGCHAIN_PROJECT: str           # "cji-poc" — from env

# Paths
ROOT: Path                       # Path(__file__).parent
DATA_DIR: Path                   # ROOT / "data" — mkdir(exist_ok=True)
EVENTS_PARQUET: Path             # DATA_DIR / "events.parquet"
DUCKDB_PATH: Path                # DATA_DIR / "cji.duckdb"
CHROMA_DIR: Path                 # DATA_DIR / "chroma" — mkdir(exist_ok=True)

# Collector (realtime mode)
COLLECTOR_HOST: str              # "http://localhost:8000" — from env
COLLECTOR_PORT: int              # 8000 — from env
CJI_ADMIN_KEY: str               # "changeme-set-in-prod" — from env
COLLECTOR_API_KEY: str           # "cji_dev_localtest" — from env

# Agent
MAX_AGENT_ITERATIONS: int        # 20 — from env
FRICTION_SCORE_THRESHOLD: int    # 60 — from env

# Realtime
REALTIME_WINDOW_MINUTES: int     # 60 — from env
REALTIME_AUTO_RUN_INTERVAL: int  # 0 (disabled) — from env

# Journey
JOURNEY_CONFIG: dict             # {name: str, steps: list[str]}
```

### 4.2 .env.example

```
CJI_MODE=demo
LLM_MODEL=claude-sonnet-4-6
ANTHROPIC_API_KEY=your_key_here
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=cji-poc
COLLECTOR_HOST=http://localhost:8000
COLLECTOR_API_KEY=cji_dev_localtest
CJI_ADMIN_KEY=changeme-set-in-prod
REALTIME_WINDOW_MINUTES=60
FRICTION_SCORE_THRESHOLD=60
MAX_AGENT_ITERATIONS=20
```

---

## 5. Demo Mode — Data Layer

### 5.1 synthetic_data.py — Implementation Spec

**Step friction profiles (module-level dict, exact values required):**

```python
STEP_PROFILES = {
    "landing_page":       {"drop_rate": 0.15, "avg_dwell_s": 12,  "error_rate": 0.02},
    "sign_up_form":       {"drop_rate": 0.25, "avg_dwell_s": 45,  "error_rate": 0.18},
    "email_verification": {"drop_rate": 0.42, "avg_dwell_s": 180, "error_rate": 0.35},  # high friction — required
    "profile_setup":      {"drop_rate": 0.20, "avg_dwell_s": 60,  "error_rate": 0.08},
    "first_action":       {"drop_rate": 0.12, "avg_dwell_s": 30,  "error_rate": 0.05},
    "completion":         {"drop_rate": 0.05, "avg_dwell_s": 10,  "error_rate": 0.01},
}
```

**Session simulation loop:**

```python
for step in steps:
    1. Generate page_view: dwell_ms = max(500, int(gauss(avg_dwell_s*1000, avg_dwell_s*200)))
    2. If random() < error_rate: generate error event with:
       metadata = {"error_code": choice(["TIMEOUT","VALIDATION_FAIL","SERVER_500","TOKEN_EXPIRED"]),
                   "retry_count": randint(1, 4)}
    3. If random() < error_rate * 0.5: generate rage_click with:
       metadata = {"click_count": randint(3, 10), "element": "submit-btn"}
    4. If random() < drop_rate: generate abandon → BREAK (session ends)
    5. Else: generate step_complete → continue to next step
```

**Public API:**

```python
def generate(n_sessions: int = 2000, days: int = 30) -> pd.DataFrame:
    # Returns DataFrame, writes to EVENTS_PARQUET
```

**Required columns in output DataFrame:** `event_id`, `user_id`, `journey_id`, `step_id`, `event_type`, `timestamp` (datetime64[us,UTC]), `duration_ms` (int64), `metadata` (JSON string)

### 5.2 DuckDB Demo Mode Setup

**Connection singleton (module-level in journey_data_server.py):**

```python
_conn: Optional[duckdb.DuckDBPyConnection] = None

def _db() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(DUCKDB_PATH))
        _setup_views(_conn)
    return _conn
```

**View creation (demo mode):**

```python
conn.execute(f"""
    CREATE OR REPLACE VIEW events AS
    SELECT event_id, user_id, journey_id, step_id,
           event_type, timestamp, duration_ms, metadata
    FROM read_parquet('{EVENTS_PARQUET}')
""")
```

**Time window clause (demo mode):**

```python
f"timestamp >= NOW() - INTERVAL '{days_back} days'"
```

---

## 6. Realtime Mode — Tracking Layer

### 6.1 tracker.js — Implementation Spec

**Required window.CJI_CONFIG keys:**

```javascript
{
    apiKey:    string,   // required — client API key
    journeyId: string,   // required — e.g. "onboarding"
    endpoint:  string,   // required — collector URL e.g. "http://localhost:8000/collect"
    stepMap:   object,   // required — {"/path": "step_id"}
    debug:     boolean,  // optional — default false
}
```

**Anonymous identity generation:**

```javascript
// user_id: UUID v4, persisted in localStorage
// session_id: UUID v4, new per page load
// Falls back to in-memory UUID if localStorage unavailable (private browsing)
```

**Event batching:**

```javascript
const MAX_BATCH  = 20;     // flush threshold
const FLUSH_MS   = 5000;   // flush interval

// On each event: push to queue, start timer if not running
// On flush: POST to ENDPOINT/batch with {api_key, events}
// On beforeunload: flush remaining queue with navigator.sendBeacon (fallback)
```

**Rage click detection:**

```javascript
const RAGE_WINDOW_MS = 500;
const RAGE_THRESHOLD = 3;
// Track clicks per element; if 3+ clicks within 500ms → fire rage_click event
// Reset buffer after detection
```

**SPA navigation:**

```javascript
// Intercept history.pushState and history.replaceState
// On navigation: record step_complete with dwell_ms, then trackPageView for new step
// Also handle window.addEventListener('popstate')
```

**Public API exposed on window.CJITracker:**

```javascript
window.CJITracker = {
    track: function(eventType, metadata) { ... },  // manual event firing
    identify: function(traits) { ... },             // anonymised trait enrichment
    flush: function() { ... },                       // force flush
}
```

**Embed tag pattern:**

```html
<script>
  window.CJI_CONFIG = {
    apiKey:    'cji_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    journeyId: 'onboarding',
    endpoint:  'https://your-server/collect',
    stepMap: { '/': 'landing_page', '/signup': 'sign_up_form' }
  };
</script>
<script src="https://your-server/tracker.js" async crossorigin="anonymous"></script>
```

### 6.2 collector/models.py — Pydantic Schemas

```python
class TrackerEvent(BaseModel):
    event_id:    str    # min_length 8
    user_id:     str    # min_length 8
    session_id:  str    # min_length 8
    journey_id:  str
    step_id:     str
    event_type:  str    # validated against allowed set
    timestamp:   str    # ISO-8601, validated by datetime.fromisoformat
    duration_ms: int    # ge=0
    url:         str    # stripped of query params in validator
    metadata:    dict[str, Any]

    @field_validator("event_type")
    # Allowed: page_view|click|form_submit|error|rage_click|abandon|step_complete|identify

    @field_validator("url")
    # Strip query params: urlparse → scheme://netloc/path only

class EventBatch(BaseModel):
    api_key: str    # min_length 20
    events:  list[TrackerEvent]  # min=1, max=100

class CollectorResponse(BaseModel):
    accepted: int
    rejected: int
    errors:   list[str] = []
```

### 6.3 collector/api.py — FastAPI Routes

**All routes:**

```
GET  /tracker.js              → serve tracker.js (FileResponse, Cache-Control: 1h)
POST /collect/batch           → receive EventBatch, validate API key, write in background
POST /collect/event           → receive SingleEvent, validate API key, write
GET  /live/stats              → per-step counts for last N minutes (API key in header)
GET  /live/feed               → SSE stream of new events (API key in header)
POST /admin/api-keys          → create new API key (CJI_ADMIN_KEY in header)
GET  /health                  → {"status": "ok", "live_events_count": int}
```

**DuckDB live_events table creation (in _create_tables):**

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

**api_keys table creation:**

```sql
CREATE TABLE IF NOT EXISTS api_keys (
    api_key     VARCHAR PRIMARY KEY,
    journey_id  VARCHAR NOT NULL,
    client_name VARCHAR NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    active      BOOLEAN DEFAULT TRUE
)
-- Insert dev key for local testing:
INSERT OR IGNORE INTO api_keys (api_key, journey_id, client_name)
VALUES ('cji_dev_localtest', 'onboarding', 'Local Development')
```

**Event write pattern (background task):**

```python
def write_events(events: list[dict]) -> tuple[int, int, list[str]]:
    # INSERT OR IGNORE to handle duplicate event_ids
    # Returns (accepted, rejected, errors)
```

**CORS middleware:**

```python
app.add_middleware(CORSMiddleware,
    allow_origins=["*"],           # restrict to client domains in production
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)
```

### 6.4 snippet_generator.py — Output Files

```python
# Input arguments: --journey, --host, --output, --debug
# Generated files in output directory:
#   embed_snippet.html   — HTML snippet for website <head>
#   verify_tracker.py    — Python script to test tracker connection
#   useCJITracker.js     — React/Next.js hook
#   api_key.json         — {api_key, journey_id, host, created_at}
```

**API key format:** `cji_live_{secrets.token_hex(16)}` — 36 characters total

### 6.5 DuckDB Realtime Mode Setup

**Table (not VIEW — live data needs INSERT):**

```python
# In journey_data_server.py _setup_views() for realtime mode:
conn.execute("CREATE TABLE IF NOT EXISTS live_events (...)")
conn.execute("CREATE OR REPLACE VIEW events AS SELECT ... FROM live_events")
```

**Time window clause (realtime mode):**

```python
f"timestamp >= NOW() - INTERVAL '{minutes_back} minutes'"
```

**Important:** Collector API and Journey Data MCP both connect to the same `DUCKDB_PATH`. In the PoC they run in separate processes. DuckDB supports one writer per file — the collector writes, the MCP reads via the VIEW. This works because MCP only reads.

---

## 7. MCP Server Specifications

### 7.1 FastMCP Pattern (applies to all 4 servers)

```python
from fastmcp import FastMCP

mcp = FastMCP(name="cji-server-name", description="...")

@mcp.tool(
    description="Verb-noun description of what this tool does.",
    annotations={"readOnlyHint": True, "idempotentHint": True},
)
def tool_name(param: str, optional_param: int = 30) -> dict:
    """Docstring."""
    return {"key": "value"}

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 7.2 MCP Server 1: Journey Data Server

**File:** `mcp_servers/journey_data_server.py`  
**Name:** `cji-journey-data`  
**Mode-aware:** Yes — reads Parquet (demo) or live_events table (realtime)

**Tools:**

| Tool | Signature | Returns | Annotations |
|---|---|---|---|
| `get_system_info` | `() -> dict` | mode, journey, steps, event_count, data_source | readOnly |
| `get_funnel_steps` | `() -> dict` | journey, steps, count, mode | readOnly |
| `query_events` | `(step_id="", days_back=30, limit=500) -> dict` | summary, sample_events, total_filtered, mode | readOnly |
| `get_step_metrics` | `(days_back=30, minutes_back=0) -> dict` | metrics list, window, mode | readOnly |
| `get_funnel_dropoff` | `(days_back=30, minutes_back=0) -> dict` | funnel list, mode | readOnly |
| `get_live_snapshot` | `(minutes=15) -> dict` | snapshot, window_mins, total_events (realtime only) | readOnly |

**Step metrics output schema (per row):**

```
step_id, unique_users, completion_rate_pct, abandon_rate_pct,
error_rate_pct, avg_dwell_ms, avg_rage_clicks, avg_retries
```

**Funnel dropoff output schema (per row):**

```
step_id, users, drop_off_pct
```

### 7.3 MCP Server 2: Friction Engine Server

**File:** `mcp_servers/friction_engine_server.py`  
**Name:** `cji-friction-engine`  
**Mode-aware:** No — pure computation, no data access

**Module-level constants:**

```python
WEIGHTS = {
    "abandon_rate":    0.35,
    "error_rate":      0.25,
    "avg_dwell_ms":    0.15,
    "avg_retries":     0.15,
    "avg_rage_clicks": 0.10,
}
BASELINES = {
    "abandon_rate":    10.0,
    "error_rate":      5.0,
    "avg_dwell_ms":    15_000,
    "avg_retries":     0.1,
    "avg_rage_clicks": 0.05,
}
```

**Private functions:**

```python
def _normalise(value: float, baseline: float) -> float:
    return min(value / max(baseline, 0.001), 3.0) / 3.0

def _compute_score(metrics: dict) -> tuple[int, list[str], float]:
    # returns (score, signals, confidence)
```

**Tools:**

| Tool | Signature | Returns | Annotations |
|---|---|---|---|
| `score_friction` | `(step_metrics: dict) -> dict` | FrictionScore dict | readOnly, idempotent |
| `score_all_steps` | `(all_step_metrics: list[dict]) -> dict` | scores sorted desc, critical_steps, avg_score | readOnly, idempotent |
| `detect_dropoffs` | `(funnel_data: list[dict], threshold_pct=25.0) -> dict` | critical_dropoffs, count | readOnly |
| `correlate_signals` | `(scores: list[dict]) -> dict` | signal_frequency, co_occurring_patterns, systemic_signals | readOnly |

**Exact signal strings (immutable — tests depend on these):**

```
"high_drop_off"        abandon > 30%
"critical_drop_off"    abandon > 50%
"frequent_errors"      error > 15%
"extended_hesitation"  dwell > 60,000ms
"severe_confusion"     dwell > 120,000ms
"repeated_retries"     retries > 1.0
"rage_clicks_detected" rage_clicks > 0.5
```

### 7.4 MCP Server 3: Insight Server

**File:** `mcp_servers/insight_server.py`  
**Name:** `cji-insight`  
**Mode-aware:** No

**ChromaDB singleton:**

```python
_chroma: Optional[chromadb.Collection] = None

def _collection():
    global _chroma
    if _chroma is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _chroma = client.get_or_create_collection("cji_insights", metadata={"hnsw:space": "cosine"})
    return _chroma
```

**LLM call wrapper:**

```python
def _llm(system: str, user: str) -> str:
    response = litellm.completion(
        model=LLM_MODEL, temperature=LLM_TEMPERATURE, max_tokens=LLM_MAX_TOKENS,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return response.choices[0].message.content.strip()
```

**generate_insight system prompt must include:**
- "Respond ONLY with valid JSON"
- Exact schema: title (max 8 words), root_cause (2-3 sentences), category (UX|data|system|process), evidence (list), suggested_fix (1-2 sentences), fix_effort (low|medium|high)

**JSON fallback (mandatory):**

```python
raw = raw.strip().replace("```json", "").replace("```", "").strip()
try:
    result = json.loads(raw)
    required = {"title","root_cause","category","evidence","suggested_fix","fix_effort"}
    if not required.issubset(result.keys()):
        raise ValueError("Missing fields")
except (json.JSONDecodeError, ValueError):
    result = {
        "title": f"Friction at {step_id}",
        "root_cause": raw[:300] if raw else "Analysis unavailable",
        "category": "unknown",
        "evidence": [],
        "suggested_fix": "Manual investigation required.",
        "fix_effort": "medium",
    }
```

**ChromaDB metadata must be string types:**

```python
metadata = {
    "step_id":    str(insight["step_id"]),
    "category":   str(insight["category"]),
    "priority":   str(insight.get("priority", 3)),
    "score":      str(insight.get("score", 0)),
    "fix_effort": str(insight.get("fix_effort", "")),
}
```

**search_insights guard:**

```python
n = min(n_results, coll.count())
if n == 0:
    return {"results": [], "query": query}
results = coll.query(query_texts=[query], n_results=n)
```

**Tools:**

| Tool | Signature | Returns |
|---|---|---|
| `generate_insight` | `(friction_score: dict) -> dict` | Insight dict (with fallback) |
| `prioritise_fix` | `(insight: dict, unique_users: int = 1000) -> dict` | Insight + priority, priority_score |
| `save_insight` | `(insight: dict) -> dict` | {insight_id, saved: True} |
| `search_insights` | `(query: str, n_results: int = 5) -> dict` | {results, query} |
| `rank_all_fixes` | `(insights: list[dict]) -> dict` | {ranked_insights, action_plan} |

### 7.5 MCP Server 4: Report Server

**File:** `mcp_servers/report_server.py`  
**Name:** `cji-report`  
**Mode-aware:** Accepts mode parameter, shows DEMO/LIVE badge in report

**Report file path:** `{ROOT}/reports/cji_report_{journey_name}_{YYYYMMDD_HHMMSS}.html`

**Chart.js CDN:** `https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js`

**Friction bar chart colours:** `#e24b4a` (≥70), `#ef9f27` (50–69), `#1d9e75` (<50)

**Tools:**

| Tool | Signature | Returns |
|---|---|---|
| `generate_narrative` | `(insights, journey_name, avg_score, critical_count, mode) -> dict` | {narrative, generated_at} |
| `export_report` | `(journey_name, narrative, friction_scores, insights, funnel_data, mode) -> dict` | {report_path, file_size_kb} |

---

## 8. LangGraph Agent Specifications

### 8.1 Supervisor Function

**Type:** Synchronous Python function (NOT async)  
**File:** `agents/supervisor.py`

```python
VALID_NEXT = {"data_worker", "friction_worker", "insight_worker", "report_worker", "END"}

def supervisor(state: CJIState) -> dict:
    has_data     = bool(state.get("event_summary"))
    has_scores   = bool(state.get("friction_scores"))
    has_insights = bool(state.get("insights"))
    is_approved  = state.get("human_approved", False)
    has_report   = bool(state.get("report_path"))
    iteration    = state.get("iteration", 0)

    if iteration >= MAX_AGENT_ITERATIONS:  next_w = "END"
    elif not has_data:                      next_w = "data_worker"
    elif not has_scores:                    next_w = "friction_worker"
    elif not has_insights:                  next_w = "insight_worker"
    elif not is_approved:                   next_w = "END"     # pause gate
    elif not has_report:                    next_w = "report_worker"
    else:                                   next_w = "END"
    
    return {"next_worker": next_w, "iteration": iteration + 1}

def route(state: CJIState) -> str:
    return state.get("next_worker", "END")
```

**LLM fallback (_llm_route):** called only when none of above match; returns single worker name string; sanitised against VALID_NEXT before use.

### 8.2 Worker Pattern (all 4 workers)

**Type:** Async Python function  
**File:** `agents/workers.py`

```python
async def worker_name(state: CJIState) -> dict:
    print(f"[worker_name] Starting in {CJI_MODE} mode...")
    try:
        async with mcp_session("server_key") as sess:
            result = await call_tool(sess, "tool_name", args)
        return {
            "output_key": result,
            "worker_statuses": state.get("worker_statuses", []) + [
                WorkerStatus(worker="worker_name", status="done", message="...")
            ],
            "messages": [AIMessage(content="[worker_name] Summary.")],
            "next_worker": "supervisor",
        }
    except Exception as e:
        return {
            "errors":   state.get("errors", []) + [f"worker_name: {e}"],
            "messages": [AIMessage(content=f"[worker_name] Error: {e}")],
            "next_worker": "supervisor",
        }
```

### 8.3 data_worker (mode-aware)

**Mode logic:**

```python
if CJI_MODE == "realtime":
    mins   = state.get("analysis_window_mins", REALTIME_WINDOW_MINUTES)
    kwargs = {"minutes_back": mins}
else:
    days   = state.get("analysis_window_days", 30)
    kwargs = {"days_back": days}
```

**MCP calls:**
1. `get_system_info({})` → info dict
2. `get_step_metrics(kwargs)` → step metrics
3. `get_funnel_dropoff(kwargs)` → funnel data
4. `get_funnel_steps({})` → step list
5. If realtime: `get_live_snapshot({"minutes": mins})` → live counts

**Writes to state:** `event_summary`, `journey_steps`, `live_event_count`

### 8.4 friction_worker (mode-agnostic)

**MCP calls:**
1. `score_all_steps({"all_step_metrics": step_metrics})` → scores + critical list
2. `correlate_signals({"scores": scores})` → systemic signal analysis

**Writes to state:** `friction_scores`, `critical_steps`

### 8.5 insight_worker (mode-agnostic)

**Target selection:**

```python
targets = [s for s in scores if s["step_id"] in critical or s.get("score", 0) > 50]
```

**Per-target MCP calls (in sequence):**
1. `generate_insight({"friction_score": score})` → raw insight
2. `prioritise_fix({"insight": raw, "unique_users": users_by_step.get(step_id, 1000)})` → prioritised
3. `save_insight({"insight": prioritised})` → persisted

**Final MCP call:**
4. `rank_all_fixes({"insights": all_insights})` → ranked list + action plan

**Writes to state:** `insights`, `prioritized_fixes`

### 8.6 report_worker (mode-agnostic)

**MCP calls:**
1. `generate_narrative({insights, journey_name, avg_score, critical_count, mode})`
2. `export_report({journey_name, narrative, friction_scores, insights, funnel_data, mode})`

**Writes to state:** `report_path`, `narrative`

### 8.7 Graph Compilation

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

builder = StateGraph(CJIState)
builder.add_node("supervisor",      supervisor)       # sync
builder.add_node("data_worker",     data_worker)      # async
builder.add_node("friction_worker", friction_worker)  # async
builder.add_node("insight_worker",  insight_worker)   # async
builder.add_node("report_worker",   report_worker)    # async
builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", route,
    {"data_worker": "data_worker", "friction_worker": "friction_worker",
     "insight_worker": "insight_worker", "report_worker": "report_worker", "END": END})
for w in ["data_worker", "friction_worker", "insight_worker", "report_worker"]:
    builder.add_edge(w, "supervisor")

checkpointer = SqliteSaver.from_conn_string(checkpoint_db_path) if use_persistence else MemorySaver()
graph = builder.compile(checkpointer=checkpointer, interrupt_before=["report_worker"])
```

### 8.8 Human-in-Loop Resume Pattern

```python
# Pause occurs automatically when supervisor routes to "report_worker"
# because of interrupt_before=["report_worker"]

# Check state after pause:
snapshot = graph.get_state(config)
# snapshot.next == ("report_worker",) means paused

# Update and resume:
graph.update_state(config, {"human_approved": True}, as_node="supervisor")
for event in graph.stream(None, config=config, stream_mode="values"):
    pass  # report_worker now runs
```

---

## 9. State Management

### 9.1 Complete CJIState TypedDict

```python
from __future__ import annotations
from typing import Annotated, Any
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class CJIState(TypedDict):
    messages:             Annotated[list, add_messages]  # appends, never overwrites
    mode:                 str           # "demo" | "realtime"
    journey_name:         str
    journey_steps:        list[str]
    analysis_window_days: int           # demo: days back to query
    analysis_window_mins: int           # realtime: minutes back to query
    live_event_count:     int
    collector_url:        str
    last_run_at:          str           # ISO timestamp
    raw_events:           list[dict]
    event_summary:        dict[str, Any]
    friction_scores:      list[dict]
    critical_steps:       list[str]
    insights:             list[dict]
    prioritized_fixes:    list[dict]
    report_path:          str
    narrative:            str
    next_worker:          str
    worker_statuses:      list[dict]
    errors:               list[str]
    iteration:            int
    human_approved:       bool
```

### 9.2 Initial State Template

```python
initial_state: CJIState = {
    "messages": [], "mode": mode,
    "journey_name": journey_name,
    "journey_steps": JOURNEY_CONFIG["steps"],
    "analysis_window_days": days,
    "analysis_window_mins": mins,
    "live_event_count": 0,
    "collector_url": COLLECTOR_HOST,
    "last_run_at": datetime.utcnow().isoformat() + "Z",
    "raw_events": [], "event_summary": {},
    "friction_scores": [], "critical_steps": [],
    "insights": [], "prioritized_fixes": [],
    "report_path": "", "narrative": "",
    "next_worker": "", "worker_statuses": [],
    "errors": [], "iteration": 0,
    "human_approved": auto_approve,
}
```

### 9.3 State Update Rules

- Workers return a **partial dict** — LangGraph merges into checkpoint
- `messages` key uses `add_messages` reducer — appends new messages
- All other keys **replace** — last write wins
- Growing lists: `state.get("key", []) + [new_item]`
- Never mutate state in-place

---

## 10. LiteLLM Integration

### 10.1 Standard Call Pattern

```python
import litellm
from config import LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS, ANTHROPIC_API_KEY, OPENAI_API_KEY

litellm.anthropic_key = ANTHROPIC_API_KEY
litellm.openai_key    = OPENAI_API_KEY

def _llm(system: str, user: str) -> str:
    response = litellm.completion(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return response.choices[0].message.content.strip()
```

### 10.2 Provider Model Strings

| Provider | LLM_MODEL value |
|---|---|
| Anthropic | `claude-sonnet-4-6` |
| OpenAI | `gpt-4o` |
| Ollama local | `ollama/llama3.1` |
| Ollama Mistral | `ollama/mistral` |

### 10.3 JSON Stripping (mandatory for all LLM outputs)

```python
raw = response.strip()
for fence in ["```json", "```"]:
    raw = raw.replace(fence, "").strip()
```

---

## 11. Dashboard Implementation

### 11.1 Session State Initialisation (must be at top of script)

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

### 11.2 Mode Toggle

```python
selected_mode = st.radio("Mode", ["demo", "realtime"], horizontal=True)
if selected_mode != st.session_state.mode:
    os.environ["CJI_MODE"] = selected_mode
    st.session_state.mode       = selected_mode
    st.session_state.thread_id  = None
    st.session_state.state_snap = {}
    st.rerun()
```

### 11.3 Analysis Trigger (blocking pattern — correct for Streamlit)

```python
# NOTE: Never use asyncio.run() in Streamlit — use graph.stream() directly
if st.button("Run"):
    for event in graph.stream(initial_state, config=config, stream_mode="values"):
        st.session_state.state_snap = event
    st.rerun()
```

### 11.4 Approval Gate

```python
if not approved and not report and insights:
    if st.button("Approve & generate report"):
        graph.update_state(config, {"human_approved": True}, as_node="supervisor")
        for event in graph.stream(None, config=config, stream_mode="values"):
            st.session_state.state_snap = event
        st.rerun()
```

### 11.5 Collector Health Check (realtime mode)

```python
def collector_health() -> bool:
    try:
        r = requests.get(f"{COLLECTOR_HOST}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False
```

---

## 12. CLI Implementation

### 12.1 Full Argument Matrix

```
--mode demo|realtime         # CJI_MODE (default: from .env)
--generate-data              # demo: run synthetic_data.generate()
--generate-snippet           # realtime: run snippet_generator.py
--run                        # start LangGraph analysis
--approve                    # resume after human review
--auto-approve               # skip human gate (demo mode)
--thread-id UUID             # resume specific thread
--days N                     # demo analysis window (default 30)
--window-mins N              # realtime window (default REALTIME_WINDOW_MINUTES)
--journey NAME               # journey name (default "onboarding")
--host URL                   # collector host for --generate-snippet
```

### 12.2 Mode Override

```python
os.environ["CJI_MODE"] = args.mode
# Must be set BEFORE importing config or graph modules
```

---

## 13. Testing Specification

### 13.1 Required Test Files

**tests/test_friction_engine.py** — All tests must pass with zero network calls, zero API keys:

```python
import sys
sys.path.insert(0, "..")
from mcp_servers.friction_engine_server import (
    score_friction, score_all_steps, detect_dropoffs, correlate_signals
)

# Fixtures
@pytest.fixture
def low_step():
    return {"step_id": "landing_page", "abandon_rate_pct": 8.0, "error_rate_pct": 2.0,
            "avg_dwell_ms": 10_000, "avg_retries": 0.05, "avg_rage_clicks": 0.02}

@pytest.fixture
def high_step():
    return {"step_id": "email_verification", "abandon_rate_pct": 55.0, "error_rate_pct": 38.0,
            "avg_dwell_ms": 200_000, "avg_retries": 3.2, "avg_rage_clicks": 1.8}

# Required tests (minimum):
def test_low_friction_below_threshold(low_step)          # score < 60, is_critical=False
def test_high_friction_is_critical(high_step)            # score >= 60, is_critical=True
def test_score_bounded_0_to_100(high_step)               # 0 <= score <= 100
def test_confidence_bounded_0_to_1(high_step)            # 0 <= confidence <= 0.98
def test_high_step_has_critical_signals(high_step)       # "critical_drop_off" in signals
def test_zero_inputs_gives_zero_score()                  # all zeros → score=0, signals=[]
def test_all_steps_sorted_descending(low_step, high_step)
def test_critical_list_correct(low_step, high_step)      # email_verification in critical
def test_detect_dropoffs_above_threshold()
def test_detect_dropoffs_empty_below_threshold()
def test_systemic_signals_detected()
def test_full_pipeline_no_crash(low_step, high_step)
```

**tests/test_collector_models.py:**

```python
import sys
sys.path.insert(0, "..")
from collector.models import TrackerEvent, EventBatch

def test_valid_event_parses()
def test_invalid_event_type_rejected()        # ValueError
def test_url_query_params_stripped()           # /page?token=abc → /page
def test_short_id_rejected()                   # len < 8 → ValueError
def test_batch_too_large_rejected()            # > 100 events
def test_metadata_defaults_to_empty_dict()
```

---

## 14. Error Handling Patterns

### 14.1 Worker Error Template

```python
except Exception as e:
    return {
        "errors":   state.get("errors", []) + [f"worker_name: {type(e).__name__}: {str(e)}"],
        "messages": [AIMessage(content=f"[worker_name] Failed: {e}")],
        "next_worker": "supervisor",
        # Note: NO other keys — don't overwrite good data with empty values
    }
```

### 14.2 MCP call_tool Error

```python
async def call_tool(session, tool_name, arguments):
    try:
        result = await session.call_tool(tool_name, arguments=arguments)
        if result.content and len(result.content) > 0:
            text = result.content[0].text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return text
        return {}
    except Exception as e:
        raise RuntimeError(f"MCP tool '{tool_name}' failed: {e}") from e
```

### 14.3 Supervisor Safety

```python
if iteration >= MAX_AGENT_ITERATIONS:
    return {
        "next_worker": "END",
        "iteration":   iteration + 1,
        "errors":      state.get("errors", []) + [f"Safety cutoff at iteration {iteration}"],
    }
```

### 14.4 Collector Event Write

```python
# INSERT OR IGNORE for duplicate event_id protection
# Per-event try/except: reject individual bad events, accept good ones in same batch
# Return (accepted, rejected, errors) to calling endpoint
```

---

## 15. Observability

### 15.1 LangSmith (zero-code integration)

Set in .env:
```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=cji-poc
```

Automatically captured: every graph node, every LLM call (model, tokens, cost), every MCP tool call (via LangChain), graph topology.

### 15.2 Console Output Format

```
[supervisor] iteration=1 → data_worker
  ✓  data_worker          Fetched metrics for 6 steps (15234 events, realtime mode)
[supervisor] iteration=2 → friction_worker
  ✓  friction_worker      3 critical / 6 steps, avg=67
...
```

---

## 16. Dependency Versions

```
langgraph==0.2.28
langchain-anthropic==0.3.3
langchain-core==0.3.15
litellm==1.44.0
fastmcp==0.4.1
mcp==1.2.0
duckdb==0.10.3
pandas==2.2.2
pyarrow==16.1.0
chromadb==0.5.3
faker==24.14.0
fastapi==0.111.1
uvicorn[standard]==0.30.1
httpx==0.27.0
requests==2.32.3
python-multipart==0.0.9
pydantic==2.7.4
langsmith==0.1.98
streamlit==1.36.0
plotly==5.22.0
python-dotenv==1.0.1
tenacity==8.4.2
sentence-transformers==3.0.1
pytest==8.2.2
pytest-asyncio==0.23.7
```

---

## 17. Build Order and Verification

### 17.1 Correct Build Sequence

```
1.  config.py              — no dependencies
2.  state.py               — no dependencies
3.  collector/models.py    — pydantic only
4.  collector/api.py       — models + fastapi + duckdb
5.  tracker/tracker.js     — no dependencies
6.  tracker/snippet_generator.py — stdlib only
7.  mcp_servers/friction_engine_server.py — config only
8.  tools/synthetic_data.py — faker + pandas + config
9.  mcp_servers/journey_data_server.py — duckdb + config
10. mcp_servers/insight_server.py — litellm + chromadb + config
11. mcp_servers/report_server.py — litellm + config
12. tools/mcp_client.py    — mcp SDK
13. agents/workers.py      — mcp_client + state + config
14. agents/supervisor.py   — state + config + litellm
15. graph.py               — all agents + langgraph
16. main.py                — graph + config
17. dashboard.py           — graph + streamlit + requests
18. tests/                 — mcp_servers (friction)
```

### 17.2 Verification Checklist

```bash
python -c "from config import CJI_MODE; print('config OK')"
python -c "from state import CJIState; print('state OK')"
python -c "from collector.models import EventBatch; print('models OK')"
python -c "from mcp_servers.friction_engine_server import score_friction; print('friction OK')"
python main.py --mode demo --generate-data
pytest tests/ -v
python main.py --mode demo --run --auto-approve
```

---

## 18. Critical Implementation Rules

1. **Never import from `mcp_servers/` in `agents/`** — always go through `tools/mcp_client.py`
2. **Never call `anthropic.Anthropic()` directly** — always use `litellm.completion()`
3. **Never mutate `state` in-place** — return a partial dict update
4. **Workers must be async, supervisor must be sync**
5. **Every worker must catch all exceptions** — never let a worker raise
6. **Always strip JSON markdown fences** from LLM output before `json.loads()`
7. **DuckDB and ChromaDB connections must be module-level singletons**
8. **Never use `asyncio.run()` inside Streamlit** — use `graph.stream()` directly
9. **All ChromaDB metadata values must be strings** — never int, never list
10. **`graph.update_state()` must include `as_node="supervisor"`** for human approval
11. **Initial state must contain ALL keys from CJIState** — missing keys cause KeyError
12. **`data/` and `reports/` directories must be created in config.py at import time**
13. **tracker.js must be a single file with no external imports or build step**
14. **API keys must be generated with `secrets.token_hex(16)` — never random.randint**

---

## 19. Common Failure Modes

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError: events.parquet` | Not generated yet | `python main.py --mode demo --generate-data` |
| `DuckDB IO Error: lock` | Two processes writing same file | In PoC: collector uses same DUCKDB_PATH for writes, MCP reads only |
| `LiteLLM AuthenticationError` | Wrong or missing API key | Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env |
| `json.JSONDecodeError` on LLM output | LLM added markdown fences | Strip ```json``` before json.loads() |
| `LangGraph KeyError` on initial state | Missing state key | Use full initial_state template — all keys required |
| `supervisor loops forever` | iteration not incrementing | Verify supervisor always returns `"iteration": iteration + 1` |
| `ChromaDB ValueError: metadata type` | Non-string metadata value | Convert all metadata fields to str() |
| `graph.update_state` doesn't resume | Missing as_node parameter | Add `as_node="supervisor"` to update_state call |
| `asyncio.run() error in Streamlit` | Using async inside sync Streamlit | Use `graph.stream()` directly — it's a synchronous iterator |
| `MCP server dies immediately` | Import error in server | Test with `python mcp_servers/server.py` directly |
| `tracker.js CORS error` | Collector not allowing browser origin | Ensure CORS middleware is in collector with allow_origins=["*"] |
| `sendBeacon blocked` | Privacy browser extension | Expected in dev; fetch fallback handles it |
| `ChromaDB embedding pause` | sentence-transformers downloading | Expected on first run; ~90MB, wait 2 minutes |
| `collector 401 on valid key` | Key not in api_keys table | Run snippet_generator.py and ensure collector has started |
