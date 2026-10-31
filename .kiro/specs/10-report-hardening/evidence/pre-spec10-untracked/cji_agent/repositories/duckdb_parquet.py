"""
Demo event repository: in-memory DuckDB over the configured Parquet file (Spec 05, RP-02).

Never creates a database engine (RP-09). Writes are atomic file replacements, idempotent
by event_id (OD-30/OD-31).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import duckdb
import pandas as pd  # type: ignore[import-untyped]
from pydantic import ValidationError

from domain.events import EVENT_RECORDS, EventRecord
from domain.metrics import FunnelStep, StepMetrics

from .base import (
    DEMO_LIVE_SNAPSHOT_MESSAGE,
    EVENT_COLUMNS,
    MISSING_PARQUET_MESSAGE,
    LiveSnapshot,
    Mode,
    NotSupported,
    RepositoryError,
    TimeWindow,
    WriteResult,
    dedupe_batch,
    describe_failure,
    frame_rows,
)
from .queries import DEMO_SOURCE, DUCKDB, events_sql, funnel_sql, step_metrics_sql


class DuckDbParquetRepository:
    mode: Mode = "demo"
    data_source = "parquet"

    def __init__(self, parquet_path: Path) -> None:
        self.parquet_path = Path(parquet_path)
        self._conn: duckdb.DuckDBPyConnection | None = None

    # ── connection ──────────────────────────────────────────────────────────
    def _connection(self, operation: str) -> duckdb.DuckDBPyConnection:
        if self._conn is not None:
            return self._conn
        if not self.parquet_path.exists():
            raise RepositoryError(operation, MISSING_PARQUET_MESSAGE)
        try:
            conn = duckdb.connect(":memory:")
            conn.execute("PRAGMA threads=1")
            # DuckDB cannot bind parameters inside CREATE VIEW. The path comes from
            # settings (not user input) and is quote-escaped so it cannot end the literal.
            path = self.parquet_path.resolve().as_posix().replace("'", "''")
            conn.execute(
                "CREATE OR REPLACE TEMP VIEW events AS "
                "SELECT * FROM read_parquet('" + path + "')"  # nosec B608 - escaped settings path
            )
        except duckdb.Error as exc:
            raise RepositoryError(operation, describe_failure(exc)) from exc
        self._conn = conn
        return conn

    def _query(self, operation: str, sql: str, params: dict[str, Any]) -> pd.DataFrame:
        conn = self._connection(operation)
        try:
            return conn.execute(sql, params).df()
        except duckdb.Error as exc:
            raise RepositoryError(operation, describe_failure(exc)) from exc

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── reads ───────────────────────────────────────────────────────────────
    def health(self) -> None:
        if not self.parquet_path.exists():
            raise RepositoryError("health", MISSING_PARQUET_MESSAGE)
        self._query("health", "SELECT COUNT(*) FROM events", {})

    def window_fields(self, window: TimeWindow) -> tuple[int | None, int | None]:
        return window.days_back, None          # demo applies no time filter (F-10)

    def step_metrics(self, journey_id: str, window: TimeWindow) -> list[StepMetrics]:
        df = self._query("step_metrics", step_metrics_sql(DUCKDB, DEMO_SOURCE), {"journey_id": journey_id})
        return cast(list[StepMetrics], frame_rows(df))

    def funnel(self, journey_id: str, steps: Sequence[str], window: TimeWindow) -> list[FunnelStep]:
        params = {"journey_id": journey_id, "steps": list(steps)}
        df = self._query("funnel", funnel_sql(DUCKDB, DEMO_SOURCE), params)
        return cast(list[FunnelStep], frame_rows(df))

    def events(
        self, journey_id: str, *, limit: int, step_id: str | None, event_type: str | None
    ) -> list[dict[str, Any]]:
        params = {"journey_id": journey_id, "step_id": step_id, "event_type": event_type, "limit": limit}
        df = self._query("events", events_sql(DUCKDB, DEMO_SOURCE), params)
        return frame_rows(df, stringify_timestamp=True)

    def live_snapshot(self, minutes: int) -> LiveSnapshot:
        raise NotSupported("live_snapshot", DEMO_LIVE_SNAPSHOT_MESSAGE)

    # ── writes ──────────────────────────────────────────────────────────────
    def append_events(self, records: Sequence[EventRecord]) -> WriteResult:
        try:
            EVENT_RECORDS.validate_python(list(records))
        except ValidationError as exc:
            raise RepositoryError("append_events", f"invalid event record: {exc.errors()[0]['msg']} "
                                  f"at {exc.errors()[0]['loc']}") from exc
        destination = str(self.parquet_path)
        unique = dedupe_batch(records)
        batch_duplicates = len(records) - len(unique)
        if not unique:
            return WriteResult(0, batch_duplicates, destination)
        try:
            new = pd.DataFrame(unique, columns=list(EVENT_COLUMNS))
            new["timestamp"] = pd.to_datetime(new["timestamp"], utc=True, format="ISO8601")
            new["duration_ms"] = new["duration_ms"].astype("int64")
            if self.parquet_path.exists():
                existing = pd.read_parquet(self.parquet_path)
                new = new[~new["event_id"].isin(existing["event_id"])]
                if not new.empty:
                    new = new.astype({c: existing[c].dtype for c in new.columns if c in existing.columns})
                merged = pd.concat([existing, new], ignore_index=True)
            else:
                merged = new
            written = len(new)
            if written:
                self._replace_file(merged)
        except RepositoryError:
            raise
        except Exception as exc:  # broad-except: repository boundary: file untouched, re-raised as RepositoryError
            raise RepositoryError("append_events", describe_failure(exc)) from exc
        return WriteResult(written, len(unique) - written + batch_duplicates, destination)

    def _replace_file(self, frame: pd.DataFrame) -> None:
        """Write to a temporary file in the same directory, then rename over the original."""
        self.parquet_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.parquet_path.with_name(f".{self.parquet_path.name}.{os.getpid()}.tmp")
        try:
            frame.to_parquet(tmp, index=False)
            os.replace(tmp, self.parquet_path)
        finally:
            if tmp.exists():
                tmp.unlink()
