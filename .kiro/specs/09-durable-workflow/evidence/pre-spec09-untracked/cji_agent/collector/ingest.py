"""
Collector ingestion (Spec 07): envelope parsing, per-event validation, and the single write.

Pure functions except `store_events`, which runs one statement on the caller's connection:

    INSERT INTO live_events (...) VALUES (...), (...) ON CONFLICT (event_id) DO NOTHING RETURNING event_id

The caller owns the transaction (OD-41): nothing is reported as stored until it commits.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Column, MetaData, Table, Text
from sqlalchemy.dialects.postgresql import insert

from collector.models import CollectStatus, EventError
from domain.events import TrackerEvent, to_live_events_row
from domain.journeys import MAX_IDENTIFIER_LENGTH

MIN_KEY_LENGTH = 10
MAX_KEY_LENGTH = 256
MAX_EVENTS = 100
# application/json from fetch(); text/plain from navigator.sendBeacon() with a string body (OD-49).
ACCEPTED_CONTENT_TYPES: frozenset[str] = frozenset({"application/json", "text/plain"})

# SQL generation only; the table itself is created by collector.api._create_tables (unchanged DDL).
# Values are bound as text, as before Spec 07; PostgreSQL converts them to TIMESTAMP and JSONB.
LIVE_EVENTS = Table(
    "live_events",
    MetaData(),
    Column("timestamp", Text),
    Column("event_id", Text, primary_key=True),
    Column("session_id", Text),
    Column("user_id", Text),
    Column("journey_name", Text),
    Column("step_id", Text),
    Column("event_type", Text),
    Column("url", Text),
    Column("element_selectors", Text),
    Column("metadata", Text),
)


class EnvelopeError(Exception):
    """The request as a whole is unusable; no event is looked at."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class Envelope:
    api_key: str
    events: list[Any]


@dataclass(frozen=True)
class CheckedBatch:
    valid: list[TrackerEvent]       # unique by event_id, first occurrence kept
    errors: list[EventError]        # ordered by index
    repeats: int                    # valid events whose event_id appeared earlier in the batch


def acceptable_content_type(value: str | None) -> bool:
    media_type = (value or "").split(";", 1)[0].strip().lower()
    return media_type in ACCEPTED_CONTENT_TYPES


def parse_envelope(body: bytes) -> Envelope:
    """Parse `{"api_key": str, "events": [...]}`. Raises EnvelopeError (400 or 422)."""
    try:
        payload = json.loads(body)
    except (ValueError, RecursionError):
        raise EnvelopeError(400, "The request body is not valid JSON.") from None
    if not isinstance(payload, dict):
        raise EnvelopeError(422, "The body must be a JSON object with api_key and events.")
    api_key = payload.get("api_key")
    if not isinstance(api_key, str) or not MIN_KEY_LENGTH <= len(api_key) <= MAX_KEY_LENGTH:
        raise EnvelopeError(422, "api_key is missing or invalid.")
    events = payload.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise EnvelopeError(422, f"events must be a list of 1 to {MAX_EVENTS} events.")
    return Envelope(api_key=api_key, events=events)


def _fields(exc: ValidationError) -> list[str]:
    """Names of the failing fields, without the submitted values."""
    fields: list[str] = []
    for error in exc.errors(include_url=False, include_input=False, include_context=False):
        name = ".".join(str(part) for part in error["loc"])
        if name and name not in fields:
            fields.append(name)
    return fields


def _client_event_id(raw: Any) -> str | None:
    """The event's own id, for the error entry, when it is a plausible identifier."""
    if not isinstance(raw, dict):
        return None
    value = raw.get("event_id")
    if isinstance(value, str) and 8 <= len(value.strip()) <= MAX_IDENTIFIER_LENGTH and value.isprintable():
        return value.strip()
    return None


def validate_events(raw_events: list[Any], journey: str) -> CheckedBatch:
    """Validate each event on its own against the canonical contract and the key's journey."""
    valid: list[TrackerEvent] = []
    errors: list[EventError] = []
    seen: set[str] = set()
    repeats = 0
    for index, raw in enumerate(raw_events):
        try:
            event = TrackerEvent.model_validate(raw)
        except ValidationError as exc:
            fields = _fields(exc)
            event_id = None if "event_id" in fields else _client_event_id(raw)
            errors.append(EventError(index=index, event_id=event_id, reason="invalid", fields=fields))
            continue
        if event.journey_id != journey:
            errors.append(EventError(index=index, event_id=event.event_id, reason="journey_not_authorized",
                                     fields=["journey_id"]))
            continue
        if event.event_id in seen:
            repeats += 1
            continue
        seen.add(event.event_id)
        valid.append(event)
    return CheckedBatch(valid=valid, errors=errors, repeats=repeats)


def store_events(conn: Any, events: list[TrackerEvent]) -> int:
    """Insert the events in one statement; return how many were new (the rest already existed)."""
    if not events:
        return 0
    statement = (
        insert(LIVE_EVENTS)
        .values([to_live_events_row(event) for event in events])
        .on_conflict_do_nothing(index_elements=["event_id"])
        .returning(LIVE_EVENTS.c.event_id)
    )
    return len(conn.execute(statement).fetchall())


def status_for(accepted: int, duplicates: int, rejected: int) -> tuple[CollectStatus, int]:
    """Response status and HTTP code (OD-43): 200 nothing rejected, 207 some, 422 all."""
    if rejected == 0:
        return "stored", 200
    if accepted + duplicates > 0:
        return "partial", 207
    return "rejected", 422
