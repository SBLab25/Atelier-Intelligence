"""
Start an MCP server on the endpoint the service registry defines (Spec 04, CF-03).

Every server's entry point calls serve(mcp, "<logical name>") instead of choosing
its own port and transport.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from cji.logs import configure_logging
from cji.settings import ConfigError, get_settings, require


def add_health_routes(mcp: Any, name: str) -> None:
    """`GET /health` (liveness; journey-data also checks its repository) and `GET /metrics` (Spec 15).

    The servers bind loopback addresses and are never routed through the proxy, so the routes have no auth.
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse, Response

    from cji.observability import metrics

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> Response:
        if name == "cji-journey-data":
            from cji.repositories import RepositoryError, event_repository

            repo = event_repository(get_settings())
            try:
                repo.health()
            except RepositoryError as exc:
                logging.getLogger("cji.mcp").warning("health: repository unavailable (%s)", type(exc).__name__)
                return JSONResponse({"status": "not_ready"}, status_code=503)
            finally:
                repo.close()
        return JSONResponse({"status": "ok", "service": name})

    @mcp.custom_route("/metrics", methods=["GET"])
    async def metrics_text(_request: Request) -> Response:
        return PlainTextResponse(metrics.REGISTRY.render(), media_type=metrics.CONTENT_TYPE)


def serve(mcp: Any, name: str) -> None:
    """Validate configuration for `mcp:<name>`, then run `mcp` on its registry endpoint."""
    configure_logging(service=name)
    role = f"mcp:{name}"
    try:
        settings = require(get_settings(), role)
        actual = getattr(mcp, "name", name)
        if actual != name:
            raise ConfigError(
                [f"The server object is named {actual!r} but was started as {name!r}."], role=role
            )
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2) from None
    endpoint = settings.services.get(name)
    settings.ensure_storage()
    if endpoint.transport in ("sse", "http", "streamable-http") and hasattr(mcp, "custom_route"):
        add_health_routes(mcp, name)
    if hasattr(mcp, "add_middleware"):
        mcp.add_middleware(run_context_middleware())
    _route_library_logs()
    logging.getLogger("cji.mcp").info(
        "Starting %s on %s:%s (%s)", name, endpoint.host, endpoint.port, endpoint.transport
    )
    if endpoint.transport in ("sse", "http", "streamable-http"):
        # No banner, and uvicorn logs through the CJI handler (one JSON object per line in production).
        mcp.run(transport=endpoint.transport, host=endpoint.host, port=endpoint.port, show_banner=False,
                uvicorn_config={"log_config": None})
    else:
        mcp.run(transport=endpoint.transport, show_banner=False)


def _route_library_logs() -> None:
    """FastMCP installs its own (rich) handlers on import; send its records to the root handler instead."""
    for logger_name in ("fastmcp", "mcp"):
        library = logging.getLogger(logger_name)
        library.handlers.clear()
        library.propagate = True


def run_context_middleware() -> Any:
    """Bind the workflow's `run_context` argument for the duration of a tool call (Spec 15, OD-159): log lines and
    audit records written by the tool carry the run id, and one line records each call."""
    from fastmcp.server.middleware import Middleware

    from cji.integrations import RunContext, new_correlation_id
    from cji.integrations.context import bind_run

    log = logging.getLogger("cji.mcp")

    class RunContextMiddleware(Middleware):  # type: ignore[misc]
        async def on_call_tool(self, context: Any, call_next: Any) -> Any:
            tool = getattr(context.message, "name", "?")
            arguments = getattr(context.message, "arguments", None) or {}
            raw = arguments.get("run_context") if isinstance(arguments, dict) else None
            if not isinstance(raw, dict):
                log.info("tool %s called", tool)
                return await call_next(context)
            with bind_run(RunContext.from_arg(raw, new_correlation_id())):
                log.info("tool %s called", tool)
                return await call_next(context)

    return RunContextMiddleware()
