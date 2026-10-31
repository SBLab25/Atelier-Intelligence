"""
Process and request context for log records (Spec 15, OD-159).

`ContextFilter` adds `service`, `request_id`, `run_id`, `trace_id` and `span_id` to every record that passes the
handler it is attached to, so formatters and log shippers can correlate lines without each message embedding ids.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_service = ""


def set_service(name: str) -> None:
    global _service
    _service = name


def service_name() -> str:
    """The configured service name, else the name of the running command (e.g. `cji-api`)."""
    if _service:
        return _service
    argv0 = Path(sys.argv[0]).stem if sys.argv and sys.argv[0] else "python"
    return argv0 or f"pid-{os.getpid()}"


def current_run_id() -> str | None:
    from cji.integrations.context import current_run

    run = current_run()
    return run.correlation_id if run is not None else None


class ContextFilter(logging.Filter):
    """Never drops a record; only adds context attributes (existing attributes win)."""

    def filter(self, record: logging.LogRecord) -> bool:
        from cji.http.request_id import current_request_id

        from .trace import current_span_id, current_trace_id

        fields = record.__dict__
        fields.setdefault("service", service_name())
        fields.setdefault("request_id", current_request_id())
        fields.setdefault("run_id", current_run_id() or "-")
        fields.setdefault("trace_id", current_trace_id() or "-")
        fields.setdefault("span_id", current_span_id() or "-")
        return True
