"""
CJI Collector - models
======================
The browser event contracts are defined once in domain/events.py (Spec 03) and
re-exported here so existing imports keep working:

    ALLOWED_EVENT_TYPES, TrackerEvent, EventBatch

The response models below are the collector's response contract (Spec 07, OD-43 / OD-48).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cji.domain.events import ALLOWED_EVENT_TYPES, EventBatch, TrackerEvent

__all__ = [
    "ALLOWED_EVENT_TYPES",
    "CollectResult",
    "EventBatch",
    "EventError",
    "HealthStatus",
    "TrackerEvent",
]

CollectStatus = Literal["stored", "partial", "rejected", "failed"]


class EventError(BaseModel):
    """One rejected event. Submitted values are never echoed; only field names."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(..., ge=0, description="Position of the event in the request")
    event_id: str | None = Field(default=None, description="The event's id, when it was readable")
    reason: Literal["invalid", "journey_not_authorized"]
    fields: list[str] = Field(default_factory=list, description="Fields that failed validation")


class CollectResult(BaseModel):
    """
    Response for POST /collect/batch.

    accepted   events stored by this request
    duplicates events already stored (retries) or repeated inside the request
    rejected   events refused; see errors
    status     stored (nothing rejected, HTTP 200), partial (207), rejected (422),
               failed (503: nothing stored, retry with the same event_id values)
    """

    status: CollectStatus
    request_id: str
    received: int = 0
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    errors: list[EventError] = Field(default_factory=list)
    retryable: bool | None = None
    detail: str | None = None


class HealthStatus(BaseModel):
    """Response for GET /health/live, /health/ready and /health."""

    status: Literal["ok", "ready", "not_ready"]
    live_events_count: int | None = None
