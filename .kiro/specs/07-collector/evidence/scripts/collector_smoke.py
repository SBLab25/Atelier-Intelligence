"""
Spec 07 T7: start the collector with uvicorn (CJI_ENV=production) against a throwaway pgserver
database and exercise the public contract over real HTTP. Never touches DATABASE_URL / Supabase.
Prints one line per check and exits 1 if any check fails.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import requests

APP = Path(__file__).resolve().parents[5] / "cji_agent"
ADMIN = secrets.token_urlsafe(32)
ORIGIN = "https://app.example.test"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def event(event_id: str, **over):
    return {"timestamp": "2026-10-27T10:15:30.123Z", "event_id": event_id, "session_id": "sess-SMOKESESS01",
            "user_id": "user-SMOKEUSER01", "journey_name": "user_onboarding", "step_id": "sign_up_form",
            "event_type": "click", "url": "https://smoke-host.example/signup?x=1", "metadata": {"m": "SMOKEMETA01"},
            **over}


def main() -> int:
    import pgserver

    tmp = tempfile.mkdtemp(prefix="cji_s07_smoke_")
    server = pgserver.get_server(os.path.join(tmp, "pg"), cleanup_mode="stop")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "CJI_ENV": "production", "DATABASE_URL": server.get_uri(), "CJI_ADMIN_KEY": ADMIN,
           "CJI_CORS_ORIGINS": ORIGIN, "CJI_MODE": "realtime", "CJI_KEEPALIVE_URL": ""}
    # cji_agent/.env exists (live Supabase): the process environment wins over it, so every setting the
    # collector uses is given here; SUPABASE_DATABASE_URL stays the gate's dead URL (DATABASE_URL wins).
    log_path = Path(tmp) / "uvicorn.log"
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "collector.api:app", "--host", "127.0.0.1",
                             "--port", str(port), "--log-level", "info"], cwd=APP, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    http = requests.Session()
    http.trust_env = False                      # loopback only; ignore the gate's dead proxy
    try:
        for _ in range(60):
            try:
                if http.get(f"{base}/health/live", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.5)
        check("liveness", http.get(f"{base}/health/live", timeout=5).json() == {"status": "ok"})
        check("readiness", http.get(f"{base}/health/ready", timeout=5).json() == {"status": "ready"})

        r = http.post(f"{base}/collect/batch", json={"api_key": "cji_unknown_key_000", "events": [event("evt-smoke-0000")]},
                      timeout=10)
        check("unknown key 401", r.status_code == 401, str(r.status_code))
        r = http.get(f"{base}/live/stats", timeout=5)
        check("live/stats without admin key 403", r.status_code == 403, str(r.status_code))

        r = http.post(f"{base}/admin/api-keys", json={"journey_name": "user_onboarding", "description": "smoke"},
                      headers={"X-CJI-Admin-Key": ADMIN}, timeout=10)
        key = r.json().get("api_key", "")
        check("admin creates key", r.status_code == 200 and key.startswith("cji_live_"), str(r.status_code))

        ids = [f"evt-smoke-{uuid.uuid4()}" for _ in range(3)]
        body = {"api_key": key, "events": [event(i) for i in ids]}
        r = http.post(f"{base}/collect/batch", json=body, headers={"X-CJI-Key": key, "X-Request-ID": "smoke-req-0001"},
                      timeout=10)
        j = r.json()
        check("batch stored", r.status_code == 200 and (j["status"], j["accepted"]) == ("stored", 3), json.dumps(j))
        check("request id echoed", r.headers.get("X-Request-ID") == "smoke-req-0001" and j["request_id"] == "smoke-req-0001")
        r = http.post(f"{base}/collect/batch", json=body, timeout=10)
        j = r.json()
        check("retry is duplicates", r.status_code == 200 and (j["accepted"], j["duplicates"]) == (0, 3), json.dumps(j))

        beacon = {"api_key": key, "events": [event(f"evt-smoke-{uuid.uuid4()}", event_type="abandon")]}
        r = http.post(f"{base}/collect/batch", data=json.dumps(beacon),
                      headers={"Content-Type": "text/plain;charset=UTF-8"}, timeout=10)
        check("sendBeacon text/plain stored", r.status_code == 200 and r.json()["accepted"] == 1, str(r.status_code))

        mixed = {"api_key": key, "events": [event(f"evt-smoke-{uuid.uuid4()}"), event("evt-smoke-bad-0001", event_type="scroll")]}
        r = http.post(f"{base}/collect/batch", json=mixed, timeout=10)
        j = r.json()
        check("partial 207", r.status_code == 207 and (j["accepted"], j["rejected"]) == (1, 1), json.dumps(j))

        big = {"api_key": key, "events": [event(f"evt-smoke-{i:04d}-big", metadata={"b": "x" * 8000}) for i in range(40)]}
        r = http.post(f"{base}/collect/batch", json=big, timeout=10)
        check("oversized body 413", r.status_code == 413, str(r.status_code))

        r = http.get(f"{base}/live/stats?minutes=43200", headers={"X-CJI-Admin-Key": ADMIN}, timeout=10)
        stats = {s["step"]: s["count"] for s in r.json().get("stats", [])}
        check("live/stats with admin key", r.status_code == 200 and stats.get("sign_up_form") == 5, json.dumps(stats))
        check("/health count", http.get(f"{base}/health", timeout=5).json() == {"status": "ok", "live_events_count": 5})

        pre = http.options(f"{base}/collect/batch", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                                                             "Access-Control-Request-Headers": "content-type,x-cji-key"},
                           timeout=5)
        check("CORS preflight for configured origin", pre.headers.get("access-control-allow-origin") == ORIGIN)
        pre = http.options(f"{base}/collect/batch", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET",
                                                             "Access-Control-Request-Headers": "x-cji-admin-key"},
                           timeout=5)
        check("CORS refuses admin header", pre.status_code == 400, str(pre.status_code))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        server.cleanup()

    server_log = log_path.read_text(encoding="utf-8", errors="replace")
    leaked = [s for s in (key, ADMIN, "SMOKESESS01", "SMOKEUSER01", "evt-smoke-", "smoke-host.example", "SMOKEMETA01")
              if s and s in server_log]
    check("server log has no keys, ids, URLs or metadata", not leaked, str(leaked))
    print("---- uvicorn log (collector lines) ----")
    print("\n".join(line for line in server_log.splitlines() if "collect" in line or "ERROR" in line)[:4000])
    failed = [n for n, ok, _ in results if not ok]
    print(f"smoke: {len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
