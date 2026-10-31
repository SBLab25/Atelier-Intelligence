"""
Spec 15 (OD-169): failure injection and recovery with real processes. Each case starts its own deployment
(temporary home, free loopback ports) and records what it observed through `_system.record`.

Run with `pytest -m recovery` (CI stage "integration"). Never touches DATABASE_URL / Supabase: the database cases
use their own PostgreSQL started with pg_ctl.
"""

from __future__ import annotations

import contextlib
import json
import socket
import threading
import time
import uuid

import pytest

from tests._system import Postgres, System, http, record, status_of, wait_for

pytestmark = pytest.mark.recovery
JOURNEY = "user_onboarding"
API = "/api/v1"


def _auth(token: str, key: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = "rk-" + uuid.uuid4().hex[:20]
    return headers


def _start_run(system: System, token: str) -> str:
    r = http().post(
        system.url("api", f"{API}/runs"),
        headers=_auth(token, key=True),
        json={"journey_id": JOURNEY, "auto_approve": True},
        timeout=30,
    )
    assert r.status_code == 202, r.text
    return str(r.json()["run_id"])


def _run(system: System, token: str, run_id: str) -> dict:
    r = http().get(system.url("api", f"{API}/runs/{run_id}"), headers=_auth(token), timeout=10)
    return r.json() if r.status_code == 200 else {"status": f"http {r.status_code}"}


def _status_in(system: System, token: str, run_id: str, wanted: set[str]) -> dict | None:
    run = _run(system, token, run_id)
    return run if run.get("status") in wanted else None


def _wait_status(system: System, token: str, run_id: str, wanted: set[str], timeout: float = 180) -> dict:
    return wait_for(lambda: _status_in(system, token, run_id, wanted), timeout, 1.0) or _run(system, token, run_id)


def _busy(system: System, token: str, run_id: str) -> dict | None:
    """The run while it is running and at least one step has succeeded."""
    run = _run(system, token, run_id)
    steps = (run.get("steps") or {}).values()
    started = any((st or {}).get("status") == "succeeded" for st in steps)
    return run if run.get("status") == "running" and started else None


def _resume_accepted(system: System, token: str, run_id: str) -> int | None:
    return 202 if _resume(system, token, run_id) == 202 else None


def _resume(system: System, token: str, run_id: str) -> int:
    r = http().post(system.url("api", f"{API}/runs/{run_id}/resume"), headers=_auth(token, key=True), timeout=30)
    return r.status_code


@pytest.fixture
def system(tmp_path):
    made: list[System] = []

    def make(**env: str) -> System:
        s = System(tmp_path / f"s{len(made)}", extra_env=env)
        made.append(s)
        return s

    yield make
    for s in made:
        s.stop_all()


# 1 ── database outage while the API and the collector run ────────────────────────────────────────────────


def test_database_outage_and_recovery_without_restart(system, tmp_path):
    from cji.migrations import runner

    pg = Postgres(tmp_path / "pg")
    try:
        runner.up(runner.engine_for(pg.url))
        runner._engines.pop(pg.url).dispose()
        s = system(CJI_MODE="realtime", DATABASE_URL=pg.url, SUPABASE_DATABASE_URL="")
        s.start("api")
        s.start("collector")
        viewer = s.token("viewer")
        metrics = s.url("api", f"{API}/journeys/{JOURNEY}/metrics")
        assert wait_for(lambda: status_of(s.ready_url("api")) == 200, 30)
        collector_ready = s.url("collector", "/health/ready")
        assert wait_for(lambda: status_of(collector_ready) == 200, 30)
        from tests.test_collector import batch, ids, wire

        def collect(prefix):
            return (
                http()
                .post(
                    s.url("collector", "/collect/batch"),
                    timeout=10,
                    json=batch(*[wire(i) for i in ids(prefix, 2)], key="cji_dev_localtest"),
                )
                .status_code
            )

        assert collect("before") == 200
        pg.stop()
        # Connection refused takes ~2 s per attempt on Windows; allow the checks time to answer.
        down = {
            "api_ready": status_of(s.ready_url("api"), timeout=30),
            "api_metrics": status_of(metrics, timeout=30, headers=_auth(viewer)),
            "collector_ready": status_of(collector_ready, timeout=30),
            "collect": collect("during"),
        }
        pg.start()
        back = wait_for(lambda: status_of(s.ready_url("api")) == 200 and status_of(collector_ready) == 200, 60)
        after = {"api_metrics": status_of(metrics, headers=_auth(viewer)), "collect": collect("after")}
        ok = (
            down == {"api_ready": 503, "api_metrics": 503, "collector_ready": 503, "collect": 503}
            and bool(back)
            and after == {"api_metrics": 200, "collect": 200}
        )
        record(
            "database outage",
            "readiness 503 and requests 503 while PostgreSQL is down; ready again without a restart",
            f"during outage {down}; recovered={bool(back)}; after {after}",
            ok,
        )
        assert ok, (down, back, after)
    finally:
        with contextlib.suppress(Exception):  # teardown of a server that may already be stopped
            pg.stop()


# 2 ── an MCP server dies during a run ────────────────────────────────────────────────────────────────────


def test_mcp_server_death_fails_the_run_and_resume_completes(system):
    s = system()
    s.start_mcp()
    s.start("api")
    token = s.token("operator")
    run_id = _start_run(s, token)
    s.kill("cji-report")  # the last step's server
    failed = _wait_status(s, token, run_id, {"failed", "completed"})
    s.start("cji-report")
    resumed = _resume(s, token, run_id)
    done = _wait_status(s, token, run_id, {"completed"})  # 202 returns the run as it was: still "failed"
    ok = failed.get("status") == "failed" and resumed == 202 and done.get("status") == "completed"
    record(
        "MCP server killed during a run",
        "run failed at the report step; after the server is back, resume completes",
        f"status after kill={failed.get('status')} failure={failed.get('failure')}; resume HTTP "
        f"{resumed}; final={done.get('status')} {done.get('failure') or ''}",
        ok,
    )
    assert ok, (failed, resumed, done)


# 3 ── the API dies during a background run ───────────────────────────────────────────────────────────────


class Blackhole:
    """A proxy that accepts connections and never answers: LLM calls through it wait until their timeout."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(50)
        self.port = self.sock.getsockname()[1]
        self.conns: list[socket.socket] = []
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.conns.append(conn)

    def close(self) -> None:
        for c in self.conns:
            c.close()
        self.sock.close()


def test_api_death_during_a_run_is_resumable_after_restart(system):
    hole = Blackhole()
    try:
        proxy = f"http://127.0.0.1:{hole.port}"
        s = system(
            CJI_LLM_PROVIDER="groq",
            GROQ_API_KEY="recovery-dummy-key-0000",
            HTTPS_PROXY=proxy,
            HTTP_PROXY=proxy,
            CJI_LLM_TIMEOUT_S="3",
            CJI_LLM_DEADLINE_S="5",
            CJI_LLM_RETRY_ATTEMPTS="1",
        )
        s.start_mcp()
        s.start("api")
        token = s.token("operator")
        run_id = _start_run(s, token)
        busy = wait_for(lambda: _busy(s, token, run_id), 60, 0.3)
        s.kill("api")
        time.sleep(1)
        s.start("api")
        interrupted = _run(s, token, run_id)
        resumed = wait_for(lambda: _resume_accepted(s, token, run_id), 30, 1.0)
        done = _wait_status(s, token, run_id, {"completed", "failed"}, timeout=240)
        ok = (
            bool(busy)
            and interrupted.get("status") != "completed"
            and resumed == 202
            and done.get("status") == "completed"
        )
        record(
            "API killed during a background run",
            "after a restart the run is resumable and completes",
            f"killed while {busy.get('status') if busy else 'not running'}; after restart "
            f"status={interrupted.get('status')} active={interrupted.get('active')}; resume HTTP {resumed}; "
            f"final={done.get('status')}",
            ok,
        )
        assert ok, (busy, interrupted, resumed, done)
    finally:
        hole.close()


# 4 ── LLM provider unreachable ───────────────────────────────────────────────────────────────────────────


def test_unreachable_llm_provider_falls_back_with_provenance(system):
    s = system(
        CJI_LLM_PROVIDER="groq",
        GROQ_API_KEY="recovery-dummy-key-0000",
        CJI_LLM_RETRY_ATTEMPTS="1",
        CJI_LLM_DEADLINE_S="5",
    )  # HTTPS_PROXY is the dead port of the test environment
    s.start_mcp()
    s.start("api")
    token = s.token("operator")
    run_id = _start_run(s, token)
    done = _wait_status(s, token, run_id, {"completed", "failed"})
    results = http().get(s.url("api", f"{API}/runs/{run_id}/results"), headers=_auth(token), timeout=10).json()
    sources = sorted({str((i.get("provenance") or {}).get("source")) for i in results.get("insights", [])})
    narrative = (results.get("narrative_provenance") or {}).get("source")
    ok = done.get("status") == "completed" and sources == ["fallback"] and narrative == "fallback"
    record(
        "LLM provider unreachable",
        "run completes; insights and narrative carry provenance source=fallback",
        f"final={done.get('status')}; insight sources={sources}; narrative source={narrative}",
        ok,
    )
    assert ok, (done, sources, narrative)


# 5 ── reports directory unwritable ───────────────────────────────────────────────────────────────────────


def test_unwritable_reports_directory_fails_clearly_and_resume_completes(system):
    import shutil

    s = system()
    reports = s.home / "reports"
    s.start_mcp()
    s.start("api")
    token = s.token("operator")
    r = http().post(
        s.url("api", f"{API}/runs"),
        headers=_auth(token, key=True),
        json={"journey_id": JOURNEY, "auto_approve": False},
        timeout=30,
    )
    assert r.status_code == 202, r.text
    run_id = str(r.json()["run_id"])
    paused = _wait_status(s, token, run_id, {"awaiting_approval", "failed", "completed"})
    if reports.exists():
        shutil.rmtree(reports)
    reports.write_text("not a directory", encoding="utf-8")  # the report step can no longer write
    approved = (
        http()
        .post(s.url("api", f"{API}/runs/{run_id}/approval"), headers=_auth(token, key=True), json={}, timeout=30)
        .status_code
    )
    failed = _wait_status(s, token, run_id, {"failed", "completed"})
    blocked = http().post(
        s.url("api", f"{API}/runs"),
        headers=_auth(token, key=True),
        json={"journey_id": JOURNEY, "auto_approve": True},
        timeout=30,
    )
    other = (
        _wait_status(s, token, str(blocked.json().get("run_id")), {"failed", "completed"})
        if blocked.status_code == 202
        else {}
    )  # frees the run slot (max_active_runs)
    reports.unlink()
    reports.mkdir()
    resumed = _resume(s, token, run_id)
    done = _wait_status(s, token, run_id, {"completed"})  # 202 returns the run as it was: still "failed"
    written = sorted(p.name for p in reports.glob("*.html"))
    ok = (
        paused.get("status") == "awaiting_approval"
        and approved == 202
        and failed.get("status") == "failed"
        and resumed == 202
        and done.get("status") == "completed"
        and bool(written)
    )
    record(
        "reports directory unwritable",
        "report step fails with a failure code; after the fix resume completes and writes the report",
        f"paused={paused.get('status')}; approval HTTP {approved}; "
        f"status={failed.get('status')} failure={json.dumps(failed.get('failure'))}; a new run meanwhile: HTTP "
        f"{blocked.status_code}, ended {other.get('status')} {(other.get('failure') or {}).get('code') or ''}; "
        f"resume HTTP {resumed}; final={done.get('status')}; reports={len(written)}",
        ok,
    )
    assert ok, (paused, approved, failed, resumed, done, written)


# 6 ── corrupt token file ─────────────────────────────────────────────────────────────────────────────────


def test_corrupt_token_file_is_503_until_fixed(system):
    s = system()
    s.start("api")
    token = s.token("viewer")
    path = s.home / "data" / "api_tokens.json"
    good = path.read_bytes()
    journeys = s.url("api", f"{API}/journeys")
    before = status_of(journeys, headers=_auth(token))
    path.write_text("{ broken", encoding="utf-8")
    broken = {"request": status_of(journeys, headers=_auth(token)), "ready": status_of(s.ready_url("api"))}
    path.write_bytes(good)
    after = wait_for(lambda: status_of(journeys, headers=_auth(token)) == 200, 10)
    ok = before == 200 and broken == {"request": 503, "ready": 503} and bool(after)
    record(
        "corrupt token file",
        "authenticated requests 503 service_misconfigured and readiness 503; normal "
        "again once the file is restored, without a restart",
        f"before {before}; broken {broken}; restored ok={bool(after)}",
        ok,
    )
    assert ok, (before, broken, after)


# 7 ── rate-limit flood ───────────────────────────────────────────────────────────────────────────────────


def test_rate_limit_flood_recovers_after_the_window(system):
    s = system(CJI_API_RATE_PER_TOKEN="5")
    s.start("api")
    token = s.token("viewer")
    journeys = s.url("api", f"{API}/journeys")
    session = http()
    codes = [session.get(journeys, headers=_auth(token), timeout=5) for _ in range(8)]
    limited = [r for r in codes if r.status_code == 429]
    retry_after = int(limited[0].headers.get("Retry-After", "0")) if limited else 0
    time.sleep(retry_after + 1)
    after = session.get(journeys, headers=_auth(token), timeout=5).status_code
    ok = bool(limited) and retry_after > 0 and after == 200
    record(
        "rate-limit flood",
        "429 with Retry-After once the per-token limit is used; 200 after the wait",
        f"statuses {[r.status_code for r in codes]}; Retry-After {retry_after}s; after the wait {after}",
        ok,
    )
    assert ok, ([r.status_code for r in codes], retry_after, after)
