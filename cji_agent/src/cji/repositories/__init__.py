"""
Event repositories (Spec 05).

    repo = get_repository()          # chosen once from Settings.app.mode
    with use_repository(fake): ...   # tests

demo → DuckDbParquetRepository(settings.storage.events_parquet)
realtime → PostgresEventRepository(settings.database)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from cji.settings import ConfigError, Settings, get_settings
from cji.settings.roles import database_missing

from .base import (
    EventRepository,
    LiveSnapshot,
    NotSupported,
    RepositoryError,
    TimeWindow,
    WriteResult,
)
from .postgres import PostgresEventRepository

__all__ = [
    "EventRepository",
    "LiveSnapshot",
    "NotSupported",
    "PostgresEventRepository",
    "RepositoryError",
    "TimeWindow",
    "WriteResult",
    "event_repository",
    "get_repository",
    "reset_repository",
    "use_repository",
]

_current: EventRepository | None = None


def event_repository(settings: Settings) -> EventRepository:
    """The repository for CJI. Requires a database URL."""
    url = settings.database.url_value()
    if not url:
        raise ConfigError([database_missing("CJI (event repository)")], env=settings.app.env)
    return PostgresEventRepository(url)


def get_repository() -> EventRepository:
    """Process-wide repository, created on first use from the active settings."""
    global _current
    if _current is None:
        _current = event_repository(get_settings())
    return _current


def reset_repository() -> None:
    global _current
    if _current is not None:
        _current.close()
    _current = None


@contextmanager
def use_repository(repository: EventRepository) -> Iterator[EventRepository]:
    """Make `repository` the active one inside the block (tests)."""
    global _current
    previous = _current
    _current = repository
    try:
        yield repository
    finally:
        _current = previous
