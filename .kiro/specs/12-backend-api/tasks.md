# Spec 12 — Versioned Backend API (`/api/v1`): Tasks

Sequential. `[x]` means evidence exists. No commits or pushes: each step is recorded as a patch file in `evidence/`.

**Environment:** protected environment (dummy LLM keys, dead proxy, dead database URLs, `CJI_MODE=demo`). Network
only for uv when the lock gains `openapi-spec-validator` (OD-124).

**Status:** Implemented 2026-10-28 (approved: "implement spec 12", defaults OD-108 to OD-127). Gate passed; record below.

## Tasks

- [x] **T0 Prepare.** Save `pre-spec12-tracked.patch` and copies of untracked files. Baseline = Spec 11 gate
  (1078 + 1 skipped editable, 1079/1079 wheel).
- [x] **T1 Failing tests first.** `tests/test_api_contract.py` and `tests/test_api_units.py` (design §8) against the
  current tree; record which fail.
- [x] **T2 Shared pieces.** `cji.http` (request ids, collector switched), `cji.analytics.friction` (MCP server
  re-exports; scores identical on the demo data), `events_page` in both repositories, `run_index` written by
  `Workflow` and `Workflow.mark_approved`.
- [x] **T3 Services.** `cji.services.*`; CLI `--status` and the dashboard report list moved onto them (`--approve` unchanged, D-3).
- [x] **T4 API core.** App factory, problems and handlers, auth and token store, `cji-api-token`, limits, cursors,
  idempotency store, security headers, CORS, settings keys and role `api`, `cji-api`, registry service `api`.
- [x] **T5 Routes.** Health, me, journeys (+ events, metrics, friction, insights), reports, runs, approval.
- [x] **T6 OpenAPI.** Error responses declared per route, snapshot `openapi/v1.json`, document validation,
  response-validation fixture in the contract tests; test dependencies and lock (`lock-diff.txt`: additions only).
- [x] **T7 Docs.** README section "Backend API" (start, tokens, roles, endpoints, errors, pagination, idempotency),
  `.env.example`, environment table.
- [x] **T8 Gate.** Spec 11 gate plus design §9; save `spec12-tracked.patch` and new-file copies; final record here.

## Final gate (2026-10-28 22:09–22:24)

`evidence/scripts/gate_spec12.ps1` (written by `make_gate.py` from the Spec 11 gate; every step of that gate kept)
ran to the end; per-step exit codes are in `evidence/gate-results.txt`, the summary in `evidence/final-numbers.txt`.
The first gate run (21:46–22:01) passed as well; it showed new bandit findings in the new code (below, G-1), which
were marked and the gate was run again. The numbers here are from the second run.

| Check | Result | Spec 11 |
|---|---|---|
| Full suite, baseline venv (editable), `-m "not integration"` | 1169 pass, 1 skipped (the gate-only lock check), 0 fail | 1078 + 1 skipped |
| Full suite, clean venv (wheel, `uv pip sync requirements.lock`) | 1170/1170 | 1079/1079 |
| New tests | 91: `test_api_contract.py` 69, `test_api_units.py` 20, `test_packaging.py` 2 (new scripts); T1 baseline 0/89 | |
| Spec 12 test set (API, packaging, docs, settings, cleanup, friction, workflow, dashboard, repositories) | 525 pass, 1 skipped | |
| `cji-api` live (`gate-api-live.log`) | 36/36 checks: tokens (hash-only file), health, served OpenAPI = snapshot, docs off in production, me, journeys, metrics, friction, two event pages, 401/403/404/422, approval 202 → replay → 409 key reuse → background report step to `completed` → 200 `already_approved`, report metadata and HTML (CSP, nosniff), 429 with `Retry-After`, no token in the server log | |
| CLI `--status` of the run approved through the API | `completed`, human approved, report path set | |
| `python -m cji.api.openapi_snapshot --check` | matches | |
| `cji-settings check --role api` | exit 0 with an https origin and a 32+ character cursor secret; exit 2 with production defaults | |
| Golden snapshot of the MCP server tools | identical to Spec 11 (friction scoring moved to `cji.analytics`) | |
| ruff | 92 findings, none new (per file and rule) | 92 |
| mypy (README command) | 33 errors in 11 files; the one change is `journey_data_server.py` 1 → 0 | 34 in 12 |
| mypy `--strict` on `cji.api`, `cji.services`, `cji.analytics`, `cji.http`, `workflow/index.py` | no issues (29 files) | |
| bandit `-r src` | HIGH 0, MEDIUM 10, LOW 25, no change per file | same |
| bandit `-r .` | MEDIUM 13 (+1: the fake SQL text of the leak sentinel in `test_api_contract.py`), LOW +170 (test asserts) | MEDIUM 12 |
| pip-audit on the lock | 15 advisories in 5 packages (OD-102, unchanged) | 15 in 5 |
| Wheel | 10 console scripts, Spec 12 modules present, no tests/data/tokens | 8 scripts |
| Lock (`lock-diff.txt`) | 188 packages: 4 added (`openapi-spec-validator` 0.9.0, `openapi-schema-validator` 0.9.0, `lazy-object-proxy` 1.13.0, `rfc3339-validator` 0.1.4), 0 removed, 0 changed | 184 |
| Pipelines, kill/resume, ingest probe, mode mismatch, audits, report contract | as in Spec 11 | |
| `git diff --check` | clean | |

Change set: `evidence/spec12-tracked.patch` (518096 bytes) and `evidence/spec12-new-files/` (133 untracked files:
33 new, 19 changed, 81 unchanged; `MANIFEST.txt`). Nothing was committed or pushed.

## Gate findings and deviations

| ID | What | Resolution |
|---|---|---|
| G-1 | bandit flagged the new code: B608 on the three `run_index` statements (fixed column list, bound values) and B105 on the problem codes `missing_token`/`invalid_token` and `TOKEN_PREFIX`. | Marked `# nosec` with the reason on each line; `-r src` totals back to Spec 11. |
| G-2 | Two `integration`-marked tests in `test_ingestion_intelligence.py` call the LLM when a (dummy) key is set. | Not a regression: the gate runs `-m "not integration"`, as in Spec 11. |
| D-1 | `test_runs_list_detail_and_insights` expected the insights of the completed run, but OD-113 says "the latest run that has insights" (the paused run started later). | Test corrected to OD-113; `?run_id=` of the completed run is asserted separately. |
| D-2 | Public paths (`/health`, `/openapi.json`) shared the per-address bucket with failed authentication, so fetching the document counted against `CJI_API_RATE_PER_IP`. | Public paths use their own per-address bucket with the same rate (OD-121 refined). |
| D-3 | OD-125/T3 named CLI `--approve` and the dashboard last-run panel as service callers. | Only `--status` (`services.runs.cli_status`) and the dashboard report list (`services.reports.list_report_files`) moved. `--approve` keeps its synchronous approve-and-report behaviour; the last-run panel waits for Spec 14. |
| D-4 | Design names `Component.detail_code` and `Health.status: ok\|degraded`. | `Component.code`; `/health` is liveness only (`ok`); `/health/details` reports `degraded`. |
| D-5 | Every protected operation also declares 503 (unusable token file answers `service_misconfigured` before routing); `/health` declares 429. | Documented in the OpenAPI document. |
| D-6 | FastAPI's included routers no longer expose `.path`, so `test_docs.py` reads the backend routes from `openapi/v1.json`. | README routes are checked against the collector and the snapshot. |
| D-7 | The baseline venv still had `filelock` 3.32.7; installing the new lock moved it to 4.2.4, the version the lock has pinned since Spec 11. | No lock change. |
| D-8 | `tests/_api_harness.py` imports `jsonschema`, which has no type stubs in the lock. | `# type: ignore[import-untyped]`; no stub package added. |

## Behaviour changes for users

- New service `cji-api` (`/api/v1`, port 8006, registry service `api`) and `cji-api-token create|list|revoke`.
  Token file `CJI_API_TOKENS_FILE` (default `<data_dir>/api_tokens.json`), idempotency store `<data_dir>/api_state.db`.
- New settings `CJI_API_TOKENS_FILE`, `CJI_API_RATE_PER_TOKEN`, `CJI_API_RATE_PER_IP`, `CJI_API_CORS_ORIGINS`,
  `CJI_API_CURSOR_SECRET`, `CJI_API_PORT`/`CJI_API_URL`; role `api` for `cji-settings check`. Outside development and
  test, `cji-api` refuses to start without https origins and a 32+ character cursor secret.
- `Workflow` writes a `run_index` table into the checkpoint database on every run status change; `cji-api` indexes
  older runs once at startup.
- Friction scoring lives in `cji.analytics.friction`; the MCP server re-exports it (outputs identical).
- CLI `--status` and the dashboard report list go through `cji.services` (same output).
- Test dependency group gains `jsonschema` and `openapi-spec-validator`; the lock gains 4 packages.

## Rollback

1. `git apply -R evidence/spec12-tracked.patch`.
2. Delete the files listed as `new` in `evidence/spec12-new-files/MANIFEST.txt`; restore the `changed` ones from
   `evidence/pre-spec12-untracked/`; restore `cji_agent/requirements.lock` from `evidence/requirements.lock.before`.
3. Optional: `DROP TABLE run_index` in the checkpoint database; delete `api_tokens.json` and `api_state.db` from the
   data directory. Older code ignores all three.

## Findings carried forward

| ID | Finding | Owner |
|---|---|---|
| OD-102 / F-53 (part) | 15 advisories in LangGraph, LangGraph checkpoint (sqlite), LangChain-core and Chroma | Later Spec |
| F-49 | Dashboard pages other than Insights render data as HTML | Spec 14 |
| F-12, F-20, F-21 | Prompt reuse; `event_id` global key; plain-text tracker keys | Later Specs |
| F-16, F-22 to F-25, F-27, F-28 | Owner checks (password rotation, Supabase journey names, tracked dev key snippet, per-process limits, retired `LLM_MODEL`, raw rows to the LLM, unused OpenAI key) | Owner |
| New | Rate limits and the idempotency in-progress state are per process; a multi-instance deployment needs a shared store | Later Spec |

## Findings carried in (at the start)

| ID | Finding | Owner |
|---|---|---|
| F-57 to F-63 | API survey findings (requirements §1) | This Spec |
| F-53 (part) | LangGraph / LangChain-core / Chroma advisories (OD-102) | Later Spec |
| F-49 | Dashboard renders data as HTML on pages other than Insights | Spec 14 |
| F-12, F-20, F-21 | Prompt reuse; `event_id` global key; plain-text tracker keys | Later Specs |
| F-16, F-22 to F-25, F-27, F-28 | Owner checks (password rotation, journey names, dev key snippet, per-process limits, retired model, raw rows to the LLM, unused OpenAI key) | Owner |
