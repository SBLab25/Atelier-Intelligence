"""
Spec 11 T7: record the change set without committing.
- spec11-tracked.patch: `git diff --binary` of tracked files (against the index, like pre-spec11-tracked.patch). The
  move shows as deletions of the old tracked paths; the new paths are untracked and copied below.
- spec11-new-files/: current copies of every untracked, not ignored file under cji_agent/
  (the moved package, launchers, pyproject.toml, requirements.lock, new tests), with MANIFEST.txt:
  new / moved (same content as a file in pre-spec11-untracked/ or HEAD at the old path) / moved+changed / changed.
"""
import hashlib
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "11-packaging" / "evidence"
PRE = EV / "pre-spec11-untracked"


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


def old_path(rel: str) -> str:
    """cji_agent/src/cji/x -> cji_agent/x (tools/generate_diverse.py -> generate_diverse.py)."""
    if rel == "cji_agent/src/cji/tools/generate_diverse.py":
        return "cji_agent/generate_diverse.py"
    return rel.replace("cji_agent/src/cji/", "cji_agent/", 1)


def previous(rel: str) -> bytes | None:
    old = old_path(rel)
    if (PRE / old).exists():
        return (PRE / old).read_bytes()
    show = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{old}"], capture_output=True)
    return show.stdout if show.returncode == 0 else None


patch = git("diff", "--binary")
(EV / "spec11-tracked.patch").write_bytes(patch)
untracked = [p for p in git("ls-files", "--others", "--exclude-standard").decode("utf-8").splitlines()
             if p.startswith("cji_agent/")]
dest = EV / "spec11-new-files"
if dest.exists():
    shutil.rmtree(dest)
lines, counts = [], {}
for rel in sorted(untracked):
    src = ROOT / rel
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    before = previous(rel)
    now = src.read_bytes()
    moved = old_path(rel) != rel
    if before is None:
        state = "new"
    elif before.replace(b"\r\n", b"\n") == now.replace(b"\r\n", b"\n"):
        state = "moved" if moved else "unchanged"
    else:
        state = "moved+changed" if moved else "changed"
    counts[state] = counts.get(state, 0) + 1
    lines.append(f"{state:14} {rel} sha256={hashlib.sha256(now).hexdigest()[:16]}"
                 + (f" (was {old_path(rel)})" if moved and before is not None else ""))
(dest / "MANIFEST.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
summary = (f"spec11-tracked.patch: {len(patch)} bytes\nuntracked files copied: {len(lines)} {counts}\n"
           + "\n".join(lines) + "\n")
(EV / "save-spec11.txt").write_text(summary, encoding="utf-8")
print(summary[:3000])
