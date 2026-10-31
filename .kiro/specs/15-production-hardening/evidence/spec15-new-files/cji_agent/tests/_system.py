"""
System-test harness (Spec 15, OD-169): real CJI processes on free loopback ports with a temporary home, and a
PostgreSQL server that can be stopped and started on a fixed port. Never touches DATABASE_URL / Supabase.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

APP = Path(__file__).resolve().parent.parent
MCP_MODULES = {
    "cji-journey-data": ("cji.mcp_servers.journey_data_server", "CJI_JOURNEY_DATA_PORT"),
    "cji-friction-engine": ("cji.mcp_servers.friction_engine_server", "CJI_FRICTION_ENGINE_PORT"),
    "cji-insight": ("cji.mcp_servers.insight_server", "CJI_INSIGHT_PORT"),
    "cji-report": ("cji.mcp_servers.report_server", "CJI_REPORT_PORT"),
    "cji-ingestion-intelligence": ("cji.mcp_servers.ingestion_intelligence_server", "CJI_INGESTION_INTELLIGENCE_PORT"),
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def http() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    return session


def wait_for(check, timeout: float, interval: float = 0.5) -> Any:
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        last = check()
        if last:
            return last
        time.sleep(interval)
    return last


def status_of(url: str, timeout: float = 3.0, **kw: Any) -> int:
    try:
        return http().get(url, timeout=timeout, **kw).status_code
    except requests.RequestException:
        return 0


@dataclass
class System:
    """One isolated deployment: home, environment, ports and processes."""

    root: Path
    extra_env: dict[str, str] = field(default_factory=dict)
    procs: dict[str, subprocess.Popen[bytes]] = field(default_factory=dict)
    ports: dict[str, int] = field(default_factory=dict)
    python: str = sys.executable  # the rollback drill runs other releases from their own venvs

    def __post_init__(self) -> None:
        self.home = self.root / "home"
        (self.home / "data").mkdir(parents=True, exist_ok=True)
        shutil.copy2(APP / "data" / "events.parquet", self.home / "data" / "events.parquet")
        self.logs = self.root / "logs"
        self.logs.mkdir(exist_ok=True)
        for name in MCP_MODULES:
            self.ports[name] = free_port()
        self.ports["api"] = free_port()
        self.ports["collector"] = free_port()

    def env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in ("CJI_TEST_DATABASE_URL", "PYTEST_CURRENT_TEST")}
        env.update(
            {
                "CJI_HOME": str(self.home),
                "CJI_ENV": "development",
                "CJI_MODE": "demo",
                "CJI_SERVICE_HOST": "127.0.0.1",
                "CJI_WORKFLOW_RETRY_BACKOFF_S": "0",
                "CJI_WORKFLOW_STEP_ATTEMPTS": "1",
                "CJI_WORKFLOW_STEP_TIMEOUT_S": "300",
                "CJI_MCP_CALL_TIMEOUT_S": "60",
                "CJI_CHECKPOINTS_DB": str(self.home / "data" / "cji_checkpoints.db"),
                "CJI_API_PORT": str(self.ports["api"]),
                "CJI_COLLECTOR_PORT": str(self.ports["collector"]),
                "CJI_API_CURSOR_SECRET": "r" * 40,
                "CJI_LOG_FORMAT": "json",
                "PYTHONIOENCODING": "utf-8",
                "CJI_AUDIT_DIR": str(self.home / "data" / "audit"),
            }
        )
        for name, (_module, key) in MCP_MODULES.items():
            env[key] = str(self.ports[name])
        env.update(self.extra_env)
        return env

    def start(self, name: str, *args: str) -> None:
        if name in MCP_MODULES:
            cmd = [self.python, "-m", MCP_MODULES[name][0]]
        elif name == "api":
            cmd = [self.python, "-m", "cji.api.serve", "--host", "127.0.0.1", "--port", str(self.ports["api"])]
        elif name == "collector":
            cmd = [
                self.python,
                "-m",
                "cji.collector.serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.ports["collector"]),
            ]
        else:
            raise ValueError(name)
        log = (self.logs / f"{name}.log").open("ab")
        self.procs[name] = subprocess.Popen(
            [*cmd, *args], cwd=self.home, env=self.env(), stdout=log, stderr=subprocess.STDOUT
        )
        ready = self.ready_url(name)
        proc = self.procs[name]
        # Started = answers HTTP at all (0.11.0 MCP servers have no /health; readiness is checked by the callers).
        if not wait_for(lambda: proc.poll() is not None or status_of(ready) != 0, 60) or proc.poll() is not None:
            raise RuntimeError(f"{name} did not start; log: {self.log_tail(name)}")

    def ready_url(self, name: str) -> str:
        port = self.ports[name]
        path = {"api": "/api/v1/health/ready", "collector": "/health/live"}.get(name, "/health")
        return f"http://127.0.0.1:{port}{path}"

    def url(self, name: str, path: str) -> str:
        return f"http://127.0.0.1:{self.ports[name]}{path}"

    def kill(self, name: str) -> None:
        proc = self.procs.pop(name, None)
        if proc is not None:
            proc.kill()  # TerminateProcess on Windows: an abrupt crash, no cleanup
            proc.wait(timeout=30)

    def start_mcp(self) -> None:
        for name in MCP_MODULES:
            self.start(name)

    def stop_all(self) -> None:
        for name in list(self.procs):
            self.kill(name)

    def log_tail(self, name: str, n: int = 3000) -> str:
        path = self.logs / f"{name}.log"
        return path.read_bytes()[-n:].decode("utf-8", "replace") if path.exists() else ""

    def token(self, role: str = "admin") -> str:
        from cji.api.auth import create_token

        return create_token(self.home / "data" / "api_tokens.json", label=f"recovery-{role}", role=role, journeys=["*"])


class Postgres:
    """A throwaway PostgreSQL on a fixed loopback port, controlled with pg_ctl (stop/start keep the data)."""

    def __init__(self, root: Path) -> None:
        import pgserver

        self.bin = Path(pgserver.__file__).parent / "pginstall" / "bin"
        self.data = root / "pgdata"
        self.port = free_port()
        self.log = root / "postgres.log"
        exe = ".exe" if os.name == "nt" else ""
        subprocess.run(
            [
                str(self.bin / f"initdb{exe}"),
                "-D",
                str(self.data),
                "-U",
                "postgres",
                "--auth=trust",
                "-E",
                "UTF8",
                "--no-instructions",
            ],
            check=True,
            capture_output=True,
        )
        self.start()
        self.create_database("cji")

    def create_database(self, name: str) -> None:
        if not name.isidentifier():
            raise ValueError(name)
        exe = ".exe" if os.name == "nt" else ""
        subprocess.run(
            [
                str(self.bin / f"psql{exe}"),
                "-h",
                "127.0.0.1",
                "-p",
                str(self.port),
                "-U",
                "postgres",
                "-c",
                f"CREATE DATABASE {name}",
            ],
            check=True,
            capture_output=True,
        )

    @property
    def url(self) -> str:
        return f"postgresql://postgres@127.0.0.1:{self.port}/cji"

    def _ctl(self, *args: str) -> None:
        exe = ".exe" if os.name == "nt" else ""
        # No pipes: the server started by pg_ctl inherits its handles, and a captured pipe would never close.
        subprocess.run(
            [str(self.bin / f"pg_ctl{exe}"), "-D", str(self.data), "-l", str(self.log), *args],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )

    def start(self) -> None:
        self._ctl("-o", f'-p {self.port} -h 127.0.0.1 -k ""', "-w", "start")

    def stop(self) -> None:
        self._ctl("-m", "fast", "-w", "stop")


def record(case: str, expected: str, observed: str, ok: bool) -> None:
    """Append the observed behaviour of a recovery case to RECOVERY_LOG (the gate turns it into recovery.md).
    Not a CJI_ name: settings refuse unknown CJI_ variables in tests."""
    target = os.environ.get("RECOVERY_LOG")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"case": case, "expected": expected, "observed": observed, "ok": ok}) + "\n")
