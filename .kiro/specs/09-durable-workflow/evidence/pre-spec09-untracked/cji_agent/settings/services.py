"""
Service registry (Spec 04, CF-02).

The only place that defines default ports, paths and transports. Callers use
logical service names; endpoints are resolved from the loaded Settings.
Pure module: stdlib and pydantic only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from .errors import ConfigError

ServiceName = Literal[
    "cji-ingestion-intelligence",
    "cji-journey-data",
    "cji-friction-engine",
    "cji-insight",
    "cji-report",
    "collector",
    "dashboard",
    "frontend",
]
SERVICE_NAMES: tuple[str, ...] = get_args(ServiceName)
ServiceKind = Literal["mcp", "http", "ui"]
Transport = Literal["sse", "http"]

DEFAULT_SERVICE_HOST = "127.0.0.1"
LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class ServiceDefault:
    name: ServiceName
    kind: ServiceKind
    transport: Transport
    port: int
    path: str
    launch: str | None


# MCP services are listed in launch and preflight order (unchanged from Spec 03).
DEFAULT_SERVICES: tuple[ServiceDefault, ...] = (
    ServiceDefault("cji-ingestion-intelligence", "mcp", "sse", 8005, "/sse",
                   "mcp_servers.ingestion_intelligence_server"),
    ServiceDefault("cji-journey-data", "mcp", "sse", 8001, "/sse", "mcp_servers.journey_data_server"),
    ServiceDefault("cji-friction-engine", "mcp", "sse", 8002, "/sse", "mcp_servers.friction_engine_server"),
    ServiceDefault("cji-insight", "mcp", "sse", 8003, "/sse", "mcp_servers.insight_server"),
    ServiceDefault("cji-report", "mcp", "sse", 8004, "/sse", "mcp_servers.report_server"),
    ServiceDefault("collector", "http", "http", 8000, "", "collector.api:app"),
    ServiceDefault("dashboard", "ui", "http", 8501, "", "dashboard.py"),
    ServiceDefault("frontend", "ui", "http", 3000, "", None),
)


def env_prefix(name: str) -> str:
    """Environment-variable prefix for a service: 'cji-report' -> 'CJI_REPORT'."""
    return "CJI_" + name.removeprefix("cji-").upper().replace("-", "_")


class ServiceEndpoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: ServiceName
    kind: ServiceKind
    transport: Transport
    host: str
    port: int = Field(ge=1, le=65535)
    path: str = ""
    launch: str | None = None
    url_override: str | None = None

    @property
    def url(self) -> str:
        """URL clients use: the override if set, otherwise http://host:port/path."""
        if self.url_override:
            return self.url_override
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}{self.path}"

    @property
    def is_remote(self) -> bool:
        return self.url_override is not None


class ServiceRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[ServiceEndpoint, ...]

    def names(self) -> tuple[str, ...]:
        return tuple(endpoint.name for endpoint in self.services)

    def get(self, name: str) -> ServiceEndpoint:
        for endpoint in self.services:
            if endpoint.name == name:
                return endpoint
        raise ConfigError([f"Unknown service '{name}'. Known: {', '.join(sorted(self.names()))}."])

    def mcp_services(self) -> tuple[ServiceEndpoint, ...]:
        return tuple(endpoint for endpoint in self.services if endpoint.kind == "mcp")

    def with_endpoint(self, name: str, *, url: str | None = None, port: int | None = None) -> ServiceRegistry:
        """Copy with one endpoint replaced (test injection)."""
        current = self.get(name)
        update: dict[str, object] = {}
        if url is not None:
            update["url_override"] = url
        if port is not None:
            update["port"] = port
        replaced = current.model_copy(update=update)
        return ServiceRegistry(
            services=tuple(replaced if e.name == name else e for e in self.services)
        )
