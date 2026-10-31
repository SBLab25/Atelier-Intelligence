"""
cji-api-token: manage /api/v1 bearer tokens (Spec 12, OD-109).

    cji-api-token create --label nextjs-dev --role operator --journey user_onboarding [--expires-days 90]
    cji-api-token list
    cji-api-token revoke tok_0123456789ab

The token value is printed once by `create`; the file keeps only its SHA-256.
Default file: CJI_API_TOKENS_FILE (default <CJI_HOME>/data/api_tokens.json).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cji.api.auth import (
    ROLE_RANK,
    TokenFileError,
    create_token,
    load_token_file,
    revoke_token,
)


def _default_file() -> Path:
    from cji.settings import get_settings

    return get_settings().api.tokens_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cji-api-token", description="Manage CJI API bearer tokens.")
    parser.add_argument("--file", type=Path, default=None, help="token file (default: CJI_API_TOKENS_FILE)")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create a token and print it once")
    create.add_argument("--label", required=True)
    create.add_argument("--role", required=True, choices=sorted(ROLE_RANK))
    create.add_argument("--journey", action="append", required=True,
                        help="journey the token may read (repeat; '*' = all journeys)")
    create.add_argument("--expires-days", type=int, default=None)
    commands.add_parser("list", help="list tokens (ids, labels, roles, journeys; never values)")
    revoke = commands.add_parser("revoke", help="revoke a token by id")
    revoke.add_argument("token_id")
    args = parser.parse_args(argv)
    path = args.file or _default_file()
    try:
        if args.command == "create":
            token = create_token(path, label=args.label, role=args.role, journeys=args.journey,
                                 expires_days=args.expires_days)
            print("Store this token now; it is not shown again:")
            print(f"  {token}")
            return 0
        if args.command == "list":
            for entry in load_token_file(path).tokens:
                state = "revoked" if entry.revoked else (f"expires {entry.expires_at}" if entry.expires_at else "active")
                print(f"{entry.id}  {entry.label}  {entry.role}  {','.join(entry.journeys)}  {state}")
            return 0
        if not revoke_token(path, args.token_id):
            print(f"No active token {args.token_id}.", file=sys.stderr)
            return 1
        print(f"Revoked {args.token_id}.")
        return 0
    except TokenFileError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
