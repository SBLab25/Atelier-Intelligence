"""Spec 07: summarise the gate logs into final-numbers.txt (compared with the Spec 06 gate)."""
from __future__ import annotations

import pathlib
import re
import xml.etree.ElementTree as ET

EV = pathlib.Path(__file__).resolve().parents[1]
EV06 = EV.parents[1] / "06-cleanup" / "evidence"


def read(p: pathlib.Path) -> str:
    return p.read_bytes().replace(b"\x00", b"").decode("utf-8", "replace") if p.exists() else ""


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
    return text.splitlines()[-1] if text else "empty"


out = ["gate-results.txt:"] + ["   " + line for line in read(EV / "gate-results.txt").splitlines()]
now, before = junit(EV / "gate-pytest-junit.xml"), junit(EV06 / "gate-pytest-junit.xml")
if now and before:
    t, f, s, names = now
    t6, f6, _, names6 = before
    out.append(f"full suite: {t - len(f) - s}/{t} pass, {len(f)} fail, {s} skipped (Spec 06: {t6 - len(f6)}/{t6})")
    out.append(f"failures identical to the Spec 06 set (F-01): {f == f6}; new: {sorted(f - f6)}; fixed: {sorted(f6 - f)}")
    out.append(f"tests added: {len(names - names6)}; tests no longer present: {sorted(names6 - names)}")
new = junit(EV / "gate-new-tests-junit.xml")
if new:
    t, f, s, _ = new
    out.append(f"Spec 07 test set: {t - len(f) - s}/{t} pass, {s} skipped; failing: {sorted(f)}")
before_new = junit(EV / "before-tests-junit.xml")
if before_new:
    t, f, s, names = before_new
    collector = {n for n in names if "test_collector::" in n}
    failed_c = {n for n in f if "test_collector::" in n}
    out.append(f"test_collector.py before the change: {len(collector) - len(failed_c)}/{len(collector)} pass "
               "(3 security unit tests re-run with collector/security.py absent: see before-tests.log)")
ruff, ruff06 = re.search(r"Found (\d+) error", read(EV / "gate-ruff.log")), re.search(r"Found (\d+) error", read(EV06 / "gate-ruff.log"))
out.append(f"ruff total findings: {ruff.group(1) if ruff else 'none/0'} (Spec 06: {ruff06.group(1) if ruff06 else '?'})")
for log in ["gate-ruff-new.log", "gate-mypy-collector.log", "gate-mypy-repositories-strict.log", "gate-bandit-collector.log"]:
    out.append(f"{log}: {last_line(log)}")
my = re.search(r"Found (\d+) errors? in (\d+) files?.*", read(EV / "gate-mypy.log"))
my06 = re.search(r"Found (\d+) errors? in (\d+) files?.*", read(EV06 / "gate-mypy.log"))
out.append(f"mypy: {my.group(0) if my else read(EV / 'gate-mypy.log').strip()[-200:]} (Spec 06: {my06.group(0) if my06 else '?'})")
out.append("static compare:")
out += ["   " + line for line in read(EV / "gate-static-compare.log").splitlines() if line.strip()]
out.append("collector smoke:")
out += ["   | " + line for line in read(EV / "gate-collector-smoke.log").splitlines() if re.match(r"(PASS|FAIL|smoke:)", line)]
for log, pats in [
    ("gate-demo-pipeline.log", [r"\[OK\]", r"\[DONE\]", r"\[FAIL\]", r"ERROR"]),
    ("gate-ingest-probe.log", [r"flagged", r"\[FAIL\]", r"ERROR"]),
    ("gate-mode-mismatch.log", [r"ModeMismatch"]),
    ("gate-settings-check.log", [r'"status"', r"error"]),
    ("gate-collector-import.log", [r"/collect/batch"]),
    ("gate-snippet-no-key.log", [r"--api-key"]),
    ("gate-snippet-key.log", [r"Generated", r"All checks passed", r"error"]),
]:
    hits = [line.strip()[:220] for line in read(EV / log).splitlines() if any(re.search(p, line) for p in pats)]
    out.append(f"{log}:")
    out += ["   | " + h for h in hits[:8]]
for log in ["gate-help-main.log", "gate-help-run-servers.log", "gate-help-snippet.log"]:
    first = read(EV / log).strip().splitlines()
    out.append(f"{log}: {first[0][:120] if first else 'EMPTY'}")
out.append("git status (modified tracked files):")
out += ["   " + line for line in read(EV / "gate-git-status.log").splitlines()]
out.append(f"diff --check log bytes: {len(read(EV / 'gate-diff-check.log'))}")
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
