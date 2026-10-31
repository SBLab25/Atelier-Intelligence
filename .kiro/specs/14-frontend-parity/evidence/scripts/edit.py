"""Exact-text edits with count checks (Spec 14). `apply(path, [(old, new), ...])`: every `old` must occur exactly
once (or `count` times for (old, new, count)); nothing is written unless all edits match. LF line endings kept."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]


def apply(rel: str, edits: list[tuple]) -> None:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    crlf = "\r\n" in text
    if crlf:
        text = text.replace("\r\n", "\n")
    for edit in edits:
        old, new = edit[0], edit[1]
        want = edit[2] if len(edit) > 2 else 1
        found = text.count(old)
        if found != want:
            raise SystemExit(f"{rel}: expected {want} match(es), found {found}: {old[:80]!r}")
        text = text.replace(old, new)
    if crlf:
        text = text.replace("\n", "\r\n")
    path.write_bytes(text.encode("utf-8"))
    print(f"edited {rel} ({len(edits)} edits)")
