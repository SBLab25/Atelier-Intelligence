"""
Spec 07 T7: record the change set without committing.

- spec07-tracked.patch: `git diff` of tracked files (against HEAD, like pre-spec07-tracked.patch).
- spec07-new-files/: current copies of every file Spec 07 created or changed that git does not track,
  with MANIFEST.txt (path, sha256, new or changed).
"""
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "07-collector" / "evidence"
PRE = EV / "pre-spec07-untracked"
TOUCHED = [
    "README.md",
    "cji_agent/.env.example",
    "cji_agent/collector/api.py",
    "cji_agent/collector/ingest.py",
    "cji_agent/collector/middleware.py",
    "cji_agent/collector/models.py",
    "cji_agent/collector/security.py",
    "cji_agent/domain/events.py",
    "cji_agent/settings/load.py",
    "cji_agent/settings/model.py",
    "cji_agent/settings/roles.py",
    "cji_agent/snippets/verify_tracker.py",
    "cji_agent/tracker/snippet_generator.py",
    "cji_agent/tests/conftest.py",
    "cji_agent/tests/test_collector.py",
    "cji_agent/tests/test_collector_models.py",
    "cji_agent/tests/test_contracts.py",
    "cji_agent/tests/test_p0_security.py",
    "cji_agent/tests/test_repositories.py",
]


def tracked(rel: str) -> bool:
    return subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel],
                          capture_output=True).returncode == 0


patch = subprocess.run(["git", "-C", str(ROOT), "diff", "--binary"], capture_output=True, check=True).stdout
(EV / "spec07-tracked.patch").write_bytes(patch)

dest = EV / "spec07-new-files"
if dest.exists():
    shutil.rmtree(dest)
lines = []
for rel in TOUCHED:
    src = ROOT / rel
    if tracked(rel):
        lines.append(f"tracked   {rel} (in spec07-tracked.patch)")
        continue
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    state = "changed" if any(PRE.rglob(src.name)) else "new"
    lines.append(f"{state:9} {rel} sha256={hashlib.sha256(src.read_bytes()).hexdigest()[:16]}")
(dest / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"spec07-tracked.patch: {len(patch)} bytes")
print("\n".join(lines))
