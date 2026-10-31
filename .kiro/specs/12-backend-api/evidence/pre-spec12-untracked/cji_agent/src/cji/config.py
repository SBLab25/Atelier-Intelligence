"""
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
  - Paths are relative to the runtime home: CJI_HOME, else the working directory
    (Spec 11, OD-99). ROOT is that home.
  - Never configures logging; entry points call cji.logs.configure_logging().
  - Never import config.py from state.py, domain/ or settings/.
"""
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from cji.settings import get_settings, resolve_home
from cji.settings.model import KNOWN_DEFAULT_ADMIN_KEYS as _KNOWN_DEFAULT_ADMIN_KEYS
from cji.settings.model import secret_value as _secret

if os.getenv("CJI_ENV", "").strip().lower() != "test":
    load_dotenv(resolve_home() / ".env")

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
ROOT:           Path = SETTINGS.storage.home   # runtime home (CJI_HOME or the working directory)
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

# ── LOGGING ─────────────────────────────────────────────────────────────────────
# Handlers are added by entry points (cji.logs.configure_logging), not on import (Spec 11, OD-105).

# CJI application logger (import this in other modules)
logger = logging.getLogger("cji")
