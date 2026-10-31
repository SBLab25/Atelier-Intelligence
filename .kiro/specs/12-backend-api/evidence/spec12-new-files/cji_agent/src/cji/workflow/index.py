"""
Run index (Spec 12, OD-115): one row per run in the checkpoint database, next to `run_leases`.

LangGraph stores checkpoints by thread id only; the index answers "the runs of journey X", "runs awaiting approval"
and "the latest run" without opening every thread. `Workflow` writes it after every stored step and status change.
Runs written before the index existed are added by `backfill`.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol

logger = logging.getLogger("cji.workflow")

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS run_index (run_id TEXT PRIMARY KEY, journey_id TEXT NOT NULL, mode TEXT NOT NULL, "
    "status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, report_file TEXT)"
)
_ORDER = "CREATE INDEX IF NOT EXISTS run_index_updated ON run_index (updated_at DESC, run_id DESC)"
_COLUMNS = "run_id, journey_id, mode, status, created_at, updated_at, report_file"


@dataclass(frozen=True)
class IndexedRun:
    run_id: str
    journey_id: str
    mode: str
    status: str
    created_at: str
    updated_at: str
    report_file: str | None


class _Inspector(Protocol):
    db_path: Path

    async def inspect(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]: ...


def report_file_name(report_path: str | None) -> str | None:
    """File name of a report path from run state (either path style), else None."""
    if not report_path:
        return None
    name = PureWindowsPath(report_path).name if "\\" in report_path else PurePosixPath(report_path).name
    return name or None


def indexed_from_values(run_id: str, values: Mapping[str, Any]) -> IndexedRun:
    run = values.get("run") or {}
    now = datetime.now(UTC).isoformat()
    created = str(run.get("created_at") or now)
    return IndexedRun(
        run_id=run_id,
        journey_id=str(values.get("journey_name") or ""),
        mode=str(values.get("mode") or ""),
        status=str(run.get("status") or "running"),
        created_at=created,
        updated_at=str(run.get("updated_at") or created),
        report_file=report_file_name(values.get("report_path")),
    )


class RunIndex:
    def __init__(self, db_path: Path | str) -> None:
        self.path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.execute(_SCHEMA)
        conn.execute(_ORDER)
        return conn

    def upsert(self, run: IndexedRun) -> None:
        conn = self._connect()
        try:
            conn.execute(
                f"INSERT INTO run_index ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(run_id) DO UPDATE SET "  # nosec B608 - fixed column list
                "journey_id = excluded.journey_id, mode = excluded.mode, status = excluded.status, "
                "updated_at = excluded.updated_at, report_file = COALESCE(excluded.report_file, report_file)",
                (run.run_id, run.journey_id, run.mode, run.status, run.created_at, run.updated_at, run.report_file),
            )
        finally:
            conn.close()

    def record(self, run_id: str, values: Mapping[str, Any]) -> None:
        self.upsert(indexed_from_values(run_id, values))

    def get(self, run_id: str) -> IndexedRun | None:
        conn = self._connect()
        try:
            row = conn.execute(f"SELECT {_COLUMNS} FROM run_index WHERE run_id = ?", (run_id,)).fetchone()  # nosec B608 - fixed column list
        finally:
            conn.close()
        return IndexedRun(*row) if row else None

    def page(self, *, journeys: Collection[str] | None, journey_id: str | None, status: str | None, limit: int,
             after: tuple[str, str] | None) -> list[IndexedRun]:
        """Newest first (updated_at, run_id descending). `journeys` None = all journeys."""
        clauses: list[str] = []
        params: list[Any] = []
        if journeys is not None:
            if not journeys:
                return []
            clauses.append("journey_id IN (" + ", ".join("?" for _ in journeys) + ")")   # placeholders only
            params += list(journeys)
        if journey_id is not None:
            clauses.append("journey_id = ?")
            params.append(journey_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if after is not None:
            clauses.append("(updated_at < ? OR (updated_at = ? AND run_id < ?))")
            params += [after[0], after[0], after[1]]
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT {_COLUMNS} FROM run_index{where} ORDER BY updated_at DESC, run_id DESC LIMIT ?"  # nosec B608 - fixed fragments only
        conn = self._connect()
        try:
            rows = conn.execute(sql, (*params, limit)).fetchall()
        finally:
            conn.close()
        return [IndexedRun(*row) for row in rows]

    def thread_ids(self) -> list[str]:
        """Thread ids stored by the checkpointer (read-only, no parameters)."""
        conn = self._connect()
        try:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'checkpoints'").fetchone()
            if not exists:
                return []
            return [str(r[0]) for r in conn.execute("SELECT DISTINCT thread_id FROM checkpoints").fetchall()]
        finally:
            conn.close()

    async def backfill(self, workflow: _Inspector) -> int:
        """Index runs present in the checkpoints but not in the index. Returns how many were added."""
        added = 0
        for run_id in self.thread_ids():
            if self.get(run_id) is not None:
                continue
            try:
                _status, values = await workflow.inspect(run_id)
            except Exception as exc:  # noqa: BLE001  # broad-except: legacy or unreadable runs are skipped, not fatal
                logger.info("run index backfill skipped %s: %s", run_id, type(exc).__name__)
                continue
            self.record(run_id, values)
            added += 1
        return added
