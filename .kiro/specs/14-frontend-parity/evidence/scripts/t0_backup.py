"""Spec 14 T0: copy every file this Spec may change to evidence/pre-spec14-untracked/ (same relative paths).
Run once before the first edit; refuses to overwrite an existing backup."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DEST = ROOT / ".kiro" / "specs" / "14-frontend-parity" / "evidence" / "pre-spec14-untracked"
FILES = [
    "README.md", ".env.example", "docs/README.md",
    "cji_agent/.env.example",
    "cji_agent/openapi/v1.json",
    "cji_agent/src/cji/settings/load.py", "cji_agent/src/cji/settings/model.py",
    "cji_agent/src/cji/state.py", "cji_agent/src/cji/workflow/runtime.py",
    "cji_agent/src/cji/agents/workers.py", "cji_agent/src/cji/tools/ingest_json.py",
    "cji_agent/src/cji/services/runs.py",
]
TREES = ["cji_agent/src/cji/api", "frontend/src", "frontend/e2e", "frontend/tests", "frontend/scripts"]
FRONTEND_FILES = ["package.json", "package-lock.json", "next.config.ts", "playwright.config.ts", "vitest.config.ts",
                  "eslint.config.mjs", "tsconfig.json", ".env.example", "README.md"]


def main() -> int:
    if DEST.exists():
        print(f"backup exists: {DEST}")
        return 1
    copied = 0
    paths = [ROOT / f for f in FILES] + [ROOT / "frontend" / f for f in FRONTEND_FILES]
    for tree in TREES:
        paths += [p for p in (ROOT / tree).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    for src in paths:
        if not src.exists():
            print(f"missing (skipped): {src.relative_to(ROOT).as_posix()}")
            continue
        target = DEST / src.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied += 1
    print(f"copied {copied} files to {DEST.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
