"""
Ingestion with validation feedback (Spec 14, OD-148).

POST /ingestions/validations parses an uploaded file and writes nothing to the event store; POST /ingestions writes a
validated file to tracking_events (append: operator, replace: admin). Mounted only when CJI_API_WRITE_OPERATIONS
is true (OD-155).
"""
from __future__ import annotations

import logging
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from cji.services import ingestion, journeys

from ..errors import ApiError
from ..schemas import Ingestion, IngestionRequest, IngestionValidation
from ._deps import (
    API_PREFIX,
    Caller,
    Ctx,
    check_idempotency_key,
    errors,
    json_body,
    only_query,
    require_role,
)

router = APIRouter(tags=["ingestions"])
logger = logging.getLogger("cji.api")

UPLOAD_PATH = f"{API_PREFIX}/ingestions/validations"
UPLOAD_TYPES = ("application/json", "application/x-ndjson", "text/csv")
MAX_MAP_ENTRIES = 20
FileName = Annotated[str, Query(min_length=6, max_length=128,
                                pattern=r"^[^\x00-\x1f\x7f/\\:]+\.([jJ][sS][oO][nN]|[nN][dD][jJ][sS][oO][nN]|"
                                        r"[jJ][sS][oO][nN][lL]|[cC][sS][vV])$",
                                description="Original file name (.json, .ndjson, .jsonl or .csv); selects the parser")]
RootKey = Annotated[str | None, Query(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$",
                                      description="Key of the record list in a wrapped JSON object")]
MapEntries = Annotated[list[str] | None, Query(alias="map",
                                               description="Column mapping `your_col=cji_col`, repeatable (max 20)")]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key", description="8-64 of A-Z a-z 0-9 . _ -")]
STATUS = {"ingestion_unreadable": 422, "unsupported_media_type": 415, "validation_not_found": 404,
          "validation_used": 409, "database_unavailable": 503}


def _store(ctx: Ctx) -> ingestion.UploadStore:
    return ingestion.UploadStore(ctx.settings.storage.data_dir / "ingestion_uploads")


def _database_configured(ctx: Ctx) -> bool:
    return ctx.ingestion_engine is not None or bool(ctx.settings.database.url_value())


def _raise(exc: ingestion.IngestionError) -> NoReturn:
    raise ApiError(STATUS[exc.code], exc.code) from None


def _journey_steps(ctx: Ctx, caller: Caller) -> list[str]:
    steps: list[str] = []
    for journey in journeys.list_journeys(ctx.settings):
        if caller.can_see(journey.name):
            steps += [s for s in journey.steps if s not in steps]
    return steps


@router.post(
    "/ingestions/validations", response_model=IngestionValidation, status_code=201,
    summary="Validate an event file without writing it (operator)", operation_id="validateIngestion",
    dependencies=[only_query("filename", "root_key", "map")],
    responses=errors(403, 413, 415, 422),
    openapi_extra={"requestBody": {"required": True, "content": {
        media: {"schema": {"type": "string", "format": "binary"}} for media in UPLOAD_TYPES}}},
)
async def validate_ingestion(request: Request, ctx: Ctx, caller: Caller, filename: FileName,
                             root_key: RootKey = None, mapping: MapEntries = None) -> JSONResponse:
    require_role(caller, "operator")
    media = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media not in UPLOAD_TYPES:
        raise ApiError(415, "unsupported_media_type",
                       "Send the file as application/json, application/x-ndjson or text/csv.")
    entries = list(mapping or [])
    if len(entries) > MAX_MAP_ENTRIES:
        raise RequestValidationError([{"type": "too_long", "loc": ("query", "map"), "msg": "Too many entries"}])
    try:
        col_map = ingestion.parse_map(entries)
    except ValueError:
        raise RequestValidationError([{"type": "invalid_mapping", "loc": ("query", "map"),
                                       "msg": "Use your_col=cji_col with a CJI column"}]) from None
    data = await request.body()
    if not data.strip():
        raise ApiError(422, "ingestion_unreadable")
    try:
        result = await run_in_threadpool(
            ingestion.validate, _store(ctx), data=data, filename=filename, root_key=root_key, col_map=col_map,
            journey_steps=_journey_steps(ctx, caller), token_id=caller.token_id,
            database_configured=_database_configured(ctx))
    except ingestion.IngestionError as exc:
        _raise(exc)
    body = IngestionValidation.model_validate(result).model_dump(mode="json")
    logger.info("ingestion %s validated by %s: %d of %d rows accepted", body["validation_id"], caller.token_id,
                body["rows"]["accepted"], body["rows"]["parsed"])
    return JSONResponse(body, status_code=201)


@router.post(
    "/ingestions", response_model=Ingestion, status_code=201,
    summary="Write a validated file to tracking_events (append: operator, replace: admin)",
    operation_id="createIngestion", dependencies=[only_query()],
    responses=errors(400, 403, 404, 409, 413, 415, 422),
    openapi_extra={"requestBody": {"required": True, "content": {
        "application/json": {"schema": {"$ref": "#/components/schemas/IngestionRequest"}}}}},
)
async def create_ingestion(request: Request, ctx: Ctx, caller: Caller,
                           idempotency_key: IdempotencyKey = None) -> JSONResponse:
    key = check_idempotency_key(idempotency_key)
    raw = await request.body()
    body = json_body(request, raw, IngestionRequest)
    require_role(caller, "admin" if body.write_mode == "replace" else "operator")
    route = f"POST {API_PREFIX}/ingestions"
    store = ctx.idempotency
    replay = store.begin(caller.token_id, key, route, store.request_hash(route, raw))
    if replay is not None:
        code, stored = replay
        return JSONResponse(stored, status_code=code, headers={"Idempotent-Replayed": "true"})
    try:
        if not _database_configured(ctx):
            raise ApiError(503, "database_unavailable")
        engine: Any = ctx.ingestion_engine() if ctx.ingestion_engine else None
        try:
            result = await run_in_threadpool(ingestion.commit, _store(ctx), validation_id=body.validation_id,
                                             write_mode=body.write_mode, token_id=caller.token_id, engine=engine)
        except ingestion.IngestionError as exc:
            _raise(exc)
        payload = Ingestion.model_validate(result).model_dump(mode="json")
        store.finish(caller.token_id, key, 201, payload)
    except BaseException:  # broad-except: free the key on any failure so the client can retry; re-raised
        store.abandon(caller.token_id, key)
        raise
    return JSONResponse(payload, status_code=201)
