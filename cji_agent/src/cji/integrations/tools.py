"""
ToolGateway (Spec 08, OD-66): the MCP client used by every workflow worker.

Per-call timeout, one retry when opening a session fails, no retries of tool calls (several have side
effects), strict JSON-object results, correlation ids from the bound RunContext, and an audit record
per call with argument key names only.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from .audit import AuditSink, default_sink, make_record, scrub
from .context import current_run, new_call_id
from .errors import GatewayError, MalformedToolResult, ToolFailed, ToolTimeout
from .types import Outcome

log = logging.getLogger("cji.integrations")

Opener = Callable[[str], contextlib.AbstractAsyncContextManager[Any]]


def resolve_mcp_url(server_name: str) -> str:
    """URL of an MCP service from the settings registry (ConfigError for unknown or non-MCP names)."""
    from cji.settings import ConfigError, get_settings

    services = get_settings().services
    endpoint = services.get(server_name)          # ConfigError for unknown names
    if endpoint.kind != "mcp":
        known = ", ".join(e.name for e in services.mcp_services())
        raise ConfigError([f"Service '{server_name}' is not an MCP service. MCP services: {known}."])
    return str(endpoint.url)


@contextlib.asynccontextmanager
async def sse_opener(server_name: str) -> AsyncIterator[Any]:
    """Open an initialised MCP ClientSession over SSE (endpoints and timeouts from settings)."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    from cji.settings import get_settings

    url = resolve_mcp_url(server_name)
    timeouts = get_settings().mcp
    async with contextlib.AsyncExitStack() as stack:
        streams = await stack.enter_async_context(
            sse_client(url, timeout=timeouts.connect_timeout_s, sse_read_timeout=timeouts.read_timeout_s))
        session = await stack.enter_async_context(ClientSession(*streams))
        await session.initialize()
        yield session


def parse_tool_result(tool: str, result: Any) -> dict[str, Any]:
    """A tool result as a JSON object; tool errors and other shapes raise instead of changing shape."""
    if result is None:
        return {}
    content = getattr(result, "content", None) or []
    if getattr(result, "is_error", False) or getattr(result, "isError", False):  # mcp 2.x / 1.x
        text = getattr(content[0], "text", "") if content else ""
        log.warning("MCP tool %s returned an error result: %s", tool, scrub(str(text))[:500])
        raise ToolFailed(f"MCP tool '{tool}' returned an error result (tool_error)", code="tool_error")
    if not content:
        return {}
    text = getattr(content[0], "text", None)
    if not isinstance(text, str):
        raise MalformedToolResult(f"MCP tool '{tool}' returned non-text content (malformed_tool_result)")
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        raise MalformedToolResult(f"MCP tool '{tool}' returned text that is not JSON (malformed_tool_result)") from None
    if not isinstance(value, dict):
        raise MalformedToolResult(f"MCP tool '{tool}' returned JSON that is not an object (malformed_tool_result)")
    return value


def single_error(group: BaseExceptionGroup[BaseException]) -> Exception | None:
    """The only leaf of a (nested) exception group when it is an ordinary Exception, else None."""
    leaves: list[BaseException] = []
    pending: list[BaseException] = [group]
    while pending:
        exc = pending.pop()
        if isinstance(exc, BaseExceptionGroup):
            pending.extend(exc.exceptions)
        else:
            leaves.append(exc)
    if len(leaves) == 1 and isinstance(leaves[0], Exception):
        return leaves[0]
    return None


class ToolGateway:
    def __init__(
        self,
        *,
        call_timeout_s: float = 150.0,
        connect_attempts: int = 2,
        audit: AuditSink | None = None,
        opener: Opener | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self.call_timeout_s = call_timeout_s
        self.connect_attempts = max(1, connect_attempts)
        self.audit = audit or default_sink("workflow")
        self._opener = opener or sse_opener
        self._secrets = secrets
        self._services: dict[int, str] = {}

    @contextlib.asynccontextmanager
    async def session(self, service: str) -> AsyncIterator[Any]:
        try:
            async with contextlib.AsyncExitStack() as stack:
                session = await self._open(stack, service)
                self._services[id(session)] = service
                try:
                    yield session
                finally:
                    self._services.pop(id(session), None)
        except BaseExceptionGroup as group:
            # The SSE client's anyio task group wraps whatever the session body raised. Callers get the
            # one real error (e.g. ToolFailed) instead of "unhandled errors in a TaskGroup".
            leaf = single_error(group)
            if leaf is None:
                raise
            raise leaf from leaf.__cause__

    async def _open(self, stack: contextlib.AsyncExitStack, service: str) -> Any:
        from cji.settings import ConfigError

        started = time.monotonic()
        ctx = current_run()
        for attempt in range(1, self.connect_attempts + 1):
            try:
                session = await stack.enter_async_context(self._opener(service))
            except ConfigError:
                raise
            except Exception as exc:  # broad-except: connection boundary (SSE/anyio groups): retried, then ToolFailed
                if attempt < self.connect_attempts:
                    log.warning("MCP service %s: connect attempt %d failed (%s); retrying",
                                service, attempt, type(exc).__name__)
                    continue
                self._write(kind="tool_session", service=service, ctx_id=ctx, outcome="error",
                            code="connect_failed", attempts=attempt, started=started)
                raise ToolFailed(f"could not connect to MCP service '{service}' (connect_failed)",
                                 code="connect_failed") from exc
            self._write(kind="tool_session", service=service, ctx_id=ctx, outcome="ok", code=None,
                        attempts=attempt, started=started)
            return session
        raise ToolFailed(f"could not connect to MCP service '{service}' (connect_failed)", code="connect_failed")

    async def call(self, session: Any, tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(arguments or {})
        service = self._services.get(id(session), "-")
        call_id = new_call_id()
        started = time.monotonic()
        outcome: Outcome = "error"
        code: str | None = None
        try:
            try:
                async with asyncio.timeout(self.call_timeout_s):
                    result = await session.call_tool(tool, arguments=args)
            except TimeoutError:
                raise ToolTimeout(f"MCP tool '{tool}' timed out after {self.call_timeout_s:g}s (tool_timeout)") from None
            data = parse_tool_result(tool, result)
            outcome = "ok"
            return data
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except GatewayError as exc:
            code = exc.code
            raise
        except Exception as exc:  # broad-except: MCP call boundary: classified as ToolFailed, cause chained
            code = "tool_failed"
            log.warning("MCP tool %s on %s failed: %s", tool, service,
                        scrub(f"{type(exc).__name__}: {exc}", self._secrets)[:500])
            raise ToolFailed(f"MCP tool '{tool}' failed: {type(exc).__name__} (tool_failed)") from exc
        finally:
            ctx = current_run()
            from cji.observability import metrics

            metrics.TOOL_CALLS.inc(service=service, tool=tool, outcome=outcome)
            self.audit.write(make_record(
                kind="tool", service=service, correlation_id=ctx.correlation_id if ctx else None,
                worker=ctx.worker if ctx else None, call_id=call_id, tool=tool, outcome=outcome, code=code,
                attempts=1, latency_ms=int((time.monotonic() - started) * 1000), arg_keys=sorted(args),
            ))

    def _write(self, *, kind: str, service: str, ctx_id: Any, outcome: Outcome, code: str | None,
               attempts: int, started: float) -> None:
        self.audit.write(make_record(
            kind=kind, service=service, correlation_id=ctx_id.correlation_id if ctx_id else None,
            worker=ctx_id.worker if ctx_id else None, call_id=new_call_id(), outcome=outcome, code=code,
            attempts=attempts, latency_ms=int((time.monotonic() - started) * 1000),
        ))


_gateway: ToolGateway | None = None


def tool_gateway() -> ToolGateway:
    """The process-wide ToolGateway, built from settings on first use."""
    global _gateway
    if _gateway is None:
        from cji.settings import get_settings

        _gateway = ToolGateway(call_timeout_s=get_settings().mcp.call_timeout_s)
    return _gateway


def reset_tool_gateway(gateway: ToolGateway | None = None) -> None:
    """Replace (tests) or drop the process-wide ToolGateway."""
    global _gateway
    _gateway = gateway
