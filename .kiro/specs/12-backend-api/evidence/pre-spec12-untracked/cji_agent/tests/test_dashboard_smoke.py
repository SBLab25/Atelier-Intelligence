"""
Spec 06 (CL-08, CL-14): the dashboard renders headless when PostgreSQL is
unreachable and says which panels could not load, instead of showing empty
panels without a reason.

Uses Streamlit's AppTest. The database URL points at a closed local port, so
nothing leaves the machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest

from cji.dashboard_launcher import dashboard_path
from cji.settings import make_test_settings, override_settings

APP_ROOT = Path(__file__).resolve().parent.parent
DEAD_DATABASE = "postgresql://cji:cji@127.0.0.1:1/cji"


def _run_dashboard(tmp_path, **env):
    settings = make_test_settings(tmp_path, CJI_MODE="demo", **env)
    with override_settings(settings):
        app = AppTest.from_file(str(dashboard_path()), default_timeout=120)    # the installed cji/dashboard.py
        app.run()
    return app


def test_dashboard_renders_and_reports_unreachable_database(tmp_path):
    app = _run_dashboard(tmp_path, DATABASE_URL=DEAD_DATABASE)

    assert not app.exception, [e.value for e in app.exception]
    warnings = " ".join(w.value for w in app.warning)
    assert "Could not load" in warnings
    assert "OperationalError" in warnings
    assert "cji:cji@" not in warnings          # credentials never shown


def test_dashboard_renders_without_a_database(tmp_path):
    app = _run_dashboard(tmp_path)

    assert not app.exception, [e.value for e in app.exception]
    assert not [w for w in app.warning if "Could not load" in w.value]
