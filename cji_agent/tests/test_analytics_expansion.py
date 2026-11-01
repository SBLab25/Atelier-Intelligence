import asyncio
from datetime import datetime, timezone, timedelta
import pytest
from cji.collector.security import KeyGrant, allows_journey
from cji.collector.ingest import validate_events
from cji.collector.api import EventBroadcaster
from cji.ops.cli import prune_live_events
from sqlalchemy import create_engine, text


def _event(event_id, journey_id, step="step_1", ev_type="click"):
    return {
        "event_id": event_id,
        "journey_name": journey_id,
        "step_id": step,
        "event_type": ev_type,
        "timestamp": "2026-10-31T12:00:00Z",
        "user_id": "user-12345",
        "session_id": "sess-67890",
        "url": "https://example.com/checkout",
    }


def test_allows_journey_patterns():
    # Wildcard
    assert allows_journey("*", "any_journey")
    assert allows_journey("all", "any_journey")

    # Single journey exact
    assert allows_journey("checkout", "checkout")
    assert not allows_journey("checkout", "onboarding")

    # Comma-separated list
    pattern = "checkout, onboarding, settings_flow"
    assert allows_journey(pattern, "checkout")
    assert allows_journey(pattern, "onboarding")
    assert allows_journey(pattern, "settings_flow")
    assert not allows_journey(pattern, "other_journey")

    # Grant dataclass
    grant = KeyGrant(fingerprint="abcdef01", journey="user_onboarding,checkout")
    assert grant.allows_journey("user_onboarding")
    assert grant.allows_journey("checkout")
    assert not grant.allows_journey("billing")


def test_validate_events_multi_journey():
    grant_wildcard = KeyGrant(fingerprint="12345678", journey="*")
    events = [
        _event("evt-0001", "checkout"),
        _event("evt-0002", "onboarding"),
        _event("evt-0003", "account_settings"),
    ]
    batch = validate_events(events, grant_wildcard)
    assert len(batch.valid) == 3
    assert len(batch.errors) == 0

    grant_list = KeyGrant(fingerprint="12345678", journey="checkout,onboarding")
    batch2 = validate_events(events, grant_list)
    assert len(batch2.valid) == 2
    assert len(batch2.errors) == 1
    assert batch2.errors[0].reason == "journey_not_authorized"
    assert batch2.errors[0].event_id == "evt-0003"


def test_event_broadcaster():
    broadcaster = EventBroadcaster()
    queue = broadcaster.subscribe()

    test_events = [
        {"event_id": "ev-1", "journey_id": "checkout", "event_type": "click"},
        {"event_id": "ev-2", "journey_id": "checkout", "event_type": "rage_click"},
    ]

    broadcaster.publish(test_events)

    assert queue.qsize() == 2
    ev1 = queue.get_nowait()
    assert ev1["event_id"] == "ev-1"
    ev2 = queue.get_nowait()
    assert ev2["event_id"] == "ev-2"

    broadcaster.unsubscribe(queue)
    broadcaster.publish([{"event_id": "ev-3"}])
    assert queue.empty()


def test_prune_live_events_dry_run_and_execution(tmp_path):
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}")

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE live_events (
                timestamp TIMESTAMP,
                event_id VARCHAR PRIMARY KEY,
                journey_name VARCHAR
            )
        """))
        now = datetime.now(timezone.utc)
        old_time = (now - timedelta(days=40)).isoformat()
        new_time = (now - timedelta(days=5)).isoformat()
        conn.execute(text("INSERT INTO live_events VALUES (:ts, 'e-old-1', 'j1')"), {"ts": old_time})
        conn.execute(text("INSERT INTO live_events VALUES (:ts, 'e-old-2', 'j1')"), {"ts": old_time})
        conn.execute(text("INSERT INTO live_events VALUES (:ts, 'e-new-1', 'j1')"), {"ts": new_time})

    # Dry-run
    count = prune_live_events(engine, days=30, dry_run=True)
    assert count == 2

    # Verify rows still exist
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM live_events")).scalar() == 3

    # Execute purge
    deleted = prune_live_events(engine, days=30, dry_run=False)
    assert deleted == 2

    with engine.connect() as conn:
        remaining = conn.execute(text("SELECT event_id FROM live_events")).scalars().all()
        assert remaining == ["e-new-1"]
