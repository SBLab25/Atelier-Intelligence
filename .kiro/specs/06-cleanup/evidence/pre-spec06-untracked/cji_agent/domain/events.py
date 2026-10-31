"""
Event contracts (Spec 03, RC-01..RC-04).

The only definition of:
  - the event taxonomy (ALLOWED_EVENT_TYPES),
  - URL sanitising,
  - the browser event (TrackerEvent) and batch (EventBatch) accepted by the collector,
  - the stored event record (EventRecord) used by Parquet, DuckDB, file ingestion and state.

Pure module: standard library and pydantic only.
"""
import json
from datetime import datetime
from typing import Annotated, Any, Literal, cast, get_args
from urllib.parse import urlparse

from pydantic import (
    AfterValidator,
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
)
from typing_extensions import TypedDict

from .journeys import (
    MAX_IDENTIFIER_LENGTH,
    Identifier,
    JourneyId,
    StepId,
    _no_control_characters,
)

# ── Taxonomy ──────────────────────────────────────────────────────────────────
EventType = Literal[
    "page_view",
    "click",
    "form_submit",
    "error",
    "rage_click",
    "abandon",
    "step_complete",
    "identify",
]
ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))


# ── Shared field rules ────────────────────────────────────────────────────────
def sanitise_url(url: str) -> str:
    """Strip query string and fragment (PII prevention). Unparseable input becomes ''."""
    if not url:
        return url
    try:
        sanitised = urlparse(url)._replace(query="", fragment="").geturl()
    except ValueError:
        return ""
    return sanitised.rstrip("?").rstrip("#")


def _iso_timestamp(value: str) -> str:
    """Accept any ISO-8601 datetime string (a trailing Z is allowed); keep the original text."""
    text = value.strip()
    try:
        datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text)
    except ValueError:
        raise ValueError("must be an ISO-8601 datetime") from None
    return value


def _json_text(value: str) -> str:
    try:
        json.loads(value)
    except ValueError:
        raise ValueError("must be a JSON string") from None
    return value


# Tracker-generated ids are UUIDs; the minimum lengths match the collector's earlier rules.
EventId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=8, max_length=MAX_IDENTIFIER_LENGTH),
    AfterValidator(_no_control_characters),
]
ClientId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=4, max_length=MAX_IDENTIFIER_LENGTH),
    AfterValidator(_no_control_characters),
]
IsoTimestamp = Annotated[str, AfterValidator(_iso_timestamp)]
DurationMs = Annotated[int, Field(ge=0)]
JsonText = Annotated[str, AfterValidator(_json_text)]


# ── Browser event (collector input) ───────────────────────────────────────────
class TrackerEvent(BaseModel):
    """
    One browser event from tracker.js.

    Accepts the tracker wire format (journey_name, element_selectors, no duration_ms)
    and the documented format (journey_id). The canonical field is journey_id.
    Unknown fields are ignored. URLs lose their query string and fragment.
    """

    model_config = ConfigDict(extra="ignore")

    event_id: EventId = Field(..., description="Unique event identifier")
    user_id: ClientId = Field(..., description="Anonymous user UUID")
    session_id: ClientId = Field(..., description="Per-tab session UUID")
    journey_id: JourneyId = Field(
        ...,
        validation_alias=AliasChoices("journey_id", "journey_name"),
        description="Journey being tracked (wire name: journey_name)",
    )
    step_id: StepId = Field(..., description="Step within the journey")
    event_type: str = Field(..., description="Must be in ALLOWED_EVENT_TYPES")
    timestamp: IsoTimestamp = Field(..., description="ISO-8601 UTC timestamp")
    duration_ms: DurationMs = Field(default=0, description="Event duration in milliseconds")
    url: str = Field(default="", description="Page URL without query string or fragment")
    element_selectors: str | None = Field(default=None, description="CSS selector of the target")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Event-specific data")

    @field_validator("event_type")
    @classmethod
    def _known_event_type(cls, v: str) -> str:
        if v not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"Unknown event_type '{v}'. Allowed: {sorted(ALLOWED_EVENT_TYPES)}")
        return v

    @field_validator("url")
    @classmethod
    def _sanitise_url(cls, v: str) -> str:
        return sanitise_url(v)

    @field_validator("metadata", mode="before")
    @classmethod
    def _coerce_metadata(cls, v: Any) -> dict[str, Any]:
        """Accept a dict or a JSON object string; anything else becomes {}."""
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
            except ValueError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}


class EventBatch(BaseModel):
    """One POST /collect/batch request: an API key and 1-100 events."""

    api_key: str = Field(..., min_length=10, description="CJI API key")
    events: list[TrackerEvent] = Field(..., min_length=1, max_length=100, description="1-100 tracker events")

    @property
    def accepted_events_count(self) -> int:
        return len(self.events)


# ── Stored event record ───────────────────────────────────────────────────────
class EventRecord(TypedDict):
    """A stored event (Parquet / DuckDB / file ingestion). metadata is a JSON string."""

    event_id: Identifier
    user_id: Identifier
    session_id: Identifier
    journey_id: JourneyId
    step_id: StepId
    event_type: EventType
    timestamp: IsoTimestamp
    duration_ms: DurationMs
    url: str
    metadata: JsonText


EVENT_RECORD: TypeAdapter[EventRecord] = TypeAdapter(EventRecord)
EVENT_RECORDS: TypeAdapter[list[EventRecord]] = TypeAdapter(list[EventRecord])


def to_record(event: TrackerEvent) -> EventRecord:
    """Browser event → stored event record."""
    return EventRecord(
        event_id=event.event_id,
        user_id=event.user_id,
        session_id=event.session_id,
        journey_id=event.journey_id,
        step_id=event.step_id,
        event_type=cast(EventType, event.event_type),  # checked by TrackerEvent
        timestamp=event.timestamp,
        duration_ms=event.duration_ms,
        url=event.url,
        metadata=json.dumps(event.metadata),
    )


def to_live_events_row(event: TrackerEvent) -> dict[str, Any]:
    """
    Browser event → `live_events` row (bind parameters).

    The table keeps its existing layout: the journey column is `journey_name` and
    metadata is JSON text for the JSONB column. This is the only conversion.
    """
    return {
        "timestamp": event.timestamp,
        "event_id": event.event_id,
        "session_id": event.session_id,
        "user_id": event.user_id,
        "journey_name": event.journey_id,
        "step_id": event.step_id,
        "event_type": event.event_type,
        "url": event.url,
        "element_selectors": event.element_selectors,
        "metadata": json.dumps(event.metadata),
    }
