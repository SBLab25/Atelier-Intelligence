"""
The /api/v1 application (Spec 12). `create_app(settings)` builds it; `app` is the instance `uvicorn` and
`cji-api` serve (settings from the environment on first request).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import sqlite3
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from cji.collector.security import RateLimiter
from cji.http.request_id import REQUEST_ID_HEADER, RequestIdFilter
from cji.repositories import EventRepository, RepositoryError, event_repository
from cji.services.runs import RunService, WorkflowFactory
from cji.settings import ConfigError, Settings, get_settings
from cji.workflow.errors import LegacyRun, RunLeased, RunNotFound, RunNotResumable

from .auth import TokenFileError, TokenStore
from .errors import PROBLEM_TYPE, ApiError, problem_body
from .idempotency import IdempotencyStore
from .middleware import ApiGate
from .openapi import build_openapi
from .pagination import CursorCodec

API_VERSION = "1.0.0"
logger = logging.getLogger("cji.api")
logger.addFilter(RequestIdFilter())


@dataclass
class ApiContext:
    settings: Settings
    repository: EventRepository
    runs: RunService
    tokens: TokenStore
    idempotency: IdempotencyStore
    cursors: CursorCodec
    ip_limiter: RateLimiter
    token_limiter: RateLimiter
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)


def build_context(settings: Settings, workflow_factory: WorkflowFactory | None = None,
                  repository: EventRepository | None = None) -> ApiContext:
    from cji.settings.model import secret_value

    secret = secret_value(settings.api.cursor_secret)
    return ApiContext(
        settings=settings,
        repository=repository or event_repository(settings),
        runs=RunService(settings.storage.checkpoints_db, workflow_factory),
        tokens=TokenStore(settings.api.tokens_file),
        idempotency=IdempotencyStore(settings.storage.data_dir / "api_state.db"),
        cursors=CursorCodec(secret.encode("utf-8") if secret else secrets.token_bytes(32)),
        ip_limiter=RateLimiter(settings.api.rate_per_ip),
        token_limiter=RateLimiter(settings.api.rate_per_token),
    )


def _problem(status: int, code: str, detail: str | None = None, errors: list[dict[str, str]] | None = None,
             headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(problem_body(status, code, detail, errors), status_code=status, media_type=PROBLEM_TYPE,
                        headers=headers)


def _field_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    out = []
    for err in exc.errors()[:20]:
        loc = [str(part) for part in err.get("loc", ())]
        location = loc[0] if loc else "request"
        out.append({"location": location, "field": ".".join(loc[1:]) or location, "reason": str(err.get("type"))})
    return out


def _install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return _problem(exc.status, exc.code, exc.detail, exc.errors, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(422, "validation_failed", errors=_field_errors(exc))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 405:
            return _problem(405, "method_not_allowed")
        if exc.status_code == 404:
            return _problem(404, "not_found")
        return _problem(500, "internal_error")

    @app.exception_handler(RunNotFound)
    @app.exception_handler(LegacyRun)
    async def run_missing(_request: Request, _exc: Exception) -> JSONResponse:
        return _problem(404, "run_not_found")

    @app.exception_handler(RunLeased)
    async def run_busy(_request: Request, _exc: RunLeased) -> JSONResponse:
        return _problem(409, "run_busy", headers={"Retry-After": "5"})

    @app.exception_handler(RunNotResumable)
    async def not_awaiting(_request: Request, _exc: RunNotResumable) -> JSONResponse:
        return _problem(409, "run_not_awaiting_approval")

    @app.exception_handler(RepositoryError)
    @app.exception_handler(sqlite3.Error)
    async def storage(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("storage failure: %s", type(exc).__name__)
        return _problem(503, "storage_unavailable", headers={"Retry-After": "5"})

    @app.exception_handler(ConfigError)
    @app.exception_handler(TokenFileError)
    async def misconfigured(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("configuration problem: %s", type(exc).__name__)
        return _problem(503, "service_misconfigured")


def create_app(settings: Settings | None = None, *, workflow_factory: WorkflowFactory | None = None,
               repository: EventRepository | None = None) -> FastAPI:
    state: dict[str, ApiContext] = {}
    apps: list[FastAPI] = []

    def context() -> ApiContext:
        if "ctx" not in state:
            state["ctx"] = build_context(settings or get_settings(), workflow_factory, repository)
            for built in apps:
                built.state.ctx = state["ctx"]
        return state["ctx"]

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        ctx = context()
        try:
            ctx.tokens.entries()
        except TokenFileError:
            logger.error("token file %s is not valid; authenticated requests will fail", ctx.tokens.path.name)
        try:
            added = await ctx.runs.backfill()
            if added:
                logger.info("run index: %d runs added", added)
            ctx.idempotency.purge()
        except (sqlite3.Error, OSError) as exc:
            logger.warning("startup maintenance skipped: %s", type(exc).__name__)
        try:
            yield
        finally:
            for task in list(ctx.tasks):
                task.cancel()
            if ctx.tasks:
                await asyncio.gather(*ctx.tasks, return_exceptions=True)
            ctx.repository.close()

    dev = (settings or get_settings()).app.env == "development"
    app = FastAPI(
        title="CJI API", version=API_VERSION, lifespan=lifespan,
        description="Customer Journey Intelligence backend API, version 1 (Spec 12).",
        openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs" if dev else None, redoc_url=None,
    )
    apps.append(app)
    from .routes import router

    app.include_router(router)
    _install_handlers(app)
    app.openapi = lambda: build_openapi(app, API_VERSION)  # type: ignore[method-assign]
    app.add_middleware(ApiGate, context=context)
    origins = list((settings or get_settings()).api.cors_origins)
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER, "Retry-After", "Idempotent-Replayed"], max_age=600,
    )
    return app


def _lazy_app() -> Callable[..., Any]:
    """`cji.api.app:app` for uvicorn: built on first use from the environment's settings."""
    built: dict[str, FastAPI] = {}

    async def asgi(scope: Any, receive: Any, send: Any) -> None:
        if "app" not in built:
            built["app"] = create_app()
        await built["app"](scope, receive, send)

    return asgi


app = _lazy_app()
