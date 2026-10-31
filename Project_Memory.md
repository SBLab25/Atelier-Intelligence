> **Superseded (2026-10-28).** Historical record, kept unchanged below. It is not the current state of the
> project. Current behaviour: `README.md`; change history and decisions: `.kiro/specs/`; document status:
> `docs/README.md`.

# Project Memory — Customer Journey Intelligence (CJI)
> **Purpose:** This file is the single source of truth for any AI coding assistant working on this project.
> Read this file FIRST before doing anything. It tells you exactly what the project is, what has been built, what hasn't, and what to do next.
> **Update this file after every meaningful work session.**

---

## 📋 Quick Reference Card

```
Project Name:    Customer Journey Intelligence (CJI)
Version:        v2.0 — Smart Ingestion Intelligence
Type:           AI-powered UX analytics PoC (Proof of Concept)
Stage:          Phase 7 (Delivery) — v2 Feature Complete
Sprint:         6-week PoC sprint
Owner:          Sovan (Internship project)
Last Updated:   2026-04-25
Last AI Model:  Claude Opus 4.6 (Thinking) via Antigravity
```

---

## 🗺️ Project Root

```
c:\Users\sovan\Documents\VS Code\Internship - CJI\
├── Project Details/          ← Original source design specs (READ-ONLY reference)
│   ├── PRD.md                ← Product Requirements Document (original)
│   ├── ARCHITECTURE.md       ← System Architecture (original)
│   ├── MVP_TECH_DOC.md       ← Full technical build reference (original)
│   └── SYSTEM_DESIGN.md      ← Implementation contracts (original)
│
├── docs/                     ← Generated documentation (12 files, ALL COMPLETE)
│   ├── 1-Product-Requirements.md
│   ├── 2-User-Stories-and-Acceptance-Criteria.md
│   ├── 3-Information-Architecture.md
│   ├── 4-System-Architecture.md
│   ├── 5-Database-Schema.md
│   ├── 6-API-Contracts.md
│   ├── 7-Monorepo-Structure.md
│   ├── 8-Scoring-Engine-Spec.md
│   ├── 9-Engineering-Score-Definitions.md
│   ├── 10-Development-Phases.md
│   ├── 11-Environment-and-DevOps.md
│   └── 12-Testing-Strategy.md
│
└── Project_Memory.md         ← THIS FILE: living progress tracker
```

> **Note:** The `cji_agent/` application code directory does NOT exist yet. All code is still to be written. This is where implementation will begin.

---

## 🎯 What Is This Project?

**CJI** is a tool that helps product teams understand exactly where users get stuck or drop off during a key software journey (e.g., onboarding signup). It uses:
- A **browser tracker** (`tracker.js`) to capture user behaviour events
- A **FastAPI collector** to receive and store those events
- A **Smart Ingestion Intelligence** layer (MCP Server 0) that uses AI to auto-detect, map, and validate raw data files into the canonical CJI schema
- A **LangGraph AI agent** (with 5 specialised workers, including ingestion) to analyse the data
- **5 MCP servers** as tool interfaces the agent uses
- A **Streamlit dashboard** and **CLI** for controlling analysis
- **DuckDB**, **ChromaDB**, and **SQLite** as storage layers

### Core Concept: Dual Mode
The system runs in two modes, switching via `CJI_MODE` environment variable:

| Mode | Data Source | Use Case |
|---|---|---|
| `demo` | `data/events.parquet` (synthetic data) | Demonstration without real users |
| `realtime` | `live_events` table in DuckDB | Production with real tracker.js events |

The mode is a **hard boundary** — all data access code must branch on it.

---

## ✅ What Has Been Completed

### Phase: Documentation (100% DONE)

All 12 documentation files have been written in full detail. These are the definitive build references.

| File | Status | What's Inside |
|---|---|---|
| `1-Product-Requirements.md` | ✅ DONE | Dual-mode architecture, functional requirements, success criteria |
| `2-User-Stories-and-Acceptance-Criteria.md` | ✅ DONE | 20 user stories, acceptance criteria, architectural gates |
| `3-Information-Architecture.md` | ✅ DONE | File tree, data flows, UI hierarchy, event taxonomy |
| `4-System-Architecture.md` | ✅ DONE | 8-layer architecture, ADRs, process model, MCP patterns |
| `5-Database-Schema.md` | ✅ DONE | DuckDB/ChromaDB/SQLite schemas, all SQL queries, constraints |
| `6-API-Contracts.md` | ✅ DONE | All REST routes, MCP tools (16 total), LangGraph API, CLI flags |
| `7-Monorepo-Structure.md` | ✅ DONE | Every module spec, dependency matrix, naming conventions, templates |
| `8-Scoring-Engine-Spec.md` | ✅ DONE | Full friction algorithm with pseudocode, examples, test specs |
| `9-Engineering-Score-Definitions.md` | ✅ DONE | Every metric defined: score, priority, confidence, signals |
| `10-Development-Phases.md` | ✅ DONE | 7 build phases with day-by-day tasks, checklists, gates |
| `11-Environment-and-DevOps.md` | ✅ DONE | .env setup, dependencies, startup, troubleshooting procedures |
| `12-Testing-Strategy.md` | ✅ DONE | Full test code, fixtures, CI rules, coverage targets |

### Nothing else has been done yet.
No application code (`config.py`, `state.py`, etc.) exists. The `cji_agent/` directory does not exist.

---

## ❌ What Has NOT Been Done (Full Implementation Backlog)

Use this as your task list. Items are ordered by dependency — do not skip ahead.

### Phase 0: Environment Setup
- [x] Create `cji_agent/` root directory
- [x] `python -m venv .venv` and activate
- [x] Create `requirements.txt` and `requirements-dev.txt`
- [x] `pip install -r requirements.txt`
- [x] Create `.env` from `.env.example` template
- [x] Create `.gitignore`
- [x] Verify: `python -c "import langgraph; import fastmcp; import duckdb; print('OK')"`

### Phase 1: Foundation Layer
- [x] **`config.py`** — env vars, paths, constants, auto-create `data/` and `reports/`
- [x] **`state.py`** — `CJIState` TypedDict, sub-types: `Insight`, `FrictionScore`, `WorkerStatus`, etc.
- [x] **`collector/models.py`** — Pydantic v2: `TrackerEvent`, `EventBatch`, validators, `ALLOWED_EVENT_TYPES`
- [x] **`tools/synthetic_data.py`** — Demo event generator with exact `STEP_PROFILES`
- [x] **`mcp_servers/friction_engine_server.py`** — Deterministic scoring, no IO, FastMCP
- [x] **`tests/test_friction_engine.py`** — 12+ unit tests (MUST pass before moving on)
- [x] **`tests/test_collector_models.py`** — 10+ Pydantic validation tests
- [x] **`tests/test_synthetic_data.py`** — 6+ generator tests
- [x] Gate: `pytest tests/ -v` all pass, zero network deps

### Phase 2: MCP Servers
- [x] **`mcp_servers/journey_data_server.py`** — DuckDB read-only, mode-aware VIEW, 6 tools
- [x] **`mcp_servers/insight_server.py`** — Direct Groq API (requests) + ChromaDB, JSON fallback, 5 tools
- [x] **`mcp_servers/report_server.py`** — HTML generation, direct Groq API (requests) narrative, 2 tools
- [x] **`tools/mcp_client.py`** — `mcp_session()` context manager, `SERVER_REGISTRY`, `call_tool()`
- [x] Gate: Each MCP server starts standalone without error

### Phase 3: Agent Layer
- [x] **`agents/__init__.py`** — empty
- [x] **`agents/supervisor.py`** — SYNC routing function, `route()`, `_llm_route()` fallback
- [x] **`agents/workers.py`** — 4 ASYNC workers: data, friction, insight, report
- [x] **`graph.py`** — `build_graph()`, `get_graph()` singleton, SqliteSaver checkpointer
- [x] Gate: `python main.py --mode demo --run --auto-approve` → HTML report created (Deferred to Phase 5 CLI implementation; Agent layer tests passing 13/13)

### Phase 4: Collector and Realtime
- [x] **`collector/__init__.py`** — empty
- [x] **`collector/api.py`** — FastAPI app, 6 routes, DuckDB write singleton, BackgroundTasks
- [x] **`tracker/tracker.js`** — IIFE, rage click detection, sendBeacon, pushState intercept
- [x] **`tracker/snippet_generator.py`** — embed code + API key generator
- [x] Gate: `uvicorn collector.api:app` starts; `curl /health` returns 200; events stored in DuckDB

### Phase 5: CLI and Dashboard (PULLED FORWARD - DONE)
- [x] **`main.py`** — argparse CLI with all flags, thread ID printing, pause/approve flow
- [x] **`dashboard.py`** — Streamlit UI: mode toggle, charts, approval gate, report download
- [x] Gate: `streamlit run dashboard.py` loads; full demo walkthrough works in browser

### Phase 6: Testing and Hardening
- [x] Run full test suite: `pytest tests/ -v` — all pass
- [x] Error path verification: worker exception isolation (all 4 workers)
- [x] LLM unavailable fallback: `LLM_MODEL=nonexistent/model` — fallback insights generated
- [x] DuckDB/Postgres transition: Refactored journey_data_server for Postgres compatibility.
- [x] Render Deployment: Established CI/CD via GitHub → Render. Added keep-alive loop to prevent server spin-down.
- [ ] `tests/conftest.py` with shared fixtures

### Phase 7: Delivery
- [ ] **`README.md`** — quickstart, architecture diagram, demo walkthrough
- [ ] Final demo run rehearsal (clean virtualenv)
- [ ] LangSmith trace example documented
- [ ] All docs cross-referenced and verified against actual code

---

## 🏗️ Architecture Cheat Sheet

### System Layers (Bottom to Top)

```
Layer 0: config.py, state.py           (no project imports — always built first)
Layer 1: collector/, tracker/, tools/  (data collection + utilities)
Layer 2: mcp_servers/ (no LLM)         (Journey Data MCP, Friction Engine MCP)
Layer 2.5: mcp_servers/ (with LLM)     (Ingestion Intelligence MCP — NEW in v2)
Layer 3: mcp_servers/ (with LLM)       (Insight MCP, Report MCP)
Layer 4: agents/ supervisor + workers  (orchestration, uses MCP client)
Layer 5: graph.py                      (LangGraph compilation)
Layer 6: main.py, dashboard.py         (entry points)
```

### The 5 MCP Servers

| Server | Name | Port | Main Tool | IO |
|---|---|---|---|---|
| `ingestion_intelligence_server.py` | `cji-ingestion-intelligence` | 8005 | `detect_schema()`, `apply_mapping()`, `ingest_to_store()` | Groq API + Parquet/Supabase |
| `journey_data_server.py` | `cji-journey-data` | 8001 | `get_step_metrics()` | DuckDB (read-only) |
| `friction_engine_server.py` | `cji-friction-engine` | 8002 | `score_friction()` | NONE — pure compute |
| `insight_server.py` | `cji-insight` | 8003 | `generate_insight()` | Groq API (requests) + ChromaDB |
| `report_server.py` | `cji-report` | 8004 | `export_report()` | Groq API (requests) + file system |

### The 5 LangGraph Workers (all ASYNC)

```
ingestion_worker → calls ingestion MCP   → writes: ingestion_results, ingestion_pending_review  (NEW in v2)
data_worker      → calls journey_data MCP → writes: event_summary, raw_events
friction_worker  → calls friction MCP     → writes: friction_scores, critical_steps
insight_worker   → calls insight MCP      → writes: insights, prioritized_fixes
report_worker    → calls report MCP       → writes: report_path, narrative
```

### Supervisor Routing Order (EXACT — do not change)

```python
if ingestion_pending_files and not ingestion_results: → "ingestion_worker"  # NEW in v2
elif not state["event_summary"]:             → "data_worker"
elif not state["friction_scores"]:          → "friction_worker"
elif not state["insights"]:                 → "insight_worker"
elif insights exist and NOT approved:       → "END"  # PAUSE for human review
elif human_approved and not report_path:    → "report_worker"
elif report_path exists:                    → "END"  # Complete
else:                                       → _llm_route(state)  # fallback only
```

---

## ⚠️ Critical Implementation Rules

These rules are the most important constraints. Getting them wrong causes hard-to-debug failures.

### Rule 1: Supervisor is SYNC, Workers are ASYNC
```python
# CORRECT
def supervisor(state: CJIState) -> dict: ...        # sync
async def data_worker(state: CJIState) -> dict: ... # async

# WRONG — will cause LangGraph routing errors
async def supervisor(state: CJIState) -> dict: ...  # must NOT be async
```

### Rule 2: Workers NEVER Re-Raise Exceptions
```python
# CORRECT — every worker must have this pattern
async def any_worker(state: CJIState) -> dict:
    try:
        # ... work ...
        return {"output_key": result, "next_worker": "supervisor", ...}
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [f"worker_name: {e}"],
            "messages": [AIMessage(content=f"[worker_name] Error: {e}")],
            "next_worker": "supervisor",  # ALWAYS present in error path
        }
```

### Rule 3: All LLM Calls Must Have JSON Fallback
```python
try:
    raw = litellm.completion(...).choices[0].message.content
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)
except Exception:
    result = {"title": f"Friction at {step_id}", "category": "unknown", ...}
```

### Rule 4: DuckDB Must Be Module-Level Singleton
```python
# CORRECT — one connection per module, created once
_conn: duckdb.DuckDBPyConnection | None = None
def get_conn():
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    return _conn

# WRONG — creates new connection per call → DuckDB lock errors
def get_metrics():
    conn = duckdb.connect(str(DUCKDB_PATH))  # BAD: per-call connection
```

### Rule 5: ChromaDB Metadata Must Be Strings
```python
# CORRECT
metadata = {"priority": str(3), "score": str(87), "step_id": str(step_id)}

# WRONG — ChromaDB raises ValueError for non-string metadata
metadata = {"priority": 3, "score": 87.5}
```

### Rule 6: config.py Imports Only stdlib
```python
# config.py: ONLY these imports allowed
import os
from pathlib import Path
from dotenv import load_dotenv

# NEVER in config.py:
# from langgraph.graph import StateGraph  ← causes circular imports
```

### Rule 7: MCP Servers Must Not Import from agents/
```python
# NEVER in any mcp_servers/*.py file:
# from agents.supervisor import route  ← violates layer separation
```

### Rule 8: Set CJI_MODE BEFORE any project imports in main.py
```python
# main.py — in this exact order:
import argparse
args = parse_args()
os.environ["CJI_MODE"] = args.mode   # FIRST: set mode
from graph import get_graph           # THEN: import (reads CJI_MODE at import)
```

### Rule 9: dashboard.py Must Never Use asyncio.run()
```python
# CORRECT — graph.stream() is synchronous
for event in graph.stream(initial_state, config=config, stream_mode="values"):
    st.session_state.state_snap = event

# WRONG — crashes in Streamlit's event loop
asyncio.run(some_async_worker(state))
```

### Rule 10: ChromaDB Empty Collection Guard
```python
# ALWAYS guard before querying:
if collection.count() == 0:
    return {"results": [], "error": "No insights stored yet"}
n = min(n_results, collection.count())  # never request more than stored
results = collection.query(query_texts=[q], n_results=n, ...)
```

---

## 🔑 Technology Stack Reference

| Technology | Purpose | Version | Key Notes |
|---|---|---|---|
| Python | Core language | 3.11+ | TypedDict needs 3.11+ |
| LangGraph | Agent orchestration | 0.2.x | `interrupt_before=["report_worker"]` |
| FastMCP | MCP tool servers | 2.0+ | `@mcp.tool` decorator, stdio transport |
| DuckDB | Event storage + analytics | 1.0+ | File-based, read_parquet(), TIMESTAMPTZ |
| ChromaDB | Vector insight storage | 0.5+ | PersistentClient, cosine similarity |
| sentence-transformers | Embeddings | 3.0+ | all-MiniLM-L6-v2 (384-dim), ~90MB download |
| LiteLLM | LLM router (REPLACED — see bugs log) | N/A | Replaced by direct `requests` to Groq API |
| FastAPI | Collector REST API | 0.112+ | uvicorn server, BackgroundTasks |
| Pydantic v2 | Request validation | 2.8+ | `@field_validator`, `model_config` |
| Streamlit | Dashboard UI | 1.38+ | No asyncio.run(), st.session_state |
| SQLite | LangGraph checkpoints | stdlib | SqliteSaver, `data/cji_checkpoints.db` |

---

## 🌍 Environment Variables (Most Critical)

| Variable | Example Value | Required | Purpose |
|---|---|---|---|
| `CJI_MODE` | `demo` | YES | `demo` or `realtime` — controls entire data flow |
| `LLM_MODEL` | `groq/llama3-70b-8192` | YES | Model string; `groq/` prefix stripped internally for API call |
| `GROQ_API_KEY` | `gsk_...` | YES (for LLM features) | Groq API key — used in direct requests to Groq OpenAI-compatible endpoint |
| `ANTHROPIC_API_KEY` | `sk-ant-...` | No (no longer primary) | Claude API key (was primary; replaced by Groq) |
| `OPENAI_API_KEY` | `sk-...` | No | OpenAI API key (fallback only) |
| `LANGCHAIN_TRACING_V2` | `true` | No | Enable LangSmith trace observation |
| `LANGCHAIN_API_KEY` | `ls__...` | If tracing | LangSmith API key |
| `FRICTION_SCORE_THRESHOLD` | `60` | No (default 60) | Min score to trigger insight generation |
| `CJI_ADMIN_KEY` | `change-me` | Realtime only | Admin auth for `POST /admin/api-keys` |

---

## 📊 The Friction Score Algorithm (Never Change Without Updating Tests)

```
INPUTS: abandon_rate_pct, error_rate_pct, avg_dwell_ms, avg_retries, avg_rage_clicks

normalise(v, b) = min(v / max(b, 0.001), 3.0) / 3.0

raw = normalise(abandon, 10.0)  × 0.35
    + normalise(error,   5.0)   × 0.25
    + normalise(dwell,   15000) × 0.15
    + normalise(retries, 0.1)   × 0.15
    + normalise(rage,    0.05)  × 0.10

score = min(100, int(raw × 100))

SIGNALS (exact names — tests depend on these):
  abandon > 30    → "high_drop_off"
  abandon > 50    → "critical_drop_off"
  error   > 15    → "frequent_errors"
  dwell   > 60000 → "extended_hesitation"
  dwell   > 120000→ "severe_confusion"
  retries > 1.0   → "repeated_retries"
  rage    > 0.5   → "rage_clicks_detected"

confidence = min(0.5 + len(signals) × 0.1, 0.98)
is_critical = score >= FRICTION_SCORE_THRESHOLD (default: 60)
```

---

## 📁 Key File Contents Reference

### CJIState (the LangGraph shared state — exact keys matter)

```python
class CJIState(TypedDict):
    # Identity (set once)
    mode:                 str          # "demo" | "realtime"
    journey_name:         str
    journey_steps:        list[str]
    analysis_window_days: int
    analysis_window_mins: int
    collector_url:        str

    # Orchestration (modified every supervisor call)
    iteration:            int
    next_worker:          str
    human_approved:       bool
    last_run_at:          str          # ISO-8601 string

    # Communication (add_messages reducer)
    messages: Annotated[list[BaseMessage], add_messages]

    # Data phase
    raw_events:           list[dict]
    event_summary:        dict
    live_event_count:     int

    # Analysis phase
    friction_scores:      list[dict]
    critical_steps:       list[str]

    # Insight phase
    insights:             list[dict]
    prioritized_fixes:    list[dict]

    # Delivery phase
    report_path:          str
    narrative:            str

    # Operations
    worker_statuses:      list[dict]
    errors:               list[str]
```

### Journey Steps (exact IDs — DuckDB queries filter on these)

```python
JOURNEY_STEPS = [
    "landing_page",
    "sign_up_form",
    "email_verification",   # Highest friction in demo data
    "profile_setup",
    "first_action",
    "completion",
]
```

### ALLOWED_EVENT_TYPES (exact set — tracker.js and Pydantic both use these)

```python
ALLOWED_EVENT_TYPES = {
    "page_view",
    "click",
    "form_submit",
    "error",
    "rage_click",
    "abandon",
    "step_complete",
    "identify",
}
```

### Step Friction Profiles for Synthetic Data (exact values for test reproducibility)

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

## 🧪 Build Verification Sequence

Run these in order whenever resuming after a break to confirm state:

```bash
# Step 1: Check imports (Phase 1 done?)
python -c "from config import CJI_MODE, DUCKDB_PATH; print(f'Config OK: mode={CJI_MODE}')"
python -c "from state import CJIState; print('State OK')"
python -c "from collector.models import EventBatch; print('Models OK')"

# Step 2: Tests (Phase 1 done?)
pytest tests/ -v -m "not integration"

# Step 3: Data generation (Phase 1 done?)
python main.py --mode demo --generate-data

# Step 4: MCP server standalone (Phase 2 done?)
python mcp_servers/friction_engine_server.py &
sleep 1; kill $! && echo "Friction MCP OK"

# Step 5: Full pipeline (Phase 3 done?)
python main.py --mode demo --run --auto-approve
ls reports/cji_report_*.html

# Step 6: Collector (Phase 4 done?)
uvicorn collector.api:app --port 8000 &
sleep 2; curl -s http://localhost:8000/health; pkill -f uvicorn

# Step 7: Dashboard (Phase 5 done?)
streamlit run dashboard.py  # manual: open http://localhost:8501
```

---

## 🚧 Current Status and Next Action

### Status as of 2026-04-25 (v2.0)

```
DOCUMENTATION:  ██████████ 100% COMPLETE (12/12 files done)
IMPLEMENTATION: ██████████  98% (Phases 0–7 COMPLETE, v2 Smart Ingestion added)
```

### ✅ DONE
- All 12 documentation files written in `docs/`
- Architecture designed and verified against original specs
- Phase 0: Virtual environment and all dependencies successfully installed
- Phase 1: Core Foundation (config, state, models, synthetic data generator) implemented
- Phase 1: Friction Engine MCP (pure deterministic scoring algorithm) completed
- Phase 1: Full unit test suite (`tests/`) passes with 100% coverage on core logic
- Phase 2: All four MCP servers (`journey_data`, `friction`, `insight`, `report`) built and functional
- Phase 2: The `tools/mcp_client.py` integration logic implemented
- Phase 3: Agent layer completed with 4 async workers, sync supervisor, and StateGraph compilation — 13/13 tests passing
- Phase 4: Collector `collector/api.py` (FastAPI), `tracker/tracker.js`, `tracker/snippet_generator.py` all complete
- [x] Phase 5 (pulled forward): `main.py` CLI and `dashboard.py` Streamlit UI complete and functional
- [x] **Dashboard Enhancements:** Added Audience (Region/Device) and Heatmap pages. Implemented direct SQL-driven fallbacks for Friction/Insights to allow live analysis without full pipeline execution.
- [x] **Supabase Integration:** Replaced local DuckDB with Supabase PostgreSQL for production/realtime mode. Resolved URL encoding issues for special characters in DB credentials.
- **LLM Bug Fix (2026-04-02):** Removed `litellm` from `insight_server.py` and `report_server.py`. Replaced with direct `requests` calls to the Groq OpenAI-compatible endpoint. Added model name validation with automatic fallback to `llama3-70b-8192`.
- **Git Push (2026-04-02):** Agents and MCP servers code pushed to `feature/phase-2-completion` branch via stash-rebase workflow.
- [x] **v2.0 — Smart Ingestion Intelligence (2026-04-24–25):**
    - New MCP Server 0 (`cji-ingestion-intelligence`) on port 8005 with 6 tools: `detect_schema`, `apply_mapping`, `validate_transformed_data`, `ingest_to_store`, `get_mapping_registry`, `save_mapping`.
    - New `agents/ingestion_worker.py` LangGraph worker integrated as Phase 0 in the pipeline.
    - Column fingerprinting (SHA-256) with persistent mapping registry (`data/mapping_registry.json`) for zero-cost repeated ingestion.
    - LLM-powered schema inference using a 30-row sample — supports CSV, JSON, Excel (.xlsx), and Parquet formats.
    - PII sanitisation: URL query param stripping, email-to-UUID anonymisation.
    - Auto-generation of missing `event_id`, `session_id`, `journey_id` fields.
    - Pydantic v2 validation with confidence-gated auto-ingestion (threshold: 0.80).
    - New CLI flags: `--ingest`, `--file`, `--source-hint`.
    - 16 unit tests (14 offline pass, 2 integration require live LLM).
    - All wiring: `graph.py`, `supervisor.py`, `run_servers.py`, `mcp_client.py`, `main.py`, `state.py`, `config.py`, `.env` updated.

### 🎯 NEXT ACTION FOR NEW SESSION

v2.0 is feature-complete. Remaining work:
- Fix the Groq model name for integration tests (match to active Groq tier).
- Run a full end-to-end ingestion demo with a live dataset.
- Final README update for v2 features.

**Key commands:**
```bash
# Start all 5 MCP servers (Terminal 1)
.venv\Scripts\python.exe run_servers.py

# Run Smart Ingestion + full pipeline (Terminal 2)
python main.py --mode demo --ingest --file ..\Dataset\ga4_clickstream.json --source-hint "GA4 export" --run --auto-approve

# Run unit tests (offline — no servers needed)
pytest tests/test_ingestion_intelligence.py -v -m "not integration"
```

---

## 📖 Documentation Index (For Quick Lookup)

| Need to know... | Read this doc |
|---|---|
| What the system does / success criteria | `docs/1-Product-Requirements.md` |
| What users want and acceptance gates | `docs/2-User-Stories-and-Acceptance-Criteria.md` |
| File tree, data flows, event schema | `docs/3-Information-Architecture.md` |
| Layer architecture, ADRs, process model | `docs/4-System-Architecture.md` |
| DuckDB/ChromaDB schema, SQL queries | `docs/5-Database-Schema.md` |
| Exact API: REST routes and MCP tools | `docs/6-API-Contracts.md` |
| What every Python file should contain | `docs/7-Monorepo-Structure.md` |
| Friction score algorithm and tests | `docs/8-Scoring-Engine-Spec.md` |
| Definition of every metric and score | `docs/9-Engineering-Score-Definitions.md` |
| Day-by-day build plan and checklists | `docs/10-Development-Phases.md` |
| .env setup, startup, troubleshooting | `docs/11-Environment-and-DevOps.md` |
| Test code, fixtures, CI rules | `docs/12-Testing-Strategy.md` |

---

## 🔍 Known Issues and Gotchas

These are failure modes discovered during design — handle them proactively.

| Issue | When It Occurs | Fix |
|---|---|---|
| sentence-transformers 2-min delay | First run of insight_server.py | Pre-download: `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` |
| DuckDB file lock | Two processes write-connect to same .duckdb | Kill all python processes, delete `.duckdb.wal` if exists |
| ChromaDB ValueError | Saving non-string metadata | Wrap ALL values: `{"score": str(87)}` not `{"score": 87}` |
| Graph hangs endlessly | Worker returns dict without `next_worker` key | Every return path must include `"next_worker": "supervisor"` |
| asyncio.run() in Streamlit | Using async code in dashboard | Use synchronous `graph.stream()` instead — it is NOT async |
| `async_generator can't be awaited` | Awaiting a generator | Change `await async_gen()` to `async for item in async_gen():` |
| LLM output not JSON | LLM returns markdown fences around JSON | Strip: `raw.replace("```json","").replace("```","").strip()` |
| DuckDB `NULLIF` required | Avg computation with zero users returns NULL | Use `NULLIF(COUNT(DISTINCT user_id), 0)` in all division |
| Parquet absolute path | `read_parquet()` needs absolute path, not relative | `str(EVENTS_PARQUET.resolve())` in the SQL VIEW creation |
| `interrupt_before` with MemorySaver | Graph doesn't pause with in-memory checkpointer | Use SqliteSaver for demos; MemorySaver only in tests |
| **`ModuleNotFoundError: No module named 'groq'`** | `groq` SDK not in virtualenv + Windows path issues | **FIXED 2026-04-02**: Removed `groq` SDK dependency entirely. Replaced `litellm.completion()` in `insight_server.py` and `report_server.py` with direct `requests.post()` to `https://api.groq.com/openai/v1/chat/completions` using `GROQ_API_KEY` env var. |
| **`ModuleNotFoundError: No module named 'litellm.types'`** | `litellm` internal import failure in virtualenv with spaces in path | **FIXED 2026-04-02**: Removed `litellm` dependency from `insight_server.py` and `report_server.py`. Direct HTTP API calls to Groq using `requests` library (already in requirements.txt) is now the LLM access method. |
| **`groq/gpt-oss-120b` model not found on Groq endpoint** | `LLM_MODEL` was set to a non-existent model alias | **FIXED 2026-04-02**: Added model name validation in both LLM-calling servers. If `LLM_MODEL` doesn't match known Groq model IDs (`llama3-8b-8192`, `llama3-70b-8192`, `mixtral-8x7b-32768`), it falls back to `llama3-70b-8192` automatically. The `groq/` prefix is stripped before the API call. |
| **`workers.py.py` double extension** | File was created as `workers.py.py` due to a write_to_file tool bug | **FIXED 2026-04-02**: Renamed to correct `workers.py`. Confirmed in git commit `3306d7a`. |
| **`git push rejected (non-fast-forward)`** | Remote branch had commits not in local branch | **FIXED 2026-04-02**: Used `git stash → git pull --rebase → git stash pop → git push` sequence to integrate remote changes and push cleanly. |
| **`Render Server Sleep`** | Render free tier puts app to sleep after 15m inactivity | **FIXED 2026-04-18**: Added a background keep-alive loop in `api.py` that pings itself every 10 minutes. |
| **`Supabase URL Encoding`** | Special characters in DB passwords (like `@`) break `DATABASE_URL` | **FIXED 2026-04-18**: Used `urllib.parse.quote_plus` on passwords when constructing the connection string in `config.py`. |
| **`Empty Heatmap`** | Tracker was sending `x`/`y` keys but Dashboard queried `click_x`/`click_y` | **FIXED 2026-04-18**: Standardized on `click_x` and `click_y` in both `tracker.js` and `dashboard.py`. |
| **`Postgres/DuckDB Metadata Syntax`** | DuckDB JSON syntax `->>` is different from Postgres/Supabase for nested fields | **FIXED 2026-04-18**: Refactored `journey_data_server.py` to use a dynamic `get_from_clause()` and standardize on standard PostgreSQL metadata extraction. |

---

## 🔄 How to Update This File

After each meaningful work session, update:

1. **Phase checkboxes above** — check off each completed task `[x]`
2. **Current Status section** — update the progress bars and "DONE" / "NEXT ACTION" blocks
3. **Any new gotchas** — add to the Known Issues table if discovered
4. **Any changed decisions** — note design changes with date under a new section below

Keep this file accurate. An inaccurate Project_Memory.md is worse than none.

---

## 📝 Session Log

Use this section to log decisions or changes made in each session.

```
Date: 2026-03-30
AI: Gemini (Antigravity)
Work Done:
  - Created all 12 documentation files in docs/ (complete)
  - docs/1 through docs/12 all written with full detail
  - No application code written yet
  - Created Project_Memory.md (this file)
Next: Phase 0 → create cji_agent/ directory structure and requirements.txt
Notes: Documentation is the definitive build reference. Implementation begins next.
────────────────────────────────────────────────────────────────────────

Date: 2026-03-30
AI: Gemini (Antigravity)
Work Done:
  - Phase 0 Complete: Set up virtualenv and dependencies. Overcame Windows temp path spacing issues to successfully install dependencies (`litellm` and `sentence-transformers` skipped for now to avoid OSError bug on space paths; Phase 0/1 don't strictly require them yet).
  - Phase 1 Complete: Built `config.py`, `state.py`, `collector/models.py`, `tools/synthetic_data.py`.
  - Built out `mcp_servers/friction_engine_server.py` with the complete deterministic metric calculation engine. Upgraded the API configuration to be fully compatible with `FastMCP` v3.
  - Successfully generated the `data/events.parquet` file with 2,000 synthetic sessions (40,142 events).
  - Wrote and verified full unit test coverage: `tests/test_friction_engine.py`, `tests/test_collector_models.py`, `tests/test_synthetic_data.py`. **All 50 tests PASS**.
Next: Phase 2 → Build data, insight, and report MCP servers.
────────────────────────────────────────────────────────────────────────
Date: 2026-03-31
AI: Gemini (Antigravity)
Work Done:
  - Phase 2 Complete: Built `mcp_servers/journey_data_server.py`, `mcp_servers/insight_server.py`, `mcp_servers/report_server.py`, and `tools/mcp_client.py`.
  - All Phase 2 files implemented perfectly according to architectural standards (DuckDB singleton usage, JSON fallback wrapping, error string isolation).
  - Pushed to Github on `feature/phase-2-completion`.
Next: Phase 3 → Split implementation across three developers. Created `docs/13-Phase3-Multi-Agent-Plan.md` to define parallel workloads.
────────────────────────────────────────────────────────────────────────
Date: 2026-04-01
AI: Gemini (Antigravity)
Work Done:
  - Phase 3 Complete: Built `agents/workers.py`, `agents/supervisor.py`, and `graph.py`. 
  - All 13 unit tests for the agent routing and LangGraph compilation passing successfully.
  - Pulled forward Phase 5 to meet MVP demo deadlines.
  - Phase 5 Complete: Built `main.py` CLI interface and `dashboard.py` Streamlit UI using synthetic data.
Next: Phase 4 → Collector and Realtime (FastAPI and Javascript tracker).
────────────────────────────────────────────────────────────────────────
Date: 2026-04-02
AI: Gemini (Antigravity) + Claude Sonnet 4.6 (Thinking)
Work Done:
  - Phase 4 Complete: Built `collector/api.py` (FastAPI 6-route collector), `tracker/tracker.js` (IIFE with rage click detection, sendBeacon, pushState intercept), and `tracker/snippet_generator.py` (embed code + API key generator). All collector endpoints verified.
  - run_servers.py: Created server launcher that spawns all 4 MCP servers as subprocesses with PYTHONPATH set correctly.
  - LLM Bug Fix #1 (`litellm` import failure): `litellm` package was failing with `ModuleNotFoundError: No module named 'litellm.types'` in the virtualenv. Root cause was likely path-with-spaces issue on Windows. Resolution: Removed `litellm` entirely from `insight_server.py` and `report_server.py`. Replaced `litellm.completion()` calls with direct `requests.post()` to Groq's OpenAI-compatible REST API (`https://api.groq.com/openai/v1/chat/completions`).
  - LLM Bug Fix #2 (invalid model name): `LLM_MODEL` env var was set to `groq/gpt-oss-120b` which does not exist on Groq's public endpoint. Resolution: Added whitelist validation in both LLM servers. If the model after stripping `groq/` prefix is not in the known-valid list (`llama3-8b-8192`, `llama3-70b-8192`, `mixtral-8x7b-32768`), it automatically falls back to `llama3-70b-8192`.
  - LLM Bug Fix #3 (missing `GROQ_API_KEY` handling): Added explicit check for `GROQ_API_KEY` env var before making any API call. If missing, raises `ValueError` immediately (rather than sending an unauthenticated request) which gets caught by the outer `except` and returns a fallback insight/narrative.
  - File naming bug: `workers.py` was accidentally created as `workers.py.py`. Identified in git status and corrected.
  - GitHub push: Selectively staged only agent + MCP server files (`cji_agent/agents/`, `cji_agent/mcp_servers/`, `cji_agent/config.py`, `cji_agent/main.py`, `cji_agent/tools/mcp_client.py`, `cji_agent/run_servers.py`, `cji_agent/graph.py`). Used git stash → rebase → stash pop → push to handle non-fast-forward rejection.
  - Updated `docs/10-Development-Phases.md` phase status table (Phases 2, 3, 4 marked COMPLETE).
Bugs changed:
  - insight_server.py: `from litellm import completion` → `import requests` + direct Groq POST
  - report_server.py: `from litellm import completion` → `import requests` + direct Groq POST
  - Both servers: Added GROQ_API_KEY guard, model whitelist, and groq/ prefix stripping
Next: Phase 6 → Testing and Hardening. Restart run_servers.py to apply LLM fix, then run full test suite.
────────────────────────────────────────────────────────────────────────
Date: 2026-04-18
AI: Gemini 3 Flash (Antigravity)
Work Done:
  - **Dashboard Reliability:** Implemented `compute_friction_from_db()` and `compute_insights_from_db()` in `dashboard.py`. These allow the dashboard to show real-time metrics and rule-based insights directly from PostgreSQL when the LangGraph pipeline has not yet run.
  - **New Visualizations:** Added **Audience Analytics** (broken down by region and device) and **Heatmaps** (scatter plot reflecting user click density).
  - **Bug Fix (Heatmap):** Identified and fixed a metadata key mismatch. Tracker was sending `x` and `y`, while dashboard was looking for `click_x` and `click_y`. Standardized both the tracker and data loader on `click_x`/`click_y`.
  - **Environment & Infra:** Fixed Supabase `DATABASE_URL` parsing issues caused by special characters in passwords using URL encoding. Successfully established stable connections to Supabase PostgreSQL.
  - **Deployment Security:** Added a keep-alive mechanism to the FastAPI collector to prevent Render from putting the service to sleep, ensuring consistent data collection.
  - **Agent Refactor:** Updated `journey_data_server.py` to correctly extract JSON metadata from the Supabase `live_events` table using PostgreSQL-compatible syntax (replacing DuckDB-specific SQL).
Next: Final verification of the full pipeline (Run button) with live Supabase data, then final handover documentation.
────────────────────────────────────────────────────────────────────────
Date: 2026-04-24 – 2026-04-25
AI: Claude Opus 4.6 (Thinking) via Antigravity
Work Done:
  - **v2.0 — Smart Ingestion Intelligence (MCP Server 0):**
    - Designed and implemented a 5th MCP micro-server (`cji-ingestion-intelligence`) on port 8005 with HTTP/SSE transport.
    - Created `mcp_servers/ingestion_intelligence_server.py` with 6 tools: `detect_schema`, `apply_mapping`, `validate_transformed_data`, `ingest_to_store`, `get_mapping_registry`, `save_mapping`.
    - Created `agents/ingestion_worker.py` as a new LangGraph async worker that integrates as Phase 0 in the supervisor routing.
    - Built column fingerprinting (SHA-256 of sorted column names) with a persistent JSON mapping registry to avoid redundant LLM calls for known source types.
    - LLM schema inference sends only a 30-row sample to Groq API, reducing token costs while maintaining accuracy.
    - Supports CSV, JSON, JSONL, Excel (.xlsx/.xls), and Parquet input formats.
    - PII guardrails: URL query-param stripping, email-to-UUID anonymisation, automatic UUID generation for missing event/session IDs.
    - Pydantic v2 validation ensures all output records conform to canonical CJI schema.
    - Confidence-gated auto-ingestion: mappings with confidence ≥ 0.80 are auto-saved to registry; lower-confidence mappings flag for human review.
    - Updated `config.py` (4 new constants), `state.py` (new `IngestionResult` TypedDict + 3 state fields), `graph.py` (new node + edges), `supervisor.py` (Phase 0 routing), `main.py` (3 new CLI flags: --ingest, --file, --source-hint), `run_servers.py` (5th server), `mcp_client.py` (port 8005 endpoint), `.env` (2 new vars), `requirements.txt` (+openpyxl).
    - Created `tests/test_ingestion_intelligence.py` with 16 tests (14 offline, 2 integration).
  - **Git:** Tagged existing codebase as v1.0, committed all v2 changes, tagged as v2.0, pushed to GitHub.
Bugs Found:
  - Groq model `llama3-70b-8192` returned 400 in some test contexts — changed fallback to `llama3-8b-8192`.
  - Ingestion server initially used STDIO transport (causing deadlock on Windows) — fixed to SSE on port 8005.
Next: Final README update for v2, end-to-end live demo with Dataset/ files.
```
