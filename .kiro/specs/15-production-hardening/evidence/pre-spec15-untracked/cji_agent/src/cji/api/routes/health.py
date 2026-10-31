"""GET /health (public), /health/details and /me."""
from __future__ import annotations

import logging
import sqlite3
from typing import Literal

from fastapi import APIRouter

from cji.repositories import RepositoryError

from ..errors import problem_responses
from ..schemas import Component, Health, HealthDetails, Me
from ._deps import Caller, Ctx, errors, only_query

router = APIRouter(tags=["health"])
logger = logging.getLogger("cji.api")


def _version() -> str:
    from ..app import API_VERSION

    return API_VERSION


@router.get("/health", response_model=Health, summary="Liveness (public)", operation_id="getHealth",
            responses=problem_responses(429, 500), dependencies=[only_query()])
def health(ctx: Ctx) -> Health:
    return Health(status="ok", version=_version(), mode=ctx.settings.app.mode)


@router.get("/health/details", response_model=HealthDetails, summary="Component status",
            operation_id="getHealthDetails", responses=errors(), dependencies=[only_query()])
def health_details(ctx: Ctx, _caller: Caller) -> HealthDetails:
    components = [_repository(ctx), _checkpoints(ctx), _reports(ctx)]
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


@router.get("/me", response_model=Me, summary="The calling token", operation_id="getMe", responses=errors(),
            dependencies=[only_query()])
def me(caller: Caller) -> Me:
    return Me(token_id=caller.token_id, label=caller.label, role=caller.role,  # type: ignore[arg-type]
              journeys=list(caller.journeys))
