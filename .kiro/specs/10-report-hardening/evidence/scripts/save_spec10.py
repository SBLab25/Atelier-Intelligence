"""
Spec 10 T7: record the change set without committing.
- spec10-tracked.patch: `git diff --binary` of tracked files (against HEAD, like pre-spec10-tracked.patch).
- spec10-new-files/: current copies of every file Spec 10 created or changed that git does not track,
  with MANIFEST.txt (new / changed relative to pre-spec10-untracked/).
"""
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "10-report-hardening" / "evidence"
PRE = EV / "pre-spec10-untracked"
TOUCHED = [
    "README.md", ".gitattributes",
    "cji_agent/reporting/__init__.py", "cji_agent/reporting/model.py", "cji_agent/reporting/escape.py",
    "cji_agent/reporting/render.py", "cji_agent/reporting/output.py",
    "cji_agent/mcp_servers/report_server.py", "cji_agent/domain/insights.py", "cji_agent/agents/workers.py",
    "cji_agent/dashboard.py",
    "cji_agent/tests/test_reports.py", "cji_agent/tests/_report_checks.py",
    "cji_agent/tests/snapshots/report_basic.html", "cji_agent/tests/snapshots/report_empty.html",
    "cji_agent/tests/snapshots/report_malicious.html",
    "cji_agent/tests/conftest.py", "cji_agent/tests/test_p0_security.py", "cji_agent/tests/test_workflow.py",
]


def tracked(rel: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
                          capture_output=True).returncode == 0


patch = subprocess.run(["git", "-C", str(ROOT), "diff", "--binary"], capture_output=True, check=True).stdout
(EV / "spec10-tracked.patch").write_bytes(patch)
dest = EV / "spec10-new-files"
if dest.exists():
    shutil.rmtree(dest)
lines = []
for rel in TOUCHED:
    src = ROOT / rel
    if tracked(rel):
        lines.append(f"tracked   {rel} (in spec10-tracked.patch)")
        continue
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    state = "changed" if (PRE / rel).exists() else "new"
    lines.append(f"{state:9} {rel} sha256={hashlib.sha256(src.read_bytes()).hexdigest()[:16]}")
(dest / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
summary = f"spec10-tracked.patch: {len(patch)} bytes\n" + "\n".join(lines) + "\n"
(EV / "save-spec10.txt").write_text(summary, encoding="utf-8")
print(summary)
