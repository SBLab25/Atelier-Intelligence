"""Helper for the compatibility launchers in cji_agent/ (Spec 11, OD-98): run main() of a module of the
installed `cji` package, or explain how to install it."""
import importlib
import sys

INSTALL = "cd cji_agent && pip install -r requirements.lock && pip install --no-deps -e ."


def run(module: str) -> None:
    try:
        target = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name != "cji":
            raise
        print(f"The cji package is not installed. Install it with:\n  {INSTALL}", file=sys.stderr)
        raise SystemExit(2) from None
    raise SystemExit(target.main())
