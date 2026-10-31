"""
Collector request middleware (Spec 07): correlation ids (OD-47) and the body-size limit (OD-45).

Pure ASGI (no BaseHTTPMiddleware) so the request id context variable set here is visible to the
route, to the thread pool that runs synchronous code, and to every log record of the
`collector` logger through RequestIdFilter.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from starlette.datastructures import Headers, MutableHeaders

# Request ids are shared with the /api/v1 app since Spec 12 (OD-120); re-exported for existing imports.
from cji.http.request_id import (
    REQUEST_ID_HEADER,
    RequestIdFilter,
    current_request_id,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)

__all__ = ["REQUEST_ID_HEADER", "BodyTooLarge", "CollectorMiddleware", "RequestIdFilter", "current_request_id",
           "resolve_request_id"]

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

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
        token = set_request_id(request_id)
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
            reset_request_id(token)
