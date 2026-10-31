"""
Realtime event repository: PostgreSQL through SQLAlchemy (Spec 05, RP-02).

Reads the existing realtime model (tracking_events UNION ALL live_events); holds no
reference to demo storage (RP-09). Writes go to tracking_events in one transaction per batch,
idempotent by event_id (OD-29/OD-30/OD-31). No DDL: the schema is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast

import pandas as pd  # type: ignore[import-untyped]
from pandas.errors import DatabaseError as PandasDatabaseError  # type: ignore[import-untyped]
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from cji.domain.events import EVENT_RECORDS, EventRecord
from cji.domain.metrics import FunnelStep, StepMetrics

from .base import (
    LiveSnapshot,
    Mode,
    RepositoryError,
    TimeWindow,
    WriteResult,
    dedupe_batch,
    describe_failure,
    frame_rows,
)
from .queries import (
    LIVE_SNAPSHOT,
    POSTGRES,
    REQUIRED_TABLES,
    TABLES_PRESENT,
    TRACKING_EVENT_EXISTS,
    TRACKING_EVENT_INSERT,
    events_sql,
    funnel_sql,
    realtime_source,
    step_metrics_sql,
)

DESTINATION = "postgresql://tracking_events"


class PostgresEventRepository:
    mode: Mode = "realtime"
    data_source = "live_events"

    def __init__(self, url: str, *, engine_factory: Callable[..., Engine] = create_engine) -> None:
        self._url = url
        self._engine_factory = engine_factory
        self._engine: Engine | None = None

    # ── connection ──────────────────────────────────────────────────────────
    def _get_engine(self, operation: str) -> Engine:
        if self._engine is None:
            try:
                self._engine = self._engine_factory(self._url, pool_pre_ping=True)
            except (SQLAlchemyError, ValueError) as exc:
                raise RepositoryError(operation, describe_failure(exc)) from exc
        return self._engine

    def _read(self, operation: str, sql: str, params: dict[str, Any]) -> pd.DataFrame:
        try:
            with self._get_engine(operation).begin() as conn:
                return pd.read_sql(text(sql), conn, params=params)
        except (SQLAlchemyError, PandasDatabaseError) as exc:
            raise RepositoryError(operation, describe_failure(exc)) from exc

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    # ── reads ───────────────────────────────────────────────────────────────
    def health(self) -> None:
        try:
            with self._get_engine("health").begin() as conn:
                conn.execute(text("SELECT 1"))
                present = conn.execute(text(TABLES_PRESENT)).fetchone()
        except SQLAlchemyError as exc:
            raise RepositoryError("health", describe_failure(exc)) from exc
        missing = [t for t, ok in zip(REQUIRED_TABLES, present or (False, False), strict=True) if not ok]
        if missing:
            raise RepositoryError(
                "health",
                f"required table(s) missing: {', '.join(missing)}. Realtime queries read tracking_events "
                "UNION ALL live_events; live_events is created by the collector at startup and "
                "tracking_events by file ingestion.",
            )

    def window_fields(self, window: TimeWindow) -> tuple[int | None, int | None]:
        return None, window.realtime_minutes

    def step_metrics(self, journey_id: str, window: TimeWindow) -> list[StepMetrics]:
        params = {"journey_id": journey_id, "window": window.realtime_minutes}
        df = self._read("step_metrics", step_metrics_sql(POSTGRES, realtime_source(journey_id)), params)
        return cast(list[StepMetrics], frame_rows(df))

    def funnel(self, journey_id: str, steps: Sequence[str], window: TimeWindow) -> list[FunnelStep]:
        params = {"journey_id": journey_id, "window": window.realtime_minutes, "steps": list(steps)}
        df = self._read("funnel", funnel_sql(POSTGRES, realtime_source(journey_id)), params)
        return cast(list[FunnelStep], frame_rows(df))

    def events(
        self, journey_id: str, *, limit: int, step_id: str | None, event_type: str | None
    ) -> list[dict[str, Any]]:
        params = {"journey_id": journey_id, "step_id": step_id, "event_type": event_type, "limit": limit}
        df = self._read("events", events_sql(POSTGRES, realtime_source(journey_id)), params)
        return frame_rows(df, stringify_timestamp=True)

    def live_snapshot(self, minutes: int) -> LiveSnapshot:
        df = self._read("live_snapshot", LIVE_SNAPSHOT, {"minutes": minutes})
        steps = frame_rows(df)
        return LiveSnapshot(
            steps=steps,
            total_events=sum(int(s["event_count"]) for s in steps),
            snapshot_at=str(df["last_event_at"].max()) if not df.empty else None,
        )

    # ── writes ──────────────────────────────────────────────────────────────
    def append_events(self, records: Sequence[EventRecord]) -> WriteResult:
        try:
            EVENT_RECORDS.validate_python(list(records))
        except ValidationError as exc:
            raise RepositoryError("append_events", f"invalid event record: {exc.errors()[0]['msg']} "
                                  f"at {exc.errors()[0]['loc']}") from exc
        unique = dedupe_batch(records)
        written = 0
        try:
            with self._get_engine("append_events").begin() as conn:   # one transaction: all or nothing
                for record in unique:
                    written += self._insert_one(conn, record)
        except SQLAlchemyError as exc:
            message = describe_failure(exc)
            if "tracking_events" in message and "does not exist" in message:
                message = ("tracking_events does not exist. Create it by ingesting a file once, or with the "
                           "same columns as the stored event record; nothing was written.")
            raise RepositoryError("append_events", message) from exc
        return WriteResult(written, len(records) - written, DESTINATION)

    def _insert_one(self, conn: Connection, record: EventRecord) -> int:
        """Insert one record unless its event_id is already stored. Returns 1 if inserted."""
        if conn.execute(text(TRACKING_EVENT_EXISTS), {"event_id": record["event_id"]}).fetchone():
            return 0
        conn.execute(text(TRACKING_EVENT_INSERT), dict(record))
        return 1
