"""
Rollback drill (Spec 15, OD-175): `python ci/rollback_drill.py --old-wheel W --old-frontend DIR --work DIR --out DIR`.

Runs the upgrade and the rollback for real, offline, in a temporary work directory with its own PostgreSQL
(pgserver, never DATABASE_URL / Supabase):

  1. venvs for the old release (wheel 0.11.0) and the new one (wheel built here from cji_agent/), installed with
     `pip --no-deps --no-index`; dependencies come from this interpreter's site-packages (the tested lock set).
  2. old release: ingest the demo events into PostgreSQL (`cji-ingest-json`, tables created the old way) and run
     an analysis through its API and MCP servers.
  3. `cji-backup create` + `verify` before the upgrade.
  4. new release: `cji-db migrate up`, run the same analysis, compare with the old result; the pre-Spec 15 frontend
     is built and its smoke test runs against this API.
  5. configuration rollback: `CJI_API_WRITE_OPERATIONS=false` stops start/resume/ingestion, reads still work.
  6. schema and release rollback: `cji-db migrate down --to 1`, the old release runs again and must give the same
     result; `migrate up` again (up/down/up).
  7. `cji-backup restore` into a fresh database and home; row counts and table checksums must equal the source.

Writes OUT/rollback-drill.md (every command, exit code and compared value) and OUT/rollback-drill.json (flags read
by ci/release_check.py). Exit 0 when every flag is true.
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
import sysconfig
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "cji_agent"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "src"))
from tests._system import Postgres, System, http, wait_for  # noqa: E402

JOURNEY = "user_onboarding"
API = "/api/v1"
WINDOW_MINUTES = 43200  # 30 days: the largest realtime window the API accepts


def recent(events: Any) -> Any:
    """The demo events moved in time so the newest is 10 minutes old (realtime mode reads a window ending now)."""
    import pandas as pd

    ts = pd.to_datetime(events["timestamp"], utc=True)
    shift = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=10) - ts.max()
    out = events.copy()
    out["timestamp"] = ts + shift
    return out


VOLATILE = (
    "run_id",
    "thread",
    "_at",
    "time",
    "duration",
    "path",
    "url",
    "sha256",
    "generated",
    "started",
    "finished",
    "created",
    "updated",
    "request",
    "trace",
    "elapsed",
    "latency",
    "file",
    "filename",
    "href",
)


class Drill:
    def __init__(self, work: Path) -> None:
        self.work = work
        self.steps: list[dict[str, Any]] = []
        self.flags: dict[str, Any] = {}
        self.systems: list[System] = []

    # ── recording ──────────────────────────────────────────────────────────────────────────────────────────
    def record(self, step: str, command: str, code: int | str, detail: str) -> None:
        self.steps.append({"step": step, "command": command, "exit": code, "detail": detail})
        print(f"[{code}] {step}: {detail}", flush=True)

    def cmd(
        self,
        step: str,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
        timeout: int = 900,
        show: str = "",
    ) -> tuple[int, str]:
        full = {**os.environ, **(env or {})}
        try:
            proc = subprocess.run(
                args,
                cwd=cwd or self.work,
                env=full,
                capture_output=True,
                text=True,  # nosec B603
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            code, out = proc.returncode, proc.stdout + proc.stderr
        except subprocess.TimeoutExpired:
            code, out = -1, f"timed out after {timeout}s"
        log = self.work / "logs" / f"{len(self.steps):02d}.log"
        log.parent.mkdir(exist_ok=True)
        log.write_text(
            f"$ {' '.join(args)}\n{re.sub(r'cji_api_[A-Za-z0-9_-]+', 'cji_api_<redacted>', out)}", encoding="utf-8"
        )
        tail = [ln for ln in out.strip().splitlines() if ln.strip()][-1:] or [""]
        self.record(step, " ".join(_short(a) for a in args), code, show or tail[0][:300])
        return code, out


def _short(arg: str) -> str:
    """Command lines in the report: paths relative to the work directory, no secrets (none are passed)."""
    return arg.replace(str(ROOT), "<repo>")


def site_packages(venv: Path) -> Path:
    return venv / "Lib" / "site-packages" if os.name == "nt" else next((venv / "lib").glob("python*/site-packages"))


def venv_python(venv: Path) -> str:
    return str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))


def make_venv(d: Drill, name: str, wheel: Path) -> str:
    venv = d.work / name
    code, out = d.cmd(f"{name}: create venv", [sys.executable, "-m", "venv", str(venv)], timeout=600)
    if code != 0 or not site_packages(venv).is_dir():
        raise RuntimeError(f"venv {name} incomplete (exit {code}): {out.strip()[-300:]}")
    # addsitedir also processes the dependencies' own .pth files (pywin32); the venv's site-packages stays first,
    # so `cji` is imported from the installed wheel (checked below).
    deps = sysconfig.get_paths()["purelib"]
    (site_packages(venv) / "cji-drill-deps.pth").write_text(
        f"import site; site.addsitedir({deps!r})\n", encoding="utf-8"
    )
    py = venv_python(venv)
    d.cmd(
        f"{name}: install {wheel.name}",
        [
            py,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "-q",
            str(wheel),
        ],
    )
    code, out = d.cmd(
        f"{name}: installed version",
        [
            py,
            "-c",
            (
                "import importlib.metadata as m, cji, pathlib, sys; "
                "print(m.version('cji-agent'), pathlib.Path(cji.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()))"
            ),
        ],
    )
    words = out.split()
    if code != 0 or len(words) < 2 or words[-1] != "True" or not wheel.name.startswith(f"cji_agent-{words[-2]}-"):
        raise RuntimeError(f"{name}: cji is not imported from the installed {wheel.name}: {out.strip()[-200:]}")
    return py


def normalise(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: normalise(v) for k, v in sorted(value.items()) if not any(t in k.lower() for t in VOLATILE)}
    if isinstance(value, list):
        return [normalise(v) for v in value]
    if isinstance(value, float):
        return round(value, 6)
    return value


def common(a: Any, b: Any) -> tuple[Any, Any]:
    """The parts of two results that both releases produce (new fields of 0.15.0 are not a difference)."""
    if isinstance(a, dict) and isinstance(b, dict):
        keys = sorted(set(a) & set(b))
        pairs = [common(a[k], b[k]) for k in keys]
        return dict(zip(keys, (p[0] for p in pairs))), dict(zip(keys, (p[1] for p in pairs)))
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        pairs = [common(x, y) for x, y in zip(a, b)]
        return [p[0] for p in pairs], [p[1] for p in pairs]
    return a, b


def compare(d: Drill, step: str, a: dict[str, Any], b: dict[str, Any]) -> bool:
    x, y = common(normalise(a), normalise(b))
    equal = x == y and bool(x)
    detail = f"{len(json.dumps(x))} bytes compared, equal={equal}"
    if not equal:
        diffs = [k for k in (x if isinstance(x, dict) else {}) if x.get(k) != y.get(k)]
        detail += f"; differing keys: {diffs[:10]}"
    d.record(step, "compare normalised results", 0 if equal else 1, detail)
    return equal


def token(d: Drill, py: str, path: Path, role: str) -> str:
    code, out = d.cmd(
        f"token ({role})",
        [
            py,
            "-m",
            "cji.api.tokens_cli",
            "--file",
            str(path),
            "create",
            "--label",
            f"drill-{role}-{uuid.uuid4().hex[:6]}",
            "--role",
            role,
            "--journey",
            JOURNEY,
        ],
        show="token created (value not recorded)",
    )
    found = [w for w in out.split() if w.startswith("cji_api_")]
    if code != 0 or not found:
        raise RuntimeError(f"token creation failed (exit {code})")
    return found[0]


def analysis(
    d: Drill, label: str, py: str, db_url: str, *, keep: bool = False
) -> tuple[dict[str, Any], System | None, str]:
    """Start MCP servers and the API of one release, run the journey with auto-approval, return its results."""
    s = System(
        d.work / f"sys-{label}",
        python=py,
        extra_env={
            "CJI_MODE": "realtime",
            "DATABASE_URL": db_url,
            "SUPABASE_DATABASE_URL": "",
            "REALTIME_WINDOW_MINUTES": str(WINDOW_MINUTES),
        },
    )
    d.systems.append(s)
    tok = token(d, py, s.home / "data" / "api_tokens.json", "operator")
    s.start("collector")  # a deployment runs it; 0.11.0 creates live_events and api_keys when it starts
    s.start_mcp()
    s.start("api")
    auth = {"Authorization": f"Bearer {tok}"}
    r = http().post(
        s.url("api", f"{API}/runs"),
        timeout=60,
        json={"journey_id": JOURNEY, "auto_approve": True, "window_minutes": WINDOW_MINUTES},
        headers={**auth, "Idempotency-Key": "drill-" + uuid.uuid4().hex[:16]},
    )
    if r.status_code != 202:
        d.record(f"{label}: start run", "POST /api/v1/runs", r.status_code, r.text[:200])
        return {}, s if keep else _stop(s), tok
    run_id = str(r.json()["run_id"])
    run = (
        wait_for(
            lambda: (lambda x: x if x.get("status") in ("completed", "failed") else None)(
                http().get(s.url("api", f"{API}/runs/{run_id}"), headers=auth, timeout=15).json()
            ),
            600,
            2.0,
        )
        or {}
    )
    status = run.get("status")
    results = http().get(s.url("api", f"{API}/runs/{run_id}/results"), headers=auth, timeout=30)
    metrics = http().get(s.url("api", f"{API}/journeys/{JOURNEY}/metrics"), headers=auth, timeout=30)
    d.record(
        f"{label}: analysis run",
        "POST /runs (auto_approve) + GET results, metrics",
        0 if status == "completed" else 1,
        f"status={status} failure={(run.get('failure') or {}).get('code')}; results HTTP {results.status_code}; "
        f"metrics HTTP {metrics.status_code}",
    )
    out = {
        "status": status,
        "results": results.json() if results.ok else {},
        "metrics": metrics.json() if metrics.ok else {},
    }
    (d.work / f"result-{label}.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out, (s if keep else _stop(s)), tok


def _stop(s: System) -> None:
    s.stop_all()
    return None


def schema_version(d: Drill, py: str, env: dict[str, str], label: str) -> int:
    code, out = d.cmd(
        label,
        [py, "-m", "cji.ops.db_cli", "--database-url-env", "DRILL_DATABASE_URL", "migrate", "status", "--json"],
        env=env,
    )
    match = re.search(r'"current":\s*(\d+)', out)
    return int(match.group(1)) if code == 0 and match else -1


def facts(url: str) -> dict[str, Any]:
    from cji.ops.backup import _engine, table_facts

    engine = _engine(url)
    try:
        return json.loads(json.dumps(table_facts(engine), default=str))
    finally:
        engine.dispose()


def old_frontend(d: Drill, source: Path, api_url: str, viewer: str) -> bool:
    fe = d.work / "frontend-old"
    shutil.copytree(source, fe, ignore=shutil.ignore_patterns(".next", "node_modules", "test-results"))
    modules = ROOT / "frontend" / "node_modules"
    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    env = {
        "CJI_SESSION_SECRET": "drill-" + secrets.token_urlsafe(32),
        "CJI_API_BASE_URL": api_url,
        "NEXT_TELEMETRY_DISABLED": "1",
        "E2E_LIVE_API_URL": api_url,
        "E2E_LIVE_TOKEN": viewer,
    }
    if os.name == "nt":
        d.cmd("old frontend: link node_modules", ["cmd", "/c", "mklink", "/J", str(fe / "node_modules"), str(modules)])
    else:
        (fe / "node_modules").symlink_to(modules, target_is_directory=True)
    code, _ = d.cmd(
        "old frontend: next build", ["node", "node_modules/next/dist/bin/next", "build"], cwd=fe, env=env, timeout=900
    )
    if code != 0:
        # Turbopack can refuse a linked node_modules outside the project; fall back to a real copy.
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "rmdir", str(fe / "node_modules")], check=False)  # nosec B603 B607
        else:
            (fe / "node_modules").unlink()
        shutil.copytree(modules, fe / "node_modules", symlinks=True)
        code, _ = d.cmd(
            "old frontend: next build (copied node_modules)",
            ["node", "node_modules/next/dist/bin/next", "build"],
            cwd=fe,
            env=env,
            timeout=900,
        )
    if code != 0:
        return False
    code, _ = d.cmd(
        "old frontend: smoke test against the 0.15.0 API",
        [npx, "playwright", "test", "smoke.spec.ts"],
        cwd=fe,
        env=env,
        timeout=900,
    )
    return code == 0


def write_switch(d: Drill, py: str, db_url: str) -> bool:
    s = System(
        d.work / "sys-write-off",
        python=py,
        extra_env={
            "CJI_MODE": "realtime",
            "DATABASE_URL": db_url,
            "SUPABASE_DATABASE_URL": "",
            "REALTIME_WINDOW_MINUTES": str(WINDOW_MINUTES),
            "CJI_API_WRITE_OPERATIONS": "false",
        },
    )
    d.systems.append(s)
    tok = token(d, py, s.home / "data" / "api_tokens.json", "operator")
    try:
        s.start("api")
        auth = {"Authorization": f"Bearer {tok}"}
        start = (
            http()
            .post(
                s.url("api", f"{API}/runs"),
                json={"journey_id": JOURNEY, "auto_approve": True},
                headers={**auth, "Idempotency-Key": "drill-" + uuid.uuid4().hex[:16]},
                timeout=30,
            )
            .status_code
        )
        read = http().get(s.url("api", f"{API}/runs"), headers=auth, timeout=30).status_code
        ok = start in (404, 405) and read == 200
        d.record(
            "configuration rollback",
            "CJI_API_WRITE_OPERATIONS=false: POST /runs, GET /runs",
            0 if ok else 1,
            f"POST /runs HTTP {start} (expected 404/405); GET /runs HTTP {read}",
        )
        return ok
    finally:
        s.stop_all()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ci/rollback_drill.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--old-wheel", type=Path, required=True)
    parser.add_argument("--old-frontend", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True, help="empty or new directory (removed at the end)")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--keep", action="store_true", help="keep the work directory")
    args = parser.parse_args(argv)
    work = args.work.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    d = Drill(work)
    started = time.monotonic()
    pg: Postgres | None = None
    try:
        # 1 ── releases ────────────────────────────────────────────────────────────────────────────────────
        build = work / "build"
        build.mkdir()
        shutil.copy2(APP / "pyproject.toml", build / "pyproject.toml")
        shutil.copytree(APP / "src", build / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        d.cmd(
            "build wheel 0.15.0",
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--no-index",
                "--no-build-isolation",
                "-q",
                "-w",
                str(work / "wheels"),
                str(build),
            ],
        )
        new_wheel = next((work / "wheels").glob("cji_agent-*.whl"))
        old_py = make_venv(d, "venv-old", args.old_wheel.resolve())
        new_py = make_venv(d, "venv-new", new_wheel)
        pg = Postgres(work / "pg")
        db_url = pg.url
        env = {
            "DRILL_DATABASE_URL": db_url,
            "DATABASE_URL": db_url,
            "SUPABASE_DATABASE_URL": "",
            "CJI_MODE": "realtime",
            "CJI_ENV": "development",
            "CJI_HOME": str(work / "home-ingest"),
            "REALTIME_WINDOW_MINUTES": str(WINDOW_MINUTES),
        }
        (work / "home-ingest" / "data").mkdir(parents=True)
        # 2 ── old release: ingest (tables created the old way) and analyse ─────────────────────────────────
        import pandas as pd

        events = recent(pd.read_parquet(APP / "data" / "events.parquet"))
        span = events["timestamp"].max() - events["timestamp"].min()
        d.record(
            "demo events shifted to end 10 minutes ago",
            "-",
            0 if span < pd.Timedelta(minutes=WINDOW_MINUTES - 20) else 1,
            f"{len(events)} events spanning {span}; realtime window {WINDOW_MINUTES} minutes",
        )
        csv = work / "events.csv"
        events.to_csv(csv, index=False)
        code, _ = d.cmd(
            "0.11.0: cji-ingest-json events.csv",
            [old_py, "-m", "cji.tools.ingest_json", str(csv)],
            env=env,
            timeout=900,
        )
        source_rows = facts(db_url).get("tracking_events", {}).get("rows")
        d.record(
            "0.11.0: rows ingested",
            "count(*) tracking_events",
            0 if source_rows == len(events) else 1,
            f"{source_rows} rows (file {len(events)})",
        )
        old1, _, _ = analysis(d, "0.11.0-before", old_py, db_url)
        # 3 ── backup before the upgrade ───────────────────────────────────────────────────────────────────
        home = d.work / "sys-0.11.0-before" / "home"
        before = facts(db_url)
        bak_env = {**env, "CJI_HOME": str(home)}
        c_create, _ = d.cmd(
            "cji-backup create",
            [
                new_py,
                "-m",
                "cji.ops.backup",
                "--database-url-env",
                "DRILL_DATABASE_URL",
                "--pg-bin",
                str(pg.bin),
                "create",
                "--out",
                str(work / "backup"),
            ],
            env=bak_env,
        )
        backup = next(iter(sorted((work / "backup").glob("cji-backup-*"))), work / "backup")
        c_verify, _ = d.cmd(
            "cji-backup verify",
            [new_py, "-m", "cji.ops.backup", "--pg-bin", str(pg.bin), "verify", str(backup)],
            env=bak_env,
        )
        # 4 ── upgrade to 0.15.0 ───────────────────────────────────────────────────────────────────────────
        c_up, _ = d.cmd(
            "0.15.0: cji-db migrate up",
            [new_py, "-m", "cji.ops.db_cli", "--database-url-env", "DRILL_DATABASE_URL", "migrate", "up"],
            env=env,
        )
        v_up = schema_version(d, new_py, env, "0.15.0: schema version after up")
        new, new_sys, _ = analysis(d, "0.15.0", new_py, db_url, keep=True)
        same_new = compare(d, "0.15.0 result = 0.11.0 result", old1, new)
        fe_ok = False
        if new_sys is not None:
            try:
                viewer = token(d, new_py, new_sys.home / "data" / "api_tokens.json", "viewer")
                fe_ok = old_frontend(d, args.old_frontend.resolve(), new_sys.url("api", ""), viewer)
            finally:
                new_sys.stop_all()
        # 5 ── configuration rollback ──────────────────────────────────────────────────────────────────────
        switch_ok = write_switch(d, new_py, db_url)
        # 6 ── schema and release rollback ─────────────────────────────────────────────────────────────────
        c_down, _ = d.cmd(
            "cji-db migrate down --to 1",
            [
                new_py,
                "-m",
                "cji.ops.db_cli",
                "--database-url-env",
                "DRILL_DATABASE_URL",
                "migrate",
                "down",
                "--to",
                "1",
            ],
            env=env,
        )
        v_down = schema_version(d, new_py, env, "schema version after down")
        old2, _, _ = analysis(d, "0.11.0-after-rollback", old_py, db_url)
        same_old = compare(d, "0.11.0 after rollback = 0.11.0 before", old1, old2)
        c_reup, _ = d.cmd(
            "cji-db migrate up (again)",
            [new_py, "-m", "cji.ops.db_cli", "--database-url-env", "DRILL_DATABASE_URL", "migrate", "up"],
            env=env,
        )
        v_reup = schema_version(d, new_py, env, "schema version after the second up")
        # 7 ── restore into a fresh database and home ──────────────────────────────────────────────────────
        pg.create_database("cji_restore")
        restore_url = db_url.rsplit("/", 1)[0] + "/cji_restore"
        r_env = {**env, "DRILL_RESTORE_URL": restore_url, "CJI_HOME": str(work / "home-restored")}
        c_restore, _ = d.cmd(
            "cji-backup restore (fresh database and home)",
            [
                new_py,
                "-m",
                "cji.ops.backup",
                "--database-url-env",
                "DRILL_RESTORE_URL",
                "--pg-bin",
                str(pg.bin),
                "restore",
                str(backup),
                "--home",
                str(work / "home-restored"),
                "--confirm-database",
                "cji_restore",
            ],
            env=r_env,
        )
        after = facts(restore_url)
        equal_tables = {t: before[t] == after.get(t) for t in before}
        tokens_equal = _sha(home / "data" / "api_tokens.json") == _sha(
            work / "home-restored" / "data" / "api_tokens.json"
        )
        d.record(
            "restore = source",
            "table_facts (rows, checksum) and token file hash",
            0 if all(equal_tables.values()) and tokens_equal else 1,
            f"tables equal: {equal_tables}; api_tokens.json equal: {tokens_equal}",
        )
        d.flags = {
            "restore_equal": c_create == 0
            and c_verify == 0
            and c_restore == 0
            and all(equal_tables.values())
            and bool(equal_tables)
            and tokens_equal,
            "restore_equal_detail": f"{len(equal_tables)} tables equal={all(equal_tables.values())}, token file "
            f"equal={tokens_equal}, create/verify/restore exit {c_create}/{c_verify}/{c_restore}",
            "schema_rollback_ok": c_up == 0
            and v_up == 2
            and c_down == 0
            and v_down == 1
            and old2.get("status") == "completed"
            and c_reup == 0
            and v_reup == 2,
            "schema_rollback_ok_detail": f"versions up/down/up {v_up}/{v_down}/{v_reup}; 0.11.0 on version 1: "
            f"{old2.get('status')}",
            "release_rollback_ok": old1.get("status") == "completed"
            and new.get("status") == "completed"
            and same_new
            and same_old,
            "release_rollback_ok_detail": f"0.11.0 {old1.get('status')}, 0.15.0 {new.get('status')} (same={same_new}), "
            f"0.11.0 again {old2.get('status')} (same={same_old})",
            "old_frontend_ok": fe_ok,
            "old_frontend_ok_detail": "pre-Spec 15 frontend build + smoke test against the 0.15.0 API: "
            + ("passed" if fe_ok else "failed"),
            "write_switch_ok": switch_ok,
            "write_switch_ok_detail": "CJI_API_WRITE_OPERATIONS=false: "
            + ("writes refused, reads served" if switch_ok else "unexpected answers"),
        }
    except Exception as exc:  # noqa: BLE001  # broad-except: the drill reports any failure as a failed step
        d.record("drill aborted", "-", "error", f"{type(exc).__name__}: {str(exc)[:300]}")
    finally:
        for s in d.systems:
            s.stop_all()
        if pg is not None:
            try:
                pg.stop()
            except Exception:  # noqa: BLE001  # broad-except: teardown of a server that may already be stopped
                pass
    ok = all(
        d.flags.get(k) is True
        for k in ("restore_equal", "schema_rollback_ok", "release_rollback_ok", "old_frontend_ok", "write_switch_ok")
    )
    write_report(args.out, d, ok, time.monotonic() - started)
    if not args.keep:
        _remove(work)
    return 0 if ok else 1


def _sha(path: Path) -> str | None:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _remove(path: Path) -> None:
    link = path / "frontend-old" / "node_modules"
    if os.name == "nt" and link.is_junction():
        subprocess.run(["cmd", "/c", "rmdir", str(link)], check=False)  # nosec B603 B607 - removes the junction only
    shutil.rmtree(path, ignore_errors=True)


def write_report(out: Path, d: Drill, ok: bool, seconds: float) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "rollback-drill.json").write_text(
        json.dumps({**d.flags, "ok": ok, "steps": d.steps}, indent=2), encoding="utf-8"
    )
    lines = [
        "# Rollback drill",
        "",
        f"`python ci/rollback_drill.py` (Spec 15, OD-175), {time.strftime('%Y-%m-%d %H:%M')}, "
        f"{seconds / 60:.1f} min. Result: **{'PASS' if ok else 'FAIL'}**.",
        "",
        "| Flag | Result | Detail |",
        "|---|---|---|",
    ]
    for key in ("restore_equal", "schema_rollback_ok", "release_rollback_ok", "old_frontend_ok", "write_switch_ok"):
        lines.append(
            f"| {key} | {'pass' if d.flags.get(key) is True else 'FAIL'} | {d.flags.get(key + '_detail', '-')} |"
        )
    lines += ["", "| # | Step | Command | Exit | Detail |", "|---|---|---|---|---|"]
    for i, s in enumerate(d.steps, 1):
        cells = [str(i), s["step"], f"`{s['command'][:160]}`", str(s["exit"]), s["detail"]]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    (out / "rollback-drill.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
