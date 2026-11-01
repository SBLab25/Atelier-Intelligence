"""
Unit Tests: Collector Models (Pydantic v2)
==========================================
Tests validation logic in collector/models.py.
Zero network, zero database, zero LLM — pure Pydantic validation.

Run:
  pytest tests/test_collector_models.py -v
"""

import pytest
from pydantic import ValidationError

from cji.collector.models import (
    ALLOWED_EVENT_TYPES,
    CollectResult,
    EventBatch,
    EventError,
    HealthStatus,
    TrackerEvent,
)

# ── Helpers ───────────────────────────────────────────────────────────────────

# ── Fixtures (Shared fixtures now in conftest.py)


# ── TrackerEvent: Happy Path ───────────────────────────────────────────────────

def test_valid_event_passes(valid_event_data_dict):
    """A fully valid TrackerEvent is accepted without error."""
    e = TrackerEvent(**valid_event_data_dict.copy())
    assert e.step_id == "email_verification"
    assert e.event_type == "page_view"
    assert isinstance(e.metadata, dict)


def test_all_allowed_event_types_accepted(valid_event_data_dict):
    """Every value in ALLOWED_EVENT_TYPES is accepted as event_type."""
    data = valid_event_data_dict.copy()
    for etype in ALLOWED_EVENT_TYPES:
        data["event_type"] = etype
        e = TrackerEvent(**data)
        assert e.event_type == etype


def test_allowed_event_types_set_not_empty(valid_event_data_dict):
    """ALLOWED_EVENT_TYPES is a non-empty frozenset."""
    assert isinstance(ALLOWED_EVENT_TYPES, frozenset)
    assert len(ALLOWED_EVENT_TYPES) > 0
    assert "page_view" in ALLOWED_EVENT_TYPES
    assert "abandon" in ALLOWED_EVENT_TYPES
    assert "rage_click" in ALLOWED_EVENT_TYPES


def test_metadata_dict_accepted(valid_event_data_dict):
    """Metadata as a dict is accepted directly."""
    data = valid_event_data_dict.copy()
    data["metadata"] = {"key": "value", "count": 3}
    e = TrackerEvent(**data)
    assert e.metadata == {"key": "value", "count": 3}


def test_duration_ms_zero_allowed(valid_event_data_dict):
    """duration_ms of 0 is valid."""
    data = valid_event_data_dict.copy()
    data["duration_ms"] = 0
    e = TrackerEvent(**data)
    assert e.duration_ms == 0


def test_duration_ms_large_value_allowed(valid_event_data_dict):
    """Large duration_ms values (multi-hour sessions) are valid."""
    data = valid_event_data_dict.copy()
    data["duration_ms"] = 3600000  # 1 hour
    e = TrackerEvent(**data)
    assert e.duration_ms == 3600000


def test_extra_fields_ignored(valid_event_data_dict):
    """Unknown fields from tracker.js are silently dropped."""
    data = valid_event_data_dict.copy()
    data["unknown_field"] = "should be ignored"
    data["another_unknown"] = 123
    e = TrackerEvent(**data)
    assert not hasattr(e, "unknown_field")


# ── TrackerEvent: Rejection Tests ─────────────────────────────────────────────

def test_invalid_event_type_rejected(valid_event_data_dict):
    """Unknown event_type raises ValidationError."""
    data = valid_event_data_dict.copy()
    data["event_type"] = "INVALID_TYPE"
    with pytest.raises(ValidationError) as exc_info:
        TrackerEvent(**data)
    assert "event_type" in str(exc_info.value)


def test_event_type_case_sensitive(valid_event_data_dict):
    """event_type is case-sensitive: 'PAGE_VIEW' is not 'page_view'."""
    data = valid_event_data_dict.copy()
    data["event_type"] = "PAGE_VIEW"
    with pytest.raises(ValidationError):
        TrackerEvent(**data)


def test_negative_duration_ms_rejected(valid_event_data_dict):
    """Negative duration_ms raises ValidationError."""
    data = valid_event_data_dict.copy()
    data["duration_ms"] = -100
    with pytest.raises(ValidationError):
        TrackerEvent(**data)


def test_short_event_id_rejected(valid_event_data_dict):
    """event_id shorter than 8 characters raises ValidationError."""
    data = valid_event_data_dict.copy()
    data["event_id"] = "short"  # 5 chars
    with pytest.raises(ValidationError):
        TrackerEvent(**data)


def test_exactly_8_char_event_id_accepted(valid_event_data_dict):
    """event_id of exactly 8 characters is accepted."""
    data = valid_event_data_dict.copy()
    data["event_id"] = "12345678"  # exactly 8 chars
    e = TrackerEvent(**data)
    assert e.event_id == "12345678"


def test_empty_event_type_rejected(valid_event_data_dict):
    """Empty string event_type raises ValidationError."""
    data = valid_event_data_dict.copy()
    data["event_type"] = ""
    with pytest.raises(ValidationError):
        TrackerEvent(**data)


# ── TrackerEvent: URL Sanitisation ────────────────────────────────────────────

def test_url_query_param_stripped(valid_event_data_dict):
    """Query parameters are removed from URL."""
    data = valid_event_data_dict.copy()
    data["url"] = "https://example.com/verify?token=secret&email=user@test.com"
    e = TrackerEvent(**data)
    assert "?" not in e.url
    assert "secret" not in e.url
    assert "email" not in e.url
    assert e.url == "https://example.com/verify"


def test_url_fragment_stripped(valid_event_data_dict):
    """Fragment (#) is removed from URL."""
    data = valid_event_data_dict.copy()
    data["url"] = "https://example.com/page#section-heading"
    e = TrackerEvent(**data)
    assert "#" not in e.url
    assert "section-heading" not in e.url
    assert e.url == "https://example.com/page"


def test_url_query_and_fragment_both_stripped(valid_event_data_dict):
    """Both query string and fragment are removed."""
    data = valid_event_data_dict.copy()
    data["url"] = "https://example.com/path?key=val#anchor"
    e = TrackerEvent(**data)
    assert "?" not in e.url
    assert "#" not in e.url
    assert "key" not in e.url
    assert "anchor" not in e.url


def test_clean_url_unchanged(valid_event_data_dict):
    """URL without query or fragment passes through unchanged."""
    data = valid_event_data_dict.copy()
    data["url"] = "https://example.com/verify"
    e = TrackerEvent(**data)
    assert e.url == "https://example.com/verify"


def test_empty_url_accepted(valid_event_data_dict):
    """Empty URL string is valid (optional field)."""
    data = valid_event_data_dict.copy()
    data["url"] = ""
    e = TrackerEvent(**data)
    assert e.url == ""


# ── TrackerEvent: Metadata Coercion ───────────────────────────────────────────

def test_metadata_json_string_coerced_to_dict(valid_event_data_dict):
    """Valid JSON string in metadata is parsed into a dict."""
    data = valid_event_data_dict.copy()
    data["metadata"] = '{"error_code": "TOKEN_EXPIRED", "retry_count": 2}'
    e = TrackerEvent(**data)
    assert isinstance(e.metadata, dict)
    assert e.metadata["error_code"] == "TOKEN_EXPIRED"
    assert e.metadata["retry_count"] == 2


def test_metadata_invalid_json_string_returns_empty_dict(valid_event_data_dict):
    """Invalid JSON string in metadata returns empty dict (no error)."""
    data = valid_event_data_dict.copy()
    data["metadata"] = "not valid json {"
    e = TrackerEvent(**data)
    assert e.metadata == {}


def test_metadata_none_returns_empty_dict(valid_event_data_dict):
    """None metadata returns empty dict (no crash)."""
    data = valid_event_data_dict.copy()
    data["metadata"] = None
    e = TrackerEvent(**data)
    assert e.metadata == {}


def test_metadata_empty_dict_accepted(valid_event_data_dict):
    """Empty dict metadata is accepted."""
    data = valid_event_data_dict.copy()
    data["metadata"] = {}
    e = TrackerEvent(**data)
    assert e.metadata == {}


# ── EventBatch: Valid Batches ─────────────────────────────────────────────────

def test_valid_batch_single_event_accepted(valid_event_data_dict):
    """A batch with 1 valid event and valid api_key is accepted."""
    batch = EventBatch(
        api_key="cji_dev_localtest",
        events=[TrackerEvent(**valid_event_data_dict.copy())],
    )
    assert batch.accepted_events_count == 1
    assert len(batch.events) == 1


def test_valid_batch_100_events_accepted(valid_event_data_dict):
    """Batch with exactly 100 events (max) is accepted."""
    events = [TrackerEvent(**valid_event_data_dict.copy()) for _ in range(100)]
    batch = EventBatch(api_key="cji_dev_localtest", events=events)
    assert len(batch.events) == 100


def test_batch_api_key_preserved(valid_event_data_dict):
    """api_key value is preserved in the model."""
    batch = EventBatch(
        api_key="cji_dev_localtest",
        events=[TrackerEvent(**valid_event_data_dict.copy())],
    )
    assert batch.api_key == "cji_dev_localtest"


# ── EventBatch: Rejection Tests ───────────────────────────────────────────────

def test_empty_batch_rejected(valid_event_data_dict):
    """Batch with 0 events raises ValidationError."""
    with pytest.raises(ValidationError):
        EventBatch(api_key="cji_dev_localtest", events=[])


def test_oversized_batch_rejected(valid_event_data_dict):
    """Batch with 101 events (over max) raises ValidationError."""
    events = [TrackerEvent(**valid_event_data_dict.copy()) for _ in range(101)]
    with pytest.raises(ValidationError) as exc_info:
        EventBatch(api_key="cji_dev_localtest", events=events)
    assert "100" in str(exc_info.value)


def test_short_api_key_rejected(valid_event_data_dict):
    """api_key shorter than 10 characters raises ValidationError."""
    with pytest.raises(ValidationError):
        EventBatch(
            api_key="short",  # < 10 chars
            events=[TrackerEvent(**valid_event_data_dict.copy())],
        )


def test_batch_with_invalid_event_rejected(valid_event_data_dict):
    """Batch containing an event with invalid event_type raises ValidationError."""
    bad_data = valid_event_data_dict.copy()
    bad_data["event_type"] = "INVALID"
    with pytest.raises(ValidationError):
        EventBatch(
            api_key="cji_dev_localtest",
            events=[TrackerEvent(**bad_data)],  # This raises before batch is validated
        )


# ── Response Models ─────────────────────────────────────────────────────────

def test_collect_result_defaults(valid_event_data_dict):
    """CollectResult (Spec 07) counts default to zero and never says 'queued'."""
    r = CollectResult(status="stored", request_id="req-12345678", received=5, accepted=5)
    assert (r.accepted, r.duplicates, r.rejected, r.errors) == (5, 0, 0, [])
    with pytest.raises(ValidationError):
        CollectResult(status="queued", request_id="req-12345678")
    err = EventError(index=2, reason="invalid", fields=["event_type"])
    assert err.model_dump(exclude_none=True) == {"index": 2, "reason": "invalid", "fields": ["event_type"]}


def test_health_status_fields(valid_event_data_dict):
    """HealthStatus (Spec 07) carries the status and, for /health, the live_events count."""
    h = HealthStatus(status="ok", live_events_count=42)
    assert (h.status, h.live_events_count) == ("ok", 42)
    assert HealthStatus(status="not_ready").live_events_count is None
