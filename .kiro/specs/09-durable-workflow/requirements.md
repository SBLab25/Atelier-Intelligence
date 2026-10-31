# Spec 09 — Durable Workflow: Requirements

**Source:** `kiro_upgrade_prompts.md` Prompt 8. **Findings addressed:** F-01 (obsolete supervisor tests, assigned
to this Spec), the Spec 08 defect F-32, and the survey findings F-33 to F-40 below.

**Branch:** `phase-02-security` (no commits; patch files are the rollback points, as in Specs 02–08).

**Status:** written 2026-10-28; OD-67 to OD-80 approved with their defaults; implemented and gated 2026-10-28 (see tasks.md).

## 1. Current state (surveyed after Spec 08)

Installed: `langgraph` 0.2.28, `langgraph-checkpoint-sqlite` 1.0.4, `aiosqlite` 0.20.0, `chromadb` 1.5.9.
The experiments run the real `graph.py` and supervisor with stub workers (no servers, no network). Scripts and
output: `evidence/survey/` (`exp.py`/`exp.txt`, `exp5.py`/`exp5.txt`).

| Area | What the code does today | Evidence |
|---|---|---|
| Graph | `supervisor` → `route()` → one worker → `supervisor`, sequential. `route()` returns `__end__` when insights exist and `human_approved` is false. | `graph.py`, `agents/supervisor.py` |
| Checkpoints | `main.py` opens `AsyncSqliteSaver` on `data/cji_checkpoints.db` per command. LangGraph 0.2.28 writes checkpoints in a background task; the next worker starts before the previous checkpoint is stored. | `pregel/loop.py:554` "save it, without blocking" (`survey/src.txt`) |
| Process death | Killing the process inside `friction_worker` left only the input checkpoint (iteration 0). Resume re-ran `data_worker`. | exp4 |
| Step-wise driving | Stopping after every worker (`interrupt_after`) makes the loop wait for the pending write. After the same kill, 3 of 3 trials resumed at `friction_worker` without re-running `data_worker`. | exp5 |
| Approval | Two mechanisms: `route()` ends the run, and `main.py` also compiles with `interrupt_before=["report_worker"]` (never reached) and `break`s out of the stream. | `main.py:229-255` |
| `--approve` | After a paused run, the stored checkpoint was stale (iteration 1, next `data_worker`). `--approve` re-ran data, friction and insight, then stopped before the report. A second `--approve` produced the report. | exp2 |
| `--approve` unknown id | Runs a full analysis on a nearly empty state; no error. | exp3 |
| State lists | `errors` and `worker_statuses` have no reducer: every worker's return **replaces** them. `ingestion_worker` appends by hand, the other workers do not. | exp1: 1 error and 1 status kept after 20 worker calls |
| Failure handling | Every worker catches all exceptions and returns an error status; the graph continues. A data failure makes `route()` alternate data ↔ friction until the iteration cutoff. | exp1: 20 worker calls, only the cutoff error survives |
| Worker error text | `_error_text()` calls itself for gateway errors: infinite recursion. Any `GatewayError` at a worker boundary raises `RecursionError` from the except handler. | exp0 |
| Insights | `insight_id` is a new UUID4 every run; `save_insight` uses `collection.add`; `rank_all_fixes` ranks every insight ever stored. | Spec 08 gate: "ranked 130 / 134 / 138 fixes" on three runs over the same data |
| Reports | File name `cji_report_{journey}_{YYYYmmdd_HHMMSS}.html`: every run and every retry writes a new file. | `report_server.py:113` |
| Ingested events | Files without `event_id` get UUID4 ids per load, so loading the same file twice stores every event twice (the repository dedupes by `event_id` only). | `ingestion_intelligence_server.py:326` |
| Persistence switches | `build_graph(use_persistence=True)` ignores its argument; the `graph.py` docstring says it attaches `SqliteSaver` and `interrupt_before` (it does neither). | `graph.py:34-44` |
| Dashboard data | `data/last_run.json` is written after `--run` only, not after `--approve`. | `main.py:268-288` |
| Callers | CLI: `--run`, `--auto-approve`, `--approve --thread-id`. Streamlit runs `main.py --mode <m> --run --auto-approve` as a subprocess (`CJI_PIPELINE_TIMEOUT_S`, 180 s) and reads `last_run.json`. | `dashboard.py:413-416` |
| Tests | 11 obsolete tests in `test_supervisor.py` (F-01). No test drives the graph with a checkpointer, approves, resumes or injects failures. | Spec 08 gate |

### Findings

| ID | Finding | Owner |
|---|---|---|
| F-32 | **Spec 08 defect:** `agents/workers.py::_error_text` recurses forever on a `GatewayError`. Spec 08's test used a non-gateway exception, so it did not catch this. | This Spec, task T0 (one-line fix plus test), or earlier if you prefer |
| F-33 | `errors` and `worker_statuses` are overwritten, not appended | This Spec (OD-70) |
| F-34 | A failed step loops data ↔ friction until the cutoff and loses the original error | This Spec (OD-72) |
| F-35 | `--approve` re-runs the analysis and needs a second approve; the paused run's checkpoint is stale | This Spec (OD-74) |
| F-36 | `--approve` with an unknown or finished thread id starts a new analysis | This Spec (OD-74) |
| F-37 | Checkpoints are written in the background; a process death loses completed steps | This Spec (OD-68) |
| F-38 | Reruns duplicate insights (ChromaDB), reports (new file each time) and ingested events without ids | This Spec (OD-73) |
| F-39 | `use_persistence` is ignored; two approval mechanisms; misleading `graph.py` docstring | This Spec (OD-75) |
| F-40 | `last_run.json` is not written after `--approve` | This Spec (OD-74) |

## 2. Decisions (defaults; confirm or change before implementation)

| ID | Decision | Default | Alternatives considered |
|---|---|---|---|
| OD-67 | Checkpoint store | Keep SQLite (`data/cji_checkpoints.db`), opened in one place (`workflow/runtime.py`) with WAL and `synchronous=FULL`. Path setting `CJI_CHECKPOINTS_DB` (default unchanged). | Postgres saver on Supabase (live database, extra package, not needed for one CLI process); in-memory (not durable) |
| OD-68 | Durability on LangGraph 0.2.28 | Drive the graph **one worker at a time** (`interrupt_after` every worker; the driver loops until the run stops). Each step's checkpoint is stored before the next worker starts (exp5). No dependency upgrade. | Upgrade to LangGraph ≥ 0.6 for `durability="sync"` (major-version jump of `langgraph` and the sqlite saver, network install, API changes; worth a later Spec); own step journal beside the checkpointer (duplicates LangGraph) |
| OD-69 | Run and step ids | `run_id` = LangGraph `thread_id` (UUID4; already the Spec 08 correlation id). `step_id` = `{run_id}:{worker}:{attempt}`. Both in state, audit and worker status. | Separate run id from thread id (two ids for one thing) |
| OD-70 | Typed state | New `run` state key: `RunRecord` (status, timestamps, `steps` per worker as `StepRecord`, `failure`). Status changes only through a pure `transition()` function with an allowed-transition table (illegal → `IllegalTransition`). Append reducers for `errors` and `worker_statuses` (F-33). | Keep untyped dicts; replace the TypedDict state with Pydantic (bigger change to every worker and test) |
| OD-71 | Run statuses | `running` → `awaiting_approval` → `approved` → `completed`; `running`/`approved` → `failed`; `failed` → `running` (resume). Step statuses `pending`, `running`, `succeeded`, `failed`, `skipped`. | More states (`cancelled`, `timed_out`): covered by `failed` with an error code |
| OD-72 | Failure semantics | A step that fails after its retries **fails the run**: `run.status = failed`, `run.failure = {step_id, worker, code, message, retryable, attempts}`; the supervisor stops; no later worker runs. "No critical steps" and contract warnings stay non-fatal. Codes come from the Spec 08 gateway errors plus `step_timeout`, `mode_mismatch`, `no_step_metrics`, `iteration_limit`. | Keep today's "record and continue" (causes F-34 and reports built on missing data) |
| OD-73 | Idempotency | Step guard: a step already `succeeded` in this run is not executed again. Insights: `insight_id = uuid5(run_id, step_id)`, `save_insight` upserts, `rank_all_fixes(run_id)` ranks this run's insights (history stays stored). Reports: `cji_report_{journey}_{run_id}.html`, written to a temp file and renamed. Ingestion: missing `event_id` = `uuid5` of the row's canonical JSON plus its occurrence number in the file. `last_run.json` written atomically. | Content hashes for insights across runs (the same friction on another day would merge with history); keep timestamped report names (a retry leaves a second file) |
| OD-74 | CLI | Unchanged: `--run`, `--auto-approve`, `--approve --thread-id`. New: `--resume --thread-id` (continue an interrupted or failed run from its last checkpoint; the failed step runs again) and `--status --thread-id` (run record as JSON: status, steps, attempts, failure, report). `--approve` is accepted only for `awaiting_approval`; a second approve of an approved or completed run prints the state and exits 0 without running anything; unknown ids exit 1. `last_run.json` is written whenever a run completes. Exit codes: 0 completed or paused, 1 failed, 2 configuration. | Approve and resume in one flag (hides what is about to run) |
| OD-75 | Persistence switches | Remove the `use_persistence` argument and the second approval mechanism (`interrupt_before`); one driver (`workflow/runtime.py`) used by `--run`, `--approve`, `--resume`. `graph.py` docstring describes what it does. | Keep the argument as deprecated (keeps the misleading switch) |
| OD-76 | Retries and timeouts | Per step: timeout `CJI_WORKFLOW_STEP_TIMEOUT_S` (900 s; above the MCP call timeout and the insight worker's per-insight LLM deadline), attempts `CJI_WORKFLOW_STEP_ATTEMPTS` (2), fixed backoff `CJI_WORKFLOW_RETRY_BACKOFF_S` (5 s). Only retryable errors are retried (gateway `retryable`, `connect_failed`, `step_timeout`). The iteration cutoff stays (`MAX_AGENT_ITERATIONS`) and now fails the run with `iteration_limit`. | LangGraph `RetryPolicy` on `add_node` (retries on exceptions only; workers would have to stop catching, and attempts would not be recorded in state) |
| OD-77 | Concurrent execution | A lease row per run in the checkpoint database (`run_leases`: run_id, owner, expires_at; renewed at each step). A second process that tries to run, approve or resume a leased run exits 1 ("run is active in process …"). An expired lease (crashed owner) can be taken over. | No lease (two `--resume` calls of one run would execute steps twice); file locks (not portable across machines sharing a database later) |
| OD-78 | Workflow audit | Spec 08 audit sink, file `workflow.jsonl`: `kind=step` (run_id, step_id, worker, attempt, outcome, code, latency_ms) and `kind=run` (run_id, from_status, to_status, code). New allow-listed fields only; no state payloads. | Separate workflow log format |
| OD-79 | Tests | `tests/test_workflow.py`: transitions, reducers, guard, approval, resume, lease, audit, and failure injection at every worker boundary (fault before the side effect, after the side effect before the checkpoint, process death in a subprocess with `os._exit`). Stub workers and fake MCP sessions; SQLite in `tmp_path`. | Only in-process exceptions (would not prove resume after process death) |
| OD-80 | F-01 tests | Delete the 11 obsolete `test_supervisor.py` tests that check removed behaviour (`_llm_route`, supervisor messages, `next_worker` from the supervisor); their still-valid intent (cutoff keeps earlier errors, full-pipeline order) is covered by new tests. | Rewrite them in place (they test an API that no longer exists) |

## 3. Requirements

**R1 Preserve.**
- Worker order ingestion → data → friction → insight → (approval) → report.
- The human approval checkpoint: without `--auto-approve` the run stops as `awaiting_approval` and reports nothing until approved.
- The iteration cutoff.
- Deterministic friction scores: same input, same output; the friction engine still imports no AI code (Spec 08 test kept).
- CLI flags, `last_run.json` format, and the Streamlit subprocess call.

**R2 Durable checkpoints.**
- One configured checkpoint store.
- Each completed step is stored before the next one starts.
- After a process death, at most the interrupted step runs again.

**R3 Typed transitions.**
- Run and step status change only through `transition()`.
- Illegal transitions raise; the tests cover the full table.

**R4 Identifiers.**
- `run_id` and `step_id` in state, worker statuses, errors, audit records and `--status` output.

**R5 Idempotent workers.**
- Running a step twice in one run leaves the same stored insights, report file and events as running it once.
- A completed step is not executed again on resume.

**R6 Retries and timeouts.**
- Bounded per step (OD-76).
- No unbounded loops: the cutoff and the failure stop are both tested.

**R7 Resume.**
- `--resume` continues a run interrupted by an exception, a timeout or a process kill.
- It refuses unknown, completed, or leased runs, with a message and exit code 1.

**R8 Structured failures.**
- A failed run has `run.status = failed` and a `run.failure` record (step_id, worker, code, message, retryable, attempts).
- `errors` keeps every error of the run in order.

**R9 Safe approval.**
- Approval works only for `awaiting_approval`.
- Repeating it is a no-op.
- Approving never re-runs completed steps.
- Unknown ids are refused.

**R10 Audit.** Step and run records with correlation ids and no payloads (OD-78).

**R11 No unbounded parallelism.** The graph stays sequential: one successor per worker; no `Send`, no fan-out. A test enforces this.

**R12 Diagnosable partial runs.** `--status` shows every step with its status, attempts, timestamps and error code.

## 4. Non-goals

- LangGraph or checkpoint-saver upgrades (OD-68 alternative; candidate for a later Spec).
- Shared checkpoints across machines, or Postgres checkpoints.
- Parallel workers or parallel insight generation.
- Changes to friction scoring, prompts, or the report layout.
- Dashboard features beyond keeping its current call working.
- Migrating checkpoints written before this Spec: `--resume`/`--approve` on such a thread exits 1 with "created before Spec 09; start a new run".

## 5. Acceptance criteria (Prompt 8)

1. Interrupted runs resume from a checkpoint (exception, timeout, and process kill at each worker boundary).
2. Failed runs expose structured errors (`run.failure`, `errors`, `--status`, audit).
3. Duplicate execution is safe (step run twice, resume after a crash between side effect and checkpoint, approve twice, two processes on one run).
4. Approval and resume tests pass.
