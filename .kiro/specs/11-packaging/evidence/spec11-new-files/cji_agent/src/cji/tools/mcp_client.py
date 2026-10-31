"""
MCP client helpers. Since Spec 08 these are thin wrappers over `integrations.ToolGateway`
(per-call timeout, connect retry, strict JSON results, correlation ids, audit). Endpoints, transport
and timeouts come from the settings service registry (Spec 04); callers pass logical service names only.
"""
import contextlib
import logging

from cji.integrations.tools import resolve_mcp_url, tool_gateway
from cji.settings import get_settings

logger = logging.getLogger(__name__)


def server_url(server_name: str) -> str:
    """URL of an MCP service, resolved from the active settings at call time."""
    return resolve_mcp_url(server_name)


def mcp_service_names() -> tuple[str, ...]:
    return tuple(e.name for e in get_settings().services.mcp_services())


# Read-only compatibility view, resolved at import. New code calls server_url().
SERVER_URLS = {e.name: e.url for e in get_settings().services.mcp_services()}


@contextlib.asynccontextmanager
async def mcp_session(server_name: str):
    """Connect to an MCP server via SSE and yield an initialised ClientSession (through the ToolGateway)."""
    async with tool_gateway().session(server_name) as session:
        yield session


async def call_tool(session, tool_name: str, arguments: dict | None = None) -> dict:
    """
    Execute an MCP tool and return its JSON object result. Raises a GatewayError (a RuntimeError):
    ToolTimeout, ToolFailed (including tool error results) or MalformedToolResult (non-JSON output).
    """
    return await tool_gateway().call(session, tool_name, arguments)


async def ping_all_servers():
    """Validates all MCP endpoints connect successfully before running graph."""
    for name in mcp_service_names():
        try:
            async with mcp_session(name):
                logger.info(f"Ping successful: {name}")
        except Exception as e:  # broad-except: connection boundary: re-raised as RuntimeError with the cause
            logger.error(f"Failed to connect to {name}: {type(e).__name__}")
            raise RuntimeError(f"Startup check failed for {name}. Make sure servers are running.") from e
