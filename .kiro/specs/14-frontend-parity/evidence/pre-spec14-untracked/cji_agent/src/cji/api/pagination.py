"""
Opaque, signed keyset cursors (Spec 12, OD-119).

cursor = base64url(json {"k": keyset, "q": hash(filters)}) + "." + base64url(HMAC-SHA256(key, payload))[:22]
A cursor only works with the query that produced it (same filters) and cannot be edited.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from .errors import ApiError

MAX_CURSOR_LENGTH = 1024
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _filters_hash(filters: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(filters), sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


class CursorCodec:
    def __init__(self, key: bytes) -> None:
        self.key = key

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self.key, payload.encode("ascii"), hashlib.sha256).digest())[:22]

    def encode(self, keyset: list[Any], filters: Mapping[str, Any]) -> str:
        payload = _b64(json.dumps({"k": keyset, "q": _filters_hash(filters)}, separators=(",", ":")).encode("utf-8"))
        return f"{payload}.{self._sign(payload)}"

    def decode(self, cursor: str, filters: Mapping[str, Any]) -> list[Any]:
        try:
            if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
                raise ValueError
            payload, signature = cursor.split(".", 1)
            if not hmac.compare_digest(signature, self._sign(payload)):
                raise ValueError
            data = json.loads(_unb64(payload))
            if data.get("q") != _filters_hash(filters) or not isinstance(data.get("k"), list):
                raise ValueError
            return list(data["k"])
        except (ValueError, TypeError, UnicodeError):
            raise ApiError(422, "invalid_cursor") from None
