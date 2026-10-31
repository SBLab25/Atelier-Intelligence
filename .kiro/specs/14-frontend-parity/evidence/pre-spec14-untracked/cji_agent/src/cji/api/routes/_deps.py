"""Shared request helpers for the /api/v1 routes: context, principal, query checks, journey visibility."""
from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, Path, Query, Request
from fastapi.exceptions import RequestValidationError

from cji.domain.journeys import JourneyDefinition
from cji.services import journeys

from ..app import ApiContext
from ..auth import Principal
from ..errors import ApiError, problem_responses
from ..pagination import DEFAULT_LIMIT, MAX_LIMIT

API_PREFIX = "/api/v1"
MAX_QUERY_ERRORS = 20

# Error statuses every protected operation can return (OD-118, OD-121, OD-127; 503 = unusable token file).
COMMON = (401, 429, 500, 503)

JourneyId = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f/]+$",
                                description="Journey id (the configured journey name)")]
RunId = Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{1,64}$", description="Run id (thread id)")]
ReportId = Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,140}$",
                               description="Report file name without `cji_report_` and `.html`")]
Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Page size")]
Cursor = Annotated[str | None, Query(max_length=1024, description="`page.next_cursor` of the previous page")]
DEFAULT_PAGE = DEFAULT_LIMIT


def errors(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI responses for the common errors plus `statuses`."""
    return problem_responses(*sorted(set(COMMON) | set(statuses)))


def get_context(request: Request) -> ApiContext:
    ctx: ApiContext = request.app.state.ctx
    return ctx


def get_principal(request: Request) -> Principal:
    principal = request.scope.get("state", {}).get("principal")
    if not isinstance(principal, Principal):      # the gate authenticates every protected path first
        raise ApiError(401, "missing_token", headers={"WWW-Authenticate": 'Bearer realm="cji-api"'})
    return principal


Ctx = Annotated[ApiContext, Depends(get_context)]
Caller = Annotated[Principal, Depends(get_principal)]


def only_query(*names: str) -> Any:
    """Dependency: 422 for query parameters the operation does not define (OD-122). Values are never echoed."""
    allowed = frozenset(names)

    def check(request: Request) -> None:
        unknown = sorted({k for k in request.query_params if k not in allowed})
        if unknown:
            raise RequestValidationError([
                {"type": "unknown_parameter", "loc": ("query", name), "msg": "Unknown query parameter"}
                for name in unknown[:MAX_QUERY_ERRORS]
            ])

    return Depends(check)


def require_role(principal: Principal, role: str) -> None:
    if not principal.has_role(role):
        raise ApiError(403, "insufficient_role")


def require_filter(principal: Principal, journey_id: str | None) -> None:
    """A list filter naming a journey outside the token is forbidden (OD-110)."""
    if journey_id is not None and not principal.can_see(journey_id):
        raise ApiError(403, "journey_forbidden")


def visible_journey(ctx: ApiContext, principal: Principal, journey_id: str, role: str = "viewer") -> JourneyDefinition:
    """Visibility first (403 even for unknown ids), then the role, then existence (404)."""
    if not principal.can_see(journey_id):
        raise ApiError(403, "journey_forbidden")
    require_role(principal, role)
    found = journeys.get_journey(ctx.settings, journey_id)
    if found is None:
        raise ApiError(404, "journey_not_found")
    return found


def page_after(ctx: ApiContext, cursor: str | None, filters: dict[str, Any]) -> list[Any] | None:
    return None if cursor is None else ctx.cursors.decode(cursor, filters)


def next_cursor(ctx: ApiContext, more: bool, keyset: Callable[[], list[Any]], filters: dict[str, Any]) -> str | None:
    return ctx.cursors.encode(keyset(), filters) if more else None
