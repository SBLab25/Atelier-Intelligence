"""
Collector authentication and rate limiting (Spec 07, OD-44 / OD-46).

- `authenticate` looks a tracker key up in `api_keys` inside the caller's transaction.
- `key_fingerprint` is the only form of a key that reaches logs or rate-limit buckets.
- `RateLimiter` is an in-process token bucket per identifier. Limits are per process: with
  several workers each worker counts separately (documented in README).
- `client_address` uses the socket peer unless the deployment declares trusted proxy hops.
"""
from __future__ import annotations

import hashlib
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

_KEY_LOOKUP = text("SELECT journey_name, is_active FROM api_keys WHERE api_key = :api_key")
_EPSILON = 1e-9   # refill arithmetic in floats: 30 s x (2/60 per s) must count as one token


@dataclass(frozen=True)
class KeyGrant:
    """An active tracker key: which journey it may write, and its log-safe fingerprint."""

    fingerprint: str
    journey: str


def key_fingerprint(key: str) -> str:
    """First 8 hex characters of sha256(key): enough to tell keys apart in logs, not to recover them."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def authenticate(api_key: str, conn: Any) -> KeyGrant | None:
    """Return the grant for an active key, or None for an unknown or inactive key."""
    row = conn.execute(_KEY_LOOKUP, {"api_key": api_key}).fetchone()
    if row is None or not row[1]:
        return None
    return KeyGrant(fingerprint=key_fingerprint(api_key), journey=str(row[0] or ""))


class RateLimiter:
    """
    Token buckets: each identifier may make `rate_per_minute` requests per minute, with bursts up
    to the same number. `check` consumes one token and returns None, or returns the seconds to wait.
    """

    def __init__(
        self,
        rate_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_buckets: int = 10_000,
    ) -> None:
        if rate_per_minute < 1:
            raise ValueError("rate_per_minute must be at least 1")
        self.capacity = float(rate_per_minute)
        self.refill_per_s = rate_per_minute / 60.0
        self._clock = clock
        self._max_buckets = max_buckets
        self._buckets: dict[str, tuple[float, float]] = {}   # id -> (tokens, last update)
        self._lock = threading.Lock()

    def check(self, bucket_id: str) -> float | None:
        with self._lock:
            now = self._clock()
            tokens, last = self._buckets.get(bucket_id, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.refill_per_s)
            if tokens >= 1.0 - _EPSILON:
                self._buckets[bucket_id] = (tokens - 1.0, now)
                self._prune(now)
                return None
            self._buckets[bucket_id] = (tokens, now)
            return (1.0 - tokens) / self.refill_per_s

    def _prune(self, now: float) -> None:
        """Drop buckets that have refilled completely once the table grows past its bound."""
        if len(self._buckets) <= self._max_buckets:
            return
        full_after = self.capacity / self.refill_per_s
        for bucket_id, (_, last) in list(self._buckets.items()):
            if now - last >= full_after:
                del self._buckets[bucket_id]


def retry_after_header(wait_s: float) -> str:
    """Whole seconds for a Retry-After header (at least 1)."""
    return str(max(1, math.ceil(wait_s)))


def client_address(peer: str | None, forwarded_for: str | None, trusted_hops: int) -> str:
    """
    The client address used for rate limiting. With `trusted_hops == 0` the socket peer is used and
    X-Forwarded-For is ignored (it is client-controlled). With N trusted proxies, the N-th address
    from the right of X-Forwarded-For is the one the outermost trusted proxy saw.
    """
    if trusted_hops > 0 and forwarded_for:
        hops = [part.strip() for part in forwarded_for.split(",") if part.strip()]
        if len(hops) >= trusted_hops:
            return hops[-trusted_hops]
    return peer or "unknown"
