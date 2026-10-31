"""Typed requests, results and run context for the gateways (Spec 08, OD-60)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

Outcome = Literal["ok", "fallback", "error", "cancelled"]
CORRELATION_PATTERN = r"^[A-Za-z0-9._:-]{1,64}$"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Usage(_Frozen):
    input_tokens: int = 0
    output_tokens: int = 0


class RunBudget(_Frozen):
    """What a run may still spend. `cost_left_usd=None` means no cost cap."""

    calls_left: int = Field(..., ge=0)
    tokens_left: int = Field(..., ge=0)
    cost_left_usd: float | None = Field(default=None, ge=0)


class RunContext(BaseModel):
    """Travels with every call of a run: correlation id, calling worker, remaining budget."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    correlation_id: str = Field(..., pattern=CORRELATION_PATTERN)
    worker: str = Field(default="-", max_length=64)
    budget: RunBudget | None = None

    @classmethod
    def from_arg(cls, value: Any, fallback_correlation_id: str) -> RunContext:
        """Parse a `run_context` tool argument; anything unusable becomes a fresh context (never an error)."""
        if isinstance(value, dict):
            try:
                return cls.model_validate(value)
            except ValidationError:
                # A malformed context must not stop the tool; the call still gets an id and is audited.
                return cls(correlation_id=fallback_correlation_id)
        return cls(correlation_id=fallback_correlation_id)


class LLMRequest(_Frozen):
    purpose: str = Field(..., min_length=1, max_length=64)
    system: str
    user: str
    response_format: Literal["json", "text"] = "text"
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)

    @property
    def prompt_chars(self) -> int:
        return len(self.system) + len(self.user)


class LLMCallInfo(_Frozen):
    """Metadata about one LLM call: returned to workers, written to audit. Contains no payload."""

    call_id: str
    provider: str
    model: str
    outcome: Outcome
    code: str | None = None
    attempts: int = 0
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class LLMResult(_Frozen):
    text: str
    data: dict[str, Any] | None = None
    info: LLMCallInfo
