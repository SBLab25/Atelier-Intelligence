"""
Spec 06 (OD-38): put a status banner at the top of historical documents. Bodies are
not changed. Idempotent: a document that already starts with a banner is skipped.
"""
from __future__ import annotations

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[5]
SUPERSEDED = ["Project_Memory.md", "Project_status.md", "docs/development_status.md"]
SUPERSEDED_BANNER = (
    "> **Superseded (2026-10-28).** Historical record, kept unchanged below. It is not the current state of the\n"
    "> project. Current behaviour: `README.md`; change history and decisions: `.kiro/specs/`; document status:\n"
    "> `docs/README.md`.\n\n"
)
HISTORICAL_BANNER = (
    "> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from\n"
    "> the code, the code and `README.md` win. Known divergences: `docs/README.md`.\n\n"
)


def historical() -> list[str]:
    docs = [p for p in (REPO / "docs").glob("*.md") if p.name not in {"README.md", "development_status.md"}]
    details = list((REPO / "Project Details").glob("*.md"))
    return sorted(str(p.relative_to(REPO)).replace("\\", "/") for p in docs + details)


def add(rel: str, banner: str) -> str:
    path = REPO / rel
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    bom = text.startswith("\ufeff")
    body = text[1:] if bom else text
    if body.lstrip().startswith("> **Superseded") or body.lstrip().startswith("> **Historical design reference"):
        return f"skip     {rel}"
    crlf = "\r\n" in body
    block = banner.replace("\n", "\r\n") if crlf else banner
    path.write_bytes((("\ufeff" if bom else "") + block + body).encode("utf-8"))
    return f"bannered {rel}"


def main() -> None:
    lines = [add(rel, SUPERSEDED_BANNER) for rel in SUPERSEDED]
    lines += [add(rel, HISTORICAL_BANNER) for rel in historical()]
    out = pathlib.Path(__file__).resolve().parents[1] / "t6-banners.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
