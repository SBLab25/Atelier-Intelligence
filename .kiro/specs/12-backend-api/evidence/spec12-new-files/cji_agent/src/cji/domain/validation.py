"""
Check-only validation at worker boundaries (Spec 03, RC-10).

check() never changes or rejects a value. It returns a WorkflowError describing the
first contract violation, or None when the value conforms. Pure module.
"""
from typing import Any

from pydantic import TypeAdapter, ValidationError

from .runs import ErrorSource, WorkflowError, workflow_error


def check(adapter: TypeAdapter[Any], value: object, worker: ErrorSource, what: str) -> WorkflowError | None:
    try:
        adapter.validate_python(value)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "<root>"
        return workflow_error(
            worker,
            f"contract violation in {what}: {exc.error_count()} problem(s); first at {where}: {first['msg']}",
        )
    return None
