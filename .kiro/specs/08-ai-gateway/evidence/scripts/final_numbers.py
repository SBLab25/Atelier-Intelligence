"""Spec 08: summarise the gate logs into final-numbers.txt (compared with the Spec 07 gate)."""
from __future__ import annotations

import pathlib
import re
import xml.etree.ElementTree as ET

EV = pathlib.Path(__file__).resolve().parents[1]
EV07 = EV.parents[1] / "07-collector" / "evidence"


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
now, before = junit(EV / "gate-pytest-junit.xml"), junit(EV07 / "gate-pytest-junit.xml")
if now and before:
    t, f, s, names = now
    t7, f7, _, names7 = before
    out.append(f"full suite: {t - len(f) - s}/{t} pass, {len(f)} fail, {s} skipped (Spec 07: {t7 - len(f7)}/{t7})")
    out.append(f"failures identical to the Spec 07 set (F-01): {f == f7}; new: {sorted(f - f7)}; fixed: {sorted(f7 - f)}")
    out.append(f"tests added: {len(names - names7)}; tests no longer present: {sorted(names7 - names)}")
new = junit(EV / "gate-new-tests-junit.xml")
if new:
    t, f, s, names = new
    gw = [n for n in names if "test_gateway::" in n]
    out.append(f"Spec 08 test set: {t - len(f) - s}/{t} pass, {s} skipped; failing: {sorted(f)}; test_gateway.py: {len(gw)} tests")
ruff, ruff07 = re.search(r"Found (\d+) error", read(EV / "gate-ruff.log")), re.search(r"Found (\d+) error", read(EV07 / "gate-ruff.log"))
out.append(f"ruff total findings: {ruff.group(1) if ruff else 'none/0'} (Spec 07: {ruff07.group(1) if ruff07 else '?'})")
for log in ["gate-ruff-new.log", "gate-mypy-integrations-strict.log", "gate-mypy-repositories-strict.log",
            "gate-bandit-integrations.log"]:
    out.append(f"{log}: {last_line(log)}")
my = re.search(r"Found (\d+) errors? in (\d+) files?.*", read(EV / "gate-mypy.log"))
my07 = re.search(r"Found (\d+) errors? in (\d+) files?.*", read(EV07 / "gate-mypy.log"))
out.append(f"mypy: {my.group(0) if my else read(EV / 'gate-mypy.log').strip()[-200:]} (Spec 07: {my07.group(0) if my07 else '?'})")
out.append("static compare:")
out += ["   " + line for line in read(EV / "gate-static-compare.log").splitlines() if line.strip()]
for log, pats in [
    ("gate-collector-smoke.log", [r"^smoke:", r"^FAIL"]),
    ("gate-demo-pipeline-none.log", [r"\[OK\]", r"\[DONE\]", r"\[FAIL\]", r"ERROR"]),
    ("gate-demo-pipeline.log", [r"\[OK\]", r"\[DONE\]", r"\[FAIL\]", r"ERROR", r"provider_unavailable"]),
    ("gate-ingest-probe.log", [r"flagged", r"\[FAIL\]", r"ERROR"]),
    ("gate-mode-mismatch.log", [r"ModeMismatch"]),
    ("gate-settings-check.log", [r'"status"', r'"provider"', r"error"]),
    ("gate-settings-mismatch.log", [r"CJI_LLM_PROVIDER", r"status"]),
    ("gate-audit-check.log", [r".*"]),
]:
    hits = [line.strip()[:220] for line in read(EV / log).splitlines() if any(re.search(p, line) for p in pats)]
    out.append(f"{log}:")
    out += ["   | " + h for h in hits[:24]]
out.append("git status (modified tracked files):")
out += ["   " + line for line in read(EV / "gate-git-status.log").splitlines()]
out.append(f"diff --check log bytes: {len(read(EV / 'gate-diff-check.log'))}")
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
