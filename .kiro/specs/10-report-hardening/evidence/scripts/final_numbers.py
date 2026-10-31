"""Spec 10: summarise the gate logs into final-numbers.txt (compared with the Spec 09 gate)."""
from __future__ import annotations

import collections
import json
import pathlib
import re
import xml.etree.ElementTree as ET

EV = pathlib.Path(__file__).resolve().parents[1]
EV09 = EV.parents[1] / "09-durable-workflow" / "evidence"


def read(p: pathlib.Path) -> str:
    if not p.exists():
        return ""
    raw = p.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.replace(b"\x00", b"").decode("utf-8", "replace")


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
            c[m.group(1).replace("\\", "/")] += 1
    return c


def bandit(p: pathlib.Path):
    t = read(p)
    i = t.find('"errors"')
    if i < 0:
        return None, {}
    data, _ = json.JSONDecoder().raw_decode(t[t.rfind("{", 0, i):])
    files: collections.Counter = collections.Counter()
    for r in data["results"]:
        files[(r["filename"].replace("\\", "/").removeprefix("./"), r["issue_severity"], r["test_id"])] += 1
    return {k: int(v) for k, v in data["metrics"]["_totals"].items() if k.startswith("SEVERITY")}, files


out = ["gate-results.txt:"] + ["   " + line for line in read(EV / "gate-results.txt").splitlines()]
now, before = junit(EV / "gate-pytest-junit.xml"), junit(EV09 / "gate-pytest-junit.xml")
if now and before:
    t, f, s, names = now
    t9, f9, _, names9 = before
    out.append(f"full suite: {t - len(f) - s}/{t} pass, {len(f)} fail, {s} skipped (Spec 09: {t9 - len(f9)}/{t9})")
    out.append(f"tests added: {len(names - names9)}; tests no longer present: {sorted(names9 - names)}")
    added = collections.Counter(n.split("::")[0] for n in names - names9)
    out.append(f"added per module: {dict(sorted(added.items()))}")
new = junit(EV / "gate-new-tests-junit.xml")
if new:
    t, f, s, names = new
    rep = sum(1 for n in names if "test_reports" in n)
    out.append(f"Spec 10 test set: {t - len(f) - s}/{t} pass; failing: {sorted(f)}; test_reports.py: {rep} tests")
t1 = junit(EV / "before-tests-junit.xml")
if t1:
    t, f, s, _ = t1
    out.append(f"T1 baseline of tests/test_reports.py before the change: {t - len(f) - s}/{t} pass")
ruff, ruff9 = (re.search(r"Found (\d+) error", read(e / "gate-ruff.log")) for e in (EV, EV09))
out.append(f"ruff total findings: {ruff.group(1) if ruff else 'none/0'} (Spec 09: {ruff9.group(1) if ruff9 else '?'})")
for log in ["gate-ruff-new.log", "gate-mypy-reporting-strict.log", "gate-mypy-workflow-strict.log",
            "gate-mypy-integrations-strict.log", "gate-mypy-repositories-strict.log", "gate-bandit-reporting.log",
            "gate-bandit-workflow.log"]:
    out.append(f"{log}: {last_line(log)}")
pat = r"Found (\d+) errors? in (\d+) files?.*"
my, my9 = (re.search(pat, read(e / "gate-mypy.log")) for e in (EV, EV09))
out.append(f"mypy: {my.group(0) if my else read(EV / 'gate-mypy.log').strip()[-200:]} "
           f"(Spec 09: {my9.group(0) if my9 else '?'})")
a, b = mypy_per_file(EV / "gate-mypy.log"), mypy_per_file(EV09 / "gate-mypy.log")
out.append("mypy per-file changes vs Spec 09: " + (", ".join(
    f"{k}: {b[k]} -> {a[k]}" for k in sorted(set(a) | set(b)) if a[k] != b[k]) or "none"))
s10, f10 = bandit(EV / "gate-bandit.json.log")
s9, f9b = bandit(EV09 / "gate-bandit.json.log")
out.append(f"bandit totals: {s10} (Spec 09: {s9})")
diff = {k: f10.get(k, 0) - f9b.get(k, 0) for k in set(f10) | set(f9b) if f10.get(k, 0) != f9b.get(k, 0)}
out.append("bandit changes vs Spec 09: " + (", ".join(f"{k[0]} {k[1]}:{k[2]} {v:+d}" for k, v in sorted(diff.items()))
                                             or "none"))
for log, pats in [
    ("gate-report-contract.log", [r".*"]),
    ("gate-audit-check.log", [r".*"]),
    ("gate-audit-workflow.log", [r".*"]),
    ("gate-kill-resume.log", [r"killed during", r"^thread:", r'"status": "(running|completed)"', r"\[DONE\]"]),
    ("gate-mode-mismatch.log", [r"\[FAILED\]"]),
    ("gate-collector-smoke.log", [r"^smoke:"]),
]:
    hits = [line.strip()[:240] for line in read(EV / log).splitlines() if any(re.search(p, line) for p in pats)]
    out.append(f"{log}:")
    out += ["   | " + h for h in hits[:30]]
out.append("git status (modified tracked files):")
out += ["   " + line for line in read(EV / "gate-git-status.log").splitlines()]
out.append(f"diff --check log bytes: {len(read(EV / 'gate-diff-check.log'))}")
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
