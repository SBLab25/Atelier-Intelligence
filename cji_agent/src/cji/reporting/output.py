"""
Report file output (Spec 10, design §5, OD-86): safe file name, path check, size limit, atomic write.

Nothing from the input can choose the directory: the journey name becomes a slug of `[a-z0-9_-]`, the id is a
validated run id or the input hash, and the resolved target must be a direct child of the reports directory.
The file is written to a temporary name in the same directory, synced and renamed; on any failure the
temporary file is removed and no report file appears.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import re
import tempfile
from pathlib import Path

from .model import ReportInput

MAX_REPORT_BYTES = 1024 * 1024
SLUG_CHARS = 64
_SLUG_ALLOWED = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")
_RUN_ID = re.compile(r"[A-Za-z0-9-]{1,64}")


class ReportOutputError(Exception):
    """A report could not be written. `code` is the structured error code (OD-90)."""

    code = "report_write_failed"


class ReportPathError(ReportOutputError):
    """The target would not be a direct child of the reports directory."""


class ReportTooLarge(ReportOutputError):
    code = "report_too_large"


class ReportWriteError(ReportOutputError):
    pass


def slug(journey_name: str) -> str:
    out = "".join(ch if ch in _SLUG_ALLOWED else "_" for ch in journey_name.lower())[:SLUG_CHARS]
    return out or "journey"


def report_filename(inp: ReportInput) -> str:
    ident = inp.run_id if _RUN_ID.fullmatch(inp.run_id) else inp.input_sha256()[:16]
    return f"cji_report_{slug(inp.journey_name)}_{ident}.html"


def _reason(exc: OSError) -> str:
    """The OS error text without the file names that str(OSError) appends."""
    if exc.strerror:
        return exc.strerror[:200]
    if exc.filename is None and exc.filename2 is None and str(exc):
        return str(exc)[:200]                  # e.g. OSError("disk full"): no file name attached
    return type(exc).__name__
def write_report(html: str, directory: Path, filename: str) -> tuple[Path, str, int]:
    """Write `html` to directory/filename atomically. Returns (path, sha256 hex, size in bytes)."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        base = directory.resolve(strict=True)
    except OSError as exc:
        # The message reaches the run state and the API: OS error text only, no server path (Spec 15, F-94).
        raise ReportWriteError(f"reports directory is not usable: {_reason(exc)}") from exc
    target = (base / filename).resolve()
    if target.parent != base or target.suffix != ".html" or target.name != filename:
        raise ReportPathError("report file name must be a plain .html name inside the reports directory")
    try:
        data = html.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ReportWriteError("report text is not valid UTF-8") from exc
    if len(data) > MAX_REPORT_BYTES:
        raise ReportTooLarge(f"report is {len(data)} bytes, over the limit of {MAX_REPORT_BYTES} bytes")
    fd, tmp_name = tempfile.mkstemp(prefix=".cji_report_", suffix=".tmp", dir=base)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except OSError as exc:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise ReportWriteError(f"could not write the report: {_reason(exc)}") from exc
    return target, hashlib.sha256(data).hexdigest(), len(data)
