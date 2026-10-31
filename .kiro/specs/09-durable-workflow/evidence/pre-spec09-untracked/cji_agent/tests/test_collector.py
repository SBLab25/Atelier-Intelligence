"""
Spec 07 — durable, authenticated collector (design §7).

PostgreSQL-backed cases run on a throwaway local server only (the shared `pg_url` fixture in
conftest.py: pgserver on a temporary directory, or a loopback CJI_TEST_DATABASE_URL).
Never DATABASE_URL / Supabase.
"""
import importlib
import json
import logging
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from settings import ConfigError

GOOD_ADMIN = "a" * 40
ACTIVE_KEY = "cji_test_active_0001"
INACTIVE_KEY = "cji_test_inactive_0001"
OTHER_KEY = "cji_test_checkout_0001"
JOURNEY = "user_onboarding"
DEAD_URL = "postgresql://nobody:nothing@127.0.0.1:1/none"
UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def wire(event_id, **over):
    """One event exactly as tracker.js makeEvent() sends it (wire format v1)."""
    return {
        "timestamp": "2026-10-27T10:15:30.123Z",
        "event_id": event_id,
        "session_id": "sess-1234abcd",
        "user_id": "user-5678efgh",
        "journey_name": JOURNEY,
        "step_id": "sign_up_form",
        "event_type": "click",
        "url": "https://app.example.test/signup?email=a%40b.example",
        "element_selectors": "button#submit",
        "metadata": {"button": "submit"},
        **over,
    }


def ids(prefix, n):
    return [f"evt-{prefix}-{i:04d}-0000" for i in range(n)]


def batch(*events, key=ACTIVE_KEY):
    return {"api_key": key, "events": list(events)}


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def api():
    return importlib.import_module("collector.api")


class Collector:
    """The collector app bound to a disposable PostgreSQL database."""

    def __init__(self, api, engine):
        self.api = api
        self.engine = engine
        self.client = TestClient(api.app, raise_server_exceptions=False)

    def post(self, body, headers=None):
        return self.client.post("/collect/batch", json=body, headers=headers or {})

    def rows(self):
        with self.engine.connect() as conn:
            return list(conn.execute(text("SELECT event_id FROM live_events ORDER BY event_id")).scalars())

    def execute(self, sql):
        with self.engine.begin() as conn:
            conn.execute(text(sql))


@pytest.fixture
def collector(api, pg_url, monkeypatch):
    engine = api._make_engine(pg_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS live_events, api_keys"))
        conn.execute(text("DROP FUNCTION IF EXISTS cji_test_refuse_commit()"))
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(api, "CJI_ENV", "production")
    api._create_tables()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO api_keys (api_key, journey_name, description, is_active) VALUES "
                 "(:a, :j, 'test', true), (:i, :j, 'test', false), (:o, 'checkout', 'test', true)"),
            {"a": ACTIVE_KEY, "i": INACTIVE_KEY, "o": OTHER_KEY, "j": JOURNEY},
        )
    yield Collector(api, engine)
    engine.dispose()


def without_database(api, monkeypatch, engine):
    monkeypatch.setattr(api, "engine", engine)
    return TestClient(api.app, raise_server_exceptions=False)


# ═════════════════════════════════════════════════════════════════════════════
# Authentication
# ═════════════════════════════════════════════════════════════════════════════

def test_missing_api_key_is_422(collector):
    res = collector.post({"events": [wire(ids("nokey", 1)[0])]})
    assert res.status_code == 422
    assert collector.rows() == []


def test_short_api_key_is_422(collector):
    assert collector.post(batch(wire(ids("short", 1)[0]), key="short")).status_code == 422


@pytest.mark.parametrize("key", ["cji_test_unknown_0001", INACTIVE_KEY])
def test_unknown_or_inactive_key_is_401(collector, key):
    res = collector.post(batch(wire(ids("badkey", 1)[0]), key=key))
    assert res.status_code == 401
    assert res.json()["status"] == "rejected"
    assert key not in res.text
    assert collector.rows() == []


def test_header_key_must_match_body_key(collector):
    event = wire(ids("hdr", 1)[0])
    assert collector.post(batch(event), headers={"X-CJI-Key": OTHER_KEY}).status_code == 401
    assert collector.rows() == []
    assert collector.post(batch(event), headers={"X-CJI-Key": ACTIVE_KEY}).status_code == 200
    assert collector.rows() == [event["event_id"]]


def test_development_seeds_the_dev_key_for_the_configured_journey(collector, monkeypatch):
    from settings.model import DEV_TRACKER_KEY

    def dev_rows():
        with collector.engine.connect() as conn:
            return conn.execute(text("SELECT journey_name FROM api_keys WHERE api_key = :k"),
                                {"k": DEV_TRACKER_KEY}).fetchall()

    assert dev_rows() == []                                   # production: never seeded
    monkeypatch.setattr(collector.api, "CJI_ENV", "development")
    monkeypatch.setattr(collector.api, "JOURNEY_NAME", JOURNEY)
    collector.api._create_tables()
    assert [r[0] for r in dev_rows()] == [JOURNEY]
    assert collector.post(batch(wire(ids("dev", 1)[0]), key=DEV_TRACKER_KEY)).status_code == 200


# ═════════════════════════════════════════════════════════════════════════════
# Authorization
# ═════════════════════════════════════════════════════════════════════════════

def test_events_for_another_journey_are_rejected_per_event(collector):
    mine, theirs = ids("authz", 2)
    res = collector.post(batch(wire(mine, journey_name="checkout"), wire(theirs), key=OTHER_KEY))
    assert res.status_code == 207
    body = res.json()
    assert (body["accepted"], body["rejected"]) == (1, 1)
    assert body["errors"] == [{"index": 1, "event_id": theirs, "reason": "journey_not_authorized",
                               "fields": ["journey_id"]}]
    assert collector.rows() == [mine]


def test_live_stats_requires_the_admin_key(collector, monkeypatch):
    monkeypatch.setattr(collector.api, "CJI_ADMIN_KEY", GOOD_ADMIN)
    collector.post(batch(*[wire(i) for i in ids("stats", 3)]))
    client = collector.client
    assert client.get("/live/stats?minutes=43200").status_code == 403
    assert client.get("/live/stats?minutes=43200", headers={"X-CJI-Admin-Key": "b" * 40}).status_code == 403
    res = client.get("/live/stats?minutes=43200", headers={"X-CJI-Admin-Key": GOOD_ADMIN})
    assert res.status_code == 200
    assert res.json()["stats"] == [{"step": "sign_up_form", "count": 3}]


def test_live_stats_is_closed_while_the_admin_key_is_a_default(collector, monkeypatch):
    monkeypatch.setattr(collector.api, "CJI_ADMIN_KEY", "change-me-in-production")
    res = collector.client.get("/live/stats", headers={"X-CJI-Admin-Key": "change-me-in-production"})
    assert res.status_code == 403


def test_admin_key_creation_validates_the_journey(collector, monkeypatch):
    monkeypatch.setattr(collector.api, "CJI_ADMIN_KEY", GOOD_ADMIN)
    headers = {"X-CJI-Admin-Key": GOOD_ADMIN}
    bad = collector.client.post("/admin/api-keys", json={"journey_name": "  ", "description": "d"}, headers=headers)
    assert bad.status_code == 422
    ok = collector.client.post("/admin/api-keys", json={"journey_name": JOURNEY, "description": "d"},
                               headers=headers)
    assert ok.status_code == 200
    key = ok.json()["api_key"]
    assert collector.post(batch(wire(ids("newkey", 1)[0]), key=key)).status_code == 200


# ═════════════════════════════════════════════════════════════════════════════
# Limits
# ═════════════════════════════════════════════════════════════════════════════

def test_body_over_the_limit_is_413_by_content_length(collector, monkeypatch):
    monkeypatch.setattr(collector.api, "MAX_BODY_BYTES", 4096)
    res = collector.post(batch(*[wire(i) for i in ids("big", 40)]))
    assert res.status_code == 413
    assert collector.rows() == []


def test_body_over_the_limit_is_413_when_streamed(collector, monkeypatch):
    monkeypatch.setattr(collector.api, "MAX_BODY_BYTES", 4096)
    raw = json.dumps(batch(*[wire(i) for i in ids("stream", 40)])).encode()
    chunks = iter([raw[:3000], raw[3000:]])
    res = collector.client.post("/collect/batch", content=chunks, headers={"Content-Type": "application/json"})
    assert res.status_code == 413
    assert collector.rows() == []


@pytest.mark.parametrize("count", [0, 101])
def test_event_count_outside_1_to_100_is_422(collector, count):
    res = collector.post(batch(*[wire(i) for i in ids("count", count)]))
    assert res.status_code == 422
    assert collector.rows() == []


def test_oversize_metadata_url_and_selector_are_rejected_per_event(collector):
    ok, meta, url, sel = ids("size", 4)
    res = collector.post(batch(
        wire(ok),
        wire(meta, metadata={"blob": "x" * 9000}),
        wire(url, url="https://app.example.test/" + "p" * 3000),
        wire(sel, element_selectors="div " * 200),
    ))
    assert res.status_code == 207
    errors = res.json()["errors"]
    assert [(e["index"], e["fields"]) for e in errors] == [(1, ["metadata"]), (2, ["url"]), (3, ["element_selectors"])]
    assert "xxxx" not in res.text and "pppp" not in res.text
    assert collector.rows() == [ok]


# ═════════════════════════════════════════════════════════════════════════════
# Rate limits
# ═════════════════════════════════════════════════════════════════════════════

def test_per_key_rate_limit_returns_429_with_retry_after(collector, monkeypatch):
    from collector.security import RateLimiter

    clock = FakeClock()
    monkeypatch.setattr(collector.api, "KEY_LIMITER", RateLimiter(2, clock=clock))
    first, second, third = ids("rate", 3)
    assert collector.post(batch(wire(first))).status_code == 200
    assert collector.post(batch(wire(second))).status_code == 200
    limited = collector.post(batch(wire(third)))
    assert limited.status_code == 429
    assert 1 <= int(limited.headers["Retry-After"]) <= 30
    assert limited.json()["retryable"] is True
    assert collector.post(batch(wire(third), key=OTHER_KEY)).status_code != 429   # other key, own bucket
    clock.now += 30
    assert collector.post(batch(wire(third))).status_code == 200
    assert collector.rows() == sorted([first, second, third])


def test_per_address_rate_limit_returns_429(collector, monkeypatch):
    from collector.security import RateLimiter

    clock = FakeClock()
    monkeypatch.setattr(collector.api, "IP_LIMITER", RateLimiter(1, clock=clock))
    first, second = ids("iprate", 2)
    assert collector.post(batch(wire(first))).status_code == 200
    res = collector.post(batch(wire(second), key=OTHER_KEY))
    assert res.status_code == 429 and "Retry-After" in res.headers
    assert collector.rows() == [first]


def test_admin_requests_are_rate_limited_per_address(collector, monkeypatch):
    from collector.security import RateLimiter

    monkeypatch.setattr(collector.api, "CJI_ADMIN_KEY", GOOD_ADMIN)
    monkeypatch.setattr(collector.api, "ADMIN_LIMITER", RateLimiter(1, clock=FakeClock()))
    headers = {"X-CJI-Admin-Key": "wrong" * 8}
    assert collector.client.get("/live/stats", headers=headers).status_code == 403
    res = collector.client.get("/live/stats", headers={"X-CJI-Admin-Key": GOOD_ADMIN})
    assert res.status_code == 429 and "Retry-After" in res.headers


def test_rate_limiter_refills_over_time():
    from collector.security import RateLimiter

    clock = FakeClock()
    limiter = RateLimiter(60, clock=clock)              # one token per second
    assert all(limiter.check("k") is None for _ in range(60))
    wait = limiter.check("k")
    assert wait is not None and 0 < wait <= 1
    clock.now += 1
    assert limiter.check("k") is None
    assert limiter.check("other") is None


def test_client_address_trusts_forwarded_for_only_with_proxy_hops():
    from collector.security import client_address

    xff = "203.0.113.9, 198.51.100.7"
    assert client_address("10.0.0.5", xff, 0) == "10.0.0.5"
    assert client_address("10.0.0.5", xff, 1) == "198.51.100.7"
    assert client_address("10.0.0.5", xff, 2) == "203.0.113.9"
    assert client_address("10.0.0.5", xff, 3) == "10.0.0.5"
    assert client_address("10.0.0.5", None, 1) == "10.0.0.5"
    assert client_address(None, None, 0) == "unknown"


def test_key_fingerprint_is_short_and_does_not_contain_the_key():
    from collector.security import key_fingerprint

    fp = key_fingerprint(ACTIVE_KEY)
    assert re.fullmatch(r"[0-9a-f]{8}", fp)
    assert fp == key_fingerprint(ACTIVE_KEY) != key_fingerprint(OTHER_KEY)


# ═════════════════════════════════════════════════════════════════════════════
# Content types
# ═════════════════════════════════════════════════════════════════════════════

def test_beacon_text_plain_json_is_stored(collector):
    event = wire(ids("beacon", 1)[0], event_type="abandon")
    res = collector.client.post("/collect/batch", content=json.dumps(batch(event)),
                                headers={"Content-Type": "text/plain;charset=UTF-8"})
    assert res.status_code == 200
    assert collector.rows() == [event["event_id"]]


@pytest.mark.parametrize("content_type", ["text/html", None])
def test_other_content_types_are_415(collector, content_type):
    headers = {"Content-Type": content_type} if content_type else {}
    res = collector.client.post("/collect/batch", content=json.dumps(batch(wire(ids("ct", 1)[0]))),
                                headers=headers)
    assert res.status_code == 415
    assert collector.rows() == []


def test_invalid_json_is_400(collector):
    res = collector.client.post("/collect/batch", content=b'{"api_key": "x', headers={"Content-Type": "application/json"})
    assert res.status_code == 400
    assert res.json()["status"] == "rejected"


# ═════════════════════════════════════════════════════════════════════════════
# Idempotency
# ═════════════════════════════════════════════════════════════════════════════

def test_retrying_a_batch_stores_each_event_once(collector):
    events = [wire(i) for i in ids("retry", 5)]
    first = collector.post(batch(*events))
    assert first.status_code == 200
    assert {k: first.json()[k] for k in ("status", "received", "accepted", "duplicates", "rejected")} == \
        {"status": "stored", "received": 5, "accepted": 5, "duplicates": 0, "rejected": 0}
    again = collector.post(batch(*events))
    assert again.status_code == 200
    assert {k: again.json()[k] for k in ("status", "accepted", "duplicates")} == \
        {"status": "stored", "accepted": 0, "duplicates": 5}
    assert collector.rows() == sorted(e["event_id"] for e in events)


def test_repeats_inside_one_batch_are_duplicates(collector):
    event = wire(ids("repeat", 1)[0])
    res = collector.post(batch(event, event, {**event, "step_id": "other_step"}))
    body = res.json()
    assert res.status_code == 200
    assert (body["accepted"], body["duplicates"], body["rejected"]) == (1, 2, 0)
    with collector.engine.connect() as conn:
        step = conn.execute(text("SELECT step_id FROM live_events")).scalar_one()
    assert step == "sign_up_form"                                             # first occurrence wins


def test_collect_writes_one_statement_per_batch(collector):
    statements = []

    from sqlalchemy import event as sa_event

    def record(conn, cursor, statement, params, context, executemany):
        if "live_events" in statement and statement.lstrip().upper().startswith("INSERT"):
            statements.append(statement)

    sa_event.listen(collector.engine, "before_cursor_execute", record)
    try:
        assert collector.post(batch(*[wire(i) for i in ids("one", 20)])).status_code == 200
    finally:
        sa_event.remove(collector.engine, "before_cursor_execute", record)
    assert len(statements) == 1
    assert "ON CONFLICT" in statements[0].upper() and "RETURNING" in statements[0].upper()
    assert len(collector.rows()) == 20


# ═════════════════════════════════════════════════════════════════════════════
# Partial batches
# ═════════════════════════════════════════════════════════════════════════════

def test_mixed_batch_is_207_with_exact_counts_and_indexes(collector):
    a, bad, foreign, d = ids("mix", 4)
    events = [wire(a), wire(bad, event_type="scroll"), wire(foreign, journey_name="checkout"), wire(a), wire(d),
              {"event_type": "click"}, "not-an-event"]
    res = collector.post(batch(*events))
    assert res.status_code == 207
    body = res.json()
    assert {k: body[k] for k in ("status", "received", "accepted", "duplicates", "rejected")} == \
        {"status": "partial", "received": 7, "accepted": 2, "duplicates": 1, "rejected": 4}
    errors = body["errors"]
    assert [e["index"] for e in errors] == [1, 2, 5, 6]
    assert errors[0] == {"index": 1, "event_id": bad, "reason": "invalid", "fields": ["event_type"]}
    assert errors[1] == {"index": 2, "event_id": foreign, "reason": "journey_not_authorized", "fields": ["journey_id"]}
    assert errors[2]["reason"] == "invalid" and "event_id" not in errors[2] and "event_id" in errors[2]["fields"]
    assert errors[3]["reason"] == "invalid" and "event_id" not in errors[3]
    assert "scroll" not in res.text and "not-an-event" not in res.text
    assert collector.rows() == sorted([a, d])

    again = collector.post(batch(*events))
    assert again.status_code == 207
    assert (again.json()["accepted"], again.json()["duplicates"], again.json()["rejected"]) == (0, 3, 4)
    assert collector.rows() == sorted([a, d])


def test_all_invalid_batch_is_422_and_stores_nothing(collector):
    res = collector.post(batch(*[wire(i, event_type="scroll") for i in ids("allbad", 3)]))
    assert res.status_code == 422
    body = res.json()
    assert (body["status"], body["accepted"], body["rejected"]) == ("rejected", 0, 3)
    assert collector.rows() == []


# ═════════════════════════════════════════════════════════════════════════════
# Durability — failed persistence is never reported as stored
# ═════════════════════════════════════════════════════════════════════════════

def assert_failed(res, received):
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "failed" and body["accepted"] == 0 and body["retryable"] is True
    assert body["received"] == received
    assert "Retry-After" in res.headers
    assert "stored" not in json.dumps(body).replace("not stored", "")


def test_unreachable_database_is_503(api, monkeypatch):
    engine = create_engine(DEAD_URL)
    client = without_database(api, monkeypatch, engine)
    res = client.post("/collect/batch", json=batch(wire(ids("dead", 1)[0])))
    assert_failed(res, 1)
    assert "nothing" not in res.text and "127.0.0.1" not in res.text
    engine.dispose()


def test_unconfigured_database_is_503(api, monkeypatch):
    client = without_database(api, monkeypatch, api.UnconfiguredDatabase())
    assert_failed(client.post("/collect/batch", json=batch(wire(ids("nodb", 1)[0]))), 1)


def test_insert_failure_is_503_and_stores_nothing(collector):
    collector.execute("ALTER TABLE live_events ADD CONSTRAINT cji_test_no_boom CHECK (step_id <> 'boom_step')")
    good, boom = ids("insfail", 2)
    res = collector.post(batch(wire(good), wire(boom, step_id="boom_step")))
    assert_failed(res, 2)
    assert collector.rows() == []                     # one transaction: the valid event is not kept either


def test_missing_table_is_503(collector):
    collector.execute("DROP TABLE live_events")
    assert_failed(collector.post(batch(wire(ids("notable", 1)[0]))), 1)


def test_commit_failure_is_503_and_stores_nothing(collector):
    collector.execute(
        "CREATE FUNCTION cji_test_refuse_commit() RETURNS trigger LANGUAGE plpgsql AS "
        "$$ BEGIN RAISE EXCEPTION 'commit refused'; END $$"
    )
    collector.execute(
        "CREATE CONSTRAINT TRIGGER cji_test_refuse AFTER INSERT ON live_events "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cji_test_refuse_commit()"
    )
    res = collector.post(batch(*[wire(i) for i in ids("commit", 3)]))
    assert_failed(res, 3)
    assert collector.rows() == []


# ═════════════════════════════════════════════════════════════════════════════
# Health
# ═════════════════════════════════════════════════════════════════════════════

def test_liveness_needs_no_database(api, monkeypatch):
    client = without_database(api, monkeypatch, api.UnconfiguredDatabase())
    res = client.get("/health/live")
    assert res.status_code == 200 and res.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/health/ready", "/health"])
def test_readiness_is_503_without_a_database(api, monkeypatch, path):
    engine = create_engine(DEAD_URL)
    client = without_database(api, monkeypatch, engine)
    res = client.get(path)
    assert res.status_code == 503 and res.json() == {"status": "not_ready"}
    assert without_database(api, monkeypatch, api.UnconfiguredDatabase()).get(path).status_code == 503
    engine.dispose()


def test_readiness_and_compat_health_with_a_database(collector):
    collector.post(batch(*[wire(i) for i in ids("health", 2)]))
    assert collector.client.get("/health/ready").json() == {"status": "ready"}
    res = collector.client.get("/health")
    assert res.status_code == 200 and res.json() == {"status": "ok", "live_events_count": 2}


def test_readiness_is_503_when_a_table_is_missing(collector):
    collector.execute("DROP TABLE api_keys")
    assert collector.client.get("/health/ready").status_code == 503


# ═════════════════════════════════════════════════════════════════════════════
# Correlation
# ═════════════════════════════════════════════════════════════════════════════

def test_valid_request_id_is_echoed(collector):
    res = collector.post(batch(wire(ids("rid", 1)[0])), headers={"X-Request-ID": "req-12345678"})
    assert res.headers["X-Request-ID"] == "req-12345678"
    assert res.json()["request_id"] == "req-12345678"


@pytest.mark.parametrize("given", ["bad id!", "short", "x" * 65, None])
def test_invalid_or_missing_request_id_is_replaced(collector, given):
    headers = {"X-Request-ID": given} if given else {}
    res = collector.client.get("/health/live", headers=headers)
    rid = res.headers["X-Request-ID"]
    assert rid != given and UUID4.fullmatch(rid)


def test_request_id_is_attached_to_collector_log_records(collector, caplog):
    caplog.set_level(logging.INFO, logger="collector")
    collector.post(batch(wire(ids("logid", 1)[0])), headers={"X-Request-ID": "req-logcheck-01"})
    tagged = [r for r in caplog.records if r.name == "collector" and getattr(r, "request_id", None) == "req-logcheck-01"]
    assert tagged, [r.getMessage() for r in caplog.records]


# ═════════════════════════════════════════════════════════════════════════════
# Logging — no keys, user/session/event ids, URLs or metadata
# ═════════════════════════════════════════════════════════════════════════════

SECRETS = {
    "user_id": "user-SECRETUSER01",
    "session_id": "sess-SECRETSESS01",
    "url": "https://secret-host.example/private-path",
    "metadata": {"note": "SECRETMETA01"},
}


def test_logs_never_contain_identifiers_or_payload(collector, caplog):
    ok_id, fail_id = "evt-SECRETEVT-0001", "evt-SECRETEVT-0002"
    # Set up the failing constraint before SQL logging is switched on (this statement is the test's own).
    collector.execute("ALTER TABLE live_events ADD CONSTRAINT cji_test_no_secret CHECK (event_id <> '" + fail_id + "')")
    caplog.set_level(logging.DEBUG, logger="collector")
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")
    collector.post(batch(wire(ok_id, **SECRETS)))                                   # stored
    collector.post(batch(wire("evt-SECRETEVT-0003", event_type="scroll", **SECRETS)))  # rejected
    collector.post(batch(wire(ok_id, **SECRETS)), headers={"X-CJI-Key": "cji_SECRETHEADER_01"})  # 401
    assert collector.post(batch(wire(fail_id, **SECRETS))).status_code == 503       # database failure

    logged = caplog.text + "\n".join(r.getMessage() for r in caplog.records)
    assert caplog.records, "expected collector log records"
    for secret in (ACTIVE_KEY, "cji_SECRETHEADER_01", "SECRETUSER01", "SECRETSESS01", "SECRETEVT",
                   "secret-host.example", "private-path", "SECRETMETA01"):
        assert secret not in logged, f"{secret!r} reached the logs"


def test_engine_hides_bound_parameters(api):
    engine = api._make_engine("postgresql://u:p@127.0.0.1:1/x")
    assert engine.hide_parameters is True
    engine.dispose()


# ═════════════════════════════════════════════════════════════════════════════
# CORS
# ═════════════════════════════════════════════════════════════════════════════

ORIGIN = "https://app.example"


@pytest.fixture
def cors_client(api, monkeypatch):
    from starlette.middleware.cors import CORSMiddleware

    monkeypatch.setattr(api, "engine", api.UnconfiguredDatabase())
    return TestClient(CORSMiddleware(api.app, **api.cors_options([ORIGIN])), raise_server_exceptions=False)


def preflight(client, origin, headers="content-type,x-cji-key,x-request-id"):
    return client.options("/collect/batch", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": headers,
    })


def test_cors_allows_listed_origin_without_credentials(cors_client):
    res = preflight(cors_client, ORIGIN)
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-credentials" not in res.headers
    simple = cors_client.get("/health/live", headers={"Origin": ORIGIN})
    exposed = simple.headers.get("access-control-expose-headers", "").lower()
    assert "x-request-id" in exposed and "retry-after" in exposed


def test_cors_ignores_unlisted_origins(cors_client):
    res = preflight(cors_client, "https://evil.example")
    assert "access-control-allow-origin" not in res.headers


def test_cors_does_not_allow_the_admin_header_from_browsers(api, cors_client):
    assert preflight(cors_client, ORIGIN, "x-cji-admin-key").status_code == 400
    cors = [m for m in api.app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert "X-CJI-Admin-Key" not in cors[0].kwargs["allow_headers"]


def test_production_refuses_plain_http_origins(api):
    with pytest.raises(ConfigError, match="https"):
        api.validate_collector_settings("production", GOOD_ADMIN, ["http://app.example"])
    api.validate_collector_settings("production", GOOD_ADMIN, ["http://localhost:3000", "https://app.example"])
    api.validate_collector_settings("development", "", ["http://app.example"])


# ═════════════════════════════════════════════════════════════════════════════
# Units — envelope parsing and response status (no database)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("body, status", [
    (b"{not json", 400),
    (b"[]", 422),
    (b'{"api_key": "short", "events": [{}]}', 422),
    (b'{"api_key": "cji_long_enough", "events": []}', 422),
    (b'{"api_key": "cji_long_enough", "events": {}}', 422),
    (b'{"api_key": 12345678901, "events": [{}]}', 422),
])
def test_envelope_errors(body, status):
    from collector import ingest

    with pytest.raises(ingest.EnvelopeError) as exc:
        ingest.parse_envelope(body)
    assert exc.value.status_code == status


def test_envelope_accepts_a_valid_body():
    from collector import ingest

    envelope = ingest.parse_envelope(json.dumps(batch(wire("evt-unit-0001"))).encode())
    assert envelope.api_key == ACTIVE_KEY and len(envelope.events) == 1


@pytest.mark.parametrize("content_type, ok", [
    ("application/json", True), ("application/json; charset=utf-8", True), ("text/plain;charset=UTF-8", True),
    ("text/html", False), ("", False), ("multipart/form-data", False),
])
def test_accepted_content_types(content_type, ok):
    from collector import ingest

    assert ingest.acceptable_content_type(content_type) is ok


@pytest.mark.parametrize("accepted, duplicates, rejected, expected", [
    (3, 0, 0, ("stored", 200)),
    (0, 3, 0, ("stored", 200)),
    (1, 0, 2, ("partial", 207)),
    (0, 1, 2, ("partial", 207)),
    (0, 0, 2, ("rejected", 422)),
])
def test_status_mapping(accepted, duplicates, rejected, expected):
    from collector import ingest

    assert ingest.status_for(accepted, duplicates, rejected) == expected


# ═════════════════════════════════════════════════════════════════════════════
# Domain limits (OD-45) — TrackerEvent boundaries
# ═════════════════════════════════════════════════════════════════════════════

def _event(**over):
    from domain.events import TrackerEvent

    return TrackerEvent.model_validate(wire("evt-limit-0001", **over))


def test_url_limit_applies_after_the_query_string_is_removed():
    base = "https://app.example.test/"
    assert len(_event(url=base + "p" * (2048 - len(base))).url) == 2048
    assert _event(url=base + "?q=" + "x" * 5000).url == base
    with pytest.raises(ValidationError):
        _event(url=base + "p" * (2049 - len(base)))


def test_element_selector_limit():
    assert len(_event(element_selectors="s" * 512).element_selectors) == 512
    with pytest.raises(ValidationError):
        _event(element_selectors="s" * 513)


def test_metadata_limit_is_8192_bytes_of_compact_json():
    overhead = len('{"k":""}')
    assert _event(metadata={"k": "x" * (8192 - overhead)}).metadata
    with pytest.raises(ValidationError):
        _event(metadata={"k": "x" * (8193 - overhead)})
    with pytest.raises(ValidationError):
        _event(metadata=json.dumps({"k": "x" * 9000}))              # JSON-string metadata is measured too
