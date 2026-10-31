"""Dump line ranges: python s14_dump.py relpath@a-b ... (relative to TCS-CJI) -> s14_dump.txt"""
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\sovan\Documents\Projects\TCS-CJI")
out = []
for spec in sys.argv[1:]:
    rel, _, rng = spec.partition("@")
    lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    a, b = (int(x) for x in rng.split("-")) if rng else (1, len(lines))
    out.append(f"===== {rel} ({len(lines)} lines) {a}-{b}")
    out += [f"{i:5}: {lines[i - 1]}" for i in range(a, min(b, len(lines)) + 1)]
Path(r"C:\Users\sovan\.kiro\s14_dump.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
