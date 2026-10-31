import re
from pathlib import Path

ROOT = Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
SRC = ROOT / "cji_agent/src/cji"
out = []


def show(path: Path, start: int, end: int) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out.append(f"\n===== {path.relative_to(ROOT)} [{start}-{min(end, len(lines))}] of {len(lines)}")
    out.extend(f"{i:4}: {lines[i - 1]}" for i in range(start, min(end, len(lines)) + 1))


tables = {}
for p in SRC.rglob("*.py"):
    for t in re.findall(r"(?:FROM|INTO|UPDATE|TABLE IF NOT EXISTS|TABLE)\s+([a-z_]{4,})", p.read_text(encoding="utf-8",
                                                                                                     errors="replace")):
        tables.setdefault(t, set()).add(str(p.relative_to(SRC)).replace("\\", "/"))
out.append("SQL tables: " + "; ".join(f"{t}: {sorted(v)[:4]}" for t, v in sorted(tables.items())))
show(SRC / "collector/api.py", 125, 165)
show(SRC / "collector/api.py", 376, 420)
show(SRC / "http/request_id.py", 1, 60)
out.append("\n settings __main__:")
show(SRC / "settings/__main__.py", 1, 80)
grep_files = {"settings/load.py": r"home|data_dir|reports_dir|audit_dir|checkpoints|tokens_file|chroma|LANGCHAIN",
              "settings/model.py": r"class |_dir|_db|_file|tracing"}
for rel, pat in grep_files.items():
    for i, line in enumerate((SRC / rel).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(pat, line):
            out.append(f"{rel}:{i}: {line.strip()[:160]}")
fe = ROOT / "frontend/src/lib"
for name in ("session.ts", "config-core.ts"):
    for i, line in enumerate((fe / name).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"secret|SECRET|secure|maxAge|rate|limit|NODE_ENV|console", line):
            out.append(f"frontend/{name}:{i}: {line.strip()[:160]}")
act = ROOT / "frontend/src/app/actions.ts"
for i, line in enumerate(act.read_text(encoding="utf-8").splitlines(), 1):
    if re.search(r"limit|429|console|forward|x-forwarded|headers\(", line, re.I):
        out.append(f"frontend/app/actions.ts:{i}: {line.strip()[:160]}")
Path(r"C:\Users\sovan\.kiro\s15_survey4.txt").write_text("\n".join(out).encode("ascii", "replace").decode(),
                                                        encoding="ascii")
print("ok")
