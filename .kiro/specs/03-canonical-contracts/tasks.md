# Spec 03 — Canonical Domain Contracts: Tasks

Sequential. `[x]` means evidence exists. No commits or pushes: each step is recorded as a patch file in `evidence/`.

**Environment:** protected environment from `01-baseline/requirements.md` §8 plus `JOURNEY_NAME=user_onboarding`
(see T0); interpreter `C:\Users\sovan\.venvs\cji-baseline-312`.

## Tasks

- [x] **T0 Prepare.** `pre-spec03-tracked.patch` (39,110 bytes, Spec 02 state) saved. `JOURNEY_NAME` in
  `cji_agent/.env` is `onboarding`; `.env` wins over the config default, so every run in this Spec sets
  `JOURNEY_NAME=user_onboarding` explicitly. `.env` was not edited. Evidence: `t0-summary.txt`.
- [x] **T1 Failing tests first.** `tests/test_contracts.py` (35 tests) run against the Spec 02 code:
  **2 pass, 33 fail** (32 × `ModuleNotFoundError: domain`, 1 × `collector.api` still has `EventItem`). The 2 that
  passed hold trivially without `domain/` (isolation scan of an empty folder; valid MCP result adds no error).
  Evidence: `before-contracts.log`, `before-contracts-junit.xml`.
- [x] **T2 `domain/` package.** `events`, `journeys`, `metrics`, `insights`, `runs`, `validation`, `__init__`.
  Imports only stdlib, pydantic, typing_extensions (test enforced). mypy clean, also with `--strict`; ruff clean.
- [x] **T3 Events.** `collector/models.py` re-exports `ALLOWED_EVENT_TYPES`, `TrackerEvent`, `EventBatch`
  (response models kept, marked inactive). `collector/api.py` validates with `EventBatch` and writes rows with
  `to_live_events_row()`; `EventItem`/`BatchPayload` deleted. Ingestion server takes the taxonomy and URL
  sanitiser from the domain, checks each output record against `EVENT_RECORD`, and returns `records_coerced`
  (also passed through `ingest_to_store`). `ingest_json`: `VALID_EVENT_TYPES` is the domain set;
  `EVENT_TYPE_ALIASES` maps `drop_off → abandon`, `session_start → page_view`; other types are skipped and counted
  in the log.
- [x] **T4 Records.** `state.py` re-exports the domain TypedDicts (`JourneyEvent = EventRecord`);
  `errors: list[WorkflowError]`. `output_validator` uses `INSIGHT_CATEGORIES`/`FIX_EFFORTS` and validates
  `JOURNEY_CONFIG` via `journey_from_config`. Supervisor imports `VALID_WORKERS` and emits the cutoff error with
  `workflow_error("supervisor", …)`. `ingestion_worker` annotates its error list as `list[WorkflowError]`.
- [x] **T5 Worker-boundary checks.** `agents/workers.py` checks step metrics + funnel (data), friction scores,
  insights + ranked fixes, narrative + report result. Check-only: values pass through unchanged; a violation adds an
  `errors` entry. 0 violations in the demo pipeline and ingest probe.
- [x] **T6 Journey identifier.** `config.JOURNEY_NAME` default `user_onboarding`; `.env.example` updated.
- [x] **T7 Gate.** All rows below. Rollback files saved.

## Gate results (T7)

Logs in `evidence/`; summary in `final-numbers.txt` and `gate-results.txt` (run 2026-10-27 23:00–23:04).

| Check | Command | Result | Spec 02 |
|---|---|---|---|
| Contract tests | `pytest tests/test_contracts.py` | **35/35** (before fix 2/35). Re-run after the test-file lint fix: exit 0 (`after-lintfix-contracts.log`) | — |
| Full suite | `pytest tests -m "not integration"` | **239/250**; the 11 failures are exactly the Spec 02 F-01 set (no new, none fixed) | 204/215 |
| Golden snapshot | `02-p0-security/evidence/scripts/golden.py` | **identical** to Spec 02 `golden-after.json` (file hash equal) | — |
| ruff | `ruff check .` | **255** total; no changed file worse than baseline; `domain/` and `test_contracts.py` clean | 263 |
| mypy | `mypy .` | **49** total (same as Spec 02); no changed file worse; `domain/` clean incl. `--strict` | 49 |
| bandit | `bandit -r .` (json) | no medium+ finding in any changed file (`collector/api.py` B608 1 → 0, from Spec 02) | — |
| Demo pipeline | `main.py --mode demo --run --auto-approve` | exit 0; 8 step metrics, 4 critical, 4 insights, report written; 0 contract violations | same |
| Ingest probe | `main.py --ingest --file probe.csv --run --auto-approve` | exit 0; 4 posts to 8005, 0 × 404, 0 calls to `8004/tools`, no iteration-cap hit; file flagged (confidence 0.0) | same |
| Whitespace | `git -c core.whitespace=cr-at-eol diff --check` | clean | clean |
| Side effects | hash of `data/events.parquet` | unchanged | unchanged |

The demo pipeline ran with `JOURNEY_NAME=user_onboarding` set explicitly because the local `.env` overrides the
default (T0). `test_default_journey_matches_the_tracked_data` proves the code default with `.env` loading disabled.
B-03 is closed for anyone without a `JOURNEY_NAME` override; the local `.env` still needs the owner's change.

## Changed files

Tracked: `.env.example`, `agents/ingestion_worker.py`, `agents/supervisor.py`, `agents/workers.py`,
`collector/api.py`, `collector/models.py`, `config.py`, `guardrails/output_validator.py`,
`mcp_servers/ingestion_intelligence_server.py`, `state.py`, `tests/test_agent_layer.py` (cutoff assertion reads
`e["error"]`), `tools/ingest_json.py`.
New: `cji_agent/domain/` (7 files), `cji_agent/tests/test_contracts.py`.
Scripts: `evidence/scripts/apply_spec03.py`, `apply_spec03_fixups.py` (lint), `apply_spec03_fixups2.py` (mypy),
`gate_spec03.ps1`, `final_numbers.py`. `ruff --fix` was applied to `domain/` and to the import block of
`tests/test_contracts.py` only.

## Rollback (no git)

- `evidence/spec03-tracked.patch` (69,511 bytes) is the cumulative tracked diff after Spec 03 (Spec 02 + 03).
- `evidence/spec03-new-files/` holds copies of `domain/*.py` and `tests/test_contracts.py`.
- Back to the Spec 02 state: `git apply -R evidence/spec03-tracked.patch`, then
  `git apply evidence/pre-spec03-tracked.patch`, then delete `cji_agent/domain/` and
  `cji_agent/tests/test_contracts.py`. This rewrites the working tree, so it needs the owner's approval.

## Validation commands

```powershell
$py = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
& $py -m pytest tests/test_contracts.py -v -p no:cacheprovider
& $py -m pytest tests -m "not integration" -p no:cacheprovider       # only F-01 may fail
& $py -m mypy domain --strict
& $py -m ruff check domain tests/test_contracts.py
powershell -NoProfile -ExecutionPolicy Bypass -File ..\.kiro\specs\03-canonical-contracts\evidence\scripts\gate_spec03.ps1
```

## Findings

| ID | Finding | Handed to |
|---|---|---|
| F-02 | `errors` in `CJIState` has no reducer. `data_worker`, `friction_worker`, `insight_worker` and `report_worker` return `{"errors": [new]}`, overwriting earlier errors; the ingestion worker appends to the full list. Found during the survey, not caused by any Spec. Contract-violation entries from T5 follow the same (overwrite) behaviour. | Spec 09 |
| F-03 | `get_step_metrics` rates are event counts per unique user, so they exceed 100 %: on the tracked data `completion_rate_pct` is 114.98 and 100.43 on two steps. `StepMetrics` therefore bounds rates at ≥ 0 only (and `FrictionScore.drop_off_rate` is not capped at 1). Changing the metric definition would change the golden snapshot, so it is out of scope here. | Analytics Spec (metric definitions) |
| F-01 | 11 obsolete tests in `test_supervisor.py` (unchanged from Spec 02). | Spec 09, or delete |

## Owner action

`cji_agent/.env` sets `JOURNEY_NAME=onboarding`, which matches no tracked data (B-03). Change it to
`user_onboarding` or remove the line so the new default applies.
