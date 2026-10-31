"""
Spec 05 — event repositories: contract suite (both implementations), parity, and
implementation-specific cases (empty, invalid, failures).

PostgreSQL runs on a throwaway local server only: pgserver on a temporary directory, or
CJI_TEST_DATABASE_URL pointing at a loopback server. Never DATABASE_URL / Supabase.
"""
import ast
import importlib
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from repositories import (
    DuckDbParquetRepository,
    NotSupported,
    PostgresEventRepository,
    RepositoryError,
    TimeWindow,
    event_repository,
)
from repositories import base as repo_base
from repositories import duckdb_parquet as duck_module
from settings import make_test_settings

APP_ROOT = Path(__file__).resolve().parent.parent
JOURNEY = "user_onboarding"
STEPS = ["landing_page", "sign_up_form", "email_verification"]
WINDOW = TimeWindow(days_back=30, minutes_back=60)
INJECTION = "x' OR '1'='1"

# (step, user, event_type, duration_ms, metadata)
FIXTURE = [
    ("landing_page", "u1", "page_view", 1000, {}),
    ("landing_page", "u2", "page_view", 2000, {}),
    ("landing_page", "u3", "page_view", 3000, {}),
    ("landing_page", "u4", "page_view", 4000, {}),
    ("landing_page", "u1", "step_complete", 500, {}),
    ("landing_page", "u2", "step_complete", 500, {}),
    ("landing_page", "u3", "abandon", 0, {}),
    ("landing_page", "u4", "rage_click", 0, {"clicks": 4}),
    ("sign_up_form", "u1", "page_view", 1000, {}),
    ("sign_up_form", "u2", "page_view", 3000, {}),
    ("sign_up_form", "u1", "error", 0, {"retry_count": 2}),
    ("sign_up_form", "u2", "error", 0, {"retry_count": 4}),
    ("sign_up_form", "u1", "step_complete", 0, {}),
    ("email_verification", "u1", "page_view", 6000, {}),
    ("email_verification", "u1", "abandon", 0, {}),
]
EXPECTED_METRICS = [
    {"step_id": "email_verification", "unique_users": 1, "completion_rate_pct": 0.0, "abandon_rate_pct": 100.0,
     "error_rate_pct": 0.0, "avg_dwell_ms": 6000.0, "avg_rage_clicks": 0.0, "avg_retries": 0.0},
    {"step_id": "landing_page", "unique_users": 4, "completion_rate_pct": 50.0, "abandon_rate_pct": 25.0,
     "error_rate_pct": 0.0, "avg_dwell_ms": 1833.0, "avg_rage_clicks": 0.25, "avg_retries": 0.0},
    {"step_id": "sign_up_form", "unique_users": 2, "completion_rate_pct": 50.0, "abandon_rate_pct": 0.0,
     "error_rate_pct": 100.0, "avg_dwell_ms": 1333.0, "avg_rage_clicks": 0.0, "avg_retries": 3.0},
]
EXPECTED_FUNNEL = [
    {"step_id": "landing_page", "users": 4, "drop_off_pct": 50.0},
    {"step_id": "sign_up_form", "users": 2, "drop_off_pct": 50.0},
    {"step_id": "email_verification", "users": 1, "drop_off_pct": 0.0},
]


def fixture_frame(rows=FIXTURE, *, minutes_ago=5):
    """Stored-event rows (EventRecord layout) as the tracked Parquet and ingest_json store them."""
    now = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    data = [{
        "event_id": f"evt-{i:04d}-{uuid.uuid4().hex[:8]}",
        "user_id": user, "session_id": f"s-{user}", "journey_id": JOURNEY, "step_id": step,
        "event_type": etype, "timestamp": now - timedelta(seconds=i), "duration_ms": duration,
        "url": f"https://app.example.test/{step}", "metadata": json.dumps(meta),
    } for i, (step, user, etype, duration, meta) in enumerate(rows)]
    df = pd.DataFrame(data, columns=list(repo_base.EVENT_COLUMNS))
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["duration_ms"] = df["duration_ms"].astype("int64")
    return df


def records_of(df):
    out = []
    for row in df.to_dict(orient="records"):
        out.append({**row, "timestamp": row["timestamp"].isoformat(), "duration_ms": int(row["duration_ms"])})
    return out


# ── PostgreSQL server (session) ───────────────────────────────────────────────

# pg_url (pgserver or a loopback CJI_TEST_DATABASE_URL) is shared from conftest.py (Spec 07, OD-51).


@pytest.fixture
def pg_engine(pg_url):
    engine = create_engine(pg_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS tracking_events, live_events, api_keys"))
    yield engine
    engine.dispose()


def create_live_tables(engine, monkeypatch):
    """live_events / api_keys exactly as the collector creates them at startup."""
    collector_api = importlib.import_module("collector.api")
    monkeypatch.setattr(collector_api, "engine", engine)
    monkeypatch.setattr(collector_api, "CJI_ENV", "production")
    collector_api._create_tables()


def load_postgres(engine, monkeypatch, df):
    create_live_tables(engine, monkeypatch)
    df.to_sql("tracking_events", engine, if_exists="replace", index=False)   # ingest_json layout


def load_parquet(path, df):
    df.to_parquet(path, index=False)
    return path


@pytest.fixture
def shared_frame():
    """One fixture dataset per test, loaded into whichever stores the test uses (parity)."""
    return fixture_frame()


@pytest.fixture
def demo_repo(tmp_path, shared_frame):
    repo = DuckDbParquetRepository(load_parquet(tmp_path / "events.parquet", shared_frame))
    yield repo
    repo.close()


@pytest.fixture
def pg_repo(pg_engine, pg_url, monkeypatch, shared_frame):
    load_postgres(pg_engine, monkeypatch, shared_frame)
    repo = PostgresEventRepository(pg_url)
    yield repo
    repo.close()


@pytest.fixture(params=["demo", "realtime"])
def repo(request):
    return request.getfixturevalue("demo_repo" if request.param == "demo" else "pg_repo")


# ═════════════════════════════════════════════════════════════════════════════
# Contract suite — both implementations
# ═════════════════════════════════════════════════════════════════════════════

def test_contract_health(repo):
    repo.health()


def test_contract_step_metrics(repo):
    assert repo.step_metrics(JOURNEY, WINDOW) == EXPECTED_METRICS
    for row in repo.step_metrics(JOURNEY, WINDOW):
        assert isinstance(row["unique_users"], int)
        assert all(isinstance(row[k], float) for k in row if k not in ("step_id", "unique_users"))


def test_contract_funnel(repo):
    assert repo.funnel(JOURNEY, STEPS, WINDOW) == EXPECTED_FUNNEL


def test_contract_unknown_steps_sort_last(repo):
    order = [r["step_id"] for r in repo.funnel(JOURNEY, ["sign_up_form"], WINDOW)]
    assert order[0] == "sign_up_form" and set(order) == set(STEPS)


def test_contract_events_order_limit_and_filters(repo):
    sample = repo.events(JOURNEY, limit=5, step_id=None, event_type=None)
    assert len(sample) == 5
    stamps = [pd.Timestamp(e["timestamp"]) for e in sample]
    assert stamps == sorted(stamps, reverse=True)
    assert len(repo.events(JOURNEY, limit=100, step_id="sign_up_form", event_type=None)) == 5
    errors = repo.events(JOURNEY, limit=100, step_id=None, event_type="error")
    assert [json.loads(e["metadata"])["retry_count"] for e in errors] == [2, 4]
    assert repo.events(JOURNEY, limit=100, step_id="sign_up_form", event_type="abandon") == []


def test_contract_values_are_bound_not_interpolated(repo):
    assert repo.events(JOURNEY, limit=100, step_id=INJECTION, event_type=None) == []
    assert repo.events(INJECTION, limit=100, step_id=None, event_type=INJECTION) == []
    assert repo.step_metrics("o'brien", WINDOW) == []
    assert max(r["users"] for r in repo.funnel(JOURNEY, ["a'b", "c"], WINDOW)) == 4   # unknown steps tie


def test_contract_unknown_journey_is_empty(repo):
    assert repo.step_metrics("no_such_journey", WINDOW) == []
    assert repo.funnel("no_such_journey", STEPS, WINDOW) == []


def test_contract_append_is_idempotent(repo):
    records = records_of(fixture_frame(FIXTURE[:3]))
    first = repo.append_events(records)
    second = repo.append_events(records)
    assert (first.written, first.duplicates) == (3, 0)
    assert (second.written, second.duplicates) == (0, 3)
    assert len(repo.events(JOURNEY, limit=1000, step_id=None, event_type=None)) == len(FIXTURE) + 3


def test_contract_duplicates_inside_one_batch_collapse(repo):
    records = records_of(fixture_frame(FIXTURE[:2]))
    result = repo.append_events([records[0], records[0], records[1]])
    assert (result.written, result.duplicates) == (2, 1)


def test_contract_invalid_records_write_nothing(repo):
    good = records_of(fixture_frame(FIXTURE[:2]))
    bad = {**good[1], "event_type": "scroll"}
    with pytest.raises(RepositoryError, match="invalid event record"):
        repo.append_events([good[0], bad])
    assert len(repo.events(JOURNEY, limit=1000, step_id=None, event_type=None)) == len(FIXTURE)


def test_contract_empty_batch(repo):
    result = repo.append_events([])
    assert (result.written, result.duplicates) == (0, 0)


# ═════════════════════════════════════════════════════════════════════════════
# Parity — the same fixture through both implementations
# ═════════════════════════════════════════════════════════════════════════════

COMMON_EVENT_KEYS = ("user_id", "session_id", "journey_id", "step_id", "event_type", "duration_ms", "metadata")


def test_parity_between_demo_and_realtime(demo_repo, pg_repo):
    assert demo_repo.step_metrics(JOURNEY, WINDOW) == pg_repo.step_metrics(JOURNEY, WINDOW)
    assert demo_repo.funnel(JOURNEY, STEPS, WINDOW) == pg_repo.funnel(JOURNEY, STEPS, WINDOW)
    for step_id, event_type in [(None, None), ("landing_page", None), (None, "error")]:
        demo = demo_repo.events(JOURNEY, limit=100, step_id=step_id, event_type=event_type)
        live = pg_repo.events(JOURNEY, limit=100, step_id=step_id, event_type=event_type)
        assert [{k: e[k] for k in COMMON_EVENT_KEYS} for e in demo] == \
               [{k: e[k] for k in COMMON_EVENT_KEYS} for e in live]
        assert [pd.Timestamp(e["timestamp"]) for e in demo] == [pd.Timestamp(e["timestamp"]) for e in live]


def test_parity_on_an_empty_store(tmp_path, pg_engine, pg_url, monkeypatch):
    empty = fixture_frame([])
    demo = DuckDbParquetRepository(load_parquet(tmp_path / "events.parquet", empty))
    load_postgres(pg_engine, monkeypatch, fixture_frame(FIXTURE[:1]))
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM tracking_events"))
    live = PostgresEventRepository(pg_url)
    try:
        for r in (demo, live):
            r.health()
            assert r.step_metrics(JOURNEY, WINDOW) == []
            assert r.funnel(JOURNEY, STEPS, WINDOW) == []
            assert r.events(JOURNEY, limit=10, step_id=None, event_type=None) == []
    finally:
        demo.close()
        live.close()


# ═════════════════════════════════════════════════════════════════════════════
# DuckDB / Parquet (demo)
# ═════════════════════════════════════════════════════════════════════════════

def test_demo_missing_parquet(tmp_path):
    repo = DuckDbParquetRepository(tmp_path / "missing.parquet")
    with pytest.raises(RepositoryError, match="events.parquet not found"):
        repo.health()
    with pytest.raises(RepositoryError, match="events.parquet not found"):
        repo.step_metrics(JOURNEY, WINDOW)


def test_demo_corrupt_parquet(tmp_path):
    path = tmp_path / "events.parquet"
    path.write_bytes(b"this is not parquet")
    with pytest.raises(RepositoryError):
        DuckDbParquetRepository(path).health()


def test_demo_live_snapshot_is_not_supported(demo_repo):
    with pytest.raises(NotSupported, match="only available in realtime mode"):
        demo_repo.live_snapshot(15)


def test_demo_window_is_reported_but_not_applied(tmp_path):
    old = DuckDbParquetRepository(load_parquet(tmp_path / "events.parquet", fixture_frame(minutes_ago=60 * 24 * 90)))
    assert old.step_metrics(JOURNEY, TimeWindow(days_back=1)) == EXPECTED_METRICS     # F-10: kept as-is
    assert old.window_fields(TimeWindow(days_back=7, minutes_back=5)) == (7, None)
    old.close()


def test_demo_write_is_atomic(tmp_path, monkeypatch):
    path = load_parquet(tmp_path / "events.parquet", fixture_frame())
    before = path.read_bytes()

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(duck_module.os, "replace", broken_replace)
    with pytest.raises(RepositoryError, match="disk full"):
        DuckDbParquetRepository(path).append_events(records_of(fixture_frame(FIXTURE[:2])))
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["events.parquet"]


def test_demo_write_creates_the_file_and_keeps_types(tmp_path):
    path = tmp_path / "new" / "events.parquet"
    repo = DuckDbParquetRepository(path)
    assert repo.append_events(records_of(fixture_frame())).written == len(FIXTURE)
    stored = pd.read_parquet(path)
    assert str(stored["timestamp"].dtype).startswith("datetime64") and stored["duration_ms"].dtype == "int64"
    assert repo.step_metrics(JOURNEY, WINDOW) == EXPECTED_METRICS


def test_demo_never_builds_a_database_engine(demo_repo, monkeypatch):
    import sqlalchemy

    def no_engine(*args, **kwargs):
        raise AssertionError("demo repository asked for a database engine")

    monkeypatch.setattr(sqlalchemy, "create_engine", no_engine)
    demo_repo.health()
    demo_repo.step_metrics(JOURNEY, WINDOW)
    demo_repo.funnel(JOURNEY, STEPS, WINDOW)
    demo_repo.events(JOURNEY, limit=5, step_id=None, event_type=None)
    demo_repo.append_events(records_of(fixture_frame(FIXTURE[:1])))


# ═════════════════════════════════════════════════════════════════════════════
# PostgreSQL (realtime)
# ═════════════════════════════════════════════════════════════════════════════

def test_realtime_unreachable_database_hides_credentials():
    repo = PostgresEventRepository("postgresql://cji:s3cret-pw@127.0.0.1:1/cji")
    for call in (repo.health, lambda: repo.step_metrics(JOURNEY, WINDOW),
                 lambda: repo.append_events(records_of(fixture_frame(FIXTURE[:1])))):
        with pytest.raises(RepositoryError) as exc:
            call()
        assert "s3cret-pw" not in str(exc.value)


def test_realtime_missing_tables_are_named(pg_engine, pg_url):
    repo = PostgresEventRepository(pg_url)
    with pytest.raises(RepositoryError, match="tracking_events, live_events"):
        repo.health()
    with pytest.raises(RepositoryError, match="tracking_events"):
        repo.step_metrics(JOURNEY, WINDOW)
    with pytest.raises(RepositoryError, match="tracking_events does not exist"):
        repo.append_events(records_of(fixture_frame(FIXTURE[:1])))
    repo.close()


def test_realtime_window_excludes_old_events(pg_engine, pg_url, monkeypatch):
    frame = pd.concat([fixture_frame(), fixture_frame(FIXTURE[:4], minutes_ago=180)], ignore_index=True)
    load_postgres(pg_engine, monkeypatch, frame)
    repo = PostgresEventRepository(pg_url)
    assert repo.step_metrics(JOURNEY, TimeWindow(minutes_back=60)) == EXPECTED_METRICS
    assert repo.window_fields(TimeWindow(days_back=30, minutes_back=0)) == (None, 60)
    repo.close()


def test_realtime_reads_live_events_too(pg_repo, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO live_events (timestamp, event_id, session_id, user_id, journey_name, step_id, "
            "event_type, url, element_selectors, metadata) VALUES (NOW(), 'live-1', 's9', 'u9', :j, "
            "'landing_page', 'page_view', '', NULL, CAST('{}' AS JSONB))"), {"j": JOURNEY})
    landing = next(r for r in pg_repo.step_metrics(JOURNEY, WINDOW) if r["step_id"] == "landing_page")
    assert landing["unique_users"] == 5
    snapshot = pg_repo.live_snapshot(15)
    assert snapshot.total_events == 1 and snapshot.steps[0]["step_id"] == "landing_page"
    assert snapshot.snapshot_at is not None


def test_realtime_write_rolls_back_the_whole_batch(pg_repo, monkeypatch):
    calls = {"n": 0}
    original = PostgresEventRepository._insert_one

    def failing_second(self, conn, record):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OperationalError("INSERT", {}, Exception("connection lost"))
        return original(self, conn, record)

    monkeypatch.setattr(PostgresEventRepository, "_insert_one", failing_second)
    with pytest.raises(RepositoryError, match="connection lost"):
        pg_repo.append_events(records_of(fixture_frame(FIXTURE[:3])))
    assert len(pg_repo.events(JOURNEY, limit=1000, step_id=None, event_type=None)) == len(FIXTURE)


def test_realtime_writes_go_to_tracking_events(pg_repo, pg_engine):
    result = pg_repo.append_events(records_of(fixture_frame(FIXTURE[:2])))
    assert result.destination == "postgresql://tracking_events"
    with pg_engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tracking_events")).scalar() == len(FIXTURE) + 2
        assert conn.execute(text("SELECT COUNT(*) FROM live_events")).scalar() == 0


def test_realtime_never_touches_demo_storage(tmp_path, pg_repo):
    settings = make_test_settings(tmp_path, CJI_MODE="realtime", DATABASE_URL=pg_repo._url)
    repo = event_repository(settings)
    assert isinstance(repo, PostgresEventRepository)
    repo.health()
    repo.step_metrics(JOURNEY, WINDOW)
    repo.append_events(records_of(fixture_frame(FIXTURE[:1])))
    repo.close()
    assert not (tmp_path / "data").exists()
    assert not hasattr(repo, "parquet_path")


# ═════════════════════════════════════════════════════════════════════════════
# Selection and isolation
# ═════════════════════════════════════════════════════════════════════════════

def test_factory_selects_once_from_the_configured_mode(tmp_path):
    demo = event_repository(make_test_settings(tmp_path))
    assert isinstance(demo, DuckDbParquetRepository)
    assert demo.parquet_path == tmp_path / "data" / "events.parquet"
    realtime = event_repository(make_test_settings(tmp_path, CJI_MODE="realtime", DATABASE_URL="postgresql://u@127.0.0.1:1/x"))
    assert isinstance(realtime, PostgresEventRepository)


def test_factory_requires_a_database_for_realtime(tmp_path):
    from settings import ConfigError

    with pytest.raises(ConfigError, match="DATABASE_URL"):
        event_repository(make_test_settings(tmp_path, CJI_MODE="realtime"))


def _imports(path):
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add((node.module or "").split(".")[0])
    return names


def test_implementations_cannot_reach_the_other_store():
    pkg = APP_ROOT / "repositories"
    assert "sqlalchemy" not in _imports(pkg / "duckdb_parquet.py")
    assert "duckdb" not in _imports(pkg / "postgres.py")
    assert "parquet" not in (pkg / "postgres.py").read_text(encoding="utf-8").lower()


def test_repository_package_dependencies():
    allowed = set(sys.stdlib_module_names) | {"pandas", "duckdb", "sqlalchemy", "pydantic", "domain", "settings"}
    for path in sorted((APP_ROOT / "repositories").glob("*.py")):
        assert _imports(path) <= allowed, path.name


def test_rendered_sql_contains_no_values():
    from repositories import queries as q

    for sql in (q.step_metrics_sql(q.POSTGRES, q.realtime_source(INJECTION)),
                q.funnel_sql(q.DUCKDB, q.DEMO_SOURCE), q.events_sql(q.POSTGRES, q.realtime_source(JOURNEY))):
        assert INJECTION not in sql and JOURNEY not in sql
    assert q.realtime_source(q.LIVE_ONLY_LABEL).count("FROM live_events") == 1

