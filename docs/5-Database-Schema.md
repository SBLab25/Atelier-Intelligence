> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Database Schema
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** Database Schema Reference

---

## Table of Contents

1. [Data Store Overview](#1-data-store-overview)
2. [DuckDB Schema — Demo Mode](#2-duckdb-schema--demo-mode)
3. [DuckDB Schema — Realtime Mode](#3-duckdb-schema--realtime-mode)
4. [DuckDB Schema — Shared Tables](#4-duckdb-schema--shared-tables)
5. [ChromaDB Schema](#5-chromadb-schema)
6. [SQLite Checkpoint Schema (LangGraph)](#6-sqlite-checkpoint-schema-langgraph)
7. [Pydantic Validation Schema (Collector Input)](#7-pydantic-validation-schema-collector-input)
8. [File Storage Schema (Parquet, Reports)](#8-file-storage-schema-parquet-reports)
9. [Standard Queries](#9-standard-queries)
10. [Schema Constraints and Rules](#10-schema-constraints-and-rules)
11. [Indexes and Performance](#11-indexes-and-performance)
12. [Migration Notes](#12-migration-notes)

---

## 1. Data Store Overview

CJI uses four distinct data stores, each serving a specific purpose:

| Data Store | File | Purpose | Mode |
|---|---|---|---|
| DuckDB | `data/cji.duckdb` | Event storage + API key management | Both |
| Parquet | `data/events.parquet` | Demo synthetic event storage | Demo only |
| ChromaDB | `data/chroma/cji_insights/` | Vector store for insight semantic search | Both |
| SQLite | `data/cji_checkpoints.db` | LangGraph agent state checkpoints | Both |

All files are auto-created at startup (DuckDB on Journey Data MCP start, Parquet on `--generate-data`, ChromaDB on first insight save, SQLite on first graph run).

---

## 2. DuckDB Schema — Demo Mode

### 2.1 Events VIEW (Demo Mode)

In demo mode, the unified `events` VIEW reads from the Parquet file. No DuckDB table stores events.

```sql
-- Created at:  mcp_servers/journey_data_server.py → _setup_views()
-- Condition:   CJI_MODE == "demo"

CREATE OR REPLACE VIEW events AS
SELECT
    event_id     VARCHAR,    -- UUID string (e.g. "3f4e9a12-b123-...")
    user_id      VARCHAR,    -- Anonymous UUID (no PII)
    journey_id   VARCHAR,    -- Journey name (e.g. "onboarding")
    step_id      VARCHAR,    -- Step within journey (e.g. "email_verification")
    event_type   VARCHAR,    -- One of: page_view|click|form_submit|error|rage_click|abandon|step_complete|identify
    timestamp    TIMESTAMPTZ,-- ISO-8601 timezone-aware datetime
    duration_ms  BIGINT,     -- Milliseconds; 0 for instant events
    metadata     VARCHAR     -- JSON string with event-specific payload
FROM read_parquet('/absolute/path/to/data/events.parquet')
```

**Notes:**
- `read_parquet()` uses the absolute path from `config.EVENTS_PARQUET`
- DuckDB resolves this lazily — file must exist before any query is run
- The VIEW is re-created on each DuckDB connection startup

### 2.2 Parquet Column Schema

The Parquet file generating from `tools/synthetic_data.py` must match exactly:

```
Column      DuckDB Type   Arrow Type      Notes
──────────────────────────────────────────────────
event_id    VARCHAR       utf8            UUID v4
user_id     VARCHAR       utf8            UUID v4
journey_id  VARCHAR       utf8            e.g. "onboarding"
step_id     VARCHAR       utf8            e.g. "email_verification"
event_type  VARCHAR       utf8            from ALLOWED_EVENT_TYPES
timestamp   TIMESTAMPTZ   timestamp[us]   UTC timezone
duration_ms BIGINT        int64           non-negative integer
metadata    VARCHAR       utf8            valid JSON string
```

**Validation rules at generation:**
- `event_id` and `user_id` must be valid UUID strings (len 36)
- `event_type` must be in `ALLOWED_EVENT_TYPES`
- `timestamp` must be timezone-aware and within the past 90 days
- `duration_ms` must be ≥ 0
- `metadata` must be a valid JSON string (at minimum `{}`)

---

## 3. DuckDB Schema — Realtime Mode

### 3.1 live_events TABLE

```sql
-- Created at:  mcp_servers/journey_data_server.py → _setup_views()
-- Condition:   CJI_MODE == "realtime"
-- Access:      Written by collector/api.py; read by journey_data_server.py (via VIEW)

CREATE TABLE IF NOT EXISTS live_events (
    event_id    VARCHAR       PRIMARY KEY,    -- UUID string ≥ 8 chars
    user_id     VARCHAR       NOT NULL,       -- Anonymous UUID (from localStorage)
    session_id  VARCHAR       NOT NULL,       -- Session UUID (per browser tab)
    journey_id  VARCHAR       NOT NULL,       -- e.g. "onboarding"
    step_id     VARCHAR       NOT NULL,       -- e.g. "landing_page"
    event_type  VARCHAR       NOT NULL,       -- From ALLOWED_EVENT_TYPES set
    timestamp   TIMESTAMPTZ   NOT NULL,       -- From browser: new Date().toISOString()
    duration_ms BIGINT        DEFAULT 0,      -- Milliseconds; 0 for instant events
    url         VARCHAR       DEFAULT '',     -- Sanitised URL (no query params)
    metadata    VARCHAR       DEFAULT '{}',   -- JSON string
    received_at TIMESTAMPTZ   DEFAULT NOW()   -- Server receipt time (for time-window queries)
)
```

**Column notes:**
- `session_id`: absent in demo mode VIEW but present in live_events for session analytics
- `url`: absent in demo mode VIEW but useful for realtime page-level analysis
- `received_at`: the critical addition for realtime mode — used for rolling window queries
- `INSERT OR IGNORE` prevents duplicate events (idempotent delivery)

### 3.2 Events VIEW (Realtime Mode)

Exposes `live_events` as the standard `events` VIEW so all downstream queries are identical:

```sql
-- Created immediately after live_events table creation
-- This VIEW is what all get_step_metrics() queries run against

CREATE OR REPLACE VIEW events AS
SELECT
    event_id,
    user_id,
    journey_id,
    step_id,
    event_type,
    timestamp,
    duration_ms,
    metadata
FROM live_events
```

**Design note:** `session_id`, `url`, and `received_at` are intentionally excluded from the `events` VIEW to maintain identical schema compatibility with the demo VIEW.

---

## 4. DuckDB Schema — Shared Tables

### 4.1 api_keys TABLE

```sql
-- Created at:  collector/api.py → _create_tables() on startup
-- Purpose:     API key validation and client management

CREATE TABLE IF NOT EXISTS api_keys (
    api_key     VARCHAR       PRIMARY KEY,   -- "cji_live_{32 hex chars}" format
    journey_id  VARCHAR       NOT NULL,      -- Which journey this key authorises
    client_name VARCHAR       NOT NULL,      -- Human-readable client identifier
    created_at  TIMESTAMPTZ   DEFAULT NOW(), -- Key creation timestamp
    active      BOOLEAN       DEFAULT TRUE   -- Revoke by setting to FALSE
)
```

**Initial data (inserted on first collector startup):**

```sql
-- Dev key for local development — allows testing without snippet generation
INSERT OR IGNORE INTO api_keys (api_key, journey_id, client_name)
VALUES ('cji_dev_localtest', 'onboarding', 'Local Development')
```

**Key format rules:**
- Dev key: `cji_dev_localtest` (fixed)
- Live keys: `cji_live_{secrets.token_hex(16)}` = `cji_live_` + 32 hex chars (36 chars total)
- Admin key: `CJI_ADMIN_KEY` env var — never stored in api_keys table

**Access patterns:**
- Validation (every POST /collect/batch): `SELECT active FROM api_keys WHERE api_key = ?`
- Create new key: `INSERT INTO api_keys VALUES (?, ?, ?, DEFAULT, DEFAULT)`
- Revoke key: `UPDATE api_keys SET active = FALSE WHERE api_key = ?`
- Reactivate key: `UPDATE api_keys SET active = TRUE WHERE api_key = ?`
- List all keys: `SELECT api_key, journey_id, client_name, created_at, active FROM api_keys`

---

## 5. ChromaDB Schema

### 5.1 Collection Definition

```python
# Collection name: "cji_insights"
# Created at: mcp_servers/insight_server.py → _get_or_create_collection()
# Persistence: data/chroma/ directory

collection = chroma_client.get_or_create_collection(
    name="cji_insights",
    metadata={"hnsw:space": "cosine"}  # cosine similarity for semantic search
)
```

### 5.2 Document Format

Each document stored in ChromaDB represents one insight:

```
Document string format:
"{title}. {root_cause}. {suggested_fix}"

Example:
"High abandon rate on email verification. Users are failing the email verification step
 due to OTP tokens expiring within 2 minutes — shorter than the time most users take
 to check their email on mobile. Extend OTP token validity to 15 minutes, add a
 resend button prominently above the fold, and provide a countdown timer."

This composite document format improves semantic search quality by including all
textual aspects of the insight in one searchable string.
```

### 5.3 Metadata Schema

**All metadata values must be strings** (ChromaDB requirement for filtering).

```python
metadata = {
    "step_id":    str(insight["step_id"]),     # e.g. "email_verification"
    "category":   str(insight["category"]),    # "UX"|"data"|"system"|"process"|"unknown"
    "priority":   str(insight["priority"]),    # "1"|"2"|"3"|"4"|"5"
    "score":      str(insight["score"]),       # "87" (string of integer)
    "fix_effort": str(insight["fix_effort"]),  # "low"|"medium"|"high"
}
```

**Critical rule:** All Python values must be wrapped in `str()` before saving. Non-string metadata values cause `ChromaDB ValueError`. This includes integers, floats, booleans, and lists.

### 5.4 ChromaDB CRUD Operations

```python
# INSERT (save_insight):
collection.add(
    documents=[document_string],
    metadatas=[metadata_dict],
    ids=[insight_id]  # UUID string
)

# SEARCH (search_insights):
n_results = min(n_results, collection.count())  # GUARD: prevent error on small collection
results = collection.query(
    query_texts=[query_text],
    n_results=n_results,
    include=["documents", "metadatas", "distances"]
)

# READ ALL (for ranking):
all_results = collection.get(include=["documents", "metadatas"])
```

**Empty collection guard:**
```python
if collection.count() == 0:
    return {"results": [], "query": query_text, "error": "No insights stored yet"}
n = min(n_results, collection.count())  # NEVER request more than stored
```

### 5.5 Embedding Model

```
Model:           sentence-transformers/all-MiniLM-L6-v2
Dimensions:      384
Download size:   ~90 MB (cached after first run)
First-run delay: ~2 minutes (download + model load)
Cache location:  ~/.cache/huggingface/hub/ (default)
Distance metric: cosine (lower = more similar)
```

---

## 6. SQLite Checkpoint Schema (LangGraph)

### 6.1 LangGraph-Managed Tables

The SQLite file at `data/cji_checkpoints.db` is entirely managed by LangGraph's `SqliteSaver`. **Do not access it directly** — only via the LangGraph API.

The internal schema (for reference only):

```sql
-- LangGraph internal checkpoint format (do not modify)
CREATE TABLE checkpoints (
    thread_id    TEXT,           -- UUID string (the "conversation" identifier)
    checkpoint_id TEXT,          -- UUID of the specific checkpoint
    parent_checkpoint_id TEXT,   -- Links to previous checkpoint in thread
    type         TEXT,           -- Always "msgpack" in current LangGraph
    checkpoint   BLOB,           -- Serialised CJIState (JSON → msgpack)
    metadata     TEXT,           -- JSON: {"step": "supervisor", ...}
    PRIMARY KEY (thread_id, checkpoint_id)
)
```

### 6.2 Access Patterns (via LangGraph API only)

```python
# Start new analysis thread:
config = {"configurable": {"thread_id": str(uuid4())}}
for event in graph.stream(initial_state, config=config, stream_mode="values"):
    pass

# Check current state (after pause):
snapshot = graph.get_state(config)
snapshot.values    # dict: full CJIState
snapshot.next      # tuple: ("report_worker",) if paused, () if done

# Approve and resume:
graph.update_state(config, {"human_approved": True}, as_node="supervisor")
for event in graph.stream(None, config=config, stream_mode="values"):
    pass

# Resume after crash (same thread_id):
for event in graph.stream(None, config=config, stream_mode="values"):
    pass
```

### 6.3 CJIState Serialisation

LangGraph serialises the full `CJIState` TypedDict to each checkpoint. All values must be JSON-serialisable.

**JSON-safe requirements:**
- All dict keys must be strings
- All insight lists must contain only lists, dicts, strings, and numbers
- `BaseMessage` objects are handled by LangGraph's `add_messages` reducer
- No Python objects, no datetime objects directly — use ISO-8601 strings
- No `None` in critical fields — use empty list `[]` or empty string `""`

---

## 7. Pydantic Validation Schema (Collector Input)

### 7.1 TrackerEvent Model

```python
# Located: collector/models.py

class TrackerEvent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    event_id:    str = Field(min_length=8)          # UUID ≥ 8 chars
    user_id:     str = Field(min_length=8)          # UUID ≥ 8 chars
    session_id:  str = Field(min_length=8)          # UUID ≥ 8 chars
    journey_id:  str = Field(min_length=1)          # e.g. "onboarding"
    step_id:     str = Field(min_length=1)          # e.g. "email_verification"
    event_type:  str                                # validated against Literal below
    timestamp:   str = Field(min_length=1)          # ISO-8601 string
    duration_ms: int = Field(default=0, ge=0)       # non-negative milliseconds
    url:         str = Field(default="")            # BEFORE sanitisation
    metadata:    dict | str = Field(default_factory=dict)

    @field_validator("event_type")
    @classmethod
    def allowed_event_type(cls, v):
        if v not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"event_type '{v}' not allowed. Must be one of {ALLOWED_EVENT_TYPES}")
        return v

    @field_validator("url")
    @classmethod
    def sanitise_url(cls, v):
        """Strip query parameters and fragments — enforced here even if tracker.js missed it."""
        try:
            parsed = urllib.parse.urlparse(v)
            return urllib.parse.urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
            )
        except Exception:
            return v.split("?")[0].split("#")[0]

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, v):
        """Handle both dict and JSON string metadata."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v or {}
```

### 7.2 EventBatch Model

```python
class EventBatch(BaseModel):
    api_key: str = Field(min_length=10)     # "cji_live_..." or "cji_dev_localtest"
    events:  List[TrackerEvent]             # 1 to 100 events per batch
    
    @field_validator("events")
    @classmethod
    def validate_batch_size(cls, v):
        if len(v) < 1:
            raise ValueError("Batch must contain at least 1 event")
        if len(v) > 100:
            raise ValueError("Batch size exceeds maximum of 100 events")
        return v
```

### 7.3 ALLOWED_EVENT_TYPES

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

### 7.4 Collector API Response Models

```python
class CollectResponse(BaseModel):
    accepted: int              # Events successfully written to DuckDB
    rejected: int              # Events with individual write errors
    errors:   List[str] = []   # Per-event error descriptions (max 10)
    message:  str = "OK"       # Human-readable status

class HealthResponse(BaseModel):
    status:             str    # "ok" | "error"
    live_events_count:  int    # Total events in live_events table
    mode:               str    # CJI_MODE value

class LiveStats(BaseModel):
    steps:        Dict[str, int]  # step_id → event count in last N minutes
    window_mins:  int             # Window queried
    total_events: int             # Total events in window
```

---

## 8. File Storage Schema (Parquet, Reports)

### 8.1 Parquet File Specification

```
File path:      data/events.parquet
Engine:         pandas + pyarrow
Row count:      ~15,000 rows for 2,000 sessions × 6 steps × avg 1.25 events/step/user
File size:      ~3 MB
Compression:    snappy (pyarrow default)
Schema engine:  DuckDB reads natively; no pandas required to read
```

**Writing (synthetic_data.py):**
```python
df = pd.DataFrame(events)
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df["metadata"] = df["metadata"].apply(json.dumps)
df.to_parquet(EVENTS_PARQUET, index=False, engine="pyarrow")
```

**Reading (journey_data_server.py via DuckDB):**
```sql
CREATE OR REPLACE VIEW events AS
SELECT * FROM read_parquet('/absolute/path/to/events.parquet')
```

### 8.2 HTML Report File Specification

```
File path:    reports/cji_report_{journey}_{YYYYMMDD_HHMMSS}.html
Engine:       Python string formatting (no Jinja2)
Typical size: 80–120 KB
Format:       UTF-8 HTML5 with embedded JSON data for Chart.js
Dependencies: Chart.js CDN (requires internet on first open)
```

**Report naming examples:**
```
reports/cji_report_onboarding_20260315_143022.html
reports/cji_report_onboarding_20260315_160847.html
```

**Critical rule:** Report must never fail to create due to missing `reports/` directory. `config.py` must create this directory at import time: `REPORTS_DIR.mkdir(parents=True, exist_ok=True)`

---

## 9. Standard Queries

### 9.1 get_step_metrics() — Core Aggregation Query

**Demo mode (days-based window):**
```sql
SELECT
    step_id,
    COUNT(DISTINCT user_id)                                         AS unique_users,
    -- COMPLETION RATE: sessions that have a step_complete event
    ROUND(SUM(CASE WHEN event_type = 'step_complete' THEN 1 ELSE 0 END)
          * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2)         AS completion_rate_pct,
    -- ABANDON RATE: sessions that have an abandon event
    ROUND(SUM(CASE WHEN event_type = 'abandon' THEN 1 ELSE 0 END)
          * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2)         AS abandon_rate_pct,
    -- ERROR RATE: sessions with at least one error event
    ROUND(SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END)
          * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2)         AS error_rate_pct,
    -- AVERAGE DWELL TIME: from page_view and step_complete duration_ms
    COALESCE(ROUND(AVG(CASE WHEN event_type IN ('page_view','step_complete')
                        THEN duration_ms ELSE NULL END), 0), 0)    AS avg_dwell_ms,
    -- RAGE CLICK RATE: ratio of users with rage_click to total users
    ROUND(SUM(CASE WHEN event_type = 'rage_click' THEN 1 ELSE 0 END)
          * 1.0 / NULLIF(COUNT(DISTINCT user_id), 0), 4)           AS avg_rage_clicks,
    -- RETRY RATE: retry_count from error event metadata
    COALESCE(ROUND(AVG(CASE WHEN event_type = 'error'
        THEN CAST(json_extract_string(metadata, '$.retry_count') AS DOUBLE)
        ELSE NULL END), 4), 0)                                      AS avg_retries
FROM events
WHERE
    journey_id = 'onboarding'              -- configurable via JOURNEY_CONFIG
    AND timestamp >= NOW() - INTERVAL '30 days'  -- demo: days-based
GROUP BY step_id
ORDER BY step_id
```

**Realtime mode difference:** Replace the WHERE clause temporal condition:
```sql
AND received_at >= NOW() - INTERVAL '60 minutes'
```

**Edge cases handled:**
- `NULLIF(COUNT(DISTINCT user_id), 0)` → division by zero protection (empty step)
- `COALESCE(..., 0)` → NULL protection for steps with no dwell events or retry data
- `json_extract_string()` → DuckDB native JSON path

### 9.2 get_funnel_dropoff() — Sequential Funnel Query

```sql
WITH funnel AS (
    SELECT
        step_id,
        COUNT(DISTINCT user_id) AS users_entered
    FROM events
    WHERE journey_id = 'onboarding'
      AND timestamp >= NOW() - INTERVAL '30 days'
      AND event_type = 'page_view'
    GROUP BY step_id
),
ordered AS (
    SELECT
        f1.step_id,
        f1.users_entered,
        LEAD(f1.users_entered) OVER (
            ORDER BY ARRAY_POSITION(ARRAY['landing_page','sign_up_form',
                'email_verification','profile_setup','first_action','completion'],
                f1.step_id)
        ) AS next_step_users
    FROM funnel f1
)
SELECT
    step_id,
    users_entered                AS users,
    CASE WHEN next_step_users IS NULL THEN 0.0
         ELSE ROUND((users_entered - next_step_users) * 100.0 / users_entered, 2)
    END                          AS drop_off_pct
FROM ordered
ORDER BY ARRAY_POSITION(ARRAY['landing_page','sign_up_form',
    'email_verification','profile_setup','first_action','completion'], step_id)
```

**Notes:**
- `ARRAY_POSITION()` enforces journey step ordering independent of event timestamps
- Steps with no page_view events return 0 users and 0% drop-off
- Final step (completion) always has drop_off_pct = 0.0

### 9.3 query_events() — Sampled Event Query

```sql
-- Used by data_worker for raw event sampling
SELECT *
FROM events
WHERE journey_id = 'onboarding'
  AND step_id = ?                         -- optional step filter
  AND event_type = ?                      -- optional event type filter
  AND timestamp >= NOW() - INTERVAL '30 days'
ORDER BY timestamp DESC
LIMIT 100
```

### 9.4 get_live_snapshot() — Rolling Count (Realtime Only)

```sql
-- Runs against live_events directly (not VIEW), uses received_at for precision
SELECT
    step_id,
    COUNT(*) AS event_count,
    COUNT(DISTINCT user_id) AS unique_users,
    MIN(received_at) AS first_event_at,
    MAX(received_at) AS last_event_at
FROM live_events
WHERE received_at >= NOW() - INTERVAL ? MINUTES
GROUP BY step_id
ORDER BY event_count DESC
```

### 9.5 API Key Validation Query

```sql
-- Every POST /collect/batch runs this before writing any events
SELECT active
FROM api_keys
WHERE api_key = ?
LIMIT 1
```

**Logic:**
- No row returned → 401 Unauthorized
- `active = FALSE` → 401 Unauthorized
- `active = TRUE` → proceed with event batch

---

## 10. Schema Constraints and Rules

### 10.1 DuckDB Type Rules

| Field | Constraint | Reason |
|---|---|---|
| event_id | VARCHAR, min 8 chars | UUID strings are 36 chars; min 8 allows short test IDs |
| event_type | Constrained in Pydantic, not DuckDB | DuckDB doesn't enforce enum; Pydantic validates at API boundary |
| timestamp | TIMESTAMPTZ (not TIMESTAMP) | Timezone-aware required for cross-system comparisons |
| duration_ms | BIGINT DEFAULT 0 | Never NEGATIVE; page_view and instant events are 0 |
| metadata | VARCHAR DEFAULT '{}' | Stored as JSON string; DuckDB json_extract for access |
| active | BOOLEAN DEFAULT TRUE | Keys start active; set FALSE to revoke |

### 10.2 ChromaDB Metadata String Rule

**ALL ChromaDB metadata fields must be strings:**

```python
# CORRECT:
metadata = {
    "priority": str(3),          # "3" not 3
    "score":    str(87),         # "87" not 87
    "step_id":  str("email_v"),  # already str, str() is idempotent
}

# INCORRECT (raises ChromaDB ValueError):
metadata = {
    "priority": 3,               # int not allowed
    "score":    87.5,            # float not allowed
}
```

### 10.3 Pydantic Validation Rules

| Field | Rule | Violation Response |
|---|---|---|
| event_type | Must be in ALLOWED_EVENT_TYPES | HTTP 422 Unprocessable Entity |
| event_id | min_length=8 | HTTP 422 |
| duration_ms | ge=0 | HTTP 422 |
| batch events | 1–100 events per batch | HTTP 422 |
| url | Sanitised by validator (not rejected) | URL cleaned, no error |

### 10.4 DuckDB Connection Rules

| Location | Connection Type | Rule |
|---|---|---|
| journey_data_server.py | READ ONLY | Module-level singleton, created once |
| collector/api.py | READ+WRITE | Module-level singleton, created once |
| Other components | NONE | No other components access DuckDB directly |

```python
# Correct pattern (module-level singleton):
# At module level in journey_data_server.py:
_conn: duckdb.DuckDBPyConnection | None = None

def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(DUCKDB_PATH), read_only=True)  # MCP: read-only
        _setup_views(_conn)    # Create VIEW from Parquet or live_events
    return _conn

# Correct pattern in collector/api.py:
_conn = duckdb.connect(str(DUCKDB_PATH))  # Read-write singleton
_create_tables(_conn)  # Create live_events + api_keys if not exist
```

---

## 11. Indexes and Performance

### 11.1 Recommended DuckDB Indexes (Realtime Mode)

DuckDB auto-indexes PRIMARY KEY columns. For performance with large live_events tables:

```sql
-- Step-level query optimisation (most common):
CREATE INDEX IF NOT EXISTS idx_live_events_step
    ON live_events (step_id, journey_id, received_at);

-- Time-window optimisation (for rolling queries):
CREATE INDEX IF NOT EXISTS idx_live_events_time
    ON live_events (received_at);

-- User-level session queries:
CREATE INDEX IF NOT EXISTS idx_live_events_user
    ON live_events (user_id, session_id);
```

**PoC note:** Indexes are optional for PoC (DuckDB OLAP engine scans efficiently up to ~1M rows). Add for realtime mode if >100K events are expected during demo.

### 11.2 ChromaDB Performance

ChromaDB uses HNSW (Hierarchical Navigable Small World) indexing:
- Automatically managed by ChromaDB
- `search_insights(n_results=n)` guard: `n = min(n, collection.count())`
- For PoC collection size (< 50 insights), HNSW lookup is < 5ms

### 11.3 Parquet Query Performance

DuckDB `read_parquet()` is a full column scan:
- For 15,000 rows: < 100ms per query
- Push-down predicates applied automatically (WHERE clause)
- No indexes needed for demo scale

---

## 12. Migration Notes

### 12.1 Demo to Realtime Migration

No migration needed — both modes share the same DuckDB file. Mode change:
1. Set `CJI_MODE=realtime` in `.env`
2. Start collector: `uvicorn collector.api:app` (creates live_events table + VIEW)
3. Run analysis — Journey Data MCP auto-detects mode and queries live_events

### 12.2 PoC to Production Migration (Phase 3)

**DuckDB → PostgreSQL:**

```sql
-- Events table (replaces live_events):
CREATE TABLE events (
    event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    session_id  UUID NOT NULL,
    journey_id  VARCHAR(100) NOT NULL,
    step_id     VARCHAR(100) NOT NULL,
    event_type  VARCHAR(50) NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    url         TEXT DEFAULT '',
    metadata    JSONB DEFAULT '{}',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_id   UUID NOT NULL  -- Multi-tenant addition
)
-- Use TimescaleDB hypertable for time-series:
-- SELECT create_hypertable('events', 'timestamp');
```

**ChromaDB → pgvector:**
```sql
-- Insights table replacing ChromaDB:
CREATE TABLE insights (
    insight_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id     VARCHAR(100) NOT NULL,
    title       TEXT NOT NULL,
    root_cause  TEXT NOT NULL,
    category    VARCHAR(20) NOT NULL,
    evidence    JSONB DEFAULT '[]',
    suggested_fix TEXT NOT NULL,
    fix_effort  VARCHAR(20) NOT NULL,
    priority    SMALLINT NOT NULL,
    score       SMALLINT NOT NULL,
    tenant_id   UUID NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    embedding   vector(384)  -- pgvector extension
);
CREATE INDEX ON insights USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

**SQLite → Redis (LangGraph):**
```python
# Phase 3 checkpoint store:
from langgraph.checkpoint.redis import AsyncRedisSaver
checkpointer = AsyncRedisSaver.from_conn_string("redis://localhost:6379")
graph = builder.compile(checkpointer=checkpointer, interrupt_before=["report_worker"])
```
