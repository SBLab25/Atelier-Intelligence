"""
Gateway errors and their classification (Spec 08, OD-56 / OD-60).

Every message is built from a provider name, an HTTP status and a code. Response bodies and the text of
underlying exceptions never become part of a message, so a key echoed by a provider cannot leak.
`GatewayError` subclasses `RuntimeError` because callers of the old MCP client caught `RuntimeError`.
"""
from __future__ import annotations

from typing import Any

# Statuses worth another attempt: rate limit and transient server-side failures (529 = Anthropic overloaded).
RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504, 529})


class GatewayError(RuntimeError):
    code: str = "gateway_error"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        self.status = status
        self.retry_after = retry_after
        self.info: Any = None          # LLMCallInfo, attached by the gateway for audit and usage


class LLMTimeout(GatewayError):
    code = "timeout"
    retryable = True


class ProviderUnavailable(GatewayError):
    code = "provider_unavailable"
    retryable = True


class RateLimited(GatewayError):
    code = "rate_limited"
    retryable = True


class ProviderRejected(GatewayError):
    code = "bad_request"


class MalformedResponse(GatewayError):
    code = "malformed_response"


class BudgetExceeded(GatewayError):
    code = "budget_exceeded"


class LLMDisabled(GatewayError):
    code = "llm_disabled"


class ToolTimeout(GatewayError):
    code = "tool_timeout"
    retryable = True


class ToolFailed(GatewayError):
    code = "tool_failed"


class MalformedToolResult(GatewayError):
    code = "malformed_tool_result"


def parse_retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header (delta-seconds form only); None if absent or unusable."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _error_hint(body: Any) -> str:
    """Lower-cased provider error type/code, used only to choose a code (never shown)."""
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        parts = [error.get("code"), error.get("type")]
        return " ".join(str(p) for p in parts if isinstance(p, str)).lower()
    return ""


def classify_status(provider: str, status: int, body: Any = None, retry_after: str | None = None) -> GatewayError:
    """Map an HTTP error status to a gateway error."""
    if status == 429:
        return RateLimited(f"{provider} call failed: HTTP 429 (rate_limited)", status=status,
                           retry_after=parse_retry_after(retry_after))
    if status in RETRYABLE_STATUS:
        return ProviderUnavailable(f"{provider} call failed: HTTP {status} (provider_unavailable)", status=status,
                                   retry_after=parse_retry_after(retry_after))
    if status in (401, 403):
        code = "auth_failed"
    elif status == 404 or "model" in _error_hint(body):
        code = "model_not_found"
    else:
        code = "bad_request"
    return ProviderRejected(f"{provider} call failed: HTTP {status} ({code})", code=code, status=status)
