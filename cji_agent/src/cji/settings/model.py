"""
Typed settings model (Spec 04, CF-01). Frozen pydantic models; pure module.

Built by settings.load.load_settings(); never reads the environment itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, SecretStr

from .services import ServiceRegistry

Environment = Literal["development", "test", "production"]
Mode = Literal["demo", "realtime"]
ENVIRONMENTS: tuple[str, ...] = ("development", "test", "production")
MODES: tuple[str, ...] = ("demo", "realtime")

MIN_ADMIN_KEY_LENGTH = 32
# Admin key values that must never authenticate (shipped defaults).
KNOWN_DEFAULT_ADMIN_KEYS: frozenset[str] = frozenset({"", "change-me", "change-me-in-production"})
# Seeded into api_keys in development only (Spec 02).
DEV_TRACKER_KEY = "cji_dev_localtest"


def secret_value(secret: SecretStr | None) -> str:
    """The secret's value, or '' when unset."""
    return secret.get_secret_value() if secret is not None else ""


def _redact(secret: SecretStr | None) -> str:
    return "unset" if secret is None else f"set ({len(secret.get_secret_value())} chars)"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AppSettings(_Frozen):
    env: Environment = "production"
    mode: Mode = "demo"
    journey_name: str = "user_onboarding"


class StorageSettings(_Frozen):
    home: Path                       # CJI_HOME (default: working directory); relative paths resolve here (Spec 11)
    data_dir: Path
    reports_dir: Path
    audit_dir: Path | None = None    # gateway audit JSONL files; None = log only (Spec 08)
    checkpoints_path: Path | None = None   # CJI_CHECKPOINTS_DB; None = <data_dir>/cji_checkpoints.db (Spec 09)

    @property
    def events_parquet(self) -> Path:
        return self.data_dir / "events.parquet"

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "cji.duckdb"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def checkpoints_db(self) -> Path:
        return self.checkpoints_path or self.data_dir / "cji_checkpoints.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "ingestion_uploads"

    @property
    def mapping_registry(self) -> Path:
        return self.data_dir / "mapping_registry.json"

    @property
    def last_run_file(self) -> Path:
        return self.data_dir / "last_run.json"

    def ensure(self) -> None:
        """Create the writable directories (called at startup, never on import)."""
        for directory in (self.data_dir, self.reports_dir, self.uploads_dir):
            directory.mkdir(parents=True, exist_ok=True)


class DatabaseSettings(_Frozen):
    url: SecretStr | None = None
    source: Literal["DATABASE_URL", "SUPABASE_DATABASE_URL"] | None = None

    @property
    def configured(self) -> bool:
        return self.url is not None

    def url_value(self) -> str | None:
        return self.url.get_secret_value() if self.url is not None else None


class RetryPolicy(_Frozen):
    attempts: int = 3
    min_wait_s: float = 2.0
    max_wait_s: float = 10.0


# LLM providers the gateway supports (Spec 08, OD-54). One per process; never switched silently.
LLM_PROVIDERS: tuple[str, ...] = ("groq", "anthropic", "none")
DEFAULT_LLM_MODELS: dict[str, str] = {
    "groq": "openai/gpt-oss-120b",        # what insight/report sent with default settings before Spec 08
    "anthropic": "claude-sonnet-4-6",     # the settings default before Spec 08
    "none": "none",
}


def llm_model_mismatch(provider: str, model: str) -> str | None:
    """A message when LLM_MODEL obviously belongs to another provider, else None."""
    m = model.strip().lower()
    if provider == "groq" and m.startswith(("claude", "anthropic/")):
        return f"LLM_MODEL={model!r} is an Anthropic model but CJI_LLM_PROVIDER=groq."
    if provider == "anthropic" and not m.removeprefix("anthropic/").startswith("claude"):
        return f"LLM_MODEL={model!r} is not an Anthropic model but CJI_LLM_PROVIDER=anthropic."
    return None


class RunBudgetSettings(_Frozen):
    """Per-run LLM limits (Spec 08, OD-59). Cost is enforced only when prices are configured."""

    max_calls: int = 20
    max_tokens: int = 50_000
    max_cost_usd: float | None = None


class LLMSettings(_Frozen):
    provider: str = "groq"
    model: str = DEFAULT_LLM_MODELS["groq"]
    temperature: float = 0.0
    max_tokens: int = 2048
    groq_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None   # read but unused (F-28)
    timeout_s: float = 30.0
    deadline_s: float = 90.0
    retry: RetryPolicy = RetryPolicy()
    rate_per_min: int = 30
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    run_budget: RunBudgetSettings = RunBudgetSettings()


class MCPSettings(_Frozen):
    # The mcp library's sse_client defaults, made explicit.
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 300.0
    call_timeout_s: float = 150.0   # one tool call (Spec 08, OD-66)


class BudgetSettings(_Frozen):
    max_agent_iterations: int = 20
    pipeline_timeout_s: float = 180.0
    ingestion_sample_rows: int = 30
    ingestion_confidence_threshold: float = 0.80
    friction_score_threshold: int = 60
    realtime_window_minutes: int = 60
    realtime_auto_run_interval: int = 0

    @property
    def recursion_limit(self) -> int:
        """LangGraph hard limit; must exceed the supervisor's iteration cap."""
        return self.max_agent_iterations * 3


class WorkflowSettings(_Frozen):
    """Per-step limits of the LangGraph workflow (Spec 09, OD-76)."""

    step_timeout_s: float = 900.0
    step_attempts: int = 2
    retry_backoff_s: float = 5.0

    @property
    def lease_s(self) -> float:
        """How long a run stays leased to one process without renewal (renewed after every step)."""
        return self.step_timeout_s * self.step_attempts + 60.0


class CorsSettings(_Frozen):
    origins: tuple[str, ...] = ()


class AuthSettings(_Frozen):
    admin_key: SecretStr | None = None
    dev_tracker_key: str = DEV_TRACKER_KEY


class CollectorSettings(_Frozen):
    """Collector request limits (Spec 07, OD-45 / OD-46). Rate limits are per process."""

    max_body_bytes: int = 262_144
    rate_per_key: int = 120             # requests per minute per tracker key
    rate_per_ip: int = 300              # requests per minute per client address
    admin_rate_per_ip: int = 10         # admin requests per minute per client address
    trusted_proxy_hops: int = 0         # 0: ignore X-Forwarded-For


class ApiSettings(_Frozen):
    """The /api/v1 service (Spec 12). Rate limits are per process."""

    tokens_file: Path
    rate_per_token: int = 120           # requests per minute per API token
    rate_per_ip: int = 60               # requests per minute per address without a valid token
    cors_origins: tuple[str, ...] = ()
    cursor_secret: SecretStr | None = None   # HMAC key for page cursors; None = random per process
    max_active_runs: int = 1            # runs started or resumed by one API process at once (Spec 14)
    max_upload_bytes: int = 10_485_760  # ingestion validation upload limit (Spec 14)
    write_operations: bool = True       # false: start/resume/ingestion operations are not mounted (Spec 14)
    trusted_proxy_hops: int = 0         # X-Forwarded-For hops to trust for client addresses (Spec 15)
    auth_failures_per_min: int = 10     # failed authentications per minute per address (Spec 15)


class KeepAliveSettings(_Frozen):
    url: str | None = None
    interval_s: float = 300.0


class ObservabilitySettings(_Frozen):
    langchain_tracing: bool = False
    langchain_api_key: SecretStr | None = None
    langchain_project: str = "cji-poc"
    log_format: str = "text"            # json | text (Spec 15; logs.py reads the same variable before settings load)
    log_level: str = "INFO"
    audit_retention_days: int = 90      # cji-ops maintenance deletes older audit lines (Spec 15)
    allow_third_party_tracing: bool = False   # required in production for LANGCHAIN_TRACING_V2 (Spec 15)
    pg_bin: str | None = None           # directory of pg_dump/pg_restore for cji-backup (Spec 15)


class Settings(_Frozen):
    app: AppSettings
    storage: StorageSettings
    database: DatabaseSettings
    services: ServiceRegistry
    llm: LLMSettings
    mcp: MCPSettings
    budgets: BudgetSettings
    cors: CorsSettings
    auth: AuthSettings
    keepalive: KeepAliveSettings
    collector: CollectorSettings = CollectorSettings()
    workflow: WorkflowSettings = WorkflowSettings()
    api: ApiSettings
    observability: ObservabilitySettings
    warnings: tuple[str, ...] = ()

    def ensure_storage(self) -> None:
        self.storage.ensure()

    def with_endpoint(self, name: str, *, url: str | None = None, port: int | None = None) -> Settings:
        """Copy with one service endpoint replaced (test injection)."""
        return self.model_copy(update={"services": self.services.with_endpoint(name, url=url, port=port)})

    def describe(self) -> dict[str, Any]:
        """Resolved configuration with every secret redacted."""
        database = (
            f"set (from {self.database.source})" if self.database.configured else "unset"
        )
        return {
            "app": self.app.model_dump(),
            "storage": {
                "home": str(self.storage.home),
                "data_dir": str(self.storage.data_dir),
                "reports_dir": str(self.storage.reports_dir),
                "audit_dir": str(self.storage.audit_dir) if self.storage.audit_dir else "off",
                "checkpoints_db": str(self.storage.checkpoints_db),
            },
            "database": database,
            "services": {
                e.name: {"url": e.url, "transport": e.transport, "remote": e.is_remote}
                for e in self.services.services
            },
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
                "deadline_s": self.llm.deadline_s,
                "rate_per_min": self.llm.rate_per_min,
                "price_input_per_mtok": self.llm.price_input_per_mtok,
                "price_output_per_mtok": self.llm.price_output_per_mtok,
                "run_budget": self.llm.run_budget.model_dump(),
                "temperature": self.llm.temperature,
                "max_tokens": self.llm.max_tokens,
                "timeout_s": self.llm.timeout_s,
                "retry": self.llm.retry.model_dump(),
                "groq_api_key": _redact(self.llm.groq_api_key),
                "anthropic_api_key": _redact(self.llm.anthropic_api_key),
                "openai_api_key": _redact(self.llm.openai_api_key),
            },
            "mcp": self.mcp.model_dump(),
            "budgets": {**self.budgets.model_dump(), "recursion_limit": self.budgets.recursion_limit},
            "cors": list(self.cors.origins),
            "auth": {"admin_key": _redact(self.auth.admin_key)},
            "keepalive": {"url": self.keepalive.url or "disabled", "interval_s": self.keepalive.interval_s},
            "collector": self.collector.model_dump(),
            "api": {
                "tokens_file": str(self.api.tokens_file),
                "rate_per_token": self.api.rate_per_token,
                "rate_per_ip": self.api.rate_per_ip,
                "cors_origins": list(self.api.cors_origins),
                "cursor_secret": _redact(self.api.cursor_secret),
            },
            "workflow": {**self.workflow.model_dump(), "lease_s": self.workflow.lease_s},
            "observability": {
                "langchain_tracing": self.observability.langchain_tracing,
                "langchain_api_key": _redact(self.observability.langchain_api_key),
                "langchain_project": self.observability.langchain_project,
            },
        }
