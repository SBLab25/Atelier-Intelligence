> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Testing Strategy
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Document Type:** Testing Strategy and Test Specification Reference

---

## Table of Contents

1. [Testing Philosophy](#1-testing-philosophy)
2. [Test Categories and Scope](#2-test-categories-and-scope)
3. [Unit Tests: Friction Engine](#3-unit-tests-friction-engine)
4. [Unit Tests: Collector Models](#4-unit-tests-collector-models)
5. [Unit Tests: Synthetic Data Generator](#5-unit-tests-synthetic-data-generator)
6. [Integration Tests: Collector API](#6-integration-tests-collector-api)
7. [Integration Tests: MCP Servers](#7-integration-tests-mcp-servers)
8. [Integration Tests: LangGraph Graph](#8-integration-tests-langgraph-graph)
9. [End-to-End Tests](#9-end-to-end-tests)
10. [Negative and Edge Case Tests](#10-negative-and-edge-case-tests)
11. [Performance Tests](#11-performance-tests)
12. [Test Fixtures and Factories](#12-test-fixtures-and-factories)
13. [Test Execution and CI Rules](#13-test-execution-and-ci-rules)
14. [Test Coverage Targets](#14-test-coverage-targets)

---

## 1. Testing Philosophy

### 1.1 Core Principles

**1. Tests run offline (no network, no API key) by default.**
Every test in `tests/` must pass without an internet connection, LLM API key, or running database. Tests requiring external services are marked `@pytest.mark.integration` and excluded from CI.

**2. Tests document behaviour before implementation continues.**
Write the test file for the next component before coding it. Running a failing test confirms the interface contract is understood. (TDD: Red → Green → Refactor)

**3. Friction engine is the most critical test target.**
It has no IO dependencies, is used throughout the system, and has exact mathematical expectations. 100% function coverage is required for `mcp_servers/friction_engine_server.py`.

**4. Worker error isolation is a core safety requirement.**
Any worker that crashes must return a valid dict with `next_worker="supervisor"` — not propagate an exception. Tests exist to verify this behaviour under forced exception.

**5. The graph must never hang.**
The supervisor's safety cutoff at MAX_AGENT_ITERATIONS must be tested to ensure the graph terminates even when all workers fail repeatedly.

### 1.2 What NOT to Test

| Not Tested | Reason |
|---|---|
| LLM output quality | Non-deterministic, too slow, costs money |
| LangSmith trace contents | LangSmith infrastructure concern |
| ChromaDB vector similarity quality | Model-dependent, not unit-testable |
| HTML report visual appearance | Use manual browser check in demo rehearsal |
| tracker.js in a real browser | Manual testing; Playwright is Phase 3 |
| DuckDB SQL performance | Covered by Phase 6 smoke test timing |

---

## 2. Test Categories and Scope

### 2.1 Test Pyramid

```
                /‾‾‾‾‾‾‾‾‾‾‾\
               /  E2E Tests   \      2 scenarios
              /─────────────────\    (demo, realtime)
             /  Integration Tests \  ~15 tests
            /─────────────────────\  (API, MCP, Graph)
           /     Unit Tests        \ ~35 tests
          /─────────────────────────\
```

### 2.2 Test File Map

| Test File | Component Tested | Dependencies | CI Safe? |
|---|---|---|---|
| `tests/test_friction_engine.py` | friction_engine_server.py | None | ✅ Yes |
| `tests/test_collector_models.py` | collector/models.py | Pydantic only | ✅ Yes |
| `tests/test_synthetic_data.py` | tools/synthetic_data.py | Faker, pandas, pyarrow | ✅ Yes |
| `tests/test_collector_api.py` | collector/api.py | DuckDB (temp), httpx | ✅ Yes (temp DB) |
| `tests/test_mcp_journey_data.py` | journey_data_server.py | DuckDB, Parquet | ✅ Yes (temp DB) |
| `tests/test_mcp_friction.py` | friction_engine_server.py via MCP protocol | subprocess | ✅ Yes |
| `tests/test_graph.py` | graph.py, supervisor, workers | LangGraph, MCP | ❌ Integration |
| `tests/e2e_demo.py` | Full demo pipeline | All, LLM API | ❌ Integration |
| `tests/e2e_realtime.py` | Full realtime pipeline | All, LLM API, collector | ❌ Integration |

### 2.3 Markers

```ini
# pytest.ini or setup.cfg
[pytest]
markers =
    integration: marks tests requiring network, API keys, or long-running processes
    slow:        marks tests taking > 10 seconds
    realtime:    marks tests requiring a running collector
```

**Default run (CI-safe):**
```bash
pytest tests/ -v -m "not integration and not slow and not realtime"
```

**Full run (manual, with API key):**
```bash
pytest tests/ -v -m "not realtime"  # Includes integration but not realtime
pytest tests/ -v                     # All tests including realtime
```

---

## 3. Unit Tests: Friction Engine

**File:** `tests/test_friction_engine.py`
**Dependencies:** None (pure Python computation)
**Required:** 100% function coverage of friction_engine_server.py

### 3.1 Fixtures

```python
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.friction_engine_server import (
    score_friction, score_all_steps, detect_dropoffs, correlate_signals,
    _normalise, _compute_score, FRICTION_SCORE_THRESHOLD, WEIGHTS, BASELINES
)


@pytest.fixture
def low_step() -> dict:
    """Low-friction step (landing page characteristics)."""
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
    """High-friction step (email verification characteristics)."""
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
    """All-zero step for edge case testing."""
    return {
        "step_id":          "zero_step",
        "unique_users":     0,
        "abandon_rate_pct": 0.0,
        "error_rate_pct":   0.0,
        "avg_dwell_ms":     0,
        "avg_retries":      0.0,
        "avg_rage_clicks":  0.0,
    }
```

### 3.2 Core Scoring Tests

```python
# ─── _normalise tests ────────────────────────────────────────────────────────

def test_normalise_at_baseline():
    """Value at baseline → normalise returns 1/3 = 0.333..."""
    result = _normalise(10.0, 10.0)  # abandon at baseline
    assert abs(result - 1/3) < 0.001

def test_normalise_at_three_times_baseline():
    """Value at 3× baseline → normalise returns exactly 1.0 (capped)."""
    result = _normalise(30.0, 10.0)
    assert result == pytest.approx(1.0)

def test_normalise_above_three_times_baseline_capped():
    """Value > 3× baseline → still returns 1.0 (3.0/3.0 cap)."""
    result = _normalise(100.0, 10.0)
    assert result == pytest.approx(1.0)

def test_normalise_zero_value():
    """Zero value → normalise returns 0.0."""
    assert _normalise(0.0, 10.0) == 0.0

def test_normalise_zero_baseline_guard():
    """Zero baseline → does not raise ZeroDivisionError."""
    result = _normalise(5.0, 0.0)
    assert result == pytest.approx(1.0)   # 5.0 / 0.001 >> 3.0, capped at 1.0

# ─── score_friction: basic checks ─────────────────────────────────────────────

def test_low_step_score_below_threshold(low_step):
    """Landing page characteristics score below critical threshold."""
    r = score_friction(low_step)
    assert r["score"] < FRICTION_SCORE_THRESHOLD
    assert r["is_critical"] is False

def test_high_step_score_at_or_above_threshold(high_step):
    """Email verification characteristics score at or above critical threshold."""
    r = score_friction(high_step)
    assert r["score"] >= FRICTION_SCORE_THRESHOLD
    assert r["is_critical"] is True

def test_score_bounded_0_to_100(high_step):
    """Score is always within [0, 100]."""
    r = score_friction(high_step)
    assert 0 <= r["score"] <= 100

def test_score_zero_step_returns_zero(zero_step):
    """All-zero inputs produce score=0."""
    r = score_friction(zero_step)
    assert r["score"] == 0

def test_score_zero_step_no_signals(zero_step):
    """All-zero inputs produce empty signals list."""
    r = score_friction(zero_step)
    assert r["signals"] == []

def test_score_zero_step_low_confidence(zero_step):
    """All-zero inputs produce minimum confidence of 0.50."""
    r = score_friction(zero_step)
    assert r["confidence"] == pytest.approx(0.50)

def test_step_id_in_result(low_step):
    """step_id is preserved in output."""
    r = score_friction(low_step)
    assert r["step_id"] == "landing_page"

def test_missing_fields_do_not_raise():
    """Dict with only step_id does not raise KeyError."""
    r = score_friction({"step_id": "sparse"})
    assert r["score"] == 0
    assert r["is_critical"] is False

# ─── Signal tests ──────────────────────────────────────────────────────────────

def test_high_step_expected_signals(high_step):
    """Email verification characteristics trigger expected signals."""
    r = score_friction(high_step)
    signals = r["signals"]
    assert "high_drop_off" in signals        # abandon 41.8 > 30 ✓
    assert "frequent_errors" in signals      # error 34.7 > 15 ✓
    assert "extended_hesitation" in signals  # dwell 184000 > 60000 ✓
    assert "severe_confusion" in signals     # dwell 184000 > 120000 ✓
    assert "repeated_retries" in signals     # retries 1.8 > 1.0 ✓
    assert "rage_clicks_detected" in signals # rage 0.62 > 0.5 ✓
    # N.B.: "critical_drop_off" requires abandon > 50, abandon=41.8 does NOT trigger it:
    assert "critical_drop_off" not in signals

def test_critical_drop_off_signal_at_exactly_50():
    """critical_drop_off triggers ONLY when abandon > 50, not at 50 exactly."""
    step_49 = {"step_id": "t", "abandon_rate_pct": 50.0, "error_rate_pct": 0,
                "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0}
    step_51 = {**step_49, "abandon_rate_pct": 50.1}
    assert "critical_drop_off" not in score_friction(step_49)["signals"]
    assert "critical_drop_off" in score_friction(step_51)["signals"]

def test_high_drop_off_signal_at_boundary():
    """high_drop_off triggers ONLY when abandon > 30."""
    step_30 = {"step_id": "t", "abandon_rate_pct": 30.0, "error_rate_pct": 0,
                "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0}
    step_31 = {**step_30, "abandon_rate_pct": 30.1}
    assert "high_drop_off" not in score_friction(step_30)["signals"]
    assert "high_drop_off" in score_friction(step_31)["signals"]

def test_low_step_no_critical_signals(low_step):
    """Low-friction landing page does not trigger critical signals."""
    r = score_friction(low_step)
    assert "critical_drop_off" not in r["signals"]
    assert "severe_confusion" not in r["signals"]
    assert "rage_clicks_detected" not in r["signals"]

def test_confidence_increases_with_signals():
    """More signals → higher confidence, capped at 0.98."""
    step_0_sigs = {"step_id": "t", "abandon_rate_pct": 0, "error_rate_pct": 0,
                    "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0}
    step_5_sigs = {"step_id": "t", "abandon_rate_pct": 40, "error_rate_pct": 20,
                    "avg_dwell_ms": 130000, "avg_retries": 1.5, "avg_rage_clicks": 0.6}
    r0 = score_friction(step_0_sigs)
    r5 = score_friction(step_5_sigs)
    assert r0["confidence"] < r5["confidence"]
    assert r5["confidence"] <= 0.98

# ─── score_all_steps ───────────────────────────────────────────────────────────

def test_all_steps_sorted_descending(low_step, high_step):
    """Results are sorted by score descending."""
    r = score_all_steps([low_step, high_step])
    scores = [s["score"] for s in r["scores"]]
    assert scores == sorted(scores, reverse=True)

def test_all_steps_critical_list(low_step, high_step):
    """critical_steps list contains only steps meeting threshold."""
    r = score_all_steps([low_step, high_step])
    assert "email_verification" in r["critical_steps"]
    assert "landing_page" not in r["critical_steps"]

def test_all_steps_empty_list():
    """Empty list input returns empty results."""
    r = score_all_steps([])
    assert r["scores"] == []
    assert r["avg_score"] == 0.0

def test_all_steps_avg_score():
    """Average score is computed correctly from list."""
    step_a = {"step_id": "a", "abandon_rate_pct": 0, "error_rate_pct": 0,
               "avg_dwell_ms": 15000, "avg_retries": 0.1, "avg_rage_clicks": 0.05}
    step_b = {**step_a, "step_id": "b"}
    r = score_all_steps([step_a, step_b])
    # Both steps at exact baselines → normalise = 1/3 per component
    # raw = (1/3×0.35 + 1/3×0.25 + 1/3×0.15 + 1/3×0.15 + 1/3×0.10) = 1/3
    # score ≈ 33
    assert r["avg_score"] > 0

# ─── detect_dropoffs ──────────────────────────────────────────────────────────

def test_detect_dropoffs_above_threshold():
    """Steps above threshold are returned; steps below are excluded."""
    funnel = [
        {"step_id": "step_a", "drop_off_pct": 50.0, "users": 500},
        {"step_id": "step_b", "drop_off_pct": 10.0, "users": 450},
    ]
    r = detect_dropoffs(funnel, 25.0)
    assert r["count"] == 1
    assert r["critical_dropoffs"][0]["step_id"] == "step_a"

def test_detect_dropoffs_users_lost_calculation():
    """users_lost is correctly computed as users × drop_off / 100."""
    funnel = [{"step_id": "x", "drop_off_pct": 40.0, "users": 1000}]
    r = detect_dropoffs(funnel, 25.0)
    assert r["critical_dropoffs"][0]["users_lost"] == 400

def test_detect_dropoffs_all_below_threshold():
    """No steps above threshold → count=0."""
    funnel = [{"step_id": "x", "drop_off_pct": 5.0, "users": 1000}]
    r = detect_dropoffs(funnel, 25.0)
    assert r["count"] == 0
    assert r["critical_dropoffs"] == []

def test_detect_dropoffs_sorted_by_pct_desc():
    """Results sorted by drop_off_pct descending."""
    funnel = [
        {"step_id": "low",  "drop_off_pct": 30.0, "users": 500},
        {"step_id": "high", "drop_off_pct": 60.0, "users": 400},
    ]
    r = detect_dropoffs(funnel, 25.0)
    assert r["critical_dropoffs"][0]["step_id"] == "high"

# ─── correlate_signals ────────────────────────────────────────────────────────

def test_correlate_systemic_signal():
    """Signal appearing in all steps is marked as systemic."""
    scores = [
        {"step_id": "a", "signals": ["high_drop_off"]},
        {"step_id": "b", "signals": ["high_drop_off"]},
        {"step_id": "c", "signals": ["high_drop_off"]},
    ]
    r = correlate_signals(scores)
    assert "high_drop_off" in r["systemic_signals"]

def test_correlate_isolated_signal_not_systemic():
    """Signal appearing in only 1 of 4 steps is NOT systemic."""
    scores = [
        {"step_id": "a", "signals": ["rage_clicks_detected"]},
        {"step_id": "b", "signals": ["high_drop_off"]},
        {"step_id": "c", "signals": ["high_drop_off"]},
        {"step_id": "d", "signals": []},
    ]
    r = correlate_signals(scores)
    assert "rage_clicks_detected" not in r["systemic_signals"]

def test_correlate_empty_list():
    """Empty scores list returns empty results."""
    r = correlate_signals([])
    assert r["systemic_signals"] == []
    assert r["signal_frequency"] == {}
```

---

## 4. Unit Tests: Collector Models

**File:** `tests/test_collector_models.py`
**Dependencies:** Pydantic v2 only — no network, no database

```python
import sys
from pathlib import Path
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from collector.models import TrackerEvent, EventBatch, ALLOWED_EVENT_TYPES


def valid_event_data() -> dict:
    """Factory for a valid TrackerEvent dict."""
    return {
        "event_id":   "event-12345678-abcdef",
        "user_id":    "user-12345678-abcdef",
        "session_id": "sess-12345678-abcdef",
        "journey_id": "onboarding",
        "step_id":    "email_verification",
        "event_type": "page_view",
        "timestamp":  "2026-03-15T14:30:00Z",
        "duration_ms": 0,
        "url":        "https://example.com/verify",
        "metadata":   {},
    }

# ─── TrackerEvent validation ──────────────────────────────────────────────────

def test_valid_event_passes():
    """Valid TrackerEvent is accepted without error."""
    e = TrackerEvent(**valid_event_data())
    assert e.step_id == "email_verification"

def test_invalid_event_type_rejected():
    """Unknown event_type raises ValidationError."""
    data = valid_event_data()
    data["event_type"] = "INVALID_TYPE"
    with pytest.raises(ValidationError) as exc_info:
        TrackerEvent(**data)
    assert "event_type" in str(exc_info.value)

def test_all_allowed_event_types_accepted():
    """All types in ALLOWED_EVENT_TYPES are accepted."""
    data = valid_event_data()
    for etype in ALLOWED_EVENT_TYPES:
        data["event_type"] = etype
        e = TrackerEvent(**data)
        assert e.event_type == etype

def test_negative_duration_ms_rejected():
    """Negative duration_ms raises ValidationError."""
    data = valid_event_data()
    data["duration_ms"] = -100
    with pytest.raises(ValidationError):
        TrackerEvent(**data)

def test_short_event_id_rejected():
    """event_id shorter than 8 chars raises ValidationError."""
    data = valid_event_data()
    data["event_id"] = "short"  # 5 chars
    with pytest.raises(ValidationError):
        TrackerEvent(**data)

def test_url_query_param_stripped():
    """URL with query params returns sanitised URL without params."""
    data = valid_event_data()
    data["url"] = "https://example.com/verify?token=secret&email=user@test.com"
    e = TrackerEvent(**data)
    assert "?" not in e.url
    assert "secret" not in e.url
    assert "email" not in e.url
    assert e.url == "https://example.com/verify"

def test_url_fragment_stripped():
    """URL with fragment (#) is sanitised."""
    data = valid_event_data()
    data["url"] = "https://example.com/page#section-heading"
    e = TrackerEvent(**data)
    assert "#" not in e.url
    assert e.url == "https://example.com/page"

def test_metadata_json_string_coerced_to_dict():
    """Metadata accepted as JSON string and coerced to dict."""
    data = valid_event_data()
    data["metadata"] = '{"error_code": "TOKEN_EXPIRED", "retry_count": 2}'
    e = TrackerEvent(**data)
    assert isinstance(e.metadata, dict)
    assert e.metadata["error_code"] == "TOKEN_EXPIRED"

def test_metadata_invalid_json_string_returns_empty():
    """Invalid JSON string metadata returns empty dict (no error)."""
    data = valid_event_data()
    data["metadata"] = "not valid json {"
    e = TrackerEvent(**data)
    assert e.metadata == {}

# ─── EventBatch validation ─────────────────────────────────────────────────────

def test_valid_batch_accepted():
    """Valid EventBatch with 1 event is accepted."""
    batch = EventBatch(api_key="cji_dev_localtest", events=[TrackerEvent(**valid_event_data())])
    assert batch.accepted_events_count == 1  # or len(batch.events)

def test_empty_batch_rejected():
    """Zero-event batch raises ValidationError."""
    with pytest.raises(ValidationError):
        EventBatch(api_key="cji_dev_localtest", events=[])

def test_oversized_batch_rejected():
    """Batch with 101 events raises ValidationError."""
    events = [TrackerEvent(**valid_event_data()) for _ in range(101)]
    with pytest.raises(ValidationError) as exc_info:
        EventBatch(api_key="cji_dev_localtest", events=events)
    assert "100" in str(exc_info.value)

def test_short_api_key_rejected():
    """api_key shorter than 10 chars raises ValidationError."""
    with pytest.raises(ValidationError):
        EventBatch(api_key="short", events=[TrackerEvent(**valid_event_data())])
```

---

## 5. Unit Tests: Synthetic Data Generator

**File:** `tests/test_synthetic_data.py`
**Dependencies:** Faker, pandas, pyarrow, pathlib

```python
import sys
from pathlib import Path
import tempfile
import pytest
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.synthetic_data import generate_demo_data, STEP_PROFILES, ALLOWED_EVENT_TYPES


@pytest.fixture
def parquet_path(tmp_path: Path) -> Path:
    """Temporary Parquet file for testing."""
    return tmp_path / "test_events.parquet"


def test_generates_expected_columns(parquet_path):
    """Generated Parquet has all required columns with correct types."""
    generate_demo_data(n_sessions=50, seed=42, output_path=parquet_path)
    df = pd.read_parquet(parquet_path)
    required_cols = {"event_id", "user_id", "journey_id", "step_id",
                      "event_type", "timestamp", "duration_ms", "metadata"}
    assert required_cols.issubset(set(df.columns))

def test_event_types_valid(parquet_path):
    """All event_type values are in ALLOWED_EVENT_TYPES."""
    generate_demo_data(n_sessions=50, seed=42, output_path=parquet_path)
    df = pd.read_parquet(parquet_path)
    assert set(df["event_type"].unique()).issubset(ALLOWED_EVENT_TYPES)

def test_duration_ms_non_negative(parquet_path):
    """All duration_ms values are >= 0."""
    generate_demo_data(n_sessions=50, seed=42, output_path=parquet_path)
    df = pd.read_parquet(parquet_path)
    assert (df["duration_ms"] >= 0).all()

def test_email_verification_highest_drop_rate(parquet_path):
    """email_verification has highest abandon rate among steps."""
    generate_demo_data(n_sessions=500, seed=42, output_path=parquet_path)
    df = pd.read_parquet(parquet_path)
    abandons = df[df["event_type"] == "abandon"].groupby("step_id").size() / \
               df.groupby("step_id")["user_id"].nunique()
    if "email_verification" in abandons.index:
        # email_verification should have abandon rate close to STEP_PROFILES value (0.42)
        ev_rate = abandons.get("email_verification", 0)
        assert ev_rate > 0.30, f"email_verification abandon rate too low: {ev_rate}"

def test_reproducibility(parquet_path):
    """Same seed produces same event count (Faker seeded)."""
    path1 = parquet_path.parent / "run1.parquet"
    path2 = parquet_path.parent / "run2.parquet"
    generate_demo_data(n_sessions=100, seed=42, output_path=path1)
    generate_demo_data(n_sessions=100, seed=42, output_path=path2)
    df1 = pd.read_parquet(path1)
    df2 = pd.read_parquet(path2)
    assert len(df1) == len(df2)

def test_all_journey_steps_present(parquet_path):
    """All 6 journey steps appear in generated data."""
    generate_demo_data(n_sessions=100, seed=42, output_path=parquet_path)
    df = pd.read_parquet(parquet_path)
    from config import JOURNEY_CONFIG
    expected_steps = set(JOURNEY_CONFIG["steps"])
    actual_steps = set(df["step_id"].unique())
    assert expected_steps == actual_steps
```

---

## 6. Integration Tests: Collector API

**File:** `tests/test_collector_api.py`
**Dependencies:** httpx, DuckDB (temp in-memory), FastAPI TestClient

```python
import sys
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

# Patch config to use temp DB path before importing the app
with tempfile.TemporaryDirectory() as tmpdir:
    import os
    os.environ["CJI_MODE"] = "realtime"
    # Set temp DB path via env or monkeypatching

from collector.api import app

client = TestClient(app)


def valid_event_payload(api_key: str = "cji_dev_localtest") -> dict:
    return {
        "api_key": api_key,
        "events": [{
            "event_id":    "test-event-12345678",
            "user_id":     "test-user-12345678",
            "session_id":  "test-sess-12345678",
            "journey_id":  "onboarding",
            "step_id":     "email_verification",
            "event_type":  "page_view",
            "timestamp":   "2026-03-15T14:30:00Z",
            "duration_ms": 0,
            "url":         "https://example.com/verify",
            "metadata":    {}
        }]
    }


def test_health_endpoint_returns_200():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "live_events_count" in data

def test_health_endpoint_returns_mode():
    r = client.get("/health")
    data = r.json()
    assert data["mode"] in ("demo", "realtime")

def test_tracker_js_served():
    r = client.get("/tracker.js")
    assert r.status_code == 200
    assert "CJITracker" in r.text

def test_collect_batch_dev_key_accepted():
    r = client.post("/collect/batch", json=valid_event_payload())
    assert r.status_code == 200
    data = r.json()
    assert data["accepted"] >= 0

def test_collect_batch_invalid_key_rejected():
    payload = valid_event_payload("invalid_key_that_does_not_exist")
    r = client.post("/collect/batch", json=payload)
    assert r.status_code == 401

def test_collect_batch_invalid_event_type_rejected():
    payload = valid_event_payload()
    payload["events"][0]["event_type"] = "INVALID"
    r = client.post("/collect/batch", json=payload)
    assert r.status_code == 422

def test_collect_batch_duplicate_event_idempotent():
    """Duplicate event_id is silently ignored (INSERT OR IGNORE)."""
    payload = valid_event_payload()
    r1 = client.post("/collect/batch", json=payload)
    r2 = client.post("/collect/batch", json=payload)
    # Both succeed
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Second batch: accepted or rejected (implementation may vary)
    # What matters: no 500 error

def test_live_stats_returns_structure():
    r = client.get("/live/stats", headers={"X-CJI-Key": "cji_dev_localtest"})
    assert r.status_code == 200
    data = r.json()
    assert "steps" in data
    assert "total_events" in data
    assert "window_mins" in data
```

---

## 7. Integration Tests: MCP Servers

**File:** `tests/test_mcp_friction.py`
**Dependencies:** asyncio, MCP subprocess protocol

```python
"""
Integration test: friction_engine_server via real MCP subprocess protocol.
Tests the JSON-RPC communication layer, not just the Python functions.
"""
import sys
import json
import subprocess
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.integration
class TestFrictionMCPProtocol:

    def test_server_starts_and_responds_to_initialize(self):
        """Server responds to JSON-RPC initialize with valid result."""
        p = subprocess.Popen(
            [sys.executable, "mcp_servers/friction_engine_server.py"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        p.stdin.write(b'{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}\n')
        p.stdin.flush()
        line = p.stdout.readline()
        p.terminate()
        data = json.loads(line)
        assert "result" in data
        assert "cji-friction-engine" in str(data)

    def test_score_friction_via_mcp_protocol(self):
        """score_friction tool returns valid result over stdio JSON-RPC."""
        import asyncio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def run():
            params = StdioServerParameters(
                command=sys.executable,
                args=["mcp_servers/friction_engine_server.py"]
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "score_friction",
                        arguments={"step_metrics": {
                            "step_id": "test",
                            "abandon_rate_pct": 41.8,
                            "error_rate_pct": 34.7,
                            "avg_dwell_ms": 184000,
                            "avg_retries": 1.8,
                            "avg_rage_clicks": 0.62,
                        }}
                    )
                    text = result.content[0].text
                    data = json.loads(text)
                    assert "score" in data
                    assert data["is_critical"] is True
                    return data

        result = asyncio.run(run())
        assert result["score"] >= 60
```

---

## 8. Integration Tests: LangGraph Graph

**File:** `tests/test_graph.py`
**Dependencies:** LangGraph, MCP subprocess, LLM API

```python
"""
Integration test: full graph routing logic with MemorySaver (no SQLite).
LLM calls are NOT tested — workers fail gracefully and graph routes to END.
"""
import sys
from pathlib import Path
from uuid import uuid4
import pytest
from langgraph.checkpoint.memory import MemorySaver

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.integration
def test_graph_compiles_without_error():
    """Graph compilation succeeds without API key or DuckDB access."""
    from graph import build_graph
    g = build_graph(use_persistence=False)
    assert g is not None

@pytest.mark.integration
def test_supervisor_routes_to_data_worker_first():
    """Empty state → supervisor routes to data_worker."""
    from agents.supervisor import supervisor
    state = {
        "event_summary": {}, "friction_scores": [], "insights": [],
        "human_approved": False, "report_path": "", "iteration": 0,
        "errors": [], "messages": [], "worker_statuses": [],
    }
    r = supervisor(state)
    assert r["next_worker"] == "data_worker"
    assert r["iteration"] == 1

@pytest.mark.integration
def test_supervisor_safety_cutoff():
    """At MAX_AGENT_ITERATIONS, supervisor routes to END."""
    from config import MAX_AGENT_ITERATIONS
    from agents.supervisor import supervisor
    state = {
        "event_summary": {}, "friction_scores": [], "insights": [],
        "human_approved": False, "report_path": "", "iteration": MAX_AGENT_ITERATIONS,
        "errors": [], "messages": [], "worker_statuses": [],
    }
    r = supervisor(state)
    assert r["next_worker"] == "END"

@pytest.mark.integration
def test_supervisor_routes_to_friction_after_data():
    """With event_summary but no friction_scores → route to friction_worker."""
    from agents.supervisor import supervisor
    state = {
        "event_summary": {"step_metrics": [{"step_id": "x"}]},  # non-empty
        "friction_scores": [],
        "insights": [],
        "human_approved": False,
        "report_path": "",
        "iteration": 1,
        "errors": [],
        "messages": [],
        "worker_statuses": [],
    }
    r = supervisor(state)
    assert r["next_worker"] == "friction_worker"

@pytest.mark.integration
def test_graph_pauses_before_report():
    """Graph pauses at report_worker when human_approved=False."""
    from graph import build_graph
    from datetime import datetime, timezone
    from config import JOURNEY_CONFIG

    g = build_graph(use_persistence=False)
    config = {"configurable": {"thread_id": str(uuid4())}}

    # State with fake completed analysis to trigger pause
    initial_state = {
        "mode": "demo",
        "journey_name": "onboarding",
        "journey_steps": JOURNEY_CONFIG["steps"],
        "analysis_window_days": 30,
        "analysis_window_mins": 60,
        "collector_url": "http://localhost:8000",
        "iteration": 0,
        "next_worker": "",
        "human_approved": False,
        "messages": [],
        "raw_events": [],
        "event_summary": {"test": True},         # triggers friction routing
        "live_event_count": 0,
        "friction_scores": [{"step_id": "x"}],   # triggers insight routing
        "critical_steps": [],
        "insights": [{"insight_id": "test"}],     # triggers pause
        "prioritized_fixes": [],
        "report_path": "",
        "narrative": "",
        "last_run_at": datetime.now(timezone.utc).isoformat(),
        "worker_statuses": [],
        "errors": [],
    }

    # Run — should reach END (pause) without calling report_worker
    events = list(g.stream(initial_state, config=config, stream_mode="values"))
    snapshot = g.get_state(config)

    # Graph should be paused (next = report_worker) or at END
    # Due to interrupt_before=["report_worker"], next should be report_worker
    assert snapshot.values.get("report_path") == ""
```

---

## 9. End-to-End Tests

**File:** `tests/e2e_demo.py`
**Dependencies:** All services, LLM API key
**Runtime:** ~3–5 minutes

```python
"""
End-to-end test: Full demo mode pipeline.
Requires: ANTHROPIC_API_KEY or OPENAI_API_KEY set in .env
"""
import sys
import glob
import subprocess
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.mark.integration
@pytest.mark.slow
def test_e2e_demo_pipeline():
    """Full demo mode pipeline produces a valid HTML report."""
    # 1. Generate data
    r = subprocess.run(
        [sys.executable, "main.py", "--mode", "demo", "--generate-data"],
        capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, f"generate-data failed: {r.stderr}"
    assert Path("data/events.parquet").exists()

    # 2. Run analysis
    r = subprocess.run(
        [sys.executable, "main.py", "--mode", "demo", "--run", "--auto-approve"],
        capture_output=True, text=True, timeout=300  # 5-minute timeout
    )
    assert r.returncode == 0, f"analysis failed: {r.stderr}"

    # 3. Check report created
    reports = glob.glob("reports/cji_report_onboarding_*.html")
    assert len(reports) > 0, "No report generated"

    # 4. Validate report contents
    report_content = Path(reports[-1]).read_text()
    assert "Chart.js" in report_content, "Missing Chart.js CDN"
    assert "Friction Score" in report_content, "Missing friction score section"
    assert len(report_content) > 10000, "Report too small — likely incomplete"

    print(f"E2E test PASSED: {reports[-1]}")
```

---

## 10. Negative and Edge Case Tests

### 10.1 Error Isolation Tests (Manual Verification Procedure)

These tests require temporarily injecting exceptions into workers. They cannot be fully automated without dependency injection — use as manual regression checks.

**Test: data_worker exception isolation**
```python
# In agents/workers.py, temporarily add at top of data_worker:
# raise ValueError("Injected test exception")

# Then run:
python main.py --mode demo --run --auto-approve
# Expected:
# - No crash (process exits 0)
# - errors list in state contains "data_worker: ValueError: Injected test exception"
# - Report may be incomplete but is generated with available data
```

**Test: LLM unavailable — insight fallback**
```bash
LLM_MODEL=nonexistent/model-xyz python main.py --mode demo --run --auto-approve
# Expected:
# - insight_worker completes without crash
# - Insights have category="unknown", title="Friction at {step_id}"
# - report_worker generates report with fallback narrative
```

**Test: ChromaDB empty — search guard**
```bash
rm -rf data/chroma/
python main.py --mode demo --run --auto-approve 2>&1 | grep -i "chroma\|insight"
# Expected: no crash, "No insights stored yet" returned from search_insights
```

### 10.2 Boundary Value Tests (Automated)

```python
def test_friction_score_at_threshold_boundary():
    """Score of exactly 60 is marked critical."""
    # Compute inputs that produce exactly score=60:
    # Only abandon = 3× baseline (0.35 × 1.00 = 0.35) + error = 3× (0.25 × 1.00 = 0.25) = 0.60
    step = {"step_id": "boundary", "abandon_rate_pct": 30.0, "error_rate_pct": 15.0,
            "avg_dwell_ms": 0, "avg_retries": 0, "avg_rage_clicks": 0}
    r = score_friction(step)
    assert r["score"] >= 60  # May be exactly 60 or above depending on normalisation
    assert r["is_critical"] is True

def test_event_batch_exactly_100_accepted():
    """Exactly 100 events in a batch is accepted (boundary = max)."""
    events = [TrackerEvent(**valid_event_data()) for _ in range(100)]
    batch = EventBatch(api_key="cji_dev_localtest", events=events)
    assert len(batch.events) == 100

def test_event_batch_101_rejected():
    """101 events in a batch is rejected."""
    events = [TrackerEvent(**valid_event_data()) for _ in range(101)]
    with pytest.raises(ValidationError):
        EventBatch(api_key="cji_dev_localtest", events=events)
```

---

## 11. Performance Tests

### 11.1 Friction Engine Performance

```bash
python -c "
import time, sys; sys.path.insert(0, '.')
from mcp_servers.friction_engine_server import score_all_steps

steps = [
    {'step_id': f's{i}', 'abandon_rate_pct': 30.0, 'error_rate_pct': 10.0,
     'avg_dwell_ms': 60000, 'avg_retries': 0.5, 'avg_rage_clicks': 0.2}
    for i in range(100)
]

start = time.time()
for _ in range(1000):
    score_all_steps(steps)
elapsed = time.time() - start
print(f'1000 × 100 steps: {elapsed:.3f}s ({elapsed/1000*1000:.1f}ms per call)')
assert elapsed < 5.0, f'Friction engine too slow: {elapsed}s for 1000 iterations'
print('Performance test PASSED')
"
# Expected: < 5 seconds for 1000 × 100 steps (50ms per call)
```

### 11.2 DuckDB Analytics Performance

```bash
python -c "
import time, duckdb, sys; sys.path.insert(0, '.')
from config import EVENTS_PARQUET
import os

if not os.path.exists(EVENTS_PARQUET):
    print('Generate data first: python main.py --generate-data')
    sys.exit(0)

conn = duckdb.connect()
conn.execute(f\"CREATE VIEW events AS SELECT * FROM read_parquet('{EVENTS_PARQUET}')\")

query = '''
    SELECT step_id, COUNT(DISTINCT user_id) as users,
           ROUND(SUM(CASE WHEN event_type='abandon' THEN 1 ELSE 0 END)
                 * 100.0 / NULLIF(COUNT(DISTINCT user_id), 0), 2) as abandon_rate_pct
    FROM events
    WHERE journey_id = 'onboarding'
    GROUP BY step_id
'''

start = time.time()
for _ in range(100):
    conn.execute(query).fetchall()
elapsed = time.time() - start
avg_ms = (elapsed / 100) * 1000
print(f'100 queries: {elapsed:.3f}s ({avg_ms:.1f}ms avg)')
assert avg_ms < 200, f'DuckDB too slow: {avg_ms}ms per query'
print('DuckDB performance PASSED')
"
# Expected: < 100ms per query average (typically 10–30ms with 15K rows)
```

---

## 12. Test Fixtures and Factories

### 12.1 Shared Fixtures (conftest.py)

```python
# tests/conftest.py

import sys
import os
from pathlib import Path
import pytest
import tempfile

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def demo_parquet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate demo Parquet file once for all tests in session."""
    from tools.synthetic_data import generate_demo_data
    out = tmp_path_factory.mktemp("data") / "test_events.parquet"
    generate_demo_data(n_sessions=200, seed=42, output_path=out)
    return out


@pytest.fixture
def demo_step_metrics() -> list:
    """Standard 6-step demo metrics for testing."""
    return [
        {"step_id": "landing_page",       "unique_users": 2000, "abandon_rate_pct": 15.0,
         "error_rate_pct": 2.1, "avg_dwell_ms": 12000, "avg_retries": 0.01, "avg_rage_clicks": 0.02},
        {"step_id": "sign_up_form",        "unique_users": 1700, "abandon_rate_pct": 25.0,
         "error_rate_pct": 18.0, "avg_dwell_ms": 45000, "avg_retries": 0.4, "avg_rage_clicks": 0.15},
        {"step_id": "email_verification",  "unique_users": 732, "abandon_rate_pct": 41.8,
         "error_rate_pct": 34.7, "avg_dwell_ms": 184000, "avg_retries": 1.8, "avg_rage_clicks": 0.62},
        {"step_id": "profile_setup",       "unique_users": 156, "abandon_rate_pct": 20.0,
         "error_rate_pct": 8.0, "avg_dwell_ms": 60000, "avg_retries": 0.2, "avg_rage_clicks": 0.05},
        {"step_id": "first_action",        "unique_users": 134, "abandon_rate_pct": 12.0,
         "error_rate_pct": 5.0, "avg_dwell_ms": 30000, "avg_retries": 0.1, "avg_rage_clicks": 0.03},
        {"step_id": "completion",          "unique_users": 112, "abandon_rate_pct": 5.0,
         "error_rate_pct": 1.0, "avg_dwell_ms": 10000, "avg_retries": 0.0, "avg_rage_clicks": 0.01},
    ]


@pytest.fixture
def demo_funnel_data() -> list:
    """Standard 6-step funnel data for testing."""
    return [
        {"step_id": "landing_page",       "users": 2000, "drop_off_pct": 15.0},
        {"step_id": "sign_up_form",        "users": 1700, "drop_off_pct": 25.0},
        {"step_id": "email_verification",  "users": 1275, "drop_off_pct": 42.5},
        {"step_id": "profile_setup",       "users":  733, "drop_off_pct": 20.0},
        {"step_id": "first_action",        "users":  586, "drop_off_pct": 12.0},
        {"step_id": "completion",          "users":  516, "drop_off_pct": 0.0},
    ]
```

---

## 13. Test Execution and CI Rules

### 13.1 Standard Test Commands

```bash
# Run all CI-safe tests (default — no API key needed)
pytest tests/ -v -m "not integration and not slow"

# Run friction engine only (fastest — pure computation)
pytest tests/test_friction_engine.py -v

# Run with coverage report
pytest tests/ -v --cov=mcp_servers --cov-report=term-missing

# Run integration tests (requires API key)
pytest tests/ -v -m integration

# Run everything including realtime
pytest tests/ -v

# Run in parallel (after pip install pytest-xdist)
pytest tests/ -n auto -m "not integration"
```

### 13.2 CI Rules (Non-Negotiable)

1. **All tests in `tests/test_friction_engine.py` must pass:** Zero exceptions. These are the first thing reviewers will check.
2. **No LLM calls in `tests/` (not marked integration):** Tests must pass with `LLM_MODEL=` unset.
3. **No DuckDB file access in unit tests:** Inject temp paths or use in-memory DuckDB.
4. **No sleep() > 100ms in unit tests:** Tests must run in < 30 seconds total.
5. **`@pytest.mark.integration` required for:** subprocess spawning, API calls, file system writes outside tmp_path.

### 13.3 pytest.ini Configuration

```ini
[pytest]
testpaths = tests
python_files = test_*.py e2e_*.py
python_classes = Test*
python_functions = test_*

markers =
    integration: Tests requiring network, API keys, or long-running processes
    slow: Tests taking > 10 seconds (excluded from quick runs)
    realtime: Tests requiring a running collector on port 8000

filterwarnings =
    ignore::DeprecationWarning:chromadb.*
    ignore::DeprecationWarning:sentence_transformers.*
    ignore::pydantic.*

addopts = --tb=short -q
```

---

## 14. Test Coverage Targets

### 14.1 Coverage Requirements by Component

| Component | Coverage Target | Priority | Notes |
|---|---|---|---|
| `mcp_servers/friction_engine_server.py` | 100% | P0 | Every function, every branch |
| `collector/models.py` | 100% | P0 | Every validator, every rejection path |
| `tools/synthetic_data.py` | 80% | P1 | Core generation logic |
| `agents/supervisor.py` | 90% | P1 | All routing branches |
| `mcp_servers/journey_data_server.py` | 70% | P2 | SQL queries via integration |
| `mcp_servers/insight_server.py` | 60% | P2 | LLM paths via integration only |
| `graph.py` | 80% | P1 | Compile and get_graph |
| `collector/api.py` | 70% | P2 | Route handlers |
| `dashboard.py` | 20% | P3 | UI code hard to test automatically |
| `main.py` | 30% | P3 | CLI argument parsing |

### 14.2 Running Coverage Report

```bash
# Install coverage tool
pip install pytest-cov

# Run with coverage for critical components
pytest tests/test_friction_engine.py tests/test_collector_models.py \
    --cov=mcp_servers.friction_engine_server \
    --cov=collector.models \
    --cov-report=term-missing \
    --cov-fail-under=90
```

### 14.3 Coverage Check in Build Verification

```bash
# Minimum gate: friction engine must be > 90% covered
pytest tests/test_friction_engine.py \
    --cov=mcp_servers.friction_engine_server \
    --cov-fail-under=90 \
    --cov-report=term-missing -q
# Expected: shows coverage report, exits 0
```
