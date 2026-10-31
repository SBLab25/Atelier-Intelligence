# Spec 09 — Durable Workflow: Design

## 1. Module layout

```
cji_agent/
  workflow/                 new package
    __init__.py
    model.py                RunStatus, StepStatus, RunRecord, StepRecord, Failure, transition(), IllegalTransition
    reducers.py             append reducer (errors, worker_statuses), run-record merge reducer
    step.py                 @step(worker): RunContext binding, guard, attempts, timeout, classification, audit
    runtime.py              open_checkpointer(), lease, drive(), start_run(), approve(), resume(), status()
    errors.py               StepFailed, RunNotFound, RunNotResumable, RunLeased, LegacyRun
  graph.py                  build_graph() (no arguments); WORKER_NODES constant
  agents/supervisor.py      route() also stops on run.status in {failed, awaiting_approval}
  agents/workers.py         workers raise on failure; @step replaces @with_run; _error_text fixed (F-32)
  agents/ingestion_worker.py  returns only new status/error entries (append reducer)
  state.py                  run: Annotated[RunRecord, merge_run]; errors/worker_statuses: Annotated[..., append]
  main.py                   --run / --approve / --resume / --status via workflow.runtime
  mcp_servers/insight_server.py   deterministic ids, upsert, rank_all_fixes(run_id)
  mcp_servers/report_server.py    run-scoped file name, atomic write
  mcp_servers/ingestion_intelligence_server.py  deterministic missing event ids
```

`dashboard.py` is unchanged: it still calls `main.py --mode <m> --run --auto-approve` and reads `last_run.json`.

## 2. State

```python
class StepRecord(TypedDict):
    worker: WorkerName
    status: StepStatus            # pending | running | succeeded | failed | skipped
    attempts: int
    step_id: str                  # f"{run_id}:{worker}:{attempts}"
    started_at: str
    finished_at: str
    code: str | None              # error code of the last failed attempt

class RunRecord(TypedDict):
    run_id: str
    status: RunStatus             # running | awaiting_approval | approved | completed | failed
    created_at: str
    updated_at: str
    steps: dict[str, StepRecord]
    failure: Failure | None       # step_id, worker, code, message, retryable, attempts
```

- **`merge_run` reducer:** merges `steps` per worker, and applies `status` through `transition()`. An illegal change raises `IllegalTransition`, which fails the node, so the error is visible rather than ignored.
- **`append` reducers on `errors` and `worker_statuses`:** workers return only their new entries. `ingestion_worker` stops concatenating by hand.
- **Old and new entries:** each `WorkflowError` gains the optional keys `run_id`, `step_id` and `code`. Old entries without them remain valid.

### Allowed transitions (`workflow/model.py`)

| From | To |
|---|---|
| (new) | running |
| running | awaiting_approval, approved (auto-approve), failed |
| awaiting_approval | approved |
| approved | completed, failed |
| failed | running (resume) |
| completed | — |

`approved` with no report yet and `running` both route to work; `awaiting_approval` and `failed` route to `__end__`.

## 3. Step wrapper (`workflow/step.py`)

```
@step("insight_worker")
async def insight_worker(state) -> dict: ...      # raises on failure; returns the state update on success
```

The wrapper does the following, in order:

1. **Bind context.** Binds the `RunContext` (Spec 08 correlation id = `run_id`).
2. **Guard.** If `run.steps[worker].status == "succeeded"`, it returns `{}`: no side effects and no new status.
3. **Mark running.** Records the step as `running` with `attempts + 1` and a new `step_id`.
4. **Run attempts.** For each attempt up to `CJI_WORKFLOW_STEP_ATTEMPTS`, it runs the body inside `asyncio.timeout(CJI_WORKFLOW_STEP_TIMEOUT_S)`.
   - Success: the step becomes `succeeded`, and the wrapper merges the body's update with the `worker_statuses` entry, which now carries `run_id` and `step_id`.
   - Retryable error (`GatewayError.retryable`, `connect_failed`, timeout): writes an audit record, sleeps `CJI_WORKFLOW_RETRY_BACKOFF_S`, then tries again.
   - Other error, or the last attempt: the step becomes `failed`, the run becomes `failed` with a `failure` record, and one `errors` entry and one error status are added.
5. **Cancellation.** `CancelledError` propagates. The step stays `running` in the last stored checkpoint, so `--resume` runs it again.

Workers keep their current bodies, except that failure paths `raise` instead of returning empty results. The non-fatal paths stay as they are:
- "No critical steps": success with no insights.
- Contract warnings: an `errors` entry while the step still succeeds.
- `friction_worker` with no step metrics: it can only happen after a data success with zero steps, so it fails with `no_step_metrics`.

## 4. Driver (`workflow/runtime.py`)

```
async with open_checkpointer(path) as cp:          # aiosqlite, WAL, synchronous=FULL, run_leases table
    graph = build_graph().compile(checkpointer=cp, interrupt_after=WORKER_NODES)
    async with lease(cp, run_id):                   # refuse if another live owner holds it
        snap = await drive(graph, config, input)    # loop: astream until stop; renew lease each step
```

- **`drive()`:** loops `astream(input, config)` and then `astream(None, config)` until `aget_state(config).next` is empty, or the run status is `awaiting_approval` or `failed`. Each loop exit waits for the pending checkpoint write (exp5).
- **`start_run()`:** new `run_id`, initial state with `run.status = running`. `--auto-approve` sets `human_approved=True` and moves the run to `approved` when the insight step succeeds.
- **`approve(run_id)`:**
  1. Loads the snapshot. Unknown → `RunNotFound` (exit 1). Created before Spec 09 (no `run` key) → `LegacyRun` (exit 1).
  2. If the status is `approved` or `completed`, it prints the status and exits 0 without running anything. Any other status except `awaiting_approval` → `RunNotResumable` (exit 1).
  3. Otherwise it calls `aupdate_state(config, {"human_approved": True, "run": {"status": "approved"}}, as_node="supervisor")`, so the next node is `route()` → `report_worker`, then calls `drive()`.
- **`resume(run_id)`:** allowed for `running` (interrupted), `approved` (interrupted after approval) and `failed`. For `failed`, `aupdate_state(..., {"run": {"status": "running", "failure": None}, ...}, as_node="supervisor")` resets the failed step to `pending` and keeps its attempt count; then it calls `drive()`. Completed steps are skipped by the guard and by `route()`.
- **`status(run_id)`:** the `RunRecord` plus `report_path`, the error count and the last 5 errors, as JSON.
- **Completion:** when a run reaches `completed`, the driver writes `last_run.json` atomically (temp file plus `os.replace`), in the same format as today.

## 5. Supervisor

`route()` keeps its order and checks. Added before them:
- `run.status == "failed"`: returns `__end__`.
- Iteration cutoff exceeded: the supervisor sets `run.status = failed` with code `iteration_limit` instead of setting `next_worker = "__end__"`. The old flag is still honoured for states created before this Spec.

After the insight step, the supervisor moves the run to `awaiting_approval`, or to `approved` when `human_approved` is true. After the report step, it moves the run to `completed`. `has_run()` checks the `run.steps` status instead of the last `worker_statuses` entry, which F-33 made unreliable.

## 6. Idempotent side effects

| Side effect | Key | Change |
|---|---|---|
| Insight in ChromaDB | `insight_id = uuid5(NAMESPACE_URL, f"cji:{run_id}:{step_id}")` | `save_insight` → `collection.upsert`; `run_id` stored in metadata; `rank_all_fixes(run_id=None)` filters with `where={"run_id": run_id}` when given (old callers without it rank everything, as today) |
| HTML report | `cji_report_{journey}_{run_id}.html` | `export_report(..., run_id="")` (empty → old timestamp name for old callers); write to `*.tmp` then `os.replace` |
| Ingested event without `event_id` | `uuid5(NAMESPACE_URL, f"cji-event:{canonical_row_json}#{n}")`, n = occurrence of that exact row in the file | Existing ids untouched; repository dedupe by `event_id` does the rest |
| `last_run.json` | — | Atomic write; also after `--approve` and `--resume` (F-40) |
| LLM usage | step guard | A guarded (skipped) step adds no usage |

## 7. Settings

| Key | Default | Check |
|---|---|---|
| `CJI_CHECKPOINTS_DB` | `<data_dir>/cji_checkpoints.db` | parent directory must exist or be creatable |
| `CJI_WORKFLOW_STEP_TIMEOUT_S` | 900 | > `CJI_MCP_CALL_TIMEOUT_S` |
| `CJI_WORKFLOW_STEP_ATTEMPTS` | 2 | 1–5 |
| `CJI_WORKFLOW_RETRY_BACKOFF_S` | 5 | 0–300 |

The lease duration is the step timeout plus 60 s. It is renewed at every step, so a crashed owner's lease expires after at most that long.

## 8. Tests (`tests/test_workflow.py`, plus updates)

| Group | Tests |
|---|---|
| Model | full transition table (allowed and illegal); `merge_run`; append reducers keep order |
| Graph | worker order unchanged; one successor per worker, no fan-out (R11); `build_graph()` has no persistence argument |
| Step wrapper | success record; guard skips a succeeded step (body not called, no side effect, no usage); retryable error retried then succeeds; non-retryable fails at once; timeout → `step_timeout`; attempts bounded; cancellation leaves `running` |
| Failure | data failure stops the run (no loop, 1 data call); `run.failure` fields; every error kept in order; iteration cutoff → `failed` / `iteration_limit` |
| Failure injection, every worker | fault before the side effect; fault after the side effect before the checkpoint (resume → same insight ids, one report file, no duplicate events); subprocess `os._exit` inside the worker → `--resume` re-runs only that worker |
| Approval | pause → `awaiting_approval`, no report; approve → only `report_worker` runs; approve twice → no-op exit 0; approve unknown → exit 1; approve legacy → exit 1; approve failed run → exit 1 |
| Resume | interrupted run; failed run after the cause is fixed (attempt count continues); completed run refused; leased run refused; expired lease taken over |
| CLI | `--run --auto-approve` completes and writes `last_run.json` (same keys); `--status` JSON; exit codes |
| Audit | step and run records with `run_id`/`step_id`, allow-listed fields only, no payloads |
| Idempotency at servers | `save_insight` twice → one row; `rank_all_fixes(run_id)` excludes other runs; `export_report` twice → one file; missing-id ingestion twice → same ids |
| Friction | same metrics, same scores (existing tests kept; one rerun test added) |

Every worker test uses stub workers or `FakeToolSession`. Checkpoints use SQLite in `tmp_path`. No servers, network or real databases are involved.

## 9. Risks

| Risk | Mitigation |
|---|---|
| `interrupt_after` driving changes stream events seen by callers | Only `main.py` consumes the stream; its printing moves into the driver; output lines stay the same |
| Failing the run on a step error is a behaviour change (today the report is built on missing data) | Documented; `--resume` after fixing the cause; `--status` shows the failed step |
| ChromaDB `upsert`/`where` on 1.5.9 | Covered by a server-level test against a temporary Chroma directory |
| Old checkpoints (no `run` key) | Refused with a clear message (non-goal: migration) |
| LangGraph 0.2.28 `aupdate_state(as_node=...)` after the graph ended | Verified by the approval tests before the driver is built on it (T1) |

## 10. Rollback

1. `git apply -R evidence/spec09-tracked.patch`, then `git apply evidence/pre-spec09-tracked.patch`.
2. Restore untracked files from `evidence/pre-spec09-untracked/`.
3. Delete `cji_agent/workflow/` and `tests/test_workflow.py`.

Checkpoints written by Spec 09 runs are not readable as resumable runs by the old code, which ignores the extra `run` key. Report files and ChromaDB rows written in the meantime stay valid.
