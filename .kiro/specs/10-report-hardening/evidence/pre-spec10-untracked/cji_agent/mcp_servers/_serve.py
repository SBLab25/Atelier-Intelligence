"""
Start an MCP server on the endpoint the service registry defines (Spec 04, CF-03).

Every server's entry point calls serve(mcp, "<logical name>") instead of choosing
its own port and transport.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from settings import ConfigError, get_settings, require


def serve(mcp: Any, name: str) -> None:
    """Validate configuration for `mcp:<name>`, then run `mcp` on its registry endpoint."""
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
    logging.getLogger("cji.mcp").info(
        "Starting %s on %s:%s (%s)", name, endpoint.host, endpoint.port, endpoint.transport
    )
    mcp.run(transport=endpoint.transport, host=endpoint.host, port=endpoint.port)
