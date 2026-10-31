> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Monorepo Structure
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** Repository Structure Reference

---

## Table of Contents

1. [Repository Overview](#1-repository-overview)
2. [Complete File Tree with Annotations](#2-complete-file-tree-with-annotations)
3. [Module-by-Module Specification](#3-module-by-module-specification)
4. [Dependency Graph](#4-dependency-graph)
5. [Import Rules and Boundaries](#5-import-rules-and-boundaries)
6. [Naming Conventions](#6-naming-conventions)
7. [File Templates](#7-file-templates)

---

## 1. Repository Overview

CJI is a single-repository Python project with a flat but purposeful structure. It is **not** a Python package (no `pyproject.toml` with package install); it is an application with relative imports and path manipulation in tests.

**Root directory:** `cji_agent/`

**Key design choices:**
- No subdirectory for each "service" — flat enough to be navigable but structured enough to separate concerns
- `mcp_servers/` is the analytical core — all four servers are siblings, not nested
- `agents/` is minimal — supervisor and workers only
- Runtime data (Parquet, DuckDB, ChromaDB, SQLite, reports) in directories created at startup
- Test files mirror source file names (`test_{source_file}.py`)

---

## 2. Complete File Tree with Annotations

```
cji_agent/                              ← Root application directory
│
├── config.py                           ← LAYER 0: All configuration (first file built)
├── state.py                            ← LAYER 0: CJIState TypedDict (second file built)
│
├── graph.py                            ← LAYER 5: LangGraph compilation
├── main.py                             ← LAYER 6: CLI entry point
├── dashboard.py                        ← LAYER 6: Streamlit web UI
│
├── agents/                             ← LAYER 4: Orchestration
│   ├── __init__.py                     ←   Empty
│   ├── supervisor.py                   ←   Routing supervisor (sync function)
│   └── workers.py                      ←   Four worker async functions
│
├── mcp_servers/                        ← LAYER 2-3: Analytical core
│   ├── __init__.py                     ←   Empty
│   ├── journey_data_server.py          ←   MCP 1: Data access (mode-aware)
│   ├── friction_engine_server.py       ←   MCP 2: Deterministic scoring
│   ├── insight_server.py               ←   MCP 3: LLM root cause analysis
│   └── report_server.py                ←   MCP 4: HTML report generation
│
├── collector/                          ← LAYER 1: Realtime event collection
│   ├── __init__.py                     ←   Empty
│   └── api.py                          ←   FastAPI app with all routes
│   └── models.py                       ←   Pydantic v2 validation schemas
│
├── tools/                              ← LAYER 1: Internal utilities
│   ├── __init__.py                     ←   Empty
│   ├── synthetic_data.py               ←   Demo mode event generator
│   └── mcp_client.py                   ←   MCP subprocess/session manager
│
├── tracker/                            ← LAYER 1: Browser-side collection
│   ├── tracker.js                      ←   Self-contained IIFE tracker script
│   └── snippet_generator.py            ←   Generates embed code + API keys
│
├── tests/                              ← LAYER 7: Test suite
│   ├── __init__.py                     ←   Empty
│   ├── test_friction_engine.py         ←   12+ unit tests (zero network)
│   ├── test_collector_models.py        ←   Pydantic validation tests
│   └── test_synthetic_data.py          ←   Generator output tests
│
├── requirements.txt                    ← Production dependencies (pinned)
├── requirements-dev.txt                ← Development-only dependencies
├── .env.example                        ← Environment variable template
├── .env                                ← GITIGNORED: actual secrets
├── .gitignore                          ← Excludes: .env, data/, reports/, __pycache__
├── README.md                           ← Setup, demo walkthrough, architecture summary
│
├── data/                               ← RUNTIME (auto-created, gitignored)
│   ├── events.parquet                  ←   Demo mode event data (~3MB)
│   ├── cji.duckdb                      ←   DuckDB database file
│   ├── cji_checkpoints.db              ←   LangGraph SQLite checkpoints
│   └── chroma/                         ←   ChromaDB persistence directory
│       └── cji_insights/               ←   Insight vector collection
│
└── reports/                            ← RUNTIME (auto-created, gitignored)
    └── cji_report_*.html               ←   Self-contained HTML analysis reports
```

---

## 3. Module-by-Module Specification

### 3.1 config.py

**Purpose:** Single source of truth for all configuration, paths, and thresholds.
**Layer:** 0 (no imports from project)
**Size target:** ~80 lines
**Import rule:** Every other module may import from config.py. config.py imports ONLY stdlib.

```python
"""
CJI Configuration Module
Reads from environment variables (.env loaded by python-dotenv).
Priority: system env > .env file > default values.
Creates data/ and reports/ directories on import.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file (before any os.getenv calls)
load_dotenv()

# ── OPERATION MODE ─────────────────────────────────────────────────────────
CJI_MODE: str = os.getenv("CJI_MODE", "demo").lower()
assert CJI_MODE in ("demo", "realtime"), f"CJI_MODE must be 'demo' or 'realtime', got: {CJI_MODE}"

# ── LLM CONFIGURATION ──────────────────────────────────────────────────────
LLM_MODEL:       str   = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.0"))
LLM_MAX_TOKENS:  int   = int(os.getenv("LLM_MAX_TOKENS", "2048"))

# ── API KEYS (never hardcode) ───────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY:    str = os.getenv("OPENAI_API_KEY", "")

# ── PATHS ───────────────────────────────────────────────────────────────────
ROOT:            Path = Path(__file__).parent
DATA_DIR:        Path = ROOT / "data"
EVENTS_PARQUET:  Path = DATA_DIR / "events.parquet"
DUCKDB_PATH:     Path = DATA_DIR / "cji.duckdb"
CHROMA_DIR:      Path = DATA_DIR / "chroma"
REPORTS_DIR:     Path = ROOT / "reports"

# Create directories on import (idempotent)
DATA_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── COLLECTOR ───────────────────────────────────────────────────────────────
COLLECTOR_HOST: str = os.getenv("COLLECTOR_HOST", "http://localhost")
COLLECTOR_PORT: int = int(os.getenv("COLLECTOR_PORT", "8000"))
CJI_ADMIN_KEY:  str = os.getenv("CJI_ADMIN_KEY", "change-me-in-production")

# ── AGENT BEHAVIOUR ─────────────────────────────────────────────────────────
MAX_AGENT_ITERATIONS:    int = int(os.getenv("MAX_AGENT_ITERATIONS", "20"))
FRICTION_SCORE_THRESHOLD: int = int(os.getenv("FRICTION_SCORE_THRESHOLD", "60"))

# ── REALTIME SETTINGS ───────────────────────────────────────────────────────
REALTIME_WINDOW_MINUTES:    int = int(os.getenv("REALTIME_WINDOW_MINUTES", "60"))
REALTIME_AUTO_RUN_INTERVAL: int = int(os.getenv("REALTIME_AUTO_RUN_INTERVAL", "0"))

# ── OBSERVABILITY ───────────────────────────────────────────────────────────
LANGCHAIN_TRACING_V2: str = os.getenv("LANGCHAIN_TRACING_V2", "false")
LANGCHAIN_API_KEY:    str = os.getenv("LANGCHAIN_API_KEY", "")
LANGCHAIN_PROJECT:    str = os.getenv("LANGCHAIN_PROJECT", "cji-poc")

# ── JOURNEY DEFINITION ──────────────────────────────────────────────────────
JOURNEY_CONFIG: dict = {
    "name":  os.getenv("JOURNEY_NAME", "onboarding"),
    "steps": [
        "landing_page",
        "sign_up_form",
        "email_verification",
        "profile_setup",
        "first_action",
        "completion",
    ],
}
```

---

### 3.2 state.py

**Purpose:** Defines CJIState TypedDict — the single shared state structure for the LangGraph graph.
**Layer:** 0 (no imports from project; imports only stdlib and langchain_core)
**Size target:** ~80 lines
**Import rule:** Imported by graph.py, agents/, workers. Never import state.py from MCP servers.

```python
"""
CJI Agent State Definition.
CJIState is the shared state for all LangGraph graph nodes.
All keys must be present in the initial_state dict passed to graph.stream().
"""

from __future__ import annotations
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ── Sub-types (for type hints in workers) ──────────────────────────────────

class JourneyEvent(TypedDict):
    event_id:    str
    user_id:     str
    journey_id:  str
    step_id:     str
    event_type:  str
    timestamp:   str
    duration_ms: int
    metadata:    str   # JSON string


class StepMetrics(TypedDict):
    step_id:            str
    unique_users:       int
    completion_rate_pct: float
    abandon_rate_pct:   float
    error_rate_pct:     float
    avg_dwell_ms:       int
    avg_rage_clicks:    float
    avg_retries:        float


class FrictionScore(TypedDict):
    step_id:        str
    score:          int         # 0–100
    drop_off_rate:  float
    avg_dwell_ms:   int
    retry_count:    float
    rage_click_rate: float
    signals:        list[str]
    confidence:     float
    is_critical:    bool


class Insight(TypedDict):
    insight_id:    str
    step_id:       str
    title:         str
    root_cause:    str
    category:      str     # "UX" | "data" | "system" | "process" | "unknown"
    evidence:      list[str]
    suggested_fix: str
    fix_effort:    str     # "low" | "medium" | "high"
    priority:      int     # 1–5
    priority_score: float
    score:         int


class WorkerStatus(TypedDict):
    worker:  str   # "data_worker" | "friction_worker" | "insight_worker" | "report_worker"
    status:  str   # "success" | "error"
    message: str   # human-readable summary


# ── Main State ──────────────────────────────────────────────────────────────

class CJIState(TypedDict):
    # IDENTITY (set once at init)
    mode:                 str          # "demo" | "realtime"
    journey_name:         str
    journey_steps:        list[str]

    # CONFIGURATION (set once at init)
    analysis_window_days: int
    analysis_window_mins: int
    collector_url:        str

    # ORCHESTRATION (modified by supervisor on every call)
    iteration:            int          # monotonically increasing
    next_worker:          str          # routing target
    human_approved:       bool         # approval gate flag
    last_run_at:          str          # ISO-8601 timestamp

    # COMMUNICATION (append-only via add_messages reducer)
    messages: Annotated[list[BaseMessage], add_messages]

    # DATA PHASE (written by data_worker)
    raw_events:           list[JourneyEvent]
    event_summary:        dict         # contains step_metrics, funnel, system_info
    live_event_count:     int          # realtime: total events in window

    # ANALYSIS PHASE (written by friction_worker)
    friction_scores:      list[FrictionScore]
    critical_steps:       list[str]

    # INSIGHT PHASE (written by insight_worker)
    insights:             list[Insight]
    prioritized_fixes:    list[dict]

    # DELIVERY PHASE (written by report_worker)
    report_path:          str
    narrative:            str

    # OPERATIONS (append-only by convention)
    worker_statuses:      list[WorkerStatus]
    errors:               list[str]
```

---

### 3.3 agents/supervisor.py

**Purpose:** Rule-based routing supervisor; determines next worker.
**Layer:** 4
**Sync/Async:** SYNCHRONOUS (not async) — LangGraph requirement for conditional edge functions
**Size target:** ~120 lines

**Key functions:**
- `supervisor(state: CJIState) -> dict` — main routing function
- `route(state: CJIState) -> str` — pure routing (reads state["next_worker"])
- `_llm_route(state: CJIState) -> str` — LLM fallback routing (private)

**Routing logic:**
```python
def supervisor(state: CJIState) -> dict:
    """Rule-based supervisor: determines next worker from state."""
    iteration = state.get("iteration", 0)

    # Safety cutoff
    if iteration >= MAX_AGENT_ITERATIONS:
        return {"next_worker": "END", "iteration": iteration + 1,
                "errors": state.get("errors", []) + [f"Safety cutoff at iteration {iteration}"]}

    # Rule-based routing (priority order)
    if not state.get("event_summary"):
        next_w = "data_worker"
    elif not state.get("friction_scores"):
        next_w = "friction_worker"
    elif not state.get("insights"):
        next_w = "insight_worker"
    elif state.get("insights") and not state.get("human_approved"):
        next_w = "END"   # Pause for human review
    elif state.get("human_approved") and not state.get("report_path"):
        next_w = "report_worker"
    elif state.get("report_path"):
        next_w = "END"   # Analysis complete
    else:
        next_w = _llm_route(state)  # Fallback only if deterministic rules fail

    return {"next_worker": next_w, "iteration": iteration + 1}


def route(state: CJIState) -> str:
    """Called by LangGraph to resolve conditional edges."""
    return state.get("next_worker", "END")
```

---

### 3.4 agents/workers.py

**Purpose:** Four specialised async worker functions that perform the actual analysis.
**Layer:** 4
**Sync/Async:** ALL ASYNC (not sync)
**Size target:** ~250 lines

**Worker functions:**
1. `async def data_worker(state: CJIState) -> dict`
2. `async def friction_worker(state: CJIState) -> dict`
3. `async def insight_worker(state: CJIState) -> dict`
4. `async def report_worker(state: CJIState) -> dict`

**Worker output keys (each worker writes ONLY these keys):**

| Worker | Output Keys |
|---|---|
| data_worker | event_summary, raw_events, live_event_count, next_worker, messages, worker_statuses |
| friction_worker | friction_scores, critical_steps, next_worker, messages, worker_statuses |
| insight_worker | insights, prioritized_fixes, next_worker, messages, worker_statuses |
| report_worker | report_path, narrative, next_worker, messages, worker_statuses |

**Error path output (all workers, on exception):**
```python
return {
    "errors":      state.get("errors", []) + [f"{worker_name}: {type(e).__name__}: {str(e)}"],
    "messages":    [AIMessage(content=f"[{worker_name}] Error: {e}")],
    "next_worker": "supervisor",  # ALWAYS present — graph must not hang
}
# Note: No output_key in error path — preserves good data from successful runs
```

---

### 3.5 graph.py

**Purpose:** Compiles the LangGraph StateGraph; provides `get_graph()` singleton.
**Layer:** 5
**Size target:** ~80 lines

```python
"""
CJI LangGraph Graph Compilation.
Call get_graph() to obtain the singleton compiled graph.
Call build_graph(use_persistence=True) to compile fresh (for testing).
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

from config import DUCKDB_PATH
from state import CJIState
from agents.supervisor import supervisor, route
from agents.workers import data_worker, friction_worker, insight_worker, report_worker

_graph = None   # module-level singleton

def build_graph(use_persistence: bool = True):
    """Build and compile the CJI LangGraph graph."""
    builder = StateGraph(CJIState)
    builder.add_node("supervisor",      supervisor)
    builder.add_node("data_worker",     data_worker)
    builder.add_node("friction_worker", friction_worker)
    builder.add_node("insight_worker",  insight_worker)
    builder.add_node("report_worker",   report_worker)
    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges("supervisor", route, {
        "data_worker":     "data_worker",
        "friction_worker": "friction_worker",
        "insight_worker":  "insight_worker",
        "report_worker":   "report_worker",
        "END":             END,
    })
    for worker in ["data_worker", "friction_worker", "insight_worker", "report_worker"]:
        builder.add_edge(worker, "supervisor")

    checkpoint_db = str(DUCKDB_PATH).replace(".duckdb", "_checkpoints.db")
    checkpointer = (SqliteSaver.from_conn_string(checkpoint_db)
                    if use_persistence else MemorySaver())
    return builder.compile(checkpointer=checkpointer, interrupt_before=["report_worker"])

def get_graph():
    """Return the singleton compiled graph (build on first call)."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
```

---

### 3.6 tools/mcp_client.py

**Purpose:** MCP subprocess/session manager. Provides `mcp_session()` context manager.
**Layer:** 3
**Size target:** ~80 lines

**Key functions:**
- `mcp_session(server_name: str) -> AsyncContextManager[ClientSession]`
- `call_tool(session, tool_name, arguments) -> dict | str`
- `SERVER_REGISTRY: dict[str, Path]` — maps server name to file path

```python
SERVER_REGISTRY = {
    "journey_data":    ROOT / "mcp_servers" / "journey_data_server.py",
    "friction_engine": ROOT / "mcp_servers" / "friction_engine_server.py",
    "insight":         ROOT / "mcp_servers" / "insight_server.py",
    "report":          ROOT / "mcp_servers" / "report_server.py",
}

@asynccontextmanager
async def mcp_session(server_name: str):
    """Async context manager that spawns a MCP server subprocess and yields a session."""
    script = SERVER_REGISTRY[server_name]
    params = StdioServerParameters(command=sys.executable, args=[str(script)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session
```

---

### 3.7 mcp_servers/friction_engine_server.py

**Purpose:** Stateless, pure-Python friction scoring MCP server.
**Layer:** 2
**Dependencies:** config only (no database, no LLM)
**Standalone test:** `python mcp_servers/friction_engine_server.py` must start without error

**Public functions exposed as MCP tools:**
- `score_friction(step_metrics: dict) -> dict`
- `score_all_steps(all_step_metrics: list) -> dict`
- `detect_dropoffs(funnel_data: list, threshold_pct: float) -> dict`
- `correlate_signals(scores: list) -> dict`

**Private functions (used internally + by test suite):**
- `_normalise(value: float, baseline: float) -> float`
- `_compute_score(step_metrics: dict) -> tuple[int, list[str], float]`

**Constants (exact values — tests depend on these):**
```python
WEIGHTS = {
    "abandon_rate_pct": 0.35,
    "error_rate_pct":   0.25,
    "avg_dwell_ms":     0.15,
    "avg_retries":      0.15,
    "avg_rage_clicks":  0.10,
}
BASELINES = {
    "abandon_rate_pct": 10.0,
    "error_rate_pct":   5.0,
    "avg_dwell_ms":     15000.0,
    "avg_retries":      0.1,
    "avg_rage_clicks":  0.05,
}
FRICTION_SCORE_THRESHOLD = 60   # from config, but also importable directly for tests
```

---

### 3.8 mcp_servers/journey_data_server.py

**Purpose:** Mode-aware data access MCP server.
**Layer:** 2
**Dependencies:** DuckDB, config

**Mode-specific private functions:**
- `_setup_views(conn)` — creates VIEW appropriate for current mode
- `_window_clause(days_back, minutes_back)` — returns mode-specific WHERE clause

**MCP tools exposed:**
- `get_system_info() -> dict`
- `get_funnel_steps() -> dict`
- `get_step_metrics(days_back: int, minutes_back: int) -> dict`
- `get_funnel_dropoff(days_back: int, minutes_back: int) -> dict`
- `query_events(step_id: str, event_type: str, limit: int) -> dict`
- `get_live_snapshot(minutes: int) -> dict`

---

### 3.9 mcp_servers/insight_server.py

**Purpose:** LLM root cause analysis + ChromaDB vector storage.
**Layer:** 3
**Dependencies:** LiteLLM, ChromaDB, config

**Module-level singletons:**
```python
_chroma_client = None
_collection    = None

def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection    = _chroma_client.get_or_create_collection(
            name="cji_insights",
            metadata={"hnsw:space": "cosine"}
        )
    return _collection
```

---

### 3.10 mcp_servers/report_server.py

**Purpose:** HTML report generation + LLM narrative.
**Layer:** 3
**Dependencies:** LiteLLM, config, file system

**HTML generation approach:** Python f-strings with embedded Chart.js JSON data.
No Jinja2 templates — keeps dependencies minimal.

---

### 3.11 collector/api.py

**Purpose:** FastAPI event collection server.
**Layer:** 1
**Entrypoint:** `uvicorn collector.api:app --host 0.0.0.0 --port 8000`

**Module-level state:**
```python
_conn = None   # DuckDB write connection (singleton)

def get_db():
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(DUCKDB_PATH))
        _create_tables(_conn)
    return _conn
```

**Route registration:**
```python
app = FastAPI(title="CJI Collector", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
app.get("/health")(health_check)
app.get("/tracker.js")(serve_tracker)
app.post("/collect/batch")(collect_batch)
app.get("/live/stats")(live_stats)
app.get("/live/feed")(live_feed)
app.post("/admin/api-keys")(create_api_key)
```

---

### 3.12 collector/models.py

**Purpose:** Pydantic v2 validation models for collector input.
**Layer:** 0.5 (no project imports)
**Dependencies:** pydantic v2 only

**Models:**
- `TrackerEvent` — single event with all validation
- `EventBatch` — list of events + api_key (1–100 events)
- `CollectResponse` — API response
- `HealthResponse` — health endpoint response
- `LiveStats` — per-step event counts

---

### 3.13 tools/synthetic_data.py

**Purpose:** Generates realistic synthetic journey events for demo mode.
**Layer:** 1
**Dependencies:** Faker, pandas, pyarrow, config

**Key public function:**
```python
def generate_demo_data(
    n_sessions: int = 2000,
    seed: int = 42,
    output_path: Path = EVENTS_PARQUET
) -> Path:
    """Generate synthetic journey events and save to Parquet. Returns output path."""
```

**Step friction profiles (must be exact for tests):**
```python
STEP_PROFILES = {
    "landing_page":       {"drop_rate": 0.15, "avg_dwell_s": 12,  "error_rate": 0.02},
    "sign_up_form":       {"drop_rate": 0.25, "avg_dwell_s": 45,  "error_rate": 0.18},
    "email_verification": {"drop_rate": 0.42, "avg_dwell_s": 180, "error_rate": 0.35},
    "profile_setup":      {"drop_rate": 0.20, "avg_dwell_s": 60,  "error_rate": 0.08},
    "first_action":       {"drop_rate": 0.12, "avg_dwell_s": 30,  "error_rate": 0.05},
    "completion":         {"drop_rate": 0.05, "avg_dwell_s": 10,  "error_rate": 0.01},
}
```

---

### 3.14 tracker/tracker.js

**Purpose:** Self-contained browser event tracker.
**Format:** Single IIFE file, vanilla ES5-compatible JavaScript, no dependencies.
**Size target:** < 10 KB unminified

**IIFE structure:**
```javascript
(function() {
    'use strict';

    // ── GUARD: require config ────────────────────────────────
    if (!window.CJI_CONFIG) { console.warn('[CJI] window.CJI_CONFIG not set.'); return; }

    // ── CONFIG ───────────────────────────────────────────────
    var API_KEY    = window.CJI_CONFIG.apiKey;
    var JOURNEY_ID = window.CJI_CONFIG.journeyId;
    var ENDPOINT   = window.CJI_CONFIG.endpoint;
    var STEP_MAP   = window.CJI_CONFIG.stepMap || {};

    // ── IDENTITY ─────────────────────────────────────────────
    // ── EVENT FACTORY ────────────────────────────────────────
    // ── STEP DETECTION ───────────────────────────────────────
    // ── RAGE CLICK DETECTION ─────────────────────────────────
    // ── EVENT CAPTURE LISTENERS ──────────────────────────────
    // ── SPA NAVIGATION HANDLING ──────────────────────────────
    // ── BATCHING AND SENDING ─────────────────────────────────
    // ── PUBLIC API ───────────────────────────────────────────
    window.CJITracker = { track: function(type, meta) { push(makeEvent(type, meta)); } };

})();
```

---

### 3.15 tracker/snippet_generator.py

**Purpose:** CLI tool to generate embed code + API key for a client.
**Layer:** 0.5 (stdlib only — no project imports needed)
**Entrypoint:** `python tracker/snippet_generator.py --journey X --host Y`

**Output files:**
- `{output}/embed_snippet.html` — copy-paste into website `<head>`
- `{output}/verify_tracker.py` — HTTP test script
- `{output}/useCJITracker.js` — React/Next.js useEffect hook
- `{output}/api_key.json` — key record: `{api_key, journey_id, host, created_at}`

---

### 3.16 main.py

**Purpose:** CLI entry point for all non-dashboard operations.
**Layer:** 6
**Size target:** ~150 lines

**Critical mode-setting rule:**
```python
# CJI_MODE MUST be set BEFORE importing graph or config
os.environ["CJI_MODE"] = args.mode
from graph import get_graph   # config is read at import time
```

---

### 3.17 dashboard.py

**Purpose:** Streamlit web UI.
**Layer:** 6
**Size target:** ~400 lines

**Critical async rule:**
```python
# NEVER use asyncio.run() — graph.stream() is synchronous
# CORRECT:
for event in graph.stream(initial_state, config=config, stream_mode="values"):
    st.session_state.state_snap = event

# INCORRECT (causes RuntimeError in Streamlit):
# asyncio.run(some_async_function())
```

---

## 4. Dependency Graph

### 4.1 Import Dependency Matrix

| Importer | config | state | mcp_client | friction_eng | journey_data | insight | report | supervisor | workers |
|---|---|---|---|---|---|---|---|---|---|
| config | — | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| state | ✗ | — | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| friction_engine | ✓ | ✗ | ✗ | — | ✗ | ✗ | ✗ | ✗ | ✗ |
| journey_data | ✓ | ✗ | ✗ | ✗ | — | ✗ | ✗ | ✗ | ✗ |
| insight | ✓ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ | ✗ |
| report | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | — | ✗ | ✗ |
| mcp_client | ✓ | ✗ | — | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| supervisor | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | — | ✗ |
| workers | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | — |
| graph | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ |
| main | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| dashboard | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| collector/api | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| collector/models | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

**Legend:** ✓ = imports, ✗ = must NOT import

---

## 5. Import Rules and Boundaries

### 5.1 Mandatory Rules

These rules are **non-negotiable**. Violations must be treated as bugs:

| Rule | Violation Example | Consequence |
|---|---|---|
| workers must not import from mcp_servers directly | `from mcp_servers.friction_engine_server import score_friction` | Bypasses MCP protocol, breaks production upgrade path |
| No direct anthropic.Anthropic() calls | `import anthropic; client = anthropic.Anthropic()` | Breaks provider agnosticism, breaks Ollama fallback |
| config.py imports only stdlib | `from langgraph.graph import StateGraph` in config.py | Creates circular imports, breaks module isolation |
| MCP servers must not import from agents/ | `from agents.supervisor import route` | Violates layer separation, creates circular imports |
| dashboard.py must not use asyncio.run() | `asyncio.run(data_worker(state))` | Crashes in Streamlit's event loop context |
| state.py imports only stdlib + langchain_core | `from config import CJI_MODE` in state.py | state.py must be importable without config |

### 5.2 Test Import Rules

All test files must have at the top:
```python
import sys
sys.path.insert(0, "..")  # or sys.path.insert(0, str(Path(__file__).parent.parent))
```

Test files must not import from `agents/` (these require LangGraph and LLM to be available):
- `test_friction_engine.py` → import from `mcp_servers.friction_engine_server` only
- `test_collector_models.py` → import from `collector.models` only
- `test_synthetic_data.py` → import from `tools.synthetic_data` only

---

## 6. Naming Conventions

### 6.1 Python

| Category | Convention | Example |
|---|---|---|
| Files | snake_case.py | `friction_engine_server.py` |
| Variables | snake_case | `friction_scores`, `step_metrics` |
| Constants (module-level) | UPPER_SNAKE_CASE | `FRICTION_SCORE_THRESHOLD`, `WEIGHTS` |
| Classes | PascalCase | `CJIState`, `TrackerEvent` |
| Private functions | _leading_underscore | `_normalise()`, `_setup_views()` |
| MCP tool functions | verb_noun | `score_friction()`, `generate_insight()` |
| Worker functions | {domain}_worker | `data_worker()`, `friction_worker()` |
| Type hints | fully qualified | `list[FrictionScore]`, `dict[str, int]` |
| Test functions | test_{description} | `test_zero_inputs_zero_score()` |

### 6.2 JavaScript (tracker.js)

| Category | Convention | Example |
|---|---|---|
| Variables | camelCase | `userId`, `sessionId`, `pageStart` |
| Functions | camelCase | `makeEvent()`, `sanitiseUrl()`, `getStepId()` |
| Constants | UPPER_SNAKE with var | `var BATCH_SIZE = 20` |
| Private state | descriptive camelCase | `rageBuffer`, `flushTimer` |

### 6.3 MCP Tool Names (Exact — Tests and Integration Depend on These)

```
Journey Data MCP:   get_system_info, get_funnel_steps, query_events,
                    get_step_metrics, get_funnel_dropoff, get_live_snapshot

Friction MCP:       score_friction, score_all_steps, detect_dropoffs,
                    correlate_signals

Insight MCP:        generate_insight, prioritise_fix, save_insight,
                    search_insights, rank_all_fixes

Report MCP:         generate_narrative, export_report
```

**These names are immutable.** Tests (`call_tool(session, "score_friction", ...)`) depend on exact spelling.

### 6.4 Signal Names (Exact — Tests Depend on These)

```python
SIGNAL_NAMES = [
    "high_drop_off",         # abandon > 30%
    "critical_drop_off",     # abandon > 50%
    "frequent_errors",       # error > 15%
    "extended_hesitation",   # dwell > 60,000ms
    "severe_confusion",      # dwell > 120,000ms
    "repeated_retries",      # retries > 1.0
    "rage_clicks_detected",  # rage_clicks > 0.5
]
```

---

## 7. File Templates

### 7.1 __init__.py Template

All `__init__.py` files are empty:
```python
# Empty — this package does not export symbols publicly
```

### 7.2 MCP Server Template

```python
"""
CJI [Domain] MCP Server.

Server name: cji-[domain]
Tools: [list of @mcp.tool functions]
"""

import json
import sys
from pathlib import Path

from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (REQUIRED_CONSTANTS)

# ── CONSTANTS ────────────────────────────────────────────────────────────────
CONSTANT_NAME: type = value

# ── MCP SERVER ───────────────────────────────────────────────────────────────
mcp = FastMCP(name="cji-[domain]", description="...")

# ── MODULE-LEVEL SINGLETON (if DB needed) ────────────────────────────────────
_resource = None

def _get_resource():
    global _resource
    if _resource is None:
        _resource = setup_resource()
    return _resource

# ── TOOL IMPLEMENTATIONS ─────────────────────────────────────────────────────
@mcp.tool(description="Verb-noun description.", annotations={"readOnlyHint": True})
def tool_name(param: str, optional: int = 0) -> dict:
    """One-line docstring."""
    # implementation
    return {"key": "value"}

# ── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 7.3 Worker Template

```python
async def domain_worker(state: CJIState) -> dict:
    """One-line docstring describing what this worker does."""
    worker_name = "domain_worker"
    try:
        # Step 1: Call MCP tools
        async with mcp_session("server_name") as session:
            result = await call_tool(session, "tool_name", {"param": "value"})

        # Step 2: Process results
        processed = transform(result)

        # Step 3: Return update dict (only keys this worker owns)
        return {
            "output_key":    processed,
            "next_worker":   "supervisor",
            "messages":      [AIMessage(content=f"[{worker_name}] ...")],
            "worker_statuses": state.get("worker_statuses", []) + [
                WorkerStatus(worker=worker_name, status="success", message="...")
            ],
        }
    except Exception as e:
        return {
            "errors":      state.get("errors", []) + [f"{worker_name}: {type(e).__name__}: {str(e)}"],
            "messages":    [AIMessage(content=f"[{worker_name}] Error: {e}")],
            "next_worker": "supervisor",  # ALWAYS present in error path
        }
```

### 7.4 Test File Template

```python
"""
Tests for mcp_servers/[server_name].py
All tests: zero network, zero API keys, zero DuckDB.
"""

import sys
from pathlib import Path
import pytest

# PATH: allow importing from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.friction_engine_server import (
    score_friction,
    FRICTION_SCORE_THRESHOLD,
    # ... others
)


# ── FIXTURES ─────────────────────────────────────────────────────────────────
@pytest.fixture
def low_step() -> dict:
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
    return {
        "step_id":           "email_verification",
        "unique_users":      732,
        "abandon_rate_pct":  41.8,
        "error_rate_pct":    34.7,
        "avg_dwell_ms":      184000,
        "avg_retries":       1.8,
        "avg_rage_clicks":   0.62,
    }


# ── TESTS ────────────────────────────────────────────────────────────────────
def test_something(low_step: dict) -> None:
    """Test description."""
    result = score_friction(low_step)
    assert ...
```
