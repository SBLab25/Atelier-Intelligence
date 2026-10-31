"""
Spec 14 — contract tests for the parity operations (design §2, §5): start and resume runs, run results with
provenance, ingestion validation and commit, report download, the write-operation switch. Same harness as the
Spec 12 contract tests: every response is checked against the OpenAPI document the app serves.
"""
from __future__ import annotations

import json

import pytest

from tests._api_harness import bearer
from tests.test_api_contract import API, JOURNEY, ApiEnv, problem, wait_status

GOOD_ROWS = [
    {"user_id": "u1", "session_id": "s1", "step_id": "landing_page", "event_type": "page_view",
     "timestamp": "2026-01-01T10:00:00Z", "duration_ms": 1200, "url": "/"},
    {"user_id": "u1", "session_id": "s1", "step_id": "sign_up_form", "event_type": "error",
     "timestamp": "2026-01-01T10:01:00Z", "duration_ms": 0, "url": "/signup"},
    {"user_id": "u2", "session_id": "s2", "step_id": "landing_page", "event_type": "made_up_type",
     "timestamp": "2026-01-01T10:02:00Z"},
    {"user_id": "u3", "session_id": "s3", "step_id": "unknown_step", "event_type": "page_view",
     "timestamp": "not a time"},
]


async def _ok() -> None:
    return None


async def _down() -> None:
    raise RuntimeError("Startup check failed for cji-insight. Make sure servers are running.")


@pytest.fixture
def papi(tmp_path, monkeypatch):
    """The Spec 12 harness with a passing MCP preflight and a sqlite engine for ingestion writes."""
    from sqlalchemy import create_engine

    from cji.settings import override_settings
    from tests import _workflow_stubs as stubs

    stubs.FAULTS.clear()
    stubs.WARNINGS.clear()
    env = ApiEnv(tmp_path, monkeypatch)
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    with override_settings(env.settings), env:
        env.ctx = env.app.state.ctx
        env.ctx.preflight = _ok
        env.ctx.ingestion_engine = lambda: engine
        env.engine = engine
        yield env
    stubs.FAULTS.clear()


def start(api, token, body=None, key="start-key-0001"):
    return api.client.post(f"{API}/runs", headers={**bearer(token), "Idempotency-Key": key},
                           json=body if body is not None else {"journey_id": JOURNEY})


def validate(api, token, rows=None, filename="events.json", media="application/json", query=""):
    data = json.dumps(GOOD_ROWS if rows is None else rows).encode()
    return api.client.post(f"{API}/ingestions/validations?filename={filename}{query}",
                           headers={**bearer(token), "Content-Type": media}, content=data)


def commit(api, token, validation_id, mode="append", key="ingest-key-0001"):
    return api.client.post(f"{API}/ingestions", headers={**bearer(token), "Idempotency-Key": key},
                           json={"validation_id": validation_id, "write_mode": mode})


# ── start (OD-144) ───────────────────────────────────────────────────────────────────────────────────

def test_start_run_creates_a_run_that_pauses_for_approval(papi):
    r = start(papi, papi.operator)
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["journey_id"] == JOURNEY and run["mode"] == "demo" and run["human_approved"] is False
    paused = wait_status(papi, run["run_id"], "awaiting_approval", papi.viewer)
    assert paused["steps"]["insight_worker"]["status"] == "succeeded"
    listed = papi.client.get(f"{API}/runs?journey_id={JOURNEY}", headers=bearer(papi.viewer)).json()["data"]
    assert run["run_id"] in [x["run_id"] for x in listed]


def test_start_run_auto_approve_completes_with_a_report(papi):
    r = start(papi, papi.operator, {"journey_id": JOURNEY, "auto_approve": True, "window_days": 7})
    assert r.status_code == 202, r.text
    done = wait_status(papi, r.json()["run_id"], "completed", papi.viewer)
    assert done["report_id"] is not None


def test_start_run_replays_and_checks_keys_roles_and_body(papi):
    first = start(papi, papi.operator)
    again = start(papi, papi.operator)
    assert again.status_code == 202 and again.headers["idempotent-replayed"] == "true"
    assert again.json()["run_id"] == first.json()["run_id"]
    problem(start(papi, papi.operator, {"journey_id": JOURNEY, "auto_approve": True}, key="start-key-0001"),
            409, "idempotency_key_reused")
    problem(papi.client.post(f"{API}/runs", headers=bearer(papi.operator), json={"journey_id": JOURNEY}),
            400, "idempotency_key_required")
    problem(start(papi, papi.viewer, key="start-key-viewer"), 403, "insufficient_role")
    problem(start(papi, papi.other, key="start-key-other"), 403, "journey_forbidden")
    problem(start(papi, papi.admin_all, {"journey_id": "nope"}, key="start-key-nope"), 404, "journey_not_found")
    problem(start(papi, papi.operator, {"journey_id": JOURNEY, "extra": 1}, key="start-key-extra"),
            422, "validation_failed")
    problem(start(papi, papi.operator, {"journey_id": JOURNEY, "window_days": 2, "window_minutes": 5},
                  key="start-key-both"), 422, "validation_failed")
    r = papi.client.post(f"{API}/runs", headers={**bearer(papi.operator), "Idempotency-Key": "start-key-text",
                                                   "Content-Type": "text/plain"}, content=b"journey")
    problem(r, 415, "unsupported_media_type")


def test_start_run_refuses_above_capacity_and_without_services(papi):
    papi.ctx.active_runs.add("another-run")
    body = problem(start(papi, papi.operator, key="start-key-cap"), 409, "run_capacity_reached")
    assert body["detail"] and papi.client.get(f"{API}/health/details",
                                              headers=bearer(papi.viewer)).json()["active_runs"] == 1
    papi.ctx.active_runs.clear()
    papi.ctx.preflight = _down
    r = start(papi, papi.operator, key="start-key-down")
    body = problem(r, 503, "services_unavailable")
    assert "cji-insight" not in r.text and "Startup" not in body["detail"]
    papi.ctx.preflight = _ok                      # the key was freed: the same request now succeeds
    assert start(papi, papi.operator, key="start-key-down").status_code == 202


# ── resume (OD-145) ──────────────────────────────────────────────────────────────────────────────────

def test_resume_continues_a_failed_run(papi):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["data_worker"] = [RuntimeError("boom")] * 5
    failed = papi.start_run(auto_approve=True)
    assert papi.client.get(f"{API}/runs/{failed}", headers=bearer(papi.viewer)).json()["status"] == "failed"
    stubs.FAULTS.clear()
    key = {**bearer(papi.operator), "Idempotency-Key": "resume-key-01"}
    r = papi.client.post(f"{API}/runs/{failed}/resume", headers=key)
    assert r.status_code == 202, r.text
    wait_status(papi, failed, "completed", papi.viewer)
    replay = papi.client.post(f"{API}/runs/{failed}/resume", headers=key)
    assert replay.status_code == 202 and replay.headers["idempotent-replayed"] == "true"


def test_resume_refuses_completed_paused_and_unknown_runs(papi):
    done = papi.start_run(auto_approve=True)
    paused = papi.start_run()
    h = bearer(papi.operator)
    body = problem(papi.client.post(f"{API}/runs/{done}/resume", headers={**h, "Idempotency-Key": "resume-done1"}),
                   409, "run_not_resumable")
    assert "completed" in body["detail"]
    body = problem(papi.client.post(f"{API}/runs/{paused}/resume", headers={**h, "Idempotency-Key": "resume-paus1"}),
                   409, "run_not_resumable")
    assert "approve" in body["detail"]
    problem(papi.client.post(f"{API}/runs/{paused}/resume", headers={**bearer(papi.viewer),
                                                                     "Idempotency-Key": "resume-view1"}),
            403, "insufficient_role")
    problem(papi.client.post(f"{API}/runs/no-such-run/resume", headers={**h, "Idempotency-Key": "resume-none1"}),
            404, "run_not_found")
    problem(papi.client.post(f"{API}/runs/{done}/resume", headers=h), 400, "idempotency_key_required")


def test_resume_refuses_a_run_this_process_is_driving(papi):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["data_worker"] = [RuntimeError("boom")] * 5
    failed = papi.start_run(auto_approve=True)
    papi.ctx.active_runs.add(failed)
    problem(papi.client.post(f"{API}/runs/{failed}/resume", headers={**bearer(papi.operator),
                                                                     "Idempotency-Key": "resume-busy1"}),
            409, "run_active")


# ── results and provenance (OD-146, OD-147) ──────────────────────────────────────────────────────────

def test_results_of_a_completed_run(papi):
    run_id = papi.start_run(auto_approve=True)
    r = papi.client.get(f"{API}/runs/{run_id}/results", headers=bearer(papi.viewer))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed" and body["narrative"] == "N"
    assert [s["step_id"] for s in body["friction_scores"]] == ["s1", "s2"] and body["critical_steps"] == ["s1"]
    assert len(body["insights"]) == 1 and body["insights"][0]["provenance"]["source"] == "not_recorded"
    assert body["narrative_provenance"]["source"] == "not_recorded"
    assert body["llm_usage"] == {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    assert body["prioritized_fixes"][0]["step_id"] == "s1"
    problem(papi.client.get(f"{API}/runs/{run_id}/results", headers=bearer(papi.other)), 404, "run_not_found")


def test_results_map_recorded_provenance_ingestion_and_errors():
    from cji.api.routes.runs import _results
    from cji.workflow.index import IndexedRun

    row = IndexedRun(run_id="r1", journey_id=JOURNEY, mode="demo", status="completed",
                     created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:01Z", report_file=None)
    values = {
        "run": {"status": "completed"}, "narrative": "Summary",
        "insights": [{"insight_id": "i1", "step_id": "s1", "title": "Slow form"},
                     {"insight_id": "i2", "step_id": "s2", "title": "Errors"}, {"title": "no ids"}],
        "insight_provenance": {"i1": {"source": "llm", "model": "m-1", "provider": "groq", "reason": None,
                                      "generated_at": "2026-01-01T00:00:00Z"},
                               "i2": {"source": "fallback", "model": None, "provider": None,
                                      "reason": "llm_timeout", "generated_at": "2026-01-01T00:00:00Z"}},
        "narrative_provenance": {"source": "llm", "model": "m-1", "provider": "groq", "generated_at": "x"},
        "llm_usage": {"calls": 3, "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.01},
        "ingestion_results": [{"source_file": "C:\\secret\\uploads\\events.json", "detected_source": "ga4",
                               "confidence": 0.9, "records_written": 4, "records_skipped": 1, "status": "ok"}],
        "ingestion_pending_review": [{"file_path": "/srv/data/x.csv", "mapping_config": {"detected_source": "?"},
                                      "confidence": 0.4, "flagged_at": "t"}],
        "errors": [{"worker": "w", "error": f"e{i}", "ts": "t"} for i in range(60)],
    }
    out = _results(row, {"status": "completed"}, values).model_dump()
    assert [i["provenance"]["source"] for i in out["insights"]] == ["llm", "fallback"]
    assert out["insights"][0]["provenance"]["model"] == "m-1" and out["insights"][1]["provenance"]["reason"] == "llm_timeout"
    assert out["narrative_provenance"]["provider"] == "groq" and out["llm_usage"]["calls"] == 3
    assert out["ingestion_results"][0]["file_name"] == "events.json"
    assert out["ingestion_pending_review"][0] == {"file_name": "x.csv", "detected_source": "?", "confidence": 0.4,
                                                  "flagged_at": "t"}
    assert "secret" not in json.dumps(out) and "/srv" not in json.dumps(out)
    assert len(out["errors"]) == 50 and out["errors"][-1]["message"] == "e59"


# ── ingestion (OD-148) ───────────────────────────────────────────────────────────────────────────────

def test_validation_reports_counts_steps_and_samples_without_writing(papi):
    r = validate(papi, papi.operator)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["rows"] == {"parsed": 4, "accepted": 3, "dropped_event_type": 1, "repaired_timestamp": 1}
    assert body["format"] == "JSON array" and body["database_configured"] is True
    found = {s["step_id"]: s for s in body["steps_found"]}
    assert found["landing_page"]["in_journey"] and not found["unknown_step"]["in_journey"]
    assert "onboarding_done" in body["journey_steps_missing"]
    assert len(body["samples"]) == 3 and "u1" not in r.text and "s1" not in json.dumps(body["samples"])
    from sqlalchemy import inspect

    assert not inspect(papi.engine).has_table("tracking_events")            # nothing written
    uploads = papi.settings.storage.data_dir / "ingestion_uploads"
    assert {p.name for p in uploads.iterdir()} == {f"{body['validation_id']}.json",
                                                   f"{body['validation_id']}.meta.json"}


def test_commit_appends_once_and_cleans_up(papi):
    vid = validate(papi, papi.operator).json()["validation_id"]
    r = commit(papi, papi.operator, vid)
    assert r.status_code == 201, r.text
    assert r.json() == {"validation_id": vid, "write_mode": "append", "rows_written": 3, "rows_already_stored": 0,
                        "destination": "tracking_events"}
    replay = commit(papi, papi.operator, vid)
    assert replay.status_code == 201 and replay.headers["idempotent-replayed"] == "true"
    problem(commit(papi, papi.operator, vid, key="ingest-key-0002"), 409, "validation_used")
    from sqlalchemy import text

    with papi.engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM tracking_events")).scalar() == 3
    assert not (papi.settings.storage.data_dir / "ingestion_uploads" / f"{vid}.json").exists()


def test_ingestion_roles_ownership_and_replace(papi):
    problem(validate(papi, papi.viewer), 403, "insufficient_role")
    vid = validate(papi, papi.operator).json()["validation_id"]
    problem(commit(papi, papi.operator, vid, mode="replace"), 403, "insufficient_role")
    problem(commit(papi, papi.admin_all, vid, key="ingest-key-admin"), 404, "validation_not_found")
    own = validate(papi, papi.admin_all).json()["validation_id"]
    r = commit(papi, papi.admin_all, own, mode="replace", key="ingest-key-repl")
    assert r.status_code == 201 and r.json()["rows_written"] == 3
    problem(commit(papi, papi.operator, "A" * 24, key="ingest-key-none"), 404, "validation_not_found")
    problem(commit(papi, papi.operator, "short", key="ingest-key-bad1"), 422, "validation_failed")


def test_validation_rejects_bad_requests(papi):
    problem(validate(papi, papi.operator, media="text/plain"), 415, "unsupported_media_type")
    problem(validate(papi, papi.operator, filename="events.exe"), 422, "validation_failed")
    problem(validate(papi, papi.operator, query="&map=userId"), 422, "validation_failed")
    problem(validate(papi, papi.operator, query="&map=a%3Dnot_a_column"), 422, "validation_failed")
    problem(validate(papi, papi.operator, query="&unknown=1"), 422, "validation_failed")
    problem(validate(papi, papi.operator, rows=[]), 422, "ingestion_unreadable")
    r = papi.client.post(f"{API}/ingestions/validations?filename=e.json",
                         headers={**bearer(papi.operator), "Content-Type": "application/json"}, content=b"[{oops")
    problem(r, 422, "ingestion_unreadable")
    assert not any((papi.settings.storage.data_dir / "ingestion_uploads").glob("*.json"))


def test_validation_applies_the_column_map(papi):
    rows = [{"userId": "u9", "page": "landing", "kind": "page_view", "when": "2026-01-01T00:00:00Z"}]
    r = validate(papi, papi.operator, rows=rows, query="&map=when%3Dtimestamp")
    assert r.status_code == 201, r.text
    assert r.json()["steps_found"][0]["step_id"] == "landing_page" and r.json()["rows"]["repaired_timestamp"] == 0


def test_upload_limit_is_separate_from_the_json_body_limit(papi):
    big = [dict(GOOD_ROWS[0], user_id=f"u{i}") for i in range(400)]            # about 50 KiB, above 16 KiB
    assert validate(papi, papi.operator, rows=big).status_code == 201
    r = papi.client.post(f"{API}/runs", headers={**bearer(papi.operator), "Idempotency-Key": "start-key-big1"},
                         json={"journey_id": JOURNEY, "pad": "x" * 20000})
    problem(r, 413, "request_too_large")


def test_upload_limit_setting(tmp_path, monkeypatch):
    from cji.settings import override_settings

    env = ApiEnv(tmp_path, monkeypatch, CJI_API_MAX_UPLOAD_BYTES="2048")
    with override_settings(env.settings), env:
        big = [dict(GOOD_ROWS[0], user_id=f"u{i}") for i in range(40)]
        problem(validate(env, env.operator, rows=big), 413, "request_too_large")


def test_commit_without_a_database(papi, monkeypatch):
    import cji.api.routes.ingestions as routes

    monkeypatch.setattr(routes, "_database_configured", lambda ctx: False)
    r = validate(papi, papi.operator)
    assert r.status_code == 201 and r.json()["database_configured"] is False
    problem(commit(papi, papi.operator, r.json()["validation_id"]), 503, "database_unavailable")


def test_expired_validations_are_purged(papi):
    from cji.services.ingestion import UploadStore

    vid = validate(papi, papi.operator).json()["validation_id"]
    store = UploadStore(papi.settings.storage.data_dir / "ingestion_uploads")
    meta = store.read_meta(vid)
    store.write_meta(vid, {**meta, "expires_ts": 0})
    problem(commit(papi, papi.operator, vid), 404, "validation_not_found")
    assert store.purge() == 2 and not any(store.directory.iterdir())


# ── reports, health, switch ──────────────────────────────────────────────────────────────────────────

def test_report_download_disposition(papi):
    run_id = papi.start_run(auto_approve=True)
    papi.write_report(run_id)
    report_id = f"j_{run_id}"
    inline = papi.client.get(f"{API}/reports/{report_id}/content", headers=bearer(papi.viewer))
    assert inline.status_code == 200 and inline.headers["content-disposition"] == "inline"
    down = papi.client.get(f"{API}/reports/{report_id}/content?disposition=attachment", headers=bearer(papi.viewer))
    assert down.status_code == 200
    assert down.headers["content-disposition"] == f'attachment; filename="cji_report_j_{run_id}.html"'
    assert down.headers["content-security-policy"].startswith("default-src 'none'") and down.content == inline.content
    problem(papi.client.get(f"{API}/reports/{report_id}/content?disposition=save", headers=bearer(papi.viewer)),
            422, "validation_failed")


def test_write_operations_can_be_switched_off(tmp_path, monkeypatch):
    from cji.settings import override_settings

    env = ApiEnv(tmp_path, monkeypatch, CJI_API_WRITE_OPERATIONS="false")
    with override_settings(env.settings), env:
        problem(start(env, env.operator), 405, "method_not_allowed")          # GET /runs still exists
        problem(validate(env, env.operator), 404, "not_found")
        run_id = env.start_run()
        r = env.client.post(f"{API}/runs/{run_id}/approval",
                            headers={**bearer(env.operator), "Idempotency-Key": "approve-key-off"}, json={})
        assert r.status_code == 202                                  # approval (Spec 12) is not switched off
        paths = env._client.get(f"{API}/openapi.json").json()["paths"]
        assert f"{API}/runs/{{run_id}}/resume" not in paths and f"{API}/ingestions" not in paths


def test_snapshot_lists_the_new_operations():
    from cji.api.openapi_snapshot import current_document

    doc = current_document()
    ops = {op["operationId"] for item in doc["paths"].values() for op in item.values()}
    assert {"startRun", "resumeRun", "getRunResults", "validateIngestion", "createIngestion"} <= ops
    assert len(ops) == 22               # Spec 15: getReadiness, getMetrics
