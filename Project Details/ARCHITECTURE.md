> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Architecture Document
## Customer Journey Intelligence (CJI) — System Architecture

**Version:** 2.0  
**Date:** March 2026  
**Document Type:** Architecture Reference  
**Audience:** Technical architects, Claude Code, developers

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Design Principles](#2-design-principles)
3. [High-Level System Architecture](#3-high-level-system-architecture)
4. [Dual-Mode Architecture Pattern](#4-dual-mode-architecture-pattern)
5. [Layer Architecture](#5-layer-architecture)
6. [Component Architecture](#6-component-architecture)
7. [Tracker and Collector Architecture](#7-tracker-and-collector-architecture)
8. [MCP Architecture](#8-mcp-architecture)
9. [Agent Architecture](#9-agent-architecture)
10. [Data Architecture](#10-data-architecture)
11. [Communication Patterns](#11-communication-patterns)
12. [State Machine Specification](#12-state-machine-specification)
13. [PoC Deployment Architecture](#13-poc-deployment-architecture)
14. [Production Architecture (Phase 3+)](#14-production-architecture-phase-3)
15. [Security Architecture](#15-security-architecture)
16. [Alternative Architectures Considered](#16-alternative-architectures-considered)
17. [Architecture Decision Records (ADRs)](#17-architecture-decision-records-adrs)

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

This principle means: changing data sources requires modifying exactly one file (`mcp_servers/journey_data_server.py`). The friction engine, insight generation, report production, and all agent logic never change.

---

## 2. Design Principles

**P1 — Hard Mode Boundary**
Only the Journey Data MCP knows where data comes from. Every component below it treats data as normalised step metrics, regardless of source.

**P2 — Provider Agnosticism**
No production code imports `anthropic` directly. All LLM calls go through LiteLLM. Changing LLM provider = changing one environment variable.

**P3 — Independently Testable MCP Servers**
Each MCP server can be run standalone, tested with unit tests, and called from CLI. The Friction Engine MCP has zero external dependencies — it is testable offline.

**P4 — Fail Gracefully, Never Silently**
Every worker catches all exceptions and writes them to `state["errors"]`. Every LLM output has a JSON fallback. The graph never crashes — it reaches END with partial results if something fails.

**P5 — Configuration Over Code**
Journey steps, scoring weights, thresholds, LLM model, MCP ports, analysis windows — all configurable via `.env` and `config.py`. Switching clients or modes requires zero code changes.

**P6 — Observable by Default**
LangSmith traces are enabled by default. Every state transition is logged. The graph state is inspectable at any point. Collector API has health and stats endpoints.

**P7 — Browser-First Data Collection**
tracker.js is a single self-contained file with no build step, no dependencies, and async loading. It captures events without blocking page load and uses `sendBeacon` to survive tab close.

**P8 — Incremental Complexity**
stdio → HTTP MCP transport, DuckDB → PostgreSQL, ChromaDB → pgvector, Streamlit → Next.js, Parquet → Kafka. Each upgrade is an isolated swap with no architectural rethinking.

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
╔═════════════════════════════════════════════════════════════════╗
║           MODE-AGNOSTIC ANALYTICAL LAYER (BOTH MODES)           ║
║                                                                  ║
║  MCP Server 2: Friction Engine                                   ║
║  Tools: score_friction, score_all_steps,                         ║
║         detect_dropoffs, correlate_signals                       ║
║                     │                                            ║
║  MCP Server 3: Insight & LLM                                     ║
║  Tools: generate_insight, prioritise_fix,                        ║
║         save_insight, search_insights, rank_all_fixes            ║
║                     │                                            ║
║  MCP Server 4: Report & Viz                                      ║
║  Tools: generate_narrative, export_report                        ║
╚═════════════════════════════════════════════════════════════════╝
                     │
╔═════════════════════════════════════════════════════════════════╗
║           LANGGRAPH AGENT LAYER (MODE-AGNOSTIC)                  ║
║                                                                  ║
║   START → [Supervisor] ──► [Data Worker]     ──► [Supervisor]   ║
║                        ──► [Friction Worker] ──► [Supervisor]   ║
║                        ──► [Insight Worker]  ──► [Supervisor]   ║
║               ⏸ [HUMAN CHECKPOINT]                              ║
║                        ──► [Report Worker]   ──► END            ║
║                                                                  ║
║   State: CJIState TypedDict (SQLite checkpoints)                 ║
╚═════════════════════════════════════════════════════════════════╝
                     │
╔═════════════════════════════════════════════════════════════════╗
║              PRESENTATION LAYER                                  ║
║                                                                  ║
║   Streamlit Dashboard     CLI (main.py)     HTML Report          ║
║   (mode toggle, charts,   (--mode flag,     (self-contained,     ║
║    approval gate,          checkpoints,      Chart.js charts,    ║
║    live feed)              thread IDs)       downloadable)       ║
╚═════════════════════════════════════════════════════════════════╝
```

---

## 4. Dual-Mode Architecture Pattern

### 4.1 Mode Selection Flow

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
All other components: use the "events" VIEW — never know which mode they're in
```

### 4.2 What Changes Per Mode

**Demo mode only:**
- `tools/synthetic_data.py` runs to generate `data/events.parquet`
- Journey Data MCP creates a VIEW over Parquet
- Time window = days (analysis_window_days)
- CLI: `--generate-data` flag is meaningful

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

### 4.3 Data Source Abstraction

The "events" DuckDB VIEW is the abstraction boundary. Both sources produce rows matching:

```sql
event_id VARCHAR, user_id VARCHAR, journey_id VARCHAR, step_id VARCHAR,
event_type VARCHAR, timestamp TIMESTAMPTZ, duration_ms BIGINT, metadata VARCHAR
```

The `get_step_metrics()` SQL query is identical in both modes — it runs against the same VIEW name, uses the same aggregation logic, produces the same column schema. Only the WHERE clause differs (days vs minutes).

---

## 5. Layer Architecture

### Layer 1: Presentation Layer

**Components:** `dashboard.py`, `main.py`, HTML reports in `reports/`

**Responsibilities:**
- User interface for triggering analysis, reviewing findings, approving reports
- Mode toggle that restarts session state and updates `os.environ["CJI_MODE"]`
- Real-time event feed (realtime mode) showing latest tracker.js events
- Collector API status indicator (realtime mode)
- Download button for generated HTML reports

**Hard constraints:**
- No business logic — pure presentation and flow control
- Never calls MCP servers directly
- Never accesses DuckDB directly
- All data comes from LangGraph state snapshots via `graph.get_state()`

### Layer 2: Orchestration Layer (LangGraph)

**Components:** `graph.py`, `agents/supervisor.py`, `agents/workers.py`

**Responsibilities:**
- Route analysis workflow through directed state graph
- Persist state to SQLite between pause and resume
- Human-in-loop checkpoint before report generation
- Collect and aggregate all worker outputs into shared state

**Hard constraints:**
- Supervisor must be a sync function
- Workers must be async functions
- Workers never call each other directly
- Workers only write to state via return dict
- Workers always return `next_worker="supervisor"`

### Layer 3: Protocol Layer (MCP)

**Components:** `tools/mcp_client.py`, all four MCP server files

**Responsibilities:**
- Spawn MCP server subprocesses and manage their lifecycle
- JSON-RPC serialisation/deserialisation
- Route tool calls to correct MCP server

**Hard constraints:**
- Workers may not import from `mcp_servers/` directly — must go through `mcp_client.py`
- Each `mcp_session()` context manager creates a fresh subprocess
- MCP sessions must not be reused across worker invocations

### Layer 4: Business Logic Layer (MCP Servers)

**Components:** Four MCP server files

**Responsibilities:**
- Domain-specific analytical logic
- Data store access (Journey Data MCP only)
- LLM calls (Insight and Report MCPs)
- Report file generation (Report MCP)

**Hard constraints:**
- Each server owns one domain — never imports from another MCP server
- Must be independently runnable: `python mcp_servers/server.py` must start a valid MCP server
- Must expose all functionality as `@mcp.tool` decorated functions

### Layer 5: Data Collection Layer

**Components:** `tracker/tracker.js`, `collector/api.py`, `tools/synthetic_data.py`

**Responsibilities:**
- Realtime: capture browser events and deliver to collector
- Realtime: receive, validate, and persist events to DuckDB
- Demo: generate statistically realistic synthetic events and write to Parquet

**Hard constraints:**
- tracker.js must be a single file with no external dependencies
- Collector API must validate API key before any write operation
- Synthetic data must match the exact unified event schema

### Layer 6: Infrastructure Layer

**Components:** DuckDB, ChromaDB, SQLite, LiteLLM, file system

**Responsibilities:**
- Persist events (Parquet + DuckDB), insights (ChromaDB), state (SQLite), reports (HTML files)
- Abstract LLM provider

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

### 6.2 Process Architecture (PoC)

```
Process 1: main.py / dashboard.py / uvicorn (Python)
│  ├── LangGraph graph (in-process)
│  ├── DuckDB read connection (in-process)    ←── READ ONLY from here
│  └── ChromaDB client (in-process)
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

**DuckDB access pattern:**
- Collector API: WRITE (INSERT to live_events)
- Journey Data MCP: READ (SELECT from events VIEW)
- DuckDB supports multiple readers from one writer — this is safe in PoC

---

## 7. Tracker and Collector Architecture

### 7.1 tracker.js Internal Architecture

```
window.CJI_CONFIG
      │
      ▼
Identity Layer
  - userId: UUID from localStorage (persists across sessions)
  - sessionId: UUID (new per tab)
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
  - flushTimer: setTimeout(5000)
  - MAX_BATCH = 20
  - flush(useBeacon): POST to ENDPOINT/batch
      │
      ▼
Delivery Layer
  - fetch() with keepalive: true
  - sendBeacon() fallback for beforeunload
```

### 7.2 Collector API Event Processing Pipeline

```
POST /collect/batch
      │
      ▼
1. API key validation (DuckDB api_keys lookup)
      │
      ▼
2. Pydantic EventBatch validation
   - event_type in allowed set
   - timestamp valid ISO-8601
   - url query params stripped
   - id fields min length 8
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
   - rejected count
   - errors list
      │
      ▼
6. Events available in live_events table
   → Journey Data MCP queries them on next analysis run
```

### 7.3 Snippet Generator Architecture

```
snippet_generator.py --journey X --host Y --output DIR
      │
      ▼
1. secrets.token_hex(16) → api_key string
2. IMPORTANT: API key must be inserted into collector's api_keys table
   (Done by collector's _create_tables() for dev key; production key via POST /admin/api-keys)
      │
      ▼
3. Generate 4 output files:
   ├── embed_snippet.html  (window.CJI_CONFIG + script tag)
   ├── verify_tracker.py   (HTTP test script)
   ├── useCJITracker.js    (React/Next.js hook)
   └── api_key.json        (key record for safekeeping)
```

---

## 8. MCP Architecture

### 8.1 MCP Protocol Stack

```
Application Layer:  @mcp.tool() decorated Python functions
                    ↕ FastMCP wraps to JSON schema
Protocol Layer:     MCP SDK (ClientSession / ServerSession)
                    ↕ JSON-RPC 2.0 messages
Transport Layer:    stdio (subprocess pipes) — PoC
                    Streamable HTTP — Production
```

### 8.2 MCP JSON-RPC Message Flow

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

### 8.3 MCP Tool Interface Contracts

All 14 tools and their exact JSON contracts are specified in the System Design document. Key contract rule: **all tool outputs are dicts** — never return lists, strings, or primitives directly.

### 8.4 Mode-Aware MCP Design

Only one MCP server (Journey Data) is mode-aware. The mode awareness is contained in two places:
1. `_setup_views()` — creates different VIEW depending on `CJI_MODE`
2. `_window_clause()` — returns days-based or minutes-based WHERE clause

All four tools in Journey Data MCP use `_window_clause()` which automatically applies the correct time window for the current mode.

---

## 9. Agent Architecture

### 9.1 Supervisor Decision Architecture

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

### 9.2 Worker Communication via Shared State (Blackboard Pattern)

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

### 9.3 Agent Graph Topology

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

---

## 10. Data Architecture

### 10.1 Complete Data Flow

```
DEMO MODE:
Faker → sessions → events list → pd.DataFrame → events.parquet
                                                      │
                                              DuckDB VIEW "events"
                                                      │
                                       Journey Data MCP SQL queries
                                                      │
                                              step_metrics dict
                                                      │

REALTIME MODE:
User browser → tracker.js → POST /collect/batch → Collector API
                                                      │
                                           Pydantic validation
                                                      │
                                      DuckDB INSERT live_events table
                                                      │
                              DuckDB VIEW "events" → same view name
                                                      │
                                       Journey Data MCP SQL queries
                                                      │
                                              step_metrics dict
                                                      │
                                    (IDENTICAL FROM HERE DOWN)
                                                      │
                                    ┌─────────────────▼──────────────────┐
                                    │         Friction Engine MCP         │
                                    │    score_all_steps() → scores       │
                                    └─────────────────┬──────────────────┘
                                                      │
                                    ┌─────────────────▼──────────────────┐
                                    │           Insight MCP               │
                                    │  generate_insight() → LiteLLM       │
                                    │  save_insight() → ChromaDB          │
                                    └─────────────────┬──────────────────┘
                                                      │
                                    ┌─────────────────▼──────────────────┐
                                    │            Report MCP               │
                                    │  export_report() → HTML file        │
                                    └────────────────────────────────────┘
```

### 10.2 Storage Architecture Summary

| Store | Technology | Mode | Access | Persistence |
|---|---|---|---|---|
| Event store (demo) | Parquet file | Demo | Read-only after generation | File-based |
| Event store (realtime) | DuckDB live_events | Realtime | Write (collector), Read (MCP) | DuckDB file |
| Analytics | DuckDB VIEW | Both | Read-only | In-memory view |
| API keys | DuckDB table | Realtime | Read (auth), Write (admin) | DuckDB file |
| Graph checkpoints | SQLite | Both | Read/Write (LangGraph) | SQLite file |
| Insight vector store | ChromaDB | Both | Read/Write (Insight MCP) | Directory |
| Reports | HTML files | Both | Write (Report MCP) | File system |

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

```
Worker:
  async with mcp_session("server_name") as session:
    result = await call_tool(session, "tool_name", {"arg": value})
  
  Internally:
    1. subprocess.Popen([sys.executable, "mcp_servers/server.py"])
    2. stdio_client(StdioServerParameters) → (read, write) pipes
    3. ClientSession(read, write).initialize()
    4. session.call_tool("tool_name", arguments) → JSON-RPC call
    5. result.content[0].text → json.loads() → Python dict
    6. Context exit → process.terminate()
```

### 11.3 Dashboard → Collector (HTTP, realtime mode only)

```
Streamlit → requests.get("{COLLECTOR_HOST}/live/stats", headers={"x-cji-key": KEY})
           → requests.get("{COLLECTOR_HOST}/health")
           (synchronous, timeout=2-3 seconds)
```

### 11.4 Supervisor → LLM (LiteLLM, fallback only)

```
supervisor._llm_route() → litellm.completion(model=LLM_MODEL, messages=[...])
                         → response.choices[0].message.content.strip()
                         → sanitised against VALID_NEXT set
```

---

## 12. State Machine Specification

### 12.1 Full Graph State Diagram

```
┌─────────┐
│  START  │
└────┬────┘
     │ initial CJIState
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
    │          │          │               ───────────          │           │
    │          │          │               human reviews        │           │
    │          │          │               graph.update_state() │           │
    └──────────┴──────────┴─────────────────────────────────────────────┘
                                                          │
                                                [END:complete]
```

### 12.2 State Invariants

At any checkpoint, these must always hold:
1. `iteration` is monotonically increasing
2. `worker_statuses` only grows (concatenation)
3. `messages` only grows (add_messages reducer)
4. `human_approved` starts False, can only be set True via `graph.update_state()`
5. If `report_path` is non-empty, `insights` must be non-empty
6. If `friction_scores` is non-empty, `event_summary` must be non-empty
7. `next_worker` is always one of: `{data_worker, friction_worker, insight_worker, report_worker, END, ""}`
8. `mode` never changes after initial state is set

### 12.3 Checkpoint Semantics

Every node execution produces a checkpoint. On process crash + restart:
- Same `thread_id` → `graph.stream(None, config)` resumes from last checkpoint
- Human approval: graph checkpoints state, returns control to caller, human approves via `update_state()`, `graph.stream(None)` resumes from checkpoint

---

## 13. PoC Deployment Architecture

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

## 14. Production Architecture (Phase 3+)

### 14.1 Microservices Topology

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

### 14.2 Key Production Changes

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

## 15. Security Architecture

### 15.1 API Key Flow

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

### 15.2 Data Privacy Controls in tracker.js

```javascript
// URL sanitisation (mandatory):
const parsed = urlparse(url);
return `${parsed.scheme}://${parsed.netloc}${parsed.path}`
// Strips: ?query=params, #fragments, no PII in URL storage

// Anonymous identity:
userId = localStorage.getItem('_cji_uid') || crypto.randomUUID()
// UUID only, no email/name/phone ever stored

// Metadata caps:
error_message: String(msg).slice(0, 200)   // cap error message length
text_preview: el.innerText.slice(0, 50)    // cap click text capture
```

### 15.3 LLM Prompt Privacy

Insight and narrative prompts contain ONLY:
- Aggregated numeric metrics (abandon rate %, error rate %, dwell time averages)
- Signal names (strings)
- Step IDs (non-identifying strings)

Raw event data, URLs, user IDs, and metadata are NEVER sent to the LLM.

---

## 16. Alternative Architectures Considered

### 16.1 Alternative: Separate DuckDB Files for Collector and MCP

**Proposed:** Collector writes to `collector.duckdb`, Journey Data MCP reads from `journey.duckdb`, with a sync job copying between them.

**Rejected because:** Adds unnecessary complexity and latency. DuckDB supports multiple readers with one writer. Using the same file with a reader (MCP) and writer (collector) works correctly in PoC.

### 16.2 Alternative: Redis for Real-Time Events

**Proposed:** tracker.js → Redis Pub/Sub → consumer writes to DuckDB.

**Rejected because:** Requires Redis infrastructure. For PoC, direct POST to collector is simpler, reliable, and sufficient. Redis is the correct upgrade path for Phase 3.

### 16.3 Alternative: All Agents Calling LLM Directly

**Proposed:** Agents call `litellm.completion()` directly instead of via MCP Insight server.

**Rejected because:** Breaks the MCP architecture principle (LLM logic is a capability exposed by a server, not agent-specific code). Also prevents the Insight MCP from being called independently for testing.

### 16.4 Alternative: Single Monolithic Python File

**Proposed:** All logic in one script, no MCP separation.

**Rejected because:** Untestable, unreusable, does not demonstrate the agentic AI + MCP architecture. The PoC goal is to demonstrate the pattern, not just get a result.

---

## 17. Architecture Decision Records (ADRs)

### ADR-001: Dual-Mode Architecture with Hard Boundary at Journey Data MCP

**Status:** Accepted  
**Context:** Need both a demo mode (no live site required) and a realtime mode (live tracker.js data).  
**Decision:** Draw the mode boundary at the Journey Data MCP. Only this MCP is mode-aware. All downstream components are mode-agnostic.  
**Rationale:** Minimises the code that needs to change when switching modes. All analytical logic — scoring, insight generation, reporting, agent orchestration — is written once and works for both modes.  
**Consequences:** Journey Data MCP has conditional logic in `_setup_views()` and `_window_clause()`. All other components are simpler because they have no mode awareness.

### ADR-002: tracker.js as Single Self-Contained File

**Status:** Accepted  
**Context:** Need a browser tracking script that clients can embed in one line.  
**Decision:** tracker.js is a single IIFE (Immediately Invoked Function Expression) with no external imports, no build step, no framework.  
**Rationale:** Matches how GA4 and Hotjar work. Zero friction for client adoption — paste one snippet, done. Self-contained means no CDN dependency for the script itself.  
**Consequences:** Cannot use modern ES modules or npm packages. Must use ES5-compatible syntax (or modern with explicit browser support statement). All functionality must be implemented in vanilla JavaScript.

### ADR-003: FastAPI for Collector (Not Flask, Not aiohttp)

**Status:** Accepted  
**Context:** Need an async HTTP server for event collection with validation.  
**Decision:** Use FastAPI.  
**Rationale:** Native async, Pydantic v2 integration, automatic OpenAPI docs, BackgroundTasks for non-blocking writes, built-in CORS middleware. The Pydantic models are shared between the API layer and the CJI system.  
**Consequences:** Requires uvicorn. Adds uvicorn to dependencies. Worth it for the validation, async I/O, and documentation benefits.

### ADR-004: LangGraph over CrewAI or Direct Tool Use

**Status:** Accepted  
**Context:** Need multi-agent orchestration with human-in-loop and state persistence.  
**Decision:** Use LangGraph.  
**Rationale:** `interrupt_before` makes human-in-loop a first-class feature. `SqliteSaver` enables checkpoint/resume out of the box. Typed `TypedDict` state is self-documenting. LangSmith integration is zero-code.  
**Consequences:** LangChain ecosystem dependency. Workers must be async. Supervisor must be sync. Both are LangGraph constraints that are simple to follow.

### ADR-005: stdio MCP Transport for PoC

**Status:** Accepted  
**Context:** MCP supports both stdio and HTTP transports.  
**Decision:** Use stdio for PoC.  
**Rationale:** Zero configuration, zero ports, zero authentication needed. This is also how Claude Code uses MCP servers. Upgrading to HTTP transport requires changing one line in each server (`mcp.run(transport="http")`) and updating the `mcp_client.py` connection — architectural impact is zero.  
**Consequences:** Single-machine deployment only. HTTP upgrade is documented and planned for Phase 3.

### ADR-006: Shared DuckDB File Between Collector and Journey Data MCP

**Status:** Accepted  
**Context:** Collector writes to live_events; Journey Data MCP reads from events VIEW.  
**Decision:** Use a single DuckDB file for both.  
**Rationale:** DuckDB supports concurrent reads with one writer. Collector writes (INSERT); MCP only reads (SELECT). No data integrity issues. Using separate files would require a sync mechanism, adding complexity with no benefit in PoC.  
**Consequences:** In production, move to PostgreSQL which handles multi-writer, multi-reader natively.

### ADR-007: Deterministic Scoring Over ML Model

**Status:** Accepted  
**Context:** Considered training an ML model to score friction vs. using a weighted formula.  
**Decision:** Use a weighted deterministic formula with configurable thresholds.  
**Rationale:** Transparent, auditable, testable offline, explainable to evaluators. ML would require training data, MLOps pipeline, model versioning — all out of scope for 6 weeks. The formula produces defensible results that a PM can explain.  
**Consequences:** Less adaptive than ML. Weights and baselines are exposed in config for easy tuning. ML layer is the planned Phase 4 upgrade.
