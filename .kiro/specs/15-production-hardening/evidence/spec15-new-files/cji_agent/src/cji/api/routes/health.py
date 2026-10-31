"""GET /health and /health/ready (public), /health/details, /metrics (admin, Spec 15) and /me."""
from __future__ import annotations

import logging
import sqlite3
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from cji.observability import metrics
from cji.repositories import RepositoryError

from ..auth import TokenFileError
from ..errors import problem_responses
from ..schemas import Component, Health, HealthDetails, Me, Readiness
from ._deps import Caller, Ctx, errors, only_query, require_role

router = APIRouter(tags=["health"])
logger = logging.getLogger("cji.api")


def _version() -> str:
    from ..app import API_VERSION

    return API_VERSION


@router.get("/health", response_model=Health, summary="Liveness (public)", operation_id="getHealth",
            responses=problem_responses(429, 500), dependencies=[only_query()])
def health(ctx: Ctx) -> Health:
    return Health(status="ok", version=_version(), mode=ctx.settings.app.mode)


@router.get("/health/ready", response_model=Readiness, summary="Readiness (public; no details)",
            operation_id="getReadiness", dependencies=[only_query()],
            responses={**problem_responses(429, 500), 503: {"model": Readiness, "description": "Not ready"}})
def readiness(ctx: Ctx) -> JSONResponse:
    """Ready when the repository, the checkpoint store, the token file and (realtime) the schema are usable.
    The answer never says which part failed; `/health/details` (token) and the logs do."""
    checks = [_repository(ctx), _checkpoints(ctx), _reports(ctx), _token_file(ctx), _schema(ctx)]
    ready = all(c.status == "ok" for c in checks)
    return JSONResponse({"status": "ready" if ready else "not_ready"}, status_code=200 if ready else 503)


@router.get("/metrics", summary="Process metrics, Prometheus text format (admin)", operation_id="getMetrics",
            response_class=PlainTextResponse, dependencies=[only_query()],
            responses={200: {"content": {"text/plain": {"schema": {"type": "string"}}},
                             "description": "Prometheus text exposition format 0.0.4"}, **errors(403)})
def metrics_text(ctx: Ctx, caller: Caller) -> PlainTextResponse:
    require_role(caller, "admin")
    metrics.RUNS_ACTIVE.set(len(ctx.active_runs))
    return PlainTextResponse(metrics.REGISTRY.render(), media_type=metrics.CONTENT_TYPE)


@router.get("/health/details", response_model=HealthDetails, summary="Component status",
            operation_id="getHealthDetails", responses=errors(), dependencies=[only_query()])
def health_details(ctx: Ctx, _caller: Caller) -> HealthDetails:
    components = [_repository(ctx), _checkpoints(ctx), _reports(ctx), _token_file(ctx), _schema(ctx)]
    status: Literal["ok", "degraded"] = "ok" if all(c.status == "ok" for c in components) else "degraded"
    return HealthDetails(status=status, version=_version(), mode=ctx.settings.app.mode, components=components,
                         active_runs=len(ctx.active_runs))


def _repository(ctx: Ctx) -> Component:
    try:
        ctx.repository.health()
    except RepositoryError as exc:
        logger.warning("health: repository unavailable (%s)", type(exc).__name__)
        return Component(name="repository", status="unavailable", code="storage_unavailable")
    return Component(name="repository", status="ok", code=None)


def _checkpoints(ctx: Ctx) -> Component:
    try:
        ctx.runs.page(journeys=None, journey_id=None, status=None, limit=1, after=None)
    except (sqlite3.Error, OSError) as exc:
        logger.warning("health: checkpoint store unavailable (%s)", type(exc).__name__)
        return Component(name="checkpoints", status="unavailable", code="storage_unavailable")
    return Component(name="checkpoints", status="ok", code=None)


def _reports(ctx: Ctx) -> Component:
    directory = ctx.settings.storage.reports_dir
    if directory.exists() and not directory.is_dir():
        return Component(name="reports", status="unavailable", code="storage_unavailable")
    return Component(name="reports", status="ok", code=None)       # not created yet = no reports


def _token_file(ctx: Ctx) -> Component:
    try:
        ctx.tokens.entries()
    except TokenFileError:
        logger.warning("health: token file unusable")
        return Component(name="tokens", status="unavailable", code="service_misconfigured")
    return Component(name="tokens", status="ok", code=None)


def _schema(ctx: Ctx) -> Component:
    """Realtime mode: the database schema must be at the version this release needs (Spec 15, OD-167)."""
    if ctx.settings.app.mode != "realtime":
        return Component(name="schema", status="ok", code=None)
    from cji.migrations.runner import SchemaCheckError, check_schema

    try:
        check_schema(ctx.settings)
    except SchemaCheckError as exc:
        logger.warning("health: schema not ready (%s)", exc.code)
        return Component(name="schema", status="unavailable", code=exc.code)
    return Component(name="schema", status="ok", code=None)


@router.get("/me", response_model=Me, summary="The calling token", operation_id="getMe", responses=errors(),
            dependencies=[only_query()])
def me(caller: Caller) -> Me:
    return Me(token_id=caller.token_id, label=caller.label, role=caller.role,  # type: ignore[arg-type]
              journeys=list(caller.journeys))
