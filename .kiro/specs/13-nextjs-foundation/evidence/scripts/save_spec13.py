"""
Spec 13: record the change set without committing.
- spec13-tracked.patch: `git diff --binary` of tracked files (the README section is the only tracked change).
- spec13-new-files/: copies of the new frontend files (untracked, not ignored: no node_modules, .next, test output)
  with MANIFEST.txt (path, size, sha256).
"""
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "13-nextjs-foundation" / "evidence"


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


patch = git("diff", "--binary")
(EV / "spec13-tracked.patch").write_bytes(patch)
pre = (EV / "pre-spec13-tracked.patch").read_bytes()
new = [p for p in git("ls-files", "--others", "--exclude-standard", "--", "frontend").decode("utf-8").splitlines()]
dest = EV / "spec13-new-files"
if dest.exists():
    shutil.rmtree(dest)
lines = []
for rel in sorted(new):
    src = ROOT / rel
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    data = src.read_bytes()
    lines.append(f"{rel} {len(data)} sha256={hashlib.sha256(data).hexdigest()[:16]}")
(dest / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
changed = sorted(set(p for p in git("diff", "--name-only").decode().splitlines()))
summary = (f"spec13-tracked.patch: {len(patch)} bytes (pre-spec13: {len(pre)} bytes)\n"
           f"tracked files changed in total: {len(changed)}\n"
           f"new frontend files copied: {len(lines)}\n" + "\n".join(lines) + "\n")
(EV / "save-spec13.txt").write_text(summary, encoding="utf-8")
print(summary[:3000])
