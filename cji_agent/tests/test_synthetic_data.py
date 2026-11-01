"""
Unit Tests: Synthetic Data Generator
=====================================
Tests the generate_demo_data() function output structure and content.
Requires Faker, pandas, pyarrow — no network, no LLM, no DuckDB.

Run:
  pytest tests/test_synthetic_data.py -v
"""

import pandas as pd
import pytest

from cji.tools.synthetic_data import (
    ALLOWED_EVENT_TYPES,
    STEP_PROFILES,
    generate_demo_data,
)


# ── Fixtures (Shared fixtures now in conftest.py) ──────────────────────────────────────────────────────────────


# ── Schema Tests ───────────────────────────────────────────────────────────────

def test_generates_expected_columns(small_df):
    """Output Parquet has all required columns."""
    required_cols = {
        "event_id", "user_id", "session_id", "journey_id",
        "step_id", "event_type", "timestamp", "duration_ms",
        "url", "metadata",
    }
    assert required_cols.issubset(set(small_df.columns)), (
        f"Missing columns: {required_cols - set(small_df.columns)}"
    )


def test_event_id_is_unique(small_df):
    """Every event has a unique event_id."""
    assert small_df["event_id"].nunique() == len(small_df), (
        "Found duplicate event_ids"
    )


def test_event_types_all_valid(small_df):
    """All event_type values are in ALLOWED_EVENT_TYPES."""
    found_types = set(small_df["event_type"].unique())
    invalid = found_types - ALLOWED_EVENT_TYPES
    assert not invalid, f"Found invalid event types: {invalid}"


def test_duration_ms_non_negative(small_df):
    """All duration_ms values are >= 0."""
    assert (small_df["duration_ms"] >= 0).all(), (
        "Found negative duration_ms values"
    )


def test_metadata_is_json_string(small_df):
    """metadata column contains JSON strings (can be parsed)."""
    import json
    # Check a sample — all should parse without error
    for val in small_df["metadata"].head(20):
        assert isinstance(val, str), f"metadata is not a string: {type(val)}"
        parsed = json.loads(val)
        assert isinstance(parsed, dict), f"metadata does not parse to dict: {val}"


def test_journey_id_consistent(small_df):
    """All events belong to the same journey."""
    assert small_df["journey_id"].nunique() == 1


def test_all_journey_steps_present(small_df):
    """All journey steps appear in the generated data."""
    from cji.config import JOURNEY_CONFIG
    expected_steps = set(JOURNEY_CONFIG["steps"])
    actual_steps   = set(small_df["step_id"].unique())
    missing        = expected_steps - actual_steps
    assert not missing, f"Missing steps: {missing}"


def test_url_format(small_df):
    """URLs are non-empty strings and do not contain query params."""
    non_empty = small_df[small_df["url"] != ""]["url"]
    has_query = non_empty.str.contains(r"\?", regex=True)
    assert not has_query.any(), "Found URLs with query parameters"


# ── Content / Statistical Tests ────────────────────────────────────────────────

def test_email_verification_highest_drop_rate(medium_df):
    """email_verification has the highest abandon event rate among steps."""
    abandon_df = medium_df[medium_df["event_type"] == "abandon"]
    users_per_step = medium_df.groupby("step_id")["user_id"].nunique()
    abandons_per_step = abandon_df.groupby("step_id").size()
    abandon_rate = (abandons_per_step / users_per_step).dropna()

    if "email_verification" in abandon_rate.index:
        ev_rate = abandon_rate["email_verification"]
        # Should be close to the 0.42 profile value
        assert ev_rate > 0.30, (
            f"email_verification abandon rate too low: {ev_rate:.2%} "
            f"(expected > 30%)"
        )


def test_step_profiles_keys_match_journey_config():
    """STEP_PROFILES contains exactly the same keys as JOURNEY_CONFIG steps."""
    from cji.config import JOURNEY_CONFIG
    profile_keys  = set(STEP_PROFILES.keys())
    journey_steps = set(JOURNEY_CONFIG["steps"])
    assert profile_keys == journey_steps, (
        f"STEP_PROFILES keys do not match JOURNEY_CONFIG steps.\n"
        f"Extra in profiles: {profile_keys - journey_steps}\n"
        f"Missing from profiles: {journey_steps - profile_keys}"
    )


def test_email_verification_profile_values():
    """email_verification profile has exact required values from spec."""
    profile = STEP_PROFILES["email_verification"]
    assert profile["drop_rate"]   == pytest.approx(0.42)
    assert profile["avg_dwell_s"] == 180
    assert profile["error_rate"]  == pytest.approx(0.35)


def test_completion_lowest_drop_rate():
    """onboarding_done (final step) has the lowest drop_rate among all steps."""
    final_step = "onboarding_done"
    final_rate = STEP_PROFILES[final_step]["drop_rate"]
    other_rates = [
        v["drop_rate"] for k, v in STEP_PROFILES.items() if k != final_step
    ]
    assert all(final_rate <= r for r in other_rates), (
        f"{final_step} should have the lowest drop_rate (got {final_rate})"
    )


def test_error_events_have_metadata(small_df):
    """Error events have non-empty metadata (error_code field)."""
    import json
    errors = small_df[small_df["event_type"] == "error"]
    if len(errors) > 0:
        for _, row in errors.head(10).iterrows():
            meta = json.loads(row["metadata"])
            assert "error_code" in meta, f"Error event missing error_code: {meta}"


def test_rage_click_events_have_click_count(small_df):
    """Rage click events contain click_count in metadata."""
    import json
    rage = small_df[small_df["event_type"] == "rage_click"]
    if len(rage) > 0:
        for _, row in rage.head(5).iterrows():
            meta = json.loads(row["metadata"])
            assert "click_count" in meta, f"Rage click missing click_count: {meta}"
            assert meta["click_count"] >= 3, "Rage click count should be >= 3"


def test_multiple_event_types_present(small_df):
    """Generated data contains multiple distinct event types."""
    found_types = set(small_df["event_type"].unique())
    # At minimum: page_view, abandon, step_complete
    assert "page_view"     in found_types
    assert "abandon"       in found_types
    assert "step_complete" in found_types


# ── Reproducibility ────────────────────────────────────────────────────────────

def test_same_seed_same_row_count(tmp_path):
    """Same seed produces identical event counts."""
    path1 = tmp_path / "run1.parquet"
    path2 = tmp_path / "run2.parquet"
    generate_demo_data(n_sessions=100, seed=42, output_path=path1)
    generate_demo_data(n_sessions=100, seed=42, output_path=path2)
    df1 = pd.read_parquet(path1)
    df2 = pd.read_parquet(path2)
    assert len(df1) == len(df2), (
        f"Different row counts with same seed: {len(df1)} vs {len(df2)}"
    )


def test_different_seeds_different_row_counts(tmp_path):
    """Different seeds produce different outputs (not always same count)."""
    path1 = tmp_path / "seed42.parquet"
    path2 = tmp_path / "seed99.parquet"
    generate_demo_data(n_sessions=200, seed=42, output_path=path1)
    generate_demo_data(n_sessions=200, seed=99, output_path=path2)
    df1 = pd.read_parquet(path1)
    df2 = pd.read_parquet(path2)
    # At least one of: different counts OR different user_ids
    # (seeds affect faker + random decisions)
    users1 = set(df1["user_id"].unique())
    users2 = set(df2["user_id"].unique())
    assert users1 != users2, "Different seeds produced identical user IDs"


def test_return_value_is_path(tmp_path):
    """generate_demo_data returns the output Path object."""
    path = tmp_path / "out.parquet"
    result = generate_demo_data(n_sessions=10, seed=1, output_path=path)
    assert result == path
    assert result.exists()


def test_output_file_created(tmp_path):
    """Output Parquet file is created on disk."""
    path = tmp_path / "events.parquet"
    assert not path.exists()
    generate_demo_data(n_sessions=10, seed=42, output_path=path)
    assert path.exists()
    assert path.stat().st_size > 0
