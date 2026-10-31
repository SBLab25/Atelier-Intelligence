"""Compatibility launcher: `python tracker/snippet_generator.py ...` = `cji-snippet ...` (Spec 11, OD-98)."""
import sys

try:
    from cji.tracker.snippet_generator import main
except ModuleNotFoundError as exc:
    if exc.name != "cji":
        raise
    print("The cji package is not installed. From cji_agent/: "
          "pip install -r requirements.lock && pip install --no-deps -e .", file=sys.stderr)
    raise SystemExit(2) from None
raise SystemExit(main())
