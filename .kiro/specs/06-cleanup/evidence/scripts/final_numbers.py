"""Spec 06: summarise the gate logs into final-numbers.txt (compared with the Spec 05 gate)."""
from __future__ import annotations

import pathlib
import re
import xml.etree.ElementTree as ET

EV = pathlib.Path(__file__).resolve().parents[1]
EV05 = EV.parents[1] / "05-repositories" / "evidence"


def read(p: pathlib.Path) -> str:
    return p.read_bytes().replace(b"\x00", b"").decode("utf-8", "replace") if p.exists() else ""


def junit(p: pathlib.Path):
    if not p.exists():
        return None
    root = ET.parse(p).getroot()
    cases = root.iter("testcase")
    total, failed, skipped = 0, set(), 0
    for c in cases:
        total += 1
        name = f"{c.get('classname')}::{c.get('name')}"
        if c.find("failure") is not None or c.find("error") is not None:
            failed.add(name)
        if c.find("skipped") is not None:
            skipped += 1
    return total, failed, skipped


out = ["gate-results.txt:"] + ["   " + l for l in read(EV / "gate-results.txt").splitlines()]
now, before = junit(EV / "gate-pytest-junit.xml"), junit(EV05 / "gate-pytest-junit.xml")
if now and before:
    t, f, s = now
    t5, f5, _ = before
    out.append(f"full suite: {t - len(f) - s}/{t} pass, {len(f)} fail, {s} skipped (Spec 05: {t5 - len(f5)}/{t5})")
    out.append(f"failures identical to the Spec 05 set (F-01): {f == f5}; new: {sorted(f - f5)}; fixed: {sorted(f5 - f)}")
new = junit(EV / "gate-new-tests-junit.xml")
if new:
    t, f, s = new
    out.append(f"Spec 06 tests: {t - len(f) - s}/{t} pass, {s} skipped; failing: {sorted(f)}")
before_new = junit(EV / "before-tests-junit.xml")
if before_new:
    t, f, s = before_new
    out.append(f"Spec 06 tests before the change: {t - len(f) - s}/{t} pass ({len(f)} fail)")
ruff = read(EV / "gate-ruff.log")
m = re.search(r"Found (\d+) error", ruff)
ruff05 = re.search(r"Found (\d+) error", read(EV05 / "gate-ruff.log"))
out.append(f"ruff total findings: {m.group(1) if m else 'none/0'} (Spec 05: {ruff05.group(1) if ruff05 else '?'})")
names = read(EV / "gate-ruff-names.log")
out.append("ruff F401/F841/F811/F821/E722 (no snippets): " + (re.search(r"Found \d+ errors?", names).group(0) if re.search(r"Found \d+ errors?", names) else "All checks passed" if "All checks passed" in names else names.strip()[:200]))
for log in ["gate-ruff-new.log", "gate-mypy-repositories-strict.log"]:
    out.append(f"{log}: {read(EV / log).strip().splitlines()[-1] if read(EV / log).strip() else 'empty'}")
my = re.search(r"Found (\d+) errors? in (\d+) files?.*", read(EV / "gate-mypy.log"))
my05 = re.search(r"Found (\d+) errors?", read(EV05 / "gate-mypy.log"))
out.append(f"mypy: {my.group(0) if my else read(EV / 'gate-mypy.log').strip()[-200:]} (Spec 05: {my05.group(1) if my05 else '?'})")
sc = read(EV / "gate-static-compare.log").splitlines()
out.append("static compare:")
out += ["   " + l for l in sc if l.strip()]
for log, pats in [
    ("gate-demo-pipeline.log", [r"\[OK\]", r"\[DONE\]", r"\[FAIL\]", r"ERROR"]),
    ("gate-ingest-probe.log", [r"flagged", r"\[FAIL\]", r"ERROR"]),
    ("gate-mode-mismatch.log", [r"ModeMismatch"]),
    ("gate-settings-check.log", [r'"status"', r"error"]),
    ("gate-collector-import.log", [r"/collect/batch"]),
]:
    text = read(EV / log)
    hits = [l.strip()[:200] for l in text.splitlines() if any(re.search(p, l) for p in pats)]
    out.append(f"{log}:")
    out += ["   | " + h for h in hits[:8]]
for log in ["gate-help-main.log", "gate-help-run-servers.log", "gate-help-ingest-json.log", "gate-help-snippet.log"]:
    first = read(EV / log).strip().splitlines()
    out.append(f"{log}: {first[0][:120] if first else 'EMPTY'}")
out.append("git status (deleted / modified tracked files):")
out += ["   " + l for l in read(EV / "gate-git-status.log").splitlines()]
out.append(f"diff --check log bytes: {len(read(EV / 'gate-diff-check.log'))}")
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
