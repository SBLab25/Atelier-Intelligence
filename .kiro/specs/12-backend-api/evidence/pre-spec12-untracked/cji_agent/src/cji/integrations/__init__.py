"""
AI gateway (Spec 08): one typed path for LLM calls (`LLMGateway`) and MCP tool calls (`ToolGateway`).

Business code receives typed requests, results and errors; it never calls `requests`/`httpx` or a
provider SDK directly. See `.kiro/specs/08-ai-gateway/`.
"""
from .context import bind_run, correlation_from_config, current_run, new_correlation_id
from .errors import (
    BudgetExceeded,
    GatewayError,
    LLMDisabled,
    LLMTimeout,
    MalformedResponse,
    MalformedToolResult,
    ProviderRejected,
    ProviderUnavailable,
    RateLimited,
    ToolFailed,
    ToolTimeout,
)
from .llm import LLMGateway
from .tools import ToolGateway, tool_gateway
from .types import LLMCallInfo, LLMRequest, LLMResult, RunBudget, RunContext, Usage

__all__ = [
    "BudgetExceeded",
    "GatewayError",
    "LLMCallInfo",
    "LLMDisabled",
    "LLMGateway",
    "LLMRequest",
    "LLMResult",
    "LLMTimeout",
    "MalformedResponse",
    "MalformedToolResult",
    "ProviderRejected",
    "ProviderUnavailable",
    "RateLimited",
    "RunBudget",
    "RunContext",
    "ToolFailed",
    "ToolGateway",
    "ToolTimeout",
    "Usage",
    "bind_run",
    "correlation_from_config",
    "current_run",
    "new_correlation_id",
    "tool_gateway",
]
