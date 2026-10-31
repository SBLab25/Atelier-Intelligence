"""Summarise the Spec 03 gate logs into evidence/final-numbers.txt."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

EV = Path(__file__).resolve().parents[1]
EV02 = EV.parents[1] / "02-p0-security" / "evidence"
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


t3, f3 = junit(EV / "gate-pytest-junit.xml")
t2, f2 = junit(EV02 / "gate3-pytest-junit.xml")
out.append(f"full suite: {t3 - len(f3)}/{t3} pass, {len(f3)} fail (Spec 02: {t2 - len(f2)}/{t2})")
out.append(f"failures identical to Spec 02 F-01 set: {f3 == f2}; new: {sorted(f3 - f2)}; fixed: {sorted(f2 - f3)}")
tc, fc = junit(EV / "after-contracts-junit.xml")
out.append(f"contracts: {tc - len(fc)}/{tc} pass (before fix: see before-contracts-junit.xml)")
tb, fb = junit(EV / "before-contracts-junit.xml")
out.append(f"contracts before fix: {tb - len(fb)}/{tb} pass, {len(fb)} fail")

ruff = [ln for ln in read(EV / "gate-ruff.log").splitlines() if re.match(r"^\S+\.py:\d+:\d+: ", ln)]
mypy_tail = [ln for ln in read(EV / "gate-mypy.log").splitlines() if ln.startswith("Found ") or ln.startswith("Success")]
out.append(f"ruff total findings: {len(ruff)} (Spec 02: 263, baseline 266)")
out.append(f"mypy: {mypy_tail[-1] if mypy_tail else 'no summary line'} (Spec 02: 49, baseline 52)")
for name in ("gate-ruff-domain.log", "gate-mypy-domain.log", "gate-mypy-domain-strict.log"):
    lines = [ln for ln in read(EV / name).splitlines() if ln.strip()]
    out.append(f"{name}: {lines[-1] if lines else '(empty = clean)'}")
cmp_lines = read(EV / "gate-static-compare.log").splitlines()
out.append("static compare: " + next((ln for ln in cmp_lines if ln.startswith("RESULT")), "?"))
out.append("              " + next((ln for ln in cmp_lines if ln.startswith("unchanged")), "?"))

demo = read(EV / "gate-demo-pipeline.log")
out.append("demo pipeline lines:")
for pat in (r"\[OK\][^\n]*", r"\[WARN\][^\n]*", r"\[DONE\][^\n]*", r"report[^\n]*\.html", r"Max iterations[^\n]*"):
    for m in sorted(set(re.findall(pat, demo)))[:12]:
        out.append(f"   | {m.strip()[:200]}")
out.append(f"   contract violations logged: {demo.count('contract violation')}")
probe = read(EV / "gate-ingest-probe.log")
out.append("ingest probe:")
out.append(f"   8005 message posts: {len(re.findall(r'8005/messages', probe))}, "
           f"404s: {probe.count(' 404 ')}, 8004/tools calls: {probe.count('8004/tools')}, "
           f"Max iterations hits: {probe.count('Max iterations')}, contract violations: {probe.count('contract violation')}")
for m in sorted(set(re.findall(r"(?:flagged|confidence|Processed \d+ file)[^\n]*", probe)))[:6]:
    out.append(f"   | {m.strip()[:200]}")
out.append("diff --check log bytes: " + str((EV / "gate-diff-check.log").stat().st_size))
(EV / "final-numbers.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
