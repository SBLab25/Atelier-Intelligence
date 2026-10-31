"""
Logging setup for CJI entry points (Spec 11, OD-105).

Importing a CJI module never configures logging; each command (cji, cji-servers, the MCP servers, the collector,
the dashboard) calls configure_logging() when it starts.
"""
from __future__ import annotations

import logging

DEFAULT_FORMAT = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
_QUIET = ("chromadb", "langchain", "langchain_core", "httpx", "httpcore", "uvicorn.access")


def configure_logging(level: int = logging.INFO, fmt: str = DEFAULT_FORMAT) -> None:
    """Add a root handler unless one exists and quieten noisy third-party loggers. Safe to call twice."""
    if not logging.root.handlers:
        logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%dT%H:%M:%S")
    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)
