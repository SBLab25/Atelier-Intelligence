"""Summarise the Spec 04 gate logs into evidence/final-numbers.txt."""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EV = Path(__file__).resolve().parents[1]
EV03 = EV.parents[1] / "03-canonical-contracts" / "evidence"
out: list[str] = []


def read(p: Path) -> str:
    raw = p.read_bytes()
    return raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", errors="replace")


def junit(p: Path) -> tuple[int, set[str]]:
    root = ET.parse(p).getroot()
    total, failed = 0, set()
    for tc in root.iter("testcase"):
        total += 1
        if tc.find("failure") is not None or tc.find("error") is not None:
            failed.add(f"{tc.get('classname')}::{tc.get('name')}")
    return total, failed


out.append("gate-results.txt:")
out += ["   " + line for line in read(EV / "gate-results.txt").splitlines()]
t4, f4 = junit(EV / "gate-pytest-junit.xml")
t3, f3 = junit(EV03 / "gate-pytest-junit.xml")
out.append(f"full suite: {t4 - len(f4)}/{t4} pass, {len(f4)} fail (Spec 03: {t3 - len(f3)}/{t3})")
out.append(f"failures identical to the F-01 set: {f4 == f3}; new: {sorted(f4 - f3)}; fixed: {sorted(f3 - f4)}")
ts, fs = junit(EV / "gate-settings-junit.xml")
tb, fb = junit(EV / "before-settings-junit.xml")
out.append(f"test_settings.py: {ts - len(fs)}/{ts} pass; before caller migration: {tb - len(fb)}/{tb} ({len(fb)} fail)")
ruff = [ln for ln in read(EV / "gate-ruff.log").splitlines() if re.match(r"^\S+\.py:\d+:\d+: ", ln)]
out.append(f"ruff total findings: {len(ruff)} (Spec 03: 255, baseline 266)")
mypy = [ln for ln in read(EV / "gate-mypy.log").splitlines() if ln.startswith(("Found ", "Success"))]
out.append(f"mypy: {mypy[-1] if mypy else '?'} (Spec 03: 49, baseline 52)")
for name in ("gate-ruff-settings.log", "gate-mypy-settings-strict.log"):
    lines = [ln for ln in read(EV / name).splitlines() if ln.strip()]
    out.append(f"{name}: {lines[-1] if lines else '(empty = clean)'}")
cmp_lines = read(EV / "gate-static-compare.log").splitlines()
out += ["static compare:"] + ["   " + ln for ln in cmp_lines]
demo = read(EV / "gate-demo-pipeline.log")
out.append("demo pipeline:")
for pat in (r"\[OK\][^\n]*", r"\[DONE\][^\n]*", r"Max iterations[^\n]*"):
    for m in sorted(set(re.findall(pat, demo)))[:8]:
        out.append(f"   | {m.strip()[:160]}")
out.append(f"   contract violations: {demo.count('contract violation')}")
probe = read(EV / "gate-ingest-probe.log")
out.append(
    f"ingest probe: 8005 message posts {len(re.findall(r'8005/messages', probe))}, 404s {probe.count(' 404 ')}, "
    f"Max iterations {probe.count('Max iterations')}, flagged {'flagged for review' in probe}"
)
servers = read(EV / "gate-servers.err.log") + read(EV / "gate-servers.out.log")
out.append("server start lines: " + "; ".join(sorted(set(re.findall(r"Starting cji-[a-z-]+ on [0-9.:]+ \(sse\)", servers)))))
out.append("diff --check log bytes: " + str((EV / "gate-diff-check.log").stat().st_size))
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(out))
