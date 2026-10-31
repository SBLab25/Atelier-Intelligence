"""
Write (or check) the OpenAPI snapshot `cji_agent/openapi/v1.json` (Spec 12, OD-123).

    python -m cji.api.openapi_snapshot            # regenerate
    python -m cji.api.openapi_snapshot --check    # exit 1 when the snapshot differs from the app

The document does not depend on the environment (the docs UI route is not part of it), so test settings are used.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "openapi" / "v1.json"


def current_document() -> dict[str, Any]:
    from cji.settings import make_test_settings

    from .app import create_app

    with tempfile.TemporaryDirectory() as tmp:
        return create_app(make_test_settings(Path(tmp), CJI_MODE="demo")).openapi()


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m cji.api.openapi_snapshot", description=__doc__.splitlines()[1])
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH, help="snapshot file (default: %(default)s)")
    parser.add_argument("--check", action="store_true", help="compare instead of writing")
    args = parser.parse_args(argv)
    doc = current_document()
    if args.check:
        if not args.path.exists() or json.loads(args.path.read_text(encoding="utf-8")) != doc:
            print(f"{args.path} is out of date; run python -m cji.api.openapi_snapshot", file=sys.stderr)
            return 1
        print(f"{args.path} matches the app")
        return 0
    args.path.parent.mkdir(parents=True, exist_ok=True)
    args.path.write_text(render(doc), encoding="utf-8", newline="\n")
    print(f"wrote {args.path} ({len(doc['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
