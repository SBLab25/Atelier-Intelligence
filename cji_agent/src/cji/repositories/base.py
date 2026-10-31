"""
Event repository interface (Spec 05, RP-01).

One boundary for every read and write of journey events. Implementations:
DuckDbParquetRepository (demo) and PostgresEventRepository (realtime).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import pandas as pd  # type: ignore[import-untyped]

from cji.domain.events import EventRecord
from cji.domain.metrics import FunnelStep, StepMetrics

Mode = Literal["demo", "realtime"]

EVENT_COLUMNS: tuple[str, ...] = (
    "event_id", "user_id", "session_id", "journey_id", "step_id",
    "event_type", "timestamp", "duration_ms", "url", "metadata",
)
MISSING_PARQUET_MESSAGE = "events.parquet not found — run --generate-data"
DEMO_LIVE_SNAPSHOT_MESSAGE = "get_live_snapshot is only available in realtime mode"

_URL_CREDENTIALS = re.compile(r"(\w+://)([^:/@\s]+):([^@\s]*)@")


class RepositoryError(RuntimeError):
    """A storage operation failed. The message never contains credentials."""

    def __init__(self, operation: str, message: str) -> None:
        self.operation = operation
        self.message = _URL_CREDENTIALS.sub(r"\1\2:***@", message)
        super().__init__(self.message)


class NotSupported(RepositoryError):
    """The operation does not exist for this storage (e.g. live snapshot in demo mode)."""


def describe_failure(exc: BaseException) -> str:
    """First line of the underlying driver error, without the SQL text or bound parameters."""
    current: BaseException = exc
    while current.__cause__ is not None:          # pandas DatabaseError -> SQLAlchemy -> driver
        current = current.__cause__
    original = getattr(current, "orig", None)
    text = str(original if original is not None else current).strip()
    return text.splitlines()[0] if text else type(current).__name__


@dataclass(frozen=True)
class TimeWindow:
    """Analysis window as requested; each repository applies its own (existing) semantics."""

    days_back: int = 30
    minutes_back: int = 0

    @property
    def realtime_minutes(self) -> int:
        if self.minutes_back > 0:
            return self.minutes_back
        if self.days_back > 0:
            return self.days_back * 1440
        return 60


@dataclass(frozen=True)
class WriteResult:
    written: int
    duplicates: int
    destination: str


@dataclass(frozen=True)
class LiveSnapshot:
    steps: list[dict[str, Any]]
    total_events: int
    snapshot_at: str | None


class EventRepository(Protocol):
    mode: Mode
    data_source: str

    def health(self) -> None:
        """Raise RepositoryError unless the store is ready to answer queries."""

    def window_fields(self, window: TimeWindow) -> tuple[int | None, int | None]:
        """(window_days, window_minutes) as reported by get_step_metrics."""

    def step_metrics(self, journey_id: str, window: TimeWindow) -> list[StepMetrics]: ...

    def funnel(self, journey_id: str, steps: Sequence[str], window: TimeWindow) -> list[FunnelStep]: ...

    def events(
        self, journey_id: str, *, limit: int, step_id: str | None, event_type: str | None
    ) -> list[dict[str, Any]]: ...

    def events_page(
        self, journey_id: str, *, limit: int, after: tuple[str, str] | None, step_id: str | None,
        event_type: str | None,
    ) -> list[dict[str, Any]]:
        """Events newest first (timestamp, then event_id, descending), strictly after the `after` position.
        Rows: event_id, user_id, session_id, step_id, event_type, timestamp (text, as stored), duration_ms, url."""

    def live_snapshot(self, minutes: int) -> LiveSnapshot: ...

    def append_events(self, records: Sequence[EventRecord]) -> WriteResult: ...

    def close(self) -> None: ...


def page_params(journey_id: str, limit: int, after: tuple[str, str] | None, step_id: str | None,
                event_type: str | None) -> dict[str, Any]:
    """Bound parameters of the events page query."""
    return {"journey_id": journey_id, "step_id": step_id, "event_type": event_type, "limit": limit,
            "after_ts": after[0] if after else None, "after_id": after[1] if after else None}


def page_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame → JSON-safe dicts with missing values as None (event pages, Spec 12)."""
    rows: list[dict[str, Any]] = json.loads(df.to_json(orient="records"))
    return rows


def frame_rows(df: pd.DataFrame, *, stringify_timestamp: bool = False) -> list[dict[str, Any]]:
    """DataFrame → JSON-safe dicts, exactly as the journey-data tools always did (fillna(0.0), to_json)."""
    df = df.fillna(0.0)
    if stringify_timestamp and "timestamp" in df.columns:
        df["timestamp"] = df["timestamp"].astype(str)
    rows: list[dict[str, Any]] = json.loads(df.to_json(orient="records"))
    return rows


def dedupe_batch(records: Sequence[EventRecord]) -> list[EventRecord]:
    """Keep the first record for each event_id."""
    seen: set[str] = set()
    unique: list[EventRecord] = []
    for record in records:
        if record["event_id"] not in seen:
            seen.add(record["event_id"])
            unique.append(record)
    return unique
