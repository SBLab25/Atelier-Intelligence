"""
Journey and step identifiers, and the journey definition (Spec 03, RC-06).

Pure module: standard library and pydantic only.
"""
from collections.abc import Mapping
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

MAX_IDENTIFIER_LENGTH = 128


def _no_control_characters(value: str) -> str:
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("must not contain control characters")
    return value


# Non-empty after trimming, at most 128 characters, no control characters.
Identifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_IDENTIFIER_LENGTH),
    AfterValidator(_no_control_characters),
]
JourneyId = Identifier
StepId = Identifier


class JourneyDefinition(BaseModel):
    """An ordered, duplicate-free list of steps belonging to one journey."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: JourneyId
    steps: tuple[StepId, ...] = Field(min_length=1)

    @field_validator("steps")
    @classmethod
    def _steps_are_unique(cls, steps: tuple[str, ...]) -> tuple[str, ...]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for step in steps:
            (duplicates if step in seen else seen).add(step)
        if duplicates:
            raise ValueError(f"duplicate step ids: {sorted(duplicates)}")
        return steps


def journey_from_config(config: Mapping[str, Any]) -> JourneyDefinition:
    """Validate a JOURNEY_CONFIG-shaped mapping ({"name": str, "steps": [str, ...]})."""
    return JourneyDefinition.model_validate(
        {"name": config.get("name"), "steps": list(config.get("steps") or [])}
    )
