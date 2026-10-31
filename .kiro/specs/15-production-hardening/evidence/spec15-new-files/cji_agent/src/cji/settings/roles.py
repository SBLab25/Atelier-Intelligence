"""
Startup checks per role (Spec 04, CF-07). Each role checks only what it needs;
all problems are collected into one ConfigError. Pure module.

Roles: cli, launcher, collector, dashboard, api, mcp:<service>, production (Spec 15: the whole deployment).
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

ROLES_HELP = "cli, launcher, collector, dashboard, api, mcp:<service>, production"
MIN_CURSOR_SECRET_LENGTH = 32


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


def api_problems(settings: Settings) -> list[str]:
    """The /api/v1 service (Spec 12, OD-126): outside development, https origins and a fixed cursor key."""
    env = (settings.app.env or "").strip().lower()
    if env in ("development", "test"):
        return []
    problems: list[str] = []
    plain = [o for o in settings.api.cors_origins
             if urlsplit(o).scheme != "https" and (urlsplit(o).hostname or "") not in LOOPBACK_HOSTS]
    if plain:
        problems.append(f"CJI_API_CORS_ORIGINS must use https outside development (plain http only for loopback "
                        f"hosts): {', '.join(plain)}.")
    secret = secret_value(settings.api.cursor_secret)
    if len(secret) < MIN_CURSOR_SECRET_LENGTH:
        problems.append(
            f"CJI_API_CURSOR_SECRET must be a random value of at least {MIN_CURSOR_SECRET_LENGTH} characters "
            "(page cursors must survive restarts). Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))".'
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


def production_problems(settings: Settings) -> list[str]:
    """Spec 15 (OD-171): rules for a release host, on top of the api and collector checks. Each rule has a test."""
    problems: list[str] = []
    if settings.app.env != "production":
        problems.append(f"CJI_ENV must be production on a release host (it is {settings.app.env!r}).")
    if settings.app.mode == "realtime" and not settings.database.configured:
        problems.append(database_missing("CJI_MODE=realtime (production)"))
    if settings.observability.log_format != "json":
        problems.append("CJI_LOG_FORMAT must be json in production (log shippers parse one JSON object per line).")
    if settings.storage.audit_dir is None:
        problems.append("CJI_AUDIT_DIR is off; production keeps audit records (unset it or point it at a directory).")
    budget = settings.llm.run_budget
    if budget.max_cost_usd is not None and (settings.llm.price_input_per_mtok is None
                                            or settings.llm.price_output_per_mtok is None):
        problems.append("CJI_LLM_RUN_MAX_COST_USD is set but CJI_LLM_PRICE_INPUT_PER_MTOK / "
                        "CJI_LLM_PRICE_OUTPUT_PER_MTOK are not, so the cost budget cannot be enforced.")
    if settings.observability.langchain_tracing and not settings.observability.allow_third_party_tracing:
        problems.append("LANGCHAIN_TRACING_V2=true sends prompts and outputs to LangSmith (a third party). Turn it "
                        "off, or set CJI_ALLOW_THIRD_PARTY_TRACING=true to accept that.")
    api_host = settings.services.get("api").host
    if settings.api.trusted_proxy_hops > 0 and api_host not in LOOPBACK_HOSTS:
        problems.append(f"CJI_API_TRUSTED_PROXY_HOPS={settings.api.trusted_proxy_hops} with the API bound to "
                        f"{api_host}: anyone reaching the API directly could forge X-Forwarded-For. Bind it to "
                        "127.0.0.1 behind the proxy, or set the hops to 0.")
    problems += _token_file_problems(settings)
    return problems


def _token_file_problems(settings: Settings) -> list[str]:
    import json

    path = settings.api.tokens_file
    if not path.is_file():
        return [f"The API token file {path.name} does not exist; create an admin token with cji-api-token create."]
    try:
        tokens = json.loads(path.read_text(encoding="utf-8")).get("tokens", [])
    except (OSError, ValueError, AttributeError):
        return [f"The API token file {path.name} is not valid JSON."]
    admins = [t for t in tokens if isinstance(t, dict) and t.get("role") == "admin" and not t.get("revoked")]
    if not admins:
        return ["The API token file has no active admin token (needed for /api/v1/metrics and replace ingestion)."]
    return []


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
    elif role == "api":
        problems += api_problems(settings)
        if realtime and not has_db:
            problems.append(database_missing("CJI_MODE=realtime (api)"))
    elif role == "launcher":
        pass  # no launcher-specific requirements beyond the checks above
    elif role == "production":
        problems += collector_problems(
            settings.app.env, secret_value(settings.auth.admin_key), settings.cors.origins
        ) if settings.app.mode == "realtime" else []
        problems += api_problems(settings)
        problems += production_problems(settings)
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
