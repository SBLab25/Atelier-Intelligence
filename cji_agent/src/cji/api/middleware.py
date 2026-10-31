"""
The /api/v1 gate (Spec 12, design §2): one pure-ASGI middleware that runs before routing.

1. request id (shared code, OD-120) in the context and in every response;
2. body limit (16 KiB, 413; the ingestion upload path uses CJI_API_MAX_UPLOAD_BYTES, Spec 14);
3. authentication for every non-public path (401 before any validation), the per-address limit for requests
   without a valid token and the per-token limit (429);
4. security headers on every response;
5. last-resort handler: anything that escapes the app becomes a 500 problem with only the request id;
6. (Spec 15) a request span (`traceparent` in and out), request metrics, a limit on failed authentications per
   address and security audit records for failed and rate-limited authentication.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, MutableMapping
from contextlib import ExitStack
from typing import TYPE_CHECKING, Any

from starlette.datastructures import Headers, MutableHeaders

from cji.collector.security import client_address, retry_after_header
from cji.http.request_id import (
    REQUEST_ID_HEADER,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)
from cji.integrations.audit import security_event
from cji.observability import metrics
from cji.observability.trace import (
    TRACEPARENT_HEADER,
    format_traceparent,
    http_span,
    parse_traceparent,
    span,
)

from .auth import TokenFileError, token_id_for
from .errors import PROBLEM_TYPE, problem_bytes

if TYPE_CHECKING:
    from .app import ApiContext

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

MAX_BODY_BYTES = 16 * 1024
API_PREFIX = "/api/v1"
UPLOAD_PATHS = frozenset({f"{API_PREFIX}/ingestions/validations"})
PUBLIC_PATHS = frozenset({f"{API_PREFIX}/health", f"{API_PREFIX}/health/ready", f"{API_PREFIX}/openapi.json",
                          f"{API_PREFIX}/docs"})
SERVICE = "cji-api"
SECURITY_HEADERS = ((b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"))

logger = logging.getLogger("cji.api")


class _BodyTooLarge(Exception):
    pass


class ApiGate:
    def __init__(self, app: ASGIApp, *, context: Callable[[], ApiContext]) -> None:
        self.app = app
        self.context = context

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        request_id = resolve_request_id(headers.get(REQUEST_ID_HEADER))
        token = set_request_id(request_id)
        started = False
        status = 500
        t0 = time.monotonic()
        parent = parse_traceparent(headers.get(TRACEPARENT_HEADER))
        stack = ExitStack()
        request_span = stack.enter_context(span(trace_id=parent[0] if parent else None,
                                                parent_id=parent[1] if parent else None))

        async def send_wrapped(message: Message) -> None:
            nonlocal started, status
            if message["type"] == "http.response.start":
                started = True
                status = int(message.get("status", 500))
                out = MutableHeaders(scope=message)
                out[REQUEST_ID_HEADER] = request_id
                out[TRACEPARENT_HEADER] = format_traceparent(request_span.trace_id, request_span.span_id)
                for name, value in SECURITY_HEADERS:
                    if name.decode() not in out:
                        out[name.decode()] = value.decode()
            await send(message)

        async def reply(status: int, code: str, extra: dict[str, str] | None = None) -> None:
            body = problem_bytes(status, code)
            raw = [(b"content-type", PROBLEM_TYPE.encode()), (b"content-length", str(len(body)).encode())]
            raw += [(k.lower().encode(), v.encode()) for k, v in (extra or {}).items()]
            await send_wrapped({"type": "http.response.start", "status": status, "headers": raw})
            await send({"type": "http.response.body", "body": body})

        try:
            ctx = self.context()
            path = scope.get("path", "")
            limit = ctx.settings.api.max_upload_bytes if path in UPLOAD_PATHS else MAX_BODY_BYTES
            declared = headers.get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > limit:
                await reply(413, "request_too_large")
                return
            if scope.get("method") != "OPTIONS" and path not in PUBLIC_PATHS:
                denied = self._authenticate(ctx, scope, headers)
                if denied is not None:
                    status, code, extra = denied
                    await reply(status, code, extra)
                    return
            elif scope.get("method") != "OPTIONS":
                # Public paths have their own per-address bucket, apart from failed authentication.
                wait = ctx.ip_limiter.check("public:" + self._client(ctx, scope, headers))
                if wait is not None:
                    metrics.RATE_LIMITED.inc(service=SERVICE, limiter="address")
                    await reply(429, "rate_limited", {"Retry-After": retry_after_header(wait)})
                    return

            received = 0

            async def bounded_receive() -> Message:
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > limit:
                        raise _BodyTooLarge
                return message

            await self.app(scope, bounded_receive, send_wrapped)
        except _BodyTooLarge:
            if not started:
                await reply(413, "request_too_large")
        except Exception as exc:  # noqa: BLE001  # broad-except: last-resort boundary; the client gets only the request id
            from cji.integrations.audit import configured_secrets, scrub

            logger.error("unhandled error request_id=%s type=%s message=%s", request_id, type(exc).__name__,
                         scrub(str(exc), configured_secrets())[:300])
            if not started:
                await reply(500, "internal_error")
        finally:
            route_obj = scope.get("route")
            route = getattr(route_obj, "path", None) or "unmatched"
            if route.startswith("/") and not route.startswith(API_PREFIX):
                route = API_PREFIX + route                # routers keep paths relative to /api/v1
            method = str(scope.get("method", "-"))
            metrics.HTTP_REQUESTS.inc(service=SERVICE, route=route, method=method, status=status)
            metrics.HTTP_SECONDS.observe(time.monotonic() - t0, service=SERVICE, route=route)
            http_span(request_span, method=method, route=route, status=status, request_id=request_id)
            stack.close()
            reset_request_id(token)

    @staticmethod
    def _client(ctx: ApiContext, scope: Scope, headers: Headers) -> str:
        peer = scope.get("client")
        return client_address(peer[0] if peer else None, headers.get("x-forwarded-for"),
                              ctx.settings.api.trusted_proxy_hops)

    def _authenticate(self, ctx: ApiContext, scope: Scope,
                      headers: Headers) -> tuple[int, str, dict[str, str]] | None:
        challenge = {"WWW-Authenticate": 'Bearer realm="cji-api"'}
        raw = headers.get("authorization") or ""
        scheme, _, value = raw.partition(" ")
        value = value.strip()
        principal = None
        code = "missing_token"
        if scheme.lower() == "bearer" and value:
            code = "invalid_token"
            try:
                principal = ctx.tokens.authenticate(value)
            except TokenFileError:
                logger.error("token file unusable: %s", ctx.tokens.path.name)
                return 503, "service_misconfigured", {}
        if principal is None:
            address = self._client(ctx, scope, headers)
            metrics.AUTH_FAILURES.inc(reason=code)
            if code == "invalid_token":
                actor = token_id_for(value)
                failed_wait = ctx.auth_failure_limiter.check(address)     # each failure spends one token
                if failed_wait is not None:
                    metrics.RATE_LIMITED.inc(service=SERVICE, limiter="auth_failures")
                    security_event("auth.rate_limited", actor=actor, outcome="denied")
                    return 429, "rate_limited", {"Retry-After": retry_after_header(failed_wait)}
                security_event("auth.failed", actor=actor, outcome="denied")
            wait = ctx.ip_limiter.check(address)
            if wait is not None:
                metrics.RATE_LIMITED.inc(service=SERVICE, limiter="address")
                return 429, "rate_limited", {"Retry-After": retry_after_header(wait)}
            if code == "invalid_token":
                logger.info("invalid token path=%s", scope.get("path", ""))
            return 401, code, {**challenge, "WWW-Authenticate": challenge["WWW-Authenticate"] +
                                ("" if code == "missing_token" else ', error="invalid_token"')}
        wait = ctx.token_limiter.check(principal.token_id)
        if wait is not None:
            logger.info("rate limited token=%s", principal.token_id)
            metrics.RATE_LIMITED.inc(service=SERVICE, limiter="token")
            security_event("auth.rate_limited", actor=principal.token_id, outcome="denied")
            return 429, "rate_limited", {"Retry-After": retry_after_header(wait)}
        scope.setdefault("state", {})["principal"] = principal
        return None
