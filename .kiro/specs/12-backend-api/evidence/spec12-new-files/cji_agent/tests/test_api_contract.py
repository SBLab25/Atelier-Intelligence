"""
Spec 12 — /api/v1 contract tests (design §8). Offline: TestClient, temporary storage, the demo Parquet, stub
workflow workers. Every response goes through ValidatingClient, which checks it against the OpenAPI document the
app serves (status declared, content type declared, body matches the schema).
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from tests._api_harness import APP_ROOT, ValidatingClient, bearer, copy_demo_data

API = "/api/v1"
JOURNEY = "user_onboarding"
SENTINEL = "SENTINEL-s3cr3t-9f8e7d"
PROBLEM = "application/problem+json"


# ── harness ──────────────────────────────────────────────────────────────────────────────────────────

class ApiEnv:
    def __init__(self, tmp_path, monkeypatch, **env):
        from fastapi.testclient import TestClient

        from cji.api.app import create_app
        from cji.api.auth import create_token
        from cji.settings import make_test_settings

        self.tmp = tmp_path
        copy_demo_data(tmp_path / "data")
        self.tokens_file = tmp_path / "data" / "api_tokens.json"
        self.db = tmp_path / "checkpoints.db"
        values = {"CJI_MODE": "demo", "CJI_CHECKPOINTS_DB": str(self.db), "CJI_API_TOKENS_FILE": str(self.tokens_file),
                  "CJI_API_RATE_PER_TOKEN": "1000", "CJI_API_RATE_PER_IP": "1000",
                  "CJI_API_CURSOR_SECRET": "c" * 40, "CJI_WORKFLOW_RETRY_BACKOFF_S": "0", **env}
        self.settings = make_test_settings(tmp_path, **values)
        monkeypatch.setenv("WORKFLOW_STUB_STORE", str(tmp_path / "store.json"))
        monkeypatch.delenv("WORKFLOW_STUB_CRASH", raising=False)
        self.viewer = create_token(self.tokens_file, label="viewer", role="viewer", journeys=[JOURNEY])
        self.operator = create_token(self.tokens_file, label="operator", role="operator", journeys=[JOURNEY])
        self.admin_all = create_token(self.tokens_file, label="all", role="admin", journeys=["*"])
        self.other = create_token(self.tokens_file, label="other", role="operator", journeys=["other_journey"])
        self.app = create_app(self.settings, workflow_factory=self.workflow)
        self._client = TestClient(self.app, raise_server_exceptions=False)

    def workflow(self, owner=None):
        from cji.graph import build_graph
        from cji.workflow.runtime import Workflow
        from tests import _workflow_stubs as stubs

        return Workflow(self.db, graph=build_graph(nodes=stubs.nodes()), owner=owner)

    def start_run(self, *, auto_approve=False):
        from cji.workflow.runtime import initial_state

        state = initial_state(mode="demo", journey_name=JOURNEY, journey_steps=["s1", "s2"], auto_approve=auto_approve)
        outcome = asyncio.run(self.workflow(owner="test-start").start(state))
        return outcome.run_id

    def write_report(self, run_id, html="<!doctype html><html><body>report</body></html>"):
        path = self.settings.storage.reports_dir / f"cji_report_j_{run_id}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return path

    def __enter__(self):
        self._client.__enter__()
        self.client = ValidatingClient(self._client, self._client.get(f"{API}/openapi.json").json())
        return self

    def __exit__(self, *exc):
        self._client.__exit__(*exc)


@pytest.fixture
def api(tmp_path, monkeypatch):
    from cji.settings import override_settings
    from tests import _workflow_stubs as stubs

    stubs.FAULTS.clear()
    stubs.WARNINGS.clear()
    env = ApiEnv(tmp_path, monkeypatch)
    with override_settings(env.settings), env:
        yield env
    stubs.FAULTS.clear()


def problem(response, status, code):
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith(PROBLEM)
    body = response.json()
    assert body["code"] == code and body["status"] == status and body["type"] == f"urn:cji:problem:{code}"
    assert body["request_id"] == response.headers["x-request-id"]
    return body


def assert_clean(response):
    text = response.text + json.dumps(dict(response.headers))
    for marker in (SENTINEL, "Traceback", "postgresql://", "\\secret", "/secret/", "SELECT ", "File \""):
        assert marker not in text, f"{marker!r} leaked: {text[:400]}"


def wait_status(api, run_id, wanted, token, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = api.client.get(f"{API}/runs/{run_id}", headers=bearer(token))
        if r.status_code == 200 and r.json()["status"] == wanted and not r.json()["active"]:
            return r.json()
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} did not reach {wanted}: {r.text}")


def approve(api, run_id, token, key="approve-key-0001", body=None):
    headers = {**bearer(token), "Idempotency-Key": key}
    return api.client.post(f"{API}/runs/{run_id}/approval", headers=headers, json=body if body is not None else {})


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# success
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_health_is_public_and_minimal(api):
    r = api.client.get(f"{API}/health")
    assert r.status_code == 200 and r.json() == {"status": "ok", "version": "1.0.0", "mode": "demo"}
    assert r.headers["x-request-id"]
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"


def test_health_details_lists_components(api):
    r = api.client.get(f"{API}/health/details", headers=bearer(api.viewer))
    assert r.status_code == 200
    body = r.json()
    assert {c["name"] for c in body["components"]} == {"repository", "checkpoints", "reports"}
    assert body["status"] == "ok", body


def test_me_describes_the_token_without_secrets(api):
    r = api.client.get(f"{API}/me", headers=bearer(api.operator))
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "operator" and body["role"] == "operator" and body["journeys"] == [JOURNEY]
    assert body["token_id"].startswith("tok_") and api.operator not in r.text


def test_journeys_are_filtered_by_the_token(api):
    r = api.client.get(f"{API}/journeys", headers=bearer(api.viewer))
    assert r.status_code == 200
    assert [j["journey_id"] for j in r.json()["data"]] == [JOURNEY]
    assert len(r.json()["data"][0]["steps"]) == 8 and r.json()["page"]["next_cursor"] is None
    r = api.client.get(f"{API}/journeys", headers=bearer(api.other))
    assert r.status_code == 200 and r.json()["data"] == []


def test_journey_detail(api):
    r = api.client.get(f"{API}/journeys/{JOURNEY}", headers=bearer(api.viewer))
    assert r.status_code == 200 and r.json()["journey_id"] == JOURNEY and r.json()["mode"] == "demo"


def test_metrics_match_the_repository(api):
    from cji.config import JOURNEY_CONFIG
    from cji.repositories import TimeWindow, event_repository

    r = api.client.get(f"{API}/journeys/{JOURNEY}/metrics?days=30", headers=bearer(api.viewer))
    assert r.status_code == 200
    body = r.json()
    repo = event_repository(api.settings)
    try:
        assert body["steps"] == repo.step_metrics(JOURNEY, TimeWindow(days_back=30))
        assert body["funnel"] == repo.funnel(JOURNEY, JOURNEY_CONFIG["steps"], TimeWindow(days_back=30))
    finally:
        repo.close()
    assert body["window"] == {"days": 30, "minutes": None}
    assert 0 <= body["overall_completion_pct"] <= 100


def test_friction_matches_the_engine(api):
    from cji.analytics.friction import score_steps
    from cji.repositories import TimeWindow, event_repository

    r = api.client.get(f"{API}/journeys/{JOURNEY}/friction", headers=bearer(api.viewer))
    assert r.status_code == 200
    body = r.json()
    repo = event_repository(api.settings)
    try:
        expected = score_steps(repo.step_metrics(JOURNEY, TimeWindow(days_back=30)), threshold=60)
    finally:
        repo.close()
    assert body["scores"] == expected["scores"] and body["critical_steps"] == expected["critical_steps"]
    assert body["threshold"] == 60 and len(body["scores"]) == 8


def test_events_are_paged_in_a_stable_order(api):
    seen, cursor, pages = [], None, 0
    while pages < 4:
        url = f"{API}/journeys/{JOURNEY}/events?limit=7&step_id=payment_info"
        if cursor:
            url += f"&cursor={cursor}"
        r = api.client.get(url, headers=bearer(api.operator))
        assert r.status_code == 200, r.text
        page = r.json()
        assert len(page["data"]) == 7 and page["page"]["limit"] == 7
        seen += [(e["timestamp"], e["event_id"]) for e in page["data"]]
        assert all(e["step_id"] == "payment_info" for e in page["data"])
        assert set(page["data"][0]) == {"event_id", "user_id", "session_id", "step_id", "event_type", "timestamp",
                                        "duration_ms", "url"}
        cursor, pages = page["page"]["next_cursor"], pages + 1
        assert cursor
    assert len(set(seen)) == len(seen) == 28
    assert seen == sorted(seen, reverse=True)
    assert all(ts.endswith("Z") for ts, _ in seen)


def test_events_last_page_has_no_cursor(api):
    r = api.client.get(f"{API}/journeys/{JOURNEY}/events?limit=200&event_type=no_such_type", headers=bearer(api.operator))
    assert r.status_code == 200 and r.json() == {"data": [], "page": {"limit": 200, "next_cursor": None}}


def test_runs_list_detail_and_insights(api):
    done = api.start_run(auto_approve=True)
    paused = api.start_run()
    r = api.client.get(f"{API}/runs", headers=bearer(api.viewer))
    assert r.status_code == 200
    by_id = {run["run_id"]: run for run in r.json()["data"]}
    assert by_id[done]["status"] == "completed" and by_id[paused]["status"] == "awaiting_approval"
    assert by_id[done]["journey_id"] == JOURNEY and by_id[done]["report_id"] == f"j_{done}"
    r = api.client.get(f"{API}/runs?status=awaiting_approval", headers=bearer(api.viewer))
    assert [run["run_id"] for run in r.json()["data"]] == [paused]
    r = api.client.get(f"{API}/runs/{done}", headers=bearer(api.viewer))
    body = r.json()
    assert r.status_code == 200 and body["human_approved"] and not body["active"]
    assert set(body["steps"]) >= {"data_worker", "friction_worker", "insight_worker", "report_worker"}
    assert body["failure"] is None and body["insight_count"] == 1 and "lease_owner" not in body
    # OD-113: by default the latest run of the journey that has insights (the paused run started last)
    r = api.client.get(f"{API}/journeys/{JOURNEY}/insights", headers=bearer(api.viewer))
    assert r.status_code == 200 and r.json()["run_id"] == paused
    r = api.client.get(f"{API}/journeys/{JOURNEY}/insights?run_id={done}", headers=bearer(api.viewer))
    assert r.status_code == 200 and r.json()["run_id"] == done
    assert [i["step_id"] for i in r.json()["insights"]] == ["s1"]


def test_insights_without_runs_are_an_empty_list(api):
    r = api.client.get(f"{API}/journeys/{JOURNEY}/insights", headers=bearer(api.viewer))
    assert r.status_code == 200 and r.json() == {"journey_id": JOURNEY, "run_id": None, "insights": []}


def test_runs_are_paged(api):
    ids = {api.start_run(auto_approve=True) for _ in range(3)}
    r1 = api.client.get(f"{API}/runs?limit=2", headers=bearer(api.viewer))
    r2 = api.client.get(f"{API}/runs?limit=2&cursor={r1.json()['page']['next_cursor']}", headers=bearer(api.viewer))
    got = [run["run_id"] for run in r1.json()["data"] + r2.json()["data"]]
    assert set(got) == ids and len(got) == 3 and r2.json()["page"]["next_cursor"] is None


def test_reports_metadata_and_content(api):
    run_id = api.start_run(auto_approve=True)
    api.write_report(run_id)
    r = api.client.get(f"{API}/reports", headers=bearer(api.viewer))
    assert r.status_code == 200
    report = r.json()["data"][0]
    assert report["report_id"] == f"j_{run_id}" and report["run_id"] == run_id and report["journey_id"] == JOURNEY
    assert report["content_url"] == f"{API}/reports/j_{run_id}/content" and report["size_bytes"] > 0
    assert str(api.tmp) not in json.dumps(report) and "path" not in report
    r = api.client.get(f"{API}/reports/j_{run_id}", headers=bearer(api.viewer))
    assert r.status_code == 200 and r.json() == report
    r = api.client.get(f"{API}/reports/j_{run_id}/content", headers=bearer(api.viewer))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff" and "report" in r.text


def test_approval_runs_the_report_step_in_the_background(api):
    run_id = api.start_run()
    r = approve(api, run_id, api.operator)
    assert r.status_code == 202, r.text
    assert r.json()["already_approved"] is False and r.json()["run"]["status"] == "approved"
    final = wait_status(api, run_id, "completed", api.operator)
    assert final["report_id"] == f"j_{run_id}"
    r = approve(api, run_id, api.operator, key="approve-key-0002")
    assert r.status_code == 200 and r.json()["already_approved"] is True and r.json()["run"]["status"] == "completed"


def test_approval_replays_with_the_same_key(api):
    run_id = api.start_run()
    first = approve(api, run_id, api.operator, key="replay-key-0001")
    again = approve(api, run_id, api.operator, key="replay-key-0001")
    assert again.status_code == first.status_code == 202
    assert again.json() == first.json() and again.headers["idempotent-replayed"] == "true"
    wait_status(api, run_id, "completed", api.operator)


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# validation
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=abc", f"cursor={SENTINEL}", "status=nope"])
def test_list_parameters_are_validated(api, query):
    r = api.client.get(f"{API}/runs?{query}", headers=bearer(api.viewer))
    code = "invalid_cursor" if query.startswith("cursor") else "validation_failed"
    body = problem(r, 422, code)
    assert_clean(r)
    if code == "validation_failed":
        assert body["errors"] and {"location", "field", "reason"} <= set(body["errors"][0])


@pytest.mark.parametrize("query", ["days=0", "days=366", "minutes=0", "minutes=43201"])
def test_window_parameters_are_validated(api, query):
    problem(api.client.get(f"{API}/journeys/{JOURNEY}/metrics?{query}", headers=bearer(api.viewer)), 422,
            "validation_failed")


def test_unknown_query_parameters_are_rejected(api):
    r = api.client.get(f"{API}/journeys?colour={SENTINEL}", headers=bearer(api.viewer))
    body = problem(r, 422, "validation_failed")
    assert body["errors"][0]["field"] == "colour"
    assert_clean(r)


def test_identifiers_are_validated(api):
    problem(api.client.get(f"{API}/runs/bad%20id!", headers=bearer(api.viewer)), 422, "validation_failed")
    problem(api.client.get(f"{API}/reports/{'x' * 200}", headers=bearer(api.viewer)), 422, "validation_failed")
    long_journey = "j" * 129
    problem(api.client.get(f"{API}/journeys/{long_journey}", headers=bearer(api.admin_all)), 422, "validation_failed")


def test_approval_body_is_validated_without_echo(api):
    run_id = api.start_run()
    r = approve(api, run_id, api.operator, body={"comment": "ok", "extra": SENTINEL})
    problem(r, 422, "validation_failed")
    assert_clean(r)
    r = approve(api, run_id, api.operator, key="approve-key-0003", body={"comment": SENTINEL * 50})
    problem(r, 422, "validation_failed")
    assert_clean(r)


def test_approval_needs_json_and_a_bounded_body(api):
    run_id = api.start_run()
    headers = {**bearer(api.operator), "Idempotency-Key": "approve-key-0004", "Content-Type": "text/plain"}
    problem(api.client.post(f"{API}/runs/{run_id}/approval", headers=headers, content=b"{}"), 415,
            "unsupported_media_type")
    headers["Content-Type"] = "application/json"
    big = json.dumps({"comment": "x" * 20_000}).encode()
    problem(api.client.post(f"{API}/runs/{run_id}/approval", headers=headers, content=big), 413, "request_too_large")


@pytest.mark.parametrize("key, code", [(None, "idempotency_key_required"), ("short", "idempotency_key_invalid"),
                                       ("has spaces in it", "idempotency_key_invalid")])
def test_approval_requires_a_valid_idempotency_key(api, key, code):
    run_id = api.start_run()
    headers = bearer(api.operator) | ({"Idempotency-Key": key} if key else {})
    problem(api.client.post(f"{API}/runs/{run_id}/approval", headers=headers, json={}), 400, code)


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# unauthorized
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("headers, code", [
    ({}, "missing_token"),
    ({"Authorization": "Basic dXNlcjpwYXNz"}, "missing_token"),
    ({"Authorization": "Bearer cji_api_not-a-real-token-value-000000000000000"}, "invalid_token"),
    ({"Authorization": "Bearer "}, "missing_token"),
])
def test_requests_without_a_valid_token_are_unauthorized(api, headers, code):
    for path in ("/me", "/journeys", f"/journeys/{JOURNEY}/metrics", "/runs", "/reports", "/nope"):
        r = api.client.get(f"{API}{path}", headers=headers)
        problem(r, 401, code)
        assert r.headers["www-authenticate"].startswith("Bearer")


def test_revoked_and_expired_tokens_are_unauthorized(api):
    from cji.api.auth import create_token, revoke_token, token_id_for

    revoke_token(api.tokens_file, token_id_for(api.viewer))
    problem(api.client.get(f"{API}/me", headers=bearer(api.viewer)), 401, "invalid_token")
    expired = create_token(api.tokens_file, label="old", role="viewer", journeys=["*"], expires_days=-1)
    problem(api.client.get(f"{API}/me", headers=bearer(expired)), 401, "invalid_token")


def test_unauthorized_requests_never_see_validation_detail(api):
    run_id = api.start_run()
    r = api.client.post(f"{API}/runs/{run_id}/approval", json={"extra": SENTINEL})
    body = problem(r, 401, "missing_token")
    assert "errors" not in body
    assert_clean(r)


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# forbidden
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_events_need_the_operator_role(api):
    problem(api.client.get(f"{API}/journeys/{JOURNEY}/events", headers=bearer(api.viewer)), 403, "insufficient_role")


def test_approval_needs_the_operator_role(api):
    run_id = api.start_run()
    problem(approve(api, run_id, api.viewer), 403, "insufficient_role")


@pytest.mark.parametrize("path", ["", "/metrics", "/friction", "/insights", "/events"])
def test_journeys_outside_the_token_are_forbidden(api, path):
    problem(api.client.get(f"{API}/journeys/{JOURNEY}{path}", headers=bearer(api.other)), 403, "journey_forbidden")
    problem(api.client.get(f"{API}/journeys/unknown_journey{path}", headers=bearer(api.viewer)), 403,
            "journey_forbidden")


def test_list_filters_outside_the_token_are_forbidden(api):
    problem(api.client.get(f"{API}/runs?journey_id={JOURNEY}", headers=bearer(api.other)), 403, "journey_forbidden")
    problem(api.client.get(f"{API}/reports?journey_id={JOURNEY}", headers=bearer(api.other)), 403,
            "journey_forbidden")


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# not found
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_unknown_journey_inside_the_scope_is_not_found(api):
    problem(api.client.get(f"{API}/journeys/unknown_journey", headers=bearer(api.admin_all)), 404,
            "journey_not_found")


def test_unknown_and_invisible_runs_look_the_same(api):
    run_id = api.start_run(auto_approve=True)
    unknown = problem(api.client.get(f"{API}/runs/00000000-0000-0000-0000-000000000000", headers=bearer(api.other)),
                      404, "run_not_found")
    hidden = problem(api.client.get(f"{API}/runs/{run_id}", headers=bearer(api.other)), 404, "run_not_found")
    assert {k: v for k, v in unknown.items() if k != "request_id"} == {k: v for k, v in hidden.items()
                                                                       if k != "request_id"}
    problem(approve(api, run_id, api.other), 404, "run_not_found")
    r = api.client.get(f"{API}/runs", headers=bearer(api.other))
    assert r.status_code == 200 and r.json()["data"] == []


def test_unknown_and_invisible_reports_look_the_same(api):
    run_id = api.start_run(auto_approve=True)
    api.write_report(run_id)
    problem(api.client.get(f"{API}/reports/j_no-such-run", headers=bearer(api.viewer)), 404, "report_not_found")
    problem(api.client.get(f"{API}/reports/j_{run_id}", headers=bearer(api.other)), 404, "report_not_found")
    problem(api.client.get(f"{API}/reports/j_{run_id}/content", headers=bearer(api.other)), 404, "report_not_found")


def test_unknown_routes_and_methods(api):
    problem(api.client.get(f"{API}/nope", headers=bearer(api.viewer)), 404, "not_found")
    problem(api.client.request("DELETE", f"{API}/journeys", headers=bearer(api.viewer)), 405, "method_not_allowed")


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# conflict
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_only_runs_awaiting_approval_can_be_approved(api):
    from tests import _workflow_stubs as stubs

    stubs.FAULTS["data_worker"] = [RuntimeError("boom")] * 5
    failed = api.start_run()
    r = api.client.get(f"{API}/runs/{failed}", headers=bearer(api.viewer))
    assert r.json()["status"] == "failed" and r.json()["failure"]["code"] == "unexpected_error"
    body = problem(approve(api, failed, api.operator), 409, "run_not_awaiting_approval")
    assert "failed" in body["detail"]


def test_a_run_leased_elsewhere_is_busy(api):
    from cji.workflow.runtime import Lease

    run_id = api.start_run()
    Lease(api.db).acquire(run_id, "otherhost:1:abcdef", 600)
    problem(approve(api, run_id, api.operator, key="busy-key-0001"), 409, "run_busy")
    r = api.client.get(f"{API}/runs/{run_id}", headers=bearer(api.viewer))
    assert r.json()["active"] is True and "otherhost" not in r.text


def test_reusing_a_key_for_a_different_request_is_a_conflict(api):
    run_id = api.start_run()
    assert approve(api, run_id, api.operator, key="reuse-key-0001").status_code == 202
    other = api.start_run()
    problem(approve(api, other, api.operator, key="reuse-key-0001"), 409, "idempotency_key_reused")
    wait_status(api, run_id, "completed", api.operator)


def test_a_key_still_in_progress_is_a_conflict(api):
    from cji.api.auth import token_id_for

    run_id = api.start_run()
    store = api.app.state.ctx.idempotency
    route = f"POST {API}/runs/{run_id}/approval"
    assert store.begin(token_id_for(api.operator), "pending-key-0001", route, store.request_hash(route, b"{}")) is None
    problem(approve(api, run_id, api.operator, key="pending-key-0001"), 409, "request_in_progress")


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# rate limit
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_tokens_are_rate_limited(tmp_path, monkeypatch):
    from cji.settings import override_settings

    env = ApiEnv(tmp_path, monkeypatch, CJI_API_RATE_PER_TOKEN="3")
    with override_settings(env.settings), env:
        for _ in range(3):
            assert env.client.get(f"{API}/me", headers=bearer(env.viewer)).status_code == 200
        r = env.client.get(f"{API}/me", headers=bearer(env.viewer))
        problem(r, 429, "rate_limited")
        assert int(r.headers["retry-after"]) >= 1
        assert env.client.get(f"{API}/me", headers=bearer(env.operator)).status_code == 200   # own bucket


def test_bad_tokens_are_rate_limited_per_address(tmp_path, monkeypatch):
    from cji.settings import override_settings

    env = ApiEnv(tmp_path, monkeypatch, CJI_API_RATE_PER_IP="2")
    with override_settings(env.settings), env:
        bad = {"Authorization": "Bearer cji_api_guess-000000000000000000000000000000000"}
        for _ in range(2):
            problem(env.client.get(f"{API}/me", headers=bad), 401, "invalid_token")
        problem(env.client.get(f"{API}/me", headers=bad), 429, "rate_limited")


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# server errors and leaks
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

class BrokenRepository:
    mode = "demo"
    data_source = "parquet"

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            from cji.repositories import RepositoryError

            raise RepositoryError(name, f"connection to postgresql://user:{SENTINEL}@db.internal/cji failed: "
                                        f"SELECT * FROM tracking_events WHERE x = '{SENTINEL}'")
        return fail

    def close(self):
        pass


@pytest.mark.parametrize("path", ["/metrics", "/friction", "/events"])
def test_storage_failures_are_503_without_detail(api, path):
    api.app.state.ctx.repository = BrokenRepository()
    r = api.client.get(f"{API}/journeys/{JOURNEY}{path}", headers=bearer(api.operator))
    problem(r, 503, "storage_unavailable")
    assert_clean(r)


def test_health_details_report_a_broken_store_without_detail(api):
    api.app.state.ctx.repository = BrokenRepository()
    r = api.client.get(f"{API}/health/details", headers=bearer(api.viewer))
    assert r.status_code == 200 and r.json()["status"] == "degraded"
    assert {c["name"]: c["status"] for c in r.json()["components"]}["repository"] == "unavailable"
    assert_clean(r)


def test_unexpected_exceptions_are_500_without_detail(api, monkeypatch):
    from cji.services import journeys

    def explode(*args, **kwargs):
        raise RuntimeError(f"{SENTINEL} at /secret/path/config.py line 3")

    monkeypatch.setattr(journeys, "list_journeys", explode)
    r = api.client.get(f"{API}/journeys", headers=bearer(api.viewer))
    body = problem(r, 500, "internal_error")
    assert set(body) == {"type", "title", "status", "detail", "code", "request_id"}
    assert_clean(r)


def test_checkpoint_store_failures_are_503(api):
    bad = api.tmp / "not-a-db"
    bad.mkdir()
    api.app.state.ctx.runs.db_path = bad
    for path in ("/runs", "/runs/00000000-0000-0000-0000-000000000000"):
        r = api.client.get(f"{API}{path}", headers=bearer(api.viewer))
        problem(r, 503, "storage_unavailable")
        assert_clean(r)


def test_secrets_never_appear_in_any_response(api):
    run_id = api.start_run(auto_approve=True)
    api.write_report(run_id)
    paths = ["/health", "/health/details", "/me", "/journeys", f"/journeys/{JOURNEY}", f"/journeys/{JOURNEY}/metrics",
             f"/journeys/{JOURNEY}/friction", f"/journeys/{JOURNEY}/insights", f"/journeys/{JOURNEY}/events?limit=3",
             "/runs", f"/runs/{run_id}", "/reports", f"/reports/j_{run_id}"]
    for path in paths:
        r = api.client.get(f"{API}{path}", headers=bearer(api.admin_all))
        assert r.status_code == 200, (path, r.text)
        for secret in (api.admin_all, api.viewer, api.operator, "c" * 40, str(api.tmp)):
            assert secret not in r.text, (path, secret)


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# request ids, headers, CORS, cursors
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_request_ids_are_echoed_or_generated(api):
    r = api.client.get(f"{API}/me", headers={**bearer(api.viewer), "X-Request-ID": "client-req-00042"})
    assert r.headers["x-request-id"] == "client-req-00042"
    r = api.client.get(f"{API}/me", headers={**bearer(api.viewer), "X-Request-ID": "bad id with spaces"})
    assert r.headers["x-request-id"] != "bad id with spaces" and len(r.headers["x-request-id"]) == 36
    for status, response in ((401, api.client.get(f"{API}/me", headers={"X-Request-ID": "client-req-00043"})),
                             (404, api.client.get(f"{API}/nope", headers={**bearer(api.viewer),
                                                                            "X-Request-ID": "client-req-00044"}))):
        assert response.status_code == status and response.json()["request_id"] == response.headers["x-request-id"]


def test_cors_allows_only_the_configured_origin(tmp_path, monkeypatch):
    from cji.settings import override_settings

    env = ApiEnv(tmp_path, monkeypatch, CJI_API_CORS_ORIGINS="http://localhost:3000")
    with override_settings(env.settings), env:
        pre = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET",
               "Access-Control-Request-Headers": "authorization"}
        r = env._client.options(f"{API}/journeys", headers=pre)
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:3000"
        r = env._client.options(f"{API}/journeys", headers={**pre, "Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in r.headers


def test_cursors_are_tied_to_their_query(api):
    r = api.client.get(f"{API}/journeys/{JOURNEY}/events?limit=2&step_id=payment_info", headers=bearer(api.operator))
    cursor = r.json()["page"]["next_cursor"]
    problem(api.client.get(f"{API}/journeys/{JOURNEY}/events?limit=2&step_id=landing_page&cursor={cursor}",
                           headers=bearer(api.operator)), 422, "invalid_cursor")
    tampered = cursor[:-2] + ("AA" if not cursor.endswith("AA") else "BB")
    problem(api.client.get(f"{API}/journeys/{JOURNEY}/events?limit=2&step_id=payment_info&cursor={tampered}",
                           headers=bearer(api.operator)), 422, "invalid_cursor")


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# OpenAPI
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_openapi_snapshot_matches_the_app(api):
    snapshot = json.loads((APP_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8"))
    assert api.app.openapi() == snapshot, "regenerate with: python -m cji.api.openapi_snapshot"


def test_openapi_document_is_valid_and_complete(api):
    from openapi_spec_validator import validate

    doc = api.app.openapi()
    validate(doc)
    assert doc["info"]["version"] == "1.0.0" and doc["openapi"].startswith("3.1")
    assert "bearerAuth" in doc["components"]["securitySchemes"]
    for path, item in doc["paths"].items():
        assert path.startswith(API)
        for method, op in item.items():
            codes = set(op["responses"])
            if path in (f"{API}/health", f"{API}/openapi.json"):
                assert "security" not in op or op["security"] == []
                continue
            assert op.get("security") == [{"bearerAuth": []}], (method, path)
            assert {"401", "429", "500"} <= codes, (method, path, codes)
            for code in codes - {"200", "202"}:
                content = op["responses"][code].get("content", {})
                assert list(content) == ["application/problem+json"], (method, path, code)


def test_every_contract_response_was_schema_checked(api):
    api.client.get(f"{API}/health")
    api.client.get(f"{API}/me", headers=bearer(api.viewer))
    assert api.client.checked >= 2


def test_docs_ui_only_in_development(api):
    problem(api._client.get(f"{API}/docs", headers=bearer(api.viewer)), 404, "not_found")
