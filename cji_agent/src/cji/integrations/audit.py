"""
Audit records for LLM and tool calls (Spec 08, OD-62).

Records are built from an allow-list of metadata fields only: no prompt or response text, no argument
values, no keys, no user/session/event ids, no URLs. `scrub` is a second line of defence for free text
that reaches logs (configured secret values and auth header values are replaced).
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger("cji.audit")
_log = logging.getLogger("cji.integrations")

AUDIT_FIELDS: tuple[str, ...] = (
    "ts", "kind", "service", "correlation_id", "call_id", "worker", "purpose", "tool", "provider", "model",
    "outcome", "code", "retryable", "attempts", "latency_ms", "input_tokens", "output_tokens", "cost_usd",
    "prompt_chars", "http_status", "arg_keys",
    # Spec 09 workflow records (kind=step / kind=run)
    "run_id", "step_id", "attempt", "from_status", "to_status",
    # Spec 15: traces (kind=span and every record above) and security records (kind=security)
    "trace_id", "span_id", "parent_id", "name", "request_id",
    "action", "actor", "role", "target", "mode", "rows",
)
_SPAN_KINDS = frozenset({"tool", "tool_session", "llm"})
SECURITY_ACTIONS: frozenset[str] = frozenset({
    "token.create", "token.revoke", "token.rotate", "auth.failed", "auth.rate_limited", "run.start", "run.resume",
    "run.approve", "ingestion.validate", "ingestion.write", "collector.key.create", "collector.key.revoke",
    "collector.admin.denied", "backup.create", "backup.restore", "migration.apply",
})
_AUTH_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:x-api-key|authorization)['\"]?\s*[:=]\s*['\"]?)[^'\",\s}]+"),
)


def scrub(text: str, secrets: Iterable[str | None] = ()) -> str:
    """Replace configured secret values and auth header values with [redacted]."""
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "[redacted]")
    for pattern in _AUTH_PATTERNS:
        text = pattern.sub(r"\1[redacted]", text)
    return text


def make_record(**fields: Any) -> dict[str, Any]:
    """An audit record with only allow-listed fields (unknown names are a programming error)."""
    unknown = set(fields) - set(AUDIT_FIELDS)
    if unknown:
        raise ValueError(f"not audit fields: {sorted(unknown)}")
    record: dict[str, Any] = {"ts": datetime.now(UTC).isoformat(timespec="milliseconds")}
    record.update({k: v for k, v in fields.items() if v is not None})
    _add_trace(record)
    return record


def _add_trace(record: dict[str, Any]) -> None:
    """Trace ids (Spec 15): the current trace, else the run's trace; tool and LLM calls get a span of their own."""
    from cji.observability.trace import current_span_id, current_trace_id, new_span_id, trace_id_for_run

    current = current_trace_id()
    if "trace_id" not in record:
        trace_id = current or trace_id_for_run(record.get("run_id") or record.get("correlation_id"))
        if trace_id:
            record["trace_id"] = trace_id
    if "span_id" in record or "trace_id" not in record:
        return
    if record.get("kind") in _SPAN_KINDS:
        record["span_id"] = new_span_id()
        parent = current_span_id() if record["trace_id"] == current else None
        if parent:
            record["parent_id"] = parent
    elif record.get("kind") == "step" and record["trace_id"] == current and current_span_id():
        record["span_id"] = current_span_id()       # the step's own span (workflow/step.py)


class AuditSink(Protocol):
    def write(self, record: dict[str, Any]) -> None: ...


class LogSink:
    """One JSON line per record on the `cji.audit` logger."""

    def write(self, record: dict[str, Any]) -> None:
        logger.info(json.dumps(record, sort_keys=True))


class JsonlSink:
    """Append-only JSONL file. A write failure is logged (type only) and never breaks the call."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, sort_keys=True) + "\n"
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
        except OSError as exc:
            _log.warning("audit file write failed: %s", type(exc).__name__)


class MultiSink:
    def __init__(self, *sinks: AuditSink) -> None:
        self.sinks = sinks

    def write(self, record: dict[str, Any]) -> None:
        for sink in self.sinks:
            sink.write(record)


def default_sink(service: str) -> AuditSink:
    """Log sink, plus `<audit_dir>/<service>.jsonl` when an audit directory is configured."""
    from cji.settings import get_settings

    audit_dir = get_settings().storage.audit_dir
    if audit_dir is None:
        return LogSink()
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", service) or "service"
    return MultiSink(LogSink(), JsonlSink(Path(audit_dir) / f"{safe}.jsonl"))


_security_sink: AuditSink | None = None
_security_lock = threading.Lock()


def security_sink() -> AuditSink:
    global _security_sink
    with _security_lock:
        if _security_sink is None:
            _security_sink = default_sink("security")
        return _security_sink


def reset_security_sink() -> None:
    """Forget the cached sink (tests change the audit directory between cases)."""
    global _security_sink
    with _security_lock:
        _security_sink = None


def security_event(action: str, *, actor: str | None, outcome: str, sink: AuditSink | None = None,
                   **fields: Any) -> dict[str, Any]:
    """Write one `kind=security` record (Spec 15, OD-162). Only allow-listed metadata: no values, comments or
    addresses. A failing sink is logged and never breaks the action."""
    if action not in SECURITY_ACTIONS:
        raise ValueError(f"not a security action: {action}")
    from cji.http.request_id import current_request_id
    from cji.observability.context import service_name

    request_id = current_request_id()
    record = make_record(kind="security", service=service_name(), action=action, actor=actor or "-",
                         outcome=outcome, request_id=None if request_id == "-" else request_id, **fields)
    try:
        (sink or security_sink()).write(record)
    except Exception as exc:  # noqa: BLE001  # broad-except: audit must not break the audited action
        _log.warning("security audit write failed: %s", type(exc).__name__)
    return record


def configured_secrets() -> tuple[str, ...]:
    """Secret values from settings (LLM keys, admin key, database URL and its password) for `scrub`."""
    from urllib.parse import urlsplit

    from cji.settings import get_settings, secret_value

    s = get_settings()
    values = [secret_value(s.llm.groq_api_key), secret_value(s.llm.anthropic_api_key),
              secret_value(s.llm.openai_api_key), secret_value(s.auth.admin_key)]
    url = s.database.url_value()
    if url:
        values.append(url)
        password = urlsplit(url).password
        if password:
            values.append(password)
    return tuple(v for v in values if v)
