"""
Spec 15 (OD-166): cji-backup create / verify / restore on throwaway pgserver databases and temporary homes.
"""

from __future__ import annotations

import json
import sqlite3
from urllib.parse import urlsplit

import pandas as pd  # type: ignore[import-untyped]
import pytest
from sqlalchemy import create_engine, text

from cji.migrations import runner
from cji.ops import backup
from cji.ops.common import OpsError, database_name


def _events(n, start=0):
    return pd.DataFrame(
        {
            "event_id": [f"e{i}" for i in range(start, start + n)],
            "user_id": [f"user-{i % 7}" for i in range(n)],
            "session_id": "s",
            "journey_id": "user_onboarding",
            "step_id": "landing_page",
            "event_type": "page_view",
            "timestamp": pd.Timestamp("2026-10-01T10:00:00", tz="UTC"),
            "duration_ms": 5,
            "url": "",
            "metadata": "{}",
        }
    )


@pytest.fixture
def source(fresh_db_url, tmp_path):
    """A populated deployment: migrated database with events and keys, a home with SQLite stores and files."""
    url = fresh_db_url()
    engine = runner.engine_for(url)
    runner.up(engine)
    _events(40).to_sql("tracking_events", engine, if_exists="append", index=False)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO api_keys (api_key, journey_name, description) VALUES "
                "('cji_live_test', 'user_onboarding', 'test')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO live_events (timestamp, event_id, journey_name, step_id, event_type, metadata) "
                "VALUES ('2026-10-01 10:00:00', 'l1', 'user_onboarding', 'landing_page', 'click', '{}')"
            )
        )
    home = tmp_path / "home"
    data = home / "data"
    (home / "reports").mkdir(parents=True)
    data.mkdir()
    (home / "reports" / "cji_report_1.html").write_text("<html>r</html>", encoding="utf-8")
    (data / "api_tokens.json").write_text(json.dumps({"tokens": []}), encoding="utf-8")
    (data / "last_run.json").write_text(json.dumps({"run_id": "x"}), encoding="utf-8")
    conn = sqlite3.connect(data / "cji_checkpoints.db")
    conn.execute("CREATE TABLE run_index (run_id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO run_index VALUES ('r1')")
    conn.commit()
    conn.close()
    return url, backup.Layout.default(home)


def test_round_trip_restores_equal_counts_checksums_and_files(source, fresh_db_url, tmp_path, pg_bin):
    url, layout = source
    tools = backup.PgTools.find(pg_bin)
    made = backup.create(tmp_path / "backups", url=url, layout=layout, tools=tools)
    manifest = made.manifest
    assert manifest["tables"]["tracking_events"]["rows"] == 40 and manifest["schema_version"] == 2
    assert backup.verify(made.path, tools=tools) == []

    target_url = fresh_db_url()
    target = backup.Layout.default(tmp_path / "restored")
    report = backup.restore(
        made.path, url=target_url, layout=target, confirm_database=database_name(target_url), tools=tools
    )
    assert report["matches"] is True
    assert {t: v["match"] for t, v in report["tables"].items()} == {t: True for t in manifest["tables"]}
    assert (target.reports_dir / "cji_report_1.html").read_text(encoding="utf-8") == "<html>r</html>"
    conn = sqlite3.connect(target.checkpoints_db)
    assert conn.execute("SELECT run_id FROM run_index").fetchall() == [("r1",)]
    conn.close()
    restored = runner.engine_for(target_url)
    assert runner.current_version(restored) == 2  # the schema table came back with the data


def test_manifest_and_messages_hold_no_password(source, tmp_path, pg_bin):
    url, layout = source
    made = backup.create(tmp_path / "b", url=url, layout=layout, tools=backup.PgTools.find(pg_bin))
    text_ = (made.path / backup.MANIFEST).read_text(encoding="utf-8")
    parts = urlsplit(url)
    assert parts.password is None or parts.password == "" or parts.password not in text_
    assert "@" not in json.dumps(made.manifest["database"])
    clean, env = backup._split_password("postgresql://u:s3cret-pw@db.example:5432/cji")
    assert "s3cret-pw" not in clean and env["PGPASSWORD"] == "s3cret-pw"


def test_a_changed_member_fails_verification(source, tmp_path, pg_bin):
    url, layout = source
    tools = backup.PgTools.find(pg_bin)
    made = backup.create(tmp_path / "b", url=url, layout=layout, tools=tools)
    (made.path / "files" / "data" / "last_run.json").write_text("{}", encoding="utf-8")
    assert backup.verify(made.path, tools=tools) == ["changed: files/data/last_run.json"]
    with pytest.raises(OpsError, match="does not verify"):
        backup.restore(
            made.path, url=None, layout=backup.Layout.default(tmp_path / "x"), confirm_database=None, tools=tools
        )


def test_restore_refuses_a_non_empty_target_and_a_wrong_name(source, tmp_path, pg_bin):
    url, layout = source
    tools = backup.PgTools.find(pg_bin)
    made = backup.create(tmp_path / "b", url=url, layout=layout, tools=tools)
    fresh = backup.Layout.default(tmp_path / "fresh")
    with pytest.raises(OpsError, match="--confirm-database must be"):
        backup.restore(made.path, url=url, layout=fresh, confirm_database="other", tools=tools)
    with pytest.raises(OpsError, match="not empty"):
        backup.restore(made.path, url=url, layout=fresh, confirm_database=database_name(url), tools=tools)
    with pytest.raises(OpsError, match="target files exist"):
        backup.restore(made.path, url=None, layout=layout, confirm_database=None, tools=tools)


def test_replace_restores_over_changed_data(source, tmp_path, pg_bin):
    url, layout = source
    tools = backup.PgTools.find(pg_bin)
    made = backup.create(tmp_path / "b", url=url, layout=layout, tools=tools)
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tracking_events WHERE event_id < 'e2'"))
    engine.dispose()
    report = backup.restore(
        made.path, url=url, layout=layout, confirm_database=database_name(url), replace=True, tools=tools
    )
    assert report["matches"] is True
    assert report["tables"]["tracking_events"]["restored"]["rows"] == 40


def test_files_only_backup_without_database(tmp_path):
    home = tmp_path / "h"
    (home / "data").mkdir(parents=True)
    (home / "data" / "events.parquet").write_bytes(b"PAR1")
    made = backup.create(tmp_path / "b", url=None, layout=backup.Layout.default(home))
    assert [m["path"] for m in made.manifest["members"]] == ["files/data/events.parquet"]
    assert backup.verify(made.path) == []


def test_missing_tools_are_reported(tmp_path):
    with pytest.raises(OpsError, match="pg_dump not found"):
        backup.PgTools.find(str(tmp_path))
