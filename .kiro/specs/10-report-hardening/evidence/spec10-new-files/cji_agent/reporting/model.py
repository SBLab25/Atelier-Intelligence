"""
Report input contract (Spec 10, OD-83 to OD-85, OD-87). Pure module: standard library and pydantic.

All values are untrusted. Strings are cleaned (control characters, lone surrogates, newlines) and cut to the
limits below with a visible ellipsis; every cut is recorded in `truncated`. Wrong types and missing required
fields are errors (`ReportInputError`), never coerced.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)

ELLIPSIS = "…"
MODES = ("demo", "realtime")
MAX_USERS = 10**9

# Character limits per text field, and item limits per list (OD-84).
TEXT_LIMITS = {"journey_name": 128, "narrative": 4000, "narrative_model": 100, "run_id": 128, "mode": 32}
LIST_LIMITS = {"insights": 50, "funnel_data": 100, "friction_scores": 100}
ITEM_TEXT_LIMITS = {
    "insights": {"step_id": 128, "title": 200, "root_cause": 1000, "suggested_fix": 1000},
    "funnel_data": {"step_id": 128},
    "friction_scores": {"step_id": 128},
}
MAX_ERROR_FIELDS = 5
_GENERATED_AT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def clean_text(value: str) -> str:
    """Normalise newlines, drop control characters (keep tab and newline), replace lone surrogates."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for ch in value:
        code = ord(ch)
        if ch in "\t\n":
            out.append(ch)
        elif code < 0x20 or 0x7F <= code <= 0x9F:
            continue
        elif 0xD800 <= code <= 0xDFFF:
            out.append("\ufffd")
        else:
            out.append(ch)
    return "".join(out)


def _required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("must not be empty")
    return value


RequiredText = Annotated[StrictStr, AfterValidator(_required)]


class ReportInsight(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    step_id: RequiredText
    title: RequiredText
    priority: Annotated[StrictInt, Field(ge=1, le=5)]
    root_cause: StrictStr = ""
    suggested_fix: StrictStr = ""


class FunnelBar(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    step_id: RequiredText
    users: Annotated[StrictInt, Field(ge=0, le=MAX_USERS)]
    drop_off_pct: Annotated[float, Field(strict=True, allow_inf_nan=False)] | None = None


class FrictionRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    step_id: RequiredText
    score: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]
    is_critical: StrictBool = False


class ReportInput(BaseModel):
    """Everything a report is rendered from. Same instance -> same HTML (OD-87)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    journey_name: RequiredText
    mode: StrictStr
    narrative: StrictStr = ""
    insights: list[ReportInsight] = []
    funnel_data: list[FunnelBar] = []
    friction_scores: list[FrictionRow] = []
    run_id: StrictStr = ""
    generated_at: StrictStr = ""
    narrative_source: Literal["llm", "fallback", "unknown"] = "unknown"
    narrative_model: StrictStr = ""
    # Set by the validator, not by callers: field path -> original length (text) or items left out (lists),
    # and the number of items received per list.
    truncated: dict[str, int] = {}
    received: dict[str, int] = {}

    @field_validator("generated_at")
    @classmethod
    def _utc_iso(cls, value: str) -> str:
        if value and not _GENERATED_AT.fullmatch(value):
            raise ValueError("must be UTC ISO 8601 (YYYY-MM-DDTHH:MM:SSZ) or empty")
        return value

    @model_validator(mode="before")
    @classmethod
    def _clean_and_cut(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        truncated: dict[str, int] = {}
        received: dict[str, int] = {}

        def cut(path: str, value: Any, limit: int) -> Any:
            if not isinstance(value, str):
                return value
            value = clean_text(value)
            if len(value) > limit:
                truncated[path] = len(value)
                value = value[: limit - 1] + ELLIPSIS
            return value

        for key, limit in TEXT_LIMITS.items():
            if key in data:
                data[key] = cut(key, data[key], limit)
        for key, limit in LIST_LIMITS.items():
            items = data.get(key)
            if not isinstance(items, list):
                continue
            received[key] = len(items)
            if len(items) > limit:
                truncated[key] = len(items) - limit
                items = items[:limit]
            fields = ITEM_TEXT_LIMITS[key]
            data[key] = [
                {k: cut(f"{key}.{i}.{k}", v, fields[k]) if k in fields else v for k, v in item.items()}
                if isinstance(item, dict) else item
                for i, item in enumerate(items)
            ]
        data["truncated"] = truncated
        data["received"] = received
        return data

    @property
    def shown_mode(self) -> str:
        return self.mode if self.mode in MODES else "unknown"

    def input_sha256(self) -> str:
        """SHA-256 of the cleaned input (canonical JSON), recorded in the report (OD-88)."""
        payload = self.model_dump(mode="json", exclude={"truncated", "received"})
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("ascii")).hexdigest()


class ReportInputError(ValueError):
    """The input does not satisfy the report contract. The message names fields, never values."""

    def __init__(self, fields: list[str]) -> None:
        shown = fields[:MAX_ERROR_FIELDS]
        more = f" (+{len(fields) - len(shown)} more)" if len(fields) > len(shown) else ""
        super().__init__(f"invalid report input: {', '.join(shown)}{more}")
        self.fields = fields


def parse_input(data: dict[str, Any]) -> ReportInput:
    try:
        return ReportInput.model_validate(data)
    except ValidationError as exc:
        fields: list[str] = []
        for err in exc.errors():
            path = ".".join(str(p) for p in err["loc"]) or "input"
            if path not in fields:
                fields.append(path)
        raise ReportInputError(fields) from None
