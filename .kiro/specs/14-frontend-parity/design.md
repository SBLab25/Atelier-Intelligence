# Spec 14 — Frontend Parity: Design

Decisions are in `requirements.md` §2 (OD-142 to OD-157). This document describes how they are built. Status:
draft, waiting for review.

## 1. Overview

```
Browser ──(cookie cji_session)──► Next.js server (frontend/, port 3000)
                                   │  Server Components: loaders → Result<T>
                                   │  Server Actions: start / approve / resume / validate / ingest
                                   ▼  Bearer token, X-Request-ID, Idempotency-Key
                                 cji-api (port 8006) ── services ── Workflow (checkpoints) ── MCP servers
                                   │                      └── repositories (Parquet / PostgreSQL)
                                   └── background tasks: Workflow.start / resume (OD-144, OD-145, OD-157)
Streamlit (8501) and the CLI keep their own paths, unchanged (OD-156).
```

Work goes feature by feature. Each feature follows the same order: contract (OpenAPI) → API and tests → regenerate
schema → fixture API → views and Vitest → Playwright → parity notes in `docs/frontend-migration.md`.

## 2. API changes (`cji_agent/src/cji/api/`)

All new routes use the existing helpers (`require_role`, `visible_journey`, `errors(...)`, `only_query`,
`IdempotencyStore`, problem codes). New problem codes are added to `errors.py` with titles.

### 2.1 Runs (`routes/runs.py`)

| Operation | Role | Request | Responses |
|---|---|---|---|
| `POST /runs` (`startRun`) | operator | `Idempotency-Key`; JSON `StartRunRequest {journey_id, auto_approve=false, window_days?, window_minutes?}` (extra forbidden; only one window field) | 202 `Run`; 400 key; 403 role or journey outside token; 404 `journey_not_found`; 409 `run_capacity_reached`; 413; 415; 422; 503 `services_unavailable` |
| `POST /runs/{id}/resume` (`resumeRun`) | operator | `Idempotency-Key`; empty body | 202 `Run`; 404 `run_not_found`; 409 `run_not_resumable` (detail as the CLI text), `run_active`, `run_capacity_reached`; 503 |
| `GET /runs/{id}/results` (`getRunResults`) | viewer | — | 200 `RunResults`; 404; 503 |

Start: `RunService.start(journey, window, auto_approve)` builds `initial_state(...)` exactly like `main.py`
(mode from settings, `collector_url` from the service registry, no pending files), creates the run id, then hands
`Workflow.start(state, run_id=…)` to a background task. To answer 202 with a real `Run`, the service first stores
the initial checkpoint: `Workflow.start` is split internally into `create(state, run_id)` (stores the initial state
and run record, audit `running`) and `drive(run_id)`; `start()` keeps calling both, so the CLI is unchanged.

Capacity: `ApiContext.tasks` already tracks background tasks; a `RunSlots` counter (size
`CJI_API_MAX_ACTIVE_RUNS`, default 1, range 1–8) is taken before `create` and released when the task ends. The
approval continuation (Spec 12) also takes a slot; if none is free the approval still answers 202 and the
continuation waits for a slot (approval must not fail after the state changed).

MCP check: `ping_all_servers()` with the existing timeout; failure → 503 `services_unavailable` with the failing
service names (no URLs).

Resume: allowed when status is `failed`, or `running`/`approved` and `Lease.holder(run_id) is None`. Errors from
`Workflow.resume` map: `RunNotResumable` → 409 `run_not_resumable`, `RunLeased` → 409 `run_active`.

`RunResults` (new schema, all fields required, empty lists allowed):

```
run_id, journey_id, status
narrative: str | null
narrative_provenance: Provenance
friction_scores: list[FrictionScore]; critical_steps: list[str]
insights: list[InsightWithProvenance]        # Insight + provenance: Provenance
prioritized_fixes: list[Fix]                 # insight_id, step_id, title, suggested_fix, fix_effort, priority, priority_score, category, root_cause
llm_usage: {calls, input_tokens, output_tokens, cost_usd}
ingestion_results: list[{source_file (base name), detected_source, confidence, records_written, records_skipped, status, cached_mapping}]
ingestion_pending_review: list[{file_name, confidence, flagged_at, detected_source}]
errors: list[{worker, message, ts}]          # newest 50; message scrubbed as in state
Provenance: {source: "llm" | "fallback" | "not_recorded", model: str | null, provider: str | null, generated_at: str | null}
```

### 2.2 Ingestion (`routes/ingestions.py`, `services/ingestion.py`)

| Operation | Role | Request | Responses |
|---|---|---|---|
| `POST /ingestions/validations` (`validateIngestion`) | operator | raw body; `Content-Type` json / x-ndjson / csv; query `filename` (1–128, extension `.json/.ndjson/.jsonl/.csv`), `root_key?`, `map` (repeatable `src=dst`, dst in the CJI columns, ≤ 20) | 201 `IngestionValidation`; 413 `upload_too_large`; 415; 422 `ingestion_unreadable` (no records, bad JSON/CSV) or field errors; 503 `database_unavailable` |
| `POST /ingestions` (`createIngestion`) | operator; admin for `replace` | `Idempotency-Key`; JSON `{validation_id, write_mode}` | 201 `Ingestion`; 403 role; 404 `validation_not_found` (unknown or expired); 409 `validation_used`; 503 |

Body limit: `ApiGate` gets a per-path override table; only `/api/v1/ingestions/validations` uses
`CJI_API_MAX_UPLOAD_BYTES` (default 10 MiB, range 1 KiB–50 MiB). The body is streamed to
`data/ingestion_uploads/<validation_id>.<ext>` (file name from `secrets.token_urlsafe(18)`, never from the client),
with a JSON sidecar `{sha256, filename, root_key, map, created_at, expires_at, token_id, used}`. Validations
belong to the token that created them (another token gets 404). Expired files are deleted at startup and before
each validation.

`tools/ingest_json.py` split (behaviour of `ingest_file` and `cji-ingest-json` unchanged):

```python
@dataclass
class ParseStats: format: str; parsed: int; accepted: int; dropped_event_type: int; repaired_timestamp: int
def parse_file(input_path, col_map=None, root_key=None, chunk_size=100_000) -> tuple[pd.DataFrame, ParseStats]
def write_rows(df, *, replace=False) -> int            # the current _write_tracking_events with engine creation
def ingest_file(...)  # = parse_file + write_rows, same signature, same return, same logs
```

`_finalise` returns its counts instead of only logging them (the log lines stay). `_detect_and_yield` reports the
detected format name.

`IngestionValidation`: `validation_id, filename, format, rows {parsed, accepted, dropped_event_type,
repaired_timestamp}, steps_found [{step_id, rows, in_journey}], journey_steps_missing [..], event_types [{event_type,
rows}], samples (≤5 rows: step_id, event_type, timestamp, duration_ms, url), expires_at`.
`Ingestion`: `validation_id, write_mode, rows_written, rows_already_stored, destination: "tracking_events"`.

### 2.3 Reports (`routes/reports.py`)

`GET /reports/{id}/content` gains `disposition: "inline" | "attachment"` (default `inline`). `attachment` adds
`Content-Disposition: attachment; filename="<file>"; filename*=UTF-8''<file>` (report file names are generated, but
the value is still quoted and checked against `[A-Za-z0-9._-]`).

### 2.4 Other

- `GET /health/details` gains `active_runs: int`.
- `CJI_API_WRITE_OPERATIONS` (default `true`): when `false`, `startRun`, `resumeRun`, `validateIngestion` and
  `createIngestion` are not mounted (404) — the rollback switch of OD-155. Approval (Spec 12) is not affected.
- Settings: `CJI_API_MAX_ACTIVE_RUNS`, `CJI_API_MAX_UPLOAD_BYTES`, `CJI_API_WRITE_OPERATIONS` in `settings/load.py`,
  `model.py`, the known-keys list and `.env.example`.

## 3. Engine changes (provenance, OD-147)

- `state.py`: `insight_provenance: dict[str, dict]` and `narrative_provenance: dict` (merge reducers not needed:
  each written by one worker); `initial_state` adds `{}` for both.
- `insight_worker`: after `_unwrap_insight`, `provenance[insight_id] = {"source": "llm" if info.outcome == "ok"
  else "fallback", "model": info.model or None, "provider": info.provider or None, "generated_at": utc_now()}`;
  `info is None` → `not_recorded`. Returned as `insight_provenance`.
- `report_worker`: returns `narrative_provenance` with the values it already passes to `export_report`.
- `step` fallbacks: on failure the keys are `{}` (shown as not recorded).
- Old checkpoints without the keys → `not_recorded` (API layer).

## 4. Frontend (`frontend/src/`)

New and changed files (Spec 13 structure kept):

| Path | Purpose |
|---|---|
| `lib/api/loaders.ts` | new loaders: `loadMetrics(id, window)`, `loadFriction`, `loadEvents(id, filters, cursor)`, `loadRunResults`, `loadReports(filters, cursor)`, `loadInsights(id, runId?)` |
| `lib/api/mutations.ts` | `startRun`, `approveRun`, `resumeRun`, `validateIngestion`, `createIngestion`: typed calls returning `Result<T>`, with `Idempotency-Key` |
| `lib/idempotency.ts` | key creation and format check (`[A-Za-z0-9._-]{8,64}`) |
| `lib/roles.ts` | `can(me.role, "operator")` for UI state only |
| `lib/format.ts` | percentage, count, duration, timestamp formatting (the only place numbers are rounded, §4 tolerances) |
| `app/(protected)/journeys/[journeyId]/page.tsx` | window selector (GET form), funnel, metrics, friction |
| `app/(protected)/journeys/[journeyId]/steps/[stepId]/page.tsx` | drill-down |
| `app/(protected)/runs/new/page.tsx`, `runs/actions.ts` | start form and Server Actions (start, approve, resume) |
| `app/(protected)/runs/[runId]/page.tsx` | detail with actions, results, provenance |
| `app/(protected)/ingest/page.tsx`, `ingest/actions.ts` | upload → summary → confirm |
| `app/(protected)/reports/page.tsx` | report list |
| `app/reports/[reportId]/download/route.ts` | passes the attachment response through (same session checks as the preview route) |
| `components/` | `FunnelBars`, `MetricsTable`, `FrictionTable` (extends `FrictionSummary`), `EventsTable`, `InsightCard`, `ProvenanceBadge`, `UsageSummary`, `ActionForm` (submit with pending state, problem display, disabled-by-role text), `RunAutoRefresh` (client component: `router.refresh()` every 5 s, max 10 min, pauses when the tab is hidden), `UploadForm`, `ValidationSummary`, `Pager` |
| `views/` | `journey-detail.tsx`, `step-detail.tsx`, `run-detail.tsx` (extended), `ingest.tsx`, `reports.tsx` |
| `next.config.ts` | `experimental.serverActions.bodySizeLimit = "10mb"` |
| `components/Nav.tsx` | Ingest and Reports links |

Server Actions: each checks the session (`requireSession`), validates its form data (no trust in hidden fields
except the idempotency key format), calls the mutation, and returns a serialisable state
`{ok, problem?, data?}` to `useActionState`. A 401 deletes the session and redirects (Spec 13 behaviour). The
idempotency key is rendered into the form by the Server Component; after a successful action the page re-renders
with a new key.

File upload: `<input type="file" accept=".json,.ndjson,.jsonl,.csv">`, size checked on the client for an early
message and again on the server (the API is the authority). The action reads `File.arrayBuffer()` and forwards the
bytes with the content type derived from the extension.

Business logic stays out of TypeScript (OD-140): the step page reads `is_critical`, signals and confidence from the
API; the funnel width is `users / max(users)` only for drawing, with the API's numbers as text.

## 5. Fixture API and tests

- `e2e/fixture-api.ts`: new operations typed against `schema.ts`; in-memory runs move
  `running → awaiting_approval → approved → completed` on a timer; switches through a test-only header
  (`x-fixture-fault: 503|409|429|403`) to drive error states; idempotency replay behaviour like the API.
- Playwright specs: `ingest.spec.ts`, `journey.spec.ts`, `friction.spec.ts`, `insights.spec.ts`,
  `approval.spec.ts`, `reports.spec.ts`, `states.spec.ts` (viewer token: disabled actions, events permission panel;
  401 expiry; 404; 503 with retry; 409 shown at the action), each with an axe check. `smoke.spec.ts` stays.
- Live mode (`E2E_LIVE_API_URL`, `E2E_LIVE_TOKEN`, new `E2E_LIVE_VIEWER_TOKEN`): the specs marked live run against
  the real API; fault switches are skipped with an `if` (G-1 lesson).
- Python: `tests/test_api_parity.py` (contract per operation, fakes for `RunService`/`Workflow`, a sqlite URL for
  `write_rows`), `tests/test_ingest_parse.py` (`parse_file` vs the current `ingest_file` output on files in
  `Dataset/` and generated cases: unknown event type, bad timestamp, generic map, root key),
  `tests/test_provenance.py` (insight and report workers with fake MCP results: ok, fallback, no info).
- OpenAPI snapshot test (Spec 12) updated by regenerating the snapshot; `npm run api:check` must pass.

## 6. State matrix (OD-153)

| Region / action | Loading | Empty | Problem | Permission |
|---|---|---|---|---|
| Journey metrics, funnel, friction | `aria-busy` placeholder | "No events in this window" + window selector | ProblemPanel + Retry | 404 journey → not found page |
| Step drill-down events | placeholder | "No events for this step" | ProblemPanel | viewer: "Events require the operator role" (403 from API) |
| Run results | placeholder | per section: "No insights (no critical steps)" / "Report not generated yet" | ProblemPanel | 404 run |
| Insight provenance | — | "Provenance not recorded (run created before Spec 14)" | — | — |
| Start / approve / resume | button pending text, disabled | — | inline problem at the form (409 detail, 503 services) | disabled + "Requires the operator role" |
| Ingest validate / write | pending, progress text | "File has no records" (422 detail) | inline problem; 413 shows the limit | viewer: page explains operator role; replace option disabled for non-admins |
| Reports list | placeholder | "No reports yet" | ProblemPanel | journey filter outside token → 403 text |
| Session | — | — | 401 → `/auth/expired` | — |

## 7. Parity check (`evidence/scripts/parity_check.py`)

Inputs: API URL and token, a run id, the CLI and checkpoint DB used by the gate. Steps: `cji --status
--thread-id <id>` JSON; `Workflow.inspect` values; `last_run.json` when the run was completed by the CLI (the gate
runs one CLI run for this); API `GET /runs/{id}`, `/runs/{id}/results`, `/journeys/{id}/metrics` and `/friction`;
direct `services.analytics.journey_metrics` and `analytics.friction.score_steps` calls. Compares per §4 and writes
`parity.json` plus a readable `parity.txt`. Rendering parity (Next.js shows exactly the API's values) is checked in
Playwright by reading the same API JSON in the test and comparing table cells after `lib/format.ts` formatting.

Streamlit measurement (report-only): `streamlit_diff.py` repeats the aggregations of Streamlit's
`load_journey_df` and `compute_friction_from_db` (PostgreSQL SQL, so re-written in pandas with a test against
the SQL text's columns) on the gate's demo Parquet data, with no PostgreSQL connection, and lists the per-step
differences against the engine in `docs/frontend-migration.md`.

## 8. Gate (`evidence/scripts/gate_spec14.ps1`)

Extends the Spec 13 gate: Python suite (expect 1169 + new tests), ruff/mypy/bandit against the baselines,
OpenAPI snapshot, `npm run typecheck`, `lint`, `test`, `test:e2e` (fixture), `bundle:scan`, `npm audit`; live phase
with a temporary `CJI_HOME`, demo data, MCP servers started as in the Spec 12 gate, offline LLM (fallback),
operator and viewer tokens, `cji-api.exe`, Next.js production server, live Playwright specs, `parity_check.py`;
one CLI `--run --auto-approve` for the `last_run.json` comparison. No step sets or reads
`SUPABASE_DATABASE_URL`; the live phase clears `DATABASE_URL`/`SUPABASE_DATABASE_URL` in its process environment,
so ingestion is validated only (write tested with sqlite in pytest).

## 9. Documentation

`docs/frontend-migration.md` (OD-155), `frontend/README.md` (new pages, actions, upload limit, live test
variables), root `README.md` (link, new settings), `.env.example` (new API keys), `openapi/v1.json` (regenerated).

## 10. As implemented (differences from this design)

Details in `tasks.md` (D-1 to D-7, G-1 to G-3).

- §2.1: `Workflow.create`/`drive` were not split. `start_run` runs `start()` as a background task and polls the run
  index and checkpoint (up to 10 s) for the `Run` to return. There is no `RunSlots` class: capacity uses the
  `active_runs` set, and the approval continuation counts in it but is never refused.
- §2.4: with `CJI_API_WRITE_OPERATIONS=false`, `POST /runs` answers 405 (because `GET /runs` exists); the others 404.
- §3: provenance also has `reason`; `source` can be `not_recorded`.
- §6: the UI hides the events region for viewers by role and does not call the events API.
- Demo repository (G-1): DuckDB connection use is serialised with a lock, because the API serves the journey page's
  parallel requests from several threads.
