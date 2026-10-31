"""
Spec 07 T6: existing tests that described the old collector contract.

- test_p0_security: /live/stats now needs the admin key (OD-44).
- test_contracts: the fake-engine collector case moves to PostgreSQL (multi-row RETURNING, OD-41);
  same assertions, with 20 distinct event ids (identical ids are duplicates since OD-42).
- test_collector_models: the inactive Spec 03 response models were replaced (design §1).
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[5]
TESTS = ROOT / "cji_agent" / "tests"


def edit(name, pairs):
    path = TESTS / name
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        n = text.count(old)
        assert n == 1, f"{name}: expected 1 match, found {n}: {old[:70]!r}"
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("edited", name)


edit("test_p0_security.py", [(
    '''    fake = FakeEngine()
    monkeypatch.setattr(collector_api, "engine", fake)
    client = TestClient(collector_api.app, raise_server_exceptions=False)
    assert client.get("/live/stats?minutes=30").status_code == 200
''',
    '''    fake = FakeEngine()
    monkeypatch.setattr(collector_api, "engine", fake)
    monkeypatch.setattr(collector_api, "CJI_ADMIN_KEY", GOOD_KEY)       # admin only since Spec 07 (OD-44)
    client = TestClient(collector_api.app, raise_server_exceptions=False)
    assert client.get("/live/stats?minutes=30", headers={"X-CJI-Admin-Key": GOOD_KEY}).status_code == 200
''')])

contracts = TESTS / "test_contracts.py"
text = contracts.read_text(encoding="utf-8")
start = text.index("class _Result:\n")
end = text.index("# ═════════════════════════════════════════════════════════════════════════════\n# Single source of truth")
assert text.count("FakeEngine()") == 1
text = text[:start] + text[end:]
contracts.write_text(text, encoding="utf-8")
edit("test_contracts.py", [(
    '''def test_collector_rejects_invalid_events_and_stores_valid_ones(monkeypatch):
    from fastapi.testclient import TestClient

    api = importlib.import_module("collector.api")
    fake = FakeEngine()
    monkeypatch.setattr(api, "engine", fake)
    client = TestClient(api.app, raise_server_exceptions=False)

    bad = client.post("/collect/batch", json={"api_key": "cji_dev_localtest",
                                              "events": [{**TRACKER_WIRE, "event_type": "scroll"}]})
    assert bad.status_code == 422

    good = client.post("/collect/batch", json={"api_key": "cji_dev_localtest", "events": [TRACKER_WIRE] * 20})
    assert good.status_code == 200
    inserts = [p for sql, p in fake.log if "INSERT INTO live_events" in sql]
    assert len(inserts) == 20
    assert inserts[0]["journey_name"] == "user_onboarding"
    assert inserts[0]["url"] == "https://app.example.test/signup"
''',
    '''def test_collector_rejects_invalid_events_and_stores_valid_ones(monkeypatch, pg_url):
    # PostgreSQL since Spec 07: the collector writes one multi-row INSERT ... RETURNING (OD-41).
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text

    api = importlib.import_module("collector.api")
    engine = create_engine(pg_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS live_events, api_keys"))
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(api, "CJI_ENV", "development")          # seeds cji_dev_localtest
    monkeypatch.setattr(api, "JOURNEY_NAME", "user_onboarding")
    api._create_tables()
    client = TestClient(api.app, raise_server_exceptions=False)

    bad = client.post("/collect/batch", json={"api_key": "cji_dev_localtest",
                                              "events": [{**TRACKER_WIRE, "event_type": "scroll"}]})
    assert bad.status_code == 422

    events = [{**TRACKER_WIRE, "event_id": f"{TRACKER_WIRE['event_id']}-{i:02d}"} for i in range(20)]
    good = client.post("/collect/batch", json={"api_key": "cji_dev_localtest", "events": events})
    assert good.status_code == 200 and good.json()["accepted"] == 20
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT journey_name, url FROM live_events")).fetchall()
    engine.dispose()
    assert len(rows) == 20
    assert rows[0][0] == "user_onboarding"
    assert rows[0][1] == "https://app.example.test/signup"
''')])

edit("test_collector_models.py", [
    ('''    CollectResponse,
    EventBatch,
    HealthResponse,
    TrackerEvent,
''', '''    CollectResult,
    EventBatch,
    EventError,
    HealthStatus,
    TrackerEvent,
'''),
    ('''def test_collect_response_defaults(valid_event_data_dict):
    """CollectResponse has sensible defaults."""
    r = CollectResponse(accepted=5)
    assert r.accepted == 5
    assert r.rejected == 0
    assert r.errors == 0
    assert r.message == "OK"
''', '''def test_collect_result_defaults(valid_event_data_dict):
    """CollectResult (Spec 07) counts default to zero and never says 'queued'."""
    r = CollectResult(status="stored", request_id="req-12345678", received=5, accepted=5)
    assert (r.accepted, r.duplicates, r.rejected, r.errors) == (5, 0, 0, [])
    with pytest.raises(ValidationError):
        CollectResult(status="queued", request_id="req-12345678")
    err = EventError(index=2, reason="invalid", fields=["event_type"])
    assert err.model_dump(exclude_none=True) == {"index": 2, "reason": "invalid", "fields": ["event_type"]}
'''),
    ('''def test_health_response_fields(valid_event_data_dict):
    """HealthResponse accepts mode and live_events_count."""
    h = HealthResponse(status="ok", mode="demo", live_events_count=42)
    assert h.status == "ok"
    assert h.mode == "demo"
    assert h.live_events_count == 42
    assert h.version == "2.0"
''', '''def test_health_status_fields(valid_event_data_dict):
    """HealthStatus (Spec 07) carries the status and, for /health, the live_events count."""
    h = HealthStatus(status="ok", live_events_count=42)
    assert (h.status, h.live_events_count) == ("ok", 42)
    assert HealthStatus(status="not_ready").live_events_count is None
'''),
])
