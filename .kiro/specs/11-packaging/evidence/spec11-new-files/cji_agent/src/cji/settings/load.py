"""
Load Settings from an environment mapping (Spec 04, CF-01/CF-04/CF-07/CF-08).

Process environment wins over `.env`; `.env` is never read when CJI_ENV=test.
Types and forms are checked here; every problem is collected into one ConfigError.
Pure module: stdlib, pydantic and python-dotenv only. Reads files only when called.
"""

from __future__ import annotations

import difflib
import logging
import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from dotenv import dotenv_values
from pydantic import SecretStr

from .errors import ConfigError
from .model import (
    DEFAULT_LLM_MODELS,
    ENVIRONMENTS,
    LLM_PROVIDERS,
    MODES,
    AppSettings,
    AuthSettings,
    BudgetSettings,
    CollectorSettings,
    CorsSettings,
    DatabaseSettings,
    KeepAliveSettings,
    LLMSettings,
    MCPSettings,
    ObservabilitySettings,
    RetryPolicy,
    RunBudgetSettings,
    Settings,
    StorageSettings,
    WorkflowSettings,
    llm_model_mismatch,
)
from .services import (
    DEFAULT_SERVICE_HOST,
    DEFAULT_SERVICES,
    ServiceEndpoint,
    ServiceRegistry,
    env_prefix,
)


class _HomeDotenv:
    """Default `dotenv_path`: the `.env` file in the runtime home, found when settings load (Spec 11, OD-99)."""

    def __repr__(self) -> str:
        return "<CJI_HOME>/.env"


DEFAULT_DOTENV_PATH: Final[_HomeDotenv] = _HomeDotenv()


def resolve_home(environ: Mapping[str, str] | None = None) -> Path:
    """The runtime home: CJI_HOME (relative values resolve against the working directory) or the working
    directory. data/, reports/ and .env live here unless configured otherwise (Spec 11, OD-99)."""
    raw = ((os.environ if environ is None else environ).get("CJI_HOME") or "").strip()
    return (Path(raw).expanduser() if raw else Path.cwd()).resolve()
logger = logging.getLogger("cji.settings")

_SERVICE_KEYS = tuple(
    f"{env_prefix(spec.name)}_{suffix}" for spec in DEFAULT_SERVICES for suffix in ("PORT", "URL")
)

# Every variable the application reads. Unknown CJI_* names are reported.
KNOWN_KEYS: frozenset[str] = frozenset({
    "CJI_ENV", "CJI_MODE", "JOURNEY_NAME",
    "CJI_HOME", "CJI_DATA_DIR", "CJI_REPORTS_DIR",
    "DATABASE_URL", "SUPABASE_DATABASE_URL",
    "CJI_SERVICE_HOST", *_SERVICE_KEYS, "COLLECTOR_HOST", "COLLECTOR_PORT",
    "CJI_MCP_CONNECT_TIMEOUT_S", "CJI_MCP_READ_TIMEOUT_S",
    "LLM_MODEL", "LLM_TEMPERATURE", "LLM_MAX_TOKENS",
    "GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
    "CJI_LLM_TIMEOUT_S", "CJI_LLM_RETRY_ATTEMPTS", "CJI_LLM_RETRY_MIN_S", "CJI_LLM_RETRY_MAX_S",
    "CJI_LLM_PROVIDER", "CJI_LLM_DEADLINE_S", "CJI_LLM_RATE_PER_MIN", "CJI_LLM_RUN_MAX_CALLS",
    "CJI_LLM_RUN_MAX_TOKENS", "CJI_LLM_RUN_MAX_COST_USD", "CJI_LLM_PRICE_INPUT_PER_MTOK",
    "CJI_LLM_PRICE_OUTPUT_PER_MTOK", "CJI_MCP_CALL_TIMEOUT_S", "CJI_AUDIT_DIR",
    "CJI_CHECKPOINTS_DB", "CJI_WORKFLOW_STEP_TIMEOUT_S", "CJI_WORKFLOW_STEP_ATTEMPTS", "CJI_WORKFLOW_RETRY_BACKOFF_S",
    "MAX_AGENT_ITERATIONS", "CJI_PIPELINE_TIMEOUT_S",
    "INGESTION_SAMPLE_ROWS", "INGESTION_CONFIDENCE_THRESHOLD", "FRICTION_SCORE_THRESHOLD",
    "REALTIME_WINDOW_MINUTES", "REALTIME_AUTO_RUN_INTERVAL",
    "CJI_CORS_ORIGINS", "CJI_ADMIN_KEY",
    "CJI_KEEPALIVE_URL", "CJI_KEEPALIVE_INTERVAL_S",
    "CJI_COLLECTOR_MAX_BODY_BYTES", "CJI_COLLECTOR_RATE_PER_KEY", "CJI_COLLECTOR_RATE_PER_IP",
    "CJI_COLLECTOR_ADMIN_RATE_PER_IP", "CJI_COLLECTOR_TRUSTED_PROXY_HOPS",
    "LANGCHAIN_TRACING_V2", "LANGCHAIN_API_KEY", "LANGCHAIN_PROJECT",
})

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def _either(options: tuple[str, ...]) -> str:
    quoted = [f"'{o}'" for o in options]
    return quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + " or " + quoted[-1]


def _is_http_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)



def _optional_number(r: _Reader, key: str) -> float | None:
    """A non-negative number when the key is set, else None (Spec 08 prices and cost cap)."""
    return None if r.raw(key) is None else r.number(key, 0.0, minimum=0.0, unit="USD")


class _Reader:
    """Typed access to the merged environment; collects problems and warnings."""

    def __init__(self, values: Mapping[str, str]) -> None:
        self.values = values
        self.problems: list[str] = []
        self.warnings: list[str] = []

    def raw(self, key: str) -> str | None:
        value = self.values.get(key)
        if value is None:
            return None
        value = value.strip()
        return value or None

    def text(self, key: str, default: str) -> str:
        return self.raw(key) or default

    def choice(self, key: str, options: tuple[str, ...], default: str) -> str:
        value = self.raw(key)
        if value is None:
            return default
        if value.lower() in options:
            return value.lower()
        self.problems.append(f"{key}={value!r} is not valid. Use {_either(options)}.")
        return default

    def integer(self, key: str, default: int, *, minimum: int, maximum: int | None = None) -> int:
        value = self.raw(key)
        if value is None:
            return default
        try:
            number: int | None = int(value)
        except ValueError:
            number = None
        if number is None or number < minimum or (maximum is not None and number > maximum):
            bounds = f"from {minimum} to {maximum}" if maximum is not None else f"of at least {minimum}"
            self.problems.append(f"{key}={value!r} must be a whole number {bounds}, e.g. {default}.")
            return default
        return number

    def number(
        self,
        key: str,
        default: float,
        *,
        minimum: float = 0.0,
        maximum: float | None = None,
        positive: bool = False,
        unit: str = "",
    ) -> float:
        value = self.raw(key)
        if value is None:
            return default
        try:
            number: float | None = float(value)
        except ValueError:
            number = None
        bad = (
            number is None
            or not math.isfinite(number)
            or number < minimum
            or (positive and number <= 0)
            or (maximum is not None and number > maximum)
        )
        if bad or number is None:
            what = f"a number of {unit}" if unit else "a number"
            if positive:
                bounds = " > 0"
            elif maximum is not None:
                bounds = f" from {minimum:g} to {maximum:g}"
            else:
                bounds = f" of at least {minimum:g}"
            self.problems.append(f"{key}={value!r} must be {what}{bounds}, e.g. {default:g}.")
            return default
        return number

    def boolean(self, key: str, default: bool) -> bool:
        value = self.raw(key)
        if value is None:
            return default
        if value.lower() in _TRUE:
            return True
        if value.lower() in _FALSE:
            return False
        self.problems.append(f"{key}={value!r} must be true or false.")
        return default

    def secret(self, key: str) -> SecretStr | None:
        value = self.raw(key)
        return SecretStr(value) if value else None

    def url(self, key: str, *, example: str) -> str | None:
        value = self.raw(key)
        if value is None:
            return None
        if not _is_http_url(value):
            self.problems.append(f"{key}={value!r} needs a scheme and host, e.g. {example}.")
            return None
        return value


def _path(raw: str | None, default: Path, home: Path) -> Path:
    if raw is None:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else home / path


def _normalise_pg(url: str) -> str:
    return "postgresql://" + url[len("postgres://"):] if url.startswith("postgres://") else url


def _services(r: _Reader) -> ServiceRegistry:
    host = r.text("CJI_SERVICE_HOST", DEFAULT_SERVICE_HOST)
    endpoints: list[ServiceEndpoint] = []
    for spec in DEFAULT_SERVICES:
        prefix = env_prefix(spec.name)
        port = r.integer(f"{prefix}_PORT", spec.port, minimum=1, maximum=65535)
        url = r.url(f"{prefix}_URL", example=f"http://127.0.0.1:{spec.port}{spec.path}")
        if spec.name == "collector":
            if r.raw(f"{prefix}_PORT") is None and r.raw("COLLECTOR_PORT") is not None:
                port = r.integer("COLLECTOR_PORT", spec.port, minimum=1, maximum=65535)
                r.warnings.append("COLLECTOR_PORT is deprecated; use CJI_COLLECTOR_PORT or CJI_COLLECTOR_URL.")
            legacy_host = r.raw("COLLECTOR_HOST")
            if url is None and legacy_host is not None:
                candidate = f"{legacy_host.rstrip('/')}:{port}"
                if _is_http_url(candidate):
                    url = candidate
                else:
                    r.problems.append(
                        f"COLLECTOR_HOST={legacy_host!r} needs a scheme and host, e.g. http://localhost."
                    )
                r.warnings.append(
                    "COLLECTOR_HOST is deprecated; set CJI_COLLECTOR_URL to the collector's URL, "
                    "e.g. https://collector.example.com."
                )
        endpoints.append(ServiceEndpoint(
            name=spec.name, kind=spec.kind, transport=spec.transport, host=host,
            port=port, path=spec.path, launch=spec.launch, url_override=url,
        ))
    owners: dict[int, str] = {}
    for endpoint in endpoints:
        other = owners.get(endpoint.port)
        if other is not None:
            r.problems.append(
                f"{env_prefix(endpoint.name)}_PORT={endpoint.port} is already used by {other}. "
                "Choose a free port."
            )
        else:
            owners[endpoint.port] = endpoint.name
    return ServiceRegistry(services=tuple(endpoints))


def _database(r: _Reader) -> DatabaseSettings:
    primary = r.raw("DATABASE_URL")
    fallback = r.raw("SUPABASE_DATABASE_URL")
    if primary and fallback and _normalise_pg(primary) != _normalise_pg(fallback):
        r.warnings.append(
            "DATABASE_URL and SUPABASE_DATABASE_URL are both set to different values; DATABASE_URL is used."
        )
    source = "DATABASE_URL" if primary else ("SUPABASE_DATABASE_URL" if fallback else None)
    raw = primary or fallback
    if raw is None or source is None:
        return DatabaseSettings()
    url = _normalise_pg(raw)
    if not url.lower().startswith("postgresql"):
        r.problems.append(
            f"{source} must be a PostgreSQL URL such as postgresql://USER:PASSWORD@HOST:5432/DB "
            "(value not shown). Percent-encode special characters in the password."
        )
        return DatabaseSettings()
    return DatabaseSettings(url=SecretStr(url), source=source)  # type: ignore[arg-type]


def _origins(r: _Reader, raw: str) -> tuple[str, ...]:
    origins: list[str] = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        if entry == "*":
            r.problems.append("CJI_CORS_ORIGINS must list origins explicitly; '*' is not allowed.")
            continue
        try:
            parts = urlsplit(entry)
            valid = (
                parts.scheme in ("http", "https")
                and bool(parts.hostname)
                and parts.path == ""
                and not parts.query
                and not parts.fragment
                and "@" not in parts.netloc
            )
        except ValueError:
            valid = False
        if not valid:
            r.problems.append(
                f"CJI_CORS_ORIGINS entry {entry!r} must be scheme://host[:port] with no path or "
                "trailing slash, e.g. https://app.example.com."
            )
            continue
        origins.append(entry)
    return tuple(origins)


def _merged_environment(
    environ: Mapping[str, str], dotenv_path: Path | None
) -> dict[str, str]:
    process = dict(environ)
    env = (process.get("CJI_ENV") or "").strip().lower()
    from_file: dict[str, str] = {}
    if dotenv_path is not None and dotenv_path.is_file():
        loaded = {k: v for k, v in dotenv_values(dotenv_path).items() if v is not None}
        if not env:
            env = (loaded.get("CJI_ENV") or "").strip().lower()
        if env != "test":
            from_file = loaded
    values = {**from_file, **process}
    if env and not (values.get("CJI_ENV") or "").strip():
        values["CJI_ENV"] = env
    return values


def load_settings(
    environ: Mapping[str, str] | None = None,
    dotenv_path: Path | _HomeDotenv | None = DEFAULT_DOTENV_PATH,
) -> Settings:
    """Build and validate Settings. Raises ConfigError listing every problem.

    CJI_HOME is read from `environ` only (not from `.env`, which lives in the home)."""
    process = os.environ if environ is None else environ
    home = resolve_home(process)
    dotenv = home / ".env" if isinstance(dotenv_path, _HomeDotenv) else dotenv_path
    values = _merged_environment(process, dotenv)
    r = _Reader(values)
    from_file = values.get("CJI_HOME")
    if from_file is not None and from_file != process.get("CJI_HOME"):
        r.warnings.append("CJI_HOME in .env is ignored; set it in the environment.")

    env = r.choice("CJI_ENV", ENVIRONMENTS, "production")
    app = AppSettings(
        env=env,  # type: ignore[arg-type]
        mode=r.choice("CJI_MODE", MODES, "demo"),  # type: ignore[arg-type]
        journey_name=r.text("JOURNEY_NAME", "user_onboarding"),
    )
    storage = StorageSettings(
        home=home,
        data_dir=_path(r.raw("CJI_DATA_DIR"), home / "data", home),
        reports_dir=_path(r.raw("CJI_REPORTS_DIR"), home / "reports", home),
    )
    # Gateway audit files (Spec 08, OD-62): <data_dir>/audit unless "off"; log only in tests.
    raw_audit = r.raw("CJI_AUDIT_DIR")
    if raw_audit is not None and raw_audit.strip().lower() == "off":
        audit_dir = None
    elif raw_audit is not None:
        audit_dir = _path(raw_audit, storage.data_dir / "audit", home)
    else:
        audit_dir = None if env == "test" else storage.data_dir / "audit"
    raw_checkpoints = r.raw("CJI_CHECKPOINTS_DB")
    checkpoints = _path(raw_checkpoints, storage.data_dir / "cji_checkpoints.db", home) if raw_checkpoints else None
    storage = storage.model_copy(update={"audit_dir": audit_dir, "checkpoints_path": checkpoints})
    services = _services(r)
    database = _database(r)

    retry = RetryPolicy(
        attempts=r.integer("CJI_LLM_RETRY_ATTEMPTS", 3, minimum=1, maximum=10),
        min_wait_s=r.number("CJI_LLM_RETRY_MIN_S", 2.0, unit="seconds"),
        max_wait_s=r.number("CJI_LLM_RETRY_MAX_S", 10.0, unit="seconds"),
    )
    if retry.max_wait_s < retry.min_wait_s:
        r.problems.append(
            f"CJI_LLM_RETRY_MAX_S={retry.max_wait_s:g} is below CJI_LLM_RETRY_MIN_S={retry.min_wait_s:g}. "
            "Make the maximum wait at least the minimum."
        )
    # One provider per process, never switched silently (Spec 08, OD-54).
    provider = r.choice("CJI_LLM_PROVIDER", LLM_PROVIDERS, "groq")
    model = r.text("LLM_MODEL", DEFAULT_LLM_MODELS[provider])
    mismatch = llm_model_mismatch(provider, model)
    if mismatch:
        r.problems.append(mismatch + " Set CJI_LLM_PROVIDER to the model's provider or choose a model it serves.")
    price_in = _optional_number(r, "CJI_LLM_PRICE_INPUT_PER_MTOK")
    price_out = _optional_number(r, "CJI_LLM_PRICE_OUTPUT_PER_MTOK")
    max_cost = _optional_number(r, "CJI_LLM_RUN_MAX_COST_USD")
    if max_cost is not None and (price_in is None or price_out is None):
        r.problems.append(
            "CJI_LLM_RUN_MAX_COST_USD needs CJI_LLM_PRICE_INPUT_PER_MTOK and CJI_LLM_PRICE_OUTPUT_PER_MTOK "
            "(USD per million tokens); CJI has no built-in prices."
        )
    llm = LLMSettings(
        provider=provider,
        model=model,
        temperature=r.number("LLM_TEMPERATURE", 0.0, maximum=2.0),
        max_tokens=r.integer("LLM_MAX_TOKENS", 2048, minimum=1),
        groq_api_key=r.secret("GROQ_API_KEY"),
        anthropic_api_key=r.secret("ANTHROPIC_API_KEY"),
        openai_api_key=r.secret("OPENAI_API_KEY"),
        timeout_s=r.number("CJI_LLM_TIMEOUT_S", 30.0, positive=True, unit="seconds"),
        retry=retry,
        deadline_s=r.number("CJI_LLM_DEADLINE_S", 90.0, positive=True, unit="seconds"),
        rate_per_min=r.integer("CJI_LLM_RATE_PER_MIN", 30, minimum=1),
        price_input_per_mtok=price_in,
        price_output_per_mtok=price_out,
        run_budget=RunBudgetSettings(
            max_calls=r.integer("CJI_LLM_RUN_MAX_CALLS", 20, minimum=0),
            max_tokens=r.integer("CJI_LLM_RUN_MAX_TOKENS", 50_000, minimum=0),
            max_cost_usd=max_cost,
        ),
    )
    mcp = MCPSettings(
        connect_timeout_s=r.number("CJI_MCP_CONNECT_TIMEOUT_S", 5.0, positive=True, unit="seconds"),
        read_timeout_s=r.number("CJI_MCP_READ_TIMEOUT_S", 300.0, positive=True, unit="seconds"),
        call_timeout_s=r.number("CJI_MCP_CALL_TIMEOUT_S", 150.0, positive=True, unit="seconds"),
    )
    if mcp.call_timeout_s < llm.deadline_s:
        r.warnings.append(
            f"CJI_MCP_CALL_TIMEOUT_S={mcp.call_timeout_s:g} is below CJI_LLM_DEADLINE_S={llm.deadline_s:g}: "
            "an insight or narrative tool call can time out before its LLM call finishes."
        )
    workflow = WorkflowSettings(
        step_timeout_s=r.number("CJI_WORKFLOW_STEP_TIMEOUT_S", 900.0, positive=True, unit="seconds"),
        step_attempts=r.integer("CJI_WORKFLOW_STEP_ATTEMPTS", 2, minimum=1, maximum=5),
        retry_backoff_s=r.number("CJI_WORKFLOW_RETRY_BACKOFF_S", 5.0, maximum=300.0, unit="seconds"),
    )
    if workflow.step_timeout_s <= mcp.call_timeout_s:
        r.problems.append(
            f"CJI_WORKFLOW_STEP_TIMEOUT_S={workflow.step_timeout_s:g} must be above CJI_MCP_CALL_TIMEOUT_S="
            f"{mcp.call_timeout_s:g}: one workflow step makes several tool calls."
        )
    budgets = BudgetSettings(
        max_agent_iterations=r.integer("MAX_AGENT_ITERATIONS", 20, minimum=1),
        pipeline_timeout_s=r.number("CJI_PIPELINE_TIMEOUT_S", 180.0, positive=True, unit="seconds"),
        ingestion_sample_rows=r.integer("INGESTION_SAMPLE_ROWS", 30, minimum=1),
        ingestion_confidence_threshold=r.number("INGESTION_CONFIDENCE_THRESHOLD", 0.80, maximum=1.0),
        friction_score_threshold=r.integer("FRICTION_SCORE_THRESHOLD", 60, minimum=0, maximum=100),
        realtime_window_minutes=r.integer("REALTIME_WINDOW_MINUTES", 60, minimum=1),
        realtime_auto_run_interval=r.integer("REALTIME_AUTO_RUN_INTERVAL", 0, minimum=0),
    )

    raw_cors = r.raw("CJI_CORS_ORIGINS")
    if raw_cors is not None:
        origins = _origins(r, raw_cors)
    elif env == "development":
        origins = tuple(
            f"http://{host}:{e.port}" for e in services.services if e.kind == "ui"
            for host in ("localhost", "127.0.0.1")
        )
    else:
        origins = ()

    keepalive = KeepAliveSettings(
        url=r.url("CJI_KEEPALIVE_URL", example="https://collector.example.com/health"),
        interval_s=r.number("CJI_KEEPALIVE_INTERVAL_S", 300.0, positive=True, unit="seconds"),
    )
    collector = CollectorSettings(
        max_body_bytes=r.integer("CJI_COLLECTOR_MAX_BODY_BYTES", 262_144, minimum=1024, maximum=10_485_760),
        rate_per_key=r.integer("CJI_COLLECTOR_RATE_PER_KEY", 120, minimum=1),
        rate_per_ip=r.integer("CJI_COLLECTOR_RATE_PER_IP", 300, minimum=1),
        admin_rate_per_ip=r.integer("CJI_COLLECTOR_ADMIN_RATE_PER_IP", 10, minimum=1),
        trusted_proxy_hops=r.integer("CJI_COLLECTOR_TRUSTED_PROXY_HOPS", 0, minimum=0, maximum=10),
    )
    observability = ObservabilitySettings(
        langchain_tracing=r.boolean("LANGCHAIN_TRACING_V2", False),
        langchain_api_key=r.secret("LANGCHAIN_API_KEY"),
        langchain_project=r.text("LANGCHAIN_PROJECT", "cji-poc"),
    )

    for key in sorted(k for k in values if k.startswith("CJI_") and k not in KNOWN_KEYS):
        match = difflib.get_close_matches(key, KNOWN_KEYS, n=1)
        message = f"{key} is not a known setting." + (f" Did you mean {match[0]}?" if match else "")
        (r.problems if env == "test" else r.warnings).append(message)

    if r.problems:
        raise ConfigError(r.problems, env=env)

    for warning in r.warnings:
        logger.warning(warning)
    return Settings(
        app=app,
        storage=storage,
        database=database,
        services=services,
        llm=llm,
        mcp=mcp,
        budgets=budgets,
        cors=CorsSettings(origins=origins),
        auth=AuthSettings(admin_key=r.secret("CJI_ADMIN_KEY")),
        keepalive=keepalive,
        collector=collector,
        workflow=workflow,
        observability=observability,
        warnings=tuple(r.warnings),
    )
