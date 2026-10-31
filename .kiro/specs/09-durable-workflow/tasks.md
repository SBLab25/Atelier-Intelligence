# Spec 09 — Durable Workflow: Tasks

Sequential. `[x]` means evidence exists. No commits or pushes: the change set is recorded as patch files in `evidence/`.

**Environment:** protected environment (dummy LLM keys, dead proxy, dead database URLs, `CJI_MODE=demo`). Tests use
stub workers, `FakeToolSession` and SQLite checkpoints in `tmp_path`. The real Supabase URL was never used.

**Status:** OD-67 to OD-80 approved with their defaults ("implement spec 09"). Implemented 2026-10-28. Gate passed.

## Tasks

- [x] **T0 Prepare and fix F-32.**
  - `evidence/pre-spec09-tracked.patch` (380,237 bytes) and `evidence/pre-spec09-untracked/` (44 files, MANIFEST.txt).
    Baseline = Spec 08 gate (663/674, the 11 F-01 failures).
  - `_error_text` returns `str(exc)` for `GatewayError` and `StepError`
    (`test_error_text_handles_gateway_errors` uses a real `GatewayError`).
- [x] **T1 Failing tests first.** `tests/test_workflow.py` and `tests/_workflow_stubs.py` were written against the old
  code. Result: 85 tests, 1 passed, 40 failures, 44 errors (`evidence/before-tests-junit.xml`, `before-tests-summary.txt`).
  The LangGraph 0.2.28 experiments are in `evidence/survey/` (`interrupt_after` makes completed steps durable, 3/3 trials).
- [x] **T2 Model and state.** `domain/runs.py`: `RunRecord`, `StepRecord`, `Failure`, `transition()`,
  `step_transition()`, `IllegalTransition`, `merge_run`. `state.py`: the `run` key with the `merge_run` reducer;
  `errors` and `worker_statuses` append (`operator.add`).
- [x] **T3 Step wrapper and workers.** `workflow/step.py` (`@step`: ids, bounded retries, timeout, audit),
  `workflow/errors.py`. The workers raise `StepError`; `ingestion_worker` returns only new list entries; the supervisor
  stops on a failed run and the iteration cutoff fails the run.
- [x] **T4 Runtime and CLI.** `workflow/runtime.py`: SQLite checkpointer (WAL, `synchronous=FULL`), lease table,
  one-worker-at-a-time driver, `start`/`approve`/`resume`/`status`, atomic `last_run.json`. `main.py`: `--resume` and
  `--status`; `--run`, `--auto-approve`, `--approve --thread-id` keep working.
- [x] **T5 Idempotent side effects.** Run-scoped insight ids (uuid5), `save_insight` upsert, `rank_all_fixes(run_id=)`;
  report file named by run id and written atomically; deterministic ids for ingested rows without `event_id`.
- [x] **T6 Cleanup and docs.** `build_graph(use_persistence)` and the second approval mechanism (`interrupt_before`)
  removed; `graph.WORKER_NODES`; 11 F-01 tests deleted (OD-80); settings (`CJI_WORKFLOW_*`, `CJI_CHECKPOINTS_DB`);
  README and `.env.example` updated.
- [x] **T7 Gate.** `evidence/scripts/gate_spec09.ps1`, `audit_workflow_check.py`, `final_numbers.py`,
  `save_spec09.py`. Results below; `evidence/final-numbers.txt`, `spec09-tracked.patch` (426,039 bytes),
  `spec09-new-files/` (MANIFEST.txt).

## Gate (2026-10-28 15:05–15:13, protected environment)

| Check | Spec 09 | Spec 08 |
|---|---|---|
| Full suite (not integration) | **749/749** pass, 0 skipped | 663/674 (11 F-01) |
| Tests removed | 12: the 11 F-01 tests, plus `test_graph_compiles_without_persistence` (the switch is gone; `build_graph().compile()` is tested instead) | — |
| Tests added | 87 (86 in `test_workflow.py`) | — |
| Gate test set (12 modules incl. `test_workflow.py`) | 581/581 | — |
| `test_workflow.py` | 86/86 (T1 baseline of the same file: 1/85) | — |
| Collector smoke (Spec 07) | 16/16 | 16/16 |
| Golden snapshot | identical to Spec 08 | — |
| ruff, whole tree | 98 findings | 113 |
| ruff, new code | clean | clean |
| mypy, whole tree | 35 errors in 13 files (87 files checked) | 34 in 13 (81 checked) |
| mypy `--strict` workflow + `domain/runs.py` / integrations / repositories | clean / clean / clean | — / clean / clean |
| bandit, whole tree | HIGH 0, MEDIUM 12, LOW 957 | HIGH 0, MEDIUM 12, LOW 878 |
| bandit `workflow/` | no issues (exit 0) | — |
| `settings check` with step timeout below the MCP call timeout | exit 2, names both keys | — |
| CLI `--status`/`--approve`/`--resume` with an unknown thread id | refused, exit 1, before the MCP ping | — |
| Demo pipeline `--run --auto-approve` (dashboard call), no LLM | exit 0, completed | exit 0 |
| `--run` without `--auto-approve` | exit 0, `awaiting_approval` | — |
| `--resume` of the paused run | refused, exit 1 | — |
| `--approve`, then `--approve` again | exit 0, report written; second call is a no-op (exit 0); 1 report file | `--approve` re-ran the analysis (F-35) |
| Demo pipeline, groq with a dummy key behind the dead proxy | exit 0, fallback insights, 67 s | exit 0, 69 s |
| Kill during `insight_worker`, then `--resume` | killed with data and friction done (`status`: running, 2 steps succeeded); resume ran only insight and report; `status`: completed | completed steps were lost (F-37) |
| Ingest probe | exit 0 | exit 0 |
| Realtime CLI against demo servers | exit 1, `mode_mismatch`, not retried | exit 0 with an error message |
| Audit check (Spec 08: fields, secrets, correlation) | PASS | PASS |
| Workflow audit check | PASS: 6 runs (5 completed, 1 failed = the mode-mismatch run), no step succeeded twice, every status change legal, `run_id == correlation_id` | — |
| `git diff --check`, tracked `events.parquet` | clean, unchanged | clean, unchanged |

Notes on the numbers:
- **mypy +1:** `mcp_servers/insight_server.py:196`, the new `"run_id": str(insight.get("run_id", ""))` line. It
  repeats the existing `insight.get` union-attr error that already appears on 14 lines of `save_insight`. It was
  not fixed here because that would mean retyping the existing function.
- **bandit LOW +79:** all in tests. `test_workflow.py` has 98 `assert` (B101) plus B404/B603 for the subprocess in
  the process-death test; `test_supervisor.py` has 23 fewer asserts because of the deleted F-01 tests.
- **ruff −15:** the deleted F-01 tests and the rewritten `graph.py`/`workers.py`.

### Gate runs that did not count
- Run 1: the last lint edit (`workflow/runtime.py`, `sys.platform == "win32"` instead of `getattr`) landed while
  pytest was running, so the run could not count.
- Runs 1 and 2: the harness shell stopped the detached gate during the groq pipeline (no product fault; the orphaned
  servers were stopped). Runs 3 and 4 were launched through WMI.
- Run 3 completed and found a **gate-script bug**. The kill/resume step read the thread id from the killed process's stdout, which
  was still buffered, so it was empty. The script now reads the run id from the killed run's step records in
  `workflow.jsonl` (and sets `PYTHONUNBUFFERED`). No product code changed.

## Acceptance criteria (Prompt 8)

| Criterion | Evidence |
|---|---|
| Interrupted runs resume from a checkpoint | `test_resume_after_process_death_reruns_only_the_interrupted_step` (the workflow process dies inside each worker, in a subprocess), `test_a_lease_of_a_dead_local_process_is_taken_over`, `test_an_expired_lease_is_taken_over`; gate kill/resume |
| Failed runs expose structured errors | `test_data_failure_stops_the_run_with_a_structured_error`, `test_real_worker_failure_is_structured`, `test_non_retryable_error_fails_at_once`, `test_mode_mismatch_is_not_retried`, `test_no_step_metrics_fails_friction`, `test_iteration_cutoff_fails_the_run`, `test_every_error_of_the_run_is_kept_in_order`, `test_status_describes_a_partial_run`; gate mode mismatch |
| Duplicate execution is safe | `test_succeeded_step_is_not_run_again`, `test_insight_ids_are_run_scoped_and_stable`, `test_save_insight_upserts_and_ranks_one_run`, `test_export_report_twice_writes_one_file`, `test_missing_event_ids_are_deterministic`, `test_friction_scores_are_deterministic_on_rerun`, `test_approve_twice_is_a_no_op`, `test_a_leased_run_is_refused`; workflow audit (no step succeeded twice) |
| Approval and resume tests pass | `test_pause_then_approve_runs_only_the_report`, `test_approve_unknown_run_is_refused`, `test_approve_legacy_run_is_refused`, `test_approve_failed_run_is_refused`, `test_resume_a_failed_run_after_the_cause_is_fixed`, `test_resume_after_approval_failure_keeps_the_approval`, `test_resume_refuses_completed_and_paused_runs`, `test_resume_unknown_run_is_refused`, `test_cli_resume_and_approve_refuse_unknown_runs`; gate pause/approve/approve-again |
| Preserved: worker order, approval checkpoint, cutoff, deterministic friction, CLI/Streamlit calls | `test_worker_order_is_unchanged`, `test_graph_is_sequential_with_one_successor_per_worker`, `test_pause_then_approve_runs_only_the_report`, `test_iteration_cutoff_fails_the_run`, `test_friction_scores_are_deterministic_on_rerun`, golden snapshot identical, gate dashboard call (`--run --auto-approve`) |
| Bounded retries and timeouts, no unbounded parallelism | `test_retryable_error_is_retried`, `test_attempts_are_bounded`, `test_step_timeout_is_a_retryable_failure`, `test_cancellation_propagates`, `test_workflow_settings`; one worker at a time (`interrupt_after`) |
| Audit metadata | `test_step_records_run_and_step_ids`, `test_step_and_run_audit_records`; workflow audit check |
| Misleading persistence switches removed | `test_build_graph_has_no_persistence_switch` |

## Deviations from the design

- **Initial-state checkpoint.** A new run first stores its initial state (with the run record) before any worker
  runs (`interrupt_before=["supervisor"]`). Without this, a crash in `data_worker` left only the input checkpoint and
  the run could not be resumed. `_load` treats an input-only checkpoint as `running`.
- **Dead-process lease takeover.** A lease whose owner (`host:pid:token`) is a process on this host that no longer
  exists is free at once. Otherwise a killed run stays locked until the lease expires.
- **Lease length** is `step_timeout_s × step_attempts + 60` (design: step timeout + 60), so a live run that is
  retrying a step never loses its lease.
- **`failed → approved`** was added to the run transitions, so resuming a run that failed in `report_worker` keeps
  its earlier approval.
- **Model location.** The typed records live in `domain/runs.py` (next to the other domain models), not in
  `workflow/model.py`/`reducers.py` as T2 first said.
- **mypy `--follow-imports=silent`** for the strict check of `workflow/` and `domain/runs.py`, so errors that already
  exist in imported legacy modules are not reported against the new code.

## Behaviour changes callers can see

- A failed step stops the run. `main.py` exits **1** on a failed or refused run, 0 on a completed or paused run, 2 on
  a configuration error. The dashboard's `--run --auto-approve` call now returns 1 when the analysis fails (before, it
  returned 0 with an error message).
- A mode mismatch (realtime CLI, demo servers) is a structured failure with exit 1 and is not retried.
- `--approve --thread-id` runs only the report step of a paused run. Approving an approved or completed run is a
  no-op (exit 0). Unknown ids exit 1 and do **not** start a new analysis.
- New: `--resume --thread-id` (continue a failed or interrupted run) and `--status --thread-id` (prints JSON).
- Reports are named `cji_report_{journey}_{run_id}.html`; rerunning a run's report step overwrites the same file.
- `rank_all_fixes` ranks only the current run's insights.
- Checkpoints from before Spec 09 are refused (`LegacyRun`, exit 1). Start a new run instead.
- New settings: `CJI_CHECKPOINTS_DB`, `CJI_WORKFLOW_STEP_TIMEOUT_S` (900, must be above `CJI_MCP_CALL_TIMEOUT_S`),
  `CJI_WORKFLOW_STEP_ATTEMPTS` (2, 1–5), `CJI_WORKFLOW_RETRY_BACKOFF_S` (5, 0–300).
- `data/audit/workflow.jsonl` gets `kind=step` and `kind=run` records. `last_run.json` keeps its keys and is written
  after `--approve` and `--resume` too.

## Findings

| ID | Finding | Status |
|---|---|---|
| F-01 | 11 obsolete tests in `test_supervisor.py` | Fixed (deleted, OD-80) |
| F-32 | `_error_text` recursion on `GatewayError` (Spec 08 defect) | Fixed (T0) |
| F-33 | `errors` and `worker_statuses` overwritten | Fixed (append reducers) |
| F-34 | Failed step loops data ↔ friction and loses the error | Fixed (failure stops the run) |
| F-35 | `--approve` re-runs the analysis | Fixed |
| F-36 | `--approve` with an unknown id starts a new analysis | Fixed |
| F-37 | Background checkpoint writes lose completed steps on process death | Fixed (one worker per drive step) |
| F-38 | Reruns duplicate insights, reports and id-less events | Fixed |
| F-39 | `use_persistence` ignored; two approval mechanisms; misleading docstring | Fixed |
| F-40 | `last_run.json` not written after `--approve` | Fixed |
| F-12, F-20, F-21 | Prompt reuse; `event_id` global key; plain-text tracker keys | Open, later Specs |
| F-22 to F-25, F-27, F-28 | Owner checks: journey names in Supabase `api_keys`, dev key snippet, per-process limits, retired model `llama3-70b-8192`, raw rows sent to the LLM, unused OpenAI key | Open, owner |

## Rollback

1. `git apply -R .kiro/specs/09-durable-workflow/evidence/spec09-tracked.patch`, then
   `git apply .kiro/specs/09-durable-workflow/evidence/pre-spec09-tracked.patch` (restores the pre-Spec-09 tracked state).
2. Copy the files in `evidence/pre-spec09-untracked/` back over their paths (`domain/runs.py`, settings,
   `integrations/audit.py`).
3. Delete the files listed as `new` in `evidence/spec09-new-files/MANIFEST.txt` (`cji_agent/workflow/`,
   `tests/test_workflow.py`, `tests/_workflow_stubs.py`).
4. The checkpoint database (`<data_dir>/cji_checkpoints.db` and its `-wal`/`-shm` files) and `cji_agent/data/audit/`
   may be deleted. Reports named by run id in `reports/` may be deleted. No database schema change was made in Supabase.
