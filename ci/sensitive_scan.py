"""
Canary scan (Spec 15, OD-173): `python ci/sensitive_scan.py --markers FILE --paths P [P ...] [--user-allowed GLOB ...]
[--report FILE]`.

The gate gives every secret of a test deployment (LLM keys, admin key, cursor and session keys, API tokens, the
database password) a unique marker value, and gives ingested events marker user and session ids. After the full
flow this scan searches every file under the given paths as bytes (text, SQLite, the Next.js bundle, recorded HTTP
responses): secret markers must appear nowhere; user markers only in files matching --user-allowed (the event store
and the backup dump).

Markers file (JSON): {"secret": {"NAME": "value", ...}, "user": {"NAME": "value", ...}}. Values are never printed;
the report names the marker and the files. Exit 1 on any violation, 2 on bad input.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

MAX_BYTES = 512 * 1024 * 1024
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv"}


def files_under(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_file():
            found.append(path)
        elif path.is_dir():
            for item in sorted(path.rglob("*")):
                if item.is_file() and not SKIP_DIRS.intersection(item.relative_to(path).parts):
                    found.append(item)
    return found


def variants(value: str) -> list[bytes]:
    """The marker as UTF-8 and UTF-16-LE (Windows tools, SQLite text in UTF-16 databases)."""
    return [value.encode("utf-8"), value.encode("utf-16-le")]


def scan(
    files: list[Path], markers: dict[str, dict[str, str]], user_allowed: list[str]
) -> tuple[dict[str, list[str]], list[str], int]:
    hits: dict[str, list[str]] = {}
    violations: list[str] = []
    scanned = 0
    for path in files:
        try:
            if path.stat().st_size > MAX_BYTES:
                violations.append(f"not scanned (over {MAX_BYTES} bytes): {path}")
                continue
            data = path.read_bytes()
        except OSError as exc:
            violations.append(f"not readable ({type(exc).__name__}): {path}")
            continue
        scanned += 1
        posix = path.as_posix()
        for kind, named in markers.items():
            for name, value in named.items():
                if any(v in data for v in variants(value)):
                    hits.setdefault(f"{kind}:{name}", []).append(posix)
                    allowed = kind == "user" and any(fnmatch.fnmatch(posix, pattern) for pattern in user_allowed)
                    if not allowed:
                        violations.append(f"{kind} marker {name} found in {posix}")
    return hits, violations, scanned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ci/sensitive_scan.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--markers", type=Path, required=True)
    parser.add_argument("--paths", type=Path, nargs="+", required=True)
    parser.add_argument("--user-allowed", nargs="*", default=[], help="glob (posix path) where user markers may be")
    parser.add_argument("--report", type=Path, default=None, help="write the report as JSON (no marker values)")
    args = parser.parse_args(argv)
    try:
        raw = json.loads(args.markers.read_text(encoding="utf-8"))
        markers = {kind: {str(k): str(v) for k, v in raw.get(kind, {}).items()} for kind in ("secret", "user")}
    except (OSError, ValueError, AttributeError) as exc:
        print(f"markers file unusable: {type(exc).__name__}", file=sys.stderr)
        return 2
    short = [f"{kind}:{name}" for kind, named in markers.items() for name, value in named.items() if len(value) < 12]
    if short or not any(markers.values()):
        print(f"markers must be at least 12 characters (and at least one given): {short}", file=sys.stderr)
        return 2
    files = files_under(args.paths)
    hits, violations, scanned = scan(files, markers, args.user_allowed)
    report = {
        "files_scanned": scanned,
        "paths": [p.as_posix() for p in args.paths],
        "markers": {
            f"{kind}:{name}": hits.get(f"{kind}:{name}", []) for kind, named in markers.items() for name in named
        },
        "violations": violations,
        "result": "clean" if not violations else "violations",
        "ok": not violations,  # read by ci/release_check.py
        "detail": f"{scanned} files, {sum(len(v) for v in markers.values())} markers, {len(violations)} violation(s)",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for marker, where in report["markers"].items():
        print(f"{marker:<40} {len(where)} file(s)" + (f": {', '.join(where[:5])}" if where else ""))
    for line in violations:
        print(f"VIOLATION {line}")
    print(f"canary scan: {scanned} files, {len(violations)} violation(s)")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
