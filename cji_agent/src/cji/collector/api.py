"""
CJI Collector (FastAPI).

Spec 07: every batch is authenticated, validated per event, and written synchronously in one
transaction; the response is sent only after commit and reports exact accepted, duplicate and
rejected counts. Database failures return 503 and are never reported as stored.
"""
import asyncio
import json
import logging
import secrets
from importlib.resources import files
from typing import Any

import requests
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from cji.collector import ingest
from cji.collector.middleware import (
    REQUEST_ID_HEADER,
    CollectorMiddleware,
    RequestIdFilter,
    current_request_id,
)
from cji.collector.models import CollectResult
from cji.collector.security import (
    RateLimiter,
    authenticate,
    client_address,
    key_fingerprint,
    retry_after_header,
)
from cji.domain.journeys import JourneyId
from cji.integrations.audit import security_event
from cji.logs import configure_logging
from cji.observability import metrics
from cji.settings import ConfigError, get_settings, secret_value
from cji.settings.model import DEV_TRACKER_KEY, KNOWN_DEFAULT_ADMIN_KEYS
from cji.settings.roles import collector_problems, database_missing, endpoint_problems

logger = logging.getLogger("collector")
logger.addFilter(RequestIdFilter())

# ─── SETTINGS (Spec 04 / 07; module names kept so tests can patch them) ────
_SETTINGS = get_settings()
CJI_ENV: str = _SETTINGS.app.env
CJI_ADMIN_KEY: str = secret_value(_SETTINGS.auth.admin_key)
CJI_CORS_ORIGINS: list[str] = list(_SETTINGS.cors.origins)
JOURNEY_NAME: str = _SETTINGS.app.journey_name
MAX_BODY_BYTES: int = _SETTINGS.collector.max_body_bytes
TRUSTED_PROXY_HOPS: int = _SETTINGS.collector.trusted_proxy_hops
RETRY_AFTER_S = 5                       # advised wait after a database failure

NOT_STORED = "Events were not stored. Retry with the same event_id values."
INVALID_KEY = "Invalid API key."


def _new_limiters() -> tuple[RateLimiter, RateLimiter, RateLimiter]:
    c = _SETTINGS.collector
    return RateLimiter(c.rate_per_key), RateLimiter(c.rate_per_ip), RateLimiter(c.admin_rate_per_ip)


# In-process token buckets (OD-46): per key fingerprint, per client address, admin per address.
KEY_LIMITER, IP_LIMITER, ADMIN_LIMITER = _new_limiters()


def reset_rate_limits() -> None:
    """Start every bucket again (tests; also usable from an operator shell)."""
    global KEY_LIMITER, IP_LIMITER, ADMIN_LIMITER
    KEY_LIMITER, IP_LIMITER, ADMIN_LIMITER = _new_limiters()


class EventBroadcaster:
    """Async in-process fanout broadcaster for streaming live ingested events to SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)

    def publish(self, events: list[dict[str, Any]]) -> None:
        """Safe thread-safe or async dispatch of newly stored events to subscribers."""
        if not self._subscribers or not events:
            return
        for ev in events:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(ev)
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                        q.put_nowait(ev)
                    except Exception:
                        pass
                except Exception:
                    pass


BROADCASTER = EventBroadcaster()


def cors_options(origins: list[str]) -> dict[str, Any]:
    """CORS for browsers (CO-03): explicit origins, no credentials, no admin header."""
    return {
        "allow_origins": list(origins),          # explicit list from config, never "*"
        "allow_credentials": False,              # tracker authenticates with a key, not cookies
        "allow_methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "X-CJI-Key", REQUEST_ID_HEADER],
        "expose_headers": [REQUEST_ID_HEADER, "Retry-After"],
        "max_age": 600,
    }


app = FastAPI(title="CJI Collector", version="1.1.0")
# Added first, so it runs inside CORS: 413 responses still carry CORS headers.
app.add_middleware(CollectorMiddleware, max_body_bytes=lambda: MAX_BODY_BYTES)
app.add_middleware(CORSMiddleware, **cors_options(CJI_CORS_ORIGINS))


# ─── DATABASE CONNECTION ───────────────────────────────────────────────────
class UnconfiguredDatabase:
    """Engine stand-in when no database URL is configured: fails with a ConfigError on use."""

    def begin(self):
        raise ConfigError([database_missing("The collector")], role="collector", env=CJI_ENV)

    connect = begin

    def dispose(self):
        pass


def _make_engine(url):
    # hide_parameters: driver errors and SQL logging never include bound values (OD-50).
    return create_engine(url, pool_pre_ping=True, hide_parameters=True) if url else UnconfiguredDatabase()


engine = _make_engine(_SETTINGS.database.url_value())

# ─── STARTUP SETTINGS (fail closed outside explicit development) ───────────


def admin_key_usable(key: str | None) -> bool:
    """True only for a configured admin key that is not a shipped default."""
    return bool(key) and key not in KNOWN_DEFAULT_ADMIN_KEYS


def validate_collector_settings(env: str, admin_key: str | None, origins: list[str]) -> None:
    """Refuse to start with unsafe settings unless CJI_ENV is explicitly 'development'."""
    problems = collector_problems(env, admin_key, origins)
    if problems:
        raise ConfigError(problems, role="collector", env=env or "unset")


def _create_tables():
    # Live events table matching the structure of synthetic events
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS live_events (
                timestamp TIMESTAMP,
                event_id VARCHAR PRIMARY KEY,
                session_id VARCHAR,
                user_id VARCHAR,
                journey_name VARCHAR,
                step_id VARCHAR,
                event_type VARCHAR,
                url VARCHAR,
                element_selectors VARCHAR,
                metadata JSONB,
                account_id VARCHAR
            )
        """))
        conn.execute(text("ALTER TABLE live_events ADD COLUMN IF NOT EXISTS account_id VARCHAR;"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS live_events_account_idx ON live_events(account_id);"))
        # API Keys table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS api_keys (
                api_key VARCHAR PRIMARY KEY,
                journey_name VARCHAR,
                description VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT true,
                account_id VARCHAR
            )
        """))
        conn.execute(text("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS account_id VARCHAR;"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS api_keys_account_idx ON api_keys(account_id);"))

        # Development-only key for local tracker testing, for the configured journey
        # (JOURNEY_NAME). No live or production key is ever written at startup (R-03).
        if CJI_ENV == "development":
            conn.execute(text("""
                INSERT INTO api_keys (api_key, journey_name, description)
                VALUES (:api_key, :journey, 'Local Development')
                ON CONFLICT (api_key) DO NOTHING
            """), {"api_key": DEV_TRACKER_KEY, "journey": JOURNEY_NAME})

def _ping_keepalive(url: str):
    try:
        res = requests.get(url, timeout=5)
        logger.info(f"Keep-alive ping sent, status: {res.status_code}")
    except requests.RequestException as e:
        logger.error(f"Keep-alive ping failed: {type(e).__name__}: {e}")

async def keep_alive(url: str, interval_s: float):
    """Optional outbound ping, only when CJI_KEEPALIVE_URL is set (Spec 04, OD-27)."""
    await asyncio.sleep(60) # Wait 1 minute after startup
    while True:
        await asyncio.to_thread(_ping_keepalive, url)
        await asyncio.sleep(interval_s)

@app.on_event("startup")
async def startup_event():
    configure_logging()             # runtime, not import (Spec 11, OD-105); no-op if uvicorn/pytest set handlers
    # Fail closed before touching the database (R-03); report every problem at once (Spec 04).
    problems = collector_problems(CJI_ENV, CJI_ADMIN_KEY, CJI_CORS_ORIGINS)
    if isinstance(engine, UnconfiguredDatabase):
        problems.append(database_missing("The collector"))
    problems += endpoint_problems(_SETTINGS)
    if problems:
        raise ConfigError(problems, role="collector", env=CJI_ENV)
    logger.info("Connecting to Database...")
    _create_tables()
    if _SETTINGS.keepalive.url:
        asyncio.create_task(keep_alive(_SETTINGS.keepalive.url, _SETTINGS.keepalive.interval_s))

@app.on_event("shutdown")
def shutdown_event():
    engine.dispose()

# ─── MODELS ───────────────────────────────────────────────────────────────
# Browser events are validated with domain.events.TrackerEvent (Spec 03), one at a time
# (collector.ingest); responses use collector.models.CollectResult (Spec 07).
class AdminKeyCreate(BaseModel):
    journey_name: str = Field(..., min_length=1, max_length=256, description="Journey identifier, list, or '*'")
    description: str = Field(..., max_length=256)
    account_id: str | None = Field(default=None, max_length=64)


# ─── HELPERS ───────────────────────────────────────────────────────────────

def _client(request: Request) -> str:
    peer = request.client.host if request.client else None
    return client_address(peer, request.headers.get("x-forwarded-for"), TRUSTED_PROXY_HOPS)


def _sqlstate(exc: Exception) -> str:
    """PostgreSQL SQLSTATE of a driver error (safe to log: a code, never a value)."""
    return str(getattr(getattr(exc, "orig", None), "pgcode", None) or "-")


def _rejected(status_code: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    body: dict[str, object] = {"status": "rejected", "request_id": current_request_id(), "detail": detail}
    if status_code == 429:
        body["retryable"] = True
    return JSONResponse(body, status_code=status_code, headers=headers)


def _result(result: CollectResult, status_code: int, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(result.model_dump(exclude_none=True), status_code=status_code, headers=headers)


def _require_admin(request: Request, provided: str | None) -> None:
    """Admin routes: rate limited per address, then a usable admin key in constant time (R-03)."""
    wait = ADMIN_LIMITER.check(_client(request))
    if wait is not None:
        metrics.RATE_LIMITED.inc(service="cji-collector", limiter="admin")
        raise HTTPException(status_code=429, detail="Too many admin requests.",
                            headers={"Retry-After": retry_after_header(wait)})
    if not provided or not admin_key_usable(CJI_ADMIN_KEY) or not secrets.compare_digest(
        provided.encode("utf-8"), CJI_ADMIN_KEY.encode("utf-8")
    ):
        security_event("collector.admin.denied", actor="-", outcome="denied",
                       target=getattr(request.scope.get("route"), "path", None) or request.url.path)
        raise HTTPException(status_code=403, detail="Invalid ADMIN Key")


def _store_batch(envelope: ingest.Envelope, fingerprint: str) -> JSONResponse:
    """Authenticate, validate and write in one transaction; answer only after commit (OD-41)."""
    request_id = current_request_id()
    received = len(envelope.events)
    checked = None
    grant = None
    accepted = 0
    try:
        with engine.begin() as conn:
            grant = authenticate(envelope.api_key, conn)
            if grant is not None:
                checked = ingest.validate_events(envelope.events, grant)
                accepted = ingest.store_events(conn, checked.valid, account_id=grant.account_id)
    except (SQLAlchemyError, ConfigError) as exc:
        logger.error("collect failed request_id=%s key=%s received=%d error=%s sqlstate=%s",
                     request_id, fingerprint, received, type(exc).__name__, _sqlstate(exc))
        failed = CollectResult(status="failed", request_id=request_id, received=received,
                               retryable=True, detail=NOT_STORED)
        metrics.COLLECTOR_EVENTS.inc(received, outcome="failed")
        return _result(failed, 503, headers={"Retry-After": str(RETRY_AFTER_S)})

    if checked is None:
        logger.info("collect rejected request_id=%s key=%s reason=invalid_key", request_id, fingerprint)
        metrics.COLLECTOR_EVENTS.inc(received, outcome="invalid_key")
        return _rejected(401, INVALID_KEY)

    duplicates = checked.repeats + (len(checked.valid) - accepted)
    status, status_code = ingest.status_for(accepted, duplicates, len(checked.errors))
    result = CollectResult(
        status=status, request_id=request_id, received=received, accepted=accepted,
        duplicates=duplicates, rejected=len(checked.errors), errors=checked.errors,
    )
    logger.info("collect request_id=%s key=%s journey=%s received=%d accepted=%d duplicates=%d rejected=%d status=%d",
                request_id, fingerprint, grant.journey if grant else "-", received, accepted, duplicates,
                len(checked.errors), status_code)
    for outcome, count in (("accepted", accepted), ("duplicate", duplicates), ("rejected", len(checked.errors))):
        if count:
            metrics.COLLECTOR_EVENTS.inc(count, outcome=outcome)
    res = _result(result, status_code)
    if accepted > 0 and checked is not None and checked.valid:
        setattr(res, "_broadcast_events", [
            {
                "event_id": ev.event_id,
                "journey_id": ev.journey_id,
                "step_id": ev.step_id,
                "event_type": ev.event_type,
                "timestamp": ev.timestamp,
                "url": ev.url,
                "duration_ms": ev.duration_ms,
                "user_id": ev.user_id,
                "session_id": ev.session_id,
                "metadata": ev.metadata,
                "account_id": grant.account_id if grant else None,
            }
            for ev in checked.valid
        ])
    return res


def _ready(conn) -> None:
    conn.execute(text("SELECT 1 FROM live_events LIMIT 1"))
    conn.execute(text("SELECT 1 FROM api_keys LIMIT 1"))
    if CJI_ENV == "production":
        # Spec 15 (OD-167): in production the schema must be migrated to this release's version.
        from cji.migrations.runner import REQUIRED_SCHEMA_VERSION, TABLE

        version = conn.execute(text(f"SELECT coalesce(max(version), 0) FROM {TABLE}")).scalar()  # nosec B608 - constant table name
        if int(version or 0) < REQUIRED_SCHEMA_VERSION:
            raise ConfigError([f"database schema {version} is behind {REQUIRED_SCHEMA_VERSION}: run cji-db migrate up"])


def _not_ready(exc: Exception) -> JSONResponse:
    logger.warning("readiness check failed: %s sqlstate=%s", type(exc).__name__, _sqlstate(exc))
    return JSONResponse({"status": "not_ready"}, status_code=503)


# ─── ENDPOINTS ─────────────────────────────────────────────────────────────

@app.get("/health/live")
def health_live():
    """Liveness: the process answers. Never touches the database."""
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready():
    """Readiness: the database answers and both collector tables exist."""
    try:
        with engine.begin() as conn:
            _ready(conn)
    except (SQLAlchemyError, ConfigError) as exc:
        return _not_ready(exc)
    return {"status": "ready"}


@app.get("/health")
def health_check():
    """Compatibility: readiness plus the live_events row count."""
    try:
        with engine.begin() as conn:
            _ready(conn)
            count = conn.execute(text("SELECT COUNT(*) FROM live_events")).fetchone()[0]
    except (SQLAlchemyError, ConfigError) as exc:
        return _not_ready(exc)
    return {"status": "ok", "live_events_count": int(count)}

@app.get("/tracker.js")
def get_tracker():
    try:                                    # package data of cji.tracker (Spec 11, OD-99)
        body = (files("cji.tracker") / "tracker.js").read_bytes()
    except (FileNotFoundError, ModuleNotFoundError):
        raise HTTPException(status_code=404, detail="tracker.js not found on server") from None
    return Response(
        content=body,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=3600"},
    )

@app.post("/collect/batch")
async def collect_batch(request: Request):
    """
    1-100 tracker events. Envelope problems reject the whole request (400/401/413/415/422/429);
    events are then validated one by one and the valid ones stored (200 / 207 / 422; 503 on failure).
    """
    if not ingest.acceptable_content_type(request.headers.get("content-type")):
        return _rejected(415, "Send the batch as application/json (text/plain is accepted for sendBeacon).")
    body = await request.body()
    try:
        envelope = ingest.parse_envelope(body)
    except ingest.EnvelopeError as exc:
        return _rejected(exc.status_code, exc.detail)

    header_key = request.headers.get("x-cji-key")
    if header_key is not None and not secrets.compare_digest(header_key.encode("utf-8"),
                                                             envelope.api_key.encode("utf-8")):
        return _rejected(401, INVALID_KEY)

    fingerprint = key_fingerprint(envelope.api_key)
    for limiter, bucket in ((IP_LIMITER, _client(request)), (KEY_LIMITER, fingerprint)):
        wait = limiter.check(bucket)
        if wait is not None:
            logger.info("collect rate limited request_id=%s key=%s", current_request_id(), fingerprint)
            metrics.RATE_LIMITED.inc(service="cji-collector", limiter="address" if limiter is IP_LIMITER else "key")
            return _rejected(429, "Too many requests.", headers={"Retry-After": retry_after_header(wait)})

    response = await run_in_threadpool(_store_batch, envelope, fingerprint)
    broadcast_events = getattr(response, "_broadcast_events", None)
    if broadcast_events:
        BROADCASTER.publish(broadcast_events)
    return response


@app.get("/live/stream")
async def live_stream(
    request: Request,
    journey_id: str | None = Query(None, description="Optional journey filter"),
    event_type: str | None = Query(None, description="Optional event type filter"),
    account_id: str | None = Query(None, description="Optional tenant account ID filter"),
):
    """
    Server-Sent Events (SSE) live telemetry stream.
    Streams valid live events in real-time as they are committed to the collector.
    Dispatches keep-alive comment pings every 15s.
    """
    queue = BROADCASTER.subscribe()

    async def event_generator():
        try:
            # Initial handshake frame
            yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'journey_filter': journey_id or 'all'})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if journey_id and journey_id not in ("all", "*") and event.get("journey_id") != journey_id:
                        continue
                    if event_type and event.get("event_type") != event_type:
                        continue
                    if account_id and account_id not in ("all", "*") and event.get("account_id") != account_id:
                        continue
                    yield f"event: telemetry\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            BROADCASTER.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.get("/live/stats")
def live_stats(request: Request, minutes: int = Query(60, ge=1, le=43200),
               account_id: str | None = Query(None, description="Optional tenant account filter"),
               x_cji_admin_key: str | None = Header(None)):
    # Admin only (OD-44). minutes is validated (1 minute .. 30 days) and bound, never formatted into SQL (R-04).
    _require_admin(request, x_cji_admin_key)
    try:
        with engine.begin() as conn:
            stats = conn.execute(text("""
                SELECT step_id, COUNT(*) as ev_count
                FROM live_events
                WHERE timestamp >= current_timestamp - (:minutes * INTERVAL '1 minute')
                  AND (:account_id IS NULL OR account_id = :account_id)
                GROUP BY step_id
                ORDER BY ev_count DESC
            """), {"minutes": minutes, "account_id": account_id}).fetchall()
    except (SQLAlchemyError, ConfigError) as exc:
        logger.error("live stats failed: %s sqlstate=%s", type(exc).__name__, _sqlstate(exc))
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    return {"window": f"{minutes}m", "stats": [{"step": r[0], "count": r[1]} for r in stats]}

@app.post("/admin/api-keys")
def create_api_key(request: Request, data: AdminKeyCreate, x_cji_admin_key: str | None = Header(None)):
    # Disabled until a real admin key is configured; constant-time comparison (R-03).
    _require_admin(request, x_cji_admin_key)

    new_key = f"cji_live_{secrets.token_hex(16)}"
    
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO api_keys (api_key, journey_name, description, account_id) VALUES (:key, :journey, :desc, :account_id)"),
                {"key": new_key, "journey": data.journey_name, "desc": data.description, "account_id": data.account_id}
            )
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail="Database not configured") from exc
    except SQLAlchemyError as exc:
        logger.error("API key insert failed: %s sqlstate=%s", type(exc).__name__, _sqlstate(exc))
        raise HTTPException(status_code=500, detail="Database error") from exc
        
    security_event("collector.key.create", actor="admin", target=key_fingerprint(new_key), outcome="ok")
    return {"api_key": new_key, "journey_name": data.journey_name, "status": "active"}


class AdminKeyRevoke(BaseModel):
    api_key: str = Field(min_length=8, max_length=128)


@app.post("/admin/api-keys/revoke")
def revoke_api_key(request: Request, data: AdminKeyRevoke, x_cji_admin_key: str | None = Header(None)):
    """Deactivate a tracker key (Spec 15, OD-163). The key is logged and audited as its fingerprint only."""
    _require_admin(request, x_cji_admin_key)
    fingerprint = key_fingerprint(data.api_key)
    try:
        with engine.begin() as conn:
            changed = conn.execute(text("UPDATE api_keys SET is_active = false WHERE api_key = :key"),
                                   {"key": data.api_key}).rowcount
    except ConfigError as exc:
        raise HTTPException(status_code=503, detail="Database not configured") from exc
    except SQLAlchemyError as exc:
        logger.error("API key revoke failed: %s sqlstate=%s", type(exc).__name__, _sqlstate(exc))
        raise HTTPException(status_code=500, detail="Database error") from exc
    if not changed:
        security_event("collector.key.revoke", actor="admin", target=fingerprint, outcome="not_found")
        raise HTTPException(status_code=404, detail="Unknown API key")
    security_event("collector.key.revoke", actor="admin", target=fingerprint, outcome="ok")
    logger.info("tracker key %s revoked", fingerprint)
    return {"key": fingerprint, "status": "revoked"}


@app.get("/metrics")
def metrics_text(request: Request, x_cji_admin_key: str | None = Header(None)):
    """Process metrics in Prometheus text format (Spec 15, OD-160); admin key required."""
    _require_admin(request, x_cji_admin_key)
    return Response(metrics.REGISTRY.render(), media_type=metrics.CONTENT_TYPE)
