# Spec 10 — Safe Deterministic Reports: Requirements

Source: `kiro_upgrade_prompts.md`, Prompt 9 ("Harden and simplify report generation"); guide row "10 Safe Reports".
Builds on Spec 01 (R-05 escaping), Spec 03 (contracts), Spec 08 (gateway) and Spec 09 (run-named reports,
`report_export_failed`).

**Status:** written 2026-10-28; OD-81 to OD-92 approved with their defaults; implemented and gated 2026-10-28 (see tasks.md).

## 1. Current state (surveyed after Spec 09)

The report is built by one function, `mcp_servers/report_server.py::export_report` (239-line module). It formats a
Python f-string, writes a temporary file and renames it. `generate_narrative` (same module) produces the narrative.
`agents/workers.py::report_worker` calls both and raises `StepError(code="report_export_failed")` when no path
comes back. The dashboard lists `reports/*.html` and offers them for download.

What already works: `_h()` escapes element text and quoted attributes; `_js()` escapes chart data so it cannot
close the `<script>` tag; `mode` is allow-listed before it becomes a CSS class; the write is atomic. Four R-05
tests in `tests/test_p0_security.py` cover these.

Evidence: `evidence/survey/exp.py` (run in the protected environment against a temporary directory),
output in `evidence/survey/exp.txt`.

### Findings

| ID | Finding | Evidence |
|---|---|---|
| F-41 | **Path traversal and arbitrary file write.** `journey_name` goes into the file name unchecked. `journey_name="x/../../escaped"` wrote `escaped_run-1.html` one directory **above** the reports directory; the backslash form did the same. `journey_name="a:b"` created a stray file `cji_report_a` (an NTFS alternate data stream) and then failed. `journey_name` comes from settings (`JOURNEY_NAME`) and from workflow state. | exp.txt E1 |
| F-42 | **Not self-contained, no CSP.** The report loads `https://cdn.jsdelivr.net/npm/chart.js`: no version pin, no SRI hash, and no Content-Security-Policy. Opened offline the chart is blank; a compromised CDN runs code in every report. | exp.txt E5 |
| F-43 | **Not deterministic.** The header shows `datetime.now()` (local time, no zone), so two renders of the same input differ. Without a valid `run_id` the file name is a local timestamp. | exp.txt E4 |
| F-44 | **Malformed input crashes the tool.** A `None` or string insight and an integer funnel row raise `AttributeError`; a lone surrogate in the narrative raises `UnicodeEncodeError`, which the `except OSError` does not catch. The worker sees only a generic tool error. | exp.txt E2 |
| F-45 | **No size limits.** 2,000 insights with 6 KB of text each plus a 1 MB narrative produced a 13.5 MB file in 2.6 s. Only `generate_narrative` caps its own output (4,000 characters); `export_report` accepts anything. | exp.txt E3 |
| F-46 | **No input contract.** `export_report` takes untyped lists. A dict narrative is rendered as its Python repr; text in `users` goes into the chart data; `priority` is printed as given. `friction_scores` is accepted but never used. | exp.txt E2, source |
| F-47 | **Meaning gap.** The fallback narrative ends "…findings detailed in the table below", but the report has no table. | source, exp.txt E5 |
| F-48 | **No provenance.** The report does not record the run id, input hash, schema version, whether the narrative came from the LLM or the fallback, or what was left out. | source |
| F-49 | **Dashboard renders report content as HTML.** The Insights page puts the LLM narrative (`dashboard.py:1268`) and fix text and step labels (`:1335-1336`) into `st.markdown(..., unsafe_allow_html=True)` without escaping. Other pages interpolate data the same way. | source |

Not findings: `_h()` and `_js()` are correct for the contexts they are used in; the atomic write leaves no
temporary file behind (exp.txt E2).

## 2. Decisions (defaults; confirm or change before implementation)

| ID | Decision | Default | Alternatives (rejected by default) |
|---|---|---|---|
| OD-81 | Chart rendering | **Server-rendered inline SVG bar chart, no JavaScript.** Same data, labels and order; values on hover through SVG `<title>`; scales with the page through `viewBox`. The chart data is also embedded as a non-executable `<script type="application/json">` block. | (b) Vendor Chart.js (pinned version, SHA-384 checked, about 200 KB inlined per report, hash-based CSP). Keeps animation and Chart.js tooltips, but runs a third-party script in every report. (c) Pinned CDN with SRI: still needs the network, so not self-contained. |
| OD-82 | Renderer structure | New package `reporting/`: `model.py` (input/output contracts), `render.py` (pure `render(ReportInput) -> str`), `output.py` (file name, path check, atomic write). `export_report` becomes a thin MCP wrapper. Standard library only. | Jinja2 with autoescape (new dependency; does not escape JSON or SVG contexts by itself). Keep the f-string in the server. |
| OD-83 | Input validation | Pydantic `ReportInput`. **Wrong types or missing required fields fail** (`report_invalid_input`). **Over-long content is truncated visibly** (see limits) and recorded in the provenance block. | Reject anything over a limit (one long insight would cost the whole report). Truncate silently. |
| OD-84 | Limits | journey 128 chars; narrative 4,000 (same as `generate_narrative`); 50 insights shown (input order = rank); title 200 and each other insight text 1,000 chars; 100 funnel steps; 100 friction rows; users 0–10⁹ integers; finished HTML ≤ 1 MiB, otherwise `report_too_large`. | Configurable limits through settings (YAGNI until someone needs them). |
| OD-85 | Text cleaning | Remove NUL and other control characters except tab and newline; replace lone surrogates with U+FFFD; normalise newlines to `\n`. Bidi override characters are kept but escaped as character references in attributes. | Reject such text (one bad byte from the LLM would fail the run). |
| OD-86 | File name and path | `cji_report_{slug}_{id}.html`. `slug` = journey name lower-cased, characters outside `[a-z0-9_-]` replaced by `_`, at most 64 chars, `journey` if empty. `id` = `run_id` if it matches `[A-Za-z0-9-]{1,64}`, otherwise the first 16 hex characters of the input hash. The resolved path must be a direct child of the resolved reports directory. | Keep the timestamp fallback (not deterministic). Reject invalid journey names (the journey name is still shown in the report; only the file name is slugged). |
| OD-87 | Determinism | `render()` reads no clock, environment or random source. The "generated at" time is an input (`generated_at` from `generate_narrative`, UTC ISO 8601); when it is missing the report says "not recorded". Same input → byte-identical file. | Stamp the export time (breaks byte identity). |
| OD-88 | Provenance | A JSON data block (schema `cji-report/1`) with: run id, journey, mode, generated_at, input SHA-256, narrative source (`llm`/`fallback`/`unknown`) and model, counts shown and received, truncations, renderer version. A visible "Report details" footer shows the same facts. `export_report` returns `report_path`, `file_size_kb`, `sha256`, `schema`. | HTML `<meta>` tags only (no structure). A separate sidecar JSON file (two files to keep in step). |
| OD-89 | Content-Security-Policy | `<meta http-equiv="Content-Security-Policy">` as the first element of `<head>`: `default-src 'none'; style-src 'sha256-<hash of the one <style> block>'; img-src 'none'; script-src 'none'; base-uri 'none'; form-action 'none'`. No `style=""` attributes and no external URLs anywhere. | `style-src 'unsafe-inline'` (simpler, weaker). |
| OD-90 | Failure semantics | `export_report` returns `{"report_path": null, "file_size_kb": 0, "error", "code"}` with code `report_invalid_input` or `report_too_large` (not retryable) or `report_write_failed` (retryable). It never raises for bad input. `report_worker` raises `StepError` with that code. | Raise from the tool (becomes the generic, non-retryable `tool_error`). |
| OD-91 | Meaning fixes | Render the friction scores already passed in as a "Friction by step" table (step, score, critical). This makes the fallback narrative's "table below" true and uses `friction_scores`, which the worker already sends. | Change the fallback wording and keep ignoring `friction_scores`. |
| OD-92 | Dashboard scope | Escape the report content on the **Insights page** (narrative, insight and fix text, step labels, report file names). The other dashboard pages stay for the dashboard prompt; recorded as F-49 (open). | Fix every `unsafe_allow_html` interpolation now (larger change to a 1,382-line file outside report generation). Leave the dashboard alone. |

## 3. Requirements

**R1 Contracts.**
- `ReportInput` and `ReportResult` in `reporting/model.py`; `domain/insights.py::ReportResult` gains the new
  optional fields (`sha256`, `schema`, `code`). Existing keys keep their meaning.
- Insight items need `step_id`, `title`, `priority` (1–5); `root_cause`, `suggested_fix`, `category` are optional
  text. Extra keys are ignored. Funnel items need `step_id` and integer `users`.

**R2 Escaping by context.** Every untrusted value (journey, narrative, insight fields, step ids, friction rows,
model name, run id) reaches the HTML through exactly one helper for its context: element text, quoted attribute,
SVG text, or JSON data block. No value is placed in a URL, an event handler, a `style` attribute, CSS or executable
script.

**R3 Self-contained output.** One HTML file, UTF-8, with no network requests, no external URLs, no executable
JavaScript and the CSP of OD-89. It renders the same offline.

**R4 Chart.** The funnel chart shows one bar per funnel step in input order with its label and user count, scaled
to the largest value, readable without JavaScript, with the exact value on hover (OD-81).

**R5 Determinism.** Same `ReportInput` → byte-identical HTML and the same file name (OD-86, OD-87).

**R6 Limits.** As OD-84 and OD-85; every truncation is visible in the report and recorded in the provenance block.

**R7 Paths.** Writes only to a direct child of the configured reports directory, via a temporary file in the same
directory and `os.replace`. No input can choose the directory, add path separators, drive letters, NTFS streams or
a different extension. The temporary file is removed on every failure.

**R8 Explicit failure.** Invalid input, oversize output and write errors return a structured error (OD-90); the
workflow run fails with that code (Spec 09 behaviour) and no partial or empty report file is left.

**R9 Provenance.** As OD-88.

**R10 Preserved.** Section order (header, executive summary, funnel chart, insights), the insight card content,
the mode badge, the deterministic fallback narrative and `generate_narrative` behaviour stay the same, apart from
the chart technology (OD-81) and the added friction table (OD-91).

**R11 Dashboard.** As OD-92.

## 4. Non-goals

- Browser-engine testing. "Inert" is checked by parsing the output (no executable script, no event-handler
  attributes, no URLs) and by the CSP; no headless browser is installed in this environment.
- Prompt-injection defence for `generate_narrative` beyond Spec 08's sanitiser.
- Rewriting or deleting the 49 existing report files in `reports/`.
- PDF export, report themes, localisation.
- The rest of the dashboard (F-49 remains open for the dashboard prompt).

## 5. Acceptance criteria (Prompt 9)

| Criterion | How it is shown |
|---|---|
| XSS payloads render inert | A payload corpus (script tags, attribute and tag breakouts, `javascript:` and `data:` URLs, SVG/`onload`, `</title>`, `</style>`, `</script>`, comments, CDATA, Unicode line separators, bidi overrides, NUL, lone surrogates) in every untrusted field. A parser-based check finds no executable script, no `on*` attribute, no URL attribute and no unexpected element; the payload text is still present, escaped. |
| Reports satisfy the self-contained output contract | Contract check on every test report: one CSP meta first in `<head>` that matches OD-89 and the style hash; no external reference; one JSON data block that parses and matches the input; size ≤ 1 MiB. |
| Empty, large, malformed and malicious inputs are tested | Tests for: no insights, no funnel, no friction rows; limits and truncation notes; oversize output; wrong types and missing fields (structured `report_invalid_input`); path inputs (traversal, separators, `:`, reserved names, long names); the payload corpus. |
| Snapshot-style tests | Golden HTML files under `tests/snapshots/` for a basic, an empty and a malicious input, compared byte for byte; a re-render test for byte identity. |
| Failed generation is explicit | Worker tests: each error code fails the run with that code and leaves no file. |
