> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Information Architecture
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** Information Architecture Reference

---

## Table of Contents

1. [System Information Map](#1-system-information-map)
2. [Repository Information Structure](#2-repository-information-structure)
3. [Data Information Architecture](#3-data-information-architecture)
4. [User Interface Information Hierarchy](#4-user-interface-information-hierarchy)
5. [Configuration Information Structure](#5-configuration-information-structure)
6. [MCP Tool Information Taxonomy](#6-mcp-tool-information-taxonomy)
7. [Agent State Information Model](#7-agent-state-information-model)
8. [Report Information Hierarchy](#8-report-information-hierarchy)
9. [Event Taxonomy](#9-event-taxonomy)
10. [Navigation and Flow Maps](#10-navigation-and-flow-maps)

---

## 1. System Information Map

### 1.1 Top-Level Domains

The CJI system is organised around six information domains:

```
┌─────────────────────────────────────────────────────────┐
│                    CJI SYSTEM                           │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ DATA DOMAIN  │  │ ANALYSIS     │  │ DELIVERY     │  │
│  │              │  │ DOMAIN       │  │ DOMAIN       │  │
│  │ Events       │  │ Friction     │  │ Reports      │  │
│  │ Sessions     │  │ Insights     │  │ Dashboard    │  │
│  │ Journeys     │  │ Priorities   │  │ CLI          │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ AGENT DOMAIN │  │ CONFIG       │  │ SECURITY     │  │
│  │              │  │ DOMAIN       │  │ DOMAIN       │  │
│  │ State        │  │ Mode         │  │ API Keys     │  │
│  │ Checkpoints  │  │ LLM Provider │  │ Privacy      │  │
│  │ Workflow     │  │ Journeys     │  │ Validation   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 1.2 Domain Relationships

```
Config Domain
    ├── controls → Data Domain (mode, journey, paths)
    ├── controls → Agent Domain (iterations, thresholds, LLM model)
    └── controls → Security Domain (API keys, admin key)

Data Domain
    ├── feeds → Analysis Domain (step metrics, events)
    └── protected by → Security Domain (API key validation)

Analysis Domain
    ├── produces → Delivery Domain (reports, narratives)
    └── orchestrated by → Agent Domain (supervisor, workers)

Agent Domain
    ├── reads → Data Domain (via Journey Data MCP)
    ├── calls → Analysis Domain (via MCP tools)
    └── writes → Delivery Domain (via Report MCP)
```

---

## 2. Repository Information Structure

### 2.1 Complete File Map with Purpose

```
cji_agent/                          ← Root package directory
│
├── ── CONFIGURATION ──────────────────────────────────────
│
├── config.py                       All environment vars, paths, thresholds
├── .env.example                    Environment template with defaults
├── .env                            Actual secrets (gitignored)
├── .gitignore                      Files excluded from version control
├── requirements.txt                All Python dependencies with pinned versions
├── README.md                       Setup, usage, and demonstration guide
│
├── ── CORE APPLICATION ────────────────────────────────────
│
├── state.py                        CJIState TypedDict + sub-type definitions
├── graph.py                        LangGraph compilation (build_graph, get_graph)
├── main.py                         CLI entry point (argparse, pipeline trigger)
├── dashboard.py                    Streamlit web UI
│
├── ── DATA COLLECTION (mode-specific) ────────────────────
│
├── tracker/                        Browser-side data collection
│   ├── tracker.js                  Self-contained IIFE tracker script
│   └── snippet_generator.py        Generates embed code + API key
│
├── collector/                      Server-side event receiver
│   ├── __init__.py                 Empty
│   ├── api.py                      FastAPI app with all routes
│   └── models.py                   Pydantic v2 schemas for validation
│
├── tools/                          Internal utilities
│   ├── __init__.py                 Empty
│   ├── synthetic_data.py           Faker-based demo data generator
│   └── mcp_client.py               MCP subprocess/session manager
│
├── ── ANALYTICAL LAYER (MCP Servers) ─────────────────────
│
├── mcp_servers/                    Four independently deployable MCP servers
│   ├── __init__.py                 Empty
│   ├── journey_data_server.py      MCP 1: Data access (mode-aware)
│   ├── friction_engine_server.py   MCP 2: Deterministic scoring (pure logic)
│   ├── insight_server.py           MCP 3: LLM root cause analysis
│   └── report_server.py            MCP 4: HTML report generation
│
├── ── ORCHESTRATION (Agent Layer) ─────────────────────────
│
├── agents/                         LangGraph agent components
│   ├── __init__.py                 Empty
│   ├── supervisor.py               Routing supervisor (synchronous function)
│   └── workers.py                  Four worker async functions
│
├── ── TESTING ─────────────────────────────────────────────
│
├── tests/                          All test files
│   ├── __init__.py                 Empty
│   ├── test_friction_engine.py     12+ unit tests (zero network/API)
│   ├── test_collector_models.py    6+ Pydantic validation tests
│   └── test_synthetic_data.py      4+ generator output tests
│
└── ── RUNTIME DATA (auto-created, gitignored) ─────────────

    data/
    ├── events.parquet              Demo mode synthetic events (~3MB)
    ├── cji.duckdb                  DuckDB file (VIEW + live_events + api_keys)
    ├── cji_checkpoints.db          SQLite-based LangGraph state checkpoints
    └── chroma/                     ChromaDB vector store directory
        └── cji_insights/           Collection with insight embeddings

    reports/
    └── cji_report_*.html           Self-contained HTML reports
```

### 2.2 Build Dependency Order

Files must be built in this exact order (dependency chain):

```
Level 0 (no dependencies):
├── config.py
├── state.py
├── collector/models.py
├── tracker/tracker.js
└── tracker/snippet_generator.py

Level 1 (depends on Level 0):
├── collector/api.py           → models + fastapi + duckdb
├── mcp_servers/friction_engine_server.py → config only
└── tools/synthetic_data.py   → faker + pandas + config

Level 2 (depends on Level 1):
├── mcp_servers/journey_data_server.py  → duckdb + config
├── mcp_servers/insight_server.py       → litellm + chromadb + config
└── mcp_servers/report_server.py        → litellm + config

Level 3 (depends on Level 2):
└── tools/mcp_client.py        → mcp SDK

Level 4 (depends on Level 3):
├── agents/workers.py          → mcp_client + state + config
└── agents/supervisor.py       → state + config + litellm

Level 5 (depends on Level 4):
└── graph.py                   → all agents + langgraph

Level 6 (depends on Level 5):
├── main.py                    → graph + config + argparse
└── dashboard.py               → graph + streamlit + requests

Level 7 (depends on Levels 1-2):
├── tests/test_friction_engine.py
├── tests/test_collector_models.py
└── tests/test_synthetic_data.py
```

---

## 3. Data Information Architecture

### 3.1 Data Storage Map

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA STORAGE                             │
│                                                             │
│  ┌─────────────────────────────────────────┐               │
│  │         DuckDB (data/cji.duckdb)        │               │
│  │                                         │               │
│  │  DEMO MODE:                             │               │
│  │  ├── VIEW events                        │               │
│  │  │   └── reads from events.parquet      │               │
│  │  │                                      │               │
│  │  REALTIME MODE:                         │               │
│  │  ├── TABLE live_events                  │               │
│  │  │   ├── event_id (PK)                  │               │
│  │  │   ├── user_id                        │               │
│  │  │   ├── session_id                     │               │
│  │  │   ├── journey_id                     │               │
│  │  │   ├── step_id                        │               │
│  │  │   ├── event_type                     │               │
│  │  │   ├── timestamp                      │               │
│  │  │   ├── duration_ms                    │               │
│  │  │   ├── url                            │               │
│  │  │   ├── metadata (JSON string)         │               │
│  │  │   └── received_at                    │               │
│  │  ├── VIEW events (alias for live_events)|               │
│  │  └── TABLE api_keys                     │               │
│  │      ├── api_key (PK)                   │               │
│  │      ├── journey_id                     │               │
│  │      ├── client_name                    │               │
│  │      ├── created_at                     │               │
│  │      └── active (BOOLEAN)               │               │
│  └─────────────────────────────────────────┘               │
│                                                             │
│  ┌─────────────────────────────────────────┐               │
│  │         Parquet (data/events.parquet)   │               │
│  │         Demo mode raw event storage     │               │
│  │  Columns: event_id, user_id, journey_id,│               │
│  │           step_id, event_type, timestamp│               │
│  │           duration_ms, metadata         │               │
│  └─────────────────────────────────────────┘               │
│                                                             │
│  ┌─────────────────────────────────────────┐               │
│  │     ChromaDB (data/chroma/)             │               │
│  │     Collection: cji_insights            │               │
│  │                                         │               │
│  │  Document: "{title}. {root_cause}.      │               │
│  │             {suggested_fix}"            │               │
│  │  Embedding: all-MiniLM-L6-v2           │               │
│  │  Distance metric: cosine                │               │
│  │  Metadata: step_id, category, priority, │               │
│  │            score, fix_effort (all str)  │               │
│  └─────────────────────────────────────────┘               │
│                                                             │
│  ┌─────────────────────────────────────────┐               │
│  │     SQLite (data/cji_checkpoints.db)    │               │
│  │     LangGraph-managed checkpoint store  │               │
│  │                                         │               │
│  │  Key: thread_id (UUID)                  │               │
│  │  Value: serialised CJIState JSON        │               │
│  │  Accessed only via LangGraph API        │               │
│  └─────────────────────────────────────────┘               │
│                                                             │
│  ┌─────────────────────────────────────────┐               │
│  │     File System (reports/)              │               │
│  │     Naming: cji_report_{journey}_{ts}.html │            │
│  │     Format: self-contained HTML         │               │
│  │     Size: ~100KB per report             │               │
│  └─────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Event Taxonomy

All events are classified along two dimensions:

**Dimension 1: Source**
```
event_source
├── synthetic        (generated by tools/synthetic_data.py)
└── browser          (captured by tracker/tracker.js)
    ├── automatic    (triggered by browser events without user action)
    └── manual       (triggered by window.CJITracker.track())
```

**Dimension 2: Event Type Hierarchy**
```
event_type
├── navigation
│   ├── page_view        (DOMContentLoaded or SPA navigation)
│   └── step_complete    (SPA navigation away from step)
├── interaction
│   ├── click            (any element click)
│   ├── form_submit      (form submission)
│   └── rage_click       (3+ clicks on same element in 500ms)
├── friction
│   ├── error            (JS error, unhandled promise rejection)
│   └── abandon          (tab/window close via beforeunload)
└── identity
    └── identify         (anonymous trait enrichment)
```

### 3.3 Derived Data Flow

```
Raw Events (Parquet / live_events table)
    │
    ▼ get_step_metrics() SQL aggregation
StepMetrics per step
├── step_id
├── unique_users
├── completion_rate_pct
├── abandon_rate_pct
├── error_rate_pct
├── avg_dwell_ms
├── avg_rage_clicks
└── avg_retries
    │
    ▼ score_friction() per step
FrictionScore per step
├── score (0–100)
├── signals (list of named friction indicators)
├── confidence (0.0–0.98)
└── is_critical (bool)
    │
    ▼ generate_insight() + prioritise_fix() per critical step
Insight per step
├── title (max 8 words)
├── root_cause (2-3 sentences)
├── category (UX|data|system|process|unknown)
├── evidence (list of supporting data points)
├── suggested_fix (1-2 sentences)
├── fix_effort (low|medium|high)
├── priority (1–5)
└── priority_score (float)
    │
    ▼ generate_narrative() + export_report()
HTML Report
├── Executive narrative (3 paragraphs)
├── Friction bar chart
├── Funnel drop-off chart
└── Prioritised findings table
```

---

## 4. User Interface Information Hierarchy

### 4.1 Streamlit Dashboard Layout

```
CJI Dashboard
│
├── Header
│   ├── Title: "Customer Journey Intelligence"
│   └── Mode Badge: DEMO | LIVE
│
├── Sidebar
│   ├── Mode Toggle (radio: demo / realtime)
│   ├── [Realtime only] Collector Status: ● Online / ✗ Offline
│   ├── [Realtime only] Live Event Feed (last 15 events)
│   │   └── event_type, step_id, timestamp (rolling)
│   └── [Realtime only] Generate Embed Snippet button
│
├── Control Bar
│   ├── Journey selector (default: "onboarding")
│   ├── [Demo] Days back input (default: 30)
│   ├── [Realtime] Window minutes input (default: 60)
│   └── Run Analysis button
│
├── Metric Cards (4 columns)
│   ├── Steps Analysed: N/6
│   ├── Critical Steps: N (score ≥ 60)
│   ├── Avg Friction Score: N/100
│   └── Insights Generated: N
│
├── Charts Section (2 columns)
│   ├── Left: Friction Score Bar Chart
│   │   ├── X: step_id, Y: score (0–100)
│   │   └── Colors: red/amber/green by threshold
│   └── Right: Funnel Drop-off Chart
│       ├── X: step_id, Y: drop_off_pct
│       └── Color: blue (always)
│
├── Insights Review Section
│   ├── Expandable card per insight
│   │   ├── Label: "[P{priority}] {step_id}"
│   │   ├── Title: insight.title
│   │   ├── Root Cause: insight.root_cause
│   │   ├── Category: insight.category [badge]
│   │   ├── Evidence: bulleted list
│   │   ├── Suggested Fix: insight.suggested_fix
│   │   └── Fix Effort: insight.fix_effort  Score: insight.score
│   └── [No insights] → "Run analysis first"
│
├── Human Approval Gate (visible when insights exist, report not generated)
│   ├── Message: "Review the insights above and approve to generate the CIO report"
│   ├── Approve & Generate Report button
│   └── Re-run Analysis button
│
└── Report Section (visible after approval)
    ├── Success message: "Report generated: {path}"
    ├── Download Report button (downloads HTML file)
    └── Worker Status Timeline (expandable)
        └── {worker}: {status} — {message} (one row per worker)
```

### 4.2 CLI Information Hierarchy

```
python main.py
│
├── --mode demo|realtime      MODE SELECTION
├── --generate-data           DEMO: Generate synthetic events
├── --generate-snippet        REALTIME: Generate embed snippet
├── --run                     START ANALYSIS PIPELINE
├── --approve                 RESUME AFTER HUMAN REVIEW
│   └── --thread-id <UUID>    SPECIFY THREAD TO RESUME
├── --auto-approve            SKIP HUMAN GATE (demo / testing)
├── --days N                  DEMO: Analysis window in days (default 30)
├── --window-mins N           REALTIME: Analysis window in minutes (default 60)
├── --journey NAME            JOURNEY TO ANALYSE (default "onboarding")
└── --host URL                COLLECTOR HOST (for snippet generator)
```

### 4.3 HTML Report Information Hierarchy

```
CJI Analysis Report
│
├── Header Bar
│   ├── Title: "Customer Journey Intelligence"
│   ├── Journey Name
│   ├── Mode Badge: [DEMO] or [LIVE]
│   └── Timestamp
│
├── Charts Section (2 columns)
│   ├── Funnel Drop-off Chart (bar chart, blue)
│   │   └── Step → Drop-off percentage
│   └── Friction Score Chart (bar chart, colour-coded)
│       └── Step → Score (red/amber/green)
│
├── Executive Summary
│   └── 3-paragraph CIO narrative
│       ├── Para 1: Business impact and scale of friction
│       ├── Para 2: Root cause analysis by category
│       └── Para 3: Prioritised recommendations
│
├── Prioritised Findings Table
│   ├── Column: Rank (1–N)
│   ├── Column: Step
│   ├── Column: Issue Title
│   ├── Column: Category [badge]
│   ├── Column: Priority (P1–P5)
│   ├── Column: Effort [badge: low/medium/high]
│   └── Column: Recommended Fix
│
└── Footer
    ├── Generated by: CJI v2.0
    ├── Model: {LLM_MODEL}
    └── Timestamp: {generated_at}
```

---

## 5. Configuration Information Structure

### 5.1 Configuration Taxonomy

```
config.py
│
├── MODE
│   └── CJI_MODE: "demo" | "realtime"          ← Master mode switch
│
├── LLM PROVIDER
│   ├── LLM_MODEL: string                       ← Provider+model string
│   ├── LLM_TEMPERATURE: float                  ← 0.0 for deterministic
│   └── LLM_MAX_TOKENS: int                     ← Max response length
│
├── API KEYS (sensitive — never committed)
│   ├── ANTHROPIC_API_KEY
│   └── OPENAI_API_KEY
│
├── OBSERVABILITY
│   ├── LANGCHAIN_TRACING_V2: "true"|"false"
│   ├── LANGCHAIN_API_KEY
│   └── LANGCHAIN_PROJECT: "cji-poc"
│
├── PATHS (auto-created)
│   ├── ROOT: Path(__file__).parent
│   ├── DATA_DIR: ROOT / "data"
│   ├── EVENTS_PARQUET: DATA_DIR / "events.parquet"
│   ├── DUCKDB_PATH: DATA_DIR / "cji.duckdb"
│   └── CHROMA_DIR: DATA_DIR / "chroma"
│
├── COLLECTOR (realtime mode)
│   ├── COLLECTOR_HOST: URL
│   ├── COLLECTOR_PORT: int
│   ├── CJI_ADMIN_KEY: string                   ← Admin endpoint auth
│   └── COLLECTOR_API_KEY: "cji_dev_localtest"  ← Dev default key
│
├── AGENT BEHAVIOUR
│   ├── MAX_AGENT_ITERATIONS: 20               ← Safety cutoff
│   └── FRICTION_SCORE_THRESHOLD: 60           ← Critical flag threshold
│
├── REALTIME SETTINGS
│   ├── REALTIME_WINDOW_MINUTES: 60            ← Default analysis window
│   └── REALTIME_AUTO_RUN_INTERVAL: 0          ← Auto-refresh (0=disabled)
│
└── JOURNEY DEFINITION
    └── JOURNEY_CONFIG: dict
        ├── name: "onboarding"
        └── steps: [landing_page, sign_up_form, email_verification,
                    profile_setup, first_action, completion]
```

### 5.2 Environment Variable Loading Priority

```
1. System environment variables    HIGHEST PRIORITY
2. .env file (loaded by dotenv)
3. Default values in os.getenv()   LOWEST PRIORITY
```

### 5.3 Mode-Specific Configuration Behaviour

| Setting | Demo Mode | Realtime Mode |
|---|---|---|
| CJI_MODE | "demo" | "realtime" |
| Data source | EVENTS_PARQUET (Parquet file) | live_events (DuckDB table) |
| Window type | days (analysis_window_days) | minutes (REALTIME_WINDOW_MINUTES) |
| Collector | Not needed | Required (must be running) |
| tracker.js | Not needed | Required (embedded on client site) |

---

## 6. MCP Tool Information Taxonomy

### 6.1 Tool Classification

```
MCP Tools (14 total)
│
├── DATA ACCESS TOOLS (Journey Data MCP — mode-aware)
│   ├── get_system_info()           Read-only, no parameters
│   ├── get_funnel_steps()          Read-only, no parameters
│   ├── query_events()              Read-only, optional filters
│   ├── get_step_metrics()          Read-only, time window param
│   ├── get_funnel_dropoff()        Read-only, time window param
│   └── get_live_snapshot()         Read-only, minutes param
│
├── COMPUTATION TOOLS (Friction Engine MCP — stateless)
│   ├── score_friction()            Read-only, idempotent
│   ├── score_all_steps()           Read-only, idempotent
│   ├── detect_dropoffs()           Read-only, idempotent
│   └── correlate_signals()         Read-only, idempotent
│
├── LLM + VECTOR TOOLS (Insight MCP — stateful via ChromaDB)
│   ├── generate_insight()          Write (calls LLM)
│   ├── prioritise_fix()            Read, computation only
│   ├── save_insight()              Write (ChromaDB INSERT)
│   ├── search_insights()           Read (ChromaDB QUERY)
│   └── rank_all_fixes()            Write (calls LLM)
│
└── OUTPUT TOOLS (Report MCP — file write)
    ├── generate_narrative()        Write (calls LLM)
    └── export_report()             Write (creates HTML file)
```

### 6.2 Tool Input/Output Information Types

| Tool | Input Type | Output Type |
|---|---|---|
| get_system_info | None | Info dict |
| get_funnel_steps | None | Steps dict |
| query_events | str, int, int | Events list dict |
| get_step_metrics | int, int | Metrics list dict |
| get_funnel_dropoff | int, int | Funnel list dict |
| get_live_snapshot | int | Snapshot dict |
| score_friction | StepMetrics dict | FrictionScore dict |
| score_all_steps | list[StepMetrics] | Scored list dict |
| detect_dropoffs | list[funnel], float | Dropoffs dict |
| correlate_signals | list[scores] | Correlation dict |
| generate_insight | FrictionScore dict | Insight dict |
| prioritise_fix | Insight dict, int | Insight + priority dict |
| save_insight | Insight dict | Save confirmation dict |
| search_insights | str, int | Results list dict |
| rank_all_fixes | list[Insight] | Ranked + action plan dict |
| generate_narrative | insights, str, float, int, str | Narrative dict |
| export_report | str, str, list, list, list, str | Path + size dict |

### 6.3 Tool Call Sequence (per analysis run)

```
data_worker calls:
  1. get_system_info({})
  2. get_step_metrics({days_back: N} or {minutes_back: N})
  3. get_funnel_dropoff({days_back: N} or {minutes_back: N})
  4. get_funnel_steps({})
  5. [realtime only] get_live_snapshot({minutes: N})

friction_worker calls:
  1. score_all_steps({all_step_metrics: [...]})
  2. correlate_signals({scores: [...]})

insight_worker calls (per critical step):
  1. generate_insight({friction_score: score_dict})
  2. prioritise_fix({insight: insight_dict, unique_users: N})
  3. save_insight({insight: prioritised_insight})
Then once:
  4. rank_all_fixes({insights: all_insights})

report_worker calls:
  1. generate_narrative({insights, journey_name, avg_score, critical_count, mode})
  2. export_report({journey_name, narrative, friction_scores, insights, funnel_data, mode})
```

---

## 7. Agent State Information Model

### 7.1 CJIState Fields Classified by Phase

```
CJIState TypedDict fields:
│
├── IDENTITY (set at init, never change)
│   ├── mode: str                            "demo" | "realtime"
│   ├── journey_name: str                    e.g. "onboarding"
│   └── journey_steps: list[str]             6-element step list
│
├── CONFIGURATION (set at init, never change)
│   ├── analysis_window_days: int            demo window
│   ├── analysis_window_mins: int            realtime window
│   └── collector_url: str                   collector endpoint
│
├── ORCHESTRATION (modified every supervisor call)
│   ├── iteration: int                       monotonically increasing
│   ├── next_worker: str                     routing target
│   ├── human_approved: bool                 approval gate flag
│   └── last_run_at: str                     ISO timestamp
│
├── COMMUNICATION (append-only via add_messages reducer)
│   └── messages: list[BaseMessage]          agent conversation log
│
├── DATA PHASE (written by data_worker)
│   ├── raw_events: list[JourneyEvent]       sampled events
│   ├── event_summary: dict                  aggregate metrics
│   └── live_event_count: int               realtime event total
│
├── ANALYSIS PHASE (written by friction_worker)
│   ├── friction_scores: list[FrictionScore] per-step scores
│   └── critical_steps: list[str]           steps above threshold
│
├── INSIGHT PHASE (written by insight_worker)
│   ├── insights: list[Insight]             LLM root causes
│   └── prioritized_fixes: list[dict]       ranked action items
│
├── DELIVERY PHASE (written by report_worker)
│   ├── report_path: str                    path to HTML file
│   └── narrative: str                      CIO executive summary
│
└── OPERATIONS (append-only pattern)
    ├── worker_statuses: list[WorkerStatus] completion history
    └── errors: list[str]                   error accumulator
```

### 7.2 State Invariants

These must always hold at any checkpoint:

| # | Invariant |
|---|---|
| 1 | `iteration` is monotonically increasing (never decrements) |
| 2 | `worker_statuses` only grows (list concatenation, never overwrite) |
| 3 | `messages` only grows (add_messages reducer, never overwrite) |
| 4 | `human_approved` starts False, can only be set True via graph.update_state() |
| 5 | If `report_path` is non-empty, `insights` must also be non-empty |
| 6 | If `friction_scores` is non-empty, `event_summary` must also be non-empty |
| 7 | `next_worker` is always one of: {data_worker, friction_worker, insight_worker, report_worker, END, ""} |
| 8 | `mode` never changes after initial state is set |

### 7.3 State Lifecycle

```
Phase 0: Initialisation
└── All keys set to defaults, human_approved=auto_approve, iteration=0

Phase 1: Data Collection
└── event_summary, journey_steps, live_event_count populated

Phase 2: Friction Analysis
└── friction_scores, critical_steps populated

Phase 3: Insight Generation
└── insights, prioritized_fixes populated
└── ** CHECKPOINT: graph pauses if human_approved=False **

Phase 4: [Human Reviews]
└── Operator calls graph.update_state(config, {"human_approved": True}, as_node="supervisor")

Phase 5: Report Generation
└── report_path, narrative populated
└── Graph reaches END
```

---

## 8. Report Information Hierarchy

### 8.1 HTML Report Sections (in order)

```
Report Sections:
│
├── 1. Header Bar
│   ├── Brand: CJI logo/title
│   ├── Journey: {journey_name}
│   ├── Mode Badge: DEMO (green) | LIVE (blue)
│   └── Timestamp: {generated_at}
│
├── 2. Charts Grid (2 columns, equal width)
│   ├── Left: Funnel Drop-off Chart
│   │   ├── Type: Horizontal bar
│   │   ├── Data: step → drop_off_pct
│   │   └── Color: #378add (blue)
│   └── Right: Friction Score Chart
│       ├── Type: Horizontal bar
│       ├── Data: step → score
│       └── Colors: #e24b4a (≥70), #ef9f27 (50–69), #1d9e75 (<50)
│
├── 3. Executive Summary
│   ├── Section title: "Executive Summary"
│   └── 3-paragraph narrative text
│
├── 4. Prioritised Findings Table
│   ├── Column headers: Rank | Step | Issue | Category | Priority | Effort | Recommended Fix
│   └── Row per insight (sorted by priority ascending)
│
└── 5. Footer
    ├── "Generated by CJI v2.0"
    ├── "Model: {LLM_MODEL}"
    └── "Generated at: {ISO timestamp}"
```

### 8.2 Chart.js Configuration Reference

```javascript
// CDN: https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js

// Friction bar chart colours:
score >= 70 → '#e24b4a'  // red (critical)
score >= 50 → '#ef9f27'  // amber (elevated)
score  < 50 → '#1d9e75'  // green (acceptable)

// Funnel bar chart colour:
always → '#378add'        // blue

// Chart type: 'bar' (horizontal recommended)
// indexAxis: 'y' for horizontal orientation
```

---

## 9. Event Taxonomy

### 9.1 Allowed Event Types

```
ALLOWED_EVENT_TYPES = {
    "page_view",      # page loaded or SPA navigation
    "click",          # user clicked an element
    "form_submit",    # form submitted
    "error",          # JS error or unhandled rejection
    "rage_click",     # 3+ clicks on same element in 500ms
    "abandon",        # user left the page (beforeunload)
    "step_complete",  # user advanced to next step (SPA navigation)
    "identify"        # anonymous trait enrichment
}
```

### 9.2 Metadata Schemas Per Event Type

```
page_view:
  { "referrer": str, "title": str, "source": str }

click:
  { "element_tag": str, "element_id": str, "element_class": str, "text_preview": str (≤50 chars) }

form_submit:
  { "form_id": str, "form_action": str }

error:
  { "error_code": str, "error_message": str (≤200 chars), "source_file": str, "line": int }

rage_click:
  { "click_count": int, "element_tag": str, "element_id": str }

abandon:
  { "dwell_reason": "page_unload", "duration_ms": int }

step_complete:
  { "dwell_reason": "spa_navigate", "duration_ms": int }

identify:
  { "traits": dict }   # anonymised only — no PII
```

### 9.3 Error Code Taxonomy (Synthetic Data)

```
ERROR_CODES = [
    "TIMEOUT",          # network or operation timed out
    "VALIDATION_FAIL",  # form validation error
    "SERVER_500",       # backend error
    "TOKEN_EXPIRED"     # auth token expired
]
```

---

## 10. Navigation and Flow Maps

### 10.1 Demo Mode End-to-End Flow

```
START
  │
  ▼
[1. Data Generation]
  python main.py --mode demo --generate-data
  └── tools/synthetic_data.py → data/events.parquet
  │
  ▼
[2. MCP Servers Launch]  (auto-spawned as subprocesses by mcp_client.py)
  ├── journey_data_server.py  (reads Parquet via DuckDB VIEW)
  ├── friction_engine_server.py  (pure computation)
  ├── insight_server.py  (LLM + ChromaDB)
  └── report_server.py  (HTML generation)
  │
  ▼
[3. Analysis Pipeline]
  python main.py --mode demo --run
  ├── data_worker    → get_step_metrics, get_funnel_dropoff
  ├── friction_worker → score_all_steps, correlate_signals
  ├── insight_worker → generate_insight, prioritise_fix, save_insight, rank_all_fixes
  └── ** PAUSE ** (if not --auto-approve)
  │
  ▼
[4. Human Review]  (skipped with --auto-approve)
  Operator reviews insights in terminal/dashboard
  python main.py --approve --thread-id <UUID>
  │
  ▼
[5. Report Generation]
  report_worker → generate_narrative, export_report
  └── reports/cji_report_{journey}_{timestamp}.html
  │
  ▼
END
```

### 10.2 Realtime Mode End-to-End Flow

```
START
  │
  ▼
[1. Setup Collector]
  Terminal 1: uvicorn collector.api:app --port 8000
  └── DuckDB live_events table created
  └── Dev API key 'cji_dev_localtest' inserted
  │
  ▼
[2. Generate Embed Snippet]
  Terminal 2: python tracker/snippet_generator.py
  └── api_key.json (new key)
  └── embed_snippet.html (for client site <head>)
  └── verify_tracker.py (test script)
  └── useCJITracker.js (React hook if SPA)
  │
  ▼
[3. Client Website Tracking]
  Client pastes embed_snippet.html into <head>
  └── tracker.js loads async on each page
  └── Events captured: page_view, click, error, rage_click, abandon
  └── Events batched and POSTed to /collect/batch every 5s or 20 events
  └── Collector validates key → writes to live_events table
  │
  ▼
[4. Analysis Pipeline]
  Terminal 3: CJI_MODE=realtime python main.py --run --window-mins 60
  └── [same MCP/agent pipeline as demo mode]
  └── Journey Data MCP reads from live_events VIEW
  └── All downstream analysis identical to demo mode
  │
  ▼
[5. Human Review + Report] → same as demo mode steps 4-5
  │
  ▼
END
```

### 10.3 Dashboard Navigation Flow

```
Entry: streamlit run dashboard.py
    │
    ▼
Mode Selection (sidebar radio)
    ├── demo: uses synthetic data
    └── realtime: connects to collector API
    │
    ▼
[Realtime only] Collector Status Check
    ├── Online: proceed normally
    └── Offline: show warning + start command
    │
    ▼
Control: Run Analysis button
    │
    ▼
Progress Display (message per worker completion)
    ├── ✓ data_worker: "Fetched metrics for 6 steps"
    ├── ✓ friction_worker: "3 critical / 6 steps, avg=67"
    └── ✓ insight_worker: "3 insights generated"
    │
    ▼
Insights Review (expandable panels)
    └── One panel per insight with all fields
    │
    ▼
Approval Gate
    ├── Approve & Generate Report → report generated → download button shown
    └── Re-run Analysis → clears state, restarts pipeline
    │
    ▼
Report Download
    └── st.download_button → HTML file download
```
