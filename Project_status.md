> **Superseded (2026-10-28).** Historical record, kept unchanged below. It is not the current state of the
> project. Current behaviour: `README.md`; change history and decisions: `.kiro/specs/`; document status:
> `docs/README.md`.

# Project Status: Customer Journey Intelligence (CJI)

## 🎯 Overview & Theory
The **Customer Journey Intelligence (CJI)** system is an AI-powered UX analytics PoC (Proof of Concept) designed to collect, analyze, and generate actionable insights from customer telemetry and user journey flows. It acts as an intelligence engine that highlights where users get stuck in software journeys (e.g., onboarding, signup checkout) and explains why it happened and how to fix it.

### Core Concept: Dual Mode
The system runs in two parallel modes, governed by the `CJI_MODE` environment variable:
- **`demo` mode**: Operates on synthetic parity data via an event generation script (`data/events.parquet`). It is used to quickly demonstrate the analytics power without live users.
- **`realtime` mode**: Uses a lightweight browser tracker (`tracker.js`) calling a FastAPI collector to register real interaction events into a **Supabase PostgreSQL** `live_events` table (or local DuckDB if configured).

### Multi-Agent Architectural Workflow
The CJI uses an orchestrator pattern employing **LangGraph** paired with **Model Context Protocol (MCP)** tools.
1. **Collector & Persistence (Layer 1):** `tracker.js` sends event packets to the `FastAPI` collector. These events are securely written into **Supabase PostgreSQL** (or DuckDB). A background keep-alive loop prevents server suspension on Render.
2. **Smart Ingestion Intelligence (Layer 2.5 — NEW in v2):** A dedicated MCP server (`cji-ingestion-intelligence`) acts as an AI data engineer. It accepts raw data exports in CSV, JSON, Excel, or Parquet format from any third-party tool (GA4, Hotjar, UXCam, etc.), uses an LLM to automatically detect and map the incoming schema to the canonical CJI schema, validates the data with Pydantic v2, sanitises PII, and writes clean records to the appropriate store. A SHA-256 column fingerprint cache ensures the LLM is called only once per unique source type.
3. **Analysis APIs via MCP Servers (Layer 2 & 3):** Isolated tool servers calculate scores or generate embeddings. The four specialized analysis servers are:
   - **Journey Data Server**: Acts as the single point-of-read for querying PostgreSQL/DuckDB event metrics.
   - **Friction Engine Server**: Applies deterministic rules across dwell time, errors, and drop-offs to generate a "friction score".
   - **Insight Server**: Takes poor-performing steps, taps into vector search via **ChromaDB**, and sends prompts manually through the `Groq API` via standard HTTPS `requests` to retrieve AI-generated UX fixes.
   - **Report Server**: Outputs a static HTML narrative based on Groq API completions compiling insights.
4. **Orchestration Layer (Layer 4):** A single synchronous **LangGraph Supervisor** manages progression using a deterministic loop targeting five asynchronous independent working agents (Ingestion, Data, Friction, Insight, Report). They call MCP tools dynamically. 
5. **Presentation (Layer 6):** A **Streamlit Dashboard** and interactive **CLI** control graph execution. The dashboard features dedicated **Audience** and **Heatmap** analytics pages and leverages direct DB-driven fallbacks for immediate friction/insight visualization.

---

## 🔑 Technology Stack & Tools

### Languages and Core Frameworks
- **Python (3.11+)**: The core backend application logic, AI processing, and pipeline.
- **JavaScript (Vanilla)**: For the lightweight, isolated front-end event tracking script (`tracker.js`).
- **Streamlit**: Presentation UI/Dashboard for monitoring the pipelines.
- **FastAPI & Uvicorn**: Backs the telemetry ingestion collector system for realtime event gathering.

### AI, Orchestration & Agents
- **LangGraph**: Orchestrates the Multi-Agent framework for routing the processing sequence via Supervisor and asynchronous Workers.
- **MCP (Model Context Protocol)** & **FastMCP**: Deploys localized tools securely across domains (five decoupled servers — including the new Smart Ingestion server).
- **Sentence-Transformers**: Powers high-quality dense vector embedding capabilities natively.
- **Groq API HTTP REST**: Integrates straight to Groq endpoints for LLM interaction (specifically utilizing variations of `llama3-70b-8192`), decoupling heavily from large SDKs like `litellm`. 

### Databases Layer
- **Supabase PostgreSQL**: Production-grade analytical SQL DB handling real-time event tables natively.
- **DuckDB**: Fast, in-process analytical SQL DB used for demo mode logic and local development.
- **ChromaDB**: Native Vector Database running locally to index standard insights and recommendations queries.
- **SQLite**: Dedicated explicitly for persisting checkpointing memory in LangGraph to uphold robust human-in-the-loop interactions.

---

## 🏃 Commands & Walkthrough

Here is a quick walkthrough to verify and run the stack:

### 1. Installation & Environment Check
Make sure you are in the `.venv` inside `cji_agent/`:
```bash
cd cji_agent
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
# Make sure .env is appropriately configured with GROQ_API_KEY
```

### 2. Stand Up the Multi-Agent Setup
You must launch the specialized MCP sub-servers to enable your agents. Run the runner script:
```bash
python run_servers.py
```
*(Leave this running in the background — this now starts 5 servers including Smart Ingestion on port 8005).*

### 3. Start Telemetry Collection Endpoint
If building tracking data in realtime:
```bash
uvicorn collector.api:app --port 8000 &
```

### 4. Running the Analytics CLI pipeline
Trigger the core inference graph in Demo mode:
```bash
python main.py --mode demo --run --auto-approve
```

### 5. NEW: Smart Ingestion — Ingest Raw Data from Any Source (v2)
Drop any raw data file and let the AI map it automatically:
```bash
# Ingest a GA4 clickstream export and run the full pipeline
python main.py --mode demo --ingest --file ..\Dataset\ga4_clickstream.json --source-hint "GA4 export" --run --auto-approve

# Ingest a CSV dump (no analysis — just ingest)
python main.py --mode demo --ingest --file my_data.csv

# Ingest multiple files at once
python main.py --mode demo --ingest --file file1.csv file2.json --run --auto-approve
```

### 6. Open the Interactive CIO Dashboard
Access the unified web application visualization and progression management hub:
```bash
streamlit run dashboard.py
# Available locally at http://localhost:8501
```

---

## 📂 Current File Structure

The project lives under the primary repo directory: `c:\Users\KIIT\OneDrive\Desktop\Unofficial_Project\`

```text
├── Project Details/    # Original project design PRD and specs
├── docs/               # 12 specific, comprehensive documentation definition files (Phases, Contracts, Definitions).
├── Dataset/            # Relevant datasets (ga4_clickstream.json, hotjar.json, uxcam.json, surveys, etc.)
├── project_memory.md   # The authoritative memory tracking file acting as single source-of-truth progress manager.
├── Project_status.md   # THIS FILE: high-level project status overview.
└── cji_agent/          # The active workspace holding operational code
    ├── agents/         # LangGraph logic (supervisor.py, workers.py, ingestion_worker.py [NEW v2])
    ├── collector/      # FastAPI code managing events ingestion (api.py, models.py)
    ├── mcp_servers/    # FastMCP REST definitions (friction_engine, journey_data, insight, report, ingestion_intelligence [NEW v2])
    ├── reports/        # Target folder for generated CIO markdown/HTML documents
    ├── rules/          # System rules storage
    ├── tools/          # Synthetic data utility, mcp HTTP clients
    ├── tests/          # Comprehensive pytest validations ensuring system resilience (including test_ingestion_intelligence.py [NEW v2])
    ├── tracker/        # Frontend integration tags & helper snippet generator (tracker.js)
    ├── data/           # Runtime data (events.parquet, mapping_registry.json [NEW v2], ingestion_uploads/ [NEW v2])
    ├── config.py       # Safe application-wide settings and directory managers
    ├── dashboard.py    # Streamlit visual controller
    ├── graph.py        # LangGraph schema configurations (now with 5 workers)
    ├── main.py         # Primary CLI entry (now with --ingest, --file, --source-hint flags)
    ├── state.py        # CJIState TypedDict (now with IngestionResult + ingestion fields)
    └── requirements.txt  # (now includes openpyxl for Excel support)
```

---

## 🆕 What's New in v2.0 — Smart Ingestion Intelligence

### The Problem (v1)
Previously, integrating data from a new third-party tool (GA4, Hotjar, UXCam) required a developer to manually write custom ETL scripts to map columns, clean timestamps, and format data to match the CJI schema. If a vendor changed a column name, the pipeline would break.

### The Solution (v2)
A new **5th MCP micro-server** (`cji-ingestion-intelligence`, port 8005) acts as an AI Data Engineer:
- **Zero-Code Schema Mapping:** The AI samples 30 rows of the raw file and auto-maps columns to the canonical CJI schema.
- **Self-Healing Data:** Automatically generates missing UUIDs, anonymises PII, normalises timestamps, and coerces unknown event types.
- **Smart Caching:** Column fingerprinting (SHA-256) ensures the LLM is called only once per unique source type. Repeated uploads skip the LLM entirely.
- **Confidence-Gated Auto-Ingestion:** Mappings above 80% confidence are auto-saved; below-threshold mappings are flagged for human review.
- **Multi-Format Support:** CSV, JSON, JSONL, Excel (.xlsx/.xls), and Parquet files.

### Port Map (All 5 MCP Servers)

| Port | Server | Purpose |
|------|--------|---------|
| 8001 | `cji-journey-data` | Event metrics and analytics queries |
| 8002 | `cji-friction-engine` | Deterministic friction scoring |
| 8003 | `cji-insight` | LLM root-cause analysis + ChromaDB |
| 8004 | `cji-report` | CIO-level HTML report generation |
| 8005 | `cji-ingestion-intelligence` | **NEW v2:** AI-powered schema detection & data ingestion |

---

## 🚀 Development Progress

**Current Overall Status:** `98% Complete` — **v2.0 Feature Complete**

- **Documentation Phase:** `100% Done`
- **Phase 0 (Environment):** `Done`
- **Phase 1 (Foundation Layer):** `Done`
- **Phase 2 (MCP Servers Development):** `Done`
- **Phase 3 (Agent Layer):** `Done`
- **Phase 4 (Collector API & Realtime Mode):** `Done` — Supabase integration and Render deployment live.
- **Phase 5 (Visualizations & Core Testing):** `Done` — Dashboard enhanced with Heatmaps and Audience pages.
- **Phase 6 (Testing & Hardening):** `Done`
    - Address Render sleep issues (keep-alive implemented).
    - Established Supabase PostgreSQL connectivity with robust URL encoding.
    - Standardized tracker metadata keys for density mapping.
- **Phase 7 (Delivery):** 🟢 **COMPLETE**
    - Finalizing README and handover docs.
- **v2.0 (Smart Ingestion Intelligence):** 🟢 **FEATURE COMPLETE**
    - New MCP Server 0 with 6 tools, new LangGraph worker, 16 unit tests, full wiring across 10+ files.
    - Remaining: Groq model name validation for integration tests, end-to-end live demo.

**Conclusion:** The system is now a fully operational dual-mode analytics platform with intelligent, AI-driven data ingestion. Any raw data file from any third-party tool can be automatically mapped, validated, and ingested into the CJI pipeline — eliminating the need for custom ETL scripts and making the system truly tool-agnostic and scalable.
