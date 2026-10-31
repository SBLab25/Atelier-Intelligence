"""
Startup checks per role (Spec 04, CF-07). Each role checks only what it needs;
all problems are collected into one ConfigError. Pure module.

Roles: cli, launcher, collector, dashboard, mcp:<service>.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlsplit

from .errors import ConfigError
from .model import (
    KNOWN_DEFAULT_ADMIN_KEYS,
    MIN_ADMIN_KEY_LENGTH,
    Settings,
    secret_value,
)
from .services import LOOPBACK_HOSTS, env_prefix

ROLES_HELP = "cli, launcher, collector, dashboard, mcp:<service>"


def database_missing(purpose: str) -> str:
    return (
        f"DATABASE_URL is not set (SUPABASE_DATABASE_URL is also accepted). {purpose} needs "
        "PostgreSQL: set DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB."
    )


def collector_problems(env: str, admin_key: str | None, origins: Sequence[str]) -> list[str]:
    """Spec 02 rule: anything except an explicit 'development' fails closed."""
    if (env or "").strip().lower() == "development":
        return []
    problems: list[str] = []
    if not admin_key or admin_key in KNOWN_DEFAULT_ADMIN_KEYS or len(admin_key) < MIN_ADMIN_KEY_LENGTH:
        problems.append(
            f"CJI_ADMIN_KEY must be a random value of at least {MIN_ADMIN_KEY_LENGTH} characters "
            "(it is unset, too short or a shipped default). Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))". '
            "For local use set CJI_ENV=development."
        )
    if not origins:
        problems.append(
            "CJI_CORS_ORIGINS is empty. List the browser origins allowed to call the collector, "
            "comma-separated, e.g. https://app.example.com."
        )
    if (env or "").strip().lower() == "production":
        plain = [o for o in origins
                 if urlsplit(o).scheme != "https" and (urlsplit(o).hostname or "") not in LOOPBACK_HOSTS]
        if plain:
            problems.append(
                f"CJI_CORS_ORIGINS must use https in production (plain http only for loopback hosts): "
                f"{', '.join(plain)}."
            )
    return problems


def endpoint_problems(settings: Settings) -> list[str]:
    """In production, configured remote endpoints must use https unless they are loopback."""
    if settings.app.env != "production":
        return []
    problems: list[str] = []
    for endpoint in settings.services.services:
        if endpoint.url_override is None:
            continue
        parts = urlsplit(endpoint.url_override)
        if parts.scheme == "http" and (parts.hostname or "") not in LOOPBACK_HOSTS:
            key = f"{env_prefix(endpoint.name)}_URL"
            if endpoint.name == "collector":
                key += " (or COLLECTOR_HOST)"
            problems.append(
                f"{key} must use https in production; {endpoint.url_override!r} is plain http."
            )
    return problems


def require(settings: Settings, role: str) -> Settings:
    """Raise ConfigError if `settings` cannot serve `role`; return them unchanged otherwise."""
    problems: list[str] = []
    realtime = settings.app.mode == "realtime"
    has_db = settings.database.configured

    if role == "collector":
        problems += collector_problems(
            settings.app.env, secret_value(settings.auth.admin_key), settings.cors.origins
        )
        if not has_db:
            problems.append(database_missing("The collector"))
    elif role in ("cli", "dashboard"):
        if realtime and not has_db:
            problems.append(database_missing(f"CJI_MODE=realtime ({role})"))
    elif role == "launcher":
        pass  # no launcher-specific requirements beyond the checks above
    elif role.startswith("mcp:"):
        name = role.removeprefix("mcp:")
        mcp_names = [e.name for e in settings.services.mcp_services()]
        if name not in mcp_names:
            problems.append(f"Unknown MCP service '{name}'. Known: {', '.join(sorted(mcp_names))}.")
        elif name == "cji-journey-data" and realtime and not has_db:
            problems.append(database_missing("CJI_MODE=realtime (cji-journey-data)"))
    else:
        problems.append(f"Unknown role '{role}'. Use one of: {ROLES_HELP}.")

    problems += endpoint_problems(settings)
    if problems:
        raise ConfigError(problems, role=role, env=settings.app.env)
    return settings
