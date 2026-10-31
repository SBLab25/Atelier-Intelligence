# Spec 10 — Safe Deterministic Reports: Tasks

Sequential. `[x]` means evidence exists. No commits or pushes: the change set is recorded as patch files in `evidence/`.

**Environment:** protected environment (dummy LLM keys, dead proxy, dead database URLs, `CJI_MODE=demo`). Report
tests write only below `tmp_path`. The real Supabase URL was never used.

**Status:** OD-81 to OD-92 approved with their defaults ("implement spec 10"). Implemented 2026-10-28. Gate passed.

## Tasks

- [x] **T0 Prepare.** `evidence/pre-spec10-tracked.patch` (426,039 bytes) and `evidence/pre-spec10-untracked/`
  (50 files, MANIFEST.txt). Baseline = Spec 09 gate (749/749).
- [x] **T1 Failing tests first.** `tests/test_reports.py` and `tests/_report_checks.py` against the Spec 09 code:
  280 tests, 0 passed (`evidence/before-tests-junit.xml`, `before-tests-summary.txt`). The insights and friction rows
  of the last real pipeline run (`data/last_run.json`, 4 insights, 8 rows) satisfy the new contract unchanged
  (`evidence/t1-contract-check.txt`), so the stricter contract does not fail today's runs.
- [x] **T2 Contracts.** `reporting/model.py` (`ReportInput`, strict types, text cleaning, limits with recorded
  truncation, input hash, `ReportInputError` naming fields only); `domain/insights.py::ReportResult` gains `code`,
  `sha256`, `schema`.
- [x] **T3 Renderer.** `reporting/escape.py` (one helper per context) and `reporting/render.py` (page, inline SVG
  chart, friction table, insight cards, provenance footer and JSON data block, CSP with the style hash). Snapshots
  `tests/snapshots/report_{basic,empty,malicious}.html` written and read by eye.
- [x] **T4 Output.** `reporting/output.py` (slug file name, run id or input hash, direct-child path check, 1 MiB
  limit, temporary file + fsync + `os.replace`, cleanup on failure).
- [x] **T5 Wire up.** `export_report` is a 30-line wrapper returning structured errors; `report_worker` passes
  `generated_at`, narrative source and model, and maps the error code to `StepError` (only `report_write_failed`
  is retried). R-05 tests moved the attack strings out of the now-integer `priority`.
- [x] **T6 Dashboard and docs.** Insights page escapes the narrative, step labels, fix text and report names
  (OD-92). README: features row, file name, architecture row, guardrails row, new "Report output contract"
  section, FAQ. New root `.gitattributes`: `cji_agent/tests/snapshots/*.html -text`.
- [x] **T7 Gate.** `evidence/scripts/gate_spec10.ps1` (the Spec 09 gate plus `mypy --strict reporting`,
  `bandit reporting` and `report_contract_check.py` on every report the gate's pipelines wrote),
  `final_numbers.py`, `save_spec10.py`. Results below; `evidence/final-numbers.txt`, `spec10-tracked.patch`
  (432,348 bytes), `spec10-new-files/` (MANIFEST.txt).

## Gate (2026-10-28 17:10–17:20, protected environment)

| Check | Spec 10 | Spec 09 |
|---|---|---|
| Full suite (not integration) | **1036/1036** pass, 0 skipped | 749/749 |
| Tests added / removed | 287 added (280 `test_reports.py`, 7 `test_workflow.py`), none removed | — |
| Gate test set (7 modules incl. `test_reports.py`) | 556/556 | — |
| `test_reports.py` | 280/280 (T1 baseline of the same file: 0/280) | — |
| Collector smoke (Spec 07) | 16/16 | 16/16 |
| Golden snapshot | identical to Spec 09 | identical to Spec 08 |
| ruff, whole tree | 97 findings | 98 |
| ruff, new code (`reporting/`, report tests) | clean | — |
| mypy, whole tree | 35 errors in 13 files (94 files checked); no file changed its count | 35 in 13 (87 checked) |
| mypy `--strict` reporting / workflow / integrations / repositories | clean / clean / clean / clean | — / clean / clean / clean |
| bandit, whole tree | HIGH 0, MEDIUM 12, LOW 1065 | HIGH 0, MEDIUM 12, LOW 957 |
| bandit `reporting/` | no issues (exit 0) | — |
| CLI, settings, pause/approve/status, mode mismatch | all as in Spec 09 | — |
| Kill during `insight_worker`, then `--resume` | killed with 2 steps done; resume completed the run and wrote its report | same |
| Report contract and inertness on the 5 reports the gate wrote | **PASS**: CSP first in `<head>` and matching the style hash, no executable script, no URL or event-handler attribute, one JSON data block, chart data equal to the demo funnel, names match the pattern, no temporary files left | — |
| Audit check (Spec 08) / workflow audit (Spec 09) | PASS / PASS | PASS / PASS |
| `git diff --check`, tracked `events.parquet` | clean, unchanged | clean, unchanged |

Notes on the numbers:
- **ruff −1:** the removed f-string template in `report_server.py`. Every remaining finding in the changed files
  (`workers.py` I001; `dashboard.py` I001, RUF059, PLW1510, SIM102; `report_server.py` I001, UP017) is in the
  Spec 09 gate log at the same place.
- **bandit LOW +108:** all in tests (`test_reports.py`: 100 `assert`, plus B404/B603 for the hash-seed subprocess;
  `test_workflow.py`: 6 `assert`).
- Each gate report is 7,887 bytes (Spec 09 reports were 4,702 bytes plus the CDN script).

### Gate runs that did not count
- 16:47–16:56: a launch I believed had been dropped by the harness shell did run; the next run overwrote its
  results before they were read.
- 16:56–17:06: passed every check, but its reports showed the provenance problem below. After the fix the gate
  was run again (17:10–17:20, the run recorded above).

### Found while gating
- **Fallback narratives named a model.** The 16:56 gate's reports said `narrative: fallback, model
  openai/gpt-oss-120b`: the gateway reports the configured model even when the template fallback wrote the
  narrative. `report_worker` now records the model only when the LLM wrote the narrative; covered by
  `test_fallback_narrative_records_no_model`.
- `test_cleanup.py::test_tests_rely_on_conftest_for_sys_path` caught a `sys.path.insert` in the new hash-seed
  test; the subprocess does not need it (`python -c` already puts `cji_agent/` first).

## Acceptance criteria (Prompt 9)

| Criterion | Evidence |
|---|---|
| XSS payloads render inert | `test_payload_renders_inert_in_every_field` (20 payloads × 10 fields: script tags, attribute and tag breakouts, `javascript:`/`data:` URLs, SVG `onload`, `</title>`, `</style>`, `</script>`, comments, CDATA, U+2028/2029, bidi override, mutation-XSS markup, template syntax, CSS `url()`), `test_payload_text_is_escaped_not_dropped`, `test_json_block_cannot_close_the_script_or_open_a_comment`, `test_bidi_controls_are_character_references_in_attributes`, `test_mode_is_allow_listed`, `test_renderer_source_has_no_dangerous_sinks`, the R-05 tests, `report_malicious.html` snapshot; gate contract check on real reports |
| Reports satisfy the self-contained output contract | `check_contract` in every report test (CSP meta first and matching the style hash, one style block, one JSON data block, no external element or URL attribute, UTF-8 charset in the first 1,024 bytes, ≤ 1 MiB), `test_basic_report_satisfies_the_contract`, `test_provenance_block_records_the_inputs`, `test_footer_shows_the_provenance`; gate contract check |
| Empty, large, malformed and malicious inputs are tested | Empty: `test_empty_report`, `test_minimal_call_without_optional_arguments`, `test_chart_with_all_zero_users_has_zero_width_bars`. Large: `test_large_input_is_truncated_visibly`, `test_worst_case_within_limits_is_written_or_refused_explicitly`, `test_oversize_output_is_refused_and_no_file_is_left`. Malformed: 29 cases in `test_malformed_input_fails_explicitly_without_a_file`, `test_invalid_input_error_lists_at_most_five_fields`, `test_generated_at_must_be_utc_iso`, `test_text_is_cleaned`. Malicious: the payload corpus |
| Snapshot-style tests | `test_snapshot[basic/empty/malicious]` (byte comparison), `test_same_input_gives_byte_identical_files_and_names`, `test_rendering_does_not_depend_on_hash_seed_or_clock` |
| Path traversal and arbitrary writes prevented | `test_file_name_is_a_slug_inside_the_reports_directory` (13 names incl. `../`, `..\`, `/etc/passwd`, `C:\…`, `a:b`, `CON`, 300 characters, NUL), `test_invalid_run_id_uses_the_input_hash`, `test_path_check_refuses_names_outside_the_directory` |
| Failed generation is explicit | `test_write_failure_is_explicit_and_leaves_no_temporary_file`, `test_reports_directory_that_is_a_file_is_a_write_failure`, `test_report_error_codes_fail_the_step_with_that_code` (codes and retryability), `test_report_is_named_by_run_and_a_missing_file_fails_the_step` |
| Report meaning and chart behaviour preserved | `test_report_meaning_is_preserved` (section order, card text, badge, title, narrative), `test_chart_has_one_bar_per_step_in_order_scaled_to_the_largest`, `test_chart_labels_are_shortened_but_the_title_keeps_the_full_step`, `test_friction_table_lists_scores_in_input_order`, `test_report_worker_output_passes_the_real_report_contract`; gate: chart data of every report equals the demo funnel |

## Deviations from the design

- **Chart width.** The SVG `viewBox` is 860 wide (design: 800), so the value label after the longest bar stays
  inside the chart.
- **No `category` field.** `ReportInsight` does not take `category`; the report never showed it (design §2 listed
  it). Extra keys are ignored, so callers are unaffected.
- **`drop_off_pct` unbounded.** Funnel `drop_off_pct` accepts any finite number: `domain/metrics.py` documents that
  it can be negative. It is not shown in the report.
- **Model only for LLM narratives** (see "Found while gating").
- **New root `.gitattributes`** (none existed) for the snapshot rule.

## Behaviour changes callers can see

- The report has no JavaScript and loads nothing: the funnel chart is inline SVG with exact values on hover
  (no Chart.js animation or legend). It works offline.
- New "Friction by step" table, "Report details" footer and an embedded JSON data block (`cji-report/1`).
- "Generated:" shows the narrative's UTC time (`2026-01-01 00:00:00 UTC`), or "not recorded".
- File names use a slug of the journey name (`a-z 0-9 _ -`) and the run id; without a valid run id the input hash
  replaces the timestamp. Same input → same file and bytes.
- `export_report` returns `sha256` and `schema` on success, `code` on failure (`report_invalid_input`,
  `report_too_large`, `report_write_failed`); wrong types fail instead of being printed as Python reprs. The run
  fails with that code; only `report_write_failed` is retried.
- Long text is cut with "…" (narrative 4,000, title 200, other insight text 1,000 characters; 50 insights,
  100 funnel steps, 100 friction rows) and noted in the report.
- Dashboard Insights page: narrative, fix text, step labels and report names are shown as text, not HTML.

## Findings

| ID | Finding | Status |
|---|---|---|
| F-41 | Path traversal and arbitrary write through `journey_name` | Fixed (slug name, direct-child check) |
| F-42 | Unpinned CDN script, no CSP, not self-contained | Fixed (inline SVG, CSP, no external resources) |
| F-43 | Non-deterministic header time and timestamp names | Fixed |
| F-44 | Malformed input crashed the tool | Fixed (`report_invalid_input`) |
| F-45 | No size limits | Fixed (limits and 1 MiB cap) |
| F-46 | No input contract; `friction_scores` unused | Fixed |
| F-47 | "table below" without a table | Fixed (friction table) |
| F-48 | No provenance | Fixed |
| F-49 | Dashboard renders report content as HTML | Insights page fixed; **other pages open** (dashboard prompt) |
| F-12, F-20, F-21 | Prompt reuse; `event_id` global key; plain-text tracker keys | Open, later Specs |
| F-22 to F-25, F-27, F-28 | Owner checks: journey names in Supabase `api_keys`, dev key snippet, per-process limits, retired model `llama3-70b-8192`, raw rows sent to the LLM, unused OpenAI key | Open, owner |

## Rollback

1. `git apply -R .kiro/specs/10-report-hardening/evidence/spec10-tracked.patch`, then
   `git apply .kiro/specs/10-report-hardening/evidence/pre-spec10-tracked.patch` (restores the pre-Spec-10 tracked
   state).
2. Copy the files in `evidence/pre-spec10-untracked/` back over their paths (`domain/insights.py`,
   `tests/test_p0_security.py`, `tests/test_workflow.py`).
3. Delete the files listed as `new` in `evidence/spec10-new-files/MANIFEST.txt` (`cji_agent/reporting/`,
   `tests/test_reports.py`, `tests/_report_checks.py`, `tests/snapshots/`, `.gitattributes`).
4. Reports written by Spec 10 may stay (plain HTML) or be deleted. No database or settings change was made.
