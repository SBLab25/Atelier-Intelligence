"""
Tests for MCP Server 0 — Smart Ingestion Intelligence.

Follows existing CJI testing principles:
  1. All tests run offline (no LLM API key required for unit tests).
  2. LLM-dependent tests marked @pytest.mark.integration.
  3. Friction Engine equivalent for ingestion: mapping logic is testable without LLM.
"""

import asyncio
import tempfile
import uuid

import pandas as pd
import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ga4_df():
    """A small GA4-shaped DataFrame for testing."""
    return pd.DataFrame([
        {
            "event_name":             "page_view",
            "page_location":          "https://app.example.com/onboarding?token=abc",
            "ga_session_id":          "sess_001",
            "user_pseudo_id":         str(uuid.uuid4()),
            "event_timestamp":        1_700_000_000_000_000,  # Unix microseconds
            "engagement_time_msec":   3500,
        }
        for _ in range(20)
    ])


@pytest.fixture
def sample_mapping_config():
    """A pre-built mapping config (bypasses LLM for unit tests)."""
    return {
        "detected_source":    "GA4 Clickstream Export",
        "confidence":         0.94,
        "column_fingerprint": "abc123",
        "field_mapping": {
            "event_name":          "event_type",
            "page_location":       "url",
            "ga_session_id":       "session_id",
            "user_pseudo_id":      "user_id",
            "event_timestamp":     "timestamp",
            "engagement_time_msec":"duration_ms",
        },
        "derived_fields": {
            "journey_id": "hardcode as 'imported_journey'",
            "step_id":    "derive from url path",
            "event_id":   "generate UUID",
        },
        "missing_fields": [],
        "transformation_notes": ["event_timestamp is Unix microseconds — divide by 1000000"],
        "warnings":             [],
    }


# ── Unit Tests: Column Fingerprint ────────────────────────────────────────────

def test_column_fingerprint_is_deterministic():
    from cji.mcp_servers.ingestion_intelligence_server import _column_fingerprint
    cols = ["event_name", "page_location", "ga_session_id"]
    assert _column_fingerprint(cols) == _column_fingerprint(cols[::-1])


def test_column_fingerprint_differs_for_different_columns():
    from cji.mcp_servers.ingestion_intelligence_server import _column_fingerprint
    assert _column_fingerprint(["a", "b"]) != _column_fingerprint(["a", "c"])


# ── Unit Tests: PII Sanitisation ──────────────────────────────────────────────

def test_sanitise_url_removes_query_params():
    from cji.mcp_servers.ingestion_intelligence_server import _sanitise_url
    assert _sanitise_url("https://app.example.com/login?token=secret&ref=email") \
           == "https://app.example.com/login"


def test_sanitise_url_preserves_path():
    from cji.mcp_servers.ingestion_intelligence_server import _sanitise_url
    assert "/onboarding/step1" in _sanitise_url("https://app.example.com/onboarding/step1")


def test_sanitise_user_id_anonymises_email():
    from cji.mcp_servers.ingestion_intelligence_server import _sanitise_user_id
    result = _sanitise_user_id("user@example.com")
    assert "@" not in result
    assert len(result) == 36  # UUID format


def test_sanitise_user_id_preserves_uuid():
    from cji.mcp_servers.ingestion_intelligence_server import _sanitise_user_id
    uid = str(uuid.uuid4())
    assert _sanitise_user_id(uid) == uid


# ── Unit Tests: File Loader ────────────────────────────────────────────────────

def test_load_csv_file(sample_ga4_df):
    from cji.mcp_servers.ingestion_intelligence_server import _load_file
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        sample_ga4_df.to_csv(f.name, index=False)
        df = _load_file(f.name)
    assert len(df) == len(sample_ga4_df)
    assert "event_name" in df.columns


def test_load_json_file(sample_ga4_df):
    from cji.mcp_servers.ingestion_intelligence_server import _load_file
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        sample_ga4_df.to_json(f.name, orient="records")
        df = _load_file(f.name)
    assert len(df) == len(sample_ga4_df)


def test_unsupported_format_raises():
    from cji.mcp_servers.ingestion_intelligence_server import _load_file
    with pytest.raises(ValueError, match="Unsupported file format"):
        _load_file("/tmp/data.txt")


# ── Unit Tests: Pydantic Validation Model ─────────────────────────────────────

def test_canonical_event_coerces_invalid_event_type():
    from cji.mcp_servers.ingestion_intelligence_server import CanonicalEvent
    evt = CanonicalEvent(
        event_id="id1", user_id="u1", session_id="s1",
        journey_id="onboarding", step_id="login",
        event_type="custom_unknown_type",
        timestamp="2026-04-22T00:00:00Z",
    )
    assert evt.event_type == "page_view"


def test_canonical_event_coerces_invalid_metadata():
    from cji.mcp_servers.ingestion_intelligence_server import CanonicalEvent
    evt = CanonicalEvent(
        event_id="id1", user_id="u1", session_id="s1",
        journey_id="onboarding", step_id="login",
        event_type="page_view", timestamp="2026-04-22T00:00:00Z",
        metadata="not valid json {{{",
    )
    assert evt.metadata == "{}"


# ── Unit Tests: apply_mapping (offline — no LLM) ─────────────────────────────

def test_apply_mapping_produces_canonical_records(sample_ga4_df, sample_mapping_config, tmp_path):
    from cji.mcp_servers.ingestion_intelligence_server import apply_mapping
    csv_path = str(tmp_path / "ga4.csv")
    sample_ga4_df.to_csv(csv_path, index=False)

    result = apply_mapping(csv_path, sample_mapping_config)

    assert result["records_passed"] > 0
    assert result["ready_to_ingest"] is True
    assert "event_id" in result["sample_output"][0]
    assert "journey_id" in result["sample_output"][0]


def test_apply_mapping_generates_missing_event_id(sample_ga4_df, sample_mapping_config, tmp_path):
    from cji.mcp_servers.ingestion_intelligence_server import apply_mapping
    csv_path = str(tmp_path / "ga4.csv")
    sample_ga4_df.to_csv(csv_path, index=False)

    result = apply_mapping(csv_path, sample_mapping_config)
    for rec in result["sample_output"]:
        assert len(rec["event_id"]) == 36  # valid UUID


def test_apply_mapping_sanitises_urls(sample_ga4_df, sample_mapping_config, tmp_path):
    from cji.mcp_servers.ingestion_intelligence_server import apply_mapping
    csv_path = str(tmp_path / "ga4.csv")
    sample_ga4_df.to_csv(csv_path, index=False)

    result = apply_mapping(csv_path, sample_mapping_config)
    for rec in result["sample_output"]:
        assert "?" not in rec.get("url", "")


# ── Integration Tests (require API key) ───────────────────────────────────────

@pytest.mark.integration
def test_detect_schema_calls_llm_for_unknown_source(sample_ga4_df, tmp_path):
    from cji.mcp_servers.ingestion_intelligence_server import detect_schema
    csv_path = str(tmp_path / "ga4_unknown.csv")
    sample_ga4_df.to_csv(csv_path, index=False)

    result = asyncio.run(detect_schema(csv_path, source_hint="GA4 export"))
    assert result["confidence"] > 0.5
    assert "field_mapping" in result
    assert result["cached"] is False


@pytest.mark.integration
def test_detect_schema_uses_cache_on_second_call(sample_ga4_df, tmp_path):
    from cji.mcp_servers.ingestion_intelligence_server import detect_schema
    csv_path = str(tmp_path / "ga4_cache.csv")
    sample_ga4_df.to_csv(csv_path, index=False)

    asyncio.run(detect_schema(csv_path))          # first call fills the mapping cache
    second = asyncio.run(detect_schema(csv_path))

    assert second["cached"] is True