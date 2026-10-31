"""
Dependency scans (Spec 15, OD-164): `python ci/scans.py deps [--out DIR]`. Needs network (PyPI/OSV and the npm
registry), so it runs outside the protected test environment.

- Python: `pip-audit -r cji_agent/requirements.lock --format json` (the exact tested set, hashes included).
- JavaScript: `npm audit --json` in frontend/ (all dependencies, from package-lock.json).

Every advisory must have an entry in `ci/exceptions.json` (`id`, `package`, `reason`, `owner`, `expires`
YYYY-MM-DD) that has not expired; otherwise the scan fails. Writes `deps.json` with every advisory and its status.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess  # nosec B404 - fixed argument lists, no shell
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # nosec B603
        check=False,
        timeout=900,
    )
    return proc.returncode, proc.stdout, proc.stderr


def python_advisories(python: str) -> tuple[list[dict[str, str]], str | None]:
    code, out, err = _run(
        [
            python,
            "-m",
            "pip_audit",
            "-r",
            "cji_agent/requirements.lock",
            "--format",
            "json",
            "--progress-spinner",
            "off",
            "--disable-pip",
            "--no-deps",
        ],
        ROOT,
    )
    try:
        data = json.loads(out)
    except ValueError:
        return [], f"pip-audit did not produce JSON (exit {code}): {(err or out).strip().splitlines()[-1:]}"
    found = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            found.append(
                {
                    "ecosystem": "python",
                    "package": dep.get("name", "?"),
                    "version": dep.get("version", "?"),
                    "id": vuln.get("id", "?"),
                    "fix": ",".join(vuln.get("fix_versions") or []) or "none",
                }
            )
    return found, None


def npm_advisories() -> tuple[list[dict[str, str]], str | None]:
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    code, out, err = _run([npm, "audit", "--json"], ROOT / "frontend")
    try:
        data = json.loads(out)
    except ValueError:
        return [], f"npm audit did not produce JSON (exit {code}): {(err or out).strip()[:200]}"
    found = []
    for name, item in (data.get("vulnerabilities") or {}).items():
        for via in item.get("via", []):
            if isinstance(via, dict):
                found.append(
                    {
                        "ecosystem": "npm",
                        "package": name,
                        "version": str(item.get("range", "?")),
                        "id": str(via.get("url") or via.get("source") or via.get("title")),
                        "fix": "yes" if item.get("fixAvailable") else "none",
                    }
                )
    return found, None


def classify(advisories: list[dict[str, str]], exceptions: list[dict[str, str]], today: date) -> list[dict[str, str]]:
    by_id = {(e["id"], e["package"].lower()): e for e in exceptions}
    out = []
    for adv in advisories:
        exc = by_id.get((adv["id"], adv["package"].lower()))
        if exc is None:
            status = "open"
        elif date.fromisoformat(exc["expires"]) < today:
            status = f"exception expired {exc['expires']}"
        else:
            status = f"accepted until {exc['expires']} (owner {exc['owner']})"
        out.append({**adv, "status": status})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ci/scans.py")
    parser.add_argument("what", choices=["deps"])
    parser.add_argument("--out", type=Path, default=ROOT / "ci" / "out")
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args(argv)
    exceptions = json.loads((ROOT / "ci" / "exceptions.json").read_text(encoding="utf-8")).get("exceptions", [])
    py, py_error = python_advisories(args.python)
    js, js_error = npm_advisories()
    rows = classify(py + js, exceptions, date.today())
    errors = [e for e in (py_error, js_error) if e]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "deps.json").write_text(json.dumps({"advisories": rows, "errors": errors}, indent=2), encoding="utf-8")
    for row in rows:
        print(
            f"{row['ecosystem']:<7} {row['package']:<28} {row['version']:<12} {row['id']:<28} fix={row['fix']:<12} "
            f"{row['status']}"
        )
    for error in errors:
        print(f"ERROR {error}")
    failing = [r for r in rows if not r["status"].startswith("accepted")]
    print(
        f"dependency scan: {len(rows)} advisories ({len(py)} python, {len(js)} npm), {len(failing)} not accepted, "
        f"{len(errors)} scanner errors"
    )
    return 1 if failing or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
