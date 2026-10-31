"""Spec 11 T0: rollback points (tracked patch against HEAD, copies of untracked files)."""
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "11-packaging" / "evidence"
patch = subprocess.run(["git", "-C", str(ROOT), "diff", "--binary"], capture_output=True, check=True).stdout
(EV / "pre-spec11-tracked.patch").write_bytes(patch)
untracked = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"],
                           capture_output=True, text=True, check=True).stdout.splitlines()
dest = EV / "pre-spec11-untracked"
if dest.exists():
    shutil.rmtree(dest)
copied = []
for rel in untracked:
    if rel.startswith(".kiro/") or not (rel.startswith("cji_agent/") or rel == ".gitattributes"):
        continue
    src = ROOT / rel
    if src.is_file():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append(rel)
(dest / "MANIFEST.txt").write_text("\n".join(copied) + "\n", encoding="utf-8")
out = f"patch {len(patch)} bytes; untracked copied: {len(copied)}"
(EV / "t0.txt").write_text(out + "\n", encoding="utf-8")
print(out)
