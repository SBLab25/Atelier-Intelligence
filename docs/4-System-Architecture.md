> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# System Architecture
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** Technical Architecture Reference

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Design Principles](#2-design-principles)
3. [High-Level System Architecture](#3-high-level-system-architecture)
4. [Layer Architecture](#4-layer-architecture)
5. [Dual-Mode Architecture Pattern](#5-dual-mode-architecture-pattern)
6. [Component Architecture](#6-component-architecture)
7. [Process Architecture](#7-process-architecture)
8. [Tracker and Collector Architecture](#8-tracker-and-collector-architecture)
9. [MCP Architecture](#9-mcp-architecture)
10. [Agent Architecture](#10-agent-architecture)
11. [Communication Patterns](#11-communication-patterns)
12. [State Machine Specification](#12-state-machine-specification)
13. [Security Architecture](#13-security-architecture)
14. [PoC Deployment Architecture](#14-poc-deployment-architecture)
15. [Production Architecture (Phase 3+)](#15-production-architecture-phase-3)
16. [Architecture Decision Records](#16-architecture-decision-records)

---

## 1. Architecture Overview

CJI is a **multi-layer, agentic intelligence system** with a dual-mode data collection architecture. It is built around four converging patterns:

### 1.1 The Four Architectural Patterns

**Pattern 1 — Browser-to-Backend Event Pipeline (Realtime Mode)**
A lightweight JavaScript tracker (`tracker.js`) collects raw user behaviour events from client websites and delivers them to a FastAPI collector that writes to DuckDB in real time. This mirrors how GA4 and Hotjar work but is purpose-built for the CJI schema.

**Pattern 2 — Synthetic Data Layer (Demo Mode)**
A Faker-based generator produces statistically realistic journey event data stored as Parquet files, queryable via DuckDB. This layer has identical output schema to the realtime layer, making the rest of the system completely oblivious to which mode it is in.

**Pattern 3 — MCP Micro-Server Architecture**
Business logic is encapsulated in four independent MCP (Model Context Protocol) servers. Each server exposes typed tool interfaces via JSON-RPC over stdio. Agents, humans, or any MCP-compatible client can call these tools interchangeably. The Journey Data MCP is the only mode-aware server; the other three are completely agnostic.

**Pattern 4 — LangGraph Supervisor-Worker Orchestration**
A rule-based supervisor agent routes between four specialised worker agents. Workers call MCP tools, update shared typed state, and return control to the supervisor. The graph checkpoints state to SQLite, enabling pause-and-resume for the human-in-loop review gate.

### 1.2 The Central Architectural Principle

> The mode boundary is drawn at the Journey Data MCP. Everything above it is mode-specific. Everything below it is mode-agnostic.

Changing data sources requires modifying exactly one file (`mcp_servers/journey_data_server.py`). The friction engine, insight generation, report production, and all agent logic never change.

---

## 2. Design Principles

| Principle | Statement | Implication |
|---|---|---|
| P1 — Hard Mode Boundary | Only the Journey Data MCP knows where data comes from | All downstream components treat data as normalised step metrics regardless of source |
| P2 — Provider Agnosticism | No production code imports `anthropic` directly | All LLM calls go through LiteLLM; changing provider = changing one env var |
| P3 — Independently Testable MCP Servers | Each MCP server can be run standalone and tested without other components | Friction Engine MCP is testable with zero external dependencies |
| P4 — Fail Gracefully, Never Silently | Every worker catches all exceptions and writes to state["errors"] | Graph never crashes — reaches END with partial results if something fails |
| P5 — Configuration Over Code | Journey steps, scoring weights, thresholds, LLM model — all in config | Switching clients or modes requires zero code changes |
| P6 — Observable by Default | LangSmith traces enabled by default; collector has health/stats endpoints | Every state transition is logged and inspectable |
| P7 — Browser-First Data Collection | tracker.js is a single self-contained file with no build step | Zero-friction client adoption — paste one snippet, done |
| P8 — Incremental Complexity | stdio → HTTP MCP, DuckDB → PostgreSQL, ChromaDB → pgvector each isolated | Each upgrade is a targeted swap with no architectural rethinking |

---

## 3. High-Level System Architecture

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        DEMO MODE DATA LAYER                              ║
║  ┌──────────────────────────────────┐                                    ║
║  │  synthetic_data.py (Faker)       │ → events.parquet                   ║
║  │  python main.py --generate-data  │                                    ║
║  └──────────────────────────────────┘                                    ║
╚══════════════════════════════════════════════════════════════════════════╝
           │ (demo: reads Parquet)
╔══════════════════════════════════════════════════════════════════════════╗
║                     REALTIME MODE DATA LAYER                             ║
║  Client Website                                                           ║
║  ┌────────────────────────┐                                               ║
║  │  <head>                │                                               ║
║  │    window.CJI_CONFIG   │                                               ║
║  │    <script tracker.js> │ ──[POST /collect/batch]──►                   ║
║  └────────────────────────┘                                               ║
║                           ┌─────────────────────────┐                    ║
║                           │  Collector API (FastAPI) │ → live_events      ║
║                           │  uvicorn port 8000       │   (DuckDB table)  ║
║                           └─────────────────────────┘                    ║
╚══════════════════════════════════════════════════════════════════════════╝
           │ (realtime: reads live_events table)
╔══════════════════════════════════════════════════════════════════════════╗
║                    MODE BOUNDARY — Journey Data MCP                       ║
║  ┌────────────────────────────────────────────────────────────────────┐  ║
║  │  MCP Server 1: Journey Data (mode-aware)                           │  ║
║  │  Tools: get_funnel_steps, get_step_metrics, get_funnel_dropoff,    │  ║
║  │         query_events, get_live_snapshot, get_system_info           │  ║
║  └────────────────────────────────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════════╝
                     │
╔═════════════════════════════════════════════════════════════╗
║           MODE-AGNOSTIC ANALYTICAL LAYER (BOTH MODES)       ║
║                                                              ║
║  MCP Server 2: Friction Engine                               ║
║  Tools: score_friction, score_all_steps,                     ║
║         detect_dropoffs, correlate_signals                   ║
║                     │                                        ║
║  MCP Server 3: Insight & LLM                                 ║
║  Tools: generate_insight, prioritise_fix,                    ║
║         save_insight, search_insights, rank_all_fixes        ║
║                     │                                        ║
║  MCP Server 4: Report & Viz                                  ║
║  Tools: generate_narrative, export_report                    ║
╚═════════════════════════════════════════════════════════════╝
                     │
╔═════════════════════════════════════════════════════════════╗
║           LANGGRAPH AGENT LAYER (MODE-AGNOSTIC)              ║
║                                                              ║
║   START → [Supervisor] ──► [Data Worker]     ──► [Supervisor]║
║                        ──► [Friction Worker] ──► [Supervisor]║
║                        ──► [Insight Worker]  ──► [Supervisor]║
║               ⏸ [HUMAN CHECKPOINT]                          ║
║                        ──► [Report Worker]   ──► END         ║
║                                                              ║
║   State: CJIState TypedDict (SQLite checkpoints)             ║
╚═════════════════════════════════════════════════════════════╝
                     │
╔═════════════════════════════════════════════════════════════╗
║              PRESENTATION LAYER                              ║
║                                                              ║
║   Streamlit Dashboard     CLI (main.py)     HTML Report      ║
║   (mode toggle, charts,   (--mode flag,     (self-contained, ║
║    approval gate,          checkpoints,      Chart.js charts,║
║    live feed)              thread IDs)       downloadable)   ║
╚═════════════════════════════════════════════════════════════╝
```

---

## 4. Layer Architecture

### Layer 1: Presentation Layer

**Components:** `dashboard.py`, `main.py`, HTML reports in `reports/`

**Responsibilities:**
- User interface for triggering analysis, reviewing findings, approving reports
- Mode toggle that restarts session state and updates `os.environ["CJI_MODE"]`
- Real-time event feed (realtime mode) showing latest tracker.js events
- Collector API status indicator (realtime mode)
- Download button for generated HTML reports

**Hard Constraints:**
- No business logic — pure presentation and flow control
- Never calls MCP servers directly
- Never accesses DuckDB directly
- Never uses asyncio.run() — uses graph.stream() which is synchronous
- All data comes from LangGraph state snapshots via `graph.get_state()`

---

### Layer 2: Orchestration Layer (LangGraph)

**Components:** `graph.py`, `agents/supervisor.py`, `agents/workers.py`

**Responsibilities:**
- Route analysis workflow through directed state graph
- Persist state to SQLite between pause and resume
- Human-in-loop checkpoint before report generation
- Collect and aggregate all worker outputs into shared state

**Hard Constraints:**
- Supervisor must be a sync function (LangGraph requirement)
- Workers must be async functions
- Workers never call each other directly — only through state blackboard
- Workers only write to state via return dict (never mutation)
- Workers always return `next_worker="supervisor"`

---

### Layer 3: Protocol Layer (MCP)

**Components:** `tools/mcp_client.py`, all four MCP server files

**Responsibilities:**
- Spawn MCP server subprocesses and manage their lifecycle
- JSON-RPC serialisation/deserialisation
- Route tool calls to correct MCP server

**Hard Constraints:**
- Workers may not import from `mcp_servers/` directly — must go through `mcp_client.py`
- Each `mcp_session()` context manager creates a fresh subprocess
- MCP sessions must not be reused across worker invocations

---

### Layer 4: Business Logic Layer (MCP Servers)

**Components:** Four MCP server files

**Responsibilities:**
- Domain-specific analytical logic
- Data store access (Journey Data MCP only)
- LLM calls (Insight and Report MCPs)
- Report file generation (Report MCP)

**Hard Constraints:**
- Each server owns one domain — never imports from another MCP server
- Must be independently runnable: `python mcp_servers/server.py` must start a valid MCP server
- Must expose all functionality as `@mcp.tool` decorated functions

---

### Layer 5: Data Collection Layer

**Components:** `tracker/tracker.js`, `collector/api.py`, `tools/synthetic_data.py`

**Responsibilities:**
- Realtime: capture browser events and deliver to collector
- Realtime: receive, validate, and persist events to DuckDB
- Demo: generate statistically realistic synthetic events and write to Parquet

**Hard Constraints:**
- tracker.js must be a single file with no external dependencies (IIFE pattern)
- Collector API must validate API key before any write operation
- Synthetic data must match the exact unified event schema

---

### Layer 6: Infrastructure Layer

**Components:** DuckDB, ChromaDB, SQLite, LiteLLM, file system

**Responsibilities:**
- Persist events (Parquet + DuckDB), insights (ChromaDB), state (SQLite), reports (HTML files)
- Abstract LLM provider via LiteLLM

---

## 5. Dual-Mode Architecture Pattern

### 5.1 Mode Selection Flow

```
.env file: CJI_MODE=demo|realtime
    │
    ▼
config.py: reads CJI_MODE, sets all mode-specific settings
    │
    ▼
journey_data_server.py: _setup_views() branches on CJI_MODE
    │
    ├── demo:     CREATE VIEW events AS SELECT * FROM read_parquet(events.parquet)
    └── realtime: CREATE TABLE IF NOT EXISTS live_events (...)
                  CREATE VIEW events AS SELECT * FROM live_events
    │
    ▼
All other components: use the "events" VIEW — never know which mode
```

### 5.2 What Changes Per Mode

**Demo mode only:**
- `tools/synthetic_data.py` runs to generate `data/events.parquet`
- Journey Data MCP creates a VIEW over Parquet
- Time window = days (analysis_window_days)
- CLI: `--generate-data` flag is meaningful
- `--days N` controls query window

**Realtime mode only:**
- `tracker/tracker.js` embedded on client website sends events
- `collector/api.py` receives and stores events in `live_events` table
- Journey Data MCP reads from `live_events` table
- Time window = minutes (analysis_window_mins / REALTIME_WINDOW_MINUTES)
- Additional tool: `get_live_snapshot()` for rolling counts
- Collector API must be running during analysis
- Dashboard shows live event feed and collector status
- CLI: `--window-mins` flag is meaningful

**Both modes — identical:**
- Friction Engine MCP server
- Insight MCP server
- Report MCP server
- `agents/supervisor.py`
- `agents/workers.py` (data_worker passes different time params; logic identical)
- `graph.py`
- `state.py`
- `tools/mcp_client.py`

### 5.3 Data Source Abstraction

The "events" DuckDB VIEW is the abstraction boundary. Both sources produce rows matching:

```sql
event_id VARCHAR, user_id VARCHAR, journey_id VARCHAR, step_id VARCHAR,
event_type VARCHAR, timestamp TIMESTAMPTZ, duration_ms BIGINT, metadata VARCHAR
```

The `get_step_metrics()` SQL query is identical in both modes — it runs against the same VIEW name, uses the same aggregation logic, produces the same column schema. Only the WHERE clause differs (days vs minutes).

---

## 6. Component Architecture

### 6.1 Component Dependency Graph

```
dashboard.py ────────────────────► graph.py
main.py ─────────────────────────► graph.py
graph.py ────────────────────────► agents/supervisor.py
graph.py ────────────────────────► agents/workers.py
graph.py ────────────────────────► state.py
graph.py ────────────────────────► config.py
agents/supervisor.py ────────────► state.py, config.py, litellm
agents/workers.py ───────────────► tools/mcp_client.py, state.py, config.py
tools/mcp_client.py ─────────────► mcp SDK
collector/api.py ────────────────► collector/models.py, duckdb, config.py, fastapi
collector/models.py ─────────────► pydantic
mcp_servers/journey_data.py ─────► duckdb, config.py, fastmcp
mcp_servers/friction_engine.py ──► config.py, fastmcp
mcp_servers/insight.py ──────────► chromadb, litellm, config.py, fastmcp
mcp_servers/report.py ───────────► litellm, config.py, fastmcp
tools/synthetic_data.py ─────────► faker, pandas, config.py
tracker/snippet_generator.py ────► stdlib only
tracker/tracker.js ──────────────► (no dependencies)
```

**Critical rule:** No arrow from `agents/*` directly to `mcp_servers/*`. The only path is through `tools/mcp_client.py`.

---

## 7. Process Architecture

### 7.1 PoC Process Model

```
Process 1: main.py / dashboard.py (Python host process)
│  ├── LangGraph graph (in-process threads)
│  ├── DuckDB read connection (in-process, READ ONLY)
│  └── ChromaDB client (in-process, read for dashboard)
│
├── Spawns (per worker call): Process 2: mcp_servers/journey_data_server.py
│   └── DuckDB read connection (separate process, READ ONLY)
│
├── Spawns (per worker call): Process 3: mcp_servers/friction_engine_server.py
│   └── (no database connections — pure computation)
│
├── Spawns (per worker call): Process 4: mcp_servers/insight_server.py
│   ├── ChromaDB write connection
│   └── LiteLLM → external LLM API
│
└── Spawns (per worker call): Process 5: mcp_servers/report_server.py
    └── LiteLLM → external LLM API

Process 6 (realtime mode only): uvicorn collector.api:app
    └── DuckDB WRITE connection (live_events INSERT)
```

### 7.2 DuckDB Access Pattern

```
┌─────────────────────────────────────────┐
│             data/cji.duckdb             │
│                                         │
│  Writer: Collector API (Process 6)      │
│  └── INSERT INTO live_events            │
│                                         │
│  Reader: Journey Data MCP (Process 2)   │
│  └── SELECT FROM events VIEW            │
│                                         │
│  DuckDB supports one writer + N readers │
│  This is safe in PoC: no write conflict │
└─────────────────────────────────────────┘
```

---

## 8. Tracker and Collector Architecture

### 8.1 tracker.js Internal Architecture

```
window.CJI_CONFIG
      │
      ▼
Identity Layer
  - userId: UUID from localStorage (persists across sessions)
  - sessionId: UUID (new per tab)
  - Fallback: in-memory UUID if localStorage unavailable (private browsing)
      │
      ▼
Step Detection Layer
  - getStepId(): matches window.location.pathname against stepMap
  - Updates currentStep on SPA navigation
      │
      ▼
Event Capture Layer
  - DOMContentLoaded → page_view
  - document click → click + rage_click check
  - form submit → form_submit
  - input invalid → error (VALIDATION_FAIL)
  - window.onerror → error (JS_ERROR)
  - unhandledrejection → error (PROMISE_REJECTION)
  - beforeunload → abandon (dwell_ms computed)
  - history.pushState / popstate → step_complete + page_view
      │
      ▼
Batching Layer
  - queue: TrackerEvent[]
  - flushTimer: setTimeout(5000)  [5 second flush]
  - MAX_BATCH = 20                [size-based flush]
  - flush(useBeacon): POST to ENDPOINT/batch
      │
      ▼
Delivery Layer
  - fetch() with keepalive: true (primary)
  - sendBeacon() fallback for beforeunload (survive tab close)
```

### 8.2 Collector API Event Processing Pipeline

```
POST /collect/batch
      │
      ▼
1. API key validation (DuckDB api_keys lookup)
   ├── Found + active: continue
   └── Not found or inactive: return 401, discard all events
      │
      ▼
2. Pydantic EventBatch validation
   - event_type in allowed set
   - timestamp valid ISO-8601
   - url query params stripped
   - id fields min length 8
   - batch size ≤ 100
      │
      ▼
3. Background task scheduled (FastAPI BackgroundTasks)
      │
      ▼
4. Response returned immediately (< 100ms)
      │ (background continues)
      ▼
5. write_events(): INSERT OR IGNORE per event
   - accepted count
   - rejected count (per-event try/except)
   - errors list
      │
      ▼
6. Events available in live_events table
   → Journey Data MCP queries them on next analysis run
```

### 8.3 Snippet Generator Architecture

```
snippet_generator.py --journey X --host Y --output DIR
      │
      ▼
1. secrets.token_hex(16) → api_key = "cji_live_{32 hex chars}"
2. IMPORTANT: API key must be inserted into collector's api_keys table
   (Done by collector's _create_tables() for dev key;
    production key via POST /admin/api-keys or manual INSERT)
      │
      ▼
3. Generate 4 output files:
   ├── embed_snippet.html  (window.CJI_CONFIG + script tag)
   │     window.CJI_CONFIG = {
   │       apiKey: "cji_live_...",
   │       journeyId: "onboarding",
   │       endpoint: "http://host/collect",
   │       stepMap: {"/": "landing_page", ...}
   │     }
   ├── verify_tracker.py   (HTTP test script)
   ├── useCJITracker.js    (React/Next.js hook)
   └── api_key.json        (key record for safekeeping)
```

---

## 9. MCP Architecture

### 9.1 MCP Protocol Stack

```
Application Layer:  @mcp.tool() decorated Python functions
                    ↕ FastMCP wraps to JSON schema
Protocol Layer:     MCP SDK (ClientSession / ServerSession)
                    ↕ JSON-RPC 2.0 messages
Transport Layer:    stdio (subprocess pipes) — PoC
                    Streamable HTTP — Production (Phase 3)
```

### 9.2 MCP JSON-RPC Message Flow

```
1. HANDSHAKE (once per mcp_session context):
   Agent → Server: {"method": "initialize", "params": {"protocolVersion": "2024-11-05"}}
   Server → Agent: {"result": {"tools": [{"name": "score_friction", "inputSchema": {...}}]}}

2. TOOL CALL (per agent action):
   Agent → Server: {"method": "tools/call", "params": {"name": "score_friction", "arguments": {...}}}
   Server → Agent: {"result": {"content": [{"type": "text", "text": "{\"score\": 87, ...}"}]}}

3. CLEANUP (on context manager exit):
   mcp_session().__aexit__ → subprocess.terminate()
```

### 9.3 FastMCP Server Pattern

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

### 9.4 Mode-Aware MCP Design

Only one MCP server (Journey Data) is mode-aware. The mode awareness is contained in exactly two functions:

1. `_setup_views()` — creates different VIEW depending on `CJI_MODE`
2. `_window_clause()` — returns days-based or minutes-based WHERE clause

```python
def _setup_views(conn):
    if CJI_MODE == "demo":
        conn.execute(f"""CREATE OR REPLACE VIEW events AS
            SELECT ... FROM read_parquet('{EVENTS_PARQUET}')""")
    else:  # realtime
        conn.execute("CREATE TABLE IF NOT EXISTS live_events (...)")
        conn.execute("CREATE OR REPLACE VIEW events AS SELECT ... FROM live_events")

def _window_clause(days_back=30, minutes_back=0):
    if CJI_MODE == "demo":
        return f"timestamp >= NOW() - INTERVAL '{days_back} days'"
    else:
        mins = minutes_back or REALTIME_WINDOW_MINUTES
        return f"timestamp >= NOW() - INTERVAL '{mins} minutes'"
```

---

## 10. Agent Architecture

### 10.1 Supervisor Decision Architecture

```
Input: CJIState
      │
      ├── iteration ≥ 20 ──────────────────────────────────► END (safety)
      │
      ├── not state["event_summary"] ──────────────────────► data_worker
      │
      ├── not state["friction_scores"] ────────────────────► friction_worker
      │
      ├── not state["insights"] ───────────────────────────► insight_worker
      │
      ├── state["insights"] AND NOT human_approved ────────► END (pause)
      │   (graph checkpoints here; interrupt_before fires)
      │
      ├── human_approved AND NOT state["report_path"] ─────► report_worker
      │
      ├── state["report_path"] ────────────────────────────► END (complete)
      │
      └── (none match) ────────────────────────────────────► LLM fallback
Output: {next_worker: str, iteration: n+1}
```

### 10.2 Worker Communication via Shared State (Blackboard Pattern)

```
data_worker:
  reads:  analysis_window_days (or analysis_window_mins in realtime)
  writes: event_summary, journey_steps, live_event_count

friction_worker:
  reads:  event_summary["step_metrics"]
  writes: friction_scores, critical_steps

insight_worker:
  reads:  friction_scores, critical_steps, event_summary["step_metrics"]
  writes: insights, prioritized_fixes

report_worker:
  reads:  insights/prioritized_fixes, friction_scores, event_summary["funnel"], journey_name, mode
  writes: report_path, narrative
```

Workers never call each other. They communicate only through the CJIState blackboard.

### 10.3 Agent Graph Topology

```
START
  │
  ▼
[supervisor] ──(data_worker)──► [data_worker] ──────────────────► [supervisor]
             ──(friction_worker)► [friction_worker] ──────────► [supervisor]
             ──(insight_worker)─► [insight_worker] ──────────► [supervisor]
             ──(END / pause)────► checkpoint saved, iteration stops
             ──(report_worker)──► [report_worker] ──────────► [supervisor]
             ──(END / complete)─► graph terminates
```

### 10.4 Graph Compilation

```python
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

---

## 11. Communication Patterns

### 11.1 tracker.js → Collector (HTTP)

```
Browser → POST {host}/collect/batch
          Headers: Content-Type: application/json, X-CJI-Key: {api_key}
          Body:    {api_key: str, events: TrackerEvent[]}

          On success: 200 {accepted: n, rejected: 0}
          On invalid key: 401
          On bad schema: 422 (individual events rejected, others accepted)

          Fallback: navigator.sendBeacon({host}/collect/batch, Blob)
          (Used on page unload for abandon events)
```

### 11.2 Worker → MCP Server (stdio JSON-RPC)

```python
async with mcp_session("server_name") as session:
    result = await call_tool(session, "tool_name", {"arg": value})

# Internally:
# 1. subprocess.Popen([sys.executable, "mcp_servers/server.py"])
# 2. stdio_client(StdioServerParameters) → (read, write) pipes
# 3. ClientSession(read, write).initialize()
# 4. session.call_tool("tool_name", arguments) → JSON-RPC call
# 5. result.content[0].text → json.loads() → Python dict
# 6. Context exit → process.terminate()
```

### 11.3 Dashboard → Collector (HTTP, realtime mode only)

```python
requests.get(f"{COLLECTOR_HOST}/live/stats", headers={"x-cji-key": KEY})
requests.get(f"{COLLECTOR_HOST}/health")
# synchronous, timeout=2-3 seconds
```

### 11.4 Supervisor → LLM (LiteLLM, fallback only)

```python
supervisor._llm_route()
  → litellm.completion(model=LLM_MODEL, messages=[...])
  → response.choices[0].message.content.strip()
  → sanitised against VALID_NEXT set
```

### 11.5 Insight/Report MCP → LLM

```python
litellm.completion(
    model=LLM_MODEL,
    temperature=LLM_TEMPERATURE,
    max_tokens=LLM_MAX_TOKENS,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ],
)
```

---

## 12. State Machine Specification

### 12.1 Full Graph State Diagram

```
┌─────────┐
│  START  │
└────┬────┘
     │ initial CJIState (all keys set)
     ▼
┌──────────────────────────────┐
│         SUPERVISOR           │ ◄──────────────────────────────────────┐
└──────────────┬───────────────┘                                         │
               │                                                          │
    ┌──────────┼──────────────────────────────────────────────┐          │
    │          │          │                   │                │          │
    ▼          ▼          ▼                   ▼                ▼          │
[data_worker][friction][insight]          [END:pause]   [report_worker]  │
    │          │          │               ⏸checkpoint        │           │
    └──────────┴──────────┴───────────────────────────────────┘          │
                                                               │          │
                                                     [END:complete]      │
                                                                          │
                                         [HUMAN: graph.update_state()]──►│
```

### 12.2 Checkpoint Semantics

Every node execution produces a checkpoint. On process crash + restart:
- Same `thread_id` → `graph.stream(None, config)` resumes from last checkpoint
- Human approval: graph checkpoints state, returns control, human approves via `update_state()`, `graph.stream(None)` resumes from checkpoint

### 12.3 Human-in-Loop Resume Pattern

```python
# PAUSE occurs automatically when supervisor routes to "report_worker"
# because of interrupt_before=["report_worker"]

# Check state after pause:
snapshot = graph.get_state(config)
# snapshot.next == ("report_worker",) means paused at approval gate

# Update and resume (MUST include as_node="supervisor"):
graph.update_state(config, {"human_approved": True}, as_node="supervisor")
for event in graph.stream(None, config=config, stream_mode="values"):
    pass  # report_worker now runs
```

---

## 13. Security Architecture

### 13.1 API Key Flow

```
snippet_generator.py
  → secrets.token_hex(16) → "cji_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  → Stored in api_key.json (client keeps safe)
  → Must be inserted into DuckDB api_keys table before use

tracker.js (browser)
  → Includes api_key in POST body AND X-CJI-Key header

collector/api.py
  → validate_api_key(api_key): SELECT from api_keys WHERE api_key=? AND active=TRUE
  → 401 if not found or inactive
  → All event data discarded if key invalid
```

### 13.2 Data Privacy Controls in tracker.js

```javascript
// URL sanitisation (mandatory):
function sanitiseUrl(url) {
    var parsed = new URL(url);
    return parsed.protocol + '//' + parsed.host + parsed.pathname;
    // Strips: ?query=params, #fragments — no PII in URL storage
}

// Anonymous identity:
userId = localStorage.getItem('_cji_uid') || genId()
// UUID only, no email/name/phone ever stored

// Metadata caps:
error_message: String(msg).slice(0, 200)   // cap error message length
text_preview: el.innerText.slice(0, 50)    // cap click text capture
```

### 13.3 LLM Prompt Privacy

Insight and narrative prompts contain ONLY:
- Aggregated numeric metrics (abandon rate %, error rate %, dwell time averages)
- Signal names (strings)
- Step IDs (non-identifying strings)

Raw event data, URLs, user IDs, and metadata are **NEVER** sent to the LLM.

---

## 14. PoC Deployment Architecture

```
Developer Machine (local)
│
├── Python virtualenv
│   └── All pip dependencies installed
│
├── Process A: Streamlit dashboard OR Python main.py
│   ├── LangGraph (in-process)
│   ├── DuckDB read connection (in-process)
│   └── Spawns MCP server subprocesses (transient, stdio)
│
├── Process B: uvicorn collector.api:app (realtime mode only)
│   └── DuckDB write connection (live_events INSERT)
│
├── data/
│   ├── events.parquet          (demo mode)
│   ├── cji.duckdb              (shared: demo VIEW + realtime live_events)
│   ├── cji_checkpoints.db      (LangGraph state)
│   └── chroma/                 (ChromaDB)
│
├── reports/
│   └── cji_report_*.html
│
└── External API calls
    └── LLM API (Anthropic/OpenAI) or local Ollama
```

**Hardware minimum:**
- CPU: 2+ cores
- RAM: 4 GB (ChromaDB + sentence-transformers + Streamlit)
- Storage: 500 MB (dependencies + models)
- Network: Required for LLM API; optional with Ollama

---

## 15. Production Architecture (Phase 3+)

### 15.1 Microservices Topology

```
Internet
    │
    ▼
[CDN / Load Balancer]
    │
    ├──► tracker.js served from CDN
    │
    ├──► [Next.js Frontend] ─── auth (Auth0/NextAuth)
    │
    └──► [API Gateway] (Kong / AWS API GW)
              │
              ├──► [Collector Service] (FastAPI, horizontal scaling)
              │         └──► PostgreSQL (TimescaleDB for time-series events)
              │
              ├──► [CJI API Service] (FastAPI, graph trigger)
              │         └──► [LangGraph API Server]
              │                   └──► Redis (checkpoint store)
              │
              └──► [MCP Gateway] (HTTP Streamable MCP)
                        ├──► [Journey Data MCP Service] → PostgreSQL
                        ├──► [Friction Engine MCP Service] → stateless
                        ├──► [Insight MCP Service] → PostgreSQL + pgvector
                        └──► [Report MCP Service] → S3/GCS
```

### 15.2 PoC-to-Production Upgrade Map

| PoC Component | Production Replacement | Reason |
|---|---|---|
| stdio MCP transport | Streamable HTTP MCP | Remote servers, multi-client, auth |
| DuckDB + Parquet | PostgreSQL + TimescaleDB | ACID, multi-tenant, streaming |
| ChromaDB | pgvector extension | Single DB, no extra service |
| SQLite checkpoints | Redis | Distributed, HA, TTL cleanup |
| Streamlit | Next.js + Recharts | Production UI, auth, multi-user |
| Local file reports | S3/GCS presigned URLs | Shareable, access-controlled |
| Single process | Docker containers (K8s) | Scalability, rolling deploys |
| LiteLLM direct | LiteLLM Proxy server | Rate limiting, key rotation |
| Open CORS | Domain allowlist | Security |

---

## 16. Architecture Decision Records

### ADR-001: Dual-Mode Architecture with Hard Boundary at Journey Data MCP

**Status:** Accepted
**Context:** Need both a demo mode (no live site required) and a realtime mode (live tracker.js data).
**Decision:** Draw the mode boundary at the Journey Data MCP. Only this MCP is mode-aware. All downstream components are mode-agnostic.
**Rationale:** Minimises code changes when switching modes. All analytical logic — scoring, insight generation, reporting, agent orchestration — is written once and works for both modes.
**Consequences:** Journey Data MCP has conditional logic in `_setup_views()` and `_window_clause()`. All other components are simpler because they have no mode awareness.

---

### ADR-002: tracker.js as Single Self-Contained File (IIFE)

**Status:** Accepted
**Context:** Need a browser tracking script that clients can embed in one line.
**Decision:** tracker.js is a single IIFE (Immediately Invoked Function Expression) with no external imports, no build step, no framework.
**Rationale:** Matches how GA4 and Hotjar work. Zero friction for client adoption — paste one snippet, done. Self-contained means no CDN dependency for the script itself.
**Consequences:** Cannot use modern ES modules or npm packages. Must use ES5-compatible patterns. All functionality in vanilla JavaScript.

---

### ADR-003: FastAPI for Collector (Not Flask, Not aiohttp)

**Status:** Accepted
**Context:** Need an async HTTP server for event collection with validation.
**Decision:** Use FastAPI.
**Rationale:** Native async, Pydantic v2 integration, automatic OpenAPI docs, BackgroundTasks for non-blocking writes, built-in CORS middleware.
**Consequences:** Requires uvicorn. Adds uvicorn to dependencies.

---

### ADR-004: LangGraph over CrewAI or Direct Tool Use

**Status:** Accepted
**Context:** Need multi-agent orchestration with human-in-loop and state persistence.
**Decision:** Use LangGraph.
**Rationale:** `interrupt_before` makes human-in-loop a first-class feature. `SqliteSaver` enables checkpoint/resume out of the box. Typed `TypedDict` state is self-documenting. LangSmith integration is zero-code.
**Consequences:** LangChain ecosystem dependency. Workers must be async. Supervisor must be sync. Both are simple LangGraph constraints.

---

### ADR-005: stdio MCP Transport for PoC

**Status:** Accepted
**Context:** MCP supports both stdio and HTTP transports.
**Decision:** Use stdio for PoC.
**Rationale:** Zero configuration, zero ports, zero authentication needed. This is also how Claude Code uses MCP servers. Upgrading to HTTP transport requires changing one line per server (`mcp.run(transport="http")`) and updating `mcp_client.py`.
**Consequences:** Single-machine deployment only. HTTP upgrade is documented and planned for Phase 3.

---

### ADR-006: Shared DuckDB File Between Collector and Journey Data MCP

**Status:** Accepted
**Context:** Collector writes to live_events; Journey Data MCP reads from events VIEW.
**Decision:** Use a single DuckDB file for both.
**Rationale:** DuckDB supports concurrent reads with one writer. Collector writes (INSERT); MCP only reads (SELECT). No data integrity issues.
**Consequences:** In production, move to PostgreSQL which handles multi-writer, multi-reader natively.

---

### ADR-007: Deterministic Scoring Over ML Model

**Status:** Accepted
**Context:** Considered training an ML model to score friction vs. using a weighted formula.
**Decision:** Use a weighted deterministic formula with configurable thresholds.
**Rationale:** Transparent, auditable, testable offline, explainable to evaluators. ML would require training data, MLOps pipeline, model versioning — all out of scope for 6 weeks.
**Consequences:** Less adaptive than ML. Weights and baselines are exposed in config for easy tuning. ML layer is the planned Phase 4 upgrade.

---

### ADR-008: LiteLLM as Universal LLM Adapter

**Status:** Accepted
**Context:** Need to support Anthropic Claude, OpenAI GPT-4o, and local Ollama in the same codebase.
**Decision:** Route all LLM calls through `litellm.completion()`. Never import provider SDKs directly.
**Rationale:** Changing provider = changing one environment variable. No code changes. LiteLLM handles authentication, retry, and format normalisation for 100+ providers.
**Consequences:** LiteLLM library dependency. Minor overhead vs. direct SDK calls (~10-20ms). Worth it for provider agnosticism.
