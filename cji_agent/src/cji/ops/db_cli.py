"""
cji-db migrate up [--to N] | down --to N | status [--json] [--require-current]  [--database-url-env NAME]
(Spec 15, OD-167)

Applies the packaged PostgreSQL migrations. Take a backup first (`cji-backup create`). Exit 0 on success, 1 when a
migration failed or `status` found a problem, 2 on a usage or configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy.exc import SQLAlchemyError

from .common import OpsError, database_url, describe_url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cji-db", description="CJI database schema migrations (PostgreSQL).")
    parser.add_argument(
        "--database-url-env",
        metavar="NAME",
        default=None,
        help="read the database URL from this environment variable (default: CJI settings)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    migrate = commands.add_parser("migrate", help="apply, revert or show migrations")
    actions = migrate.add_subparsers(dest="action", required=True)
    up_cmd = actions.add_parser("up", help="apply pending migrations")
    up_cmd.add_argument("--to", type=int, default=None, help="stop at this version")
    down_cmd = actions.add_parser("down", help="revert migrations down to a version (never below 1)")
    down_cmd.add_argument("--to", type=int, required=True)
    status_cmd = actions.add_parser("status", help="applied and pending migrations, column differences")
    status_cmd.add_argument("--json", action="store_true")
    status_cmd.add_argument(
        "--require-current", action="store_true", help="exit 1 unless the schema is at the version this release needs"
    )
    args = parser.parse_args(argv)

    from cji.logs import configure_logging

    configure_logging(service="cji-db")
    from .. import migrations  # noqa: F401  # package data must be importable before discovery
    from ..migrations import runner

    try:
        url = database_url(args.database_url_env)
        engine = runner.engine_for(url)
        target = describe_url(url)
        if args.action == "status":
            report = runner.status(engine)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(
                    f"{target}: schema version {report['current']} (release needs {report['required']}, "
                    f"latest {report['latest']})"
                )
                for name in report["applied"]:
                    print(f"  applied  {name}")
                for name in report["pending"]:
                    print(f"  pending  {name}")
                for line in report["column_differences"]:
                    print(f"  column   {line}")
                for line in report["problems"]:
                    print(f"  PROBLEM  {line}")
            behind = args.require_current and report["current"] < report["required"]
            return 1 if report["problems"] or behind else 0
        if args.action == "up":
            done = runner.up(engine, args.to)
        else:
            done = runner.down(engine, args.to)
        verb = "applied" if args.action == "up" else "reverted"
        print(
            f"{target}: {verb} {', '.join(done) if done else 'nothing'}; "
            f"schema version {runner.current_version(engine)}"
        )
        return 0
    except OpsError as exc:
        print(f"cji-db: {exc}", file=sys.stderr)
        return 2
    except runner.MigrationError as exc:
        print(f"cji-db: {exc}", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"cji-db: database error: {runner._reason(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
