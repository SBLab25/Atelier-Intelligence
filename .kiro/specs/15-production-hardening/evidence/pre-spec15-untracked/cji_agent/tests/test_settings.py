"""
Spec 04 — typed configuration and service discovery.

Offline: settings are built from explicit mappings with dotenv_path=None, so no
.env is read and no database, LLM or network is touched.
"""
import ast
import asyncio
import contextlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import pytest

from cji.settings import (
    ConfigError,
    get_settings,
    load_settings,
    make_test_settings,
    override_settings,
    require,
)

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src" / "cji"                       # the package sources (Spec 11)
GOOD_KEY = "k" * 40
SENTINEL = "SENTINEL-do-not-print-7f3a"   # 26 characters: too short for an admin key
ENVS = ("development", "test", "production")
MCP_NAMES = ("cji-ingestion-intelligence", "cji-journey-data", "cji-friction-engine", "cji-insight", "cji-report")
SERVER_FILES = {
    "cji-ingestion-intelligence": "ingestion_intelligence_server.py",
    "cji-journey-data": "journey_data_server.py",
    "cji-friction-engine": "friction_engine_server.py",
    "cji-insight": "insight_server.py",
    "cji-report": "report_server.py",
}
DB = "postgresql://user@127.0.0.1:1/cji"


def load(env=None):
    return load_settings(dict(env or {}), dotenv_path=None)


def clean_env(**extra):
    """Process environment without CJI_* or database variables (subprocess tests)."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CJI_") and k not in ("DATABASE_URL", "SUPABASE_DATABASE_URL")}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", **extra})
    return env


# ═════════════════════════════════════════════════════════════════════════════
# Defaults, parsing, .env
# ═════════════════════════════════════════════════════════════════════════════

def test_empty_environment_gives_documented_defaults():
    s = load()
    assert (s.app.env, s.app.mode, s.app.journey_name) == ("production", "demo", "user_onboarding")
    assert s.database.url is None and s.auth.admin_key is None and s.llm.groq_api_key is None
    assert s.cors.origins == () and s.keepalive.url is None
    assert s.llm.timeout_s == 30 and s.llm.retry.attempts == 3
    assert (s.llm.retry.min_wait_s, s.llm.retry.max_wait_s) == (2, 10)
    assert (s.mcp.connect_timeout_s, s.mcp.read_timeout_s) == (5, 300)
    assert (s.budgets.max_agent_iterations, s.budgets.recursion_limit, s.budgets.pipeline_timeout_s) == (20, 60, 180)
    # Spec 11: storage defaults are under the runtime home, the working directory when CJI_HOME is unset
    assert s.storage.home == Path.cwd().resolve()
    assert s.storage.events_parquet == Path.cwd().resolve() / "data" / "events.parquet"
    assert s.storage.reports_dir == Path.cwd().resolve() / "reports"


def test_registry_defaults_match_the_current_topology():
    s = load()
    ports = {e.name: e.port for e in s.services.services}
    assert ports == {"cji-journey-data": 8001, "cji-friction-engine": 8002, "cji-insight": 8003,
                     "cji-report": 8004, "cji-ingestion-intelligence": 8005,
                     "collector": 8000, "dashboard": 8501, "frontend": 3000, "api": 8006}
    assert s.services.get("cji-report").url == "http://127.0.0.1:8004/sse"
    assert [e.name for e in s.services.mcp_services()] == list(MCP_NAMES)
    assert {e.transport for e in s.services.mcp_services()} == {"sse"}


def test_no_secret_or_credential_has_a_default():
    text = json.dumps(load().describe())
    for marker in ("password", "change-me", "postgres:", "onrender"):
        assert marker not in text


def test_variables_are_parsed_and_typed(tmp_path):
    s = load({
        "CJI_ENV": " Development ", "CJI_MODE": "REALTIME", "CJI_REPORT_PORT": "9104",
        "CJI_SERVICE_HOST": "localhost", "CJI_INSIGHT_URL": "https://insight.internal.example/sse",
        "CJI_LLM_TIMEOUT_S": "12.5", "MAX_AGENT_ITERATIONS": "7", "LANGCHAIN_TRACING_V2": "true",
        "CJI_DATA_DIR": str(tmp_path / "d"), "CJI_CORS_ORIGINS": "https://a.example, http://localhost:3000",
        "CJI_ADMIN_KEY": GOOD_KEY,
    })
    assert (s.app.env, s.app.mode) == ("development", "realtime")
    assert s.services.get("cji-report").url == "http://localhost:9104/sse"
    assert s.services.get("cji-insight").url == "https://insight.internal.example/sse"
    assert s.llm.timeout_s == 12.5 and s.budgets.recursion_limit == 21
    assert s.observability.langchain_tracing is True
    assert s.storage.events_parquet == tmp_path / "d" / "events.parquet"
    assert s.cors.origins == ("https://a.example", "http://localhost:3000")
    assert s.auth.admin_key is not None and GOOD_KEY not in repr(s)


def test_postgres_scheme_is_normalised_and_supabase_url_is_accepted():
    s = load({"SUPABASE_DATABASE_URL": "postgres://u:p@db.example:5432/x"})
    assert s.database.url_value() == "postgresql://u:p@db.example:5432/x"
    assert s.database.source == "SUPABASE_DATABASE_URL"


def test_database_url_wins_over_supabase_url_with_a_warning():
    s = load({"DATABASE_URL": "postgresql://a@h/x", "SUPABASE_DATABASE_URL": "postgresql://b@h/y"})
    assert s.database.source == "DATABASE_URL" and s.database.url_value() == "postgresql://a@h/x"
    assert any("SUPABASE_DATABASE_URL" in w for w in s.warnings)
    assert not any("a@h" in w or "b@h" in w for w in s.warnings)


def test_legacy_collector_variables_still_work_with_a_warning():
    s = load({"COLLECTOR_HOST": "http://localhost", "COLLECTOR_PORT": "8100"})
    collector = s.services.get("collector")
    assert collector.port == 8100 and collector.url == "http://localhost:8100"
    assert sum("CJI_COLLECTOR" in w for w in s.warnings) == 2


def test_development_cors_defaults_come_from_the_registry():
    dev = load({"CJI_ENV": "development"}).cors.origins
    assert {"http://localhost:8501", "http://127.0.0.1:8501", "http://localhost:3000"} <= set(dev)
    assert load({"CJI_ENV": "test"}).cors.origins == ()
    assert load({"CJI_ENV": "production"}).cors.origins == ()


def test_dotenv_is_merged_under_the_process_environment(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("JOURNEY_NAME=from_file\nLLM_MODEL=file-model\n", encoding="utf-8")
    s = load_settings({"LLM_MODEL": "process-model"}, dotenv_path=dotenv)
    assert s.app.journey_name == "from_file" and s.llm.model == "process-model"


def test_dotenv_is_never_read_in_test(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("JOURNEY_NAME=from_file\n", encoding="utf-8")
    assert load_settings({"CJI_ENV": "test"}, dotenv_path=dotenv).app.journey_name == "user_onboarding"


def test_cji_env_may_come_from_dotenv(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("CJI_ENV=development\n", encoding="utf-8")
    assert load_settings({}, dotenv_path=dotenv).app.env == "development"


# ═════════════════════════════════════════════════════════════════════════════
# Missing and invalid configuration
# ═════════════════════════════════════════════════════════════════════════════

INVALID = [
    ({"CJI_MODE": "relatime"}, ["CJI_MODE='relatime'", "'demo' or 'realtime'"]),
    ({"CJI_ENV": "staging"}, ["CJI_ENV='staging'", "'development', 'test' or 'production'"]),
    ({"CJI_MCP_READ_TIMEOUT_S": "5m"}, ["CJI_MCP_READ_TIMEOUT_S='5m'", "seconds > 0", "e.g. 300"]),
    ({"CJI_LLM_TIMEOUT_S": "0"}, ["CJI_LLM_TIMEOUT_S='0'", "> 0"]),
    ({"MAX_AGENT_ITERATIONS": "zero"}, ["MAX_AGENT_ITERATIONS='zero'", "whole number"]),
    ({"CJI_REPORT_PORT": "70000"}, ["CJI_REPORT_PORT='70000'", "65535"]),
    ({"CJI_REPORT_PORT": "8003"}, ["CJI_REPORT_PORT=8003", "already used by cji-insight"]),
    ({"CJI_REPORT_URL": "localhost:8004"}, ["CJI_REPORT_URL", "scheme and host"]),
    ({"CJI_CORS_ORIGINS": "*"}, ["CJI_CORS_ORIGINS", "'*' is not allowed"]),
    ({"CJI_CORS_ORIGINS": "https://app.example.com/"}, ["CJI_CORS_ORIGINS", "trailing slash"]),
    ({"DATABASE_URL": "mysql://u:" + SENTINEL + "@h/db"}, ["DATABASE_URL", "postgresql://", "value not shown"]),
    ({"INGESTION_CONFIDENCE_THRESHOLD": "1.5"}, ["INGESTION_CONFIDENCE_THRESHOLD", "from 0 to 1"]),
    ({"LANGCHAIN_TRACING_V2": "maybe"}, ["LANGCHAIN_TRACING_V2", "true or false"]),
    ({"CJI_LLM_RETRY_MIN_S": "20"}, ["CJI_LLM_RETRY_MAX_S", "CJI_LLM_RETRY_MIN_S"]),
    ({"COLLECTOR_HOST": "localhost"}, ["COLLECTOR_HOST", "scheme and host"]),
    ({"CJI_ENV": "test", "CJI_CORS_ORIGIN": "x"}, ["CJI_CORS_ORIGIN is not a known setting", "Did you mean CJI_CORS_ORIGINS"]),
]


@pytest.mark.parametrize("env, expected", INVALID, ids=[next(iter(e)) for e, _ in INVALID])
def test_invalid_values_give_actionable_errors(env, expected):
    with pytest.raises(ConfigError) as exc:
        load(env)
    message = str(exc.value)
    for fragment in expected:
        assert fragment in message
    assert "Run: cji-settings check" in message
    assert SENTINEL not in message


def test_all_problems_are_reported_together():
    with pytest.raises(ConfigError) as exc:
        load({"CJI_MODE": "x", "CJI_REPORT_PORT": "0", "CJI_CORS_ORIGINS": "*"})
    assert len(exc.value.problems) == 3


def test_unknown_cji_variable_is_only_a_warning_outside_test():
    s = load({"CJI_CORS_ORIGIN": "x"})
    assert any("Did you mean CJI_CORS_ORIGINS" in w for w in s.warnings)


def test_config_error_is_a_runtime_error():
    assert issubclass(ConfigError, RuntimeError)


# ═════════════════════════════════════════════════════════════════════════════
# Environments x roles
# ═════════════════════════════════════════════════════════════════════════════

OFFLINE_ROLES = ["cli", "launcher", "dashboard", *[f"mcp:{n}" for n in MCP_NAMES]]


@pytest.mark.parametrize("env", ENVS)
@pytest.mark.parametrize("role", OFFLINE_ROLES)
def test_offline_demo_needs_no_keys_database_or_network(env, role):
    require(load({"CJI_ENV": env}), role)


@pytest.mark.parametrize("env", ENVS)
@pytest.mark.parametrize("role", ["cli", "dashboard", "mcp:cji-journey-data"])
def test_realtime_requires_a_database(env, role):
    with pytest.raises(ConfigError) as exc:
        require(load({"CJI_ENV": env, "CJI_MODE": "realtime"}), role)
    assert "DATABASE_URL" in str(exc.value) and "SUPABASE_DATABASE_URL" in str(exc.value)
    require(load({"CJI_ENV": env, "CJI_MODE": "realtime", "SUPABASE_DATABASE_URL": DB}), role)


@pytest.mark.parametrize("env, passes", [("development", True), ("test", False), ("production", False)])
def test_collector_without_secrets(env, passes):
    s = load({"CJI_ENV": env, "DATABASE_URL": DB})
    if passes:
        require(s, "collector")
    else:
        with pytest.raises(ConfigError) as exc:
            require(s, "collector")
        assert "CJI_ADMIN_KEY" in str(exc.value) and "CJI_CORS_ORIGINS" in str(exc.value)


@pytest.mark.parametrize("env", ENVS)
def test_collector_fully_configured_passes(env):
    require(load({"CJI_ENV": env, "DATABASE_URL": DB, "CJI_ADMIN_KEY": GOOD_KEY,
                  "CJI_CORS_ORIGINS": "https://app.example"}), "collector")


def test_collector_reports_every_missing_setting_without_secret_values():
    with pytest.raises(ConfigError) as exc:
        require(load({"CJI_ADMIN_KEY": SENTINEL}), "collector")
    assert len(exc.value.problems) == 3
    assert SENTINEL not in str(exc.value)
    assert "secrets.token_urlsafe(32)" in str(exc.value)


@pytest.mark.parametrize("key", ["change-me-in-production", "change-me"])
def test_known_default_admin_keys_never_pass_in_production(key):
    with pytest.raises(ConfigError, match="CJI_ADMIN_KEY"):
        require(load({"CJI_ADMIN_KEY": key, "CJI_CORS_ORIGINS": "https://a.example", "DATABASE_URL": DB}),
                "collector")


def test_production_rejects_plain_http_remote_endpoints():
    with pytest.raises(ConfigError, match="https"):
        require(load({"CJI_COLLECTOR_URL": "http://collector.example.com"}), "cli")
    require(load({"CJI_ENV": "development", "CJI_COLLECTOR_URL": "http://collector.example.com"}), "cli")
    require(load({"CJI_COLLECTOR_URL": "http://localhost:8000"}), "cli")
    require(load({"CJI_COLLECTOR_URL": "https://collector.example.com"}), "cli")


def test_unknown_role_and_unknown_service_are_reported():
    with pytest.raises(ConfigError, match="Unknown MCP service 'cji-reports'"):
        require(load(), "mcp:cji-reports")
    with pytest.raises(ConfigError, match="Unknown role"):
        require(load(), "worker")
    with pytest.raises(ConfigError, match="Known: "):
        load().services.get("cji-reports")


# ═════════════════════════════════════════════════════════════════════════════
# Test injection
# ═════════════════════════════════════════════════════════════════════════════

def test_tests_can_inject_endpoints_and_temporary_storage(tmp_path):
    from cji.tools import mcp_client

    s = make_test_settings(tmp_path)
    injected = s.with_endpoint("cji-report", url="http://127.0.0.1:59999/sse")
    with override_settings(injected):
        assert get_settings() is injected
        assert mcp_client.server_url("cji-report") == "http://127.0.0.1:59999/sse"
        assert get_settings().storage.reports_dir == tmp_path / "reports"
    assert get_settings() is not injected
    assert not (tmp_path / "data").exists()       # building settings creates nothing
    s.ensure_storage()
    assert (tmp_path / "data" / "ingestion_uploads").is_dir() and (tmp_path / "reports").is_dir()


def test_mcp_client_resolves_only_mcp_services():
    from cji.tools import mcp_client

    with pytest.raises(ConfigError, match="not an MCP service"):
        mcp_client.server_url("collector")
    with pytest.raises(ConfigError, match="Unknown service"):
        mcp_client.server_url("cji-nope")


# ═════════════════════════════════════════════════════════════════════════════
# Startup paths resolve their services
# ═════════════════════════════════════════════════════════════════════════════

class _FakePopen:
    started: ClassVar[list[str]] = []

    def __init__(self, cmd, **kwargs):
        _FakePopen.started.append(cmd[-1])

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0


def test_launcher_starts_exactly_the_registry_mcp_services(monkeypatch, tmp_path):
    from cji import run_servers

    _FakePopen.started = []
    monkeypatch.setattr(run_servers.subprocess, "Popen", _FakePopen)
    s = make_test_settings(tmp_path)
    with override_settings(s):
        assert run_servers.main([]) == 0
    assert _FakePopen.started == [e.launch for e in s.services.mcp_services()]


def test_launcher_exits_2_on_a_configuration_error(monkeypatch):
    from cji import run_servers

    _FakePopen.started = []
    monkeypatch.setattr(run_servers.subprocess, "Popen", _FakePopen)
    with override_settings(load({"CJI_COLLECTOR_URL": "http://collector.example.com"})):
        assert run_servers.main([]) == 2
    assert _FakePopen.started == []


def _fastmcp_name(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "FastMCP":
            return node.args[0].value
    return None


def _main_block_serve_name(tree):
    for node in tree.body:
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            for call in ast.walk(node):
                if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "serve":
                    return call.args[1].value
    return None


@pytest.mark.parametrize("name, filename", SERVER_FILES.items())
def test_each_mcp_server_starts_through_the_registry(name, filename):
    source = (SRC / "mcp_servers" / filename).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert _fastmcp_name(tree) == name
    assert _main_block_serve_name(tree) == name
    assert "mcp.run(" not in source


def test_server_files_cover_the_registry():
    assert set(SERVER_FILES) == set(MCP_NAMES) == {e.name for e in load().services.mcp_services()}


@pytest.mark.parametrize("name", MCP_NAMES)
def test_serve_listens_on_the_registry_endpoint(name, tmp_path):
    from cji.mcp_servers._serve import serve

    calls = []

    class FakeMCP:
        def __init__(self):
            self.name = name

        def run(self, **kwargs):
            calls.append(kwargs)

    s = make_test_settings(tmp_path, CJI_REPORT_PORT="9104")
    with override_settings(s):
        serve(FakeMCP(), name)
    endpoint = s.services.get(name)
    assert calls == [{"transport": "sse", "host": endpoint.host, "port": endpoint.port}]
    assert (name != "cji-report") or endpoint.port == 9104


def test_serve_refuses_a_mismatched_server(tmp_path):
    from cji.mcp_servers._serve import serve

    class FakeMCP:
        name = "cji-insight"

        def run(self, **kwargs):
            raise AssertionError("must not run")

    with override_settings(make_test_settings(tmp_path)), pytest.raises(SystemExit) as exc:
        serve(FakeMCP(), "cji-report")
    assert exc.value.code == 2


def test_preflight_pings_every_service_the_workers_use(monkeypatch):
    from cji.tools import mcp_client

    used = set()
    for path in (SRC / "agents").glob("*.py"):
        used |= set(re.findall(r'"(cji-[a-z-]+)"', path.read_text(encoding="utf-8")))
    assert used and used <= set(MCP_NAMES)

    pinged = []

    @contextlib.asynccontextmanager
    async def fake_session(name):
        pinged.append(name)
        yield object()

    monkeypatch.setattr(mcp_client, "mcp_session", fake_session)
    asyncio.run(mcp_client.ping_all_servers())
    assert pinged == list(MCP_NAMES)


class _FakeConn:
    def execute(self, *args, **kwargs):
        return None


class _FakeEngine:
    @contextlib.contextmanager
    def begin(self):
        yield _FakeConn()

    connect = begin

    def dispose(self):
        pass


def test_collector_startup_validates_its_configuration(monkeypatch):
    from cji.collector import api

    monkeypatch.setattr(api, "engine", _FakeEngine())
    monkeypatch.setattr(api, "CJI_ENV", "development")
    monkeypatch.setattr(api, "CJI_ADMIN_KEY", "")
    monkeypatch.setattr(api, "CJI_CORS_ORIGINS", [])
    asyncio.run(api.startup_event())

    monkeypatch.setattr(api, "CJI_ENV", "production")
    monkeypatch.setattr(api, "engine", api.UnconfiguredDatabase())
    with pytest.raises(ConfigError) as exc:
        asyncio.run(api.startup_event())
    assert len(exc.value.problems) == 3
    assert "DATABASE_URL" in str(exc.value)


def test_collector_without_database_fails_with_a_configuration_error():
    from cji.collector import api

    with pytest.raises(ConfigError, match="DATABASE_URL"), api.UnconfiguredDatabase().begin():
        pass


def test_cli_exits_2_when_realtime_has_no_database():
    out = subprocess.run(
        [sys.executable, "-m", "cji.main", "--mode", "realtime", "--run"],
        cwd=APP_ROOT, env=clean_env(CJI_ENV="test"), capture_output=True, text=True,
        timeout=300, check=False,
    )
    assert out.returncode == 2, out.stdout[-500:] + out.stderr[-800:]
    assert "DATABASE_URL" in out.stdout + out.stderr


def test_dashboard_resolves_settings_through_its_role():
    source = (SRC / "dashboard.py").read_text(encoding="utf-8")
    assert 'require(get_settings(), "dashboard")' in source
    for gone in ("load_dotenv", 'os.environ.get("DATABASE_URL")', ".venv"):
        assert gone not in source


# ═════════════════════════════════════════════════════════════════════════════
# Callers use settings
# ═════════════════════════════════════════════════════════════════════════════

def test_config_facade_reexports_settings_values():
    from cji import config

    s = config.SETTINGS
    assert config.EVENTS_PARQUET == s.storage.events_parquet
    assert config.MAX_AGENT_ITERATIONS == s.budgets.max_agent_iterations
    assert config.COLLECTOR_URL == s.services.get("collector").url
    assert config.CJI_CORS_ORIGINS == list(s.cors.origins)
    assert isinstance(config.DATABASE_URL, str) and isinstance(config.CJI_ADMIN_KEY, str)
    assert "password@" not in config.DATABASE_URL
    assert config.CJI_ADMIN_KEY != "change-me-in-production"


def _offline_gateway(service, seen):
    """A gateway from the active settings whose single request fails offline (Spec 08)."""
    import httpx

    from cji.integrations import LLMGateway
    from cji.integrations.testing import MemoryAuditSink, ScriptedTransport

    def capture(request):
        seen["timeout"] = request.extensions["timeout"]["read"]
        raise httpx.ConnectError("offline")

    return LLMGateway.from_settings(service, transport=ScriptedTransport(capture), audit=MemoryAuditSink())


def test_report_llm_call_uses_the_configured_timeout(monkeypatch, tmp_path):
    from cji.mcp_servers import report_server as rs

    seen = {}
    with override_settings(make_test_settings(tmp_path, GROQ_API_KEY="dummy", CJI_LLM_TIMEOUT_S="7",
                                              CJI_LLM_RETRY_ATTEMPTS="1")):
        monkeypatch.setattr(rs, "_llm", _offline_gateway("cji-report", seen))
        out = asyncio.run(rs.generate_narrative(insights=[], journey_name="j", avg_score=1.0, critical_count=0,
                                                mode="demo"))
    assert seen["timeout"] == 7
    assert out["narrative"]                      # fallback narrative, as before


def test_insight_llm_call_uses_the_configured_timeout(monkeypatch, tmp_path):
    from cji.mcp_servers import insight_server as ins

    seen = {}
    with override_settings(make_test_settings(tmp_path, GROQ_API_KEY="dummy", CJI_LLM_TIMEOUT_S="7",
                                              CJI_LLM_RETRY_ATTEMPTS="1")):
        monkeypatch.setattr(ins, "_llm", _offline_gateway("cji-insight", seen))
        out = asyncio.run(ins.generate_insight({"step_id": "sign_up_form"}))
    assert seen["timeout"] == 7
    assert out["insight"]["title"] == "Friction at sign_up_form"   # fallback insight, as before


def test_generator_never_uploads_to_postgres_in_test(monkeypatch, tmp_path):
    from cji.tools import synthetic_data as sd

    def no_database(*args, **kwargs):
        pytest.fail("the generator tried to reach PostgreSQL in CJI_ENV=test")

    monkeypatch.setattr(sd, "create_engine", no_database)
    with override_settings(make_test_settings(tmp_path, DATABASE_URL=DB)):
        sd.generate_demo_data(n_sessions=5, seed=1, output_path=tmp_path / "e.parquet")
    assert (tmp_path / "e.parquet").exists()


def test_collector_keepalive_is_off_unless_configured():
    from cji.collector import api

    source = (SRC / "collector" / "api.py").read_text(encoding="utf-8")
    assert "onrender" not in source
    assert load().keepalive.url is None
    assert hasattr(api, "keep_alive")


# ═════════════════════════════════════════════════════════════════════════════
# Acceptance 1: no duplicated service ports in production paths
# ═════════════════════════════════════════════════════════════════════════════

PRODUCTION_PATHS = ["main.py", "run_servers.py", "graph.py", "dashboard.py", "config.py", "state.py",
                    "agents", "collector", "mcp_servers", "tools", "guardrails", "domain",
                    "tracker/snippet_generator.py"]
# Not scanned, with the Spec that owns them: browser code that cannot read server
# settings (tracker/tracker.js, snippets/*: Specs 07/13) and legacy scripts (Spec 06).
# 800x and 8501 are distinctive; 3000 counts only in a port position (":3000", "port=3000"),
# so durations such as randint(500, 3000) are not reported.
PORT_LITERAL = re.compile(r"(?<![\w.])(800[0-9]|8501)(?![\w.])|(:|port\s*=\s*)3000(?![\w.])")
TRANSPORT_LITERAL = re.compile(r"""transport\s*=\s*["']sse""")


def _production_files():
    for entry in PRODUCTION_PATHS:
        path = SRC / entry
        yield from (sorted(path.rglob("*.py")) if path.is_dir() else [path])


def test_service_ports_and_transport_are_defined_only_in_the_registry():
    offenders = []
    for path in _production_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if PORT_LITERAL.search(code) or TRANSPORT_LITERAL.search(code):
                offenders.append(f"{path.relative_to(SRC)}:{number}: {line.strip()}")
    assert offenders == []
    registry = (SRC / "settings" / "services.py").read_text(encoding="utf-8")
    for port in ("8000", "8001", "8002", "8003", "8004", "8005", "8501", "3000"):
        assert port in registry


# ═════════════════════════════════════════════════════════════════════════════
# Isolation and the check command
# ═════════════════════════════════════════════════════════════════════════════

def test_settings_package_imports_only_stdlib_pydantic_and_dotenv():
    allowed = set(sys.stdlib_module_names) | {"pydantic", "dotenv"}
    for path in sorted((SRC / "settings").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name.split(".")[0] in allowed, f"{path.name} imports {name}"


def test_importing_settings_creates_no_files(tmp_path):
    target = tmp_path / "data"
    out = subprocess.run(
        [sys.executable, "-c", "import cji.settings, cji.settings.load, cji.settings.roles, cji.settings.services"],
        cwd=APP_ROOT, env=clean_env(CJI_ENV="test", CJI_DATA_DIR=str(target)),
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert out.returncode == 0, out.stderr[-800:]
    assert not target.exists()


def _check(*args, **env):
    return subprocess.run(
        [sys.executable, "-m", "cji.settings", "check", "--no-dotenv", *args],
        cwd=APP_ROOT, env=clean_env(**env), capture_output=True, text=True, timeout=120, check=False,
    )


def test_check_command_passes_for_offline_demo_and_redacts_secrets():
    out = _check(GROQ_API_KEY=SENTINEL)
    assert out.returncode == 0, out.stderr[-800:]
    report = json.loads(out.stdout)
    assert report["status"] == "ok" and report["settings"]["app"]["env"] == "production"
    assert SENTINEL not in out.stdout + out.stderr
    assert report["settings"]["llm"]["groq_api_key"] == f"set ({len(SENTINEL)} chars)"


def test_check_command_exits_2_for_an_unconfigured_production_collector():
    out = _check("--role", "collector", CJI_ADMIN_KEY=SENTINEL)
    assert out.returncode == 2
    assert "CJI_ADMIN_KEY" in out.stderr and "CJI_CORS_ORIGINS" in out.stderr and "DATABASE_URL" in out.stderr
    assert SENTINEL not in out.stdout + out.stderr
