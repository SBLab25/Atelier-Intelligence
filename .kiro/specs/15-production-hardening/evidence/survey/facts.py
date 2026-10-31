import re
import subprocess
from pathlib import Path

ROOT = Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
SRC = ROOT / "cji_agent/src/cji"
out = []


def run(*cmd: str) -> str:
    r = subprocess.run(list(cmd), cwd=ROOT, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


out.append("check-ignore .env: " + run("git", "check-ignore", "-v", "cji_agent/.env"))
out.append("tracked .env files: " + run("git", "ls-files", "--", "*.env", "**/.env"))
out.append("check-ignore api_tokens: " + run("git", "check-ignore", "-v", "cji_agent/data/api_tokens.json"))
out.append("HEAD: " + run("git", "log", "-1", "--format=%h %ad %s", "--date=short"))


def grep(rel: str, pat: str, root: Path = SRC) -> None:
    for i, line in enumerate((root / rel).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if re.search(pat, line):
            out.append(f"{rel}:{i}: {line.strip()[:170]}")


grep("src/lib/session-core.ts", r"secure|sameSite|httpOnly|maxAge|NODE_ENV", ROOT / "frontend") if (
    ROOT / "frontend/src/lib/session-core.ts").exists() else None
for p in sorted((ROOT / "frontend/src").rglob("*.ts")):
    text = p.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"secure:|sameSite|maxAge|NODE_ENV", line):
            out.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()[:170]}")
grep("api/routes/runs.py", r"comment")
grep("collector/api.py", r"is_active|DEV_TRACKER_KEY|@app\.(delete|patch)")
grep("collector/security.py", r"is_active")
grep("settings/model.py", r"DEV_TRACKER_KEY|cji_dev")
grep("api/serve.py", r"uvicorn|log_level|access_log|host|workers")
grep("mcp_servers/_serve.py", r"host|log|uvicorn")
grep("main.py", r"configure_logging|basicConfig")
for rel in ("integrations/llm.py", "integrations/providers.py"):
    grep(rel, r"logger\.(info|warning|error)")
grep("settings/load.py", r'secret\("|r\.secret')
d = ROOT / "cji_agent/data"
out.append("data dir: " + ", ".join(sorted(p.name for p in d.iterdir())) if d.exists() else "no data dir")
Path(r"C:\Users\sovan\.kiro\s15_facts.txt").write_text("\n".join(out).encode("ascii", "replace").decode(),
                                                      encoding="ascii")
print("ok")
