"""Apply Spec 02 code changes with anchor verification.

Every edit checks its anchor (exact text, or line numbers plus expected content)
before anything is written. If any check fails, no file is modified.
Line endings (CRLF) and encoding (UTF-8, no BOM) are preserved.
Usage: python apply_spec02.py <cji_agent dir> [--dry-run]
"""
import re
import sys
from pathlib import Path

APP = Path(sys.argv[1])
DRY = "--dry-run" in sys.argv
pending = {}   # path -> new LF text
report = []


def load(rel):
    p = APP / rel
    if p in pending:
        return pending[p]
    raw = p.read_bytes().decode("utf-8")
    assert not raw.startswith("\ufeff"), f"{rel}: BOM present"
    return raw.replace("\r\n", "\n")


def save(rel, text):
    pending[APP / rel] = text


def replace_once(rel, old, new, label):
    t = load(rel)
    n = t.count(old)
    assert n == 1, f"{rel} [{label}]: anchor found {n} times"
    save(rel, t.replace(old, new))
    report.append(f"ok  {rel}: {label}")


def replace_lines(rel, start, end, new, checks, label):
    """Replace 1-based inclusive line range after verifying expected line prefixes."""
    lines = load(rel).split("\n")
    for ln, prefix in checks:
        actual = lines[ln - 1].strip()
        assert actual.startswith(prefix), f"{rel} [{label}] line {ln}: expected {prefix!r}, got {actual!r}"
    new_lines = new.split("\n")
    lines[start - 1:end] = new_lines
    save(rel, "\n".join(lines))
    report.append(f"ok  {rel}: {label} (lines {start}-{end})")


def regex_sub(rel, pattern, repl, expected, label):
    t = load(rel)
    new, n = re.subn(pattern, repl, t)
    assert n == expected, f"{rel} [{label}]: {n} matches, expected {expected}"
    save(rel, new)
    report.append(f"ok  {rel}: {label} ({n} replacements)")


# ═════════════════════════════════════════════════════════════════════════════
# U-5 + R-03 + R-04 — collector/api.py (bottom-up so line numbers stay valid)
# ═════════════════════════════════════════════════════════════════════════════
API = "collector/api.py"

replace_lines(API, 214, 220, '''\
@app.post("/admin/api-keys")
def create_api_key(data: AdminKeyCreate, x_cji_admin_key: str = Header(...)):
    # Disabled until a real admin key is configured; constant-time comparison (R-03).
    if not admin_key_usable(CJI_ADMIN_KEY) or not secrets.compare_digest(
        x_cji_admin_key.encode("utf-8"), CJI_ADMIN_KEY.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Invalid ADMIN Key")

    new_key = f"cji_live_{secrets.token_hex(16)}"''',
    [(214, '@app.post("/admin/api-keys")'), (216, "if x_cji_admin_key != CJI_ADMIN_KEY:"),
     (219, "import secrets"), (220, 'new_key = f"cji_live_')], "admin endpoint")

replace_lines(API, 201, 212, '''\
@app.get("/live/stats")
def live_stats(minutes: int = Query(60, ge=1, le=43200)):
    # minutes is validated (1 minute .. 30 days) and bound, never formatted into SQL (R-04).
    with engine.begin() as conn:
        stats = conn.execute(text("""
            SELECT step_id, COUNT(*) as ev_count 
            FROM live_events 
            WHERE timestamp >= current_timestamp - (:minutes * INTERVAL '1 minute')
            GROUP BY step_id 
            ORDER BY ev_count DESC
        """), {"minutes": minutes}).fetchall()
        
    return {"window": f"{minutes}m", "stats": [{"step": r[0], "count": r[1]} for r in stats]}''',
    [(201, '@app.get("/live/stats")'), (202, "def live_stats(minutes: int = 60):"),
     (212, 'return {"window"')], "live_stats binding")

replace_lines(API, 89, 93, '''\
@app.on_event("startup")
async def startup_event():
    # Fail closed before touching the database (R-03).
    validate_collector_settings(CJI_ENV, CJI_ADMIN_KEY, CJI_CORS_ORIGINS)
    logger.info("Connecting to Database...")
    _create_tables()
    asyncio.create_task(keep_alive())''',
    [(89, '@app.on_event("startup")'), (92, "_create_tables()"), (93, "asyncio.create_task(keep_alive())")],
    "startup validation")

replace_lines(API, 58, 70, '''\
        # Development-only key for local tracker testing. No live or production
        # key is ever written at startup (refactoring.md R-03).
        if CJI_ENV == "development":
            conn.execute(text("""
                INSERT INTO api_keys (api_key, journey_name, description) 
                VALUES ('cji_dev_localtest', 'onboarding', 'Local Development')
                ON CONFLICT (api_key) DO NOTHING
            """))''',
    [(58, "# Insert development key"), (61, "VALUES ('cji_dev_localtest'"),
     (65, "# Insert live tracking key"), (70, '"""))')], "seeded keys")

replace_lines(API, 28, 28, '''\
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ─── STARTUP SETTINGS (fail closed outside explicit development) ───────────
MIN_ADMIN_KEY_LENGTH = 32


def admin_key_usable(key: Optional[str]) -> bool:
    """True only for a configured admin key that is not a shipped default."""
    return bool(key) and key not in KNOWN_DEFAULT_ADMIN_KEYS


def validate_collector_settings(env: str, admin_key: Optional[str], origins: List[str]) -> None:
    """Refuse to start with unsafe settings unless CJI_ENV is explicitly 'development'."""
    if (env or "").strip().lower() == "development":
        return
    problems = []
    if not admin_key_usable(admin_key) or len(admin_key) < MIN_ADMIN_KEY_LENGTH:
        problems.append(
            f"CJI_ADMIN_KEY must be a random value of at least {MIN_ADMIN_KEY_LENGTH} characters"
        )
    if not origins:
        problems.append("CJI_CORS_ORIGINS must list the allowed browser origins (comma-separated)")
    if problems:
        raise RuntimeError(
            f"Collector refused to start (CJI_ENV={env or 'unset'}): "
            + "; ".join(problems)
            + ". For local use set CJI_ENV=development."
        )''',
    [(28, "engine = create_engine(DATABASE_URL, pool_pre_ping=True)")], "settings validation")

replace_lines(API, 19, 25, '''\
app.add_middleware(
    CORSMiddleware,
    allow_origins=CJI_CORS_ORIGINS,   # explicit list from config, never "*" by default
    allow_credentials=False,          # tracker authenticates with a header key, not cookies
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-CJI-Key", "X-CJI-Admin-Key"],
)''',
    [(19, "app.add_middleware("), (21, 'allow_origins=["*"],'), (22, "allow_credentials=True,"), (25, ")")],
    "CORS")

replace_lines(API, 13, 13, '''\
from config import (
    CJI_ADMIN_KEY,
    CJI_CORS_ORIGINS,
    CJI_ENV,
    DATABASE_URL,
    KNOWN_DEFAULT_ADMIN_KEYS,
    ROOT,
)''', [(13, "from cji_agent.config import DATABASE_URL, CJI_ADMIN_KEY, ROOT")], "flat config import")

replace_lines(API, 8, 8,
    "from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends, Query",
    [(8, "from fastapi import FastAPI, BackgroundTasks, HTTPException, Header, Depends")], "Query import")

replace_lines(API, 4, 4, "import asyncio\nimport secrets", [(4, "import asyncio")], "secrets import")

# ═════════════════════════════════════════════════════════════════════════════
# R-03 — config.py constants (stdlib only; no validation at import)
# ═════════════════════════════════════════════════════════════════════════════
replace_once("config.py",
    'CJI_ADMIN_KEY:  str = os.getenv("CJI_ADMIN_KEY", "change-me-in-production")\n',
    'CJI_ADMIN_KEY:  str = os.getenv("CJI_ADMIN_KEY", "change-me-in-production")\n'
    '\n'
    '# ── DEPLOYMENT ENVIRONMENT (collector fails closed outside "development") ─────\n'
    '# Must be set to "development" explicitly; anything else is treated as production.\n'
    'CJI_ENV: str = os.getenv("CJI_ENV", "production").lower().strip()\n'
    '\n'
    '# Admin key values that must never authenticate (shipped defaults).\n'
    'KNOWN_DEFAULT_ADMIN_KEYS: frozenset = frozenset({"", "change-me", "change-me-in-production"})\n'
    '\n'
    '# Browser origins allowed to call the collector (comma-separated). Local\n'
    '# dashboard/frontend ports are allowed by default in development only.\n'
    '_DEV_CORS_ORIGINS = "http://localhost:3000,http://localhost:8501,http://127.0.0.1:8501"\n'
    'CJI_CORS_ORIGINS: list = [\n'
    '    origin.strip()\n'
    '    for origin in (\n'
    '        os.getenv("CJI_CORS_ORIGINS") or (_DEV_CORS_ORIGINS if CJI_ENV == "development" else "")\n'
    '    ).split(",")\n'
    '    if origin.strip()\n'
    ']\n',
    "CJI_ENV / CORS / known defaults")

# ═════════════════════════════════════════════════════════════════════════════
# U-5 — requirements.txt: keep SQLAlchemy on the psycopg2 default driver
# ═════════════════════════════════════════════════════════════════════════════
replace_once("requirements.txt", "SQLAlchemy>=2.0.0\n",
    "SQLAlchemy>=2.0.0,<2.1   # 2.1 changed the postgresql:// default driver to psycopg (v3); we ship psycopg2\n",
    "SQLAlchemy cap")

# ═════════════════════════════════════════════════════════════════════════════
# R-03 — .env.example documents the two new variables
# ═════════════════════════════════════════════════════════════════════════════
replace_once(".env.example", "COLLECTOR_PORT=8000\nCJI_ADMIN_KEY=change-me-in-production\n",
    "COLLECTOR_PORT=8000\n"
    "# Admin key for POST /admin/api-keys. The value below is always rejected.\n"
    "# Outside CJI_ENV=development the collector will not start unless this is a\n"
    "# random value of at least 32 characters, e.g.:\n"
    "#   python -c \"import secrets; print(secrets.token_urlsafe(32))\"\n"
    "CJI_ADMIN_KEY=change-me-in-production\n"
    "\n"
    "# ── DEPLOYMENT ENVIRONMENT ─────────────────────────────────────────────────\n"
    "# development | test | production. Anything except \"development\" fails closed:\n"
    "# the collector then requires CJI_ADMIN_KEY (above) and CJI_CORS_ORIGINS.\n"
    "CJI_ENV=development\n"
    "# Browser origins allowed to call the collector (comma-separated, no \"*\").\n"
    "# Leave empty in development to allow the local dashboard/frontend ports.\n"
    "CJI_CORS_ORIGINS=\n",
    "CJI_ENV / CJI_CORS_ORIGINS")

# ═════════════════════════════════════════════════════════════════════════════
# U-4 — supervisor VALID_WORKERS + stale test expectation
# ═════════════════════════════════════════════════════════════════════════════
replace_once("agents/supervisor.py", 'logger = logging.getLogger("cji.supervisor")\n',
    'logger = logging.getLogger("cji.supervisor")\n'
    '\n'
    '# Every target route() may return. Must equal graph.py\'s conditional edge map\n'
    '# (enforced by tests/test_p0_security.py::test_u4_valid_workers_matches_graph_edges).\n'
    'VALID_WORKERS: frozenset = frozenset({\n'
    '    "ingestion_worker",\n'
    '    "data_worker",\n'
    '    "friction_worker",\n'
    '    "insight_worker",\n'
    '    "report_worker",\n'
    '    "__end__",\n'
    '})\n',
    "VALID_WORKERS")

replace_lines("tests/test_supervisor.py", 290, 292, '''\
        """VALID_WORKERS must contain every route() target: 5 workers + __end__.

        v2.0 added ingestion_worker; this expectation predated it (Spec 02, U-4).
        """
        expected = {"ingestion_worker", "data_worker", "friction_worker",
                    "insight_worker", "report_worker", "__end__"}''',
    [(290, '"""VALID_WORKERS must contain exactly the 4 workers + __end__."""'),
     (291, 'expected = {"data_worker", "friction_worker", "insight_worker",'),
     (292, '"report_worker", "__end__"}')], "stale expectation")

# ═════════════════════════════════════════════════════════════════════════════
# R-01 — ingestion worker uses the shared MCP client
# ═════════════════════════════════════════════════════════════════════════════
IW = "agents/ingestion_worker.py"
replace_lines(IW, 14, 38, '''\
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import INGESTION_CONFIDENCE_THRESHOLD
from state import CJIState, IngestionResult, WorkerStatus
from tools.mcp_client import call_tool, mcp_session

log = logging.getLogger("cji.ingestion_worker")

# Logical MCP service name. The endpoint is resolved by tools.mcp_client.SERVER_URLS,
# the same mapping every other worker uses (refactoring.md R-01).
INGESTION_SERVICE = "cji-ingestion-intelligence"''',
    [(14, "import json"), (19, "import requests"), (27, 'INGESTION_MCP_URL = "http://localhost:8004"'),
     (30, "def _call_tool(tool_name: str, args: dict) -> dict:"), (38, "return resp.json()")],
    "imports and transport")
lines = load(IW).split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("def ingestion_worker(state: CJIState) -> dict:"))
save(IW, "\n".join(lines[:start] + ["async def ingestion_worker(state: CJIState) -> dict:"] + lines[start + 1:]))
report.append(f"ok  {IW}: async def")

replace_once(IW, '''        return {
            "next_worker":    "data_worker",
            "worker_statuses": state.get("worker_statuses", []) + [''',
'''        return {
            "ingestion_pending_files": [],
            "next_worker":    "data_worker",
            "worker_statuses": state.get("worker_statuses", []) + [''', "consume files (no-op path)")

replace_once(IW, '''        try:
            # Step 1 — Schema detection (LLM or cache)
            log.info(f"Detecting schema: {file_path}")
            mapping_config = _call_tool("detect_schema", {
                "file_path":   file_path,
                "source_hint": source_hint,
            })

            confidence = mapping_config.get("confidence", 0.0)
            log.info(f"  → {mapping_config.get('detected_source')} | confidence: {confidence}")

            # Step 2 — Confidence gate
            if confidence < INGESTION_CONFIDENCE_THRESHOLD:
                log.warning(f"  → Low confidence ({confidence}) — flagging for human review")
                pending_review.append({
                    "file_path":      file_path,
                    "mapping_config": mapping_config,
                    "confidence":     confidence,
                    "flagged_at":     datetime.now(timezone.utc).isoformat(),
                })
                files_flagged += 1
                continue

            # Step 3 — Auto-ingest
            log.info(f"  → Auto-ingesting (confidence {confidence} ≥ {INGESTION_CONFIDENCE_THRESHOLD})")
            ingest_result = _call_tool("ingest_to_store", {
                "file_path":      file_path,
                "mapping_config": mapping_config,
                "mode":           state.get("mode", "demo"),
            })
''', '''        try:
            # One MCP session per file: a dropped connection affects only that file.
            async with mcp_session(INGESTION_SERVICE) as session:
                # Step 1 — Schema detection (LLM or cache)
                log.info(f"Detecting schema: {file_path}")
                mapping_config = await call_tool(session, "detect_schema", {
                    "file_path":   file_path,
                    "source_hint": source_hint,
                })

                confidence = mapping_config.get("confidence", 0.0)
                log.info(f"  → {mapping_config.get('detected_source')} | confidence: {confidence}")

                # Step 2 — Confidence gate
                if confidence < INGESTION_CONFIDENCE_THRESHOLD:
                    log.warning(f"  → Low confidence ({confidence}) — flagging for human review")
                    pending_review.append({
                        "file_path":      file_path,
                        "mapping_config": mapping_config,
                        "confidence":     confidence,
                        "flagged_at":     datetime.now(timezone.utc).isoformat(),
                    })
                    files_flagged += 1
                    continue

                # Step 3 — Auto-ingest
                log.info(f"  → Auto-ingesting (confidence {confidence} ≥ {INGESTION_CONFIDENCE_THRESHOLD})")
                ingest_result = await call_tool(session, "ingest_to_store", {
                    "file_path":      file_path,
                    "mapping_config": mapping_config,
                    "mode":           state.get("mode", "demo"),
                })
''', "MCP session calls")

replace_once(IW, '''    return {
        "ingestion_results":        results,''', '''    # Pending files are always consumed, so a failed or flagged file cannot send
    # the supervisor back to this worker until the iteration cap (Spec 02, R-01).
    return {
        "ingestion_pending_files":  [],
        "ingestion_results":        results,''', "consume files (main path)")

# ═════════════════════════════════════════════════════════════════════════════
# R-02 + R-04 — journey_data_server.py (bottom-up)
# ═════════════════════════════════════════════════════════════════════════════
JD = "mcp_servers/journey_data_server.py"
NOSEC = "  # nosec B608 - FROM clause is a fixed string from get_from_clause(); all values are bound"

replace_lines(JD, 339, 373, '''\
@mcp.tool()
async def get_live_snapshot(minutes: int = 15) -> dict:
    """Realtime mode only. Returns rolling event counts for the last N minutes."""
    if CJI_MODE == "demo":
        return {
            "error": "get_live_snapshot is only available in realtime mode",
            "mode": "demo",
            "message": "Switch to CJI_MODE=realtime to use this tool"
        }
        
    sql = """
        SELECT 
            step_id,
            COUNT(*) AS event_count,
            COUNT(DISTINCT user_id) AS unique_users,
            CAST(MIN(timestamp) AS VARCHAR) AS first_event_at,
            CAST(MAX(timestamp) AS VARCHAR) AS last_event_at
        FROM live_events
        WHERE timestamp >= NOW() - (:minutes * INTERVAL '1 minute')
        GROUP BY step_id
        ORDER BY event_count DESC
    """
    
    try:
        df = execute_query(sql, {"minutes": int(minutes)})
        steps = json.loads(df.to_json(orient='records'))
        
        return {
            "window_mins": minutes,
            "steps": steps,
            "total_events": sum(s["event_count"] for s in steps),
            "snapshot_at": str(df["last_event_at"].max()) if not df.empty else None
        }
    except Exception as e:
        return {"error": str(e)}''',
    [(339, "@mcp.tool()"), (340, "async def get_live_snapshot"), (373, 'return {"error": str(e)}')],
    "get_live_snapshot")

replace_lines(JD, 287, 336, f'''\
@mcp.tool()
async def query_events(limit: int = 100, step_id: str = None, event_type: str = None) -> dict:
    """Returns a sample of raw events with optional filters."""
    journey_id = JOURNEY_CONFIG["name"]

    if CJI_MODE == "demo":
        # Optional filters are bound parameters; a NULL filter matches everything.
        sql = """
            SELECT * FROM events
            WHERE journey_id = ?
              AND (CAST(? AS VARCHAR) IS NULL OR step_id = ?)
              AND (CAST(? AS VARCHAR) IS NULL OR event_type = ?)
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params = [journey_id, step_id, step_id, event_type, event_type, int(limit)]
        try:
            df = execute_demo_query(sql, params)
            if 'timestamp' in df.columns:
                df['timestamp'] = df['timestamp'].astype(str)
            events = json.loads(df.to_json(orient='records'))
            return {{"events": events, "count": len(events), "step_id_filter": step_id, "event_type_filter": event_type}}
        except Exception as e:
            return {{"error": str(e), "events": [], "count": 0}}

    else:
        from_clause_q = get_from_clause(journey_id)
        sql = f"""
            SELECT * FROM {{from_clause_q}}
            WHERE journey_id = :journey_id
              AND (CAST(:step_id AS TEXT) IS NULL OR step_id = :step_id)
              AND (CAST(:event_type AS TEXT) IS NULL OR event_type = :event_type)
              AND timestamp >= NOW() - INTERVAL '60 minutes'
            ORDER BY timestamp DESC
            LIMIT :limit
        """{NOSEC}
        params = {{"journey_id": journey_id, "step_id": step_id, "event_type": event_type, "limit": int(limit)}}
        try:
            df = execute_query(sql, params)
            if 'timestamp' in df.columns:
                df['timestamp'] = df['timestamp'].astype(str)
            events = json.loads(df.to_json(orient='records'))
            return {{"events": events, "count": len(events), "step_id_filter": step_id, "event_type_filter": event_type}}
        except Exception as e:
            return {{"error": str(e), "events": [], "count": 0}}''',
    [(287, "@mcp.tool()"), (288, "async def query_events"), (336, 'return {"error": str(e), "events": [], "count": 0}')],
    "query_events")

FUNNEL_TAIL = '''        ranked AS (
            SELECT step_id, users_entered, step_order,
                LEAD(users_entered) OVER (ORDER BY step_order) AS next_step_users
            FROM ordered
        )
        SELECT
            step_id,
            users_entered AS users,
            CASE WHEN next_step_users IS NULL THEN 0.0
                 ELSE ROUND((users_entered - next_step_users) * 100.0 / users_entered, 2)
            END AS drop_off_pct
        FROM ranked
        ORDER BY step_order'''

replace_lines(JD, 206, 285, f'''\
@mcp.tool()
async def get_funnel_dropoff(days_back: int = 30, minutes_back: int = 0) -> dict:
    """Returns sequential funnel drop-off percentages."""
    journey_id = JOURNEY_CONFIG["name"]
    steps = list(JOURNEY_CONFIG["steps"])

    # Step order comes from the bound step list (position in JOURNEY_CONFIG["steps"]),
    # not from step names formatted into SQL. Unknown steps sort last, as before.
    if CJI_MODE == "demo":
        sql = """
        WITH funnel AS (
            SELECT step_id, COUNT(DISTINCT user_id) AS users_entered
            FROM events
            WHERE journey_id = ? AND event_type = 'page_view'
            GROUP BY step_id
        ),
        ordered AS (
            SELECT f1.step_id, f1.users_entered,
                COALESCE(list_position(?, f1.step_id), 999) AS step_order
            FROM funnel f1
        ),
{FUNNEL_TAIL}
        """
        try:
            df = execute_demo_query(sql, [journey_id, steps])
            funnel = json.loads(df.to_json(orient='records'))
            overall_pct = 0.0
            if funnel and funnel[0]['users'] > 0:
                overall_pct = round((funnel[0]['users'] - funnel[-1]['users']) * 100.0 / funnel[0]['users'], 2)
            return {{"journey_id": journey_id, "funnel": funnel, "overall_completion_pct": 100.0 - overall_pct}}
        except Exception as e:
            logger.error(f"[demo] Funnel error: {{e}}")
            return {{"error": str(e), "funnel": []}}

    else:
        from_clause = get_from_clause(journey_id)
        window = minutes_back if minutes_back > 0 else 60
        sql = f"""
        WITH funnel AS (
            SELECT step_id, COUNT(DISTINCT user_id) AS users_entered
            FROM {{from_clause}}
            WHERE journey_id = :journey_id
              AND timestamp >= NOW() - (:window * INTERVAL '1 minute')
              AND event_type = 'page_view'
            GROUP BY step_id
        ),
        ordered AS (
            SELECT f1.step_id, f1.users_entered,
                COALESCE(array_position(CAST(:steps AS TEXT[]), CAST(f1.step_id AS TEXT)), 999) AS step_order
            FROM funnel f1
        ),
{FUNNEL_TAIL}
        """{NOSEC}
        try:
            df = execute_query(sql, {{"journey_id": journey_id, "window": int(window), "steps": steps}})
            funnel = json.loads(df.to_json(orient='records'))
            overall_pct = 0.0
            if funnel and funnel[0]['users'] > 0:
                overall_pct = round((funnel[0]['users'] - funnel[-1]['users']) * 100.0 / funnel[0]['users'], 2)
            return {{"journey_id": journey_id, "funnel": funnel, "overall_completion_pct": 100.0 - overall_pct}}
        except Exception as e:
            logger.error(f"[realtime] Funnel error: {{e}}")
            return {{"error": str(e), "funnel": []}}''',
    [(206, "@mcp.tool()"), (207, "async def get_funnel_dropoff"), (285, 'return {"error": str(e), "funnel": []}')],
    "get_funnel_dropoff")

METRIC_COLS = '''                step_id,
                COUNT(DISTINCT user_id) AS unique_users,
                ROUND(SUM(CASE WHEN event_type = 'step_complete' THEN 1 ELSE 0 END)
                      * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS completion_rate_pct,
                ROUND(SUM(CASE WHEN event_type = 'abandon' THEN 1 ELSE 0 END)
                      * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS abandon_rate_pct,
                ROUND(SUM(CASE WHEN event_type = 'error' THEN 1 ELSE 0 END)
                      * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) AS error_rate_pct,
                COALESCE(ROUND(AVG(CASE WHEN event_type IN ('page_view','step_complete')
                                    THEN duration_ms ELSE NULL END), 0), 0) AS avg_dwell_ms,
                ROUND(SUM(CASE WHEN event_type = 'rage_click' THEN 1 ELSE 0 END)
                      * 1.0 / NULLIF(COUNT(DISTINCT user_id), 0), 4) AS avg_rage_clicks,'''

replace_lines(JD, 122, 204, f'''\
@mcp.tool()
async def get_step_metrics(days_back: int = 30, minutes_back: int = 0) -> dict:
    """Returns aggregated metrics per step."""
    journey_id = JOURNEY_CONFIG["name"]

    if CJI_MODE == "demo":
        # ── DuckDB on local parquet ──────────────────────────────────────────
        sql = """
            SELECT
{METRIC_COLS}
                COALESCE(ROUND(AVG(CASE WHEN event_type = 'error'
                    THEN TRY_CAST(json_extract_string(metadata, '$.retry_count') AS DOUBLE)
                    ELSE NULL END), 4), 0) AS avg_retries
            FROM events
            WHERE journey_id = ?
            GROUP BY step_id
            ORDER BY step_id
        """
        try:
            df = execute_demo_query(sql, [journey_id])
            metrics = json.loads(df.to_json(orient='records'))
            return {{
                "journey_id": journey_id,
                "window_days": days_back,
                "window_minutes": None,
                "step_metrics": metrics,
                "total_steps": len(metrics),
            }}
        except Exception as e:
            logger.error(f"[demo] Error querying step metrics: {{e}}")
            return {{"error": str(e), "step_metrics": [], "total_steps": 0}}

    else:
        # ── Postgres (realtime) ──────────────────────────────────────────────
        from_clause = get_from_clause(journey_id)
        window = minutes_back if minutes_back > 0 else 60
        sql = f"""
            SELECT
{METRIC_COLS}
                COALESCE(ROUND(AVG(CASE WHEN event_type = 'error'
                    THEN CAST(NULLIF(metadata->>'retry_count', '') AS NUMERIC)
                    ELSE NULL END), 4), 0) AS avg_retries
            FROM {{from_clause}}
            WHERE journey_id = :journey_id
              AND timestamp >= NOW() - (:window * INTERVAL '1 minute')
            GROUP BY step_id
            ORDER BY step_id
        """{NOSEC}
        try:
            df = execute_query(sql, {{"journey_id": journey_id, "window": int(window)}})
            metrics = json.loads(df.to_json(orient='records'))
            return {{
                "journey_id": journey_id,
                "window_days": None,
                "window_minutes": window,
                "step_metrics": metrics,
                "total_steps": len(metrics),
            }}
        except Exception as e:
            logger.error(f"[realtime] Error querying step metrics: {{e}}")
            return {{"error": str(e), "step_metrics": [], "total_steps": 0}}''',
    [(122, "@mcp.tool()"), (123, "async def get_step_metrics"), (204, 'return {"error": str(e), "step_metrics": [], "total_steps": 0}')],
    "get_step_metrics")

replace_lines(JD, 89, 111, '''\
@mcp.tool()
async def get_system_info() -> dict:
    """Returns mode, data source, and connection status."""
    try:
        if CJI_MODE == "demo":
            # Demo mode is offline: check the Parquet file and DuckDB only,
            # never PostgreSQL (refactoring.md R-02).
            if not EVENTS_PARQUET.exists():
                return {
                    "status": "error",
                    "error": "events.parquet not found — run --generate-data"
                }
            get_demo_conn().execute("SELECT 1").fetchone()
        else:
            execute_query("SELECT 1")

        data_source = "parquet" if CJI_MODE == "demo" else "live_events"
        return {
            "mode": CJI_MODE,
            "data_source": data_source,
            "duckdb_path": str(DUCKDB_PATH),
            "journey_id": JOURNEY_CONFIG["name"],
            "journey_steps": JOURNEY_CONFIG["steps"],
            "status": "ok"
        }
    except Exception as e:
        if CJI_MODE == "demo" and not EVENTS_PARQUET.exists():
            return {
                "status": "error", 
                "error": "events.parquet not found — run --generate-data"
            }
        return {"status": "error", "error": str(e)}''',
    [(89, "@mcp.tool()"), (90, "async def get_system_info"), (94, 'execute_query("SELECT 1")'),
     (111, 'return {"status": "error", "error": str(e)}')], "get_system_info")

replace_lines(JD, 58, 79, '''\
def execute_demo_query(sql: str, params: list | None = None) -> pd.DataFrame:
    """Run SQL against the local events.parquet via DuckDB (demo mode only).

    Values go in ``params`` (DuckDB ``?`` placeholders), never into ``sql``.
    """
    conn = get_demo_conn()
    df = conn.execute(sql, params or []).df()
    return df.fillna(0.0)


def execute_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run SQL against Postgres (realtime).

    Values go in ``params`` (SQLAlchemy ``:name`` placeholders), never into ``sql``.
    """
    # Fixed dialect rewrite only; no values are inserted into the SQL text.
    sql = sql.replace("json_extract_string(metadata, '$.retry_count')", "metadata->>'retry_count'")

    engine = get_pg_engine()
    with engine.begin() as conn:
        df = pd.read_sql(text(sql), conn, params=params or {})
        return df.fillna(0.0)''',
    [(58, "def execute_demo_query(sql: str) -> pd.DataFrame:"), (65, "def execute_query(sql: str, params: list = None)"),
     (70, "sql = sql.replace('?', f\"'{param}'\", 1)"), (79, "return df.fillna(0.0)")], "query helpers")

replace_lines(JD, 17, 23, '''\
def _setup_views(conn: duckdb.DuckDBPyConnection):
    """Setup the events VIEW depending on the current CJI_MODE."""
    if CJI_MODE == "demo":
        # DuckDB cannot bind parameters inside CREATE VIEW. The path comes from
        # config (not user input) and is quote-escaped so it cannot end the literal.
        parquet_path = EVENTS_PARQUET.resolve().as_posix().replace("'", "''")
        conn.execute(
            "CREATE OR REPLACE TEMP VIEW events AS "
            "SELECT * FROM read_parquet('" + parquet_path + "')"  # nosec B608 - escaped config path
        )''',
    [(17, "def _setup_views(conn: duckdb.DuckDBPyConnection):"), (20, 'conn.execute(f"""'), (23, '""")')],
    "parquet view")

# ═════════════════════════════════════════════════════════════════════════════
# R-05 — report_server.py escaping
# ═════════════════════════════════════════════════════════════════════════════
RS = "mcp_servers/report_server.py"
replace_once(RS, "import json\nimport logging\n", "import html\nimport json\nimport logging\n", "html import")
replace_once(RS, 'mcp = FastMCP("cji-report")\n', '''mcp = FastMCP("cji-report")

_ALLOWED_MODES = {"demo", "realtime"}


def _h(value) -> str:
    """HTML-escape a value for element text or a quoted attribute (R-05)."""
    return html.escape("" if value is None else str(value), quote=True)


def _js(obj) -> str:
    """JSON for embedding inside <script>: cannot close the tag or break a JS string."""
    return (
        json.dumps(obj)
        .replace("<", "\\\\u003c")
        .replace(">", "\\\\u003e")
        .replace("&", "\\\\u0026")
        .replace("\\u2028", "\\\\u2028")
        .replace("\\u2029", "\\\\u2029")
    )
''', "escape helpers")
replace_once(RS, "    dropoffs = [step.get('drop_off_pct', 0) for step in funnel_data]\n",
    "    dropoffs = [step.get('drop_off_pct', 0) for step in funnel_data]\n"
    "    # Untrusted values: escape for HTML; mode doubles as a CSS class, so allow-list it.\n"
    "    safe_mode = mode if mode in _ALLOWED_MODES else \"unknown\"\n"
    "    journey_html = _h(journey_name)\n", "safe values")
replace_once(RS, "<title>CJI Report - {journey_name}</title>", "<title>CJI Report - {journey_html}</title>", "title")
replace_once(RS, '<strong>Journey:</strong> {journey_name} | <span class="badge {mode}">{mode.upper()} MODE</span>',
    '<strong>Journey:</strong> {journey_html} | <span class="badge {safe_mode}">{_h(safe_mode.upper())} MODE</span>',
    "header")
replace_once(RS, '<div class="narrative">{narrative}</div>', '<div class="narrative">{_h(narrative)}</div>', "narrative")
replace_once(RS, "<h4>[Priority {priority}] - {ins.get('step_id', 'Unknown Step')}</h4>",
    "<h4>[Priority {_h(priority)}] - {_h(ins.get('step_id', 'Unknown Step'))}</h4>", "insight heading")
replace_once(RS, "<p><strong>Issue:</strong> {ins.get('title', '')}</p>",
    "<p><strong>Issue:</strong> {_h(ins.get('title', ''))}</p>", "insight title")
replace_once(RS, "<p><strong>Root Cause:</strong> {ins.get('root_cause', '')}</p>",
    "<p><strong>Root Cause:</strong> {_h(ins.get('root_cause', ''))}</p>", "insight cause")
replace_once(RS, "<p><strong>Recommendation:</strong> {ins.get('suggested_fix', '')}</p>",
    "<p><strong>Recommendation:</strong> {_h(ins.get('suggested_fix', ''))}</p>", "insight fix")
replace_once(RS, "labels: {json.dumps(labels)},", "labels: {_js(labels)},", "chart labels")
replace_once(RS, "data: {json.dumps(users)},", "data: {_js(users)},", "chart data")

# ═════════════════════════════════════════════════════════════════════════════
# U-2 — retired key placeholders in tracked snippets and docs
# ═════════════════════════════════════════════════════════════════════════════
KEY = r"cji_live_[0-9a-f]{32}"
for rel in ("snippets/api_key.json", "snippets/embed_snippet.html",
            "snippets/useCJITracker.js", "snippets/verify_tracker.py"):
    regex_sub(rel, KEY, "YOUR_TRACKER_API_KEY", 1, "retired key placeholder")
regex_sub("../docs/6-API-Contracts.md", KEY, "cji_live_<redacted>", 2, "retired key placeholder")

# ═════════════════════════════════════════════════════════════════════════════
# New test file: normalise to the repository's CRLF convention
# ═════════════════════════════════════════════════════════════════════════════
save("tests/test_p0_security.py", load("tests/test_p0_security.py"))
report.append("ok  tests/test_p0_security.py: CRLF normalised")

# ── Write everything (only reached if every anchor matched) ─────────────────
for path, text in pending.items():
    data = text.replace("\n", "\r\n").encode("utf-8")
    if not DRY:
        path.write_bytes(data)
print("\n".join(report))
print(f"{'DRY RUN - ' if DRY else ''}{len(pending)} file(s) {'would be ' if DRY else ''}written")
