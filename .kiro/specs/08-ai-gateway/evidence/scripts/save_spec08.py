"""
Spec 08 T7: record the change set without committing.

- spec08-tracked.patch: `git diff --binary` of tracked files (against HEAD, like pre-spec08-tracked.patch).
- spec08-new-files/: current copies of every file Spec 08 created or changed that git does not track,
  with MANIFEST.txt (new / changed relative to pre-spec08-untracked/).
"""
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "08-ai-gateway" / "evidence"
PRE = EV / "pre-spec08-untracked"
TOUCHED = [
    "README.md", "cji_agent/.env.example", "cji_agent/.gitignore", "cji_agent/requirements.txt",
    "cji_agent/integrations/__init__.py", "cji_agent/integrations/audit.py", "cji_agent/integrations/context.py",
    "cji_agent/integrations/errors.py", "cji_agent/integrations/llm.py", "cji_agent/integrations/policy.py",
    "cji_agent/integrations/providers.py", "cji_agent/integrations/testing.py", "cji_agent/integrations/tools.py",
    "cji_agent/integrations/types.py", "cji_agent/integrations/usage.py",
    "cji_agent/settings/model.py", "cji_agent/settings/load.py",
    "cji_agent/tools/mcp_client.py", "cji_agent/agents/workers.py", "cji_agent/agents/ingestion_worker.py",
    "cji_agent/mcp_servers/insight_server.py", "cji_agent/mcp_servers/report_server.py",
    "cji_agent/mcp_servers/ingestion_intelligence_server.py", "cji_agent/state.py", "cji_agent/main.py",
    "cji_agent/tests/conftest.py", "cji_agent/tests/test_gateway.py", "cji_agent/tests/test_settings.py",
    "cji_agent/tests/test_contracts.py", "cji_agent/tests/test_cleanup.py",
    "cji_agent/tests/test_ingestion_intelligence.py",
]


def tracked(rel: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
                          capture_output=True).returncode == 0


patch = subprocess.run(["git", "-C", str(ROOT), "diff", "--binary"], capture_output=True, check=True).stdout
(EV / "spec08-tracked.patch").write_bytes(patch)
dest = EV / "spec08-new-files"
if dest.exists():
    shutil.rmtree(dest)
lines = ["deleted   cji_agent/guardrails/rate_limiter.py (copy in evidence/removed/; tracked: in spec08-tracked.patch)"]
for rel in TOUCHED:
    src = ROOT / rel
    if tracked(rel):
        lines.append(f"tracked   {rel} (in spec08-tracked.patch)")
        continue
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    state = "changed" if (PRE / rel).exists() else "new"
    lines.append(f"{state:9} {rel} sha256={hashlib.sha256(src.read_bytes()).hexdigest()[:16]}")
(dest / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"spec08-tracked.patch: {len(patch)} bytes")
print("\n".join(lines))
