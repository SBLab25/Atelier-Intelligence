"""
Local CI runner (Spec 15, OD-170): `python ci/run_ci.py [--stage NAME ...] [--network] [--python PY]`.

Stages: format, lint, types, unit, integration, browser, scans (default: all, in this order). Every step runs in the
protected environment (dead proxy, dead database URLs, dummy LLM keys, LLM provider "none"), so no test can reach a
real service or the database in cji_agent/.env. `--network` adds the dependency scan (`ci/scans.py deps`, PyPI/OSV
and the npm registry) to the scans stage; that one step keeps the caller's environment.

Writes ci/out/<stage>.log, JUnit XML for the test steps and ci/out/summary.md (git-ignored). Exit 1 if any step
fails. Ratchets keep the static-check baselines of Spec 14 from growing (F-93): ruff <= 92 findings, mypy <= 33
errors, bandit Low <= 25 / Medium <= 10 / High 0; the strict mypy set and every other step must be clean.
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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "cji_agent"
WEB = ROOT / "frontend"
OUT = ROOT / "ci" / "out"
STAGES = ("format", "lint", "types", "unit", "integration", "browser", "scans")
RATCHETS = {"ruff": 92, "mypy": 33, "bandit_low": 25, "bandit_medium": 10, "bandit_high": 0}
STRICT_SET = [
    "src/cji/api",
    "src/cji/services",
    "src/cji/analytics",
    "src/cji/http",
    "src/cji/workflow/index.py",
    "src/cji/observability",
    "src/cji/ops",
    "src/cji/migrations",
]
DEAD_DB = "postgresql://ci:ci@127.0.0.1:1/ci"
DUMMY = "ci-offline-dummy"
DROPPED = ("CJI_HOME", "PYTHONPATH", "CJI_TEST_DATABASE_URL", "CJI_CHECKPOINTS_DB", "CJI_API_TOKENS_FILE")


def protected_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in DROPPED}
    env.update(
        {
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "localhost,127.0.0.1",
            "DATABASE_URL": DEAD_DB,
            "SUPABASE_DATABASE_URL": DEAD_DB,
            "GROQ_API_KEY": DUMMY,
            "ANTHROPIC_API_KEY": DUMMY,
            "OPENAI_API_KEY": DUMMY,
            "LANGCHAIN_API_KEY": DUMMY,
            "LANGCHAIN_TRACING_V2": "false",
            "CJI_LLM_PROVIDER": "none",
            "CJI_MODE": "demo",
            "LLM_MODEL": "openai/gpt-oss-120b",
            "JOURNEY_NAME": "user_onboarding",
            "PYTHONIOENCODING": "utf-8",
            "CI": "1",
            "NEXT_TELEMETRY_DISABLED": "1",
            "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1",
            "CJI_CHECKPOINTS_DB": str(OUT / "tmp" / "pytest_checkpoints.db"),
        }
    )
    env.update(extra or {})
    return env


@dataclass
class Step:
    stage: str
    name: str
    cmd: list[str]
    cwd: Path
    check: Callable[[int, str], tuple[bool, str]] | None = None  # (passed, detail) from exit code and output
    env: dict[str, str] = field(default_factory=dict)
    network: bool = False
    timeout: int = 1800


@dataclass
class Result:
    step: Step
    passed: bool
    detail: str
    seconds: float


def exit_zero(code: int, _out: str) -> tuple[bool, str]:
    return code == 0, f"exit {code}"


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def pytest_check(code: int, out: str) -> tuple[bool, str]:
    lines = [ln.strip() for ln in ANSI.sub("", out).splitlines() if re.search(r"\d+ (passed|failed|error)", ln)]
    return code == 0, (lines[-1].strip("= ") if lines else f"exit {code}")


def vitest_check(code: int, out: str) -> tuple[bool, str]:
    tests = [ln.strip() for ln in ANSI.sub("", out).splitlines() if re.match(r"\s*Tests\s+\d", ln)]
    return code == 0, (tests[-1] if tests else f"exit {code}")


def ruff_check(_code: int, out: str) -> tuple[bool, str]:
    match = re.search(r"Found (\d+) errors?", out)
    count = int(match.group(1)) if match else (0 if "All checks passed" in out else -1)
    return 0 <= count <= RATCHETS["ruff"], f"{count} findings (ratchet <= {RATCHETS['ruff']})"


def mypy_ratchet(_code: int, out: str) -> tuple[bool, str]:
    match = re.search(r"Found (\d+) errors? in (\d+) files?", out)
    count = int(match.group(1)) if match else (0 if "Success: no issues found" in out else -1)
    return 0 <= count <= RATCHETS["mypy"], f"{count} errors (ratchet <= {RATCHETS['mypy']})"


def mypy_clean(_code: int, out: str) -> tuple[bool, str]:
    ok = "Success: no issues found" in out
    match = re.search(r"Found (\d+) errors?", out)
    return ok, "0 errors" if ok else f"{match.group(1) if match else '?'} errors (must be 0)"


def bandit_check(_code: int, out: str) -> tuple[bool, str]:
    start = out.find("{")
    try:  # stderr lines can follow the JSON document: decode the first value only
        totals = json.JSONDecoder().raw_decode(out[start:])[0]["metrics"]["_totals"]
    except (ValueError, KeyError, TypeError):
        return False, "bandit did not produce JSON"
    low, med, high = (int(totals.get(f"SEVERITY.{s}", 0)) for s in ("LOW", "MEDIUM", "HIGH"))
    ok = low <= RATCHETS["bandit_low"] and med <= RATCHETS["bandit_medium"] and high <= RATCHETS["bandit_high"]
    return ok, (
        f"Low {low} / Medium {med} / High {high} (ratchet <= {RATCHETS['bandit_low']}/"
        f"{RATCHETS['bandit_medium']}/{RATCHETS['bandit_high']})"
    )


def formatted_files() -> list[str]:
    listed = (ROOT / "ci" / "formatted.txt").read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in listed if ln.strip() and not ln.lstrip().startswith("#")]


def steps(python: str, network: bool) -> list[Step]:
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    npx = shutil.which("npx.cmd") or shutil.which("npx") or "npx"
    node = shutil.which("node") or "node"
    junit = OUT / "junit"
    session = {
        "CJI_SESSION_SECRET": "ci-session-" + secrets.token_urlsafe(32),
        "CJI_API_BASE_URL": "http://127.0.0.1:18006",
    }
    out: list[Step] = [
        Step(
            "format",
            "ruff format --check (ci/formatted.txt)",
            [python, "-m", "ruff", "format", "--check", "--no-cache", "--line-length", "120", *formatted_files()],
            ROOT,
        ),
        Step(
            "lint",
            "ruff check",
            [python, "-m", "ruff", "check", "--no-cache", "--output-format", "concise"],
            APP,
            ruff_check,
        ),
        Step(
            "lint",
            "bandit -c pyproject.toml -r src",
            [python, "-m", "bandit", "-c", "pyproject.toml", "-r", "src", "-q", "-f", "json"],
            APP,
            bandit_check,
        ),
        Step("lint", "eslint (npm run lint)", [npm, "run", "lint"], WEB),
        Step(
            "types",
            "mypy (project config)",
            [python, "-m", "mypy", "--cache-dir", str(OUT / "tmp" / "mypy")],
            APP,
            mypy_ratchet,
        ),
        Step(
            "types",
            "mypy --strict (strict set)",
            [
                python,
                "-m",
                "mypy",
                *STRICT_SET,
                "--strict",
                "--follow-imports=silent",
                "--cache-dir",
                str(OUT / "tmp" / "mypy"),
            ],
            APP,
            mypy_clean,
        ),
        Step("types", "tsc --noEmit (npm run typecheck)", [npm, "run", "typecheck"], WEB),
        Step("types", "api:check (types = openapi/v1.json)", [npm, "run", "api:check"], WEB),
        Step(
            "unit",
            "pytest -m 'not integration and not recovery'",
            [
                python,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "-m",
                "not integration and not recovery",
                f"--junitxml={junit / 'pytest-unit.xml'}",
            ],
            APP,
            pytest_check,
        ),
        Step(
            "unit",
            "vitest",
            [
                npx,
                "vitest",
                "run",
                "--reporter=default",
                "--reporter=junit",
                f"--outputFile.junit={junit / 'vitest.xml'}",
            ],
            WEB,
            vitest_check,
        ),
        Step(
            "integration",
            "pytest pgserver + recovery suite",
            [
                python,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "tests/test_migrations.py",
                "tests/test_backup.py",
                "tests/test_recovery.py",
                "-m",
                "not integration",
                f"--junitxml={junit / 'pytest-integration.xml'}",
            ],
            APP,
            pytest_check,
            env={"RECOVERY_LOG": str(OUT / "recovery.jsonl")},
            timeout=2400,
        ),
        Step("browser", "next build", [node, "node_modules/next/dist/bin/next", "build"], WEB, env=session),
        Step(
            "browser",
            "playwright (fixture API specs)",
            [npx, "playwright", "test", "--reporter=list,junit"],
            WEB,
            env={**session, "PLAYWRIGHT_JUNIT_OUTPUT_NAME": str(junit / "playwright.xml")},
        ),
        Step("browser", "bundle scan (.next/static)", [npm, "run", "bundle:scan"], WEB),
        Step(
            "scans",
            "secret scan (tree and history)",
            [python, "cji_agent/scripts/secret_scan.py", "--json", str(OUT / "secret-scan.json")],
            ROOT,
        ),
    ]
    if network:
        out.append(
            Step(
                "scans",
                "dependency scan (pip-audit, npm audit)",
                [python, "ci/scans.py", "deps", "--out", str(OUT)],
                ROOT,
                network=True,
            )
        )
    return out


def run_step(step: Step) -> Result:
    env = dict(os.environ) if step.network else protected_env(step.env)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            step.cmd,
            cwd=step.cwd,
            env=env,
            capture_output=True,
            text=True,  # nosec B603
            encoding="utf-8",
            errors="replace",
            timeout=step.timeout,
            check=False,
        )
        code, text = proc.returncode, proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        code, text = -1, f"timed out after {step.timeout}s\n{exc.stdout or ''}"
    except OSError as exc:
        code, text = -1, f"could not start: {exc}"
    passed, detail = (step.check or exit_zero)(code, text)
    log = OUT / f"{step.stage}.log"
    with log.open("a", encoding="utf-8") as fh:
        fh.write(
            f"\n===== {step.name}\n$ {' '.join(step.cmd)}\n(cwd {step.cwd})\n{text}\n"
            f"===== {'PASS' if passed else 'FAIL'}: {detail} (exit {code})\n"
        )
    return Result(step, passed, detail, time.monotonic() - started)


def summary(results: list[Result], stages: list[str]) -> str:
    lines = [
        "# CI summary",
        "",
        f"Run {time.strftime('%Y-%m-%dT%H:%M:%S')}; stages: {', '.join(stages)}.",
        "",
        "| Stage | Step | Result | Detail | Seconds |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.step.stage} | {r.step.name} | {'pass' if r.passed else 'FAIL'} | {r.detail} | {r.seconds:.0f} |"
        )
    failed = [r for r in results if not r.passed]
    lines += [
        "",
        f"Result: {'PASS' if not failed else 'FAIL'} ({len(results) - len(failed)} of {len(results)} steps passed).",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ci/run_ci.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--stage", action="append", choices=STAGES, help="run only these stages (repeatable)")
    parser.add_argument("--network", action="store_true", help="also run the dependency scan (needs network)")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    stages = [s for s in STAGES if not args.stage or s in args.stage]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "junit").mkdir(exist_ok=True)
    (OUT / "tmp").mkdir(exist_ok=True)
    for stage in stages:
        (OUT / f"{stage}.log").unlink(missing_ok=True)
    (OUT / "recovery.jsonl").unlink(missing_ok=True)
    results = []
    for step in steps(args.python, args.network):
        if step.stage in stages:
            result = run_step(step)
            results.append(result)
            print(
                f"{'pass' if result.passed else 'FAIL'}  {step.stage:<12} {step.name:<48} {result.detail} "
                f"({result.seconds:.0f}s)",
                flush=True,
            )
    (OUT / "summary.md").write_text(summary(results, stages), encoding="utf-8")
    shutil.rmtree(OUT / "tmp", ignore_errors=True)
    failed = [r for r in results if not r.passed]
    print(
        f"CI {'PASS' if not failed else 'FAIL'}: {len(results) - len(failed)} of {len(results)} steps passed; "
        f"summary in {OUT / 'summary.md'}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
