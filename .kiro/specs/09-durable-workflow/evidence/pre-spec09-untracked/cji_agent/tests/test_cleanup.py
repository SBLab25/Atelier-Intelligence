"""
Spec 06: dead code, exception handling and entry-point policy.

These tests read source files (AST) and call small seams directly. No network,
no database other than in-memory SQLite.
"""

from __future__ import annotations

import ast
import io
import re
import subprocess
from pathlib import Path

import pandas as pd
import pytest
import sqlalchemy
from sqlalchemy.pool import StaticPool

APP_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = APP_ROOT.parent
EXCLUDED_DIRS = {"tests", "snippets", ".venv", "venv", "__pycache__"}   # snippets/: F-14


def _app_modules() -> list[Path]:
    return sorted(
        p for p in APP_ROOT.rglob("*.py")
        if not EXCLUDED_DIRS.intersection(p.relative_to(APP_ROOT).parts)
    )


def _rel(path: Path) -> str:
    return path.relative_to(APP_ROOT).as_posix()


# ── Removed symbols and files (CL-01, CL-02, CL-10, CL-12) ───────────────────

REMOVED_FILES = [
    "check_parquet.py", "inspect_schemas.py", "query_test.py", "test_data_server.py",
    "test_duckdb_async.py", "test_load.py", "test_server.py", "test_threads.py",
    "err.log", "error.log", "out.log", "stderr.log", "main_log.txt", "main_log2.txt",
    "main_log3.txt", "main_log4.txt", "main_log5.txt", "ingest_ga4_log.txt",
    "parquet_check.txt", "schema_report.txt",
    "cji_agent/fix.py", "cji_agent/test_duckdb.py", "cji_agent/test_metadata_query.py",
    "cji_agent/test_pg.py", "cji_agent/test_servers.py", "cji_agent/verify_data.py",
    "cji_agent/dashboard2.py",
]

# (description, git grep -E pattern). Planning inputs and Spec records describe
# the removal itself and are excluded.
REMOVED_REFERENCES = [
    ("MCP tool test_dummy", r"\btest_dummy\b"),
    ("ingest_json() wrapper", r"\bingest_json\("),
    ("dashboard2.py", r"\bdashboard2\b"),
    ("fix.py", r"(^|[^_\w])fix\.py\b"),
    ("test_metadata_query.py", r"\btest_metadata_query\b"),
    ("check_parquet.py", r"\bcheck_parquet\b"),
    ("inspect_schemas.py", r"\binspect_schemas\b"),
    ("query_test.py", r"\bquery_test\b"),
    ("test_data_server.py", r"\btest_data_server\b"),
    ("test_duckdb_async.py", r"\btest_duckdb_async\b"),
    ("test_load.py", r"\btest_load\.py\b"),
    ("test_server.py", r"\btest_server\.py\b"),
    ("test_threads.py", r"\btest_threads\b"),
    ("test_duckdb.py", r"\btest_duckdb\.py\b"),
    ("test_pg.py", r"\btest_pg\b"),
    ("test_servers.py", r"\btest_servers\.py\b"),
    ("verify_data.py", r"\bverify_data\b"),
    ("run logs", r"\b(main_log[0-9]*\.txt|ingest_ga4_log\.txt|parquet_check\.txt|schema_report\.txt)\b"),
]
GREP_EXCLUDES = [
    ":!.kiro", ":!graphify-out", ":!refactoring.md", ":!kiro_upgrade_guide.md",
    ":!kiro_upgrade_prompts.md", ":!antigravity_upgrade_prompts.md", ":!.gitignore",
    ":!cji_agent/tests/test_cleanup.py",
]


@pytest.mark.parametrize("rel", REMOVED_FILES)
def test_removed_file_is_gone(rel):
    assert not (REPO_ROOT / rel).exists(), f"{rel} should have been removed (Spec 06, OD-34)"


@pytest.mark.parametrize("label,pattern", REMOVED_REFERENCES, ids=[r[0] for r in REMOVED_REFERENCES])
def test_removed_symbol_has_no_references(label, pattern):
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "grep", "-n", "-I", "-E", "--untracked", pattern, "--", ".", *GREP_EXCLUDES],
        capture_output=True, text=True, check=False,
    )
    assert out.returncode in (0, 1), out.stderr
    assert out.stdout == "", f"{label} is still referenced:\n{out.stdout[:2000]}"


def _tool_names(module_path: Path) -> list[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    return [
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any("tool" in ast.unparse(d) for d in node.decorator_list)
    ]


def test_journey_data_server_exposes_only_production_tools():
    tools = _tool_names(APP_ROOT / "mcp_servers" / "journey_data_server.py")
    assert tools == [
        "get_system_info", "get_funnel_steps", "get_step_metrics",
        "get_funnel_dropoff", "query_events", "get_live_snapshot",
    ]


def test_ingest_json_compatibility_wrapper_is_gone():
    from tools import ingest_json as ij

    assert not hasattr(ij, "ingest_json")
    assert callable(ij.ingest_file)          # the used entry point stays


# ── Exception-handling policy (CL-04, CL-05) ─────────────────────────────────

def _is_broad(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id in {"Exception", "BaseException"} for n in names)


def _is_silent(handler: ast.ExceptHandler) -> bool:
    return all(
        isinstance(s, (ast.Pass, ast.Continue))
        or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        for s in handler.body
    )


def _handlers():
    for path in _app_modules():
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ExceptHandler):
                yield _rel(path), node, lines[node.lineno - 1]


def test_no_silent_exception_handlers():
    silent = [f"{rel}:{h.lineno}" for rel, h, _ in _handlers() if _is_silent(h)]
    assert silent == [], f"handlers that swallow errors: {silent}"


def test_every_broad_handler_states_why():
    undocumented = [
        f"{rel}:{h.lineno}: {line.strip()}"
        for rel, h, line in _handlers()
        if _is_broad(h) and not re.search(r"# broad-except: \S", line)
    ]
    assert undocumented == [], "broad handlers need '# broad-except: <reason>':\n" + "\n".join(undocumented)


# ── sys.path policy (CL-11) ──────────────────────────────────────────────────

ALLOWED_SYS_PATH = {
    "mcp_servers/friction_engine_server.py",
    "mcp_servers/insight_server.py",
    "tools/ingest_json.py",
    "tools/synthetic_data.py",
    "tracker/snippet_generator.py",
}


def _sys_path_lines(path: Path) -> list[int]:
    return [
        i for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"sys\.path\.(insert|append)\(", line)
    ]


def test_sys_path_workarounds_only_in_script_entry_points():
    found = {_rel(p) for p in _app_modules() if _sys_path_lines(p)}
    assert found == ALLOWED_SYS_PATH


def test_tests_rely_on_conftest_for_sys_path():
    found = {p.name for p in (APP_ROOT / "tests").glob("*.py") if _sys_path_lines(p)}
    assert found == {"conftest.py"}


@pytest.mark.parametrize("rel", sorted(ALLOWED_SYS_PATH | {"tests/conftest.py"}))
def test_remaining_sys_path_workarounds_point_at_packaging(rel):
    path = APP_ROOT / rel
    lines = path.read_text(encoding="utf-8").splitlines()
    for n in _sys_path_lines(path):
        context = "\n".join(lines[max(0, n - 3):n])
        assert "Spec 11" in context, f"{rel}:{n} needs a 'Spec 11 (R-14)' comment"


# ── CLI console (CL-07) ──────────────────────────────────────────────────────

def test_cli_console_replaces_unencodable_characters():
    import main

    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    main._configure_console(stream)
    print("report -> \u2192 \u2713 done", file=stream)
    stream.flush()
    assert b"done" in raw.getvalue()


# ── tools/ingest_json (OD-35, CL-10) ─────────────────────────────────────────

def _sqlite_engine():
    return sqlalchemy.create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})


def _events(*ids: str) -> pd.DataFrame:
    return pd.DataFrame({"event_id": list(ids), "user_id": ["u"] * len(ids), "step_id": ["s"] * len(ids)})


def test_existing_ids_treat_only_a_missing_table_as_empty():
    from tools import ingest_json as ij

    engine = _sqlite_engine()
    assert ij._existing_event_ids(engine) == set()
    _events("a", "b").to_sql("tracking_events", engine, index=False)
    assert ij._existing_event_ids(engine) == {"a", "b"}

    broken = _sqlite_engine()
    pd.DataFrame({"other": [1]}).to_sql("tracking_events", broken, index=False)
    with pytest.raises(sqlalchemy.exc.OperationalError):
        ij._existing_event_ids(broken)


def test_append_is_the_default_and_skips_known_events():
    from tools import ingest_json as ij

    engine = _sqlite_engine()
    _events("a", "b").to_sql("tracking_events", engine, index=False)
    written = ij._write_tracking_events(_events("b", "c"), engine)
    assert written == 1
    assert sorted(pd.read_sql("SELECT event_id FROM tracking_events", engine)["event_id"]) == ["a", "b", "c"]


def test_replace_happens_only_when_requested():
    from tools import ingest_json as ij

    engine = _sqlite_engine()
    _events("a", "b").to_sql("tracking_events", engine, index=False)
    written = ij._write_tracking_events(_events("c"), engine, replace=True)
    assert written == 1
    assert list(pd.read_sql("SELECT event_id FROM tracking_events", engine)["event_id"]) == ["c"]


def test_ingest_file_refuses_append_and_replace_together(tmp_path):
    from tools import ingest_json as ij

    with pytest.raises(ValueError, match="append.*replace|replace.*append"):
        ij.ingest_file(tmp_path / "x.json", append=True, replace=True)


def test_invalid_json_array_names_the_file(tmp_path):
    from tools import ingest_json as ij

    bad = tmp_path / "bad.json"
    bad.write_text("[{\"user_id\": 1,", encoding="utf-8")
    with pytest.raises(ValueError, match="bad.json"):
        list(ij._detect_and_yield(bad, {}, None))


def test_ingest_cli_defaults_to_append():
    source = (APP_ROOT / "tools" / "ingest_json.py").read_text(encoding="utf-8")
    assert '"--replace"' in source and '"--append"' in source
    assert "PostgreSQL tracking_events" in source


# ── Collector error responses (CL-09) ────────────────────────────────────────

class _FailingEngine:
    def __init__(self, exc):
        self.exc = exc

    def begin(self):
        raise self.exc

    connect = begin

    def dispose(self):
        return None


def _admin_client(monkeypatch, engine):
    from fastapi.testclient import TestClient

    from collector import api

    key = "spec06-admin-key-" + "x" * 32
    monkeypatch.setattr(api, "engine", engine)
    monkeypatch.setattr(api, "CJI_ADMIN_KEY", key)
    return TestClient(api.app), {"X-CJI-Admin-Key": key}


def test_admin_key_database_error_hides_driver_text(monkeypatch):
    err = sqlalchemy.exc.OperationalError("INSERT", {}, Exception("password=hunter2 host=db.internal"))
    client, headers = _admin_client(monkeypatch, _FailingEngine(err))
    res = client.post("/admin/api-keys", json={"journey_name": "j", "description": "d"}, headers=headers)
    assert res.status_code == 500
    assert res.json() == {"detail": "Database error"}
    assert "hunter2" not in res.text


def test_admin_key_without_database_is_503(monkeypatch):
    from collector import api

    client, headers = _admin_client(monkeypatch, api.UnconfiguredDatabase())
    res = client.post("/admin/api-keys", json={"journey_name": "j", "description": "d"}, headers=headers)
    assert res.status_code == 503
    assert res.json() == {"detail": "Database not configured"}


def test_keepalive_ping_catches_only_http_errors(monkeypatch):
    import requests

    from collector import api

    def refuse(*_a, **_k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(api.requests, "get", refuse)
    api._ping_keepalive("http://127.0.0.1:9/health")      # logged, not raised

    def bug(*_a, **_k):
        raise ValueError("bug")

    monkeypatch.setattr(api.requests, "get", bug)
    with pytest.raises(ValueError):
        api._ping_keepalive("http://127.0.0.1:9/health")


# ── Requirements (OD-40) ─────────────────────────────────────────────────────

def test_requirements_declare_the_gateway_http_client():
    # Spec 08 (OD-56): retries live in integrations/; tenacity and guardrails/rate_limiter.py are gone.
    reqs = (APP_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert re.search(r"^httpx\b", reqs, re.MULTILINE), "integrations/llm.py imports httpx"
    assert not re.search(r"^tenacity\b", reqs, re.MULTILINE)
    assert not (APP_ROOT / "guardrails" / "rate_limiter.py").exists()
