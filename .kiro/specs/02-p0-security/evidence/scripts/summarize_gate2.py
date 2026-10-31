"""Summarize the Spec 02 gate rerun logs (gate2-*) into gate2-summary-results.txt."""
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
    text = raw.decode("utf-8", errors="replace")
    return text.replace("\x00", "")


def grep(name, pattern, limit=12):
    t = read(name)
    if t is None:
        return [f"   (missing {name})"]
    seen, res = set(), []
    for l in t.splitlines():
        h = l.strip()
        if re.search(pattern, h) and h not in seen:
            seen.add(h)
            res.append("   | " + h[:230])
    return res[:limit]


out.append("== collector import ==")
out += grep("gate2-collector-import.log", r"OK|Error", 3)
out.append("== P0 tests ==")
out += grep("gate2-p0-tests.log", r"^(FAILED|ERROR)|\d+ (passed|failed|error)", 20)
out.append("== full suite (not integration) ==")
j = ev / "gate2-pytest-junit.xml"
if j.exists():
    root = ET.parse(j).getroot()
    for s in ([root] if root.tag == "testsuite" else root.iter("testsuite")):
        out.append(f"   | junit tests={s.get('tests')} failures={s.get('failures')} errors={s.get('errors')} skipped={s.get('skipped')} time={s.get('time')}")
out += grep("gate2-pytest-full.log", r"^(FAILED|ERROR)|\d+ (passed|failed|error)", 25)
out.append("== static compare ==")
t = read("gate2-static-compare.log") or "(missing)"
out += ["   | " + l for l in t.splitlines() if l.strip() and "NativeCommandError" not in l][:20]
out += grep("gate2-ruff.log", r"^Found \d+ error", 1)
out += grep("gate2-mypy.log", r"^Found \d+ error|^Success", 1)
out.append("== pip-audit ==")
out += grep("gate2-pip-audit.log", r"Found \d+ known|No known vulnerabilities|^sqlalchemy\s|ERROR", 6)
(ev / "gate2-summary-results.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
