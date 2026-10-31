"""
CJI typed settings and service registry (Spec 04).

    settings = get_settings()                 # cached, loaded on first use
    require(settings, "collector")            # startup check for one role
    with override_settings(other): ...        # tests

Pure package: stdlib, pydantic and python-dotenv only. Importing it reads nothing;
the environment and `.env` are read on the first get_settings() / load_settings().
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import ConfigError
from .load import APP_ROOT, DEFAULT_DOTENV_PATH, KNOWN_KEYS, load_settings
from .model import Settings, secret_value
from .roles import require
from .services import SERVICE_NAMES, ServiceEndpoint, ServiceName, ServiceRegistry

__all__ = [
    "APP_ROOT",
    "DEFAULT_DOTENV_PATH",
    "KNOWN_KEYS",
    "SERVICE_NAMES",
    "ConfigError",
    "ServiceEndpoint",
    "ServiceName",
    "ServiceRegistry",
    "Settings",
    "get_settings",
    "load_settings",
    "make_test_settings",
    "override_settings",
    "require",
    "reset_settings",
    "secret_value",
]

_current: Settings | None = None


def get_settings() -> Settings:
    """The process-wide settings, loaded from os.environ and `.env` on first use."""
    global _current
    if _current is None:
        _current = load_settings()
    return _current


def reset_settings() -> None:
    """Forget the cached settings; the next get_settings() reloads them."""
    global _current
    _current = None


@contextmanager
def override_settings(settings: Settings) -> Iterator[Settings]:
    """Make `settings` the active settings inside the block (tests)."""
    global _current
    previous = _current
    _current = settings
    try:
        yield settings
    finally:
        _current = previous


def make_test_settings(tmp_path: Path, **env: str) -> Settings:
    """Test settings: CJI_ENV=test, storage under tmp_path, no `.env`, extra variables from **env."""
    values = {
        "CJI_ENV": "test",
        "CJI_DATA_DIR": str(tmp_path / "data"),
        "CJI_REPORTS_DIR": str(tmp_path / "reports"),
        **env,
    }
    return load_settings(values, dotenv_path=None)
