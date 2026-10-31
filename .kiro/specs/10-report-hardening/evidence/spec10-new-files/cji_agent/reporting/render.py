"""
Report renderer (Spec 10, design §4): `render(ReportInput) -> str`. Pure and deterministic: no clock,
environment or randomness, and every collection it walks is an ordered list.

The page is self-contained: one style block whose hash is the only style source the CSP allows, an inline SVG
chart, no executable script, and a JSON data block with the provenance (schema cji-report/1).
"""
from __future__ import annotations

import base64
import hashlib

from .escape import attr, css_class, json_block, text
from .model import LIST_LIMITS, MODES, TEXT_LIMITS, ReportInput

SCHEMA = "cji-report/1"
RENDERER = "cji-report-renderer/1"

STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 0 auto; padding: 2rem; }
h1, h2, h3 { color: #2c3e50; }
.header { border-bottom: 2px solid #eee; padding-bottom: 1rem; margin-bottom: 2rem; }
.badge { display: inline-block; padding: 0.25em 0.5em; font-size: 0.8em; font-weight: bold; line-height: 1; text-align: center; white-space: nowrap; vertical-align: baseline; border-radius: 0.25rem; background-color: #6c757d; color: #fff; }
.badge.critical { background-color: #dc3545; }
.badge.demo { background-color: #17a2b8; }
.badge.realtime { background-color: #28a745; }
.narrative { background: #f8f9fa; padding: 1.5rem; border-radius: 8px; border-left: 4px solid #007bff; margin-bottom: 2rem; white-space: pre-wrap; overflow-wrap: anywhere; }
.note { color: #6c757d; font-size: 0.9em; font-style: italic; }
table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; }
table, th, td { border: 1px solid #ddd; }
th, td { padding: 12px; text-align: left; overflow-wrap: anywhere; }
th { background-color: #f2f2f2; }
.chart-container { width: 100%; max-width: 800px; margin: 2rem auto; }
.chart text { font-size: 13px; fill: #333; }
.insight-card { border: 1px solid #ddd; padding: 1.5rem; border-radius: 8px; margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05); overflow-wrap: anywhere; }
.insight-card h4 { margin-top: 0; color: #d9534f; }
.details { border-top: 2px solid #eee; margin-top: 2rem; padding-top: 1rem; font-size: 0.9em; color: #555; }
.details dt { font-weight: bold; }
.details dd { margin: 0 0 0.5rem 0; overflow-wrap: anywhere; }
"""

STYLE_HASH = base64.b64encode(hashlib.sha256(STYLE.encode("utf-8")).digest()).decode("ascii")
CSP = (f"default-src 'none'; style-src 'sha256-{STYLE_HASH}'; img-src 'none'; script-src 'none'; "
       "base-uri 'none'; form-action 'none'")

# Chart geometry (viewBox units).
# The width leaves room for the value label after the longest bar.
_WIDTH, _LABEL_X, _BAR_X, _BAR_MAX, _ROW, _BAR_H, _TOP = 860, 170, 180, 600, 36, 28, 12
_LABEL_CHARS = 32
_FOOTER_TRUNCATIONS = 10


def _generated(value: str) -> str:
    return f"{value[:10]} {value[11:19]} UTC" if value else "not recorded"


def _label(step_id: str) -> str:
    return step_id if len(step_id) <= _LABEL_CHARS else step_id[: _LABEL_CHARS - 1] + "…"


def _received(inp: ReportInput, key: str, shown: int) -> int:
    return inp.received.get(key, shown)


def _chart(inp: ReportInput) -> list[str]:
    bars = inp.funnel_data
    if not bars:
        return ['<p class="note">No funnel data.</p>']
    height = 2 * _TOP + _ROW * len(bars)
    top = max(b.users for b in bars)
    out = [(f'<svg class="chart" viewBox="0 0 {_WIDTH} {height}" width="100%" role="img" '
            'aria-label="Users entered per funnel step">')]
    for i, bar in enumerate(bars):
        y = _TOP + _ROW * i
        width = _BAR_MAX * bar.users / top if top else 0.0
        out.append(
            f"<g><title>{text(bar.step_id)}: {bar.users:,} users</title>"
            f'<text class="label" x="{_LABEL_X}" y="{y + 19}" text-anchor="end">{text(_label(bar.step_id))}</text>'
            f'<rect class="bar" x="{_BAR_X}" y="{y}" width="{width:.1f}" height="{_BAR_H}" fill="#007bff"/>'
            f'<text class="value" x="{_BAR_X + width + 6:.1f}" y="{y + 19}">{bar.users:,}</text></g>'
        )
    out.append("</svg>")
    return out


def _friction(inp: ReportInput) -> list[str]:
    if not inp.friction_scores:
        return []
    out = ["<h2>Friction by step</h2>", '<table class="friction">',
           "<thead><tr><th>Step</th><th>Friction score</th><th>Critical</th></tr></thead>", "<tbody>"]
    out += [f"<tr><td>{text(row.step_id)}</td><td>{row.score:.1f}</td><td>{'Yes' if row.is_critical else '—'}</td></tr>"
            for row in inp.friction_scores]
    out += ["</tbody>", "</table>"]
    return out + _shown_note(inp, "friction_scores", len(inp.friction_scores), "friction rows")


def _insights(inp: ReportInput) -> list[str]:
    out = ["<h2>Top Prioritised Insights</h2>", '<div class="insights-container">']
    if not inp.insights:
        out.append("<p>No critical insights generated.</p>")
    for ins in inp.insights:
        out += [
            '<div class="insight-card">',
            f"<h4>[Priority {ins.priority}] - {text(ins.step_id)}</h4>",
            f"<p><strong>Issue:</strong> {text(ins.title)}</p>",
            f"<p><strong>Root Cause:</strong> {text(ins.root_cause)}</p>",
            f"<p><strong>Recommendation:</strong> {text(ins.suggested_fix)}</p>",
            "</div>",
        ]
    out += _shown_note(inp, "insights", len(inp.insights), "insights")
    out.append("</div>")
    return out


def _shown_note(inp: ReportInput, key: str, shown: int, noun: str) -> list[str]:
    received = _received(inp, key, shown)
    return [f'<p class="note">Showing {shown} of {received} {noun}.</p>'] if received > shown else []


def _counts(inp: ReportInput) -> dict[str, list[int]]:
    pairs = (("insights", "insights", inp.insights), ("funnel_steps", "funnel_data", inp.funnel_data),
             ("friction_rows", "friction_scores", inp.friction_scores))
    return {name: [len(items), _received(inp, key, len(items))] for name, key, items in pairs}


def _footer(inp: ReportInput, digest: str) -> list[str]:
    narrative = inp.narrative_source + (f", model {inp.narrative_model}" if inp.narrative_model else "")
    cuts = list(inp.truncated.items())
    shortened = ", ".join(f"{path} ({n})" for path, n in cuts[:_FOOTER_TRUNCATIONS]) or "nothing"
    if len(cuts) > _FOOTER_TRUNCATIONS:
        shortened += f" (+{len(cuts) - _FOOTER_TRUNCATIONS} more in the data block)"
    rows = [("Run", inp.run_id or "not recorded"), ("Schema", f"{SCHEMA} ({RENDERER})"),
            ("Input SHA-256", digest), ("Narrative", narrative), ("Shortened", shortened)]
    out = ['<footer class="details">', "<h2>Report details</h2>", "<dl>"]
    out += [f"<dt>{name}</dt><dd>{text(value)}</dd>" for name, value in rows]
    out += ["</dl>", "</footer>"]
    return out


def _data(inp: ReportInput, digest: str) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "renderer": RENDERER,
        "run_id": inp.run_id,
        "journey": inp.journey_name,
        "mode": inp.shown_mode,
        "generated_at": inp.generated_at,
        "input_sha256": digest,
        "narrative": {"source": inp.narrative_source, "model": inp.narrative_model},
        "counts": _counts(inp),
        "truncated": dict(inp.truncated),
        "funnel": [{"step_id": b.step_id, "users": b.users} for b in inp.funnel_data],
    }


def render(inp: ReportInput) -> str:
    digest = inp.input_sha256()
    mode = css_class(inp.shown_mode, MODES)
    journey = text(inp.journey_name)
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        f'<meta http-equiv="Content-Security-Policy" content="{attr(CSP)}">',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>CJI Report - {journey}</title>",
        f"<style>{STYLE}</style>",
        "</head>",
        "<body>",
        '<header class="header">',
        "<h1>Customer Journey Intelligence Report</h1>",
        (f'<p><strong>Journey:</strong> {journey} | <span class="badge {mode}">{mode.upper()} MODE</span> | '
         f"<strong>Generated:</strong> {text(_generated(inp.generated_at))}</p>"),
        "</header>",
        "<h2>Executive Summary</h2>",
        f'<div class="narrative">{text(inp.narrative)}</div>',
    ]
    if "narrative" in inp.truncated:
        parts.append(f'<p class="note">Narrative shortened to {TEXT_LIMITS["narrative"]} characters.</p>')
    parts += ["<h2>Funnel Analysis</h2>", '<div class="chart-container">', *_chart(inp), "</div>"]
    parts += _shown_note(inp, "funnel_data", len(inp.funnel_data), "funnel steps")
    parts += _friction(inp)
    parts += _insights(inp)
    parts += _footer(inp, digest)
    parts.append(f'<script type="application/json" id="cji-report-data">{json_block(_data(inp, digest))}</script>')
    parts += ["</body>", "</html>", ""]
    return "\n".join(parts)


__all__ = ["CSP", "LIST_LIMITS", "RENDERER", "SCHEMA", "STYLE", "render"]
