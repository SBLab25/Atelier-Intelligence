"""Compare ruff / mypy / bandit findings per changed file: Spec 01 baseline vs now.
Usage: python compare_static.py <baseline evidence dir> <spec02 evidence dir> <file> [<file> ...]
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

base, new = Path(sys.argv[1]), Path(sys.argv[2])
files = [f.replace("/", "\\") for f in sys.argv[3:]]


def read(path):
    raw = path.read_bytes()
    text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", errors="replace")
    return text


def ruff_counts(path):
    c = Counter()
    for line in read(path).splitlines():
        m = re.match(r"^(?:\.\\)?([^:]+\.py):\d+:\d+: ", line.strip())
        if m:
            c[m.group(1).replace("/", "\\")] += 1
    return c


def mypy_counts(path):
    c = Counter()
    for line in read(path).splitlines():
        m = re.match(r"^([^:]+\.py):\d+: error:", line.strip())
        if m:
            c[m.group(1).replace("/", "\\")] += 1
    return c


def bandit_counts(path):
    text = read(path)
    start = re.search(r'^\{\s*$|^\{\s*"', text, re.MULTILINE)   # first line that opens the JSON report
    data = json.loads(text[start.start():])
    c = Counter()
    for r in data["results"]:
        if r["issue_severity"] in ("MEDIUM", "HIGH"):
            c[(r["filename"].lstrip(".\\").replace("/", "\\"), r["test_id"])] += 1
    return c


rb, rn = ruff_counts(base / "b4-ruff-full.log"), ruff_counts(new / "gate-ruff.log")
mb, mn = mypy_counts(base / "b5-mypy.log"), mypy_counts(new / "gate-mypy.log")
bb, bn = bandit_counts(base / "b6-bandit.json.log"), bandit_counts(new / "gate-bandit.json.log")
worse = False
print(f"{'file':44} {'ruff':>11} {'mypy':>9}  bandit medium+ (before -> after)")
for f in files:
    bandit_before = {k[1]: v for k, v in bb.items() if k[0] == f}
    bandit_after = {k[1]: v for k, v in bn.items() if k[0] == f}
    flag = ""
    if rn[f] > rb[f] or mn[f] > mb[f] or sum(bandit_after.values()) > sum(bandit_before.values()):
        flag, worse = "  <-- WORSE", True
    print(f"{f:44} {rb[f]:>4} -> {rn[f]:<4} {mb[f]:>3} -> {mn[f]:<3}  {bandit_before or '{}'} -> {bandit_after or '{}'}{flag}")
others_r = sum(v for k, v in rn.items() if k not in files) - sum(v for k, v in rb.items() if k not in files)
others_m = sum(v for k, v in mn.items() if k not in files) - sum(v for k, v in mb.items() if k not in files)
print(f"unchanged files delta: ruff {others_r:+d}, mypy {others_m:+d}")
print("RESULT:", "WORSE on at least one changed file" if worse else "no changed file is worse than baseline")
