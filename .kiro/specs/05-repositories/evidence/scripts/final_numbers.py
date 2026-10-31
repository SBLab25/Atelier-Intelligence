"""Summarise the Spec 05 gate logs into evidence/final-numbers.txt."""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EV = Path(__file__).resolve().parents[1]
EV04 = EV.parents[1] / "04-configuration" / "evidence"
out: list[str] = []


def read(p: Path) -> str:
    raw = p.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.replace(b"\x00", b"").decode("utf-8", errors="replace")


def junit(p: Path) -> tuple[int, set[str], int]:
    root = ET.parse(p).getroot()
    total, failed, skipped = 0, set(), 0
    for tc in root.iter("testcase"):
        total += 1
        if tc.find("skipped") is not None:
            skipped += 1
        if tc.find("failure") is not None or tc.find("error") is not None:
            failed.add(f"{tc.get('classname')}::{tc.get('name')}")
    return total, failed, skipped


out.append("gate-results.txt:")
out += ["   " + line for line in read(EV / "gate-results.txt").splitlines()]
t5, f5, s5 = junit(EV / "gate-pytest-junit.xml")
t4, f4, _ = junit(EV04 / "gate-pytest-junit.xml")
out.append(f"full suite: {t5 - len(f5) - s5}/{t5} pass, {len(f5)} fail, {s5} skipped (Spec 04: {t4 - len(f4)}/{t4})")
out.append(f"failures identical to the F-01 set: {f5 == f4}; new: {sorted(f5 - f4)}; fixed: {sorted(f4 - f5)}")
tn, fn, sn = junit(EV / "gate-new-tests-junit.xml")
tb, fb, _ = junit(EV / "before-tests-junit.xml")
out.append(f"Spec 05 tests: {tn - len(fn) - sn}/{tn} pass, {sn} skipped; before migration: {tb - len(fb)}/{tb} ({len(fb)} fail)")
pg = [n for n in re.findall(r'name="([^"]+)"', read(EV / "gate-new-tests-junit.xml")) if "realtime" in n or "parity" in n]
out.append(f"PostgreSQL-backed tests run: {len(pg)} (names containing realtime/parity)")
ruff = [ln for ln in read(EV / "gate-ruff.log").splitlines() if re.match(r"^\S+\.py:\d+:\d+: ", ln)]
out.append(f"ruff total findings: {len(ruff)} (Spec 04: 246, baseline 266)")
mypy = [ln for ln in read(EV / "gate-mypy.log").splitlines() if ln.startswith(("Found ", "Success"))]
out.append(f"mypy: {mypy[-1] if mypy else '?'} (Spec 04: 46, baseline 52)")
for name in ("gate-ruff-new.log", "gate-mypy-repositories-strict.log"):
    lines = [ln for ln in read(EV / name).splitlines() if ln.strip()]
    out.append(f"{name}: {lines[-1] if lines else '(empty = clean)'}")
out += ["static compare:"] + ["   " + ln for ln in read(EV / "gate-static-compare.log").splitlines()]
demo = read(EV / "gate-demo-pipeline.log")
out.append("demo pipeline:")
for m in sorted(set(re.findall(r"\[(?:OK|DONE)\][^\n]*", demo)))[:8]:
    out.append(f"   | {m.strip()[:150]}")
probe = read(EV / "gate-ingest-probe.log")
out.append(f"ingest probe: 8005 posts {len(re.findall(r'8005/messages', probe))}, 404s {probe.count(' 404 ')}, "
           f"Max iterations {probe.count('Max iterations')}, flagged {'flagged for review' in probe}")
mm = read(EV / "gate-mode-mismatch.log")
out.append("mode mismatch run:")
for m in sorted(set(re.findall(r"[^\n]*(?:ModeMismatch|runs in demo mode)[^\n]*", mm)))[:4]:
    out.append(f"   | {m.strip()[:200]}")
out.append(f"   metrics collected in mismatch run: {'Collected 8 step metrics' in mm}")
out.append("diff --check log bytes: " + str((EV / "gate-diff-check.log").stat().st_size))
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(out))
