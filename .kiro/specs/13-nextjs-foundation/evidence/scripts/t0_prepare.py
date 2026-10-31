"""Spec 13 T0: save the tracked diff and the untracked file list before any change (no commit)."""
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[5]
EV = ROOT / ".kiro" / "specs" / "13-nextjs-foundation" / "evidence"


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


patch = git("diff", "--binary")
(EV / "pre-spec13-tracked.patch").write_bytes(patch)
untracked = git("ls-files", "--others", "--exclude-standard").decode("utf-8").splitlines()
(EV / "pre-spec13-untracked.txt").write_text("\n".join(untracked) + "\n", encoding="utf-8")
frontend = ROOT / "frontend"
out = (f"pre-spec13-tracked.patch: {len(patch)} bytes\nuntracked files: {len(untracked)}\n"
       f"frontend/ exists: {frontend.exists()}\n")
(EV / "t0.txt").write_text(out, encoding="utf-8")
print(out)
