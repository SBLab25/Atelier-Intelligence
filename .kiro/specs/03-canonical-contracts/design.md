# Spec 03 — Canonical Domain Contracts: Design

## 1. Package layout

```text
cji_agent/domain/
  __init__.py      # re-exports the public names below
  events.py        # ALLOWED_EVENT_TYPES, sanitise_url, TrackerEvent, EventBatch, EventRecord,
                   # to_record(), to_live_events_row(), EVENT_RECORD
  journeys.py      # JourneyId, StepId, JourneyDefinition, journey_from_config()
  metrics.py       # StepMetrics, FunnelStep, FunnelResult, FrictionScore (+ TypeAdapters)
  insights.py      # INSIGHT_CATEGORIES, FIX_EFFORTS, InsightDraft, Insight, RankedFix,
                   # Narrative, ReportResult (+ TypeAdapters)
  runs.py          # WorkerStatus, WorkflowError, ApprovalState, VALID_WORKERS, workflow_error()
  validation.py    # check(adapter, value, worker) -> WorkflowError | None
```

The domain package imports only pydantic and the standard library: no FastAPI, DuckDB, SQLAlchemy,
LangGraph or `requests` (refactoring.md §7). A test enforces this.

## 2. Modelling choices

| Kind | Form | Why |
|---|---|---|
| Boundary input (browser events, batches) | pydantic `BaseModel` with field validators | Rejects bad input with field-level errors; existing tests use attribute access |
| Records flowing through LangGraph state and MCP JSON | `TypedDict` + module-level `TypeAdapter` | One definition is both the static type and the validator; runtime values stay plain dicts, so state, checkpoints and MCP payloads are unchanged |
| Constrained strings | `Annotated[str, StringConstraints(...)]` | Reused by both forms |

`TrackerEvent.journey_id` uses `validation_alias=AliasChoices("journey_id", "journey_name")`. Then
`model_dump(by_alias=False)` always yields `journey_id`, and the collector's row conversion writes the
`journey_name` column. `extra="ignore"` stays as before; `element_selectors` becomes a declared optional field.

Timestamps stay ISO-8601 strings (no type change in storage or state) but must parse with
`datetime.fromisoformat` after `Z` normalisation; unparseable values are rejected.

## 3. Changes per file

| File | Change |
|---|---|
| `domain/*` (new) | As above |
| `collector/models.py` | Re-exports `ALLOWED_EVENT_TYPES`, `TrackerEvent`, `EventBatch` from `domain.events`. Response models stay, marked inactive (Spec 07). |
| `collector/api.py` | `collect_batch(payload: EventBatch, …)`; `write_events` uses `to_live_events_row()`. Deletes `EventItem`, `BatchPayload`. Key check unchanged (`payload.api_key or x_cji_key`). |
| `mcp_servers/ingestion_intelligence_server.py` | `CANONICAL_SCHEMA["allowed_event_types"]` and `ALLOWED_EVENT_TYPES` come from the domain. `CanonicalEvent` becomes the documented coercing adapter; output checked against `EVENT_RECORD`; `records_coerced` added to the result. |
| `tools/ingest_json.py` | `VALID_EVENT_TYPES` replaced by the domain set plus an explicit alias table; unmapped types skipped and counted |
| `state.py` | `JourneyEvent`, `StepMetrics`, `FrictionScore`, `Insight`, `WorkerStatus`, `IngestionResult` imported from `domain` (same names). `errors: list[WorkflowError]`. |
| `guardrails/output_validator.py` | Uses `INSIGHT_CATEGORIES` / `FIX_EFFORTS` from `domain.insights`; same behaviour |
| `agents/supervisor.py` | `VALID_WORKERS` from `domain.runs`; cutoff error via `workflow_error("supervisor", …)` |
| `agents/workers.py` | Check-only validation of MCP results at four points (RC-10) |
| `config.py` | `JOURNEY_NAME` default → `user_onboarding` (OD-9b) |
| `.env.example` | `JOURNEY_NAME=user_onboarding` |
| `tests/test_contracts.py` (new) | All contract tests |

## 4. Remaining duplicate shapes, each with a written adapter reason

| Shape | Reason it remains | Removed in |
|---|---|---|
| `ingestion_intelligence_server.CanonicalEvent` | Documented coercion of unknown types for third-party files; output is validated as `EventRecord` and coercions are counted | Spec 05 (repositories) |
| `live_events` row (`journey_name`, JSONB metadata) | Existing table layout; one conversion function, `to_live_events_row()` | Spec 07 / migrations |
| Dashboard fallback insight (`issue_description`) | Streamlit compatibility client; display-only | Spec 14 |
| `collector/models.py` response models | Inactive; the collector response contract belongs to Spec 07 | Spec 07 |

## 5. Tests (`tests/test_contracts.py`)

- **Single source:** `collector.models.TrackerEvent is domain.events.TrackerEvent`; the same for the
  taxonomy in collector, ingestion and guardrails; `state.FrictionScore is domain.metrics.FrictionScore`;
  `supervisor.VALID_WORKERS is domain.runs.VALID_WORKERS`; `ingest_json` emits only domain types.
- **Wire compatibility:** the exact `tracker.js` `makeEvent` payload (`journey_name`,
  `element_selectors`, no duration) validates; the documented `journey_id` form validates; both produce
  identical `EventRecord`s.
- **Invalid input:** unknown event type, negative duration, unparseable timestamp, empty identifier,
  control characters, an empty batch, a batch of 101 → explicit validation errors. Collector returns 422
  for these through `TestClient` with a fake engine.
- **Round trips:** `TrackerEvent → EventRecord → JSON → EventRecord` is lossless; `to_live_events_row()`
  maps `journey_id` to the `journey_name` column.
- **Real data:** 200 rows of the tracked Parquet validate as `EventRecord`. Live `get_step_metrics` /
  `get_funnel_dropoff` output validates as `StepMetrics` / `FunnelResult`. `score_all_steps` on that output
  validates as `FrictionScore`. Validator and fallback output validates as `InsightDraft`.
  `export_report` output validates as `ReportResult`.
- **Workflow:** ingestion `skipped` / `partial` statuses validate; the supervisor cutoff error is a
  `WorkflowError`; a malformed MCP result in a worker becomes a recorded error, not an exception.
- **Isolation:** `domain/` imports nothing outside pydantic and the standard library.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Collector now rejects batches it used to accept | Tracker fixture test; the change is limited to invalid types, durations and batch sizes. Partial-batch acceptance is Spec 07. |
| Lax pydantic coercion hides type drift | Check-only validation: values pass through unchanged, so there's no silent conversion |
| New default `JOURNEY_NAME` differs from a local `.env` | `.env` still wins; T0 reports what applies |
| Ingestion result shape gains a field | Additive; workers read with `.get()` |

## 7. Rollback

Before T1, `evidence/pre-spec03-tracked.patch` captures the cumulative tracked diff (Spec 02 state). After
the gate, `evidence/spec03-tracked.patch` captures the new cumulative diff. New files are listed in
`tasks.md`. Reverting to Spec 02 means reapplying the earlier patch to a clean checkout, which needs the
owner's approval because it discards working-tree changes.
