> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Environment and DevOps
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** Environment Configuration and Operations Reference

---

## Table of Contents

1. [Environment Overview](#1-environment-overview)
2. [Environment Variables Reference](#2-environment-variables-reference)
3. [Dependency Management](#3-dependency-management)
4. [Local Development Setup](#4-local-development-setup)
5. [Process Architecture and Startup](#5-process-architecture-and-startup)
6. [Logging and Observability](#6-logging-and-observability)
7. [LLM Provider Configuration](#7-llm-provider-configuration)
8. [Data Lifecycle Management](#8-data-lifecycle-management)
9. [Security Configuration](#9-security-configuration)
10. [Troubleshooting and Diagnostic Procedures](#10-troubleshooting-and-diagnostic-procedures)
11. [Docker Configuration (Future)](#11-docker-configuration-future)
12. [CI/CD Configuration (Future)](#12-cicd-configuration-future)

---

## 1. Environment Overview

### 1.1 PoC Environment

The PoC is designed for **local machine deployment only**. There is no cloud infrastructure requirement for the 6-week PoC sprint.

| Component | Runtime | Port | Start Command |
|---|---|---|---|
| Collector API | uvicorn (FastAPI) | 8000 | `uvicorn collector.api:app` |
| Dashboard | Streamlit | 8501 | `streamlit run dashboard.py` |
| Main CLI | Python process | — | `python main.py` |
| MCP Servers | subprocess (stdio) | — | spawned automatically |
| DuckDB | file-based | — | accessed by collector + MCP |
| ChromaDB | file-based | — | accessed by insight MCP |
| SQLite | file-based | — | accessed by LangGraph |

### 1.2 Environment Modes

**Demo mode:**
- Data: `data/events.parquet` (generated)
- No collector needed
- Start: `python main.py --mode demo --generate-data && python main.py --mode demo --run`

**Realtime mode:**
- Data: `live_events` table in `data/cji.duckdb`
- Collector must be running before analysis
- Start: `uvicorn collector.api:app` → embed tracker.js → `python main.py --mode realtime --run`

### 1.3 Operating System Support

| OS | Status | Notes |
|---|---|---|
| macOS (ARM/Intel) | Primary | Developed and tested here |
| Linux (Ubuntu 22.04+) | Supported | CI/CD target |
| Windows 11 | Supported with caveats | PowerShell path separator issues in config.py; use `Path` objects (not string concat) |

**Windows path note:** All paths in `config.py` use `pathlib.Path` objects for cross-platform compatibility. `str(Path)` on Windows uses backslashes — always convert to string only at the last moment before passing to DuckDB `read_parquet()`.

---

## 2. Environment Variables Reference

### 2.1 Complete .env.example

```bash
# ─── OPERATION MODE ───────────────────────────────────────────────────
# Controls the entire system behavior: "demo" or "realtime"
# Demo: reads from data/events.parquet (no collector needed)
# Realtime: reads from live DuckDB live_events table
CJI_MODE=demo

# ─── LLM CONFIGURATION ───────────────────────────────────────────────
# Model string passed directly to litellm.completion()
# Anthropic:  "claude-sonnet-4-6"  | "claude-3-5-haiku-20241022"
# OpenAI:     "gpt-4o"             | "gpt-4o-mini"
# Ollama:     "ollama/llama3.1"    | "ollama/mistral"
# Azure:      "azure/gpt-4o"
LLM_MODEL=claude-sonnet-4-6
LLM_TEMPERATURE=0.0
LLM_MAX_TOKENS=2048

# ─── API KEYS (at least one required for LLM calls) ──────────────────
# Anthropic — required if LLM_MODEL starts with "claude"
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI — required if LLM_MODEL starts with "gpt-" or "o1"
# OPENAI_API_KEY=sk-...

# ─── COLLECTOR CONFIGURATION ─────────────────────────────────────────
# Host and port for the FastAPI collector
COLLECTOR_HOST=http://localhost
COLLECTOR_PORT=8000

# Admin key for POST /admin/api-keys endpoint
# Change this in any shared deployment environment
CJI_ADMIN_KEY=change-me-in-production

# ─── REALTIME CONFIGURATION ──────────────────────────────────────────
# Analysis window for realtime mode queries
REALTIME_WINDOW_MINUTES=60

# Auto-run interval: 0 = manual trigger only; N = auto-run every N minutes
# This is a Phase 2 feature — set to 0 for PoC
REALTIME_AUTO_RUN_INTERVAL=0

# ─── AGENT CONFIGURATION ─────────────────────────────────────────────
# Maximum LangGraph iterations before safety cutoff
MAX_AGENT_ITERATIONS=20

# Friction score threshold: steps >= this score are flagged as critical
# Default: 60 (out of 100)
FRICTION_SCORE_THRESHOLD=60

# ─── OBSERVABILITY (LangSmith) ────────────────────────────────────────
# Set to "true" to enable LangSmith tracing
LANGCHAIN_TRACING_V2=true

# LangSmith API key (get from smith.langchain.com)
LANGCHAIN_API_KEY=ls__...

# Project name in LangSmith
LANGCHAIN_PROJECT=cji-poc

# ─── JOURNEY CONFIGURATION ───────────────────────────────────────────
# Name of the journey being analyzed (used in report naming and SQL filters)
JOURNEY_NAME=onboarding
```

### 2.2 Variable Classification

| Variable | Required | Default | Change Impact |
|---|---|---|---|
| CJI_MODE | Yes | "demo" | Changes data source; must set before any import |
| LLM_MODEL | Yes | "claude-sonnet-4-6" | Changes LLM; costs and latency change |
| ANTHROPIC_API_KEY | If using claude | "" | Without this, LLM falls back to Ollama |
| OPENAI_API_KEY | If using gpt | "" | Without this, LLM falls back to Ollama |
| COLLECTOR_HOST | Realtime only | "http://localhost" | Affects snippet embed URL |
| COLLECTOR_PORT | Realtime only | 8000 | Change if port 8000 is occupied |
| CJI_ADMIN_KEY | Realtime only | "change-me-in-production" | Security-sensitive |
| REALTIME_WINDOW_MINUTES | Realtime only | 60 | Changes amount of data analysed |
| MAX_AGENT_ITERATIONS | No | 20 | Safety cutoff only; rarely needed |
| FRICTION_SCORE_THRESHOLD | No | 60 | Determines which steps trigger insights |
| LANGCHAIN_TRACING_V2 | No | "false" | Requires LANGCHAIN_API_KEY if true |
| LANGCHAIN_API_KEY | If tracing | "" | Required if LANGCHAIN_TRACING_V2=true |

### 2.3 Secret Management Rules

**Never commit to version control:**
- `.env` file → listed in `.gitignore`
- Any file containing API keys
- `api_key.json` from snippet_generator

**Gitignore entries (must include):**
```gitignore
# Environment
.env
.env.*
!.env.example

# Runtime data (not source code)
data/
data/**
reports/
reports/**

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/

# Snippet output (may contain API keys)
snippets/api_key.json
snippets/embed_snippet.html
```

---

## 3. Dependency Management

### 3.1 Python Version Requirements

```
Minimum: Python 3.11.0
Recommended: Python 3.11.9 (tested) or 3.12.x
Reason: TypedDict with `from __future__ import annotations` in 3.11+
```

**Verification:**
```bash
python --version
# Expected: Python 3.11.x or 3.12.x
```

### 3.2 Production requirements.txt

```
# ─── LangChain / LangGraph ───────────────────────────────────────────
langchain-core>=0.3.0,<0.4.0
langgraph>=0.2.0,<0.3.0
langchain-community>=0.3.0,<0.4.0

# ─── LLM ─────────────────────────────────────────────────────────────
litellm>=1.40.0

# ─── MCP ─────────────────────────────────────────────────────────────
mcp>=1.0.0
fastmcp>=2.0.0

# ─── Database ─────────────────────────────────────────────────────────
duckdb>=1.0.0,<2.0.0
chromadb>=0.5.0
sentence-transformers>=3.0.0

# ─── Web ─────────────────────────────────────────────────────────────
fastapi>=0.112.0
uvicorn[standard]>=0.30.0
pydantic>=2.8.0

# ─── Data Generation ─────────────────────────────────────────────────
faker>=26.0.0
pandas>=2.2.0
pyarrow>=17.0.0

# ─── Utils ───────────────────────────────────────────────────────────
python-dotenv>=1.0.0
requests>=2.32.0

# ─── Dashboard ───────────────────────────────────────────────────────
streamlit>=1.38.0
plotly>=5.23.0
```

### 3.3 Development requirements-dev.txt

```
# Must install: pip install -r requirements-dev.txt (after requirements.txt)
pytest>=8.3.0
pytest-asyncio>=0.24.0
httpx>=0.27.0      # FastAPI test client
```

### 3.4 Why These Specific Packages

| Package | Why Chosen | Alternative Considered |
|---|---|---|
| duckdb | Embedded OLAP, DuckDB JSON functions, Parquet reader, no server | SQLite (no OLAP), PostgreSQL (requires server) |
| chromadb | Simple local vector DB, cosine similarity, no server | FAISS (no persistence), pgvector (requires PostgreSQL) |
| litellm | Single API for 100+ LLM providers, drop-in switch between Anthropic/OpenAI/Ollama | Direct anthropic SDK (no fallback), openai SDK (vendor lock-in) |
| fastmcp | Declarative @mcp.tool decorator, stdio transport built-in | Raw MCP SDK (much more boilerplate) |
| langgraph | Supervisor pattern with human-in-the-loop, checkpointing, interrupt_before | LangChain Agents (no htitl), Direct Python (no checkpointing) |
| sentence-transformers | Local embeddings (no API cost), all-MiniLM-L6-v2 is small and fast | OpenAI text-embedding-3-small (costs money, network dependency) |
| streamlit | Fastest Python dashboard, zero frontend code | Plotly Dash (more boilerplate), Gradio (less flexible) |

---

## 4. Local Development Setup

### 4.1 Quickstart (macOS / Linux)

```bash
# 1. Clone (or unzip) the project
cd cji_agent

# 2. Create virtualenv
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
nano .env   # or: code .env

# 5. (First run) Download sentence-transformer model (~90MB, ~2 min)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
echo "Model downloaded and cached"

# 6. Generate demo data
python main.py --mode demo --generate-data

# 7. Run demo analysis
python main.py --mode demo --run --auto-approve

# 8. (Optional) Start dashboard
streamlit run dashboard.py
```

### 4.2 Quickstart (Windows)

```powershell
# 1. Navigate to project
cd "C:\Users\{user}\cji_agent"

# 2. Create virtualenv
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configure environment
Copy-Item .env.example .env
notepad .env

# 5. Generate demo data
python main.py --mode demo --generate-data

# 6. Run demo analysis
python main.py --mode demo --run --auto-approve
```

### 4.3 IDE Setup (VS Code)

```json
// .vscode/settings.json (create if not present)
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.terminal.activateEnvironment": true,
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": ["tests"],
    "files.exclude": {
        "data/**": true,
        "reports/**": true,
        "__pycache__": true,
        "**/*.pyc": true
    }
}
```

```json
// .vscode/launch.json (for debugging)
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Demo Analysis (auto-approve)",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/main.py",
            "args": ["--mode", "demo", "--run", "--auto-approve"],
            "envFile": "${workspaceFolder}/.env"
        },
        {
            "name": "Dashboard",
            "type": "python",
            "request": "launch",
            "module": "streamlit",
            "args": ["run", "dashboard.py"],
            "envFile": "${workspaceFolder}/.env"
        },
        {
            "name": "Collector API",
            "type": "python",
            "request": "launch",
            "module": "uvicorn",
            "args": ["collector.api:app", "--reload", "--port", "8000"],
            "envFile": "${workspaceFolder}/.env"
        }
    ]
}
```

---

## 5. Process Architecture and Startup

### 5.1 Demo Mode Startup Sequence

```
1. python main.py --mode demo --run

2. config.py loads .env, creates data/ and reports/ directories
3. state.py loads (TypedDict definitions)
4. graph.py compiles StateGraph (adds nodes + edges + checkpointer)
5. initial_state dict constructed (CJIState with all required keys)
6. graph.stream(initial_state, config=...) called

7. supervisor (sync) → routes to data_worker
8. data_worker (async):
   ├── subprocess.Popen([sys.executable, 'mcp_servers/journey_data_server.py'])
   │   └── journey_data_server.py starts, connects to DuckDB (read-only)
   │       └── CJI_MODE=demo → CREATE VIEW events FROM read_parquet(events.parquet)
   ├── session.call_tool("get_step_metrics", {})
   │   └── SQL aggregation over events VIEW
   ├── session.call_tool("get_funnel_dropoff", {})
   └── subprocess terminates (context manager exit)

9. supervisor → routes to friction_worker
10. friction_worker (async):
    ├── subprocess.Popen([..., 'friction_engine_server.py'])
    ├── session.call_tool("score_all_steps", {all_step_metrics})
    │   └── Pure computation, no IO
    └── subprocess terminates

11. supervisor → routes to insight_worker
12. insight_worker (async):
    ├── For each critical step:
    │   ├── subprocess.Popen([..., 'insight_server.py'])
    │   ├── session.call_tool("generate_insight", {friction_score})
    │   │   └── litellm.completion() → LLM API call → parse JSON
    │   ├── session.call_tool("prioritise_fix", {...})
    │   ├── session.call_tool("save_insight", {...})
    │   │   └── chromadb.collection.add() → local vector store
    │   └── subprocess terminates
    └── session.call_tool("rank_all_fixes", {insights})

13. supervisor → pauses at report_worker (interrupt_before)
    └── State checkpointed to data/cji_checkpoints.db

14. [PAUSE] "⏸ Waiting for approval. Run: python main.py --approve --thread-id {UUID}"
    OR: --auto-approve skips → supervisor routes to report_worker immediately

15. report_worker (async):
    ├── subprocess.Popen([..., 'report_server.py'])
    ├── session.call_tool("generate_narrative", {...})
    │   └── litellm.completion() → LLM API call → 3-paragraph text
    ├── session.call_tool("export_report", {...})
    │   └── Write HTML to reports/cji_report_*.html
    └── subprocess terminates

16. supervisor → END
17. graph.stream returns
18. main.py prints "✓ Report generated: {path}"
```

### 5.2 Realtime Mode Additional Process

```
Concurrent processes (not same machine):
  Process A: uvicorn collector.api:app
    ├── DuckDB write connection open throughout
    ├── POST /collect/batch → INSERT OR IGNORE INTO live_events
    └── GET /health, /live/stats, /live/feed

  Browser (user's machine):
    └── tracker.js
        ├── Sends batches to Process A via fetch/sendBeacon
        └── UUID in localStorage, session UUID per tab

  Process B: python main.py --mode realtime --run
    └── Same flow as demo, but:
        ├── journey_data_server reads from live_events VIEW
        └── Analysis window = REALTIME_WINDOW_MINUTES not days
```

### 5.3 Port Conflict Resolution

```bash
# Check what's using port 8000 (macOS/Linux)
lsof -i :8000
kill -9 {PID}

# Check what's using port 8501 (Streamlit)
lsof -i :8501
kill -9 {PID}

# Change collector port if needed
COLLECTOR_PORT=8001 uvicorn collector.api:app --port 8001
# Update .env: COLLECTOR_PORT=8001
```

### 5.4 MCP Server Process Lifetime

MCP servers are **subprocess processes**, not daemons:
- Each worker spawns a new subprocess per call (using `async with mcp_session(...)`)
- Process is alive only during that worker's execution
- Process terminates cleanly when the `async with` block exits
- Maximum concurrent MCP processes: 1 (workers run sequentially, not in parallel)

**Why not persistent MCP processes?**
- PoC simplicity: removes port management and healthcheck complexity
- LangGraph workers don't run in parallel, so subprocess overhead is minimal (~200ms per start)
- Clean separation: each analysis run starts fresh, no stale state in MCP server

---

## 6. Logging and Observability

### 6.1 LangSmith Tracing

**Setup:**
```bash
# 1. Create LangSmith account: smith.langchain.com
# 2. Create project "cji-poc"
# 3. Get API key from Settings
# 4. Set in .env:
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=cji-poc
```

**What is traced:**
- All LLM calls via litellm (tokens, latency, cost)
- Supervisor routing decisions
- Worker execution time
- Full CJIState at each checkpoint

**Best practice:** Set `LANGCHAIN_TRACING_V2=false` during offline testing to avoid LangSmith network calls and accidental billing.

### 6.2 Python Logging Configuration

**Recommended logging setup (add to config.py):**
```python
import logging

# Only configure if not already configured (avoids duplicate handlers)
if not logging.root.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

# Silence noisy third-party loggers
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# CJI logger
logger = logging.getLogger("cji")
```

**Usage in workers:**
```python
import logging
logger = logging.getLogger("cji.workers")

logger.info(f"[data_worker] Fetched metrics for {len(step_metrics)} steps")
logger.error(f"[data_worker] Exception: {type(e).__name__}: {e}")
```

### 6.3 Collector Logging

FastAPI/uvicorn logging is configured at startup:
```bash
uvicorn collector.api:app --host 0.0.0.0 --port 8000 --log-level info
```

**Access logs:** Every HTTP request is logged to stdout by uvicorn.
**Application logs:** Add `import logging; logger = logging.getLogger("cji.collector")` in `collector/api.py`.

### 6.4 Debug Mode

To enable verbose LangGraph debug logging:
```python
# In main.py, before import graph:
import logging
logging.getLogger("langgraph").setLevel(logging.DEBUG)
```

To see raw LLM prompts and responses:
```python
# litellm verbose mode
import litellm
litellm.set_verbose = True
```

---

## 7. LLM Provider Configuration

### 7.1 Provider Priority

CJI uses LiteLLM as a universal router. Set `LLM_MODEL` in `.env` to switch providers:

| Provider | Model String | Notes |
|---|---|---|
| Anthropic | `claude-sonnet-4-6` | Best results; requires `ANTHROPIC_API_KEY` |
| Anthropic | `claude-3-5-haiku-20241022` | Faster, cheaper; recommended for PoC |
| OpenAI | `gpt-4o` | Alternative; requires `OPENAI_API_KEY` |
| OpenAI | `gpt-4o-mini` | Cheap alternative |
| Ollama (local) | `ollama/llama3.1` | Free; no API key; requires Ollama installed |
| Ollama (local) | `ollama/mistral` | Smallest model; lowest quality |
| Azure OpenAI | `azure/gpt-4o` | Requires `AZURE_API_KEY` etc. |

### 7.2 Ollama Setup (No API Key Required)

For fully offline operation:
```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh  # macOS/Linux

# 2. Pull a model (choose one)
ollama pull llama3.1      # 4.7GB — best quality
ollama pull mistral       # 4.1GB — compact
ollama pull phi3:mini     # 2.3GB — smallest

# 3. Start Ollama server
ollama serve

# 4. Update .env
LLM_MODEL=ollama/llama3.1
# No API key needed — ANTHROPIC_API_KEY and OPENAI_API_KEY can be empty
```

**Performance note:** Ollama on CPU runs ~15–30 seconds per LLM call. On Apple Silicon GPU, ~5–8 seconds. JSON output quality is lower than Claude/GPT — more reliance on fallback logic.

### 7.3 LiteLLM Call Pattern (MUST Follow This Exactly)

```python
import litellm
from config import LLM_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS

def call_llm(system_prompt: str, user_prompt: str) -> dict:
    """Call LLM with fallback. Never raises an exception."""
    try:
        response = litellm.completion(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )
        raw = response.choices[0].message.content or ""
        raw = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}   # Caller handles fallback
    except Exception as e:
        return {"_error": str(e)}  # Caller handles fallback
```

### 7.4 Prompt Engineering Rules

All LLM prompts must:
1. Demand JSON-only output in the system prompt: "Respond ONLY with valid JSON, no markdown, no explanation."
2. Include concrete JSON schema in system prompt
3. Strip markdown fences after response: `raw.replace("```json", "").replace("```", "")`
4. Attempt `json.loads(raw)` in try/except
5. Have a complete fallback dict ready for JSONDecodeError

Prompts must NOT:
- Use Jinja2 or f-string template logic in the LLM call
- Include newlines or indentation that might confuse the parser
- Ask for free text alongside JSON (pick one)

---

## 8. Data Lifecycle Management

### 8.1 Data Directory Contents

```
data/
├── events.parquet         ← Demo only. Regenerate with --generate-data
├── cji.duckdb             ← Realtime: live_events + api_keys tables
├── cji_checkpoints.db     ← LangGraph SQLite checkpoints (all threads)
└── chroma/
    └── cji_insights/      ← ChromaDB collection (insight vectors)
```

### 8.2 Data Creation Timeline

| File | Created By | When |
|---|---|---|
| `data/events.parquet` | `tools/synthetic_data.py` | `python main.py --generate-data` |
| `data/cji.duckdb` | `mcp_servers/journey_data_server.py` | First connection to path (DuckDB auto-creates empty file) |
| `data/cji.duckdb` live_events | `collector/api.py` | First collector startup → `_create_tables()` |
| `data/cji_checkpoints.db` | LangGraph SqliteSaver | First `graph.stream()` call |
| `data/chroma/` | ChromaDB PersistentClient | First `insight_server.py` startup |

### 8.3 Reset Procedures

**Reset demo data (regenerate events):**
```bash
rm data/events.parquet
python main.py --mode demo --generate-data
```

**Reset realtime events (clear live_events table):**
```bash
python -c "
import duckdb
conn = duckdb.connect('data/cji.duckdb')
conn.execute('DELETE FROM live_events')
print(f'Deleted live_events. api_keys preserved.')
conn.close()
"
```

**Reset all checkpoints (lose all analysis threads):**
```bash
rm data/cji_checkpoints.db
# SQLite file recreated on next analysis run
```

**Reset insight vectors (lose semantic search history):**
```bash
rm -rf data/chroma/
# ChromaDB recreated on next insight_worker run
```

**Full data reset:**
```bash
rm -rf data/ reports/
python main.py --mode demo --generate-data  # Recreates data/ and reports/
```

### 8.4 Backup Recommendations

For demo environments, back up the generated data before demos:

```bash
# Before demo: create snapshot
tar czf data_backup_$(date +%Y%m%d).tar.gz data/ reports/

# After demo: restore if something went wrong
tar xzf data_backup_20260315.tar.gz
```

### 8.5 Storage Sizes

| File | Typical Size | Max Expected |
|---|---|---|
| events.parquet | ~3 MB | 10 MB (for 5,000 sessions) |
| cji.duckdb | < 1 MB (empty) | 500 MB (with heavy realtime) |
| cji_checkpoints.db | < 5 MB | 100 MB (many threads) |
| chroma/ (insights) | < 50 MB | 500 MB |
| HTML reports | ~100 KB | 500 KB |

**Note:** For a 6-week PoC with demo data only, total storage is < 60 MB.

---

## 9. Security Configuration

### 9.1 API Key Security Model

```
CJI_ADMIN_KEY (env var, never stored in DB)
    └── Used to authenticate: POST /admin/api-keys
    └── Must be changed from default "change-me-in-production"

tracker.js API keys (stored in api_keys DuckDB table)
    ├── "cji_dev_localtest" — dev key, hardcoded, for local testing only
    └── "cji_live_{32 hex}" — generated with secrets.token_hex(16)

Key revocation:
    UPDATE api_keys SET active = FALSE WHERE api_key = 'cji_live_...'
```

### 9.2 PII Policy (PoC)

**Rule:** No real PII in ANY data store.

Tracker.js enforces this at the browser:
- User ID: anonymous UUID (from `crypto.randomUUID()`), stored in localStorage
- Session ID: anonymous UUID (NOT stored, per-tab only)
- URL sanitisation: query parameters and fragments stripped (no: `?email=user@..` etc.)
- No device fingerprinting
- No IP address storage

Collector enforces this at the API:
- Only event data stored — no user agent, no IP from headers
- URL sanitised again by Pydantic validator
- `identify` event type collects ONLY journey-level traits (account_type, signup_method) — never names, emails, or IDs

**For PoC demo:** All data is either synthetic (demo mode) or anonymous (realtime mode).

### 9.3 CORS Policy

**PoC setting:** `allow_origins=["*"]` (all origins)

**Production change required before live customer data:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-product.com", "https://staging.your-product.com"],
    allow_credentials=False,
    allow_methods=["POST", "GET"],
    allow_headers=["X-CJI-Key", "Content-Type"],
)
```

### 9.4 HTTPS Enforcement

**PoC:** HTTP only (localhost).
**Production requirement:** HTTPS via reverse proxy (nginx/Caddy) before internet exposure.

### 9.5 Sensitive Data in Logs

Never log:
- API key values (log `api_key[:8]...` prefix only)
- LLM prompt inputs (they may contain step metrics with user counts)
- DuckDB query results (raw event data)

Safe to log:
- Event count totals
- Friction scores
- Worker completion messages

---

## 10. Troubleshooting and Diagnostic Procedures

### 10.1 "ModuleNotFoundError" on import

```bash
# Check virtualenv is activated
which python  # macOS/Linux - should point to .venv
python --version  # Should be 3.11+

# Reinstall dependencies
pip install -r requirements.txt

# Check specific module
python -c "import fastmcp; print(fastmcp.__version__)"
```

### 10.2 "events.parquet not found" Error

```bash
# Generate demo data first
python main.py --mode demo --generate-data

# Verify file created
ls -la data/events.parquet
```

### 10.3 "sentence_transformers download" Slow on First Run

The first time insight_server.py runs, it downloads the embedding model (~90MB):
- Expected: 2–5 minutes on typical broadband
- Cached at: `~/.cache/huggingface/hub/`
- Pre-download command: `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"`

### 10.4 DuckDB "read-only database" Error

```bash
# Check for stale lock files
ls data/*.wal
rm data/cji.duckdb.wal  # if exists

# Kill all python processes that might hold the connection
pkill -f "python main.py"
pkill -f uvicorn

# Test connection
python -c "import duckdb; c = duckdb.connect('data/cji.duckdb', read_only=True); c.close(); print('OK')"
```

### 10.5 ChromaDB "InvalidCollectionException"

```bash
# Empty collection causes issues if not guarded
# Check collection.count() before any query

# If collection is corrupted, reset:
rm -rf data/chroma/cji_insights/
python -c "
import chromadb
client = chromadb.PersistentClient(path='data/chroma')
col = client.get_or_create_collection('cji_insights')
print(f'Collection count: {col.count()}')
"
```

### 10.6 LLM API Errors

```bash
# Test API key directly
python -c "
import litellm
r = litellm.completion(
    model='claude-3-5-haiku-20241022',
    messages=[{'role': 'user', 'content': 'Say: OK'}],
    max_tokens=5
)
print(r.choices[0].message.content)  # Should print: OK
"

# If this fails: check ANTHROPIC_API_KEY in .env
# Fallback option: use Ollama
```

### 10.7 "async_generator can't be awaited" Error

This happens when `asyncio.run()` is used inside Streamlit or when an async function returns a generator:

```python
# WRONG in workers:
async def data_worker(state):
    result = await async_generator_func()  # Can't await generators

# WRONG in Streamlit dashboard:
asyncio.run(some_async_func())  # Streamlit has its own event loop

# CORRECT — use synchronous graph.stream():
for event in graph.stream(initial_state, config=config, stream_mode="values"):
    st.session_state.state_snap = event
```

### 10.8 Graph Hangs / Safety Cutoff

If the graph runs indefinitely:
```bash
# Ctrl+C to interrupt (state is checkpointed)
# Check iteration count in state
python -c "
from graph import get_graph
config = {'configurable': {'thread_id': 'YOUR_THREAD_ID'}}
snapshot = get_graph().get_state(config)
print(f'Iteration: {snapshot.values.get(\"iteration\")}')
print(f'Next workers: {snapshot.next}')
print(f'Errors: {snapshot.values.get(\"errors\")}')
"
```

### 10.9 Port Already in Use

```bash
# macOS/Linux
sudo lsof -i :8000 -i :8501
sudo kill -9 {PID}

# Alternative: use different ports
uvicorn collector.api:app --port 8001
COLLECTOR_PORT=8001 streamlit run dashboard.py --server.port 8502
```

### 10.10 Diagnostic Checklist

Run this before filing a bug report:

```bash
echo "=== Environment ==="
python --version
pip show langgraph fastmcp duckdb chromadb litellm | grep -E "Name|Version"

echo "=== Config ==="
python -c "from config import CJI_MODE, LLM_MODEL, DUCKDB_PATH; print(f'mode={CJI_MODE}, llm={LLM_MODEL}')"

echo "=== Data Files ==="
ls -la data/ 2>/dev/null || echo "data/ directory missing"

echo "=== Test Suite ==="
pytest tests/ -q 2>&1 | tail -5

echo "=== MCP Server ==="
python mcp_servers/friction_engine_server.py &
PID=$!
sleep 2
kill $PID 2>/dev/null && echo "friction_engine_server: OK" || echo "friction_engine_server: FAILED"
```

---

## 11. Docker Configuration (Future)

**Note:** Docker is not required for the PoC. This section documents the planned Production Phase 2 configuration.

### 11.1 Dockerfile (Collector)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download sentence-transformer model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY collector/ ./collector/
COPY config.py state.py ./
COPY tracker/ ./tracker/

ENV CJI_MODE=realtime
ENV COLLECTOR_PORT=8000

EXPOSE 8000
CMD ["uvicorn", "collector.api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 11.2 Docker Compose

```yaml
version: "3.9"

services:
  collector:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - CJI_MODE=realtime
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - CJI_ADMIN_KEY=${CJI_ADMIN_KEY}
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports

  dashboard:
    build:
      context: .
      dockerfile: Dockerfile.dashboard
    ports:
      - "8501:8501"
    environment:
      - CJI_MODE=realtime
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - COLLECTOR_HOST=http://collector
      - COLLECTOR_PORT=8000
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports
    depends_on:
      - collector
```

---

## 12. CI/CD Configuration (Future)

**Note:** CI/CD is not required for the PoC. This section documents the planned post-PoC configuration.

### 12.1 GitHub Actions (Test Pipeline)

```yaml
# .github/workflows/test.yml (planned)
name: CJI Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      
      - name: Run test suite
        env:
          CJI_MODE: demo
          LLM_MODEL: claude-3-5-haiku-20241022
          # Note: no ANTHROPIC_API_KEY — tests must not call LLM
        run: pytest tests/ -v --tb=short
      
      - name: Run smoke test
        env:
          CJI_MODE: demo
        run: |
          python main.py --mode demo --generate-data
          python -c "
          import glob
          from pathlib import Path
          assert Path('data/events.parquet').exists()
          print('Smoke test PASSED')
          "
```

### 12.2 Testing Principles for CI

1. **No LLM calls in CI.** All tests in `tests/` must be offline (no network, no API key)
2. **No DuckDB write tests in CI.** Tests that write to DuckDB risk file locking in parallel jobs
3. **Friction engine tests are always safe.** Pure computation, no IO — always run in CI
4. **Collector model tests are always safe.** Pydantic validation, no IO
5. **Integration tests require secrets.** Mark with `@pytest.mark.integration` and skip in CI
