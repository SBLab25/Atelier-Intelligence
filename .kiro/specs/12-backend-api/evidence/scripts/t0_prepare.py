"""Spec 12 T0: save the starting point without committing.
- pre-spec12-tracked.patch: `git diff --binary` of tracked files.
- pre-spec12-untracked/: copies of every untracked, not ignored file under cji_agent/, with MANIFEST.txt.
"""
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "12-backend-api" / "evidence"


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


patch = git("diff", "--binary")
(EV / "pre-spec12-tracked.patch").write_bytes(patch)
dest = EV / "pre-spec12-untracked"
if dest.exists():
    shutil.rmtree(dest)
files = [p for p in git("ls-files", "--others", "--exclude-standard").decode("utf-8").splitlines()
         if p.startswith("cji_agent/")]
lines = []
for rel in sorted(files):
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / rel, target)
    lines.append(f"{rel} sha256={hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]}")
(dest / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
summary = f"pre-spec12-tracked.patch: {len(patch)} bytes\nuntracked files copied: {len(lines)}\n"
(EV / "t0.txt").write_text(summary, encoding="utf-8")
print(summary)
