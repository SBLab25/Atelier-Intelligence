"""Spec 14 (OD-148): `parse_file` reports what ingestion would write; `ingest_file` = parse_file + write_rows."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine, text


def _rows():
    return [
        {"user_id": "u1", "step_id": "landing", "event_type": "page_view", "timestamp": "2026-01-01T00:00:00Z"},
        {"user_id": "u1", "step_id": "signup", "event_type": "drop_off", "timestamp": "2026-01-01T00:01:00Z"},
        {"user_id": "u2", "step_id": "landing", "event_type": "teleport", "timestamp": "2026-01-01T00:02:00Z"},
        {"user_id": "u3", "step_id": "landing", "event_type": "page_view", "timestamp": "yesterday-ish"},
        {"step_id": "landing", "event_type": "page_view"},                                  # no user: skipped
    ]


def test_parse_file_counts(tmp_path):
    from cji.tools.ingest_json import parse_file

    path = tmp_path / "e.json"
    path.write_text(json.dumps(_rows()), encoding="utf-8")
    df, stats = parse_file(path)
    assert stats.format == "JSON array" and stats.parsed == 4 and stats.accepted == 3
    assert stats.dropped_event_type == 1 and stats.repaired_timestamp == 1
    assert sorted(df["step_id"]) == ["landing_page", "landing_page", "sign_up_form"]
    assert "abandon" in set(df["event_type"])                           # alias applied as before


@pytest.mark.parametrize(("name", "content", "fmt"), [
    ("e.csv", "user_id,session_id,step_name,rage_clicks\nu1,s1,landing,2\n", "CSV"),
    ("e.ndjson", '{"user_id": "u1", "step": "landing"}\n{"user_id": "u2", "step": "signup"}\n', "NDJSON"),
    ("e.json", json.dumps({"events": []}), "GA4 clickstream"),
    ("e.json", json.dumps({"payload": {"x": 1}, "records": [{"user_id": "u"}]}), "JSON object (list value)"),
])
def test_parse_file_reports_the_detected_format(tmp_path, name, content, fmt):
    from cji.tools.ingest_json import parse_file

    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    if fmt == "GA4 clickstream":
        with pytest.raises(ValueError):
            parse_file(path)
        return
    _df, stats = parse_file(path)
    assert stats.format == fmt


def test_parse_file_root_key_and_map(tmp_path):
    from cji.tools.ingest_json import parse_file

    path = tmp_path / "e.json"
    path.write_text(json.dumps({"meta": 1, "rows": [{"visitor": "v1", "screen": "home"}],
                                "other": [{"user_id": "z"}]}), encoding="utf-8")
    df, stats = parse_file(path, col_map={"visitor": "user_id"}, root_key="rows")
    assert stats.format == "JSON object (root key)" and list(df["user_id"]) == ["v1"]
    assert list(df["step_id"]) == ["landing_page"]


def test_ingest_file_writes_what_parse_file_accepts(tmp_path, monkeypatch):
    import cji.tools.ingest_json as ij

    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    monkeypatch.setattr(ij, "create_engine", lambda url: engine)
    path = tmp_path / "e.json"
    path.write_text(json.dumps(_rows()), encoding="utf-8")
    _df, stats = ij.parse_file(path)
    _out, written = ij.ingest_file(path, output_path=tmp_path / "unused.parquet")
    assert written == stats.accepted == 3
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tracking_events")).scalar() == 3
    assert ij.main([str(path), "--replace"]) == 0
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tracking_events")).scalar() == 3


def test_write_rows_appends_only_new_event_ids(tmp_path):
    from cji.tools.ingest_json import parse_file, write_rows

    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    path = tmp_path / "e.json"
    path.write_text(json.dumps(_rows()), encoding="utf-8")
    df, _stats = parse_file(path)
    assert write_rows(df, engine=engine) == 3
    assert write_rows(df, engine=engine) == 0                          # same event_ids: nothing new
    assert write_rows(df, replace=True, engine=engine) == 3


def test_parse_file_without_records(tmp_path):
    from cji.tools.ingest_json import parse_file

    path = tmp_path / "e.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="No records"):
        parse_file(path)
