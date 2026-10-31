"""Shared helpers for the operations commands: the database URL without putting it on a command line."""

from __future__ import annotations

import os
from urllib.parse import urlsplit


class OpsError(Exception):
    """A command cannot continue; printed without a traceback, exit code 2."""


def database_url(env_name: str | None) -> str:
    """The URL from the named environment variable, else from settings (DATABASE_URL / SUPABASE_DATABASE_URL)."""
    if env_name:
        value = (os.environ.get(env_name) or "").strip()
        if not value:
            raise OpsError(f"{env_name} is not set")
        return value
    from cji.settings import get_settings

    value = get_settings().database.url_value() or ""
    if not value:
        raise OpsError("no database URL: set DATABASE_URL (or pass --database-url-env NAME)")
    return value


def describe_url(url: str) -> str:
    """`database on host:port` for messages; never the user name or password."""
    parts = urlsplit(url)
    name = (parts.path or "/").lstrip("/") or "?"
    host = parts.hostname or "?"
    return f"database {name!r} on {host}:{parts.port or 5432}"


def database_name(url: str) -> str:
    return (urlsplit(url).path or "/").lstrip("/")
