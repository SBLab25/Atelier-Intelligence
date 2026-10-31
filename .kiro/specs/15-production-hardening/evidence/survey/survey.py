"""Spec 15 survey: what exists today for each production-hardening control (read-only)."""
import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
APP = ROOT / "cji_agent"
SRC = APP / "src" / "cji"
PY = r"C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
out: list[str] = []


def sec(title: str) -> None:
    out.append(f"\n######## {title}")


sec("top level")
out.append(", ".join(sorted(p.name + ("/" if p.is_dir() else "") for p in ROOT.iterdir())))
out.append("cji_agent: " + ", ".join(sorted(p.name + ("/" if p.is_dir() else "") for p in APP.iterdir())))
out.append("src/cji: " + ", ".join(sorted(p.name + ("/" if p.is_dir() else "") for p in SRC.iterdir())))

sec("infra files")
PRUNE = {"node_modules", ".next", ".venv", ".git", ".kiro", "__pycache__", ".mypy_cache", ".ruff_cache",
         ".pytest_cache", "test-results", "playwright-report", "data", "reports", "chroma_db", "dist", "build"}
PATS = ("Dockerfile*", "docker-compose*", ".dockerignore", "*.yml", "*.yaml", "*.toml", "*.sql", "alembic.ini",
        "Makefile", "*.ps1", "*.sh", ".pre-commit-config.yaml", ".gitleaks*", "CODEOWNERS", "SECURITY.md",
        "*.service", "Procfile", ".env*", "*.cfg", "*.ini", "*.lock", "requirements*.txt")
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in PRUNE and not d.endswith(".egg-info")]
    for f in filenames:
        if any(fnmatch.fnmatch(f, pat) for pat in PATS):
            out.append(str(Path(dirpath, f).relative_to(ROOT)).replace("\\", "/"))

sec("pyproject")
out.append((APP / "pyproject.toml").read_text(encoding="utf-8"))

sec("frontend package.json scripts/deps")
pkg = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
out.append(json.dumps({k: pkg.get(k) for k in ("scripts", "dependencies", "devDependencies", "engines")}, indent=1))

sec("keyword hits in src (file: count)")
keys = {
    "logging_setup": r"basicConfig|dictConfig|StreamHandler|FileHandler|RotatingFileHandler|Formatter\(",
    "request_id": r"request_id|X-Request-ID|correlation_id",
    "metrics_traces": r"prometheus|opentelemetry|otel|statsd|trace_id|traceparent",
    "audit": r"audit",
    "rate_limit": r"rate.?limit|RateLimit|Retry-After|429",
    "secrets": r"SECRET|api_key|token_hash|rotate|rotation|revoke",
    "health": r"/health|readiness|liveness|\bready\b",
    "backup": r"backup|pg_dump|restore|VACUUM INTO",
    "migration": r"CREATE TABLE|ALTER TABLE|migrat|schema_version|alembic",
    "dev_defaults": r"CJI_ENV|change-me|is_development|development",
    "budgets": r"budget|max_tokens|cost_usd|daily_limit|token_limit",
    "fault_injection": r"fault|inject|chaos",
    "redaction": r"redact|mask|scrub|sanitis|sanitiz",
}
for name, pat in keys.items():
    rx = re.compile(pat, re.I)
    hits = {}
    for p in SRC.rglob("*.py"):
        n = len(rx.findall(p.read_text(encoding="utf-8", errors="replace")))
        if n:
            hits[str(p.relative_to(SRC)).replace("\\", "/")] = n
    out.append(f"-- {name}: " + ", ".join(f"{k}:{v}" for k, v in sorted(hits.items(), key=lambda kv: -kv[1])[:25]))

sec("settings known keys")
env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": r"C:\Windows", "CJI_MODE": "demo",
       "DATABASE_URL": "postgresql://x:x@127.0.0.1:1/x", "SUPABASE_DATABASE_URL": "postgresql://x:x@127.0.0.1:1/x"}
r = subprocess.run([PY, "-c", "from cji.settings import KNOWN_KEYS; print(sorted(KNOWN_KEYS))"],
                   cwd=APP, capture_output=True, text=True, timeout=120, env=env)
out.append(r.stdout.strip() or r.stderr.strip()[-1500:])

sec("console scripts")
out.append("\n".join(l for l in (APP / "pyproject.toml").read_text(encoding="utf-8").splitlines() if "cji." in l))

sec("tests list")
out.append(", ".join(sorted(p.name for p in (APP / "tests").glob("test_*.py"))))
out.append("markers: " + ", ".join(sorted(set(re.findall(r"pytest\.mark\.(\w+)", "\n".join(
    p.read_text(encoding="utf-8", errors="replace") for p in (APP / "tests").glob("*.py")))))))

sec("github / ci")
gh = ROOT / ".github"
out.append(", ".join(str(p.relative_to(ROOT)) for p in gh.rglob("*")) if gh.exists() else "no .github")
out.append("git remotes: " + subprocess.run(["git", "remote", "-v"], cwd=ROOT, capture_output=True, text=True).stdout)

Path(r"C:\Users\sovan\.kiro\s15_survey.txt").write_text("\n".join(out).encode("ascii", "replace").decode(),
                                                       encoding="ascii")
print("ok", len(out))
