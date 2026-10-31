"""
Shared pytest fixtures for CJI project.
"""
import os

# Spec 04: tests run in the test environment (no .env, no PostgreSQL uploads).
os.environ.setdefault("CJI_ENV", "test")
# Spec 09: workflow step retries do not wait in tests (the attempt count is unchanged).
os.environ.setdefault("CJI_WORKFLOW_RETRY_BACKOFF_S", "0")
# Spec 11: the runtime home (data/, reports/) is cji_agent/, wherever pytest is started from.
os.environ.setdefault("CJI_HOME", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sys
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
import pytest

from cji.tools.synthetic_data import generate_demo_data

# ── Friction Engine Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def low_step() -> dict:
    """Low-friction step — landing page characteristics. Score should be < 60."""
    return {
        "step_id":           "landing_page",
        "unique_users":      2000,
        "abandon_rate_pct":  15.0,
        "error_rate_pct":    2.1,
        "avg_dwell_ms":      12000,
        "avg_retries":       0.01,
        "avg_rage_clicks":   0.02,
    }


@pytest.fixture
def high_step() -> dict:
    """High-friction step — email verification characteristics. Score should be >= 60."""
    return {
        "step_id":           "email_verification",
        "unique_users":      732,
        "abandon_rate_pct":  41.8,
        "error_rate_pct":    34.7,
        "avg_dwell_ms":      184000,
        "avg_retries":       1.8,
        "avg_rage_clicks":   0.62,
    }


@pytest.fixture
def zero_step() -> dict:
    """All-zero inputs — minimum possible score edge case."""
    return {
        "step_id":           "zero_step",
        "unique_users":      0,
        "abandon_rate_pct":  0.0,
        "error_rate_pct":    0.0,
        "avg_dwell_ms":      0,
        "avg_retries":       0.0,
        "avg_rage_clicks":   0.0,
    }


@pytest.fixture
def baseline_step() -> dict:
    """All metrics exactly at their baselines — partial scores verify math."""
    from cji.mcp_servers.friction_engine_server import BASELINES
    return {
        "step_id":          "baseline_step",
        "abandon_rate_pct": BASELINES.get("abandon_rate_pct", 10.0),
        "error_rate_pct":   BASELINES.get("error_rate_pct", 5.0),
        "avg_dwell_ms":     BASELINES.get("avg_dwell_ms", 15000.0),
        "avg_retries":      BASELINES.get("avg_retries", 0.1),
        "avg_rage_clicks":  BASELINES.get("avg_rage_clicks", 0.05),
    }


# ── Collector Models Fixtures ────────────────────────────────────────────────

@pytest.fixture
def valid_event_data_dict() -> dict:
    """Factory for a minimal valid TrackerEvent dict."""
    return {
        "event_id":    "event-12345678-abcdef",
        "user_id":     "user-12345678-abcdef",
        "session_id":  "sess-12345678-abcdef",
        "journey_id":  "onboarding",
        "step_id":     "email_verification",
        "event_type":  "page_view",
        "timestamp":   "2026-03-15T14:30:00Z",
        "duration_ms": 0,
        "url":         "https://example.com/verify",
        "metadata":    {},
    }


# ── Synthetic Data Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def parquet_path(tmp_path: Path) -> Path:
    """Temporary directory Parquet path — cleaned up automatically."""
    return tmp_path / "test_events.parquet"


@pytest.fixture
def small_df(parquet_path: Path) -> pd.DataFrame:
    """Small dataset (50 sessions) for fast tests."""
    generate_demo_data(n_sessions=50, seed=42, output_path=parquet_path)
    return pd.read_parquet(parquet_path)


@pytest.fixture
def medium_df(tmp_path: Path) -> pd.DataFrame:
    """Medium dataset (500 sessions) for statistical tests."""
    path = tmp_path / "medium.parquet"
    generate_demo_data(n_sessions=500, seed=42, output_path=path)
    return pd.read_parquet(path)


# ── Settings (Spec 04) ────────────────────────────────────────────────────────

@pytest.fixture
def cji_settings(tmp_path: Path):
    """Test settings with storage under tmp_path, active for the duration of the test."""
    from cji.settings import make_test_settings, override_settings

    with override_settings(make_test_settings(tmp_path)) as settings:
        yield settings


# ── PostgreSQL test server (Spec 05; shared since Spec 07, OD-51) ─────────────
# A throwaway local server only: pgserver on a temporary directory, or
# CJI_TEST_DATABASE_URL pointing at a loopback server. Never DATABASE_URL / Supabase.

def _loopback_only(url):
    parts = urlsplit(url)
    host = parts.hostname or ""
    if host not in ("127.0.0.1", "localhost", "::1"):
        pytest.fail(f"CJI_TEST_DATABASE_URL must point at a local throwaway server, not {host!r}")
    return url


@pytest.fixture(scope="session")
def pg_url(tmp_path_factory):
    explicit = os.environ.get("CJI_TEST_DATABASE_URL")
    if explicit:
        yield _loopback_only(explicit)
        return
    try:
        import pgserver
    except ImportError:
        pytest.skip("PostgreSQL tests need pgserver (pip install pgserver) or CJI_TEST_DATABASE_URL")
    server = pgserver.get_server(str(tmp_path_factory.mktemp("pgdata")), cleanup_mode="stop")
    try:
        yield server.get_uri()
    finally:
        server.cleanup()


@pytest.fixture
def fresh_db_url(pg_url):
    """Factory for new empty databases on the test server (Spec 15); all are dropped after the test."""
    import uuid
    from urllib.parse import urlunsplit

    from sqlalchemy import create_engine, text

    admin = create_engine(pg_url, isolation_level="AUTOCOMMIT")
    made = []

    def make():
        name = "t15_" + uuid.uuid4().hex[:12]
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        made.append(name)
        parts = urlsplit(pg_url)
        return urlunsplit((parts.scheme, parts.netloc, "/" + name, parts.query, parts.fragment))

    yield make
    from cji.migrations import runner

    for url, engine in list(runner._engines.items()):
        if any(url.split("?")[0].endswith("/" + n) for n in made):
            engine.dispose()
            runner._engines.pop(url, None)
    with admin.connect() as conn:
        for name in made:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture
def pg_bin():
    """Directory of pg_dump/pg_restore from pgserver (Spec 15 backup tests)."""
    try:
        import pgserver
    except ImportError:
        pytest.skip("backup tests need pgserver's PostgreSQL client tools")
    return str(Path(pgserver.__file__).parent / "pginstall" / "bin")


# ── Collector rate limits (Spec 07) ───────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fresh_collector_rate_limits():
    """The collector keeps in-process rate-limit buckets; every test starts with empty ones."""
    api = sys.modules.get("cji.collector.api")
    if api is not None and hasattr(api, "reset_rate_limits"):
        api.reset_rate_limits()
    yield


# ── AI gateway (Spec 08) ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_real_llm_calls(monkeypatch):
    """No test may reach an LLM provider: unscripted requests fail. Each test gets a fresh ToolGateway."""
    from cji.integrations import llm as llm_module
    from cji.integrations import tools as tools_module
    from cji.integrations.testing import BlockingTransport

    monkeypatch.setattr(llm_module, "DEFAULT_TRANSPORT", BlockingTransport())
    tools_module.reset_tool_gateway()
    yield
    tools_module.reset_tool_gateway()



def pytest_addoption(parser):
    """Spec 10: `pytest --update-report-snapshots` rewrites tests/snapshots/report_*.html."""
    parser.addoption("--update-report-snapshots", action="store_true", default=False,
                     help="rewrite the report snapshot files instead of comparing them")
