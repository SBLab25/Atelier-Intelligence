"""
Trace context (Spec 15, OD-161): W3C `traceparent` parsing, context variables and span records.

Spans are audit records. Workflow steps, tool calls and LLM calls already write one audit record each with latency
and outcome; they now also carry `trace_id`, `span_id` and `parent_id`. A run is one trace whose id is derived from
the run id (`trace_id_for_run`), so MCP servers, which receive the run id in `run_context`, join the same trace
without extra arguments. HTTP requests write `kind=span` records of their own (`http_span`).
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

TRACEPARENT_HEADER = "traceparent"
_TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}")
_trace_id: ContextVar[str | None] = ContextVar("cji_trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("cji_span_id", default=None)
_log = logging.getLogger("cji.observability")


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    """(trace_id, parent span id) of a valid version-00 header; None for anything else or all-zero ids."""
    match = _TRACEPARENT.fullmatch((value or "").strip().lower())
    if match is None or set(match.group(1)) == {"0"} or set(match.group(2)) == {"0"}:
        return None
    return match.group(1), match.group(2)


def format_traceparent(trace_id: str, span_id: str) -> str:
    return f"00-{trace_id}-{span_id}-01"


def trace_id_for_run(run_id: str | None) -> str | None:
    """The trace id of a run: its UUID as 32 hex digits (None when the id is not a UUID)."""
    try:
        return uuid.UUID(str(run_id)).hex if run_id else None
    except ValueError:
        return None


def current_trace_id() -> str | None:
    return _trace_id.get()


def current_span_id() -> str | None:
    return _span_id.get()


def current_traceparent() -> str | None:
    trace_id, span_id = _trace_id.get(), _span_id.get()
    return format_traceparent(trace_id, span_id) if trace_id and span_id else None


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: str | None
    started: float = field(default_factory=time.monotonic)

    def latency_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def ids(self) -> dict[str, Any]:
        return {"trace_id": self.trace_id, "span_id": self.span_id, "parent_id": self.parent_id}


@contextmanager
def span(*, trace_id: str | None = None, parent_id: str | None = None) -> Iterator[Span]:
    """Open a span as the current one. Trace: given, else the current one, else new; parent: given, else current."""
    current_trace, current_span = _trace_id.get(), _span_id.get()
    tid = trace_id or current_trace or new_trace_id()
    parent = parent_id if parent_id is not None else (current_span if tid == current_trace else None)
    opened = Span(trace_id=tid, span_id=new_span_id(), parent_id=parent)
    t1, t2 = _trace_id.set(tid), _span_id.set(opened.span_id)
    try:
        yield opened
    finally:
        _span_id.reset(t2)
        _trace_id.reset(t1)


_sinks: dict[str, Any] = {}
_sinks_lock = threading.Lock()


def _sink() -> Any:
    from cji.integrations.audit import default_sink

    from .context import service_name

    name = f"spans-{service_name()}"
    with _sinks_lock:
        if name not in _sinks:
            _sinks[name] = default_sink(name)
        return _sinks[name]


def http_span(opened: Span, *, method: str, route: str, status: int, request_id: str) -> None:
    """Write the `kind=span` record of one HTTP request. A failing sink never breaks the request."""
    from cji.integrations.audit import make_record

    from .context import service_name

    try:
        _sink().write(
            make_record(
                kind="span",
                service=service_name(),
                name=f"{method} {route}",
                http_status=status,
                latency_ms=opened.latency_ms(),
                request_id=request_id,
                outcome="ok" if status < 500 else "error",
                **opened.ids(),
            )
        )
    except Exception as exc:  # noqa: BLE001  # broad-except: observability must not fail a request
        _log.warning("span record dropped: %s", type(exc).__name__)
