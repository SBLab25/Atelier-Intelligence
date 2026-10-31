"""
Spec 09 T7: record the change set without committing.
- spec09-tracked.patch: `git diff --binary` of tracked files (against HEAD, like pre-spec09-tracked.patch).
- spec09-new-files/: current copies of every file Spec 09 created or changed that git does not track,
  with MANIFEST.txt (new / changed relative to pre-spec09-untracked/).
"""
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "09-durable-workflow" / "evidence"
PRE = EV / "pre-spec09-untracked"
TOUCHED = [
    "README.md", "cji_agent/.env.example",
    "cji_agent/workflow/__init__.py", "cji_agent/workflow/errors.py", "cji_agent/workflow/step.py",
    "cji_agent/workflow/runtime.py",
    "cji_agent/domain/runs.py", "cji_agent/state.py", "cji_agent/graph.py", "cji_agent/main.py",
    "cji_agent/agents/supervisor.py", "cji_agent/agents/workers.py", "cji_agent/agents/ingestion_worker.py",
    "cji_agent/settings/model.py", "cji_agent/settings/load.py", "cji_agent/integrations/audit.py",
    "cji_agent/mcp_servers/insight_server.py", "cji_agent/mcp_servers/report_server.py",
    "cji_agent/mcp_servers/ingestion_intelligence_server.py",
    "cji_agent/tests/conftest.py", "cji_agent/tests/test_workflow.py", "cji_agent/tests/_workflow_stubs.py",
    "cji_agent/tests/test_agent_layer.py", "cji_agent/tests/test_supervisor.py",
]


def tracked(rel: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
                          capture_output=True).returncode == 0


patch = subprocess.run(["git", "-C", str(ROOT), "diff", "--binary"], capture_output=True, check=True).stdout
(EV / "spec09-tracked.patch").write_bytes(patch)
dest = EV / "spec09-new-files"
if dest.exists():
    shutil.rmtree(dest)
lines = []
for rel in TOUCHED:
    src = ROOT / rel
    if tracked(rel):
        lines.append(f"tracked   {rel} (in spec09-tracked.patch)")
        continue
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    state = "changed" if (PRE / rel).exists() else "new"
    lines.append(f"{state:9} {rel} sha256={hashlib.sha256(src.read_bytes()).hexdigest()[:16]}")
(dest / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"spec09-tracked.patch: {len(patch)} bytes")
print("\n".join(lines))
