"""
Logging setup for CJI entry points (Spec 11, OD-105; structured output Spec 15, OD-159).

Importing a CJI module never configures logging; each command (cji, cji-servers, the MCP servers, the collector,
the API, the dashboard) calls configure_logging() when it starts.

`CJI_LOG_FORMAT=json|text` (default: json when CJI_ENV=production, else text) and `CJI_LOG_LEVEL` are read from the
process environment, then from `<CJI_HOME>/.env`, because logging starts before settings load. JSON lines carry
`service`, `request_id`, `run_id`, `trace_id` and `span_id`; in production a failure's traceback text is replaced by
its exception type.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from cji.observability.context import ContextFilter, set_service

DEFAULT_FORMAT = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
_QUIET = ("chromadb", "langchain", "langchain_core", "httpx", "httpcore", "uvicorn.access")
_CONTEXT = ("request_id", "run_id", "trace_id")
LOG_FORMATS = ("json", "text")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def _setting(name: str) -> str:
    """Process environment first, then `<CJI_HOME>/.env` (never in CJI_ENV=test)."""
    value = (os.environ.get(name) or "").strip()
    if value or (os.environ.get("CJI_ENV") or "").strip().lower() == "test":
        return value
    try:
        from dotenv import dotenv_values

        # Same rule as settings.load.resolve_home, without importing settings (main.py applies CJI_MODE first).
        dotenv = Path((os.environ.get("CJI_HOME") or "").strip() or ".").resolve() / ".env"
        if dotenv.is_file():
            return (dotenv_values(dotenv).get(name) or "").strip()
    except (ImportError, OSError, ValueError):
        return ""
    return ""


def log_format() -> str:
    raw = _setting("CJI_LOG_FORMAT").lower()
    if raw in LOG_FORMATS:
        return raw
    return "json" if (_setting("CJI_ENV").lower() or "production") == "production" else "text"


def _production() -> bool:
    return (_setting("CJI_ENV").lower() or "production") == "production"


class TextFormatter(logging.Formatter):
    """The Spec 11 text format, followed by the context ids that are set and not already in the message."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        message = record.getMessage()
        extra = [f"{key}={value}" for key in _CONTEXT
                 if (value := getattr(record, key, "-")) not in ("-", None, "") and f"{key}=" not in message]
        return f"{line} [{' '.join(extra)}]" if extra else line


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Messages are data: nothing in them is interpreted."""

    def __init__(self, *, production: bool) -> None:
        super().__init__()
        self.production = production

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", "-"),
        }
        for key in (*_CONTEXT, "span_id"):
            value = getattr(record, key, "-")
            if value not in ("-", None, ""):
                entry[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            entry["exc_type"] = record.exc_info[0].__name__
            if not self.production:
                entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def make_handler(fmt: str = DEFAULT_FORMAT, *, kind: str | None = None) -> logging.Handler:
    handler = logging.StreamHandler()
    handler.addFilter(ContextFilter())
    if (kind or log_format()) == "json":
        handler.setFormatter(JsonFormatter(production=_production()))
    else:
        handler.setFormatter(TextFormatter(fmt, datefmt="%Y-%m-%dT%H:%M:%S"))
    return handler


def configure_logging(level: int = logging.INFO, fmt: str = DEFAULT_FORMAT, *, service: str | None = None) -> None:
    """Add a root handler unless one exists and quieten noisy third-party loggers. Safe to call twice."""
    if service:
        set_service(service)
    raw_level = _setting("CJI_LOG_LEVEL").upper()
    if raw_level in LOG_LEVELS:
        level = getattr(logging, raw_level)
    if not logging.root.handlers:
        logging.root.addHandler(make_handler(fmt))
        logging.root.setLevel(level)
    else:
        for handler in logging.root.handlers:
            if not any(isinstance(f, ContextFilter) for f in handler.filters):
                handler.addFilter(ContextFilter())
    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.captureWarnings(True)  # Python warnings become log records (one format for every line)
    _flush_pending_settings_warnings()


def _flush_pending_settings_warnings() -> None:
    """Emit settings warnings that were found before this handler existed (without importing settings)."""
    load = sys.modules.get("cji.settings.load")
    pending = getattr(load, "PENDING_WARNINGS", None)
    if pending:
        settings_log = logging.getLogger("cji.settings")
        for message in list(pending):
            settings_log.warning(message)
        pending.clear()


__all__ = [
    "DEFAULT_FORMAT",
    "LOG_FORMATS",
    "LOG_LEVELS",
    "JsonFormatter",
    "TextFormatter",
    "configure_logging",
    "log_format",
    "make_handler",
]
