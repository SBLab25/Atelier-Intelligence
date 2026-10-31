"""Journey definitions (Spec 12, OD-111): today the configured journey; a list so more can be added."""
from __future__ import annotations

from cji.domain.journeys import JourneyDefinition, journey_from_config
from cji.settings import Settings


def configured_steps() -> list[str]:
    from cji.config import JOURNEY_CONFIG

    return list(JOURNEY_CONFIG["steps"])


def list_journeys(settings: Settings) -> list[JourneyDefinition]:
    """All configured journeys, ordered by name."""
    return [journey_from_config({"name": settings.app.journey_name, "steps": configured_steps()})]


def get_journey(settings: Settings, journey_id: str) -> JourneyDefinition | None:
    return next((j for j in list_journeys(settings) if j.name == journey_id), None)
