"""Spec 07 T3: per-event size limits in TrackerEvent (OD-45). Exact single-match replacements."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[5]
path = ROOT / "cji_agent" / "domain" / "events.py"
text = path.read_text(encoding="utf-8")

PAIRS = [
    ("ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))\n",
     "ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(get_args(EventType))\n"
     "\n"
     "# Per-event size limits for browser events (Spec 07, OD-45).\n"
     "MAX_URL_LENGTH = 2048                 # after the query string and fragment are removed\n"
     "MAX_SELECTOR_LENGTH = 512\n"
     "MAX_METADATA_BYTES = 8192             # compact JSON, UTF-8\n"),
    ('    element_selectors: str | None = Field(default=None, description="CSS selector of the target")\n',
     '    element_selectors: str | None = Field(\n'
     '        default=None, max_length=MAX_SELECTOR_LENGTH, description="CSS selector of the target"\n'
     '    )\n'),
    ("    def _sanitise_url(cls, v: str) -> str:\n        return sanitise_url(v)\n",
     "    def _sanitise_url(cls, v: str) -> str:\n"
     "        clean = sanitise_url(v)\n"
     "        if len(clean) > MAX_URL_LENGTH:\n"
     "            raise ValueError(f\"must be at most {MAX_URL_LENGTH} characters without query string\")\n"
     "        return clean\n"),
    ("            return parsed if isinstance(parsed, dict) else {}\n        return {}\n",
     "            return parsed if isinstance(parsed, dict) else {}\n        return {}\n"
     "\n"
     "    @field_validator(\"metadata\")\n"
     "    @classmethod\n"
     "    def _metadata_size(cls, v: dict[str, Any]) -> dict[str, Any]:\n"
     "        size = len(json.dumps(v, separators=(\",\", \":\"), ensure_ascii=False, default=str).encode(\"utf-8\"))\n"
     "        if size > MAX_METADATA_BYTES:\n"
     "            raise ValueError(f\"must be at most {MAX_METADATA_BYTES} bytes as JSON\")\n"
     "        return v\n"),
]
for old, new in PAIRS:
    n = text.count(old)
    assert n == 1, f"expected 1 match, found {n}: {old[:60]!r}"
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
print("edited domain/events.py")
