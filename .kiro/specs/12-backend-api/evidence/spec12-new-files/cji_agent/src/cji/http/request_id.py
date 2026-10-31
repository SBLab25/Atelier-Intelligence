"""
Request ids (Spec 07, OD-47; shared since Spec 12, OD-120).

A well-formed client `X-Request-ID` (8-64 of A-Z a-z 0-9 . _ -) is kept; anything else is replaced by a UUID4.
The id lives in a context variable for the duration of the request, so routes, thread-pool code and log records
(through RequestIdFilter) can read it.
"""
from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar, Token

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
_request_id: ContextVar[str] = ContextVar("cji_request_id", default="-")


def resolve_request_id(raw: str | None) -> str:
    """Keep a well-formed client id; otherwise generate a UUID4."""
    if raw and _VALID_REQUEST_ID.fullmatch(raw):
        return raw
    return str(uuid.uuid4())


def current_request_id() -> str:
    return _request_id.get()


def set_request_id(value: str) -> Token[str]:
    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


class RequestIdFilter(logging.Filter):
    """Adds `request_id` to every record so formatters and log shippers can correlate lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__["request_id"] = _request_id.get()
        return True
