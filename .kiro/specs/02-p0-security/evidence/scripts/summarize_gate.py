"""Summarize Spec 02 gate logs into gate-results.txt (UTF-8). Usage: python summarize_gate.py <evidence dir>"""
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
    for enc in ("utf-8", "utf-16"):
        try:
            text = raw.decode(enc)
            if enc == "utf-8" and "\x00" in text:
                continue
            return text
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def grep(name, pattern, limit=12):
    t = read(name)
    if t is None:
        return [f"   (missing {name})"]
    hits = [l.strip() for l in t.splitlines() if re.search(pattern, l)]
    seen, res = set(), []
    for h in hits:
        if h not in seen:
            seen.add(h)
            res.append("   | " + h[:220])
    return res[:limit]


out.append("== SQLAlchemy ==")
cons = read("constraints-spec02.txt") or ""
out += ["   | " + l for l in cons.splitlines() if l.lower().startswith(("sqlalchemy==", "psycopg"))]

out.append("== golden ==")
gb, ga = read("golden-before.json"), read("golden-after.json")
out.append(f"   | identical: {gb == ga}  (before {len(gb or '')} chars, after {len(ga or '')} chars)")
out += grep("gate-golden.log", r"metrics:|Error|Traceback", 5)

out.append("== P0 tests ==")
out += grep("gate-p0-tests.log", r"^(FAILED|ERROR)|\d+ (passed|failed)", 20)

out.append("== full suite ==")
j = ev / "gate-pytest-junit.xml"
if j.exists():
    root = ET.parse(j).getroot()
    for s in ([root] if root.tag == "testsuite" else root.iter("testsuite")):
        out.append(f"   | junit tests={s.get('tests')} failures={s.get('failures')} errors={s.get('errors')} skipped={s.get('skipped')} time={s.get('time')}")
out += grep("gate-pytest-full.log", r"^(FAILED|ERROR)|\d+ (passed|failed)", 25)

out.append("== collector import ==")
out += grep("gate-collector-import.log", r"OK|Error|error", 4)

out.append("== static compare (changed files) ==")
t = read("gate-static-compare.log") or "(missing)"
out += ["   | " + l for l in t.splitlines() if l.strip()]
for name, pat in (("gate-ruff.log", r"^Found \d+ error"), ("gate-mypy.log", r"^Found \d+ error|^Success")):
    out += grep(name, pat, 2)

out.append("== pip-audit ==")
out += grep("gate-pip-audit.log", r"Found \d+ known|No known vulnerabilities|^sqlalchemy\s", 6)

out.append("== smoke: demo pipeline ==")
out += grep("gate-demo-pipeline.log", r"\[OK\]|\[FAIL\]|\[DONE\]|Max iterations", 10)
out.append("== smoke: ingest probe ==")
t = read("gate-ingest-probe.log") or ""
out.append("   | routes to ingestion_worker: %d | 404s: %d | 8005 message posts: %d | 8004 /tools calls: %d | max-iteration hits: %d" % (
    len(re.findall(r"Route .*ingestion_worker", t)), len(re.findall(r"\b404\b", t)),
    len(re.findall(r"8005/messages", t)), len(re.findall(r"8004/tools", t)), len(re.findall(r"Max iterations", t))))
out += grep("gate-ingest-probe.log", r"ingestion_worker error|Processed \d+ file|\[DONE\]|flagging|Low confidence|All LLM providers failed", 8)

out.append("== diff ==")
out += grep("gate-diff-check.log", r".", 10) or ["   | (git diff --check: no output)"]
t = read("gate-diff-stat.log") or ""
out += ["   | " + l.strip() for l in t.splitlines() if l.strip()][-16:]

(ev / "gate-results.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
