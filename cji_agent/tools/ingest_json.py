"""Compatibility launcher: `python tools/ingest_json.py ...` = `cji-ingest-json ...` (Spec 11, OD-98)."""
import sys

try:
    from cji.tools.ingest_json import main
except ModuleNotFoundError as exc:
    if exc.name != "cji":
        raise
    print("The cji package is not installed. From cji_agent/: "
          "pip install -r requirements.lock && pip install --no-deps -e .", file=sys.stderr)
    raise SystemExit(2) from None
raise SystemExit(main())
