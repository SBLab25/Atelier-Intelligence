"""
RFC 9457 problem responses for /api/v1 (Spec 12, OD-118, OD-127).

Every non-2xx response is `application/problem+json` with `type`, `title`, `status`, `detail`, `code` and
`request_id` (plus `errors` for validation). `detail` is fixed per code or built from validated identifiers only;
exception messages and submitted values are never copied into a response.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cji.http.request_id import current_request_id

PROBLEM_TYPE = "application/problem+json"

TITLES: dict[str, str] = {
    "idempotency_key_required": "Idempotency-Key header required",
    "idempotency_key_invalid": "Idempotency-Key header invalid",
    "missing_token": "Authentication required",  # nosec B105 - problem code, not a secret
    "invalid_token": "Invalid token",  # nosec B105 - problem code, not a secret
    "insufficient_role": "Insufficient role",
    "journey_forbidden": "Journey not allowed",
    "not_found": "Not found",
    "journey_not_found": "Journey not found",
    "run_not_found": "Run not found",
    "report_not_found": "Report not found",
    "method_not_allowed": "Method not allowed",
    "run_not_awaiting_approval": "Run is not awaiting approval",
    "run_busy": "Run is busy",
    "idempotency_key_reused": "Idempotency-Key reused",
    "request_in_progress": "Request in progress",
    "request_too_large": "Request too large",
    "unsupported_media_type": "Unsupported media type",
    "validation_failed": "Validation failed",
    "invalid_cursor": "Invalid cursor",
    "rate_limited": "Too many requests",
    "internal_error": "Internal server error",
    "storage_unavailable": "Storage unavailable",
    "service_misconfigured": "Service misconfigured",
}

DETAILS: dict[str, str] = {
    "idempotency_key_required": "Send an Idempotency-Key header (8-64 of A-Z a-z 0-9 . _ -) with every POST.",
    "idempotency_key_invalid": "The Idempotency-Key must be 8-64 of A-Z a-z 0-9 . _ -.",
    "missing_token": "Send 'Authorization: Bearer <token>'.",  # nosec B105 - problem text, not a secret
    "invalid_token": "The token is unknown, revoked or expired.",  # nosec B105 - problem text, not a secret
    "insufficient_role": "Your token's role does not allow this request.",
    "journey_forbidden": "Your token does not include this journey.",
    "not_found": "No such resource.",
    "journey_not_found": "No journey with this id.",
    "run_not_found": "No run with this id.",
    "report_not_found": "No report with this id.",
    "method_not_allowed": "This method is not allowed on this resource.",
    "run_busy": "Another process is working on this run; retry later.",
    "idempotency_key_reused": "This Idempotency-Key was used for a different request.",
    "request_in_progress": "A request with this Idempotency-Key is still being processed; retry later.",
    "request_too_large": "The request body is too large.",
    "unsupported_media_type": "Send the body as application/json.",
    "validation_failed": "The request has invalid parameters; see errors.",
    "invalid_cursor": "The cursor is not valid for this request; start again without it.",
    "rate_limited": "Too many requests; retry after the Retry-After interval.",
    "internal_error": "The request failed. Quote the request_id when reporting it.",
    "storage_unavailable": "A storage backend is unavailable; retry later.",
    "service_misconfigured": "The service configuration is incomplete; contact the operator.",
}


class FieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str = Field(description="query, path, header or body")
    field: str
    reason: str = Field(description="Validation rule that failed (no submitted value)")


class Problem(BaseModel):
    """RFC 9457 problem details with CJI extensions."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(description="urn:cji:problem:<code>")
    title: str
    status: int
    detail: str
    code: str
    request_id: str
    errors: list[FieldError] | None = None


class ApiError(Exception):
    """An error with a stable code; turned into a problem response."""

    def __init__(self, status: int, code: str, detail: str | None = None, *,
                 headers: dict[str, str] | None = None, errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail or DETAILS.get(code, TITLES.get(code, code))
        self.headers = headers or {}
        self.errors = errors


def problem_body(status: int, code: str, detail: str | None = None,
                 errors: list[dict[str, str]] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"urn:cji:problem:{code}",
        "title": TITLES.get(code, code),
        "status": status,
        "detail": detail or DETAILS.get(code, TITLES.get(code, code)),
        "code": code,
        "request_id": current_request_id(),
    }
    if errors is not None:
        body["errors"] = errors
    return body


def problem_bytes(status: int, code: str, detail: str | None = None,
                  errors: list[dict[str, str]] | None = None) -> bytes:
    return json.dumps(problem_body(status, code, detail, errors)).encode("utf-8")


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` entries for error statuses (problem+json; the schema is added by cji.api.openapi)."""
    return {s: {"description": _DESCRIPTIONS.get(s, "Error"),
                "content": {PROBLEM_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}}}
            for s in statuses}


_DESCRIPTIONS = {
    400: "Bad request", 401: "Missing or invalid token", 403: "Forbidden", 404: "Not found", 405: "Method not allowed",
    409: "Conflict", 413: "Request too large", 415: "Unsupported media type", 422: "Validation failed",
    429: "Rate limited", 500: "Internal error", 503: "Service unavailable",
}
