"""
Spec 15 (OD-167): schema migrations on a throwaway pgserver database (never DATABASE_URL / Supabase).
"""

from __future__ import annotations

from urllib.parse import urlsplit

import pandas as pd  # type: ignore[import-untyped]
import pytest
from sqlalchemy import inspect, text

from cji.migrations import runner


@pytest.fixture
def db_url(fresh_db_url):
    """A new empty database on the test server (conftest), dropped afterwards."""
    return fresh_db_url()


def _indexes(engine, table):
    return {ix["name"] for ix in inspect(engine).get_indexes(table)}


def _events(n, start=0):
    return pd.DataFrame(
        {
            "event_id": [f"e{i}" for i in range(start, start + n)],
            "user_id": "u",
            "session_id": "s",
            "journey_id": "user_onboarding",
            "step_id": "landing_page",
            "event_type": "page_view",
            "timestamp": pd.Timestamp("2026-10-01", tz="UTC"),
            "duration_ms": 5,
            "url": "",
            "metadata": "{}",
        }
    )


def _old_style_tables(engine, df):
    """Tables as CJI created them before Spec 15: collector DDL and pandas to_sql."""
    up = "\n".join(line for line in runner.discover()[0].up.splitlines() if not line.startswith("--"))
    statements = [s for s in up.split(";") if "live_events" in s or "api_keys" in s]
    with engine.begin() as conn:
        for statement in statements:
            runner._execute(conn, statement)
    df.to_sql("tracking_events", engine, if_exists="replace", index=False)


def test_files_are_complete_and_numbered():
    migrations = runner.discover()
    assert [m.version for m in migrations] == [1, 2, 3]
    assert runner.REQUIRED_SCHEMA_VERSION == migrations[-1].version
    assert not migrations[0].reversible and migrations[1].reversible and migrations[2].reversible


def test_fresh_database_goes_to_the_required_version(db_url):
    engine = runner.engine_for(db_url)
    assert runner.up(engine) == ["0001_baseline", "0002_indexes", "0003_multi_journey_and_partitions"]
    report = runner.status(engine)
    assert report["current"] == 3 and report["pending"] == [] and report["problems"] == []
    assert report["column_differences"] == []
    assert {"tracking_events_event_id_key", "tracking_events_journey_time"} <= _indexes(engine, "tracking_events")
    assert runner.up(engine) == []  # idempotent


def test_existing_database_is_adopted_without_data_changes(db_url):
    engine = runner.engine_for(db_url)
    _old_style_tables(engine, _events(30))
    runner.up(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM tracking_events")).scalar() == 30
    assert runner.current_version(engine) == 2


def test_duplicate_event_ids_stop_0002_with_a_count(db_url):
    engine = runner.engine_for(db_url)
    df = pd.concat([_events(5), _events(2)], ignore_index=True)
    _old_style_tables(engine, df)
    with pytest.raises(runner.MigrationError, match="2 duplicated event_id"):
        runner.up(engine)
    assert runner.current_version(engine) == 1
    assert "tracking_events_event_id_key" not in _indexes(engine, "tracking_events")


def test_up_down_up_keeps_the_data(db_url):
    engine = runner.engine_for(db_url)
    runner.up(engine)
    _events(12).to_sql("tracking_events", engine, if_exists="append", index=False)
    assert runner.down(engine, 1) == ["0002_indexes"]
    assert "tracking_events_event_id_key" not in _indexes(engine, "tracking_events")
    assert runner.up(engine) == ["0002_indexes"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM tracking_events")).scalar() == 12


def test_down_never_reverts_the_baseline(db_url):
    engine = runner.engine_for(db_url)
    runner.up(engine)
    with pytest.raises(runner.MigrationError, match="baseline is not reversible"):
        runner.down(engine, 0)
    assert runner.current_version(engine) == 2


def test_a_changed_migration_file_is_refused(db_url, monkeypatch):
    engine = runner.engine_for(db_url)
    runner.up(engine, to=1)
    original = runner.discover()
    changed = [
        runner.Migration(m.version, m.name, m.up + "\n-- edited", m.down) if m.version == 1 else m for m in original
    ]
    monkeypatch.setattr(runner, "discover", lambda: changed)
    with pytest.raises(runner.MigrationError, match="checksum differs"):
        runner.up(engine)
    assert runner.status(engine)["problems"]


def test_replace_keeps_the_managed_schema(db_url):
    from cji.tools.ingest_json import _write_tracking_events

    engine = runner.engine_for(db_url)
    runner.up(engine)
    assert _write_tracking_events(_events(10), engine) == 10
    assert _write_tracking_events(pd.concat([_events(4, 100), _events(1, 100)]), engine, replace=True) == 4
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM tracking_events")).scalar() == 4
    assert "tracking_events_event_id_key" in _indexes(engine, "tracking_events")


def test_readiness_check_reports_a_schema_behind(db_url):
    class Db:
        def url_value(self):
            return db_url

    class S:
        database = Db()

    engine = runner.engine_for(db_url)
    runner.up(engine, to=1)
    with pytest.raises(runner.SchemaCheckError) as info:
        runner.check_schema(S())
    assert info.value.code == "schema_behind"
    runner.up(engine)
    assert runner.check_schema(S()) == 2


def test_cli_status_and_up_read_the_url_from_a_named_variable(db_url, monkeypatch, capsys):
    from cji.ops import db_cli

    monkeypatch.setenv("CJI_MIGRATE_TEST_URL", db_url)
    assert db_cli.main(["--database-url-env", "CJI_MIGRATE_TEST_URL", "migrate", "up"]) == 0
    assert db_cli.main(["--database-url-env", "CJI_MIGRATE_TEST_URL", "migrate", "status"]) == 0
    out = capsys.readouterr().out
    assert "schema version 2" in out
    password = urlsplit(db_url).password
    assert not password or password not in out
    assert db_cli.main(["--database-url-env", "CJI_UNSET_VARIABLE", "migrate", "status"]) == 2
