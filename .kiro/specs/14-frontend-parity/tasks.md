# Spec 14 — Frontend Parity: Tasks

Sequential. `[x]` means the checks ran and passed. No commits or pushes. **Environment:** protected environment for
tests and builds (dead proxy, dead database URLs, dummy keys); network only for `npm ci` in a separate process.

**Status:** Implemented 2026-10-29 (approved: "implement spec 14", decisions OD-142 to OD-157 as written). Final
gate passed; record below.

## T0 Preparation
- [x] Copied the files this Spec changes to `evidence/pre-spec14-untracked/` (94 files; 91 at T0, plus
      `duckdb_parquet.py`, `test_docs.py` and `test_api_contract.py` from the Spec 12 change set, checked identical
      to the pre-Spec 14 state).
- [x] Baselines: pytest 1169 pass + 1 skipped; ruff 92; mypy 33 errors in 11 files; bandit Low 25 / Medium 10 /
      High 0; Vitest 102 in 9 files; OpenAPI 15 operations.
- [x] Protected-environment runner `evidence/scripts/prun.py` (app, web, repo).

## T1 Shared contract and engine groundwork
- [x] Settings `CJI_API_MAX_ACTIVE_RUNS`, `CJI_API_MAX_UPLOAD_BYTES`, `CJI_API_WRITE_OPERATIONS` (load, model, known
      keys, `.env.example`, settings tests).
- [x] Provenance state keys and worker changes; `tests/test_provenance.py`.
- [x] Run start without the `Workflow.create`/`drive` split (D-1); workflow tests unchanged and passing.
- [x] New problem codes and titles; per-path body limit for the upload paths (`UPLOAD_PATHS`).

## T2 Feature: ingestion status and validation feedback
- [x] `parse_file`/`write_rows` split; `tests/test_ingest_parse.py` (same output as before the split).
- [x] `services/ingestion.py` and `routes/ingestions.py`; contract tests in `tests/test_api_parity.py`.
- [x] Ingestion results and pending reviews in run results (tested with T5).
- [x] Frontend `/ingest`, upload form, validation summary; Vitest; `ingest.spec.ts`.
- [x] Parity note and UX differences in `docs/frontend-migration.md` §3.

## T3 Feature: journey and funnel analytics
- [x] Contract verified (existing `/metrics`); no API change.
- [x] Frontend window selector, funnel bars, metrics table, `lib/format.ts`; Vitest; `journey.spec.ts`.
- [x] Parity: API = direct `services.analytics` call (`parity_check.py`); Streamlit differences measured
      (`streamlit_diff.py`).

## T4 Feature: friction drill-down
- [x] Contract verified (`/friction`, `/events`, `/insights`); no API change.
- [x] Frontend step page, friction table, events table with pager, viewer permission state; Vitest;
      `friction.spec.ts`.
- [x] Parity: API scores = `score_steps` on the same metrics; Streamlit's fallback formula documented.

## T5 Feature: AI insight generation and provenance
- [x] `POST /runs` and `GET /runs/{id}/results`; contract tests.
- [x] Frontend `/runs/new`, run results, insight cards with provenance, usage; Vitest; `insights.spec.ts`.
- [x] Parity: results = checkpoint state = `--status` = `last_run.json` of the same run.

## T6 Feature: approval and resume workflow
- [x] `POST /runs/{id}/resume`; the approval continuation counts in `active_runs` (D-2); `active_runs` in health
      details; contract tests (409 cases, replay).
- [x] Frontend approve and resume forms, `RunAutoRefresh`; Vitest; `approval.spec.ts`.

## T7 Feature: report preview and download
- [x] `disposition=attachment` on report content; contract tests.
- [x] Frontend `/reports`, `/reports/[id]/download`; links from runs; Vitest; `reports.spec.ts`.

## T8 Feature: error, empty and permission states
- [x] State matrix applied; Vitest per state; `states.spec.ts`; axe on every new page.

## T9 Contract snapshot and generated types
- [x] `openapi/v1.json` regenerated (19 paths, 20 operations); `schema.ts`; `api:check`; fixture API compiles.

## T10 Documentation
- [x] `docs/frontend-migration.md` (listed in `docs/README.md` under "Current guides").
- [x] `frontend/README.md`, root `README.md`, `cji_agent/.env.example`.

## T11 Gate
- [x] `evidence/scripts/gate_spec14.ps1`; two runs (G-1, G-2 fixed between them).
- [x] `parity_check.py` and `streamlit_diff.py` outputs in `evidence/parity/`.

## T12 Final record
- [x] This section; scratch files in `C:\Users\sovan\.kiro\s14_*` deleted.

## Final gate (2026-10-29 02:02–02:13)

`evidence/scripts/gate_spec14.ps1` ran to the end; per-step exit codes in `evidence/gate-results.txt`, logs in
`evidence/gate-*.log`. The first run (01:38–01:47) failed the live smoke test (G-1) and pytest (G-2); both were
fixed and the gate was run again.

| Check | Result |
|---|---|
| `npm ci`, `npm audit` | exit 0; 0 vulnerabilities |
| `npm run api:check` | `schema.ts` equals `cji_agent/openapi/v1.json` |
| typecheck (strict), lint (`--max-warnings 0`) | 0 errors, 0 problems |
| Vitest | 124/124 in 11 files (was 102 in 9) |
| `next build`; bundle scan | exit 0; no secret, server variable or token in `.next/static` |
| Playwright, fixture API (smoke + 7 feature specs) | 19 passed, 4 skipped (the 4 `live.spec.ts` tests, which need a real API) |
| CLI run `cji --run --auto-approve` | run `f5d6aedb-af24-4b24-bb69-570671d1052e`, writes `last_run.json` |
| Playwright against a real `cji-api` (demo data, viewer and operator tokens) | 5 passed: smoke; journey metrics equal the API; operator starts, approves and downloads a report with provenance (run `93eddb52-3cb8-4bb5-8d9d-06e615fdf0df`); file validated by the real parser without writing; viewer permission states |
| Parity check (API = CLI `--status` = checkpoint = `last_run.json`; API = engine) | 31 of 31 checks passed (`evidence/parity/parity.txt`) |
| After the live phase | ports 3100, 8001–8006 free; API log holds no token; 1 validation upload left (validation never writes; it expires after 1 h) |
| Python suite (`-m "not integration"`) | 1205 passed, 1 skipped (was 1169 + 1) |
| ruff | 92 findings, same as baseline |
| mypy (project config) | 33 errors in 11 files, same as baseline |
| mypy `--strict` (api, services, analytics, http, workflow index) | no issues in 31 files |
| bandit | Low 25, Medium 10, High 0, same as baseline |
| OpenAPI snapshot | matches the API |
| Streamlit SQL vs engine (report only) | users per step identical; Streamlit's fallback formula marks 0 steps critical, the engine 4 (sign_up_form 72, email_verification 90, plan_selection 63, payment_info 85) |
| `cji-dashboard --help`, `cji --help` | both work: Streamlit and the CLI are kept |
| `git diff --check` | clean |

Change set: `evidence/pre-spec14-untracked/` (state before, 94 files) and `evidence/spec14-new-files/` (77 files
created or changed, `MANIFEST.txt`). The tracked files changed by this Spec are `README.md` and
`cji_agent/.env.example`. `evidence/spec14-tracked.patch` is the full working-tree diff against `HEAD` after Spec 14:
it covers Specs 01–14, because nothing has been committed. Nothing was committed or pushed.

## Findings, gate findings and deviations

| ID | What | Resolution |
|---|---|---|
| F-81 | `ingest_json._finalise` filled missing timestamps with `fillna(..., inplace=True)` on a column copy. Under pandas Copy-on-Write that did nothing, so rows with unreadable timestamps kept `NaT`. Found by the ingestion contract tests. | Assignment instead of `inplace`. This also changes `cji-ingest-json` and the Streamlit upload: those rows now get the write time, as the code always intended (`docs/frontend-migration.md` §3). |
| F-82 | React resets uncontrolled form fields after a Server Action, so the ingest page's "replace" radio fell back to "append" after validation. Found by `ingest.spec.ts`. | A hidden `write_mode` input driven by React state; the radios are named `write_mode_choice`. |
| G-1 | Live smoke test: `GET /journeys/{id}/friction` answered 500 (`'NoneType' object has no attribute 'fillna'`). The demo repository shares one DuckDB connection across the API's worker threads. The journey page requests metrics, friction and insights at the same time, and concurrent `execute().df()` calls on one connection can return `None`. The bug has existed since Spec 12. The fixture API cannot show it. | `DuckDbParquetRepository` serialises connection use with a lock. New `tests/test_repository_threads.py` (240 reads on 8 threads) failed with the same error before the fix and passes after. The PostgreSQL repository uses a pooled engine and is not affected. |
| G-2 | `tests/test_docs.py` (Spec 06) requires every `docs/*.md` to carry the "Historical design reference" banner and to be listed in `docs/README.md`. `docs/frontend-migration.md` is a current guide. | The test has a `CURRENT_GUIDES` list (exempt from the banner, still required in the index). `docs/README.md` has a "Current guides" table. |
| G-3 | The Next.js route announcer has `role="alert"`, so strict `getByRole("alert")` locators matched two elements. | The `alerts(page)` helper in `e2e/support.ts` excludes `#__next-route-announcer__`. |
| D-1 | Design §2.1 planned to split `Workflow.create`/`drive`. | Not split. `start_run` runs `ctx.runs.workflow().start(...)` as a background task; `_started()` polls the run index and checkpoint for up to 10 s and returns the `Run`. |
| D-2 | Design planned a `RunSlots` class, with the approval continuation taking a run slot. | No class: capacity uses the `ctx.active_runs` set. The approval continuation adds itself to `active_runs` but is never refused for capacity, because the approval was already accepted. |
| D-3 | Design §2.4: write operations not mounted (404) when `CJI_API_WRITE_OPERATIONS=false`. | Resume and ingestion answer 404. `POST /runs` answers 405, because `GET /runs` exists on the same path. Documented in the migration guide. |
| D-4 | OD-147 provenance fields `{source, model, provider, generated_at}`. | Also has `reason` (why a fallback was used). `source` is `llm`, `fallback` or `not_recorded`. |
| D-5 | — | `create_app` takes `preflight` and `ingestion_engine` parameters so tests can replace the MCP check and the database. |
| D-6 | Design: the events region shows the API's 403 for viewers. | The UI decides from the role and does not call the events API for viewers; the API still answers 403. |
| D-7 | — | `next.config.ts` sets `experimental.serverActions.bodySizeLimit` and `proxyClientMaxBodySize` to `11mb`, so the 10 MiB API limit is the one users hit. |

## Behaviour changes for users

- Next.js gains journey analytics with a window selector, step drill-down with events, run start, approval and
  resume, run results with insight provenance, report list and download, and file ingestion with a validation step.
  Navigation gains Ingest and Reports.
- `cji-api` gains `POST /runs`, `POST /runs/{id}/resume`, `GET /runs/{id}/results`,
  `POST /ingestions/validations`, `POST /ingestions` and `?disposition=attachment` on report content;
  `active_runs` in health details. New settings: `CJI_API_MAX_ACTIVE_RUNS` (1), `CJI_API_MAX_UPLOAD_BYTES`
  (10 MiB), `CJI_API_WRITE_OPERATIONS` (true).
- New runs record `insight_provenance` and `narrative_provenance`; older runs show "not recorded".
- `cji-ingest-json` and the Streamlit upload now set unreadable timestamps to the write time (F-81).
- Streamlit and the CLI are otherwise unchanged.

## Rollback

- New write operations only: `CJI_API_WRITE_OPERATIONS=false` and restart `cji-api`.
- Frontend: stop the Next.js process; Streamlit and the CLI keep working.
- Code: copy `evidence/pre-spec14-untracked/` back over the working tree, delete the files in
  `spec14-new-files/MANIFEST.txt` that are not in the backup, and run `npm ci` in `frontend/`. The new state keys
  are ignored by older code.

## Findings carried forward

| ID | Finding | Owner |
|---|---|---|
| Removal criteria | Streamlit retirement still needs a parity run on realtime PostgreSQL data and a decision to port or drop business KPIs, audience, heatmaps and the track selector (F-78). | Owner decision, later Spec |
| F-76 | Low-confidence mappings from `cji --ingest` have no resolution path. | Later Spec |
| F-79 | `last_run.json` is written only by CLI runs; Streamlit can show an older run than the API. | Later Spec |
| F-49 | Dashboard renders data as HTML on pages other than Insights (Streamlit unchanged by OD-156). | Later Spec |
| Spec 13 "New" | The runs list shows the latest 50 runs only (no paging yet). | Later Spec |
| Spec 13 "New" | The sign-in rate limit is shared by all users behind the frontend server's address. | Spec 15 |
| Spec 12 "New" | Per-process rate limits, idempotency state and active-run count (one API process). | Later Spec |
| OD-102 / F-53 (part) | 15 dependency advisories (LangGraph, LangChain-core, Chroma). | Later Spec |
| F-16, F-22 to F-25, F-27, F-28 | Owner checks (F-25: `LLM_MODEL`). | Owner |

## Findings carried in (at the start)

| ID | Finding | Owner |
|---|---|---|
| F-70 to F-80 | Parity survey findings (requirements §1) | This Spec (F-73, F-74, F-75 and F-80 resolved; F-70 to F-72 and F-77 measured and documented; F-76, F-78, F-79 carried forward) |
| Spec 13 "New" | Approval, events and insights pages; run paging beyond 50 | This Spec (pages done; run paging carried forward) |
| OD-102 / F-53 (part) | Dependency advisories | Later Spec |
| F-49 | Dashboard HTML rendering | Spec 14 → carried forward (OD-156) |
| Spec 12 "New" | Per-process state | Later Spec |
| F-16, F-22 to F-25, F-27, F-28 | Owner checks | Owner |
