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
    data_dir: Path
    reports_dir: Path

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
        return self.data_dir / "cji_checkpoints.db"

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


class LLMSettings(_Frozen):
    model: str = "claude-sonnet-4-6"
    temperature: float = 0.0
    max_tokens: int = 2048
    groq_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    timeout_s: float = 30.0
    retry: RetryPolicy = RetryPolicy()


class MCPSettings(_Frozen):
    # The mcp library's sse_client defaults, made explicit.
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 300.0


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


class KeepAliveSettings(_Frozen):
    url: str | None = None
    interval_s: float = 300.0


class ObservabilitySettings(_Frozen):
    langchain_tracing: bool = False
    langchain_api_key: SecretStr | None = None
    langchain_project: str = "cji-poc"


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
            "storage": {"data_dir": str(self.storage.data_dir), "reports_dir": str(self.storage.reports_dir)},
            "database": database,
            "services": {
                e.name: {"url": e.url, "transport": e.transport, "remote": e.is_remote}
                for e in self.services.services
            },
            "llm": {
                "model": self.llm.model,
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
            "observability": {
                "langchain_tracing": self.observability.langchain_tracing,
                "langchain_api_key": _redact(self.observability.langchain_api_key),
                "langchain_project": self.observability.langchain_project,
            },
        }
