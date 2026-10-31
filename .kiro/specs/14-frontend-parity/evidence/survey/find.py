"""Find files by name under TCS-CJI and grep patterns -> s14_find.txt
usage: python s14_find.py name1,name2 [pattern ...]"""
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\sovan\Documents\Projects\TCS-CJI")
SKIP = {".venv", "node_modules", "build", ".next", "__pycache__", ".git", "dist", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
names = set(sys.argv[1].split(",")) if len(sys.argv) > 1 and sys.argv[1] else set()
pats = [re.compile(p) for p in sys.argv[2:]]
out = []


def walk(d: Path):
    for p in d.iterdir():
        if p.is_dir():
            if p.name in SKIP:
                continue
            yield from walk(p)
        else:
            yield p


for p in walk(ROOT):
    rel = p.relative_to(ROOT).as_posix()
    if p.name in names:
        out.append(f"FILE {rel} {p.stat().st_size}")
    if pats and p.suffix in {".py", ".ts", ".tsx", ".md", ".json", ".toml"} and p.stat().st_size < 2_000_000:
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for pat in pats:
                if pat.search(line):
                    out.append(f"{rel}:{i}: {line.strip()[:200]}")
                    break
Path(r"C:\Users\sovan\.kiro\s14_find.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
