"""
The /api/v1 OpenAPI document (Spec 12, OD-123): FastAPI's generated document with the contract's conventions applied.

- every error response is `application/problem+json` with the `Problem` schema (FastAPI's default 422 and its
  `HTTPValidationError` schemas are removed);
- every operation except `GET /health` and `GET /health/ready` (Spec 15) requires `bearerAuth`;
- the readiness 503 keeps its plain JSON body `{"status": "not_ready"}` (load balancers read it);
- `ApprovalRequest`, `StartRunRequest` and `IngestionRequest` are components because their bodies are parsed by
  the routes (to check the Idempotency-Key and the content type first).
The result is deterministic, so `cji_agent/openapi/v1.json` can be compared with it.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .errors import FieldError, Problem
from .schemas import ApprovalRequest, IngestionRequest, StartRunRequest

PUBLIC_OPERATIONS = frozenset({("get", "/api/v1/health"), ("get", "/api/v1/health/ready")})
PLAIN_ERRORS = frozenset({("get", "/api/v1/health/ready", "503")})
REF = "#/components/schemas/{model}"
_DROPPED = ("HTTPValidationError", "ValidationError")


def _component(model: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    schema = model.model_json_schema(ref_template=REF, mode="validation")
    defs = schema.pop("$defs", {})
    return schema, defs


def build_openapi(app: FastAPI, version: str) -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    doc = get_openapi(title=app.title, version=version, description=app.description, routes=app.routes)
    components = doc.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    for name in _DROPPED:
        schemas.pop(name, None)
    for model in (Problem, FieldError, ApprovalRequest, StartRunRequest, IngestionRequest):
        schema, defs = _component(model)
        schemas[model.__name__] = schema
        schemas.update(defs)
    components["schemas"] = dict(sorted(schemas.items()))
    components["securitySchemes"] = {"bearerAuth": {
        "type": "http", "scheme": "bearer",
        "description": "An API token (`cji_api_...`) created with `cji-api-token create`.",
    }}
    for path, item in doc.get("paths", {}).items():
        for method, operation in item.items():
            if (method, path) in PUBLIC_OPERATIONS:
                operation.pop("security", None)
            else:
                operation["security"] = [{"bearerAuth": []}]
            for status, response in operation.get("responses", {}).items():
                if status.startswith(("4", "5")) and (method, path, status) not in PLAIN_ERRORS:
                    response["content"] = {"application/problem+json": {
                        "schema": {"$ref": REF.format(model="Problem")}}}
    app.openapi_schema = doc
    return doc
