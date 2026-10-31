"""Summarize the post-fix-up gate (gate3-*, gate-ruff/mypy/bandit) into gate3-summary-results.txt."""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ev = Path(sys.argv[1])
out = []


def read(name):
    p = ev / name
    if not p.exists():
        return None
    raw = p.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace").replace("\x00", "")


def grep(name, pattern, limit=20):
    t = read(name)
    if t is None:
        return [f"   (missing {name})"]
    seen, res = set(), []
    for l in t.splitlines():
        h = l.strip()
        if re.search(pattern, h) and h not in seen and "NativeCommandError" not in h:
            seen.add(h)
            res.append("   | " + h[:230])
    return res[:limit]


out.append("== P0 tests ==")
out += grep("gate3-p0-tests.log", r"^(FAILED|ERROR)|\d+ (passed|failed|error)")
out.append("== full suite ==")
j = ev / "gate3-pytest-junit.xml"
if j.exists():
    root = ET.parse(j).getroot()
    for s in ([root] if root.tag == "testsuite" else root.iter("testsuite")):
        out.append(f"   | junit tests={s.get('tests')} failures={s.get('failures')} errors={s.get('errors')} skipped={s.get('skipped')}")
        bad = [f"{c.get('classname')}::{c.get('name')}" for c in s.iter("testcase")
               if c.find("failure") is not None or c.find("error") is not None]
        outside = [b for b in bad if not b.startswith("tests.test_supervisor.")]
        out.append(f"   | failing: {len(bad)} total, {len(outside)} outside tests.test_supervisor")
        out += ["   |   " + b for b in bad]
out.append("== collector import ==")
out += grep("gate3-collector-import.log", r"OK|Error", 3)
out.append("== static ==")
t = read("gate3-static-compare.log") or "(missing)"
out += ["   | " + l for l in t.splitlines() if l.strip() and not re.search(r"NativeCommandError|CategoryInfo|^At |^\s*[+~]", l)]
out += grep("gate-ruff.log", r"^Found \d+ error", 1) + grep("gate-mypy.log", r"^Found \d+ error|^Success", 1)
out.append("== diff ==")
out += grep("gate3-results.txt", r"diff --check|files changed|status \|", 30)
(ev / "gate3-summary-results.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
