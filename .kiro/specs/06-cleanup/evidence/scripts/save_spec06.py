"""Spec 06 T7: tracked-file patch, copies of new and changed untracked files, pre-state of untracked edits."""
import hashlib
import pathlib
import shutil
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[5]
EV = pathlib.Path(__file__).resolve().parents[1]
lines = []
patch = EV / "spec06-tracked.patch"
r = subprocess.run(["git", "-C", str(REPO), "diff", "--binary", f"--output={patch}"], capture_output=True, text=True)
lines.append(f"spec06-tracked.patch exit={r.returncode} bytes={patch.stat().st_size}")
new_files = [
    "cji_agent/tests/test_cleanup.py", "cji_agent/tests/test_docs.py", "cji_agent/tests/test_dashboard_smoke.py",
    "docs/README.md", ".gitignore",
]
changed_untracked = [
    "cji_agent/tests/conftest.py", "cji_agent/repositories/duckdb_parquet.py", "cji_agent/settings/roles.py",
    "cji_agent/tests/test_ingestion_intelligence.py",
]
for rel in new_files + changed_untracked:
    src = REPO / rel
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", rel], capture_output=True).returncode == 0
    dst = EV / "spec06-new-files" / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    lines.append(f"copied {rel} tracked={tracked} sha256={hashlib.sha256(src.read_bytes()).hexdigest()[:16]}")
pathlib.Path(EV / "t7-saved.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n".join(lines))
