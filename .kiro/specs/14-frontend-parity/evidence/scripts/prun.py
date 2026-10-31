"""Run a command in the protected environment (Spec 13 gate phase B values) and write its output to a file.

usage: prun.py <out-file> <cwd: app|web|repo> [--env K=V ...] -- <command ...>
Database URLs point at a dead port and LLM keys are dummies, so nothing real is contacted. Exit code = the
command's; the last line of <out-file> is `exit=<code>`."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DIRS = {"app": ROOT / "cji_agent", "web": ROOT / "frontend", "repo": ROOT}
DEAD_DB = "postgresql://baseline:baseline@127.0.0.1:1/baseline"


def main(argv: list[str]) -> int:
    out, where, rest = Path(argv[0]), DIRS[argv[1]], argv[2:]
    extra: dict[str, str] = {}
    while rest and rest[0] == "--env":
        key, _, value = rest[1].partition("=")
        extra[key] = value
        rest = rest[2:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    env = {k: v for k, v in os.environ.items()
           if k not in ("CJI_HOME", "PYTHONPATH", "CJI_TEST_DATABASE_URL", "CJI_CHECKPOINTS_DB")}
    env.update({
        "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "NO_PROXY": "localhost,127.0.0.1",
        "DATABASE_URL": DEAD_DB, "SUPABASE_DATABASE_URL": DEAD_DB,
        "GROQ_API_KEY": "baseline-offline-dummy", "ANTHROPIC_API_KEY": "baseline-offline-dummy",
        "OPENAI_API_KEY": "baseline-offline-dummy", "LANGCHAIN_API_KEY": "baseline-offline-dummy",
        "LANGCHAIN_TRACING_V2": "false", "CJI_MODE": "demo", "PYTHONIOENCODING": "utf-8", "CI": "1",
        "LLM_MODEL": "openai/gpt-oss-120b", "CJI_LLM_PROVIDER": "none", "JOURNEY_NAME": "user_onboarding",
        "NEXT_TELEMETRY_DISABLED": "1", "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
        "CJI_CHECKPOINTS_DB": str(Path(os.environ.get("TEMP", "C:/Windows/Temp")) / "s14_pytest_checkpoints.db"),
    })
    env.update(extra)
    if rest and rest[0] in ("npm", "npx"):
        rest = [rest[0] + ".cmd", *rest[1:]]
    with out.open("w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.run(rest, cwd=where, env=env, stdout=fh, stderr=subprocess.STDOUT, check=False)
        fh.write(f"\nexit={proc.returncode}\n")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
