"""Workflow errors and their classification (Spec 09, OD-72 / OD-76)."""
from __future__ import annotations

from integrations.errors import GatewayError

# Gateway codes worth another attempt besides those the gateway itself marks retryable.
RETRYABLE_CODES: frozenset[str] = frozenset({"connect_failed", "step_timeout"})


class StepError(RuntimeError):
    """A worker failure with a code (e.g. no_step_metrics, mode_mismatch, report_export_failed)."""

    code: str = "step_failed"
    retryable: bool = False

    def __init__(self, message: str, *, code: str | None = None, retryable: bool | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class WorkflowRuntimeError(RuntimeError):
    """A run cannot be started, approved or resumed as asked (the CLI prints it and exits 1)."""


class RunNotFound(WorkflowRuntimeError):
    pass


class LegacyRun(WorkflowRuntimeError):
    pass


class RunNotResumable(WorkflowRuntimeError):
    pass


class RunLeased(WorkflowRuntimeError):
    pass


def classify(exc: BaseException) -> tuple[str, bool]:
    """(code, retryable) for a worker failure."""
    if isinstance(exc, StepError):
        return exc.code, exc.retryable
    if isinstance(exc, GatewayError):
        return exc.code, bool(exc.retryable or exc.code in RETRYABLE_CODES)
    return "unexpected_error", False


def error_text(exc: BaseException) -> str:
    """Error text for workflow state: gateway and step messages are safe by construction; others are scrubbed."""
    if isinstance(exc, GatewayError | StepError):
        return str(exc)
    from integrations.audit import configured_secrets, scrub

    return f"{type(exc).__name__}: {scrub(str(exc), configured_secrets())[:300]}"
