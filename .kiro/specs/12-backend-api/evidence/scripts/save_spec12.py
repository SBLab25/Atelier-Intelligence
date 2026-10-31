"""
Spec 12: record the change set without committing.
- spec12-tracked.patch: `git diff --binary` of tracked files (against the index, like pre-spec12-tracked.patch).
- spec12-new-files/: current copies of every untracked, not ignored file under cji_agent/ with MANIFEST.txt:
  new (not in pre-spec12-untracked/), changed or unchanged (compared with the T0 copy).
"""
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "12-backend-api" / "evidence"
PRE = EV / "pre-spec12-untracked"


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


patch = git("diff", "--binary")
(EV / "spec12-tracked.patch").write_bytes(patch)
untracked = [p for p in git("ls-files", "--others", "--exclude-standard").decode("utf-8").splitlines()
             if p.startswith("cji_agent/")]
dest = EV / "spec12-new-files"
if dest.exists():
    shutil.rmtree(dest)
lines, counts = [], {}
for rel in sorted(untracked):
    src = ROOT / rel
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    now = src.read_bytes()
    before = (PRE / rel).read_bytes() if (PRE / rel).exists() else None
    if before is None:
        state = "new"
    elif before.replace(b"\r\n", b"\n") == now.replace(b"\r\n", b"\n"):
        state = "unchanged"
    else:
        state = "changed"
    counts[state] = counts.get(state, 0) + 1
    lines.append(f"{state:10} {rel} sha256={hashlib.sha256(now).hexdigest()[:16]}")
(dest / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
summary = (f"spec12-tracked.patch: {len(patch)} bytes\nuntracked files copied: {len(lines)} {counts}\n"
           + "\n".join(lines) + "\n")
(EV / "save-spec12.txt").write_text(summary, encoding="utf-8")
print(summary[:4000])
