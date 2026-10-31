"""
Spec 15 gate, phase C (design §18): a live deployment with canary markers, then the logs, metrics, trace, audit,
rotation and readiness checks. Offline: pgserver on loopback, LLM provider "none", dead proxy for everything else.
Never reads cji_agent/.env or the real database URLs: every process gets an explicit environment and a temporary home.

  python live_spec15.py --work DIR --out DIR [--frontend DIR]

Writes OUT/{logs,metrics,trace,audit,rotation}-check.json, OUT/ops-status.json, OUT/live.md, and
OUT/canary-markers.json + OUT/canary-paths.txt for ci/sensitive_scan.py (the gate runs the scan after phases D-E).
Marker values never appear in the report; markers.json is removed after the scan by the gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess  # nosec B404 - fixed argument lists, no shell
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "cji_agent"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "src"))
from tests._system import Postgres, System, free_port, http, status_of, wait_for  # noqa: E402

JOURNEY = "user_onboarding"
CANARY_JOURNEY = "canary_journey"
API = "/api/v1"
PY = sys.executable
REPORT: list[str] = []


def note(text: str) -> None:
    REPORT.append(text)
    print(text, flush=True)


def marker(name: str) -> str:
    return f"cjicanary{name.replace('_', '')}{secrets.token_hex(16)}"


def run(args: list[str], env: dict[str, str], cwd: Path, timeout: int = 900, stdout_only: bool = False) -> tuple[int, str]:
    proc = subprocess.run(args, cwd=cwd, env={**os.environ, **env}, capture_output=True, text=True,  # nosec B603
                          encoding="utf-8", errors="replace", timeout=timeout, check=False)
    return proc.returncode, proc.stdout if stdout_only else proc.stdout + proc.stderr


def save(out: Path, name: str, data: Any) -> None:
    (out / name).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


class Live:
    def __init__(self, work: Path, out: Path, frontend: Path) -> None:
        self.work, self.out, self.frontend = work, out, frontend
        self.responses = work / "responses"
        self.responses.mkdir(parents=True, exist_ok=True)
        self.secret: dict[str, str] = {k: marker(k) for k in (
            "admin_key", "cursor_secret", "session_secret", "groq_key", "anthropic_key", "openai_key",
            "langchain_key", "db_password")}
        self.user = {"user_id": marker("user"), "session_id": marker("session")}
        self.tokens: dict[str, str] = {}
        self.n = 0

    # ── HTTP helpers that keep every response body for the canary scan ─────────────────────────────────
    def call(self, method: str, url: str, *, keep_body: bool = True, **kw: Any) -> Any:
        """keep_body=False only for the one response that hands a new secret to its owner (key creation)."""
        r = http().request(method, url, timeout=kw.pop("timeout", 60), **kw)
        self.n += 1
        body = r.text if keep_body else "<body not recorded: returns the new key to the admin once, by design>"
        (self.responses / f"{self.n:03d}.txt").write_text(
            f"{method} {url} -> {r.status_code}\n{json.dumps(dict(r.headers))}\n{body}", encoding="utf-8")
        return r

    def auth(self, role: str, **extra: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[role]}", **extra}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--frontend", type=Path, default=ROOT / "frontend")
    args = parser.parse_args(argv)
    work, out = args.work.resolve(), args.out.resolve()
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    out.mkdir(parents=True, exist_ok=True)
    lv = Live(work, out, args.frontend.resolve())
    pg = Postgres(work / "pg")
    url = pg.url.replace("postgres@", f"postgres:{lv.secret['db_password']}@")  # trust auth ignores it; it must
    s = System(work / "sys", extra_env={                                           # still never be logged
        "CJI_MODE": "realtime", "DATABASE_URL": url, "SUPABASE_DATABASE_URL": "", "CJI_ADMIN_KEY": lv.secret["admin_key"],
        "CJI_API_CURSOR_SECRET": lv.secret["cursor_secret"], "GROQ_API_KEY": lv.secret["groq_key"],
        "ANTHROPIC_API_KEY": lv.secret["anthropic_key"], "OPENAI_API_KEY": lv.secret["openai_key"],
        "LANGCHAIN_API_KEY": lv.secret["langchain_key"], "CJI_LLM_PROVIDER": "none",
        "CJI_API_CORS_ORIGINS": "https://app.example.test", "REALTIME_WINDOW_MINUTES": "43200"})
    env = s.env()
    home = s.home
    audit = home / "data" / "audit"
    next_proc: subprocess.Popen[bytes] | None = None
    results: dict[str, Any] = {}
    try:
        # ── database: migrate, ingest the demo events ────────────────────────────────────────────────
        code, text = run([PY, "-m", "cji.ops.db_cli", "migrate", "up"], env, home)
        note(f"cji-db migrate up: exit {code}")
        csv = work / "events.csv"
        import pandas as pd
        events = pd.read_parquet(APP / "data" / "events.parquet")
        ts = pd.to_datetime(events["timestamp"], utc=True)  # realtime reads a window ending now (30 days here)
        events["timestamp"] = ts + (pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=10) - ts.max())
        events.to_csv(csv, index=False)
        code, text = run([PY, "-m", "cji.tools.ingest_json", str(csv)], env, home)
        note(f"cji-ingest-json demo events: exit {code}")
        # ── tokens (CLI: token.create audited) ───────────────────────────────────────────────────────
        for role in ("viewer", "operator", "admin"):
            code, text = run([PY, "-m", "cji.api.tokens_cli", "create", "--label", f"gate-{role}", "--role", role,
                              "--journey", JOURNEY, "--journey", CANARY_JOURNEY], env, home)
            lv.tokens[role] = re.search(r"cji_api_\S+", text).group(0)
            lv.secret[f"token_{role}"] = lv.tokens[role]
        # ── processes ────────────────────────────────────────────────────────────────────────────────
        s.start_mcp()
        s.start("api")
        s.start("collector")
        ready = wait_for(lambda: status_of(s.ready_url("api")) == 200 and
                         status_of(s.url("collector", "/health/ready")) == 200, 60)
        note(f"processes started; API and collector ready: {bool(ready)}")
        # ── collector: key create, admin denied, marker events, metrics ──────────────────────────────
        admin_hdr = {"X-CJI-Admin-Key": lv.secret["admin_key"]}
        denied = lv.call("POST", s.url("collector", "/admin/api-keys"), headers={"X-CJI-Admin-Key": "wrong-" + "x" * 30},
                         json={"journey_name": CANARY_JOURNEY, "description": "gate"}).status_code
        r = lv.call("POST", s.url("collector", "/admin/api-keys"), headers=admin_hdr, keep_body=False,
                    json={"journey_name": CANARY_JOURNEY, "description": "gate canary"})
        tracker = r.json().get("api_key", "") if r.status_code == 200 else ""
        lv.secret["tracker_key"] = tracker
        events = [{"timestamp": "2026-10-27T10:15:30.123Z", "event_id": f"evt-canary-{i:04d}-{uuid.uuid4().hex[:8]}",
                   "session_id": lv.user["session_id"], "user_id": lv.user["user_id"], "journey_name": CANARY_JOURNEY,
                   "step_id": "landing_page", "event_type": "page_view", "url": "https://app.example.test/",
                   "metadata": {}} for i in range(3)]
        collected = lv.call("POST", s.url("collector", "/collect/batch"), json={"api_key": tracker, "events": events})
        note(f"collector: admin with a wrong key HTTP {denied}; key create HTTP {r.status_code}; "
             f"marker batch HTTP {collected.status_code}")
        # ── API: auth failure, ingestion of marker rows, a run with approval ─────────────────────────
        bad = lv.call("GET", s.url("api", f"{API}/journeys"), headers={"Authorization": "Bearer cji_api_" + "x" * 43})
        rows = pd.DataFrame([{"event_id": f"ing-canary-{i}", "user_id": lv.user["user_id"],
                              "session_id": lv.user["session_id"], "journey_id": CANARY_JOURNEY, "step_id": "landing_page",
                              "event_type": "page_view", "timestamp": "2026-10-27T10:15:30Z", "duration_ms": 5,
                              "url": "", "metadata": "{}"} for i in range(3)])
        validation = lv.call("POST", s.url("api", f"{API}/ingestions/validations"), params={"filename": "canary.csv"},
                             data=rows.to_csv(index=False).encode(),
                             headers=lv.auth("admin", **{"Content-Type": "text/csv", "Idempotency-Key": _key()}))
        vid = validation.json().get("validation_id") if validation.ok else None
        written = lv.call("POST", s.url("api", f"{API}/ingestions"), json={"validation_id": vid, "write_mode": "append"},
                          headers=lv.auth("admin", **{"Idempotency-Key": _key()})) if vid else None
        request_id = f"gate-run-{uuid.uuid4().hex[:12]}"
        trace_api = uuid.uuid4().hex
        start = lv.call("POST", s.url("api", f"{API}/runs"), json={"journey_id": JOURNEY, "auto_approve": False},
                        headers=lv.auth("operator", **{"Idempotency-Key": _key(), "X-Request-ID": request_id,
                                                       "traceparent": f"00-{trace_api}-{secrets.token_hex(8)}-01"}))
        run_id = str(start.json().get("run_id")) if start.status_code == 202 else ""
        status = _wait(lv, s, run_id, {"awaiting_approval", "failed", "completed"})
        approve = lv.call("POST", s.url("api", f"{API}/runs/{run_id}/approval"), json={},
                          headers=lv.auth("operator", **{"Idempotency-Key": _key()})).status_code
        final = _wait(lv, s, run_id, {"failed", "completed"})
        lv.call("GET", s.url("api", f"{API}/runs/{run_id}/results"), headers=lv.auth("viewer"))
        reports = lv.call("GET", s.url("api", f"{API}/reports"), headers=lv.auth("viewer"))
        report_items = (reports.json().get("data") or []) if reports.ok else []
        if report_items:
            rid = report_items[0].get("report_id")
            lv.call("GET", s.url("api", f"{API}/reports/{rid}/content"), headers=lv.auth("viewer"))
        note(f"API: bad token HTTP {bad.status_code}; ingestion validate HTTP {validation.status_code}, write HTTP "
             f"{written.status_code if written is not None else '-'}; run {status} -> approve HTTP {approve} -> {final}; "
             f"reports listed {len(report_items)}")
        results["run"] = {"run_id": run_id, "status": final, "request_id": request_id, "trace_api": trace_api}
        # ── Next.js: production build with the marker session key, live browser tests, trace propagation ──
        next_env = {"CJI_SESSION_SECRET": lv.secret["session_secret"], "CJI_API_BASE_URL": s.url("api", ""),
                    "NEXT_TELEMETRY_DISABLED": "1", "NODE_ENV": "production"}
        code, text = run(["node", "node_modules/next/dist/bin/next", "build"], next_env, lv.frontend, timeout=1200)
        (work / "next-build.log").write_text(text, encoding="utf-8")
        note(f"next build (marker session key): exit {code}")
        npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
        e2e_env = {**next_env, "E2E_LIVE_API_URL": s.url("api", ""), "E2E_LIVE_TOKEN": lv.tokens["viewer"],
                   "E2E_LIVE_OPERATOR_TOKEN": lv.tokens["operator"]}
        e2e_env.pop("NODE_ENV")
        code, text = run([npx, "playwright", "test", "smoke.spec.ts", "live.spec.ts"], e2e_env, lv.frontend, timeout=1500)
        (work / "playwright-live.log").write_text(text, encoding="utf-8")
        outcome = [ln.strip() for ln in text.splitlines() if re.match(r"\s*\d+ (passed|failed|skipped|flaky)", ln)]
        results["e2e_live"] = {"exit": code, "outcome": outcome}
        note(f"browser tests against the live API (smoke + live): exit {code} {outcome}")
        port = free_port()
        next_log = (work / "next-server.log").open("wb")
        next_proc = subprocess.Popen(["node", "node_modules/next/dist/bin/next", "start", "--port", str(port)],  # nosec B603 B607
                                     cwd=lv.frontend, env={**os.environ, **next_env}, stdout=next_log,
                                     stderr=subprocess.STDOUT)
        wait_for(lambda: status_of(f"http://127.0.0.1:{port}/healthz") == 200, 60)
        me = http().get(s.url("api", f"{API}/me"), headers=lv.auth("viewer"), timeout=15).json()
        code, cookie = run(["node", "--disable-warning=ExperimentalWarning",
                            str(Path(__file__).with_name("seal_session.mjs"))],
                           {"CJI_SESSION_SECRET": lv.secret["session_secret"], "SEAL_TOKEN": lv.tokens["viewer"],
                            "SEAL_TOKEN_ID": me.get("token_id", ""), "SEAL_LABEL": me.get("label", "gate"),
                            "SEAL_ROLE": me.get("role", "viewer"), "SEAL_JOURNEYS": ",".join(me.get("journeys", []))},
                           lv.frontend, timeout=60)
        trace_next = uuid.uuid4().hex
        page = lv.call("GET", f"http://127.0.0.1:{port}/journeys/{JOURNEY}",
                       headers={"Cookie": f"cji_session={cookie.strip()}",
                                "traceparent": f"00-{trace_next}-{secrets.token_hex(8)}-01"})
        ready_next = status_of(f"http://127.0.0.1:{port}/readyz")
        results["next"] = {"page": page.status_code, "trace": trace_next, "readyz": ready_next}
        note(f"Next.js page with a sealed session HTTP {page.status_code}; /readyz HTTP {ready_next}")
        # ── rotation checks (live) ───────────────────────────────────────────────────────────────────
        rotation = {}
        code, text = run([PY, "-m", "cji.api.tokens_cli", "create", "--label", "gate-rotate", "--role", "viewer",
                          "--journey", JOURNEY], env, home)
        old = re.search(r"cji_api_\S+", text).group(0)
        lv.secret["token_rotate_old"] = old
        old_id = http().get(s.url("api", f"{API}/me"), headers={"Authorization": f"Bearer {old}"}, timeout=15).json()["token_id"]
        code, text = run([PY, "-m", "cji.api.tokens_cli", "rotate", old_id, "--overlap-hours", "0"], env, home)
        new = (re.search(r"cji_api_\S+", text) or re.search(r"$^", "")).group(0) if "cji_api_" in text else ""
        lv.secret["token_rotate_new"] = new or marker("unused")
        time.sleep(1.5)
        rotation["api_token"] = {"rotate_exit": code,
                                 "old_after": status_of(s.url("api", f"{API}/me"), headers={"Authorization": f"Bearer {old}"}),
                                 "new_after": status_of(s.url("api", f"{API}/me"), headers={"Authorization": f"Bearer {new}"})}
        revoke = lv.call("POST", s.url("collector", "/admin/api-keys/revoke"), headers=admin_hdr, json={"api_key": tracker})
        after = lv.call("POST", s.url("collector", "/collect/batch"),
                        json={"api_key": tracker, "events": [dict(events[0], event_id=f"evt-after-{uuid.uuid4().hex[:8]}")]})
        rotation["tracker_key"] = {"revoke": revoke.status_code, "batch_after": after.status_code}
        rotation_ok = (rotation["api_token"]["rotate_exit"] == 0 and rotation["api_token"]["old_after"] == 401
                       and rotation["api_token"]["new_after"] == 200 and revoke.status_code == 200
                       and after.status_code in (401, 403))
        save(out, "rotation-check.json", {"ok": rotation_ok, "detail": json.dumps(rotation)})
        note(f"rotation: {rotation}")
        # ── metrics ──────────────────────────────────────────────────────────────────────────────────
        scrapes = {"api": lv.call("GET", s.url("api", f"{API}/metrics"), headers=lv.auth("admin")).text,
                   "collector": lv.call("GET", s.url("collector", "/metrics"), headers=admin_hdr).text}
        for name in ("cji-journey-data", "cji-friction-engine", "cji-insight", "cji-report", "cji-ingestion-intelligence"):
            scrapes[name] = lv.call("GET", s.url(name, "/metrics")).text
        for name, text in scrapes.items():
            (work / f"metrics-{name}.txt").write_text(text, encoding="utf-8")
        need = {"api": ["cji_http_requests_total{", "cji_runs_finished_total{", "cji_auth_failures_total{",
                        "cji_ingestion_rows_total{"],
                "collector": ["cji_collector_events_total{", "cji_http_requests_total{"],
                "cji-insight": ["# TYPE cji_llm_calls_total counter"]}
        missing = {k: [m for m in v if m not in scrapes.get(k, "")] for k, v in need.items()}
        metrics_ok = not any(missing.values())
        save(out, "metrics-check.json", {"ok": metrics_ok, "detail": f"missing series: {missing}" if not metrics_ok
                                         else f"{sum(len(v) for v in need.values())} required series present in "
                                              f"{len(scrapes)} scrapes"})
        note(f"metrics: ok={metrics_ok} missing={missing}")
        # ── readiness, then one dependency down ──────────────────────────────────────────────────────
        started = ["api", "collector", "cji-journey-data", "cji-friction-engine", "cji-insight", "cji-report",
                   "cji-ingestion-intelligence"]
        status_cmd = [PY, "-m", "cji.ops.cli", "status", "--json", "--only", *started]
        code, text = run(status_cmd, env, home, stdout_only=True)
        statuses = _json_list(text)
        s.kill("cji-insight")
        code2, text2 = run(status_cmd, env, home, stdout_only=True)
        statuses2 = _json_list(text2)
        all_ready = len(statuses) == len(started) and all(x.get("status") == "ready" for x in statuses)
        down = [x.get("service") for x in statuses2 if x.get("status") != "ready"]
        save(out, "ops-status.json", {"ok": all_ready and code == 0 and code2 == 1 and down == ["cji-insight"],
                                      "detail": f"{len(statuses)} services ready: {all_ready} (exit {code}); with "
                                                f"cji-insight stopped: exit {code2}, not ready: {down}",
                                      "before": statuses, "after_stop": statuses2})
        note(f"cji-ops status: exit {code} -> {code2} after stopping cji-insight")
        # ── backup and restore (audited) ─────────────────────────────────────────────────────────────
        pg.create_database("cji_restore")
        b_env = {**env, "GATE_DB": url, "GATE_RESTORE_DB": url.rsplit("/", 1)[0] + "/cji_restore"}
        c1, _ = run([PY, "-m", "cji.ops.backup", "--database-url-env", "GATE_DB", "--pg-bin", str(pg.bin), "create",
                     "--out", str(work / "backup"), "--include-audit"], b_env, home)
        made = next(iter(sorted((work / "backup").glob("cji-backup-*"))), work / "backup")  # timestamped directory
        c2, _ = run([PY, "-m", "cji.ops.backup", "--database-url-env", "GATE_RESTORE_DB", "--pg-bin", str(pg.bin),
                     "restore", str(made), "--home", str(work / "restored"), "--confirm-database",
                     "cji_restore"], b_env, home)
        note(f"cji-backup create exit {c1}, restore exit {c2}")
    finally:
        if next_proc is not None:
            subprocess.run(["taskkill", "/PID", str(next_proc.pid), "/T", "/F"], capture_output=True, check=False)  # nosec B603 B607
        s.stop_all()
        try:
            pg.stop()
        except Exception:  # noqa: BLE001  # broad-except: teardown
            pass
    # ── logs: every line JSON; correlation ───────────────────────────────────────────────────────────
    logs_ok, logs_detail = check_logs(s.logs, work / "next-server.log", results)
    save(out, "logs-check.json", {"ok": logs_ok, "detail": logs_detail})
    note(f"logs: ok={logs_ok} {logs_detail}")
    # ── trace ────────────────────────────────────────────────────────────────────────────────────────
    run_id = results.get("run", {}).get("run_id", "")
    code, text = run([PY, "-m", "cji.ops.trace_cli", "show", run_id, "--audit-dir", str(audit), "--json"], env, home,
                     stdout_only=True)
    records = _json_list(text)
    services = sorted({str(r.get("service")) for r in records if r.get("service")})
    trace_ok = code == 0 and len(services) >= 3
    save(out, "trace-check.json", {"ok": trace_ok, "detail": f"run {run_id}: {len(records)} records from {services}"})
    note(f"trace: ok={trace_ok} services={services}")
    # ── audit ────────────────────────────────────────────────────────────────────────────────────────
    audit_ok, audit_detail = check_audit(audit)
    save(out, "audit-check.json", {"ok": audit_ok, "detail": audit_detail})
    note(f"audit: ok={audit_ok} {audit_detail}")
    # ── canary scan inputs (the gate runs ci/sensitive_scan.py) ──────────────────────────────────────
    save(out, "canary-markers.json", {"secret": {k: v for k, v in lv.secret.items() if v}, "user": lv.user})
    paths = [s.logs, home, lv.responses, work / "next-server.log", work / "playwright-live.log",
             work / "next-build.log", work / "restored", lv.frontend / ".next" / "static"]
    paths += [p for p in (work / "backup").rglob("*") if p.is_file() and p.suffix != ".dump"]  # dump: event store
    (out / "canary-paths.txt").write_text("\n".join(str(p) for p in paths), encoding="utf-8")
    (out / "live.md").write_text("# Live phase (gate C)\n\n" + "\n".join(f"- {line}" for line in REPORT) + "\n",
                                 encoding="utf-8")
    ok = all(json.loads((out / f).read_text(encoding="utf-8"))["ok"] for f in (
        "logs-check.json", "metrics-check.json", "trace-check.json", "audit-check.json", "rotation-check.json",
        "ops-status.json"))
    return 0 if ok and results.get("e2e_live", {}).get("exit") == 0 else 1


def _json_list(text: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(text[text.find("["):]) if "[" in text else []
    except ValueError:
        return []
    return value if isinstance(value, list) else []


def _key() -> str:
    return "gate-" + uuid.uuid4().hex[:20]


def _wait(lv: Live, s: System, run_id: str, wanted: set[str], timeout: float = 600) -> str:
    def probe() -> str | None:
        r = http().get(s.url("api", f"{API}/runs/{run_id}"), headers=lv.auth("viewer"), timeout=15)
        st = r.json().get("status") if r.ok else None
        return st if st in wanted else None
    return wait_for(probe, timeout, 2.0) or "timeout"


REQUIRED_FIELDS = ("ts", "level", "logger", "message", "service")


def check_logs(log_dir: Path, next_log: Path, results: dict[str, Any]) -> tuple[bool, str]:
    bad: dict[str, int] = {}
    total = 0
    lines_by: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(log_dir.glob("*.log")) + ([next_log] if next_log.is_file() else []):
        name = path.stem
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            total += 1
            if path == next_log and not raw.lstrip().startswith("{"):
                continue                       # Next.js banner lines ("▲ Next.js", "✓ Ready") are not log records
            try:
                rec = json.loads(raw)
                if not all(k in rec for k in REQUIRED_FIELDS):
                    raise ValueError
            except ValueError:
                bad[name] = bad.get(name, 0) + 1
                continue
            lines_by.setdefault(name, []).append(rec)
    run = results.get("run", {})
    api_lines = lines_by.get("api", [])
    run_line = [r for r in api_lines if r.get("request_id") == run.get("request_id") and r.get("run_id") == run.get("run_id")]
    mcp_lines = [r for n, recs in lines_by.items() if n.startswith("cji-") for r in recs if r.get("run_id") == run.get("run_id")]
    next_trace = results.get("next", {}).get("trace")
    from_next = [r for r in api_lines if r.get("trace_id") == next_trace]
    ok = not bad and bool(run_line) and bool(mcp_lines) and bool(from_next)
    return ok, (f"{total} lines; not JSON or missing fields: {bad or 'none'}; request {run.get('request_id')} -> run "
                f"{run.get('run_id')}: {len(run_line)} API lines, {len(mcp_lines)} MCP lines; Next.js trace "
                f"{next_trace} in {len(from_next)} API lines")


EXPECTED_ACTIONS = {"token.create", "token.rotate", "auth.failed", "run.start", "run.approve", "ingestion.validate",
                    "ingestion.write", "collector.key.create", "collector.key.revoke", "collector.admin.denied",
                    "backup.create", "backup.restore", "migration.apply"}
FORBIDDEN_KEYS = re.compile(r"(?i)(password|secret|token_value|api_key|authorization|cookie|comment|address|client_ip)")


def check_audit(directory: Path) -> tuple[bool, str]:
    path = directory / "security.jsonl"
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        return False, f"security.jsonl unreadable: {type(exc).__name__}"
    seen = {str(r.get("action")) for r in records}
    bad_keys = sorted({k for r in records for k in r if FORBIDDEN_KEYS.search(k)})
    missing = sorted(EXPECTED_ACTIONS - seen)
    ok = not missing and not bad_keys
    return ok, f"{len(records)} records, {len(seen)} actions; missing: {missing or 'none'}; forbidden fields: {bad_keys or 'none'}"


if __name__ == "__main__":
    raise SystemExit(main())
