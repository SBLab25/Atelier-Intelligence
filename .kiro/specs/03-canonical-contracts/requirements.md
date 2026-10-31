# Spec 03 — Canonical Domain Contracts: Requirements

| | |
|---|---|
| Spec | **03 Canonical Contracts** (`kiro_upgrade_guide.md` §7) = **Prompt 2** (`kiro_upgrade_prompts.md`) |
| Scope | One authoritative contract layer for events, identifiers, metrics, friction, insights, reports and workflow status (refactoring.md R-06; baseline D-06, D-15, D-31) |
| Starts from | Spec 02 working tree (`02-p0-security/evidence/spec02-tracked.patch`) |
| Version control | **No commits or pushes** (owner, 2026-10-27). Each Spec saves a patch file as its rollback point. |
| Status | **Draft, awaiting owner review.** No code changed for this Spec yet. |

## 1. Current behaviour (verified 2026-10-27)

Seven separate definitions of the same data exist, and some disagree.

| Concept | Where it is defined today | Disagreement |
|---|---|---|
| Browser event | `collector/models.py::TrackerEvent` (strict: event type, duration ≥ 0, URL sanitised, `journey_id`) | **Not used at runtime.** Only tests import it. |
| | `collector/api.py::EventItem` / `BatchPayload` (the model the endpoint actually uses) | Lax: any `event_type`, no `duration_ms`, field is `journey_name`, metadata required, no URL sanitising, no batch size limit |
| | `tracker/tracker.js::makeEvent` (what browsers send) | Sends `journey_name` and `element_selectors`, no `duration_ms`. A batch is up to 20 events. |
| Stored event | `state.py::JourneyEvent` (TypedDict, metadata `str`) | — |
| | `mcp_servers/ingestion_intelligence_server.py::CanonicalEvent` | Unknown `event_type` **silently becomes** `page_view`; metadata JSON string |
| | `data/events.parquet` columns | `metadata VARCHAR`, `timestamp TIMESTAMPTZ`, `duration_ms BIGINT` |
| | `live_events` table (collector) | Column `journey_name`, `element_selectors`, `metadata JSONB`, no `duration_ms` |
| Event types | `collector/models.py::ALLOWED_EVENT_TYPES` (8) | — |
| | `ingestion_intelligence_server.py::CANONICAL_SCHEMA` + `ALLOWED_EVENT_TYPES` (same 8, separate copy) | — |
| | `tools/ingest_json.py::VALID_EVENT_TYPES` (**12**: adds `drop_off`, `session_start`, `session_end`, `scroll`) | Writes non-taxonomy types into `tracking_events` |
| Journey and step identifiers | `config.JOURNEY_CONFIG` (8 steps, default name `onboarding`) | Tracked Parquet holds only `user_onboarding` (D-31, cause of B-03). Docs list 6 steps (D-15). |
| Step metrics, friction score, insight, worker status | `state.py` TypedDicts | No validation anywhere. `WorkerStatus` says `success\|error`, but the ingestion worker emits `skipped` and `partial`. |
| Insight categories and effort | `guardrails/output_validator.py` constants | Insight shape also implied by `insight_server.py` (adds `insight_id`, `priority`, `priority_score`); the dashboard uses its own `issue_description` shape |
| Funnel, narrative, report result | Untyped dicts in `journey_data_server.py`, `report_server.py` | — |
| Workflow errors | Workers append `{"worker","error","ts"}` dicts | `supervisor.py:55` appends a **plain string** to the same list |
| Route targets | `agents/supervisor.py::VALID_WORKERS` (Spec 02) | — |

## 2. Owner decisions needed (defaults used unless changed)

| ID | Decision | Default proposed |
|---|---|---|
| OD-9a | Canonical journey step set | The **8 steps** in `config.JOURNEY_CONFIG`; they match the tracked data and the generator. The 6-step documents are stale (not edited here). |
| OD-9b | Canonical demo journey ID | Change the `JOURNEY_NAME` default to **`user_onboarding`**, matching the tracked Parquet and the README tracker example. This fixes B-03. If your local `.env` sets `JOURNEY_NAME`, its value still wins (checked in T0, value reported only if non-secret). |
| OD-20 | Unknown event types | **Collector rejects** them (HTTP 422). **File ingestion keeps** its documented coercion to `page_view` but counts every coerced record in its result. **`ingest_json.py`** maps its known aliases to canonical types and skips anything else, with counts. |
| OD-21 | Location of the contract layer | `cji_agent/domain/`, as proposed in `refactoring.md` §7 |

## 3. Requirements

| ID | Requirement | Intended behaviour change |
|---|---|---|
| RC-01 | `domain/events.py` SHALL be the only definition of the event taxonomy (`ALLOWED_EVENT_TYPES`), URL sanitising, the browser event (`TrackerEvent`), the batch (`EventBatch`) and the stored event record (`EventRecord`). | — |
| RC-02 | `TrackerEvent` SHALL accept the browser wire format (`journey_name`, `element_selectors`, no `duration_ms`) and the documented one (`journey_id`). The canonical field is `journey_id`. | — |
| RC-03 | The collector SHALL validate requests with `EventBatch`/`TrackerEvent` and drop `EventItem`/`BatchPayload`. Persistence SHALL go through one explicit conversion to the `live_events` row (`journey_id` → `journey_name` column, metadata → JSON). | Unknown event types, negative durations, empty batches and batches over 100 now get 422. Tracker-generated batches are unaffected (proved by a fixture of the exact `makeEvent` shape). URLs are sanitised server-side. |
| RC-04 | File ingestion SHALL validate output as `EventRecord` and take event types from the domain. Its `CanonicalEvent` stays only as an **explicit adapter** (documented coercion), and the number of coerced records SHALL appear in the ingestion result. | Ingestion results gain a `records_coerced` count |
| RC-05 | `tools/ingest_json.py` SHALL use the domain taxonomy: known aliases mapped, others skipped and counted. | Non-taxonomy types are no longer written to `tracking_events` |
| RC-06 | `domain/journeys.py` SHALL define journey and step identifiers (non-empty, trimmed, ≤ 128 characters, no control characters) and validate `JOURNEY_CONFIG` where it is used. `config.py` keeps stdlib-only imports (its own rule 6). | Default `JOURNEY_NAME` → `user_onboarding` (OD-9b) |
| RC-07 | `domain/metrics.py` SHALL define `StepMetrics`, `FunnelStep`, `FunnelResult` and `FrictionScore`. `domain/insights.py` SHALL define `InsightDraft` (validator output), `Insight` (after prioritisation), `RankedFix`, the category and effort sets, `Narrative` and `ReportResult`. `domain/runs.py` SHALL define `WorkerStatus`, `WorkflowError`, `ApprovalState`, `VALID_WORKERS`. | — |
| RC-08 | Analytics and workflow records SHALL be `TypedDict`s validated with pydantic `TypeAdapter`s. They stay plain dicts at runtime, so LangGraph state and MCP JSON are unchanged. | None |
| RC-09 | `state.py`, `guardrails/output_validator.py`, `agents/supervisor.py` and `collector/models.py` SHALL import from `domain/`. Old import paths keep working as re-exports. | None |
| RC-10 | Workers SHALL validate MCP results at the worker boundary (step metrics, friction scores, insights, report result) in **check-only** mode: an invalid result becomes a recorded `WorkflowError`; a valid one is passed on unchanged. | Malformed tool output is reported instead of propagating |
| RC-11 | The supervisor's iteration-cutoff error SHALL be a `WorkflowError` dict, not a string. | `errors` entries all share one shape; `main.py` already prints both |
| RC-12 | Event taxonomy, friction weights and baselines, approval semantics and routing order SHALL NOT change. | — |
| RC-13 | Tests SHALL cover serialisation round trips, both wire variants, invalid input, the tracked Parquet rows, real journey-data, friction and report outputs, and single-source identity (each old name *is* the domain object). | — |

## 4. Non-goals

- Collector response contract, partial-batch results, duplicate counting → Spec 07 (Prompt 6). The unused `CollectResponse`, `HealthResponse` and `LiveStatsResponse` stay in `collector/models.py`, marked inactive.
- Error accumulation semantics. `errors` has no reducer, so most workers overwrite earlier errors (found in this survey) → Spec 09. Logged as F-02.
- The dashboard's own fallback insight shape (`issue_description`) → Spec 14 (parity); recorded as an explicit exception.
- Renaming the state key `journey_name` to `journey_id` (workflow-wide) → Spec 09.
- Regenerating `events.parquet`; the dead `"completion"` branch in the generator → Spec 06.
- Editing stale documents (6-step journey, contract docs), except where this Spec makes a statement false: `.env.example` `JOURNEY_NAME`.

## 5. Acceptance criteria (Prompt 2)

1. Every changed caller uses the canonical contracts (identity tests prove the re-exports are the same objects).
2. Old representations (browser wire `journey_name`, documented `journey_id`, Parquet rows, ingestion coercion, string-era supervisor errors) have compatibility tests.
3. mypy reports no new errors in changed files; the `domain/` package is mypy-clean.
4. No duplicate active schema remains without a written adapter reason (design §4 lists the remaining ones).
5. Golden journey-data snapshot identical to Spec 02's. Demo pipeline still yields 8 metrics and 4 critical steps, and now also with the **default** `JOURNEY_NAME` (B-03 fixed).
6. Full unit suite: no new failures beyond F-01.
