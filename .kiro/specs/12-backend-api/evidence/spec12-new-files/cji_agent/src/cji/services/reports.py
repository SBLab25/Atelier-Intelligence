"""
Report files (Spec 10 output) for the API and the dashboard (Spec 12, OD-114).

A report id is the file name without `cji_report_` and `.html` (e.g. `user_onboarding_<run id>`); the run id is
its last `_` segment when that is a UUID. Ids are pattern-checked and the resolved file must be a direct child of
the reports directory, so no request can name another path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

PREFIX = "cji_report_"
SUFFIX = ".html"
REPORT_ID = re.compile(r"[A-Za-z0-9_-]{1,140}")
_RUN_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
MAX_REPORT_BYTES = 1024 * 1024        # the writer's limit (reporting.output.MAX_REPORT_BYTES)


@dataclass(frozen=True)
class ReportFile:
    report_id: str
    run_id: str | None
    path: Path
    size_bytes: int
    modified: float

    @property
    def created_at(self) -> str:
        return datetime.fromtimestamp(self.modified, UTC).isoformat().replace("+00:00", "Z")


def list_report_files(reports_dir: Path) -> list[Path]:
    """HTML reports, newest first (the dashboard's report list)."""
    if not reports_dir.exists():
        return []
    return sorted(reports_dir.glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)


def report_id_for(file_name: str) -> str | None:
    if not (file_name.startswith(PREFIX) and file_name.endswith(SUFFIX)):
        return None
    ident = file_name[len(PREFIX):-len(SUFFIX)]
    return ident if REPORT_ID.fullmatch(ident) else None


def run_id_for(report_id: str) -> str | None:
    last = report_id.rsplit("_", 1)[-1]
    return last if _RUN_ID.fullmatch(last) else None


def _describe(path: Path) -> ReportFile | None:
    report_id = report_id_for(path.name)
    if report_id is None:
        return None
    stat = path.stat()
    return ReportFile(report_id, run_id_for(report_id), path, stat.st_size, stat.st_mtime)


def list_reports(reports_dir: Path) -> list[ReportFile]:
    """Report files with a valid id, newest first (ties by id, descending)."""
    found = [r for r in (_describe(p) for p in list_report_files(reports_dir)) if r is not None]
    return sorted(found, key=lambda r: (r.modified, r.report_id), reverse=True)


def find_report(reports_dir: Path, report_id: str) -> ReportFile | None:
    if not REPORT_ID.fullmatch(report_id) or not reports_dir.exists():
        return None
    base = reports_dir.resolve()
    target = (base / f"{PREFIX}{report_id}{SUFFIX}").resolve()
    if target.parent != base or not target.is_file():
        return None
    return _describe(target)


def read_report(report: ReportFile) -> bytes:
    """The file's bytes, at most MAX_REPORT_BYTES (larger files are refused with ValueError)."""
    with report.path.open("rb") as fh:
        data = fh.read(MAX_REPORT_BYTES + 1)
    if len(data) > MAX_REPORT_BYTES:
        raise ValueError("report file is larger than the report size limit")
    return data
