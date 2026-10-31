"""
cji-dashboard: start the Streamlit dashboard of the installed package (Spec 11, OD-97).

Runs `streamlit run <installed cji/dashboard.py>` in the runtime home (CJI_HOME, default: the working directory).
Arguments after the known options go to `streamlit run`, e.g. `cji-dashboard --server.port 8502`.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from importlib.resources import files
from pathlib import Path


def dashboard_path() -> Path:
    """The dashboard script inside the installed package."""
    return Path(str(files("cji") / "dashboard.py"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cji-dashboard",
        description="Start the CJI dashboard (streamlit run cji/dashboard.py) in the runtime home (CJI_HOME). "
                    "Other arguments are passed to `streamlit run`.",
    )
    _, extra = parser.parse_known_args(argv)
    from cji.settings import resolve_home

    home = resolve_home()
    command = [sys.executable, "-m", "streamlit", "run", str(dashboard_path()), *extra]
    return subprocess.call(command, cwd=home, env={**os.environ, "CJI_HOME": str(home)})  # nosec B603


if __name__ == "__main__":
    raise SystemExit(main())
