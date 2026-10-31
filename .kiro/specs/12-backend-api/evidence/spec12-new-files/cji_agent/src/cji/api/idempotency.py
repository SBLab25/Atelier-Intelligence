"""
Idempotency-Key store for /api/v1 mutations (Spec 12, OD-117). SQLite in <data_dir>/api_state.db.

begin(): None = new request (row stored as in progress); (status, body) = replay of a finished request;
ApiError 409 for a key reused with another request or still in progress. finish() stores the response;
abandon() removes the row after a failure so the client can retry with the same key.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .errors import ApiError

DEFAULT_TTL_S = 24 * 3600

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS idempotency (token_id TEXT NOT NULL, key TEXT NOT NULL, route TEXT NOT NULL, "
    "request_hash TEXT NOT NULL, status INTEGER, response TEXT, created_at REAL NOT NULL, "
    "PRIMARY KEY (token_id, key))"
)


class IdempotencyStore:
    def __init__(self, path: Path, ttl_s: float = DEFAULT_TTL_S) -> None:
        self.path = Path(path)
        self.ttl_s = ttl_s

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.execute(_SCHEMA)
        return conn

    @staticmethod
    def request_hash(route: str, body: bytes) -> str:
        return hashlib.sha256(route.encode("utf-8") + b"\n" + body).hexdigest()

    def begin(self, token_id: str, key: str, route: str, request_hash: str) -> tuple[int, Any] | None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT route, request_hash, status, response, created_at FROM idempotency "
                               "WHERE token_id = ? AND key = ?", (token_id, key)).fetchone()
            if row is not None and row[4] < time.time() - self.ttl_s:
                conn.execute("DELETE FROM idempotency WHERE token_id = ? AND key = ?", (token_id, key))
                row = None
            if row is None:
                conn.execute("INSERT INTO idempotency (token_id, key, route, request_hash, created_at) "
                             "VALUES (?, ?, ?, ?, ?)", (token_id, key, route, request_hash, time.time()))
                conn.execute("COMMIT")
                return None
            conn.execute("COMMIT")
        except BaseException:  # broad-except: roll back on any failure, then re-raise
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        if row[0] != route or row[1] != request_hash:
            raise ApiError(409, "idempotency_key_reused")
        if row[2] is None:
            raise ApiError(409, "request_in_progress", headers={"Retry-After": "1"})
        return int(row[2]), json.loads(row[3])

    def finish(self, token_id: str, key: str, status: int, body: Any) -> None:
        conn = self._connect()
        try:
            conn.execute("UPDATE idempotency SET status = ?, response = ? WHERE token_id = ? AND key = ?",
                         (status, json.dumps(body), token_id, key))
        finally:
            conn.close()

    def abandon(self, token_id: str, key: str) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM idempotency WHERE token_id = ? AND key = ? AND status IS NULL", (token_id, key))
        finally:
            conn.close()

    def purge(self, now: float | None = None) -> int:
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM idempotency WHERE created_at < ?", ((now or time.time()) - self.ttl_s,))
            return int(cur.rowcount)
        finally:
            conn.close()
