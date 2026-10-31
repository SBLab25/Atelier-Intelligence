"""
`@step(worker)`: the boundary around every graph worker (Spec 09, design §3).

- Binds the run's correlation context (Spec 08) so tool and LLM calls carry the run id.
- Guard: a step that already succeeded in this run is not executed again (no side effects, no usage).
- Per attempt: timeout `CJI_WORKFLOW_STEP_TIMEOUT_S`; up to `CJI_WORKFLOW_STEP_ATTEMPTS` attempts with
  `CJI_WORKFLOW_RETRY_BACKOFF_S` between them, for retryable errors only.
- Success: the body's update plus the step record and run/step ids on its status and error entries.
- Failure: the worker's fallback fields, one error status, one error entry, and `run.status = failed` with a
  structured `run.failure`. Cancellation propagates.

States without a `run` record (direct calls in older tests) get the same retries and the same failure
shape as before Spec 09, without run bookkeeping.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import AIMessage

from cji.integrations.audit import AuditSink, default_sink, make_record
from cji.integrations.context import bind_run, correlation_from_config
from cji.integrations.types import RunContext

from .errors import StepError, classify, error_text

Body = Callable[[Any], Awaitable[dict[str, Any]]]          # (state) -> update; state is a CJIState mapping
AUDIT: AuditSink | None = None          # tests replace it; default: the "workflow" audit sink


def audit_sink() -> AuditSink:
    global AUDIT
    if AUDIT is None:
        AUDIT = default_sink("workflow")
    return AUDIT


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def write_audit(**fields: Any) -> None:
    audit_sink().write(make_record(service="workflow", **fields))


def step(
    worker: str,
    *,
    fallback: Callable[[], dict[str, Any]] | None = None,
    describe: Callable[[BaseException], str] | None = None,
) -> Callable[[Body], Callable[..., Awaitable[dict[str, Any]]]]:
    """Wrap a worker body. The node's signature is `(state, config=None)` so LangGraph passes its config."""
    text_of = describe or error_text

    def decorate(body: Body) -> Callable[..., Awaitable[dict[str, Any]]]:
        async def node(state: dict[str, Any], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
            from cji.settings import get_settings

            run = state.get("run") or {}
            tracked = bool(run.get("run_id"))
            run_id = str(run.get("run_id") or correlation_from_config(config))
            previous = (run.get("steps") or {}).get(worker) or {}
            attempt = int(previous.get("attempts") or 0)
            if tracked and previous.get("status") == "succeeded":
                write_audit(kind="step", correlation_id=run_id, run_id=run_id, step_id=previous.get("step_id"),
                            worker=worker, attempt=attempt, outcome="skipped")
                return {}

            limits = get_settings().workflow
            started = utc_now()
            failure: BaseException | None = None
            step_id = f"{run_id}:{worker}:{attempt + 1}"
            with bind_run(RunContext(correlation_id=run_id, worker=worker)):
                for n in range(limits.step_attempts):
                    attempt += 1
                    step_id = f"{run_id}:{worker}:{attempt}"
                    t0 = time.monotonic()
                    try:
                        async with asyncio.timeout(limits.step_timeout_s):
                            update = await body(state)
                    except asyncio.CancelledError:
                        write_audit(kind="step", correlation_id=run_id, run_id=run_id, step_id=step_id,
                                    worker=worker, attempt=attempt, outcome="cancelled",
                                    latency_ms=_ms(t0))
                        raise
                    except TimeoutError:
                        failure = StepError(f"{worker} did not finish within {limits.step_timeout_s:g}s "
                                            "(step_timeout)", code="step_timeout", retryable=True)
                    except Exception as exc:  # noqa: BLE001  # broad-except: worker boundary: classified, audited, retried or recorded as the run failure
                        failure = exc
                    else:
                        write_audit(kind="step", correlation_id=run_id, run_id=run_id, step_id=step_id,
                                    worker=worker, attempt=attempt, outcome="ok", latency_ms=_ms(t0))
                        return _succeeded(update, worker, run_id, step_id, attempt, started, tracked)
                    code, retryable = classify(failure)
                    write_audit(kind="step", correlation_id=run_id, run_id=run_id, step_id=step_id, worker=worker,
                                attempt=attempt, outcome="error", code=code, retryable=retryable,
                                latency_ms=_ms(t0))
                    if not retryable or n == limits.step_attempts - 1:
                        break
                    if limits.retry_backoff_s > 0:
                        await asyncio.sleep(limits.retry_backoff_s)
            if failure is None:                       # unreachable: the loop returns on success
                failure = StepError(f"{worker} made no attempt", code="no_attempt")
            return _failed(failure, text_of(failure), fallback, worker, run_id, step_id, attempt, started, tracked)

        node.__name__ = getattr(body, "__name__", worker)
        node.__qualname__ = getattr(body, "__qualname__", worker)
        node.__doc__ = body.__doc__
        node.__module__ = body.__module__
        node.__wrapped_body__ = body  # type: ignore[attr-defined]
        return node

    return decorate


def _ms(t0: float) -> int:
    return int((time.monotonic() - t0) * 1000)


def _succeeded(update: dict[str, Any], worker: str, run_id: str, step_id: str, attempt: int, started: str,
               tracked: bool) -> dict[str, Any]:
    out = dict(update or {})
    if not tracked:
        return out
    ids = {"run_id": run_id, "step_id": step_id}
    out["worker_statuses"] = [{**s, **ids, "attempts": attempt} for s in out.get("worker_statuses") or []]
    if out.get("errors"):
        out["errors"] = [{**e, **ids} for e in out["errors"]]
    now = utc_now()
    out["run"] = {"steps": {worker: {"worker": worker, "status": "succeeded", "attempts": attempt, "step_id": step_id,
                                     "started_at": started, "finished_at": now, "code": None}},
                  "updated_at": now}
    return out


def _failed(exc: BaseException, text: str, fallback: Callable[[], dict[str, Any]] | None, worker: str, run_id: str,
            step_id: str, attempt: int, started: str, tracked: bool) -> dict[str, Any]:
    code, retryable = classify(exc)
    now = utc_now()
    out = dict(fallback() if fallback else {})
    out["next_worker"] = "supervisor"
    status: dict[str, Any] = {"worker": worker, "status": "error", "message": f"Failed: {text}"}
    error: dict[str, Any] = {"worker": worker, "error": text, "ts": now}
    if tracked:
        status.update(run_id=run_id, step_id=step_id, attempts=attempt)
        error.update(run_id=run_id, step_id=step_id, code=code)
        out["run"] = {
            "steps": {worker: {"worker": worker, "status": "failed", "attempts": attempt, "step_id": step_id,
                               "started_at": started, "finished_at": now, "code": code}},
            "status": "failed",
            "failure": {"step_id": step_id, "worker": worker, "code": code, "message": text, "retryable": retryable,
                        "attempts": attempt},
            "updated_at": now,
        }
    out["worker_statuses"] = [status]
    out["errors"] = [error]
    out["messages"] = [AIMessage(content=f"[{worker}] ERROR: {text}")]
    return out
