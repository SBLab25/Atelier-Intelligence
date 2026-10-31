"""Spec 15 survey part 2: existing logging, audit, health, tokens, schema, env checks; installed tools."""
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
SRC = ROOT / "cji_agent/src/cji"
out: list[str] = []


def show(rel: str, start: int = 1, end: int = 10_000) -> None:
    lines = (SRC / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    out.append(f"\n===== {rel} [{start}-{min(end, len(lines))}] of {len(lines)}")
    out.extend(f"{i:4}: {lines[i - 1]}" for i in range(start, min(end, len(lines)) + 1))


def grep(pattern: str, rels: list[str], ctx: int = 0) -> None:
    rx = re.compile(pattern)
    for rel in rels:
        lines = (SRC / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                for j in range(max(1, i - ctx), min(len(lines), i + ctx) + 1):
                    out.append(f"{rel}:{j}: {lines[j - 1]}")
                if ctx:
                    out.append("--")


out.append("######## tools on PATH")
for tool in ("docker", "podman", "trivy", "grype", "syft", "gitleaks", "trufflehog", "pg_dump", "pg_restore", "psql",
             "sqlite3", "gh", "act", "semgrep", "pip-audit", "osv-scanner", "node", "npm", "git"):
    out.append(f"{tool}: {shutil.which(tool)}")
venv = Path(r"C:\Users\sovan\.venvs\cji-baseline-312\Scripts")
out.append("venv tools: " + ", ".join(sorted(p.stem for p in venv.glob("*.exe")
                                             if p.stem in {"pip-audit", "bandit", "ruff", "mypy", "pytest",
                                                           "pgserver", "detect-secrets"})))
pg = list(Path(r"C:\Users\sovan\.venvs\cji-baseline-312\Lib\site-packages").glob("pgserver*/pginstall/bin/pg_dump*"))
out.append(f"pgserver pg_dump: {[str(p) for p in pg]}")

show("logs.py")
show("integrations/audit.py", 1, 80)
show("api/routes/health.py")
grep(r"add_argument|add_parser|def (create|revoke|rotate|list)", ["api/tokens_cli.py"])
grep(r"def |token_hash|expires|revoked", ["api/auth.py"])
grep(r"CREATE TABLE|CREATE INDEX|ALTER TABLE", ["collector/api.py", "api/idempotency.py", "workflow/index.py",
                                                "workflow/runtime.py", "repositories/postgres.py",
                                                "tools/ingest_json.py", "collector/ingest.py"], 0)
grep(r"production|CJI_ENV|is_dev|development|refuse|SHIPPED|insecure", ["settings/load.py", "settings/model.py",
                                                                       "settings/roles.py"], 0)
grep(r"@app\.(get|post)|health|ready", ["collector/api.py"], 0)
grep(r"rate|Retry-After|limit", ["api/middleware.py"], 0)
grep(r"getLogger|logging\.|log_level|LOG_", ["api/serve.py", "collector/serve.py", "run_servers.py",
                                             "mcp_servers/_serve.py", "main.py"], 0)

fe = ROOT / "frontend"
out.append("\n######## frontend server-side env and logging")
for p in sorted((fe / "src").rglob("*.ts")):
    text = p.read_text(encoding="utf-8", errors="replace")
    for m in sorted(set(re.findall(r"process\.env\.([A-Z_]+)", text))):
        out.append(f"{p.relative_to(fe)}: env {m}")
    if "console." in text:
        out.append(f"{p.relative_to(fe)}: console calls {text.count('console.')}")
out.append((fe / ".env.example").read_text(encoding="utf-8"))

Path(r"C:\Users\sovan\.kiro\s15_survey2.txt").write_text("\n".join(out).encode("ascii", "replace").decode(),
                                                        encoding="ascii")
print("ok")
