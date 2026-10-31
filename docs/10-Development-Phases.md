> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Development Phases
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** Development Roadmap and Phase Specification

---

## Table of Contents

1. [Phase Overview](#1-phase-overview)
2. [Phase 0: Environment Setup (Day 1)](#2-phase-0-environment-setup-day-1)
3. [Phase 1: Foundation Layer (Days 2–5)](#3-phase-1-foundation-layer-days-25)
4. [Phase 2: MCP Servers (Days 6–12)](#4-phase-2-mcp-servers-days-612)
5. [Phase 3: Agent Layer (Days 13–18)](#5-phase-3-agent-layer-days-1318)
6. [Phase 4: Realtime Mode (Days 19–25)](#6-phase-4-realtime-mode-days-1925)
7. [Phase 5: Dashboard and CLI Polish (Days 26–30)](#7-phase-5-dashboard-and-cli-polish-days-2630)
8. [Phase 6: Testing and Hardening (Days 31–35)](#8-phase-6-testing-and-hardening-days-3135)
9. [Phase 7: Demo Rehearsal and Delivery (Days 36–42)](#9-phase-7-demo-rehearsal-and-delivery-days-3642)
10. [Build Verification Sequence](#10-build-verification-sequence)
11. [Rollback Procedures](#11-rollback-procedures)
12. [Post-PoC Roadmap](#12-post-poc-roadmap)

---

## 1. Phase Overview

### 1.1 PoC Development Timeline

| Phase | Days | Key Deliverables | Gate |
|---|---|---|---|
| 0: Setup | 1 | Virtualenv, dependencies, .env configured | `python -c "import config"` passes |
| 1: Foundation | 2–5 | config.py, state.py, synthetic_data.py, test_friction_engine.py | `pytest tests/ -v` all pass |
| 2: MCP Servers | 6–12 | All 4 MCP servers independently runnable | Each server responds to tool call | (COMPLETE)
| 3: Agent Layer | 13–18 | LangGraph graph compiles, routes correctly, demo mode runs | Report HTML generated | (COMPLETE)
| 4: Realtime Mode | 19–25 | tracker.js working, collector receiving, realtime analysis completes | Events in DuckDB live_events | (COMPLETE)
| 5: Dashboard | 26–30 | Streamlit running, mode toggle, charts, approval gate | All dashboard panels functional | (PULLED FORWARD - COMPLETE)
| 6: Testing | 31–35 | Full test suite, edge cases, error scenarios | All tests pass, no unhandled exceptions |
| 7: Delivery | 36–42 | README, demo script, evaluator walkthrough | CIO-ready demo video |

### 1.2 Parallel vs Sequential Build

**Must build sequentially** (Phase N depends on Phase N-1):
```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7
```

**Within Phase 2, MCP servers can be built in any order**, but suggested order:
1. `friction_engine_server.py` (no DB/LLM dependencies — test immediately)
2. `journey_data_server.py` (DuckDB, requires Phase 1 data)
3. `insight_server.py` (LLM + ChromaDB)
4. `report_server.py` (LLM, file write)

### 1.3 Definition of Done Per Phase

Each phase must pass its gate **before** moving to the next phase. Gates are the exact verification commands listed in each section.

---

## 2. Phase 0: Environment Setup (Day 1)

### 2.1 Objectives

- Python 3.11+ virtualenv created and activated
- All dependencies installed from requirements.txt
- .env configured with at least one LLM API key (or Ollama)
- Directory structure created
- LangSmith account set up (optional but recommended)

### 2.2 Step-by-Step Setup

```bash
# 1. Verify Python version (must be 3.11+)
python --version

# 2. Create virtualenv
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy .env template and fill in values
cp .env.example .env
# Edit .env:
#   CJI_MODE=demo
#   LLM_MODEL=claude-sonnet-4-6
#   ANTHROPIC_API_KEY=sk-ant-...
#   LANGCHAIN_TRACING_V2=true
#   LANGCHAIN_API_KEY=ls__...
#   LANGCHAIN_PROJECT=cji-poc

# 5. Verify .env is gitignored
cat .gitignore | grep .env      # should show .env

# 6. Verify directory structure exists (config.py creates data/ and reports/)
python -c "from config import DATA_DIR, REPORTS_DIR; print(DATA_DIR, REPORTS_DIR)"
```

### 2.3 requirements.txt (Pinned Versions)

```
# Core
langchain-core==0.3.0
langgraph==0.2.0
langchain-community==0.3.0

# LLM
litellm>=1.40.0
anthropic>=0.28.0    # for Anthropic SDK fallback detection

# MCP
mcp>=1.0.0
fastmcp>=2.0.0

# Database
duckdb>=1.0.0
chromadb>=0.5.0
sentence-transformers>=3.0.0

# Data Generation
faker>=26.0.0
pandas>=2.2.0
pyarrow>=17.0.0

# Collector
fastapi>=0.112.0
uvicorn[standard]>=0.30.0
pydantic>=2.8.0

# Utils
python-dotenv>=1.0.0
requests>=2.32.0

# Dashboard
streamlit>=1.38.0
plotly>=5.23.0

# Dev only (requirements-dev.txt)
pytest>=8.3.0
pytest-asyncio>=0.24.0
httpx>=0.27.0         # for FastAPI testing
```

### 2.4 Phase 0 Gate

```bash
# All must pass
python -c "import config; print(f'Mode: {config.CJI_MODE}')"
# Expected: "Mode: demo"

python -c "import langgraph; print('LangGraph OK')"
python -c "import fastmcp; print('FastMCP OK')"
python -c "import duckdb; print('DuckDB OK')"
python -c "import chromadb; print('ChromaDB OK')"
python -c "import streamlit; print('Streamlit OK')"
```

---

## 3. Phase 1: Foundation Layer (Days 2–5)

### 3.1 Objectives

- `config.py` fully functional (all env vars, paths, constants)
- `state.py` with complete CJIState TypedDict
- `collector/models.py` with Pydantic validation
- `tools/synthetic_data.py` generating correct Parquet
- `mcp_servers/friction_engine_server.py` scoring correctly
- `tests/test_friction_engine.py` all passing
- `tests/test_collector_models.py` all passing

### 3.2 Build Order

```
Day 2: config.py → state.py
Day 3: collector/models.py → tools/synthetic_data.py
Day 4: mcp_servers/friction_engine_server.py
Day 5: tests/ → verify all pass
```

### 3.3 Day 2: config.py

**Implementation checklist:**
- [x] `load_dotenv()` called at top of file
- [x] `CJI_MODE` read from env with `assert` for valid values
- [x] All paths use `Path(__file__).parent` as ROOT
- [x] `DATA_DIR` and `REPORTS_DIR` created with `mkdir(parents=True, exist_ok=True)`
- [x] `JOURNEY_CONFIG` dict with name and steps list
- [x] `MAX_AGENT_ITERATIONS`, `FRICTION_SCORE_THRESHOLD` configurable
- [x] `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS` all readable

**Verification:**
```bash
python -c "from config import CJI_MODE, DUCKDB_PATH; print(f'Config OK: mode={CJI_MODE}')"
```

### 3.4 Day 2: state.py

**Implementation checklist:**
- [x] `CJIState` TypedDict has ALL required keys (see docs/7-Monorepo-Structure.md Section 3.2)
- [x] `messages` field uses `Annotated[list[BaseMessage], add_messages]` reducer
- [x] Sub-types: `JourneyEvent`, `StepMetrics`, `FrictionScore`, `Insight`, `WorkerStatus`
- [x] No imports from config.py or project modules

**Verification:**
```bash
python -c "from state import CJIState, FrictionScore, Insight; print('State OK')"
```

### 3.5 Day 3: collector/models.py

**Implementation checklist:**
- [x] `ALLOWED_EVENT_TYPES` set defined at module level
- [x] `TrackerEvent` with all field validators
- [x] `url` field validator strips query params and fragments
- [x] `event_type` validator raises ValueError for unknown types
- [x] `metadata` validator handles both dict and JSON string
- [x] `EventBatch` with batch size validator (1–100)
- [x] `CollectResponse` and `HealthResponse` models

**Verification:**
```bash
python -c "from collector.models import EventBatch; print('Models OK')"
pytest tests/test_collector_models.py -v
# Expected: 6+ tests PASSED
```

### 3.6 Day 3: tools/synthetic_data.py

**Implementation checklist:**
- [x] `STEP_PROFILES` dict with exact friction parameters (from docs/7-Monorepo-Structure.md)
- [x] `generate_demo_data(n_sessions, seed, output_path)` function
- [x] Faker seeded with `seed` for reproducibility
- [x] Events include all required types per step profile
- [x] Error events include `metadata["error_code"]` and `metadata["retry_count"]`
- [x] Rage click events generated based on profile
- [x] Output Parquet matches events schema exactly
- [x] email_verification step profile: drop_rate=0.42, avg_dwell_s=180, error_rate=0.35

**Verification:**
```bash
python main.py --mode demo --generate-data
python -c "
import duckdb
conn = duckdb.connect()
result = conn.execute(\"SELECT COUNT(DISTINCT user_id) FROM read_parquet('data/events.parquet')\").fetchone()
print(f'Sessions: {result[0]}')  # Expected: ~2000
"
```

### 3.7 Day 4: friction_engine_server.py

**Implementation checklist:**
- [x] `mcp = FastMCP(name="cji-friction-engine", ...)` at module level
- [x] `WEIGHTS` dict with exact values (see docs/8-Scoring-Engine-Spec.md)
- [x] `BASELINES` dict with exact values
- [x] `FRICTION_SCORE_THRESHOLD` imported from config
- [x] `_normalise(value, baseline)` private function
- [x] `_compute_score(step_metrics)` → tuple[int, list[str], float]
- [x] All 7 signal thresholds exactly as specified
- [x] `score_friction`, `score_all_steps`, `detect_dropoffs`, `correlate_signals` as @mcp.tool
- [x] `if __name__ == "__main__": mcp.run(transport="stdio")` at bottom

**Verification:**
```bash
python mcp_servers/friction_engine_server.py &
sleep 1
# Check process started without error, then kill
```

### 3.8 Day 5: Test Suite

**Implementation checklist:**
- [x] `tests/__init__.py` created (empty)
- [x] `tests/test_friction_engine.py` with `sys.path.insert(0, "..")` at top
- [x] All 12+ required test functions from docs/8-Scoring-Engine-Spec.md Section 10.2
- [x] Both `low_step` and `high_step` fixtures
- [x] `tests/test_collector_models.py` with 6+ Pydantic validation tests
- [x] `tests/test_synthetic_data.py` with 4+ generator tests

**Verification:**
```bash
pytest tests/ -v
# Expected: 22+ tests PASSED in < 30 seconds
```

### 3.9 Phase 1 Gate

```bash
# All must pass:
python -c "from config import CJI_MODE, DUCKDB_PATH; print(f'Config OK')"
python -c "from state import CJIState; print('State OK')"
python -c "from collector.models import EventBatch; print('Models OK')"
python main.py --mode demo --generate-data
pytest tests/ -v  # All pass, no network, no API key
```

---

## 4. Phase 2: MCP Servers (Days 6–12)

### 4.1 Objectives

All 4 MCP servers are independently runnable and respond correctly to tool calls.

### 4.2 Day 6–7: journey_data_server.py

**Implementation checklist:**
- [x] `mcp = FastMCP(name="cji-journey-data", ...)` at module level
- [x] DuckDB module-level singleton (`_conn`) with read_only=True
- [x] `_setup_views(conn)` with mode branch
- [x] Demo mode: `CREATE VIEW events AS SELECT * FROM read_parquet(...)`
- [x] Realtime mode: `CREATE TABLE IF NOT EXISTS live_events(...)` + VIEW
- [x] `_window_clause(days_back, minutes_back)` returns correct SQL fragment
- [x] All 6 MCP tools: `get_system_info`, `get_funnel_steps`, `get_step_metrics`, `get_funnel_dropoff`, `query_events`, `get_live_snapshot`
- [x] `get_live_snapshot` returns error dict (not exception) in demo mode
- [x] All partition by SQL uses `NULLIF` for zero division protection
- [x] `json_extract_string` for metadata field access

**Verification (demo mode):**
```bash
python -c "
import subprocess, sys, json
p = subprocess.Popen([sys.executable, 'mcp_servers/journey_data_server.py'],
                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)
p.stdin.write(b'{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"params\":{},\"id\":1}\n')
p.stdin.flush()
line = p.stdout.readline()
print('Server response:', json.loads(line))
p.terminate()
print('journey_data_server OK')
"
```

### 4.3 Day 8–9: insight_server.py

**Implementation checklist:**
- [x] `mcp = FastMCP(name="cji-insight", ...)`
- [x] ChromaDB module-level singleton `_collection`
- [x] `_get_collection()` function with `get_or_create_collection("cji_insights", {"hnsw:space": "cosine"})`
- [x] LiteLLM call in `generate_insight`: exact system prompt demanding JSON with schema
- [x] JSON fallback: `try: json.loads(raw) except JSONDecodeError: fallback_dict`
- [x] Markdown fence stripping before parse: `raw.replace("```json", "").replace("```", "")`
- [x] All required fields validated in parsed JSON
- [x] `prioritise_fix` with exact effort_map and priority thresholds
- [x] `save_insight`: all metadata values wrapped in str()
- [x] `search_insights`: empty collection guard with `collection.count()` check
- [x] `rank_all_fixes`: LLM-generated action_plan text

**Verification:**
```bash
CJI_MODE=demo python mcp_servers/insight_server.py &
# Should start without error
```

### 4.4 Day 10–11: report_server.py

**Implementation checklist:**
- [x] `mcp = FastMCP(name="cji-report", ...)`
- [x] LiteLLM call in `generate_narrative` for 3-paragraph CIO summary
- [x] Narrative fallback template when LLM unavailable
- [x] `export_report`: builds HTML string with embedded Chart.js JSON
- [x] Friction chart coloring: score ≥ 70 → '#e24b4a', 50–69 → '#ef9f27', < 50 → '#1d9e75'
- [x] Funnel chart: '#378add' (blue always)
- [x] Chart.js CDN: `https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js`
- [x] File naming: `cji_report_{journey}_{YYYYMMDD_HHMMSS}.html`
- [x] `REPORTS_DIR.mkdir(parents=True, exist_ok=True)` before write
- [x] Returns path and file_size_kb (not null)

### 4.5 Day 12: tools/mcp_client.py

**Implementation checklist:**
- [x] `SERVER_REGISTRY` dict: maps server names → absolute Path objects
- [x] `mcp_session(server_name)` as `@asynccontextmanager`
- [x] Uses `StdioServerParameters(command=sys.executable, args=[str(script)])`
- [x] Uses `stdio_client(params)` and `ClientSession(read, write).initialize()`
- [x] `call_tool(session, tool_name, arguments)` function
- [x] `call_tool` wraps content[0].text → json.loads
- [x] `call_tool` raises RuntimeError on any exception (not propagates raw MCP exception)

### 4.6 Phase 2 Gate

```bash
# Test each server standalone
python mcp_servers/friction_engine_server.py &
sleep 1; kill $!; echo "friction OK"

python -c "
import subprocess, sys, json
for server in ['friction_engine_server', 'journey_data_server']:
    p = subprocess.Popen([sys.executable, f'mcp_servers/{server}.py'],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    p.stdin.write(b'{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"params\":{},\"id\":1}\n')
    p.stdin.flush()
    line = p.stdout.readline()
    print(f'{server}: OK' if b'result' in line else f'{server}: FAIL')
    p.terminate()
"
```

---

## 5. Phase 3: Agent Layer (Multi-Agent Team Split) (Days 13–18)

### 5.1 Objectives

LangGraph graph compiles and runs end-to-end in demo mode, producing an HTML report.
**Note:** This phase is split into three parallel development tracks to be worked on concurrently by Sovan and two friends (using their own AI agents).

---

### 5.2 Part 1: Asynchronous Workers (Assigned to: Friend 1)
**File Assignment:** `agents/workers.py`

**Implementation checklist:**
- [ ] Import `CJIState` from `state`.
- [ ] Import `mcp_session`, `call_tool` from `tools.mcp_client`.
- [ ] Implement four `async def` workers: `data_worker`, `friction_worker`, `insight_worker`, `report_worker`.
- [ ] Each worker uses `async with mcp_session("server_name") as session:` and calls `call_tool`.
- [ ] `data_worker` collects: `event_summary`, `raw_events`, `live_event_count`.
- [ ] `friction_worker` collects: `friction_scores`, `critical_steps`.
- [ ] `insight_worker` loops over critical steps, generates insights, formats/ranks, and outputs `insights`.
- [ ] `report_worker` generates narrative, invokes export schema, outputs `report_path`.
- [ ] **CRITICAL:** All workers MUST wrap logic in `try/except Exception as e:` returning `{"errors": state.get("errors", []) + [f"worker_name: {e}"], "next_worker": "supervisor"}`.
- [ ] Success output MUST include `"next_worker": "supervisor"`.
- [ ] Success dictionary does NOT overwrite keys with None (only use specific keys).

---

### 5.3 Part 2: Synchronous Supervisor (Assigned to: Friend 2)
**File Assignment:** `agents/supervisor.py`

**Implementation checklist:**
- [x] Import `CJIState` from `state`.
- [x] **CRITICAL:** All functions must be synchronous `def` (NOT async).
- [x] Implement `def supervisor(state: CJIState) -> dict:` to increment `"iteration"` by 1.
- [x] Implement `def route(state: CJIState) -> str:` mapping exactly:
  - Empty `event_summary` → `"data_worker"`
  - Empty `friction_scores` → `"friction_worker"`
  - Empty `insights` → `"insight_worker"`
  - Exists `insights` but `human_approved` False → `"__end__"` (PAUSE)
  - `human_approved` True but missing `report_path` → `"report_worker"`
  - Else → `"__end__"`
- [x] Implement private `def _llm_route(state):` fallback just in case programmatic routing requires it.

**Completion status:** ✅ ALL DONE (2026-04-01) — 41 unit tests passing, spec verification test passing.
**Test file:** `tests/test_supervisor.py` (41 tests, 9 test classes, <1s runtime)

**Test routing logic (unit test for Friend 2):**
```bash
python -c "
from state import CJIState
from agents.supervisor import supervisor, route
empty_state = {'event_summary': {}, 'friction_scores': [], 'insights': [], 'human_approved': False, 'report_path': '', 'iteration': 0}
assert route(empty_state) == 'data_worker', 'Routing failed'
print('Supervisor routing OK')
"
```

---

### 5.4 Part 3: Graph Compilation (Assigned to: Sovan)
**File Assignment:** `graph.py` and `tests/test_agent_layer.py`

*(Depends on Friend 1 and Friend 2 merging code)*

**Implementation checklist:**
- [ ] Create `graph.py`.
- [ ] `build_graph(use_persistence)` uses `StateGraph(CJIState)`.
- [ ] Add nodes: `"supervisor"`, `"data_worker"`, `"friction_worker"`, `"insight_worker"`, `"report_worker"`.
- [ ] Add conditional edges from `"supervisor"` to the workers via the `route` function.
- [ ] Add standard edges from all 4 workers returning to `"supervisor"`.
- [ ] Add entry edge from `START` to `"supervisor"`.
- [ ] Apply `interrupt_before=["report_worker"]` in the graph compilation.
- [ ] Use `SqliteSaver.from_conn_string("sqlite:///data/cji_checkpoints.db")`.
- [ ] Implement `get_graph()` singleton.

**Integration test (requires LLM API):**
```bash
python main.py --mode demo --run --auto-approve
# Expected output:
# Thread ID: {UUID}
# ✓ data_worker: Fetched metrics for 6 steps
# ✓ friction_worker: N critical / 6 steps, avg=XX
# ✓ insight_worker: N insights generated
# ✓ Report generated: reports/cji_report_onboarding_*.html
```

---

### 5.5 Phase 3 Gate (All Team Members)

```bash
python main.py --mode demo --run --auto-approve
# Expected: HTML report in reports/ directory

ls reports/cji_report_*.html
# Expected: at least 1 file

python -c "
import glob
reports = glob.glob('reports/cji_report_*.html')
assert len(reports) > 0, 'No report generated'
size = len(open(reports[-1]).read())
assert size > 10000, f'Report too small: {size} bytes'
print(f'Report OK: {reports[-1]} ({size} bytes)')
"
```

---

## 6. Phase 4: Realtime Mode (Days 19–25)

### 6.1 Objectives

tracker.js captures browser events, sends them to the collector, and realtime analysis runs successfully.

### 6.2 Day 19–20: tracker/tracker.js

**Implementation checklist:**
- [ ] IIFE pattern: `(function() { 'use strict'; ... })();`
- [ ] Guard at top: exit gracefully if `window.CJI_CONFIG` missing
- [ ] `genId()` using `crypto.randomUUID()` with fallback
- [ ] `userId` from localStorage with fallback
- [ ] `sessionId` per-tab (no localStorage)
- [ ] `sanitiseUrl(url)` strips query and hash
- [ ] `getStepId()` matches `window.location.pathname` against `STEP_MAP`
- [ ] `makeEvent(type, meta)` factory function returning all 10 required fields
- [ ] `push(event)` batches and flushes at BATCH_SIZE=20 or FLUSH_INTERVAL=5000ms
- [ ] DOMContentLoaded → page_view
- [ ] document click → click event (with rage click check)
- [ ] Rage click: 3+ clicks on same element within 500ms → rage_click event
- [ ] form submit → form_submit event
- [ ] window.onerror → error event
- [ ] unhandledrejection → error event (PROMISE_REJECTION code)
- [ ] beforeunload → abandon event via sendBeacon
- [ ] history.pushState/replaceState intercept → step_complete + page_view
- [ ] popstate → step_complete + page_view
- [ ] `window.CJITracker.track(type, meta)` public API

**Verification:**
```bash
# Open browser test page, check DevTools → Network for POST /collect/batch
cat tests/tracker_test.html   # simple HTML with CJI_CONFIG and tracker.js embed
```

### 6.3 Day 21–22: collector/api.py

**Implementation checklist:**
- [ ] `app = FastAPI(title="CJI Collector", ...)` at module level
- [ ] `CORSMiddleware` with `allow_origins=["*"]`
- [ ] DuckDB write connection singleton (`_conn = None`)
- [ ] `_create_tables(conn)` creates `live_events` + `api_keys` tables
- [ ] Dev key `INSERT OR IGNORE INTO api_keys VALUES ('cji_dev_localtest', 'onboarding', 'Local Development')`
- [ ] `GET /health` — returns status + live_events count
- [ ] `GET /tracker.js` — reads and serves tracker.js file with Cache-Control header
- [ ] `POST /collect/batch` — validates key, validates events via Pydantic, uses BackgroundTasks
- [ ] `validate_api_key(api_key, conn)` — query api_keys table, return active bool
- [ ] `write_events(events, conn)` — INSERT OR IGNORE per event, return (accepted, rejected, errors)
- [ ] `GET /live/stats` — per-step counts in last N minutes
- [ ] `GET /live/feed` — SSE stream (optional for PoC)
- [ ] `POST /admin/api-keys` — validates CJI_ADMIN_KEY header, creates new key

**Verification:**
```bash
uvicorn collector.api:app --port 8000 &
sleep 2

curl http://localhost:8000/health
# Expected: {"status": "ok", "live_events_count": 0}

curl -s http://localhost:8000/tracker.js | head -5
# Expected: first lines of tracker.js IIFE

curl -X POST http://localhost:8000/collect/batch \
  -H "Content-Type: application/json" \
  -H "X-CJI-Key: cji_dev_localtest" \
  -d '{"api_key": "cji_dev_localtest", "events": [...]}'
# Expected: {"accepted": 1, "rejected": 0}

pkill -f uvicorn
```

### 6.4 Day 23: tracker/snippet_generator.py

**Implementation checklist:**
- [ ] `argparse` for `--journey`, `--host`, `--output` flags
- [ ] `secrets.token_hex(16)` for key generation
- [ ] Key format: `cji_live_{32 hex chars}`
- [ ] Generates `embed_snippet.html` with complete `window.CJI_CONFIG`
- [ ] Generates `verify_tracker.py` as HTTP test script
- [ ] Generates `useCJITracker.js` as React hook
- [ ] Generates `api_key.json` with key record
- [ ] Prints instructions for inserting key into collector

**Verification:**
```bash
python tracker/snippet_generator.py --journey onboarding --host http://localhost:8000
ls -la snippets/
# Expected: embed_snippet.html, verify_tracker.py, useCJITracker.js, api_key.json
```

### 6.5 Day 24–25: Integration Test – Realtime Mode End-to-End

**Test procedure:**
1. Start collector: `uvicorn collector.api:app --port 8000`
2. Send test events: `python snippets/verify_tracker.py`
3. Run analysis: `CJI_MODE=realtime python main.py --run --auto-approve`
4. Check report: `ls reports/cji_report_*.html`

**Verification:**
```bash
# Terminal 1
uvicorn collector.api:app --port 8000 &

# Terminal 2
python snippets/verify_tracker.py
# Expected: "Sent 12 test events to collector"

curl http://localhost:8000/health
# Expected: live_events_count > 0

# Terminal 3
CJI_MODE=realtime python main.py --run --window-mins 60 --auto-approve
# Expected: Report generated

pkill -f uvicorn
```

### 6.6 Phase 4 Gate

```bash
# Start collector
uvicorn collector.api:app --port 8000 &

# Send events (use verify_tracker.py or curl)
python snippets/verify_tracker.py

# Run analysis
CJI_MODE=realtime python main.py --run --auto-approve

# Check events in DuckDB
python -c "
import duckdb
conn = duckdb.connect('data/cji.duckdb', read_only=True)
count = conn.execute('SELECT COUNT(*) FROM live_events').fetchone()[0]
print(f'Live events in DuckDB: {count}')  # Should be > 0
conn.close()
"

pkill -f uvicorn
```

---

## 7. Phase 5: Dashboard and CLI Polish (Days 26–30)

### 7.1 Objectives

Streamlit dashboard is fully functional with mode toggle, charts, approval gate, and live feed.

### 7.2 Day 26–27: dashboard.py — Core Structure

**Implementation checklist:**
- [ ] `st.session_state.mode` initialised to `os.getenv("CJI_MODE", "demo")`
- [ ] `st.session_state.thread_id` initialised to None
- [ ] `st.session_state.state_snap` initialised to {}
- [ ] Main page title: "Customer Journey Intelligence"
- [ ] Sidebar mode toggle (st.radio or st.selectbox)
- [ ] Mode change clears thread_id and state_snap, calls st.rerun()
- [ ] Mode change sets `os.environ["CJI_MODE"]` before rerun
- [ ] **Never uses asyncio.run()** in any code path

### 7.3 Day 28: dashboard.py — Charts and Metrics

**Implementation checklist:**
- [ ] 4 metric cards: steps analysed, critical steps, avg score, insights count
- [ ] Friction bar chart using Plotly with red/amber/green colours
- [ ] Funnel drop-off chart using Plotly in blue
- [ ] Charts appear after analysis completes (state_snap contains friction_scores)
- [ ] Charts use plotly.express or plotly.graph_objects

### 7.4 Day 29: dashboard.py — Approval Gate and Report

**Implementation checklist:**
- [ ] Insight panels appear when state_snap["insights"] is non-empty
- [ ] Each panel shows: title, root_cause, category, evidence, fix, effort, priority
- [ ] Approve & Generate Report button calls `graph.update_state()` then `graph.stream(None)`
- [ ] Button only appears when insights exist and report not yet generated
- [ ] After approval, report_path appears and download button shown
- [ ] Download button uses `st.download_button` with file content

### 7.5 Day 30: dashboard.py — Realtime Features

**Implementation checklist:**
- [ ] Realtime mode shows collector status (GET /health with 2-second timeout)
- [ ] Collector online: "● Collector Online" in green
- [ ] Collector offline: "✗ Collector Offline" in red with start command
- [ ] Generate Embed Snippet button calls snippet_generator.py
- [ ] Live feed panel shows last 15 events (poll from GET /live/stats)

### 7.6 Day 30: main.py Polish

**Implementation checklist:**
- [ ] `argparse` with all flags documented in docs/6-API-Contracts.md Section 8
- [ ] Thread ID printed on start: `print(f"Thread ID: {thread_id}")`
- [ ] Progress messages for each worker completion
- [ ] Pause message: "⏸ Waiting for approval. Run: python main.py --approve --thread-id {UUID}"
- [ ] Resume on `--approve --thread-id {UUID}`
- [ ] `--auto-approve` sets human_approved=True in initial_state

### 7.7 Phase 5 Gate

```bash
# Dashboard starts
streamlit run dashboard.py &
sleep 5

# Manual check: open http://localhost:8501 in browser
# Verify: mode toggle visible, Run Analysis button present

# Full demo flow (manual)
# 1. Click "Run Analysis" in demo mode
# 2. See worker progress messages
# 3. See friction chart and funnel chart
# 4. Expand insight cards
# 5. Click "Approve & Generate Report"
# 6. See download button
# 7. Download report, open in browser

pkill -f streamlit
```

---

## 8. Phase 6: Testing and Hardening (Days 31–35)

### 8.1 Objectives

All edge cases handled, error paths verified, no unhandled exceptions in any scenario.

### 8.2 Day 31: Friction Engine Edge Case Tests

Additional tests to add:
```python
def test_score_with_missing_fields():
    """Missing fields should default to 0, not raise KeyError."""
    r = score_friction({"step_id": "t"})  # All metrics missing
    assert r["score"] == 0

def test_batch_size_rejection():
    """Batches > 100 events rejected."""
    events = [valid_event() for _ in range(101)]
    with pytest.raises(ValidationError):
        EventBatch(api_key="cji_dev_localtest", events=events)

def test_url_sanitisation_removes_fragment():
    e = TrackerEvent(..., url="https://example.com/page#anchor")
    assert "#" not in e.url

def test_url_sanitisation_removes_query():
    e = TrackerEvent(..., url="https://example.com/page?token=abc123")
    assert "?" not in e.url
    assert "abc123" not in e.url
```

### 8.3 Day 32: Error Scenario Testing

```bash
# Test 1: worker exception isolation
# Inject exception in data_worker and verify graph does not crash
# (Manual: add raise Exception("test") at top of data_worker, run, check errors list)

# Test 2: LLM unavailable
CJI_MODE=demo LLM_MODEL=nonexistent/model python main.py --run --auto-approve
# Expected: insights have category="unknown" (fallback), report still generated

# Test 3: DuckDB not found (demo)
mv data/events.parquet data/events.parquet.bak
python main.py --mode demo --run --auto-approve 2>&1 | head -20
# Expected: clear error message about missing Parquet file
mv data/events.parquet.bak data/events.parquet

# Test 4: Invalid API key
curl -X POST http://localhost:8000/collect/batch \
  -H "Content-Type: application/json" \
  -d '{"api_key": "invalid_key", "events": [...]}'
# Expected: 401 Unauthorized

# Test 5: Collector offline during realtime analysis
# (do NOT start collector, then run CJI_MODE=realtime)
CJI_MODE=realtime python main.py --run --auto-approve
# Expected: data_worker gets empty metrics (not crash), insight says no data
```

### 8.4 Day 33–34: End-to-End Regression Test

Full pipeline test for both modes:

```bash
# Demo mode full regression
python main.py --mode demo --generate-data
python main.py --mode demo --run              # Do NOT auto-approve
# Note thread ID

python main.py --approve --thread-id {UUID}
# Expected: report generated

ls reports/cji_report_*.html
# Expected: HTML file

open reports/cji_report_*.html   # macOS
# Expected: charts visible, narrative present, insights table populated

# Run again with --auto-approve for speed check
time python main.py --mode demo --run --auto-approve
# Expected: < 3 minutes (excluding LLM calls)

# Realtime mode full regression
uvicorn collector.api:app --port 8000 &
python tracker/snippet_generator.py
python snippets/verify_tracker.py
CJI_MODE=realtime python main.py --run --auto-approve
pkill -f uvicorn
```

### 8.5 Day 35: Final Test Suite Run

```bash
# Full test suite — must all pass offline
pytest tests/ -v --tb=short -q
# Expected: ALL tests PASS, no errors, no warnings

# Build verification sequence (from docs — exact commands)
python -c "from config import CJI_MODE, DUCKDB_PATH; print(f'Config OK: mode={CJI_MODE}')"
python -c "from state import CJIState; print('State OK')"
python -c "from collector.models import EventBatch; print('Models OK')"

pytest tests/test_friction_engine.py -v
# Expected: 12+ tests PASSED

python main.py --mode demo --generate-data
# Expected: "Generated X,XXX events → data/events.parquet"

python main.py --mode demo --run --auto-approve
# Expected: "Report generated: reports/cji_report_*.html"

uvicorn collector.api:app --port 8000 &
sleep 2; curl http://localhost:8000/health; pkill -f uvicorn
# Expected: {"status": "ok", "live_events_count": 0}
```

### 8.6 Phase 6 Gate

```bash
pytest tests/ -v  # ALL PASS

python main.py --mode demo --generate-data
python main.py --mode demo --run --auto-approve
# Both: exit code 0, report created

CJI_MODE=realtime uvicorn collector.api:app --port 8000 &
python snippets/verify_tracker.py
CJI_MODE=realtime python main.py --run --auto-approve
pkill -f uvicorn
# All: exit code 0
```

---

## 9. Phase 7: Demo Rehearsal and Delivery (Days 36–42)

### 9.1 Day 36–37: README.md

README must include:
- [ ] Project description (1 paragraph — no jargon)
- [ ] Architecture diagram (ASCII or Mermaid)
- [ ] Prerequisites (Python 3.11+, pip, API key or Ollama)
- [ ] Quick start: 5 commands to go from clone to first report
- [ ] Demo mode walkthrough (step by step)
- [ ] Realtime mode walkthrough (step by step)
- [ ] Environment variable reference
- [ ] Known issues and FAQ
- [ ] Architecture section linking to docs/
- [ ] LangSmith trace example link

### 9.2 Day 38–39: Demo Script

Write a 15-minute demo script covering:
1. Open README — explain the architecture (2 min)
2. Run `python main.py --generate-data` — show generated data (1 min)
3. Open dashboard, run analysis — show progress messages (2 min)
4. Show friction chart — explain email_verification (2 min)
5. Expand insight cards — explain root cause + LLM analysis (2 min)
6. Approve report — generate HTML (1 min)
7. Open report — show to evaluators (2 min)
8. Show tracker.js embed code — explain realtime path (2 min)
9. Open LangSmith — show trace of the run (1 min)

### 9.3 Day 40: Evaluator Environment Test

Test on a fresh machine (or clean virtualenv):
```bash
git clone {repo}
cd cji_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # manually add API key
python main.py --mode demo --generate-data
python main.py --mode demo --run --auto-approve
open reports/cji_report_*.html
```
Must work end-to-end without any other setup steps.

### 9.4 Day 41–42: Documentation and Handover

- [ ] All 12 docs files in docs/ are complete and accurate
- [ ] docs/README.md (index of docs files with descriptions)
- [ ] ARCHITECTURE.md in root (summary for quick reference)
- [ ] LangSmith trace example documented
- [ ] Known limitations documented
- [ ] Post-PoC roadmap summarised (Phase 2, 3, 4)

### 9.5 Phase 7 Gate

The PoC is complete when all evaluation criteria pass:
1. `python main.py --mode demo --run --auto-approve` exits 0 and creates HTML report
2. `pytest tests/ -v` exits 0 with no failures
3. HTML report shows ≥ 2 charts, ≥ 1 critical step, ≥ 1 insight with root_cause
4. Dashboard mode toggle switches between demo and realtime
5. Human approval gate visibly pauses and requires action
6. tracker.js embed snippet generated with valid key format
7. `uvicorn collector.api:app` starts and responds to GET /health

---

## 10. Build Verification Sequence

Run these in order after completing each phase. Each step must pass before proceeding.

```bash
# Step 1: Config and State imports
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
python -c "
import glob
reports = glob.glob('reports/cji_report_*.html')
assert len(reports) > 0, 'No report generated'
print(f'Report OK: {reports[-1]}')
"

# Step 7: Collector API (realtime)
uvicorn collector.api:app --port 8000 &
sleep 2
curl http://localhost:8000/health
# Expected: {"status":"ok","live_events_count":0}
pkill -f uvicorn

# Step 8: Dashboard (manual)
# streamlit run dashboard.py → open browser, verify UI loads
```

---

## 11. Rollback Procedures

### 11.1 If Phase 3 Breaks Phase 2 (Agent imports break MCP server)

```bash
# Verify MCP server works standalone (should always work)
python mcp_servers/friction_engine_server.py
# If this fails: check for circular imports introduced in agents/ code

# Fix: ensure no agent code was accidentally imported in MCP server files
grep -r "from agents" mcp_servers/
# Expected: no matches
```

### 11.2 If DuckDB Locks After Bad Run

```bash
# Kill all Python processes
pkill -f "python main.py"
pkill -f uvicorn
pkill -f streamlit

# Clear lock file if DuckDB created one
rm -f data/cji.duckdb.wal

# Test connection
python -c "import duckdb; conn = duckdb.connect('data/cji.duckdb', read_only=True); print('DuckDB OK'); conn.close()"
```

### 11.3 If ChromaDB Collection is Corrupted

```bash
rm -rf data/chroma/cji_insights/
# Collection will be recreated on next insight_worker run
```

### 11.4 If Checkpoint Database is Corrupted

```bash
rm data/cji_checkpoints.db
# All threads lost — start fresh analysis run
python main.py --mode demo --run --auto-approve
```

---

## 12. Post-PoC Roadmap

### Phase 2 (Months 2–3): Production Foundations

**Priority:** Make realtime mode production-ready

**Key work:**
- Replace open CORS with client domain allowlist
- Add multi-journey support via config (not code change)
- Add GA4 connector as alternative data source
- Add retry logic with exponential backoff for LLM calls
- Add Docker containerisation of collector and dashboard
- Add API rate limiting on collector
- Add basic auth on dashboard

### Phase 3 (Months 4–6): Scale and Infrastructure

**Priority:** Make the system multi-client and cloud-deployable

**Key work:**
- PostgreSQL + TimescaleDB replacing DuckDB for live events
- pgvector replacing ChromaDB for insight storage
- Redis replacing SQLite for LangGraph checkpoints
- Streamable HTTP transport replacing stdio for MCP
- Next.js frontend replacing Streamlit
- Kubernetes deployment with Helm charts
- LangSmith production tier integration

### Phase 4 (Months 7–12): Intelligence and Automation

**Priority:** Add predictive capabilities and automation

**Key work:**
- ML model for drop-off prediction (logistic regression baseline)
- Automated A/B test scaffolding from insights
- Multi-tenant SaaS with user authentication
- Scheduled analysis runs (cron/Temporal)
- Slack/Teams integration for insight delivery
- Custom journey configuration UI
- Historical trend analysis (score over time)
