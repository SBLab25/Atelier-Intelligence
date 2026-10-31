"""
Output escaping, one helper per context (Spec 10, design §3). Pure module.

The renderer never places a value in a URL, an event handler, a style attribute, CSS or executable script,
so these are the only contexts that exist.
"""
from __future__ import annotations

import html
import json
from typing import Any

# Bidirectional embedding/override/isolate controls: kept in text, written as references in attributes.
_BIDI = tuple(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


def text(value: str) -> str:
    """Element text, SVG <text> and <title>."""
    return html.escape(value, quote=True)


def attr(value: str) -> str:
    """A double-quoted attribute value."""
    out = html.escape(value, quote=True)
    for ch in _BIDI:
        out = out.replace(ch, f"&#x{ord(ch):x};")
    return out


def json_block(obj: Any) -> str:
    """Body of a <script type="application/json"> data block: cannot close the tag or open a comment."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    return raw.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def css_class(value: str, allowed: tuple[str, ...]) -> str:
    """A class name from a fixed allow-list; anything else becomes `unknown`."""
    return value if value in allowed else "unknown"
