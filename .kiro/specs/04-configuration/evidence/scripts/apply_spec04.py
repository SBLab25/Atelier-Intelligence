"""
Spec 04 patch script: migrate production callers to settings/.
Every anchor must match the stated number of times before anything is written;
files keep their newline style and UTF-8. Run from anywhere:  python apply_spec04.py
"""
import pathlib
import re
import sys

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
EDITS: dict[str, list[tuple[str, str, int]]] = {}
REWRITES: dict[str, str] = {}
POST: dict[str, list] = {}


def edit(rel: str, old: str, new: str, count: int = 1) -> None:
    EDITS.setdefault(rel, []).append((old, new, count))


def drop_import_if_unused(rel: str, import_line: str, usage: str) -> None:
    """After the edits, remove `import_line` if `usage` (regex) no longer occurs elsewhere."""
    POST.setdefault(rel, []).append((import_line, usage))


SERVE = '''if __name__ == "__main__":
    from mcp_servers._serve import serve

    serve(mcp, "{name}")
'''

# ─────────────────────────────── config.py (facade) ───────────────────────────
REWRITES["config.py"] = '''"""
CJI Configuration (compatibility facade)
========================================
Typed settings and the service registry live in settings/ (Spec 04). This module
re-exports the long-standing constants so existing imports keep working while
callers migrate to settings.get_settings().

Rules:
  - Imports ONLY stdlib, python-dotenv and the pure settings/ package.
  - Values come from settings: process environment > .env > defaults. No secret
    or credential has a default (unset secrets are exported as "").
  - .env is also loaded into the process environment (except CJI_ENV=test) for
    third-party libraries, such as LangSmith, that read it directly.
  - Creates data/, reports/ and the ingestion uploads directory on import until
    every caller calls Settings.ensure_storage() itself.
  - Never import config.py from state.py, domain/ or settings/.
"""
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from settings import get_settings
from settings.model import KNOWN_DEFAULT_ADMIN_KEYS as _KNOWN_DEFAULT_ADMIN_KEYS
from settings.model import secret_value as _secret

if os.getenv("CJI_ENV", "").strip().lower() != "test":
    load_dotenv()

SETTINGS = get_settings()
SETTINGS.ensure_storage()

# ── OPERATION MODE ─────────────────────────────────────────────────────────────
CJI_MODE: str = SETTINGS.app.mode

# ── LLM CONFIGURATION ──────────────────────────────────────────────────────────
LLM_MODEL:       str   = SETTINGS.llm.model
LLM_TEMPERATURE: float = SETTINGS.llm.temperature
LLM_MAX_TOKENS:  int   = SETTINGS.llm.max_tokens

# ── API KEYS ("" when unset; never hardcode values here) ───────────────────────
ANTHROPIC_API_KEY: str = _secret(SETTINGS.llm.anthropic_api_key)
OPENAI_API_KEY:    str = _secret(SETTINGS.llm.openai_api_key)
GROQ_API_KEY:      str = _secret(SETTINGS.llm.groq_api_key)

# ── PATHS ───────────────────────────────────────────────────────────────────────
ROOT:           Path = Path(__file__).parent.resolve()
DATA_DIR:       Path = SETTINGS.storage.data_dir
EVENTS_PARQUET: Path = SETTINGS.storage.events_parquet
DUCKDB_PATH:    Path = SETTINGS.storage.duckdb_path
CHROMA_DIR:     Path = SETTINGS.storage.chroma_dir
REPORTS_DIR:    Path = SETTINGS.storage.reports_dir
CHECKPOINTS_DB: Path = SETTINGS.storage.checkpoints_db

# ── INGESTION INTELLIGENCE (MCP Server 0) ──────────────────────────────────────
INGESTION_UPLOADS_DIR:          Path  = SETTINGS.storage.uploads_dir
INGESTION_MAPPING_REGISTRY:     Path  = SETTINGS.storage.mapping_registry
INGESTION_SAMPLE_ROWS:          int   = SETTINGS.budgets.ingestion_sample_rows
INGESTION_CONFIDENCE_THRESHOLD: float = SETTINGS.budgets.ingestion_confidence_threshold

# ── COLLECTOR ───────────────────────────────────────────────────────────────────
COLLECTOR_URL:  str = SETTINGS.services.get("collector").url
COLLECTOR_PORT: int = SETTINGS.services.get("collector").port
COLLECTOR_HOST: str = "{0.scheme}://{0.hostname}".format(urlsplit(COLLECTOR_URL))
CJI_ADMIN_KEY:  str = _secret(SETTINGS.auth.admin_key)

# ── DEPLOYMENT ENVIRONMENT (collector fails closed outside "development") ─────
CJI_ENV: str = SETTINGS.app.env
KNOWN_DEFAULT_ADMIN_KEYS: frozenset = _KNOWN_DEFAULT_ADMIN_KEYS
CJI_CORS_ORIGINS: list = list(SETTINGS.cors.origins)

# ── DATABASE ("" when neither DATABASE_URL nor SUPABASE_DATABASE_URL is set) ──
DATABASE_URL: str = SETTINGS.database.url_value() or ""

# ── AGENT BEHAVIOUR ─────────────────────────────────────────────────────────────
MAX_AGENT_ITERATIONS:     int = SETTINGS.budgets.max_agent_iterations
FRICTION_SCORE_THRESHOLD: int = SETTINGS.budgets.friction_score_threshold

# ── REALTIME SETTINGS ───────────────────────────────────────────────────────────
REALTIME_WINDOW_MINUTES:    int = SETTINGS.budgets.realtime_window_minutes
REALTIME_AUTO_RUN_INTERVAL: int = SETTINGS.budgets.realtime_auto_run_interval

# ── OBSERVABILITY (LangSmith) ───────────────────────────────────────────────────
LANGCHAIN_TRACING_V2: str = "true" if SETTINGS.observability.langchain_tracing else "false"
LANGCHAIN_API_KEY:    str = _secret(SETTINGS.observability.langchain_api_key)
LANGCHAIN_PROJECT:    str = SETTINGS.observability.langchain_project

# ── JOURNEY DEFINITION ──────────────────────────────────────────────────────────
JOURNEY_NAME: str = SETTINGS.app.journey_name  # default matches data/events.parquet (Spec 03, OD-9b)

JOURNEY_CONFIG: dict = {
    "name":  JOURNEY_NAME,
    "steps": [
        "landing_page",
        "sign_up_form",
        "email_verification",
        "profile_setup",
        "plan_selection",
        "payment_info",
        "confirm_details",
        "onboarding_done",
    ],
}

# ── LOGGING SETUP ───────────────────────────────────────────────────────────────
# Configure once (idempotent guard prevents duplicate handlers)
if not logging.root.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

# Silence noisy third-party loggers
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)
logging.getLogger("langchain_core").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# CJI application logger (import this in other modules)
logger = logging.getLogger("cji")
'''

# ─────────────────────────────── tools/mcp_client.py ──────────────────────────
REWRITES["tools/mcp_client.py"] = '''"""
MCP client helpers. Endpoints, transport and timeouts come from the settings
service registry (Spec 04); callers pass logical service names only.
"""
import contextlib
import json
import logging

from mcp import ClientSession
from mcp.client.sse import sse_client

from settings import ConfigError, get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def server_url(server_name: str) -> str:
    """URL of an MCP service, resolved from the active settings at call time."""
    services = get_settings().services
    endpoint = services.get(server_name)          # ConfigError for unknown names
    if endpoint.kind != "mcp":
        known = ", ".join(e.name for e in services.mcp_services())
        raise ConfigError([f"Service '{server_name}' is not an MCP service. MCP services: {known}."])
    return endpoint.url


def mcp_service_names() -> tuple[str, ...]:
    return tuple(e.name for e in get_settings().services.mcp_services())


# Read-only compatibility view, resolved at import. New code calls server_url().
SERVER_URLS = {e.name: e.url for e in get_settings().services.mcp_services()}


@contextlib.asynccontextmanager
async def mcp_session(server_name: str):
    """
    Context manager to connect to an MCP server via SSE and yield an active ClientSession.
    """
    url = server_url(server_name)
    timeouts = get_settings().mcp
    logger.debug(f"Connecting to MCP server via SSE: {server_name} at {url}")
    async with sse_client(
        url, timeout=timeouts.connect_timeout_s, sse_read_timeout=timeouts.read_timeout_s
    ) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            yield session


async def call_tool(session: ClientSession, tool_name: str, arguments: dict = None) -> dict:
    """
    Helper to execute an MCP tool and parse the returned JSON response.
    Never swallows errors silently; re-raises them for workers to catch.
    """
    if arguments is None:
        arguments = {}

    try:
        logger.debug(f"Calling tool '{tool_name}' with args {arguments}")
        result = await session.call_tool(tool_name, arguments=arguments)

        if result and result.content:
            text = result.content[0].text
            try:
                return json.loads(text)
            except (json.JSONDecodeError, TypeError):
                # Fallback if not JSON
                return {"text": text}
        return {}
    except Exception as e:
        # Re-raise as RuntimeError so worker outer try/except catches it
        logger.error(f"MCP tool '{tool_name}' failed: {type(e).__name__}: {e}")
        raise RuntimeError(f"MCP tool '{tool_name}' failed: {type(e).__name__}: {e}") from e


async def ping_all_servers():
    """Validates all MCP endpoints connect successfully before running graph."""
    for name in mcp_service_names():
        try:
            async with mcp_session(name):
                logger.info(f"Ping successful: {name}")
        except Exception as e:
            logger.error(f"Failed to connect to {name}: {e}")
            raise RuntimeError(f"Startup check failed for {name}. Make sure servers are running.") from e
'''

# ─────────────────────────────── run_servers.py ───────────────────────────────
REWRITES["run_servers.py"] = '''"""
CJI MCP server launcher: starts every MCP service in the settings registry
(Spec 04). Ports and transport come from the registry, not from this file.
"""
import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from settings import ConfigError, get_settings, require

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent.resolve()


def launch_plan() -> list[tuple[str, str]]:
    """(logical name, module) for every MCP service, in registry order."""
    return [(e.name, e.launch) for e in get_settings().services.mcp_services() if e.launch]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CJI MCP Server Launcher")
    parser.add_argument(
        "--mode", choices=["demo", "realtime"], default=None,
        help="Override CJI_MODE for all servers (demo or realtime)."
    )
    args = parser.parse_args(argv)

    # Inject mode override if supplied (before settings are first loaded)
    if args.mode:
        os.environ["CJI_MODE"] = args.mode
        logger.info(f"CJI_MODE overridden to: {args.mode}")
    else:
        logger.info(f"CJI_MODE from env: {os.environ.get('CJI_MODE', 'demo (default)')}")

    try:
        settings = require(get_settings(), "launcher")
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)

    processes = []
    logger.info("Starting MCP servers...")
    try:
        for name, module_name in launch_plan():
            endpoint = settings.services.get(name)
            logger.info(f"Spawning {module_name} ({name} on {endpoint.host}:{endpoint.port}, {endpoint.transport})...")
            p = subprocess.Popen(
                [sys.executable, "-m", module_name],
                cwd=str(ROOT_DIR),
                env=env,
            )
            processes.append((module_name, p))

        logger.info("All servers spawned. Press Ctrl+C to stop.")

        # Wait indefinitely for processes
        for name, p in processes:
            p.wait()

    except KeyboardInterrupt:
        logger.info("\\nShutting down servers...")
    finally:
        for name, p in processes:
            if p.poll() is None:
                logger.info(f"Terminating {name}...")
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        logger.info("Shutdown complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

# ─────────────────────────────── .env.example ─────────────────────────────────
REWRITES[".env.example"] = '''# ─── CJI configuration ──────────────────────────────────────────────────────
# Copy this file to .env and fill in what you need. .env is gitignored — NEVER commit it.
# Process environment variables override .env. .env is never read when CJI_ENV=test.
# Check a configuration:   python -m settings check [--role collector|dashboard|launcher|mcp:<service>]
# Offline demo mode needs nothing below; only the collector needs secrets.

# ── ENVIRONMENT AND MODE ───────────────────────────────────────────────────
# development | test | production. Default: production (fails closed).
CJI_ENV=development
# demo: reads data/events.parquet | realtime: reads PostgreSQL (needs DATABASE_URL)
CJI_MODE=demo
JOURNEY_NAME=user_onboarding

# ── DATABASE (PostgreSQL / Supabase) ───────────────────────────────────────
# Required by the collector, and by realtime mode. No default.
# SUPABASE_DATABASE_URL is used when DATABASE_URL is unset; postgres:// is accepted.
# Percent-encode special characters in the password.
# DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB
# SUPABASE_DATABASE_URL=

# ── STORAGE (defaults: cji_agent/data and cji_agent/reports) ────────────────
# CJI_DATA_DIR=data
# CJI_REPORTS_DIR=reports

# ── SERVICES ───────────────────────────────────────────────────────────────
# Registry defaults: journey-data 8001, friction-engine 8002, insight 8003, report 8004,
# ingestion-intelligence 8005 (MCP over SSE); collector 8000; dashboard 8501; frontend 3000.
# Bind/connect host for local services:
# CJI_SERVICE_HOST=127.0.0.1
# Per service: CJI_<SERVICE>_PORT, or CJI_<SERVICE>_URL for a service running elsewhere.
# <SERVICE> = JOURNEY_DATA, FRICTION_ENGINE, INSIGHT, REPORT, INGESTION_INTELLIGENCE,
#             COLLECTOR, DASHBOARD, FRONTEND
# CJI_REPORT_PORT=8004
# Collector URL used by the CLI and the snippet generator (https in production):
# CJI_COLLECTOR_URL=https://collector.example.com
# COLLECTOR_HOST and COLLECTOR_PORT still work but are deprecated.
# MCP client timeouts (seconds):
# CJI_MCP_CONNECT_TIMEOUT_S=5
# CJI_MCP_READ_TIMEOUT_S=300

# ── LLM PROVIDERS ──────────────────────────────────────────────────────────
# Without keys the pipeline uses rule-based fallback insights (offline demo).
LLM_MODEL=claude-sonnet-4-6
LLM_TEMPERATURE=0.0
LLM_MAX_TOKENS=2048
# GROQ_API_KEY=
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY is accepted but not used by the current code.
# CJI_LLM_TIMEOUT_S=30
# CJI_LLM_RETRY_ATTEMPTS=3
# CJI_LLM_RETRY_MIN_S=2
# CJI_LLM_RETRY_MAX_S=10

# ── BUDGETS AND THRESHOLDS ─────────────────────────────────────────────────
MAX_AGENT_ITERATIONS=20
FRICTION_SCORE_THRESHOLD=60
REALTIME_WINDOW_MINUTES=60
REALTIME_AUTO_RUN_INTERVAL=0
# Dashboard "run analysis" subprocess limit (seconds):
# CJI_PIPELINE_TIMEOUT_S=180
# INGESTION_SAMPLE_ROWS=30
# INGESTION_CONFIDENCE_THRESHOLD=0.80

# ── COLLECTOR SECURITY ─────────────────────────────────────────────────────
# Outside CJI_ENV=development the collector will not start without a random admin key
# of at least 32 characters and an explicit origin list. Generate a key with:
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
# CJI_ADMIN_KEY=
# Browser origins allowed to call the collector: comma-separated, no "*", no trailing slash.
# Leave empty in development to allow the local dashboard and frontend origins.
CJI_CORS_ORIGINS=
# Optional outbound keep-alive ping; off unless set:
# CJI_KEEPALIVE_URL=https://collector.example.com/health
# CJI_KEEPALIVE_INTERVAL_S=300

# ── OBSERVABILITY (LangSmith) ──────────────────────────────────────────────
LANGCHAIN_TRACING_V2=false
# LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=cji-poc
'''

# ─────────────────────────────── MCP server entry points ──────────────────────
for rel, name, old_main in [
    ("mcp_servers/journey_data_server.py", "cji-journey-data",
     'if __name__ == "__main__":\n    mcp.run(transport="sse", port=8001)'),
    ("mcp_servers/friction_engine_server.py", "cji-friction-engine",
     'if __name__ == "__main__":\n    mcp.run(transport="sse", port=8002)'),
    ("mcp_servers/insight_server.py", "cji-insight",
     'if __name__ == "__main__":\n    mcp.run(transport="sse", port=8003)'),
    ("mcp_servers/report_server.py", "cji-report",
     'if __name__ == "__main__":\n    mcp.run(transport="sse", port=8004)'),
    ("mcp_servers/ingestion_intelligence_server.py", "cji-ingestion-intelligence",
     'if __name__ == "__main__":\n    INGESTION_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)\n'
     '    log.info("Starting CJI Smart Ingestion Intelligence MCP Server on port 8005...")\n'
     '    mcp.run(transport="sse", port=8005)'),
]:
    edit(rel, old_main, SERVE.format(name=name).rstrip("\n"))

# journey data: database from settings, only when realtime needs it
JD = "mcp_servers/journey_data_server.py"
edit(JD, "from config import CJI_MODE, DUCKDB_PATH, EVENTS_PARQUET, JOURNEY_CONFIG, DATABASE_URL\n",
     "from config import CJI_MODE, DUCKDB_PATH, EVENTS_PARQUET, JOURNEY_CONFIG\n"
     "from settings import ConfigError, get_settings\n"
     "from settings.roles import database_missing\n")
edit(JD, "    _pg_engine = create_engine(DATABASE_URL, pool_pre_ping=True)\n",
     "    url = get_settings().database.url_value()\n"
     "    if not url:\n"
     '        raise ConfigError([database_missing("CJI_MODE=realtime (cji-journey-data)")],\n'
     '                          role="mcp:cji-journey-data")\n'
     "    _pg_engine = create_engine(url, pool_pre_ping=True)\n")

# insight: Groq key and timeout from settings
INS = "mcp_servers/insight_server.py"
edit(INS, "from config import CHROMA_DIR, LLM_MODEL\n",
     "from config import CHROMA_DIR, LLM_MODEL\nfrom settings import get_settings, secret_value\n")
edit(INS, 'res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=30)',
     'res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload,\n'
     '                        timeout=get_settings().llm.timeout_s)')
edit(INS, '        api_key = os.getenv("GROQ_API_KEY")\n',
     "        api_key = secret_value(get_settings().llm.groq_api_key)\n")
drop_import_if_unused(INS, "import os\n", r"\bos\.")

# report: Groq key from settings; the call gets a timeout (was unbounded)
REP = "mcp_servers/report_server.py"
edit(REP, "from config import REPORTS_DIR, LLM_MODEL\n",
     "from config import REPORTS_DIR, LLM_MODEL\nfrom settings import get_settings, secret_value\n")
edit(REP, '        api_key = os.getenv("GROQ_API_KEY")\n',
     "        api_key = secret_value(get_settings().llm.groq_api_key)\n")
edit(REP, '        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)\n',
     '        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload,\n'
     "                            timeout=get_settings().llm.timeout_s)\n")
drop_import_if_unused(REP, "import os\n", r"\bos\.")

# ingestion: LLM timeout from settings; database only on the realtime write path
ING = "mcp_servers/ingestion_intelligence_server.py"
edit(ING, "    DATABASE_URL,\n    DUCKDB_PATH,\n", "    DUCKDB_PATH,\n")
edit(ING, "from domain.events import ALLOWED_EVENT_TYPES, EVENT_RECORD, EventType, sanitise_url\n",
     "from domain.events import ALLOWED_EVENT_TYPES, EVENT_RECORD, EventType, sanitise_url\n"
     "from settings import ConfigError, get_settings\n"
     "from settings.roles import database_missing\n")
edit(ING, "                timeout=30,\n", "                timeout=get_settings().llm.timeout_s,\n", count=2)
edit(ING, "        engine = create_engine(DATABASE_URL, pool_pre_ping=True)\n",
     "        url = get_settings().database.url_value()\n"
     "        if not url:\n"
     '            raise ConfigError([database_missing("Realtime ingestion")],\n'
     '                              role="mcp:cji-ingestion-intelligence")\n'
     "        engine = create_engine(url, pool_pre_ping=True)\n")
drop_import_if_unused(ING, "    INGESTION_UPLOADS_DIR,\n", r"INGESTION_UPLOADS_DIR")

# ─────────────────────────────── guardrails/rate_limiter.py ───────────────────
RL = "guardrails/rate_limiter.py"
edit(RL, "from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type\n",
     "from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type\n\n"
     "from settings import get_settings\n")
edit(RL, "llm_retry = retry(\n    stop=stop_after_attempt(3),\n    wait=wait_exponential(multiplier=1, min=2, max=10),\n",
     "_POLICY = get_settings().llm.retry   # CJI_LLM_RETRY_ATTEMPTS / _MIN_S / _MAX_S (Spec 04)\n\n"
     "llm_retry = retry(\n    stop=stop_after_attempt(_POLICY.attempts),\n"
     "    wait=wait_exponential(multiplier=1, min=_POLICY.min_wait_s, max=_POLICY.max_wait_s),\n")

# ─────────────────────────────── collector/api.py ─────────────────────────────
COL = "collector/api.py"
edit(COL, '''from config import (
    CJI_ADMIN_KEY,
    CJI_CORS_ORIGINS,
    CJI_ENV,
    DATABASE_URL,
    KNOWN_DEFAULT_ADMIN_KEYS,
    ROOT,
)
''', '''from config import ROOT
from settings import ConfigError, get_settings, secret_value
from settings.model import DEV_TRACKER_KEY, KNOWN_DEFAULT_ADMIN_KEYS, MIN_ADMIN_KEY_LENGTH
from settings.roles import collector_problems, database_missing, endpoint_problems
''')
edit(COL, 'logger = logging.getLogger("collector")\n', '''logger = logging.getLogger("collector")

# ─── SETTINGS (Spec 04; module names kept so tests can patch them) ─────────
_SETTINGS = get_settings()
CJI_ENV: str = _SETTINGS.app.env
CJI_ADMIN_KEY: str = secret_value(_SETTINGS.auth.admin_key)
CJI_CORS_ORIGINS: list[str] = list(_SETTINGS.cors.origins)
''')
edit(COL, "engine = create_engine(DATABASE_URL, pool_pre_ping=True)\n", '''class UnconfiguredDatabase:
    """Engine stand-in when no database URL is configured: fails with a ConfigError on use."""

    def begin(self):
        raise ConfigError([database_missing("The collector")], role="collector", env=CJI_ENV)

    connect = begin

    def dispose(self):
        pass


def _make_engine(url):
    return create_engine(url, pool_pre_ping=True) if url else UnconfiguredDatabase()


engine = _make_engine(_SETTINGS.database.url_value())
''')
edit(COL, "MIN_ADMIN_KEY_LENGTH = 32\n", "")
edit(COL, '''    """Refuse to start with unsafe settings unless CJI_ENV is explicitly 'development'."""
    if (env or "").strip().lower() == "development":
        return
    problems = []
    if not admin_key or not admin_key_usable(admin_key) or len(admin_key) < MIN_ADMIN_KEY_LENGTH:
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
        )
''', '''    """Refuse to start with unsafe settings unless CJI_ENV is explicitly 'development'."""
    problems = collector_problems(env, admin_key, origins)
    if problems:
        raise ConfigError(problems, role="collector", env=env or "unset")
''')
edit(COL, '''                VALUES ('cji_dev_localtest', 'onboarding', 'Local Development')
                ON CONFLICT (api_key) DO NOTHING
            """))
''', '''                VALUES (:api_key, 'onboarding', 'Local Development')
                ON CONFLICT (api_key) DO NOTHING
            """), {"api_key": DEV_TRACKER_KEY})
''')
edit(COL, '''def _ping_render():
    try:
        url = "https://tcs-cjipip-install-r-cji-agent.onrender.com/health"
        res = requests.get(url, timeout=5)
        logger.info(f"Keep-alive ping sent, status: {res.status_code}")
    except Exception as e:
        logger.error(f"Keep-alive ping failed: {e}")

async def keep_alive():
    await asyncio.sleep(60) # Wait 1 minute after startup
    while True:
        try:
            await asyncio.to_thread(_ping_render)
        except Exception:
            pass
        await asyncio.sleep(300) # Ping every 5 minutes
''', '''def _ping_keepalive(url: str):
    try:
        res = requests.get(url, timeout=5)
        logger.info(f"Keep-alive ping sent, status: {res.status_code}")
    except Exception as e:
        logger.error(f"Keep-alive ping failed: {e}")

async def keep_alive(url: str, interval_s: float):
    """Optional outbound ping, only when CJI_KEEPALIVE_URL is set (Spec 04, OD-27)."""
    await asyncio.sleep(60) # Wait 1 minute after startup
    while True:
        try:
            await asyncio.to_thread(_ping_keepalive, url)
        except Exception:
            pass
        await asyncio.sleep(interval_s)
''')
edit(COL, '''    # Fail closed before touching the database (R-03).
    validate_collector_settings(CJI_ENV, CJI_ADMIN_KEY, CJI_CORS_ORIGINS)
    logger.info("Connecting to Database...")
    _create_tables()
    asyncio.create_task(keep_alive())
''', '''    # Fail closed before touching the database (R-03); report every problem at once (Spec 04).
    problems = collector_problems(CJI_ENV, CJI_ADMIN_KEY, CJI_CORS_ORIGINS)
    if isinstance(engine, UnconfiguredDatabase):
        problems.append(database_missing("The collector"))
    problems += endpoint_problems(_SETTINGS)
    if problems:
        raise ConfigError(problems, role="collector", env=CJI_ENV)
    logger.info("Connecting to Database...")
    _create_tables()
    if _SETTINGS.keepalive.url:
        asyncio.create_task(keep_alive(_SETTINGS.keepalive.url, _SETTINGS.keepalive.interval_s))
''')

# ─────────────────────────────── main.py ──────────────────────────────────────
MAIN = "main.py"
edit(MAIN, '''    # Now safe to import project modules
    from config import (
        CJI_MODE,
        CHECKPOINTS_DB,
        COLLECTOR_URL,
        EVENTS_PARQUET,
        JOURNEY_CONFIG,
        MAX_AGENT_ITERATIONS,
        FRICTION_SCORE_THRESHOLD,
        logger,
    )
''', '''    # Now safe to import project modules. Configuration is validated once, here (Spec 04).
    from settings import ConfigError

    try:
        from config import (
            CJI_MODE,
            CHECKPOINTS_DB,
            EVENTS_PARQUET,
            JOURNEY_CONFIG,
            FRICTION_SCORE_THRESHOLD,
            logger,
        )
        from settings import get_settings, require

        settings = require(get_settings(), "cli")
    except ConfigError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
''')
edit(MAIN, '"recursion_limit": MAX_AGENT_ITERATIONS * 3,  # LangGraph hard limit',
     '"recursion_limit": settings.budgets.recursion_limit,  # LangGraph hard limit')
edit(MAIN, '"recursion_limit": MAX_AGENT_ITERATIONS * 3,\n', '"recursion_limit": settings.budgets.recursion_limit,\n')
edit(MAIN, '"collector_url":        COLLECTOR_URL,', '"collector_url":        settings.services.get("collector").url,')

# ─────────────────────────────── dashboard.py ─────────────────────────────────
DASH = "dashboard.py"
edit(DASH, '''from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()
DB_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DATABASE_URL")
if DB_URL and DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

try:
    engine = create_engine(DB_URL, pool_pre_ping=True)
except Exception:
    engine = None
# ── Project paths ──────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent
DATA_DIR     = ROOT / "data"
REPORTS_DIR  = ROOT / "reports"
LAST_RUN_FILE = DATA_DIR / "last_run.json"
PARQUET_PATH  = DATA_DIR / "events.parquet"
VENV_PY       = ROOT / ".venv" / "Scripts" / "python.exe"
''', '''from sqlalchemy import create_engine

from settings import ConfigError, get_settings, require
''')
edit(DASH, '''    initial_sidebar_state="expanded",
)
''', '''    initial_sidebar_state="expanded",
)

# ── Configuration (Spec 04): validated once; shown in the page on error ────────
try:
    SETTINGS = require(get_settings(), "dashboard")
except ConfigError as exc:
    st.error(f"Configuration error\\n\\n```\\n{exc}\\n```")
    st.stop()

# DATABASE_URL, or SUPABASE_DATABASE_URL when DATABASE_URL is unset
DB_URL = SETTINGS.database.url_value()
try:
    engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None
except Exception:
    engine = None

# ── Project paths ──────────────────────────────────────────────────────────────
ROOT          = Path(__file__).parent
DATA_DIR      = SETTINGS.storage.data_dir
REPORTS_DIR   = SETTINGS.storage.reports_dir
LAST_RUN_FILE = SETTINGS.storage.last_run_file
PARQUET_PATH  = SETTINGS.storage.events_parquet
''')
edit(DASH, '''    mode = os.environ.get("CJI_MODE", "demo").lower().strip()
    result = subprocess.run(
        [str(VENV_PY), str(ROOT / "main.py"), "--mode", mode, "--run", "--auto-approve"],
        capture_output=True, text=True, timeout=180, cwd=str(ROOT),
''', '''    mode = SETTINGS.app.mode
    result = subprocess.run(
        [sys.executable, str(ROOT / "main.py"), "--mode", mode, "--run", "--auto-approve"],
        capture_output=True, text=True, timeout=SETTINGS.budgets.pipeline_timeout_s, cwd=str(ROOT),
''')
edit(DASH, 'st.error("Pipeline timed out after 3 minutes.")',
     'st.error(f"Pipeline timed out after {SETTINGS.budgets.pipeline_timeout_s:g} s.")')
drop_import_if_unused(DASH, "import os\n", r"\bos\.")

# ─────────────────────────────── tools/* ──────────────────────────────────────
SD = "tools/synthetic_data.py"
edit(SD, "from config import EVENTS_PARQUET, JOURNEY_CONFIG, DATABASE_URL, logger\n",
     "from config import EVENTS_PARQUET, JOURNEY_CONFIG, logger\nfrom settings import get_settings\n")
edit(SD, '''    # Upload to Supabase/PostgreSQL
    try:
        engine = create_engine(DATABASE_URL)
        df_sql = df.copy()
        # sqlalchemy works better when json/dict are just uploaded
        df_sql.to_sql(name="demo_events", con=engine, if_exists="replace", index=False)
        logger.info(f"[synthetic_data] Uploaded {len(df):,} events to Supabase 'demo_events' table.")
    except Exception as e:
        logger.error(f"[synthetic_data] Failed to upload to Supabase: {e}")
''', '''    # Upload to Supabase/PostgreSQL only when a database is configured, and never
    # in the test environment (Spec 04): this replaces the demo_events table.
    settings = get_settings()
    db_url = settings.database.url_value()
    if settings.app.env == "test":
        logger.info("[synthetic_data] CJI_ENV=test: PostgreSQL upload skipped.")
    elif not db_url:
        logger.info("[synthetic_data] DATABASE_URL / SUPABASE_DATABASE_URL not set: PostgreSQL upload skipped.")
    else:
        try:
            engine = create_engine(db_url)
            df_sql = df.copy()
            # sqlalchemy works better when json/dict are just uploaded
            df_sql.to_sql(name="demo_events", con=engine, if_exists="replace", index=False)
            logger.info(f"[synthetic_data] Uploaded {len(df):,} events to Supabase 'demo_events' table.")
        except Exception as e:
            logger.error(f"[synthetic_data] Failed to upload to Supabase: {e}")
''')

IJ = "tools/ingest_json.py"
edit(IJ, "from config import EVENTS_PARQUET, JOURNEY_CONFIG, logger, DATABASE_URL\n",
     "from config import EVENTS_PARQUET, JOURNEY_CONFIG, logger\n"
     "from settings import ConfigError, get_settings\n"
     "from settings.roles import database_missing\n")
edit(IJ, "    engine = create_engine(DATABASE_URL)\n",
     "    db_url = get_settings().database.url_value()\n"
     "    if not db_url:\n"
     '        raise ConfigError([database_missing("Writing ingested events to tracking_events")])\n'
     "    engine = create_engine(db_url)\n")

SG = "tracker/snippet_generator.py"
edit(SG, "import secrets\nfrom pathlib import Path\n\nfrom cji_agent.config import ROOT\n",
     "import secrets\nimport sys\nfrom pathlib import Path\n\n"
     "sys.path.insert(0, str(Path(__file__).resolve().parent.parent))\n"
     "from config import ROOT  # noqa: E402\n"
     "from settings import get_settings  # noqa: E402\n")
edit(SG, 'parser.add_argument("--host", default="http://localhost:8000", help="Collector host URL")',
     'parser.add_argument("--host", default=get_settings().services.get("collector").url,\n'
     '                        help="Collector URL (default: CJI_COLLECTOR_URL or the service registry)")')

# ─────────────────────────────── tests/conftest.py ────────────────────────────
CF = "tests/conftest.py"
edit(CF, '"""\nShared pytest fixtures for CJI project.\n"""\nimport pytest\n',
     '"""\nShared pytest fixtures for CJI project.\n"""\nimport os\n\n'
     "# Spec 04: tests run in the test environment (no .env, no PostgreSQL uploads).\n"
     'os.environ.setdefault("CJI_ENV", "test")\n\n'
     "import pytest  # noqa: E402\n")
edit(CF, "from pathlib import Path\nimport pandas as pd\nimport sys\n",
     "from pathlib import Path  # noqa: E402\nimport pandas as pd  # noqa: E402\nimport sys  # noqa: E402\n")
edit(CF, "from tools.synthetic_data import generate_demo_data\n",
     "from tools.synthetic_data import generate_demo_data  # noqa: E402\n")
edit(CF, '''    generate_demo_data(n_sessions=500, seed=42, output_path=path)
    return pd.read_parquet(path)
''', '''    generate_demo_data(n_sessions=500, seed=42, output_path=path)
    return pd.read_parquet(path)


# ── Settings (Spec 04) ────────────────────────────────────────────────────────

@pytest.fixture
def cji_settings(tmp_path: Path):
    """Test settings with storage under tmp_path, active for the duration of the test."""
    from settings import make_test_settings, override_settings

    with override_settings(make_test_settings(tmp_path)) as settings:
        yield settings
''')


def main() -> int:
    planned: dict[pathlib.Path, tuple[str, str]] = {}
    problems: list[str] = []
    for rel, new_text in REWRITES.items():
        path = APP / rel
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        planned[path] = (raw, new_text.replace("\n", nl))
    for rel, pairs in EDITS.items():
        path = APP / rel
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw
        for old, new, count in pairs:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            found = text.count(o)
            if found != count:
                problems.append(f"{rel}: anchor found {found}x (want {count}): {old[:80]!r}")
                continue
            text = text.replace(o, n)
        for import_line, usage in POST.get(rel, []):
            line = import_line.replace("\n", nl)
            rest = text.replace(line, "", 1)
            if text.count(line) == 1 and not re.search(usage, rest):
                text = rest
        planned[path] = (raw, text)
    main_text = planned[APP / MAIN][1]
    if "MAX_AGENT_ITERATIONS" in main_text or "COLLECTOR_URL" in main_text:
        problems.append("main.py still references MAX_AGENT_ITERATIONS or COLLECTOR_URL")
    if problems:
        print("NOT APPLIED:\n" + "\n".join(problems))
        return 1
    for path, (old, new) in planned.items():
        if old != new:
            path.write_bytes(new.encode("utf-8"))
            print(f"patched {path.relative_to(APP)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
