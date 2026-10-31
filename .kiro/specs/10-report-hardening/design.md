# Spec 10 — Safe Deterministic Reports: Design

Defaults from requirements §2 (OD-81 to OD-92). Changes if a decision changes.

## 1. Module layout

| File | Change |
|---|---|
| `cji_agent/reporting/__init__.py` | New. Exports `ReportInput`, `ReportOutcome`, `render`, `write_report`, `build_report`. |
| `cji_agent/reporting/model.py` | New. Input contract, limits, text cleaning, input hash (§2). |
| `cji_agent/reporting/escape.py` | New. One helper per output context (§3). |
| `cji_agent/reporting/render.py` | New. Pure `render(ReportInput) -> str`: page, SVG chart, tables, provenance (§4). |
| `cji_agent/reporting/output.py` | New. File name, path check, size check, atomic write (§5). |
| `cji_agent/mcp_servers/report_server.py` | `export_report` becomes a wrapper: validate → render → write → result dict (§6). `_h`, `_js` and the f-string template are removed. `generate_narrative` unchanged. |
| `cji_agent/domain/insights.py` | `ReportResult` gains `sha256`, `schema`, `code` (all `NotRequired`). |
| `cji_agent/agents/workers.py` | `report_worker` passes `generated_at`, narrative source and model; maps the result `code` to `StepError` (§7). |
| `cji_agent/dashboard.py` | Insights page: escape narrative, fix text, step labels, report names (§8). |
| `cji_agent/tests/test_reports.py`, `tests/_report_checks.py`, `tests/snapshots/*.html` | New (§9). |
| `tests/test_p0_security.py`, `tests/test_contracts.py`, `tests/test_workflow.py` | Updated where they call `export_report` (§9). |

`reporting/` imports only the standard library, pydantic and `domain`. mypy `--strict` for the package.

## 2. Input contract (`reporting/model.py`)

```python
class ReportInsight(BaseModel):          # extra="ignore"
    step_id: CleanText[128]              # required, non-empty
    title: CleanText[200]                # required, non-empty
    priority: int = Field(ge=1, le=5)    # strict int (no "2", no True)
    root_cause: CleanText[1000] = ""
    suggested_fix: CleanText[1000] = ""
    category: CleanText[32] = "unknown"

class FunnelBar(BaseModel):              # extra="ignore"
    step_id: CleanText[128]
    users: int = Field(ge=0, le=10**9)   # strict int
    drop_off_pct: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)

class FrictionRow(BaseModel):            # extra="ignore"
    step_id: CleanText[128]
    score: float = Field(ge=0, le=100, allow_inf_nan=False)
    is_critical: bool = False

class ReportInput(BaseModel):            # extra="forbid", frozen
    journey_name: CleanText[128]         # required, non-empty
    mode: Literal["demo", "realtime"] | str   # anything else is shown as "unknown"
    narrative: CleanText[4000] = ""
    insights: list[ReportInsight] = []   # list length limit: 50 kept, rest counted
    funnel_data: list[FunnelBar] = []    # 100
    friction_scores: list[FrictionRow] = []   # 100
    run_id: str = ""
    generated_at: str = ""               # UTC ISO 8601 or empty
    narrative_source: Literal["llm", "fallback", "unknown"] = "unknown"
    narrative_model: CleanText[100] = ""
```

- `CleanText[n]` is a `str` (strict: a dict or number is a validation error) passed through `clean_text`:
  remove C0 controls except `\t` and `\n`, remove DEL and C1 controls, normalise `\r\n`/`\r` to `\n`, replace
  lone surrogates with U+FFFD, then cut to `n` characters with `…` and record the truncation.
- Truncations go into a `truncated: dict[str, int]` field set by the validator (field path → original length;
  for lists, path → number dropped). Lists keep the first N items (the insight order is the rank).
- `input_sha256()` = SHA-256 of `model_dump(mode="json")` serialised with `sort_keys=True`,
  `separators=(",", ":")`, `ensure_ascii=True`.
- A failed validation raises `ReportInputError(message, fields)`; the message lists at most 5 field paths and
  never echoes the input values.

## 3. Escaping helpers (`reporting/escape.py`)

| Helper | Context | Rule |
|---|---|---|
| `text(v)` | element text, SVG `<text>`, `<title>` | `html.escape(v, quote=True)` |
| `attr(v)` | double-quoted attribute value | `html.escape(v, quote=True)`, plus bidi controls (U+202A–U+202E, U+2066–U+2069) as `&#x…;` |
| `json_block(obj)` | `<script type="application/json">` body | `json.dumps(sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)` then `<` `>` `&` → `\u003c` `\u003e` `\u0026` |
| `css_class(v, allowed)` | class attribute | value from a fixed allow-list, else `unknown` |
| `number(v, places)` | numbers | fixed format, e.g. `f"{v:,}"` for users, `f"{v:.1f}"` for scores |

Untrusted values are never put in URLs, event handlers, `style` attributes, CSS or executable script; the renderer
has no code path that does so (checked by the tests in §9 and by a source test that `render.py` contains no
`style="`, `href=`, `src=` or `<script>` other than the data block).

## 4. Rendering (`reporting/render.py`)

`render(inp: ReportInput) -> str` builds a list of strings and joins it. No clock, environment, randomness or
dict-order dependence: every mapping it iterates is a list or sorted.

Page structure (same order as today):
1. `<head>`: CSP meta (first), charset, viewport, `<title>CJI Report - {journey}</title>`, one `<style>` block
   (constant `STYLE`; the CSP carries `'sha256-' + b64(sha256(STYLE))`, computed at import).
2. Header: journey, mode badge (`css_class`), "Generated: {generated_at or 'not recorded'} (UTC)".
3. Executive Summary: narrative in `<div class="narrative">` (`white-space: pre-wrap`, as today); a note when it
   was truncated.
4. Funnel Analysis: inline SVG (below); "No funnel data." when empty.
5. Friction by step (OD-91): table of step, score (`.1f`), critical (Yes/—), in input order; omitted when empty.
6. Top Prioritised Insights: the same cards as today (`[Priority n] - step`, Issue, Root Cause, Recommendation);
   "No critical insights generated." when empty; "Showing 50 of N insights." when cut.
7. Report details footer: run id, schema, renderer version, input SHA-256, narrative source and model,
   truncations.
8. `<script type="application/json" id="cji-report-data">`: `{"schema": "cji-report/1", "renderer": ...,
   "run_id", "journey", "mode", "generated_at", "input_sha256", "narrative": {"source", "model"}, "counts":
   {"insights": [shown, received], "funnel_steps": [...], "friction_rows": [...]}, "truncated": {...},
   "funnel": [{"step_id", "users"}...]}`.

SVG chart (OD-81): `viewBox="0 0 800 H"` with `H = 24 + 36 × bars`, `width="100%"`, `role="img"`,
`aria-label="Users entered per funnel step"`. Per bar: label text (first 32 characters, `…` when longer) at
x = 170 right-aligned, a `<rect>` from x = 180 with width `600 × users / max_users` (0 when max is 0) and
`fill="#007bff"`, the value as text after the bar, and `<title>{full step id}: {users:,} users</title>` inside a
`<g>` for the hover value. Presentation attributes only, no `style`.

## 5. Output (`reporting/output.py`)

- `report_filename(inp)` → `cji_report_{slug}_{id}.html` (OD-86). The slug keeps only `[a-z0-9_-]`, so separators,
  `.`, `:` and drive letters cannot appear; the prefix means reserved device names cannot appear either.
- `write_report(html, directory, filename)`:
  1. `directory.mkdir(parents=True, exist_ok=True)`; `base = directory.resolve()`.
  2. `target = (base / filename).resolve()`; require `target.parent == base` and `target.suffix == ".html"`,
     otherwise `ReportPathError` (cannot happen with a valid slug; the check stays as a second line).
  3. `data = html.encode("utf-8")`; if `len(data) > 1 MiB` → `ReportTooLarge` (before any file is opened).
  4. `tempfile.NamedTemporaryFile(dir=base, prefix=".cji_report_", suffix=".tmp", delete=False)`, write, flush,
     `os.fsync`, close, `os.replace(tmp, target)`. Any exception removes the temporary file and is raised as
     `ReportWriteError`.
  5. Returns `(target, sha256(data), len(data))`.

## 6. MCP tool (`report_server.export_report`)

Signature keeps the current parameters and adds optional `generated_at`, `narrative_source`, `narrative_model`:

```python
def export_report(journey_name, narrative, friction_scores, insights, funnel_data, mode, run_id="",
                  generated_at="", narrative_source="unknown", narrative_model="") -> dict:
    try:
        inp = ReportInput.model_validate({...})
    except ReportInputError as e:   -> {"report_path": None, "file_size_kb": 0, "error": str(e), "code": "report_invalid_input"}
    html = render(inp)
    try:
        path, digest, size = write_report(html, REPORTS_DIR, report_filename(inp))
    except ReportTooLarge:          -> code "report_too_large"
    except ReportWriteError:        -> code "report_write_failed"
    return {"report_path": str(path), "file_size_kb": round(size / 1024, 2), "sha256": digest, "schema": "cji-report/1"}
```

Errors are logged with the code and field paths only.

## 7. Worker (`report_worker`)

- Pass `generated_at` from the narrative result, `narrative_source` (`llm` when the gateway outcome is `ok`,
  `fallback` when it is `fallback`, else `unknown`) and `narrative_model` (gateway info `model`).
- On a result without `report_path`: `StepError(message, code=result["code"] or "report_export_failed",
  retryable=(code == "report_write_failed"))`. `report_export_failed` stays as the code when an older server
  returns no code.

## 8. Dashboard (Insights page only)

`html.escape` for `narrative` (line 1268, newlines kept by the existing CSS), `step_lbl` and `action`
(1335–1336) and `r.name` (1358). The `st.markdown` calls without `unsafe_allow_html` and the expander label are
plain text and stay as they are.

## 9. Tests

`tests/_report_checks.py`: `check_contract(html) -> list[str]` and `check_inert(html) -> list[str]`, built on
`html.parser.HTMLParser`:
- allowed elements only (`html head meta title style body div p h1 h2 h4 span strong table thead tbody tr th td
  svg g rect text title footer dl dt dd script`);
- no attribute whose name starts with `on`, no `href`, `src`, `xlink:href`, `action`, `formaction`, `srcdoc`,
  `style`;
- exactly one `<script>`, with `type="application/json"`, whose body parses as JSON;
- the CSP meta is the first child of `<head>` and equals the expected policy including the hash of the actual
  `<style>` body; exactly one `<style>`;
- no `http:`, `https:`, `//` or `javascript:` anywhere outside the escaped text nodes;
- UTF-8 size ≤ 1 MiB.

`tests/test_reports.py`:
- **Payload corpus × fields**: each payload in each untrusted field (journey, narrative, insight fields, funnel
  and friction step ids, run id, model); `check_inert` and `check_contract` are empty, and the payload's escaped
  form is present.
- **Snapshots**: `tests/snapshots/report_basic.html`, `report_empty.html`, `report_malicious.html`, compared as
  bytes. `pytest --update-report-snapshots` (option added in `conftest.py`) rewrites them.
- **Determinism**: two renders and two exports of the same input are byte-identical; file name stable.
- **Empty**: no insights / funnel / friction rows; all-zero users (no division by zero).
- **Large**: 2,000 insights and 10,000-character fields → 50 cards, truncation notes, provenance counts; a
  constructed input over 1 MiB → `report_too_large` and no file.
- **Malformed**: `None`/string/int items, dict narrative, string or negative or float `users`, NaN scores,
  priority `"2"`, missing `title` → `report_invalid_input`, no file, message lists field paths without values.
- **Text cleaning**: NUL, controls, lone surrogates, CRLF.
- **Paths**: `../`, `..\`, absolute paths, `C:`, `a:b`, `CON`, 300-character names, empty name → file is a direct
  child of the reports directory with the expected slug; no other file appears anywhere under `tmp_path`.
- **Write failure**: `os.replace` patched to fail → `report_write_failed`, temporary file removed.
- **Chart**: bar count, order, labels and `<title>` values match `funnel_data`; widths proportional.
- **Worker**: each result code becomes a `StepError` with that code and retryability.
- **Dashboard**: source test that the four Insights-page interpolations go through `html.escape`.

Updated tests: the R-05 tests in `test_p0_security.py` move the attack strings out of `priority` (now an integer
contract) into text fields and keep their assertions; `test_contracts.py` validates the extended `ReportResult`;
`test_workflow.py` keeps `cji_report_j_run-report-1.html`.

## 10. Risks

| Risk | Mitigation |
|---|---|
| The strict contract rejects insights the pipeline produces today (e.g. a missing `priority`) and fails runs that used to produce a report | T1 runs the demo pipeline and a contract check on recorded insights before the switch; the worker test covers the fallback insight shape. Failing is explicit (R8). |
| SVG chart looks different from Chart.js | Same data, order and labels; R4 behaviour test; owner can pick OD-81 (b). |
| Snapshot files change line endings through an editor or git | Compared as bytes; `.gitattributes` entry `cji_agent/tests/snapshots/*.html -text`. |
| Dashboard escaping changes how narratives with intentional HTML look | Narratives are plain text by the prompt ("Return ONLY plain text"). |

## 11. Rollback

`spec10-tracked.patch` reversed, `pre-spec10-tracked.patch` applied, the untracked copies in
`pre-spec10-untracked/` restored, and the new files deleted (`reporting/`, `tests/test_reports.py`,
`tests/_report_checks.py`, `tests/snapshots/`). Report files written by Spec 10 can stay; they are plain HTML.
