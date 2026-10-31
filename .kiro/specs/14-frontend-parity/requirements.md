# Spec 14 — Frontend Parity: Requirements

Source: `kiro_upgrade_prompts.md`, Prompt 13 ("Expand Next.js feature by feature while preserving parity with
Streamlit and the CLI"). Builds on Spec 12 (`/api/v1`, tokens and roles, problem responses, approval with
`Idempotency-Key`) and Spec 13 (`frontend/`: session cookie, typed client generated from `openapi/v1.json`,
`Result<T>` loaders, ProblemPanel, nonce CSP, Vitest and Playwright).

**Status:** Implemented 2026-10-29 (approved: "implement spec 14", decisions OD-142 to OD-157 as written). Final gate passed; record, findings F-81/F-82, gate findings and deviations in `tasks.md`.

Per feature the prompt asks for six steps: define or verify the backend contract, implement the API if needed,
implement the Next.js UI, compare results with the existing surface, add browser and contract tests, and document
intentional UX differences. Streamlit and the CLI are **not removed** in this Spec (§5 lists the removal criteria
and how far this Spec gets toward them).

## 1. Current state (surveyed after Spec 13)

Evidence: `evidence/survey/` (`survey.py`/`survey.txt`: dashboard pages and loaders, CLI flags, workflow, state and
audit keys, API operations; `survey2.py`/`survey2.txt`: API modules, `last_run.json` shape, provenance fields, run
index, OpenAPI operations; `dump.py`/`find.py`: the line dumps and searches used for the findings below).

### Feature map today

| Feature | Streamlit (`cji-dashboard`) | CLI | `/api/v1` | Next.js (Spec 13) |
|---|---|---|---|---|
| Ingestion and validation feedback | Sidebar upload (JSON/NDJSON), column map `your_col=cji_col`, root key, replace checkbox; calls `ingest_file` and writes PostgreSQL `tracking_events` at once; shows rows written or the error (`dashboard.py:474`, `:627`) | `cji-ingest-json FILE [--map] [--root-key] [--replace]` (same function); `cji --ingest --file … --run`: LLM schema detection over MCP, confidence gate, low-confidence files listed in run state `ingestion_pending_review` | none | none |
| Journey and funnel analytics | Overview and Journey pages: own SQL over `tracking_events`/`live_events`/`demo_events`, no time window; users per step, "retention", dwell, error and rage counts; business KPIs, audience, heatmaps | none (the pipeline computes metrics inside a run) | `GET /journeys/{id}/metrics` (steps, funnel, completion; `days` 1–365 or `minutes` 1–43200) | journey detail shows a metrics summary |
| Friction drill-down | Friction page: scores from `last_run.json`, else its own SQL formula (`compute_friction_from_db`) | inside a run only | `GET /journeys/{id}/friction`; `GET /journeys/{id}/events` (operator; `step_id`, `event_type`, cursor) | friction summary table |
| AI insights and provenance | Insights page: narrative, insights, prioritized fixes from `last_run.json`; without a run, rule-based texts from SQL (`compute_insights_from_db`) | `cji --run` generates insights; the report footer shows narrative source and model | `GET /journeys/{id}/insights[?run_id]` (latest run with insights) | none |
| Start, approval and resume | "Run" button: `python -m cji.main --run --auto-approve` as a blocking subprocess (180 s timeout); no approval or resume | `--run`, `--auto-approve`, `--approve`, `--resume`, `--status` with `--thread-id` | `POST /runs/{id}/approval` (operator, `Idempotency-Key`, 202 + background report step); no start or resume | run list and detail, read-only |
| Report preview and download | Report list (8 newest) with `st.download_button` | prints the report path | `GET /reports`, `/reports/{id}`, `/reports/{id}/content` (HTML, CSP sandbox) | `/reports/[id]` streams the HTML with the API CSP plus `sandbox` |
| Error, empty, permission states | `st.warning`/`st.info` texts; no roles | exit codes 0/1/2 and `[ERROR]` lines | RFC 9457 problems with `code` and `request_id`; viewer < operator < admin, journey list per token | ProblemPanel with Retry; 401 → login, 403 and 404 messages |

### Findings

| ID | Finding | Source |
|---|---|---|
| F-70 | **Streamlit reads a different data source than the engine.** Its SQL reads PostgreSQL `tracking_events`, `live_events` and `demo_events` (or their `UNION ALL`, chosen by a "track" selector), with no time window and no journey filter. The pipeline and the API read the repository of the configured mode (demo: DuckDB/Parquet; realtime: PostgreSQL) within a window. The same "users per step" number can therefore differ between the two surfaces even on the same day. | `dashboard.py:163-178`, `services/analytics.py` |
| F-71 | **Two friction formulas.** Without a pipeline result, Streamlit scores steps with drop×0.40 + error×0.30 + rage×0.20 + dwell penalty×0.10 and calls a step critical above 50. The engine (`cji.analytics.friction`, used by the pipeline and the API) uses five normalised signals with weights 0.35/0.25/0.15/0.15/0.10 and `FRICTION_SCORE_THRESHOLD` (default 60). | `dashboard.py:307-362`, `analytics/friction.py` |
| F-72 | **Streamlit shows rule-based texts as insights** when no run exists (`compute_insights_from_db`: fixed sentences chosen by score thresholds, priority 1–3) in the same layout as LLM insights, with no label saying so. | `dashboard.py:366-410` |
| F-73 | **Insight provenance is not stored.** The insight MCP tool returns `{"insight", "llm": {model, provider, outcome "ok"/"fallback", tokens, …}}`; the insight worker adds the call to `llm_usage` totals and drops the rest. The narrative's source (`llm`/`fallback`) and model reach only the report HTML (footer and data block), not the run state. Per-call records exist only in `data/audit/*.jsonl`, keyed by the run id. | `agents/workers.py:69-73, 222-239, 325-347`, `reporting/render.py:126-149` |
| F-74 | **API gaps for parity:** no operation starts a run, resumes a failed run, returns a run's narrative, prioritized fixes or ingestion results, validates or ingests a file, or serves a report as a download. | `openapi/v1.json` (15 operations) |
| F-75 | **The Streamlit upload writes without preview.** `ingest_file` parses, normalises (unknown event types dropped, bad timestamps replaced by "now", only logged) and writes in one call; the user sees only the number of rows written. Dropped and repaired rows are not reported. | `tools/ingest_json.py:537-645` |
| F-76 | **Low-confidence mappings from `cji --ingest` have no resolution path.** They are stored in `ingestion_pending_review` and printed nowhere; no CLI flag or MCP call approves them. | `agents/ingestion_worker.py:90-100` |
| F-77 | **Streamlit's step labels do not match their values.** "Avg Errors" is the count of error events; "Retention %" is users at a step divided by the largest step; "Avg Dwell" averages all events. The API reports rates per unique user (`error_rate_pct`, `abandon_rate_pct`, `completion_rate_pct`) and a funnel with `drop_off_pct`. | `dashboard.py:181-215, 989-1003`, `domain/metrics.py` |
| F-78 | **Streamlit-only features outside the prompt's list:** business KPIs (users, new/returning, sessions, revenue from `metadata.purchase_value`, "conflict users"), audience (region, device), click heatmaps (`metadata.click_x/click_y`), the track selector, and `--generate-data`. No API exposes them. | `dashboard.py:218-299, 812-858, 1007-1151` |
| F-79 | **`last_run.json` holds only the last completed CLI run** for the whole installation (keys `timestamp, mode, journey_name, report_path, narrative, friction_scores, critical_steps, insights, prioritized_fixes`). Runs approved through the API do not write it, so Streamlit can show an older run than the API. | `workflow/runtime.py:190-204`, `api/routes/runs.py:178-186` |
| F-80 | **Request size:** the API rejects bodies above 16 KiB (`MAX_BODY_BYTES`) for every route; Next.js Server Actions accept 1 MB by default. A file upload needs its own limit on both sides. | `api/middleware.py:39` |

## 2. Decisions (defaults; confirm or change before implementation)

| ID | Topic | Default | Rejected alternatives |
|---|---|---|---|
| OD-142 | Parity reference and tolerances | Parity is measured against the **engine** (the code the CLI and the pipeline run), not against Streamlit's own SQL. Tolerances are in §4. Run results (friction scores, critical steps, insights, fixes, narrative, statuses) must be **identical** between Next.js, the API and the CLI (`--status`, checkpoint state, `last_run.json` of the same run). Live metrics must be identical between the API and a direct call of the same service function. Streamlit's SQL panels and fallback formulas (F-70 to F-72, F-77) are **not ported**; their differences are measured on one data set and documented, without a pass/fail threshold. | Matching Streamlit's SQL numbers (would copy two formulas and a windowless union into the API); porting the fallback insights (they look like LLM output, F-72). |
| OD-143 | Contract changes | Additive changes to `/api/v1` only (new operations, new optional response fields); no field is removed or renamed, so Spec 13 code keeps working. The OpenAPI snapshot and `frontend/src/lib/api/schema.ts` are regenerated; `npm run api:check` and the Python snapshot test guard them. | `/api/v2` (no breaking change needed); hand-written frontend types for the new operations. |
| OD-144 | Start a run | `POST /api/v1/runs` (operator; `Idempotency-Key` required, same rules as approval). Body `{journey_id, auto_approve: false, window_days?: 1–365, window_minutes?: 1–43200}`; the mode is the API's configured mode. Before accepting, the API pings the MCP servers (as the CLI does) and answers 503 `services_unavailable` if one is down. It answers **202** with the new `Run` and drives it in a background task of the API process, like the approval continuation. At most `CJI_API_MAX_ACTIVE_RUNS` (default 1) runs started by one API process run at once; more answer 409 `run_capacity_reached`. Pending files are not accepted here (ingestion is OD-148). | A job queue or worker process (new infrastructure for a single-host app); running the CLI as a subprocess like Streamlit (no run id until it ends, blocking). |
| OD-145 | Resume | `POST /api/v1/runs/{id}/resume` (operator, `Idempotency-Key`): allowed for `failed` runs and for `running`/`approved` runs whose lease is free (process died, e.g. an API restart). 202 + background `Workflow.resume`. 409 `run_not_resumable` for `completed` and `awaiting_approval` (with the CLI's hint text), 409 `run_active` while a process holds the lease. | Automatic resume on API start (hides failures; a run could loop). |
| OD-146 | Run results | `GET /api/v1/runs/{id}/results` (viewer): `narrative`, `narrative_provenance`, `friction_scores`, `critical_steps`, `insights` (each with `provenance`), `prioritized_fixes`, `llm_usage` (calls, tokens, cost), `ingestion_results`, `ingestion_pending_review` (file name only, never the server path), `errors` (worker, message, time; at most 50). Values come from the checkpoint state unchanged. `GET /journeys/{id}/insights` stays as it is. | Adding these fields to `GET /runs/{id}` (makes the run list/detail heavy); reading `last_run.json` (one run only, F-79). |
| OD-147 | Provenance recording | The insight worker stores the gateway metadata it now drops (F-73) in a new state key `insight_provenance: {insight_id: {source: "llm"\|"fallback", model, provider, generated_at}}`; the report worker stores `narrative_provenance: {source, model, generated_at}`. The insight dicts themselves are unchanged (they go to ChromaDB metadata and the report contract). Runs created before this Spec show provenance **"not recorded"**. Token usage stays a run total (`llm_usage`). | Nested provenance inside each insight (ChromaDB metadata must be flat; the report input contract would change); reading audit JSONL files from the API (large, per-process log files, not an API data store). |
| OD-148 | Ingestion with validation | Two operations on top of a split of `ingest_file` into `parse_file` (parse + normalise, returns rows and counts) and `write_rows` (unchanged append/replace logic); `ingest_file` and `cji-ingest-json` keep their behaviour and output. (1) `POST /api/v1/ingestions/validations` (operator): raw file body (`application/json`, `application/x-ndjson`, `text/csv`), query `filename`, `root_key?`, repeated `map=your_col=cji_col`; limit `CJI_API_MAX_UPLOAD_BYTES` (default 10 MiB, 413 above). It writes nothing to the event store and returns `validation_id`, detected format, rows parsed / accepted / dropped (unknown event type) / repaired (bad timestamp), steps and event types found versus the journey's steps, up to 5 sample rows without `user_id`/`session_id`, `expires_at`. The upload is kept under `data/ingestion_uploads/` for 1 h. (2) `POST /api/v1/ingestions` (`Idempotency-Key`; body `{validation_id, write_mode: "append"\|"replace"}`; append = operator, **replace = admin**): writes the validated rows to `tracking_events`, deletes the upload, returns rows written and rows already stored. Without a database URL both answer 503 `database_unavailable`. The LLM ingestion path (`cji --ingest`) stays CLI-only; its results and pending reviews are shown read-only in run results (OD-146), and F-76 stays open. | One-step upload like Streamlit (no feedback before writing, F-75); multipart forms (needs `python-multipart`, a new dependency); re-uploading the file to commit (the user would have to pick it again). |
| OD-149 | Reports | Preview: the existing `/reports/[id]` route (API CSP plus `sandbox`), opened from run and report pages in a new tab. Download: `GET /api/v1/reports/{id}/content?disposition=attachment` adds `Content-Disposition: attachment; filename="<report file name>"`; Next.js route `/reports/[id]/download` passes it through. A report list page `/reports` with journey filter and paging (Streamlit shows 8, unpaged). | An in-page iframe (the report CSP has `frame-ancestors 'none'` by design); downloading via a client-side Blob (the token would have to reach the browser). |
| OD-150 | Pages | `/journeys/[id]`: window selector (days or minutes by mode), funnel bars, step metrics table, friction table, links per step. `/journeys/[id]/steps/[stepId]`: drill-down (metrics, friction score with signals and confidence, funnel position, latest run's insight for the step, events filtered by step and type with cursor paging). `/runs/new`: start form. `/runs/[id]`: status, steps, failure, approve / resume actions, results (narrative, insights with provenance, fixes, usage, ingestion), report links. `/ingest`: upload → validation summary → confirm. `/reports`: list. Navigation gains Ingest and Reports. | One page per Streamlit page (Streamlit mixes KPIs, audience and heatmaps into the journey page, F-78). |
| OD-151 | Mutations in Next.js | Server Actions only (the token stays on the server). Each action form carries an `Idempotency-Key` created when the page renders (`crypto.randomUUID()`), so a double submit or a retry after a network error reuses the key. Next.js' built-in Origin check applies. Buttons are shown to every role; for a role below the required one they are disabled with the text "Requires the operator role" (the API still enforces it). After a 202 the run page refreshes every 5 s while the run is `running` or `approved` and stops on any other status or after 10 min. Server Action body limit raised to the upload limit (`serverActions.bodySizeLimit`). | Route handlers called from client fetch (needs extra CSRF handling); hiding buttons by role (users do not learn why an action is missing); WebSockets/SSE for progress (no event stream in the API). |
| OD-152 | Charts | No chart library: funnel and score bars are HTML/CSS with the numeric value always shown as text, inside tables with captions. | Plotly/Recharts (large client bundles; accessibility work per chart). |
| OD-153 | Error, empty, permission states | One matrix (design §6) applied to every data region and action: loading; empty with the next step to take ("No runs yet — start one" for operators); API problems through ProblemPanel (title, detail, code, request id, Retry; 429 shows the wait); 403 role → "Requires the operator role"; 403/404 journey outside the token → not found (the API answers 404 to avoid leaking journeys); 409 conflicts shown next to the action with the server's detail; 503 with Retry; validation errors listed per field. | Generic error toasts. |
| OD-154 | Tests | **Python contract tests** (`tests/test_api_parity.py`): every new operation's success, role, idempotency replay, conflict, limit and problem responses with fakes for the workflow and the event store; provenance recording in the workers; `parse_file`/`ingest_file` equivalence on the repository's sample files. **Vitest** for every new view and state. **Playwright** one spec file per feature against the fixture API (extended with the new operations and failure switches), including axe checks. **Live phase** of the gate: `cji-api` in demo mode with MCP servers and an offline LLM (fallback outcomes), operator and viewer tokens: start a run → awaiting approval → approve → completed with fallback provenance shown; resume of a failed run; validation of a sample file (no write: the gate never uses a real database URL); report preview and download; viewer permission states. **Parity check** script comparing the Next.js-rendered values (via the API) with CLI `--status`, the checkpoint state and `last_run.json` of one run, and API metrics with a direct service call (§4). | Live tests that write to PostgreSQL (the configured database is the real Supabase project). |
| OD-155 | Migration, rollback, fallback | New `docs/frontend-migration.md`: how to run Streamlit (8501), the API (8006) and Next.js (3000) side by side; the feature map with each intentional difference; the tolerance table; rollback (stop Next.js, nothing else changes; the new API operations can be disabled with `CJI_API_WRITE_OPERATIONS=false`, which makes them answer 404); the operational fallback (Streamlit and CLI keep every capability); the removal checklist (§5) with its current status. README links it. | Removing or redirecting Streamlit now (criteria not met, §5). |
| OD-156 | Streamlit and CLI | Unchanged in behaviour. The only shared-code changes are the `ingest_file` split (OD-148, same results) and the provenance state keys (OD-147, new keys only). Streamlit gains no API calls. | Rewriting Streamlit pages on top of the API (out of scope; it is the fallback). |
| OD-157 | Background runs and restarts | A run started or continued by the API lives in the API process. On shutdown the API cancels its tasks; the run keeps its checkpoint and lease expiry, shows `active: false` after the lease expires, and can be resumed (OD-145) from Next.js or the CLI. `GET /health/details` gains `active_runs` (count). | Blocking the request until the run finishes (minutes; proxies time out). |

## 3. Requirements

1. **R1 Contract first:** for every feature the operation, schema, roles and problems are in the OpenAPI snapshot
   before the UI uses them; the snapshot, `schema.ts` and the fixture API agree (`api:check`, typed fixture).
2. **R2 Ingestion:** an operator can upload a file up to 10 MiB, see the validation summary (format, counts of
   parsed, accepted, dropped and repaired rows, steps and event types against the journey, samples without user or
   session ids) before anything is written, then append it; replace requires admin and an explicit confirmation.
   Run results show ingestion results and pending reviews from `cji --ingest`.
3. **R3 Journey and funnel:** the journey page shows funnel users, drop-off and step metrics for a chosen window,
   with the API's values unchanged (no recalculation in TypeScript, OD-140).
4. **R4 Friction drill-down:** each step links to a page with its metrics, friction score, signals, confidence,
   critical flag, the latest insight for the step and its events (operators; viewers see the permission state).
5. **R5 Insights and provenance:** operators can start a run; every insight and the narrative show their source
   (LLM with model and provider, fallback, or not recorded) and the run shows LLM usage totals.
6. **R6 Approval and resume:** operators can approve runs awaiting approval and resume failed or orphaned runs;
   double submits do not create a second effect; progress is visible until the run stops.
7. **R7 Reports:** preview in a sandboxed page and download as a file, from run pages and a paged report list.
8. **R8 States:** every data region and action has loading, empty, error-with-retry and permission states
   (design §6), each covered by a component test; Playwright covers at least one of each per feature.
9. **R9 Parity evidence:** the parity check (§4) passes for the gate's run; Streamlit differences are measured and
   listed in `docs/frontend-migration.md`.
10. **R10 Security:** new write operations require `Idempotency-Key` and the stated role; uploads are size-limited,
    stored under the data directory with generated names and deleted after commit or expiry; no server path, user
    id or session id leaves the API in validation output; no token reaches the browser; CSP unchanged.
11. **R11 Accessibility:** no serious or critical axe violations on any new page; forms labelled; bars and states
    carry text.
12. **R12 No regressions:** the Python suite, ruff/mypy/bandit baselines, Vitest, Spec 13 smoke tests, `npm audit`
    and the CLI/Streamlit behaviour (`last_run.json` keys, exit codes) stay as before or better.

## 4. Parity tolerances

| Value | Compared surfaces | Tolerance |
|---|---|---|
| Run status, steps, failure code, `human_approved` | Next.js ↔ API `GET /runs/{id}` ↔ CLI `--status` | identical |
| Friction scores (`score`, `is_critical`, `signals`, `confidence`), `critical_steps` of a run | Next.js ↔ API results ↔ checkpoint state ↔ `last_run.json` (same run) | identical; display rounding only (confidence to 2 decimals) |
| Insights, prioritized fixes, narrative of a run | same | identical text and order |
| Live step metrics, funnel, completion % | API ↔ direct `services.analytics` call with the same window | identical; display: percentages 1 decimal, counts as integers, dwell in seconds with 1 decimal |
| Live friction scores | API ↔ `cji.analytics.friction.score_steps` on the same metrics | identical |
| Streamlit SQL panels and fallback friction/insights | Streamlit ↔ API | not ported; differences measured and documented (F-70, F-71, F-72, F-77) |
| Ingestion counts | `/ingestions/validations` ↔ `parse_file` ↔ `cji-ingest-json` rows written on an empty table | identical |

## 5. Streamlit and CLI removal criteria

Neither is removed in this Spec. Removal needs all four of the prompt's conditions; this Spec's target per
condition:

| Condition (prompt) | Target in Spec 14 | Still open after Spec 14 |
|---|---|---|
| Core results match documented tolerances | Parity check (§4) passes for the gate run | Repeat on realtime (PostgreSQL) data, which the gate cannot use |
| Migration and rollback instructions exist | `docs/frontend-migration.md` (OD-155) | — |
| Browser and integration tests pass | Vitest, Playwright fixture and live phases, Python contract tests | — |
| Users have an operational fallback | Streamlit and CLI unchanged | Streamlit-only features (F-78) have no Next.js equivalent; a decision to port or drop them is needed before Streamlit can go |

## 6. Out of scope

Business KPIs, audience and heatmap panels, the track selector and demo data generation (F-78); resolving
low-confidence LLM mappings (F-76); multi-user identity (OIDC) and per-user sign-in rate limits (Spec 15); changing
the engine's friction formula or Streamlit's numbers; CLI changes.
