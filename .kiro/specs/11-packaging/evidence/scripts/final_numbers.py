"""Spec 11: summarise the gate logs into final-numbers.txt (compared with the Spec 10 gate).

Source paths moved from cji_agent/<x> to cji_agent/src/cji/<x>; per-file comparisons strip the src/cji/ prefix.
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import xml.etree.ElementTree as ET

EV = pathlib.Path(__file__).resolve().parents[1]
EV10 = EV.parents[1] / "10-report-hardening" / "evidence"


def read(p: pathlib.Path) -> str:
    if not p.exists():
        return ""
    raw = p.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.replace(b"\x00", b"").decode("utf-8", "replace")


def norm(path: str) -> str:
    path = path.replace("\\", "/").removeprefix("./")
    return path.removeprefix("src/cji/")


def junit(p: pathlib.Path):
    if not p.exists():
        return None
    total, failed, skipped, names = 0, set(), 0, set()
    for c in ET.parse(p).getroot().iter("testcase"):
        total += 1
        name = f"{c.get('classname')}::{c.get('name')}"
        names.add(name)
        if c.find("failure") is not None or c.find("error") is not None:
            failed.add(name)
        if c.find("skipped") is not None:
            skipped += 1
    return total, failed, skipped, names


def last_line(log: str) -> str:
    text = read(EV / log).strip()
    return text.splitlines()[-1] if text else "empty (no output)"


def mypy_per_file(p: pathlib.Path) -> collections.Counter:
    c: collections.Counter = collections.Counter()
    for line in read(p).splitlines():
        m = re.search(r"([\w./\\-]+\.py):\d+(?::\d+)?: error:", line)
        if m:
            c[norm(m.group(1))] += 1
    return c


def bandit(p: pathlib.Path):
    t = read(p)
    i = t.find('"errors"')
    if i < 0:
        return None, {}
    data, _ = json.JSONDecoder().raw_decode(t[t.rfind("{", 0, i):])
    files: collections.Counter = collections.Counter()
    for r in data["results"]:
        files[(norm(r["filename"]), r["issue_severity"], r["test_id"])] += 1
    return {k: int(v) for k, v in data["metrics"]["_totals"].items() if k.startswith("SEVERITY")}, files


out = ["gate-results.txt:"] + ["   " + line for line in read(EV / "gate-results.txt").splitlines()]
for label, path in [("full suite (baseline venv, editable)", EV / "gate-pytest-junit.xml"),
                    ("full suite (clean venv, wheel)", EV / "gate-clean-pytest-junit.xml")]:
    now, before = junit(path), junit(EV10 / "gate-pytest-junit.xml")
    if now and before:
        t, f, s, names = now
        t10, f10, _, names10 = before
        out.append(f"{label}: {t - len(f) - s}/{t} pass, {len(f)} fail, {s} skipped; failing: {sorted(f)} "
                   f"(Spec 10: {t10 - len(f10)}/{t10})")
        out.append(f"   tests added: {len(names - names10)}; tests no longer present: {sorted(names10 - names)}")
        added = collections.Counter(n.split("::")[0] for n in names - names10)
        out.append(f"   added per module: {dict(sorted(added.items()))}")
new = junit(EV / "gate-new-tests-junit.xml")
if new:
    t, f, s, names = new
    pk = sum(1 for n in names if "test_packaging" in n)
    out.append(f"Spec 11 test set: {t - len(f) - s}/{t} pass, {s} skipped; failing: {sorted(f)}; "
               f"test_packaging.py: {pk} tests")
t1 = junit(EV / "before-tests-junit.xml")
if t1:
    t, f, s, _ = t1
    out.append(f"T1 baseline of tests/test_packaging.py before the change: {t - len(f) - s}/{t} pass, {s} skipped")
ruff, ruff10 = (re.search(r"Found (\d+) error", read(e / "gate-ruff.log")) for e in (EV, EV10))
out.append(f"ruff total findings: {ruff.group(1) if ruff else 'none/0'} (Spec 10: {ruff10.group(1) if ruff10 else '?'})")
for log in ["gate-ruff-new.log", "gate-mypy-new-strict.log", "gate-mypy-reporting-strict.log",
            "gate-mypy-workflow-strict.log", "gate-mypy-integrations-strict.log", "gate-mypy-repositories-strict.log",
            "gate-wheel-check.log", "gate-clean-check.log", "gate-clean-install.log"]:
    out.append(f"{log}: {last_line(log)}")
pat = r"Found (\d+) errors? in (\d+) files?.*"
my, my10 = (re.search(pat, read(e / "gate-mypy.log")) for e in (EV, EV10))
out.append(f"mypy: {my.group(0) if my else read(EV / 'gate-mypy.log').strip()[-200:]} "
           f"(Spec 10: {my10.group(0) if my10 else '?'})")
a, b = mypy_per_file(EV / "gate-mypy.log"), mypy_per_file(EV10 / "gate-mypy.log")
out.append("mypy per-file changes vs Spec 10: " + (", ".join(
    f"{k}: {b[k]} -> {a[k]}" for k in sorted(set(a) | set(b)) if a[k] != b[k]) or "none"))
s11, _ = bandit(EV / "gate-bandit.json.log")
out.append(f"bandit -c pyproject.toml -r src totals: {s11}")
s11a, f11 = bandit(EV / "gate-bandit-all.json.log")
s10, f10b = bandit(EV10 / "gate-bandit.json.log")
out.append(f"bandit -r . (Spec 10 scope) totals: {s11a} (Spec 10: {s10})")
diff = {k: f11.get(k, 0) - f10b.get(k, 0) for k in set(f11) | set(f10b) if f11.get(k, 0) != f10b.get(k, 0)}
out.append("bandit changes vs Spec 10 (same scope): " + (", ".join(
    f"{k[0]} {k[1]}:{k[2]} {v:+d}" for k, v in sorted(diff.items())) or "none"))
audit = EV / "gate-pip-audit.json"
if audit.exists():
    deps = json.loads(read(audit))["dependencies"]
    vulns = sorted({(d["name"], d["version"], v["id"]) for d in deps for v in d.get("vulns", [])})
    out.append(f"pip-audit on requirements.lock: {len(deps)} packages, {len(vulns)} distinct advisories in "
               f"{len({v[0] for v in vulns})} packages (survey before Spec 11: 30 entries in 8 packages)")
    out += [f"   | {n} {ver} {i}" for n, ver, i in vulns]
for log, pats in [
    ("gate-clean-location.log", [r".*"]),
    ("gate-clean-scripts-help.log", [r"^----", r"^exit=", r"^failures"]),
    ("gate-clean-settings-check.log", [r'"home"', r'"data_dir"', r'"reports_dir"']),
    ("gate-clean-pipeline.log", [r"\[OK\]|\[DONE\]|\[FAIL", r"^----", r"^\\"]),
    ("gate-help-launchers.log", [r"^----", r"^exit=", r"^failures"]),
    ("gate-report-contract.log", [r".*"]),
    ("gate-audit-check.log", [r".*"]),
    ("gate-audit-workflow.log", [r".*"]),
    ("gate-kill-resume.log", [r"killed during", r"^thread:", r'"status": "(running|completed)"', r"\[DONE\]"]),
    ("gate-mode-mismatch.log", [r"\[FAILED\]"]),
    ("gate-collector-smoke.log", [r"^smoke:"]),
]:
    hits = [line.strip()[:240] for line in read(EV / log).splitlines() if any(re.search(p, line) for p in pats)]
    out.append(f"{log}:")
    out += ["   | " + h for h in hits[:40]]
out.append("git status (modified tracked files):")
out += ["   " + line for line in read(EV / "gate-git-status.log").splitlines()]
out.append(f"diff --check log bytes: {len(read(EV / 'gate-diff-check.log'))}")
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
