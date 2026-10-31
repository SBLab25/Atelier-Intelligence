"""
Shared pytest fixtures for CJI project.
"""
import os

# Spec 04: tests run in the test environment (no .env, no PostgreSQL uploads).
os.environ.setdefault("CJI_ENV", "test")

import sys
from pathlib import Path

import pandas as pd
import pytest

# Allow running from both cji_agent/ and cji_agent/tests/ (until Spec 11 (R-14) packaging)
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.synthetic_data import generate_demo_data

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
    from mcp_servers.friction_engine_server import BASELINES
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
    from settings import make_test_settings, override_settings

    with override_settings(make_test_settings(tmp_path)) as settings:
        yield settings
