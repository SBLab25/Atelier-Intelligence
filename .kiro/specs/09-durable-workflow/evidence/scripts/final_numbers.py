"""Spec 09: summarise the gate logs into final-numbers.txt (compared with the Spec 08 gate)."""
from __future__ import annotations

import pathlib
import re
import xml.etree.ElementTree as ET

EV = pathlib.Path(__file__).resolve().parents[1]
EV08 = EV.parents[1] / "08-ai-gateway" / "evidence"


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
now, before = junit(EV / "gate-pytest-junit.xml"), junit(EV08 / "gate-pytest-junit.xml")
if now and before:
    t, f, s, names = now
    t8, f8, _, names8 = before
    out.append(f"full suite: {t - len(f) - s}/{t} pass, {len(f)} fail, {s} skipped (Spec 08: {t8 - len(f8)}/{t8})")
    out.append(f"Spec 08 failures (F-01) still failing: {sorted(f & f8)}; new failures: {sorted(f - f8)}")
    removed = sorted(names8 - names)
    out.append(f"tests added: {len(names - names8)}; tests no longer present: {len(removed)}")
    out += ["   - " + n for n in removed]
    out.append(f"removed tests that were the Spec 08 failures: {set(removed) == f8}")
new = junit(EV / "gate-new-tests-junit.xml")
if new:
    t, f, s, names = new
    out.append(f"Spec 09 test set (tests/test_workflow.py): {t - len(f) - s}/{t} pass, {s} skipped; failing: {sorted(f)}")
before_t1 = junit(EV / "before-tests-junit.xml")
if before_t1:
    t, f, s, _ = before_t1
    out.append(f"T1 baseline of the same file before the change: {t - len(f) - s}/{t} pass, {len(f)} fail/error")
ruff, ruff08 = (re.search(r"Found (\d+) error", read(e / "gate-ruff.log")) for e in (EV, EV08))
out.append(f"ruff total findings: {ruff.group(1) if ruff else 'none/0'} (Spec 08: {ruff08.group(1) if ruff08 else '?'})")
for log in ["gate-ruff-new.log", "gate-mypy-workflow-strict.log", "gate-mypy-integrations-strict.log",
            "gate-mypy-repositories-strict.log", "gate-bandit-workflow.log"]:
    out.append(f"{log}: {last_line(log)}")
pat = r"Found (\d+) errors? in (\d+) files?.*"
my, my08 = (re.search(pat, read(e / "gate-mypy.log")) for e in (EV, EV08))
out.append(f"mypy: {my.group(0) if my else read(EV / 'gate-mypy.log').strip()[-200:]} "
           f"(Spec 08: {my08.group(0) if my08 else '?'})")
out.append("static compare:")
out += ["   " + line for line in read(EV / "gate-static-compare.log").splitlines() if line.strip()]
for log, pats in [
    ("gate-collector-smoke.log", [r"^smoke:", r"^FAIL"]),
    ("gate-settings-step-timeout.log", [r"STEP_TIMEOUT", r"error"]),
    ("gate-cli-unknown.log", [r".*"]),
    ("gate-demo-pipeline-none.log", [r"\[OK\]", r"\[DONE\]", r"\[FAIL\]", r"Thread ID", r"ERROR"]),
    ("gate-pause.log", [r"awaiting", r"Thread ID", r"approve"]),
    ("gate-status-paused.log", [r'"status"', r'"next"']),
    ("gate-resume-paused.log", [r"awaiting|refus|approve"]),
    ("gate-approve.log", [r"\[DONE\]", r"report", r"completed"]),
    ("gate-approve-again.log", [r".*"]),
    ("gate-status-approved.log", [r'"status"']),
    ("gate-demo-pipeline.log", [r"\[OK\]", r"\[DONE\]", r"\[FAIL\]", r"ERROR", r"provider_unavailable"]),
    ("gate-kill-resume.log", [r"killed", r"thread:", r"^----", r'"status"', r"\[DONE\]", r"\[FAIL\]", r"resum"]),
    ("gate-ingest-probe.log", [r"flagged", r"\[FAIL\]", r"ERROR"]),
    ("gate-mode-mismatch.log", [r"mode_mismatch|ModeMismatch|mode mismatch"]),
    ("gate-audit-check.log", [r".*"]),
    ("gate-audit-workflow.log", [r".*"]),
]:
    hits = [line.strip()[:220] for line in read(EV / log).splitlines() if any(re.search(p, line) for p in pats)]
    out.append(f"{log}:")
    out += ["   | " + h for h in hits[:30]]
out.append("git status (modified tracked files):")
out += ["   " + line for line in read(EV / "gate-git-status.log").splitlines()]
out.append(f"diff --check log bytes: {len(read(EV / 'gate-diff-check.log'))}")
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
