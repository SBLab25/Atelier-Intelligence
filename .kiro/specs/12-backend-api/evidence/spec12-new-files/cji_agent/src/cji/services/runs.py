"""
Workflow runs for the API and the CLI (Spec 12, OD-115/OD-116/OD-125).

Listing uses the run index; details and approval go through `Workflow` (the checkpoint store is the truth).
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

from cji.workflow.index import IndexedRun, RunIndex, indexed_from_values
from cji.workflow.runtime import RunOutcome, Workflow

WorkflowFactory = Callable[[], Workflow]
LATEST_SCAN = 20          # runs inspected when looking for the latest run with insights
logger = logging.getLogger("cji.api")


async def cli_status(workflow: Workflow, run_id: str) -> dict[str, Any]:
    """`cji --status`: the workflow's status dict, unchanged."""
    return await workflow.status(run_id)


def insights_of(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(i) for i in (values.get("insights") or []) if isinstance(i, dict)]


class RunService:
    def __init__(self, db_path: Path, workflow_factory: WorkflowFactory | None = None) -> None:
        self.db_path = Path(db_path)
        self._factory = workflow_factory

    def workflow(self) -> Workflow:
        wf = self._factory() if self._factory else Workflow(self.db_path)
        wf.db_path = self.db_path
        return wf

    @property
    def index(self) -> RunIndex:
        return RunIndex(self.db_path)

    def page(self, *, journeys: Collection[str] | None, journey_id: str | None, status: str | None, limit: int,
             after: tuple[str, str] | None) -> list[IndexedRun]:
        return self.index.page(journeys=journeys, journey_id=journey_id, status=status, limit=limit, after=after)

    async def get(self, run_id: str) -> tuple[IndexedRun, dict[str, Any], dict[str, Any]]:
        """(index row, status dict, state values). RunNotFound / LegacyRun propagate."""
        indexed = self.index.get(run_id)
        status, values = await self.workflow().inspect(run_id)
        if indexed is None:                       # written by a process that predates the index
            indexed = indexed_from_values(run_id, values)
            self.index.upsert(indexed)
        return indexed, status, values

    async def mark_approved(self, run_id: str) -> RunOutcome:
        return await self.workflow().mark_approved(run_id)

    async def continue_run(self, run_id: str) -> RunOutcome:
        return await self.workflow().resume(run_id)

    async def latest_with_insights(self, journey_id: str) -> tuple[str | None, list[dict[str, Any]]]:
        for row in self.page(journeys=None, journey_id=journey_id, status=None, limit=LATEST_SCAN, after=None):
            try:
                _status, values = await self.workflow().inspect(row.run_id)
            except Exception as exc:  # noqa: BLE001  # broad-except: an unreadable run is skipped while searching
                logger.info("insights: run %s skipped (%s)", row.run_id, type(exc).__name__)
                continue
            found = insights_of(values)
            if found:
                return row.run_id, found
        return None, []

    async def backfill(self) -> int:
        return await self.index.backfill(self.workflow())
