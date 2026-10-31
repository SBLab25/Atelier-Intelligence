"""Spec 12 gate (T8): the installed `cji-api` against the gate's checkpoint store, reports and MCP servers.

Usage: python api_live_check.py <scripts dir> <app dir> <work dir> <paused run id>

Creates tokens with `cji-api-token`, starts `cji-api` (production settings: https origin, cursor secret), then checks
health, the served OpenAPI document against the snapshot, token roles and journey scopes, metrics, friction, events,
runs, approval of the paused run (202, replay, background report step polled to completed, 200 already approved),
report content headers, 401/403/404/429 problem responses and that no response leaks internals. Exit 1 on a failure.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS, APP, WORK, PAUSED = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
BASE = "http://127.0.0.1:8006/api/v1"
JOURNEY = "user_onboarding"
LEAKS = ("Traceback", "postgresql://", "SELECT ", 'File "', str(APP), "cji_api_")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> bool:
    results.append((bool(ok), label))
    print(("PASS " if ok else "FAIL ") + label, flush=True)
    return bool(ok)


def call(method: str, path: str, token: str | None = None, body: bytes | None = None,
         headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(BASE + path, data=body, method=method)
    for k, v in {**({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})}.items():
        req.add_header(k, v)
    try:
        with OPENER.open(req, timeout=60) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read()


def problem(status: int, headers: dict[str, str], body: bytes, want: int, code: str, label: str) -> None:
    ok = status == want and headers.get("content-type", "").startswith("application/problem+json")
    data = json.loads(body) if ok else {}
    ok = ok and data.get("code") == code and data.get("request_id") == headers.get("x-request-id")
    check(ok and not any(m in body.decode("utf-8", "replace") for m in LEAKS), f"{label}: {want} {code}")


def token(label: str, role: str, journey: str) -> str:
    out = subprocess.run([str(SCRIPTS / "cji-api-token.exe"), "--file", str(WORK / "api_tokens.json"), "create",
                          "--label", label, "--role", role, "--journey", journey],
                         capture_output=True, text=True, timeout=120, check=False)
    found = [line.strip() for line in out.stdout.splitlines() if line.strip().startswith("cji_api_")]
    check(out.returncode == 0 and len(found) == 1, f"cji-api-token create {label} ({role}, {journey})")
    return found[0] if found else ""


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    viewer = token("gate-viewer", "viewer", JOURNEY)
    operator = token("gate-operator", "operator", JOURNEY)
    other = token("gate-other", "operator", "other_journey")
    listed = subprocess.run([str(SCRIPTS / "cji-api-token.exe"), "--file", str(WORK / "api_tokens.json"), "list"],
                            capture_output=True, text=True, timeout=120, check=False)
    check(listed.returncode == 0 and "gate-viewer" in listed.stdout and "cji_api_" not in listed.stdout,
          "cji-api-token list shows ids and labels, never token values")
    stored = (WORK / "api_tokens.json").read_text(encoding="utf-8")
    check(viewer not in stored and operator not in stored, "token file stores hashes only")

    env = {**os.environ, "CJI_API_TOKENS_FILE": str(WORK / "api_tokens.json"),
           "CJI_API_CORS_ORIGINS": "https://app.example.test", "CJI_API_CURSOR_SECRET": secrets.token_urlsafe(36),
           "CJI_API_RATE_PER_IP": "20", "PYTHONUNBUFFERED": "1"}
    log = (WORK / "cji-api.log").open("w", encoding="utf-8")
    server = subprocess.Popen([str(SCRIPTS / "cji-api.exe")], cwd=APP, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            time.sleep(1)
            try:
                if call("GET", "/health")[0] == 200:
                    break
            except OSError:
                continue
        status, headers, body = call("GET", "/health")
        check(status == 200 and set(json.loads(body)) == {"status", "version", "mode"} and "x-request-id" in headers,
              "GET /health 200 {status, version, mode} with X-Request-ID")
        status, _, body = call("GET", "/openapi.json")
        snapshot = json.loads((APP / "openapi" / "v1.json").read_text(encoding="utf-8"))
        check(status == 200 and json.loads(body) == snapshot, "served /openapi.json equals openapi/v1.json")
        status, _, body = call("GET", "/docs")
        check(status == 404, "docs UI not served outside development")

        status, _, body = call("GET", "/me", viewer)
        check(status == 200 and json.loads(body)["role"] == "viewer" and viewer not in body.decode(), "GET /me")
        status, _, body = call("GET", "/journeys", viewer)
        check(status == 200 and [j["journey_id"] for j in json.loads(body)["data"]] == [JOURNEY], "GET /journeys")
        status, _, body = call("GET", f"/journeys/{JOURNEY}/metrics?days=30", viewer)
        check(status == 200 and len(json.loads(body)["steps"]) > 0, "GET metrics (demo Parquet)")
        status, _, body = call("GET", f"/journeys/{JOURNEY}/friction", viewer)
        check(status == 200 and len(json.loads(body)["scores"]) > 0, "GET friction")
        status, _, body = call("GET", f"/journeys/{JOURNEY}/events?limit=5", operator)
        page = json.loads(body) if status == 200 else {}
        check(status == 200 and len(page.get("data", [])) == 5 and page["page"]["next_cursor"], "GET events page 1")
        if page:
            status, _, body = call("GET", f"/journeys/{JOURNEY}/events?limit=5&cursor={page['page']['next_cursor']}",
                                   operator)
            second = json.loads(body) if status == 200 else {"data": []}
            first_ids = {e["event_id"] for e in page["data"]}
            check(status == 200 and not first_ids & {e["event_id"] for e in second["data"]}, "GET events page 2")
        problem(*call("GET", f"/journeys/{JOURNEY}/events", viewer), 403, "insufficient_role", "viewer events")
        problem(*call("GET", f"/journeys/{JOURNEY}/metrics", other), 403, "journey_forbidden", "other journey")
        problem(*call("GET", "/me"), 401, "missing_token", "no token")
        status, headers, _ = call("GET", "/me")
        check(headers.get("www-authenticate", "").startswith("Bearer"), "401 carries WWW-Authenticate: Bearer")
        problem(*call("GET", "/runs/00000000-0000-0000-0000-000000000000", viewer), 404, "run_not_found",
                "unknown run")
        problem(*call("GET", f"/runs/{PAUSED}", other), 404, "run_not_found", "run outside the token")
        problem(*call("GET", "/journeys?colour=red", viewer), 422, "validation_failed", "unknown query parameter")

        status, _, body = call("GET", "/runs?status=awaiting_approval", viewer)
        check(status == 200 and PAUSED in [r["run_id"] for r in json.loads(body)["data"]],
              "GET /runs?status=awaiting_approval lists the paused run")
        status, _, body = call("GET", f"/runs/{PAUSED}", viewer)
        check(status == 200 and json.loads(body)["status"] == "awaiting_approval", "GET /runs/{paused}")
        problem(*call("POST", f"/runs/{PAUSED}/approval", viewer, b"{}",
                      {"Content-Type": "application/json", "Idempotency-Key": "gate-viewer-0001"}),
                403, "insufficient_role", "viewer approval")
        problem(*call("POST", f"/runs/{PAUSED}/approval", operator, b"{}", {"Content-Type": "application/json"}),
                400, "idempotency_key_required", "approval without Idempotency-Key")
        key = {"Content-Type": "application/json", "Idempotency-Key": "gate-approve-0001"}
        body_in = b'{"comment": "approved by the Spec 12 gate"}'
        status, _, first = call("POST", f"/runs/{PAUSED}/approval", operator, body_in, key)
        check(status == 202 and json.loads(first)["already_approved"] is False, "POST approval 202")
        status, headers, again = call("POST", f"/runs/{PAUSED}/approval", operator, body_in, key)
        check(status == 202 and again == first and headers.get("idempotent-replayed") == "true", "approval replay")
        problem(*call("POST", f"/runs/{PAUSED}/approval", operator, b"{}", key), 409, "idempotency_key_reused",
                "same key, different body")
        final: dict = {}
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            status, _, body = call("GET", f"/runs/{PAUSED}", operator)
            final = json.loads(body) if status == 200 else {}
            if final.get("status") in ("completed", "failed") and not final.get("active"):
                break
            time.sleep(2)
        check(final.get("status") == "completed" and final.get("report_id"),
              f"background report step: run {final.get('status')}, report {final.get('report_id')}")
        status, _, body = call("POST", f"/runs/{PAUSED}/approval", operator, b"{}",
                               {"Content-Type": "application/json", "Idempotency-Key": "gate-approve-0002"})
        check(status == 200 and json.loads(body)["already_approved"] is True, "approve again: 200 already_approved")
        if final.get("report_id"):
            rid = final["report_id"]
            status, _, body = call("GET", f"/reports/{rid}", viewer)
            meta = json.loads(body) if status == 200 else {}
            check(status == 200 and meta.get("run_id") == PAUSED and meta.get("journey_id") == JOURNEY,
                  "GET /reports/{id}")
            status, headers, body = call("GET", f"/reports/{rid}/content", viewer)
            check(status == 200 and headers.get("content-type", "").startswith("text/html")
                  and "default-src 'none'" in headers.get("content-security-policy", "")
                  and headers.get("x-content-type-options") == "nosniff" and len(body) > 1000,
                  f"GET /reports/{{id}}/content: text/html, CSP, nosniff ({len(body)} bytes)")
            problem(*call("GET", f"/reports/{rid}", other), 404, "report_not_found", "report outside the token")

        limited = None
        for _ in range(30):
            status, headers, body = call("GET", "/me", "cji_api_gate-guess-000000000000000000000000000000")
            if status == 429:
                limited = (status, headers, body)
                break
        check(limited is not None and int(limited[1].get("retry-after", "0")) >= 1, "bad tokens: 429 with Retry-After")
        if limited:
            problem(*limited, 429, "rate_limited", "rate limited")
    finally:
        server.terminate()
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()
    text = (WORK / "cji-api.log").read_text(encoding="utf-8", errors="replace")
    check(viewer not in text and operator not in text and other not in text, "server log holds no token values")
    print("approval comment in the server log:", "approved by the Spec 12 gate" in text)
    failed = [label for ok, label in results if not ok]
    print(f"\nchecks: {len(results)}  passed: {len(results) - len(failed)}  failed: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
