"""
Collector request middleware (Spec 07): correlation ids (OD-47) and the body-size limit (OD-45).

Pure ASGI (no BaseHTTPMiddleware) so the request id context variable set here is visible to the
route, to the thread pool that runs synchronous code, and to every log record of the
`collector` logger through RequestIdFilter.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from contextvars import ContextVar
from typing import Any

from starlette.datastructures import Headers, MutableHeaders

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
_request_id: ContextVar[str] = ContextVar("cji_request_id", default="-")


def resolve_request_id(raw: str | None) -> str:
    """Keep a well-formed client id (8-64 of A-Z a-z 0-9 . _ -); otherwise generate a UUID4."""
    if raw and _VALID_REQUEST_ID.fullmatch(raw):
        return raw
    return str(uuid.uuid4())


def current_request_id() -> str:
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    """Adds `request_id` to every record so formatters and log shippers can correlate lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__["request_id"] = _request_id.get()
        return True


class BodyTooLarge(Exception):
    """Raised from the wrapped `receive` when a streamed body passes the limit."""


def _rejection(status: int, request_id: str, detail: str) -> bytes:
    return json.dumps({"status": "rejected", "request_id": request_id, "detail": detail}).encode("utf-8")


class CollectorMiddleware:
    """Assigns the request id, echoes it in X-Request-ID, and enforces the body-size limit."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: Callable[[], int]) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = resolve_request_id(headers.get(REQUEST_ID_HEADER))
        token = _request_id.set(request_id)
        limit = self.max_body_bytes()
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        async def reject(status: int, detail: str) -> None:
            body = _rejection(status, request_id, detail)
            await send_with_id({
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})

        too_large = f"Request body is larger than {limit} bytes."
        try:
            declared = headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > limit:
                await reject(413, too_large)
                return

            received = 0

            async def bounded_receive() -> Message:
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > limit:
                        raise BodyTooLarge
                return message

            try:
                await self.app(scope, bounded_receive, send_with_id)
            except BodyTooLarge:
                if started:
                    raise
                await reject(413, too_large)
        finally:
            _request_id.reset(token)
