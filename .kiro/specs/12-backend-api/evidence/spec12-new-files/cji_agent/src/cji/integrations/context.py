"""Correlation context for the client side (workers -> ToolGateway) (Spec 08, OD-61)."""
from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from .types import CORRELATION_PATTERN, RunContext

_current: ContextVar[RunContext | None] = ContextVar("cji_run_context", default=None)
_VALID = re.compile(CORRELATION_PATTERN)


def new_call_id() -> str:
    return uuid.uuid4().hex[:16]


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def current_run() -> RunContext | None:
    return _current.get()


@contextmanager
def bind_run(ctx: RunContext) -> Iterator[RunContext]:
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


def correlation_from_config(config: Mapping[str, Any] | None) -> str:
    """The LangGraph thread_id when it is a valid id, otherwise a fresh UUID4."""
    configurable = (config or {}).get("configurable") or {}
    thread_id = configurable.get("thread_id") if isinstance(configurable, Mapping) else None
    if isinstance(thread_id, str) and _VALID.fullmatch(thread_id):
        return thread_id
    return new_correlation_id()


def with_run(worker: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """
    Bind a RunContext (correlation id = LangGraph thread_id) around a graph node.

    The wrapper's own signature is `(state, config=None)` so LangGraph passes the run config; it is
    deliberately not functools.wraps (that would expose the inner signature without `config`).
    """
    def decorate(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def node(state: Any, config: Mapping[str, Any] | None = None) -> Any:
            ctx = RunContext(correlation_id=correlation_from_config(config), worker=worker)
            with bind_run(ctx):
                return await fn(state)

        node.__name__ = fn.__name__
        node.__qualname__ = fn.__qualname__
        node.__doc__ = fn.__doc__
        node.__module__ = fn.__module__
        return node

    return decorate


def run_or_new(worker: str) -> RunContext:
    """The bound RunContext, or a fresh one when a worker is called outside `with_run`."""
    return current_run() or RunContext(correlation_id=new_correlation_id(), worker=worker)
