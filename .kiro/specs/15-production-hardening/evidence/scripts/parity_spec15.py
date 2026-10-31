"""
Spec 15 gate, phase C2 (R18): the Spec 14 parity check on the 0.15.0 code. Demo data, offline LLM ("none").
Starts the MCP servers and the API on free loopback ports with a temporary home, completes one run with the CLI
(`cji --mode demo --run --auto-approve`) and one through the API, then runs
`.kiro/specs/14-frontend-parity/evidence/scripts/parity_check.py` (API = CLI --status = checkpoint = last_run.json;
API = engine).

  python parity_spec15.py --work DIR --out DIR      writes OUT/parity/, OUT/parity-check.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess  # nosec B404 - fixed argument lists, no shell
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / "cji_agent"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "src"))
from tests._system import System, http, wait_for  # noqa: E402

PARITY = ROOT / ".kiro" / "specs" / "14-frontend-parity" / "evidence" / "scripts" / "parity_check.py"
API = "/api/v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    work, out = args.work.resolve(), args.out.resolve()
    shutil.rmtree(work, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    s = System(work, extra_env={"CJI_MODE": "demo", "CJI_LLM_PROVIDER": "none"})
    env = s.env()
    detail = "not run"
    ok = False
    try:
        s.start_mcp()
        cli = subprocess.run([sys.executable, "-m", "cji.main", "--mode", "demo", "--run", "--auto-approve"],  # nosec B603
                             cwd=s.home, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=900, check=False)
        (work / "cli-run.log").write_text(cli.stdout + cli.stderr, encoding="utf-8")
        match = re.search(r"Thread ID:\s*([0-9a-f-]{36})", cli.stdout + cli.stderr)
        cli_run = match.group(1) if match else ""
        token = s.token("operator")
        s.start("api")
        auth = {"Authorization": f"Bearer {token}"}
        r = http().post(s.url("api", f"{API}/runs"), json={"journey_id": "user_onboarding", "auto_approve": True},
                        headers={**auth, "Idempotency-Key": "parity-" + uuid.uuid4().hex[:16]}, timeout=60)
        api_run = str(r.json().get("run_id")) if r.status_code == 202 else ""
        done = wait_for(lambda: (lambda x: x if x.get("status") in ("completed", "failed") else None)(
            http().get(s.url("api", f"{API}/runs/{api_run}"), headers=auth, timeout=15).json()), 600, 2.0) or {}
        print(f"cli run {cli_run or '-'} (exit {cli.returncode}); api run {api_run or '-'}: {done.get('status')}")
        if cli_run and api_run and done.get("status") == "completed":
            check = subprocess.run([sys.executable, str(PARITY), "--api", s.url("api", ""), "--token", token,  # nosec B603
                                    "--run", api_run, "--cli-run", cli_run, "--out", str(out / "parity")],
                                   cwd=s.home, env=env, capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=900, check=False)
            last = [ln for ln in check.stdout.splitlines() if ln.strip()][-1:] or [check.stderr.strip()[-200:]]
            ok, detail = check.returncode == 0, last[0]
            print(check.stdout)
        else:
            detail = f"runs not completed: cli exit {cli.returncode}, api status {done.get('status')}"
    finally:
        s.stop_all()
    (out / "parity-check.json").write_text(json.dumps({"ok": ok, "detail": detail}), encoding="utf-8")
    print(f"parity: ok={ok} {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
