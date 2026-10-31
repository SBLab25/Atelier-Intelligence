"""
Deterministic test doubles for the gateways (Spec 08, OD-64). No network, no real sleeps, no randomness.
"""
from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx

from .policy import Timing


class UnscriptedRequest(AssertionError):
    """A test made a provider request nobody scripted."""


class BlockingTransport(httpx.AsyncBaseTransport):
    """Fails every request: installed for the whole test session so no test can reach a provider."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise UnscriptedRequest(f"unscripted provider request to {request.url.host}")


class ScriptedTransport(httpx.AsyncBaseTransport):
    """
    Replays a script, one item per request: an `httpx.Response`, an exception instance to raise, or a
    callable(request) -> Response (may be async). Records every request (url, headers, JSON body).
    """

    def __init__(self, *items: Any) -> None:
        self.items = list(items)
        self.requests: list[httpx.Request] = []

    def bodies(self) -> list[Any]:
        return [json.loads(r.content) for r in self.requests]

    def urls(self) -> list[str]:
        return [str(r.url) for r in self.requests]

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.items:
            raise UnscriptedRequest(f"script exhausted at request {len(self.requests)}")
        item = self.items.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item) and not isinstance(item, httpx.Response):
            item = item(request)
            if inspect.isawaitable(item):
                item = await item
        if not isinstance(item, httpx.Response):
            raise UnscriptedRequest(f"script item {len(self.requests)} is not an httpx.Response")
        return item


def groq_response(content: str, *, prompt_tokens: int = 10, completion_tokens: int = 5, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


def anthropic_response(text: str, *, input_tokens: int = 10, output_tokens: int = 5) -> httpx.Response:
    return httpx.Response(200, json={
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    })


def status_response(status: int, body: Any = None, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json=body if body is not None else {"error": {"type": "error"}}, headers=headers)


@dataclass
class ManualClock:
    """Monotonic clock that only moves when `sleep` is awaited (or `advance` is called)."""

    now_s: float = 1000.0
    sleeps: list[float] = field(default_factory=list)

    def now(self) -> float:
        return self.now_s

    def advance(self, seconds: float) -> None:
        self.now_s += seconds

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 6))
        self.now_s += seconds

    def timing(self) -> Timing:
        return Timing(now=self.now, sleep=self.sleep)


class MemoryAuditSink:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def write(self, record: dict[str, Any]) -> None:
        self.records.append(dict(record))

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("kind") == kind]


def tool_result(value: Any, *, is_error: bool = False) -> SimpleNamespace:
    """An object shaped like an mcp 2.x CallToolResult (`is_error`; mcp 1.x called it `isError`)."""
    text = value if isinstance(value, str) else json.dumps(value)
    return SimpleNamespace(is_error=is_error, content=[SimpleNamespace(type="text", text=text)])


class FakeToolSession:
    """
    Stand-in for an MCP ClientSession. `handlers` maps tool name -> callable(arguments) returning a dict
    (wrapped as a JSON tool result), a ready tool result, or raising. Records every call.
    """

    def __init__(self, handlers: dict[str, Callable[[dict[str, Any]], Any]]) -> None:
        self.handlers = handlers
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        args = dict(arguments or {})
        self.calls.append((name, args))
        if name not in self.handlers:
            raise UnscriptedRequest(f"no handler for tool {name!r}")
        value = self.handlers[name](args)
        if inspect.isawaitable(value):
            value = await value
        # Ready results (a SimpleNamespace or a real mcp CallToolResult) pass through; data is wrapped.
        return value if hasattr(value, "content") else tool_result(value)
