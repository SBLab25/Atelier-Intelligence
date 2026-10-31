"""
cji-settings check [--role ROLE] [--no-dotenv]   (Spec 04, CF-13; also `python -m cji.settings`)

Prints the resolved configuration with secrets redacted. Exit 0 when the role's
requirements are met, 2 on a configuration error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .errors import ConfigError
from .load import DEFAULT_DOTENV_PATH, load_settings
from .roles import ROLES_HELP, require


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cji-settings", description="Check CJI configuration.")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="validate settings for a role and print them (redacted)")
    check.add_argument("--role", default="cli", help=f"one of: {ROLES_HELP} (default: cli)")
    check.add_argument("--no-dotenv", action="store_true", help="ignore the .env file")
    args = parser.parse_args(argv)

    try:
        settings = load_settings(os.environ, None if args.no_dotenv else DEFAULT_DOTENV_PATH)
        require(settings, args.role)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    report = {
        "role": args.role,
        "status": "ok",
        "home": str(settings.storage.home),
        "settings": settings.describe(),
        "warnings": list(settings.warnings),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
