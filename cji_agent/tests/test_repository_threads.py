"""
Spec 14 (G-1): the API serves sync routes from a thread pool, and the journey page asks for metrics, friction and
insights at the same time. The demo repository shares one DuckDB connection, so concurrent queries must not
interleave (unguarded, `execute(...).df()` returned None and the friction route answered 500).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from tests._api_harness import copy_demo_data

JOURNEY = "user_onboarding"


def test_concurrent_reads_on_one_demo_repository(tmp_path):
    from cji.repositories import DuckDbParquetRepository, TimeWindow

    repo = DuckDbParquetRepository(copy_demo_data(tmp_path))
    try:
        expected = repo.step_metrics(JOURNEY, TimeWindow())
        repo.close()                          # the first concurrent call opens the connection

        def read(i: int) -> object:
            if i % 3 == 0:
                return repo.funnel(JOURNEY, ["landing_page"], TimeWindow())
            if i % 3 == 1:
                return repo.events_page(JOURNEY, limit=5, after=None, step_id=None, event_type=None)
            return repo.step_metrics(JOURNEY, TimeWindow())

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(read, range(240)))
    finally:
        repo.close()
    assert all(isinstance(r, list) for r in results)
    assert all(results[i] == expected for i in range(2, 240, 3))
