"""
Spec 15 — production hardening: structured logs, traces, metrics, security audit, token rotation, readiness,
abuse controls, the production settings check, development-only behaviour, and the operations commands.
Offline: TestClient, temporary storage, no database.
"""

from __future__ import annotations

import ast
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.test_api_contract import API, JOURNEY, ApiEnv

SRC = Path(__file__).resolve().parent.parent / "src" / "cji"
REPO = Path(__file__).resolve().parents[2]


# ── logs (OD-159) ─────────────────────────────────────────────────────────────────────────────────────────


def _record(msg="hello %s", args=("world",), exc_info=None):
    return logging.LogRecord("cji.test", logging.ERROR if exc_info else logging.INFO, __file__, 1, msg, args, exc_info)


def test_json_lines_carry_context_and_drop_tracebacks_in_production(monkeypatch):
    from cji.http.request_id import reset_request_id, set_request_id
    from cji.logs import make_handler
    from cji.observability.trace import span

    monkeypatch.setenv("CJI_ENV", "production")
    handler = make_handler(kind="json")
    token = set_request_id("req-12345678")
    try:
        with span() as opened:
            try:
                raise ValueError("secret detail")
            except ValueError:
                import sys

                rec = _record(exc_info=sys.exc_info())
            for f in handler.filters:
                f.filter(rec)
            line = json.loads(handler.format(rec))
    finally:
        reset_request_id(token)
    assert line["message"] == "hello world" and line["level"] == "ERROR"
    assert line["request_id"] == "req-12345678" and line["trace_id"] == opened.trace_id
    assert line["exc_type"] == "ValueError" and "exc" not in line
    assert "secret detail" not in json.dumps(line)


def test_json_keeps_tracebacks_outside_production(monkeypatch):
    import sys

    from cji.logs import make_handler

    monkeypatch.setenv("CJI_ENV", "development")
    handler = make_handler(kind="json")
    try:
        raise KeyError("k")
    except KeyError:
        rec = _record(exc_info=sys.exc_info())
    for f in handler.filters:
        f.filter(rec)
    assert "Traceback" in json.loads(handler.format(rec))["exc"]


def test_format_defaults_follow_the_environment(monkeypatch):
    from cji.logs import log_format

    monkeypatch.delenv("CJI_LOG_FORMAT", raising=False)
    monkeypatch.setenv("CJI_ENV", "production")
    assert log_format() == "json"
    monkeypatch.setenv("CJI_ENV", "test")
    assert log_format() == "text"
    monkeypatch.setenv("CJI_LOG_FORMAT", "json")
    assert log_format() == "json"


def test_text_lines_append_ids_that_are_set():
    from cji.logs import make_handler
    from cji.observability.trace import span

    handler = make_handler(kind="text")
    with span() as opened:
        rec = _record()
        for f in handler.filters:
            f.filter(rec)
        line = handler.format(rec)
    assert line.endswith(f"[trace_id={opened.trace_id}]") and "hello world" in line


# ── traces (OD-161) ───────────────────────────────────────────────────────────────────────────────────────


def test_traceparent_parsing_rejects_malformed_and_zero_ids():
    from cji.observability.trace import format_traceparent, parse_traceparent, trace_id_for_run

    good = format_traceparent("ab" * 16, "cd" * 8)
    assert parse_traceparent(good) == ("ab" * 16, "cd" * 8)
    for bad in (None, "", "01-" + good[3:], good + "x", f"00-{'0' * 32}-{'cd' * 8}-01", "00-xyz"):
        assert parse_traceparent(bad) is None
    assert trace_id_for_run("d4310139-7cec-4457-aecf-8ed2ef09db68") == "d43101397cec4457aecf8ed2ef09db68"
    assert trace_id_for_run("not-a-uuid") is None


def test_audit_records_join_the_current_trace():
    from cji.integrations.audit import make_record
    from cji.observability.trace import span

    with span() as outer:
        tool = make_record(kind="tool", service="s", tool="t", outcome="ok")
    assert tool["trace_id"] == outer.trace_id and tool["parent_id"] == outer.span_id and tool["span_id"]
    run = make_record(kind="run", run_id="d4310139-7cec-4457-aecf-8ed2ef09db68", to_status="running")
    assert run["trace_id"] == "d43101397cec4457aecf8ed2ef09db68"


def test_requests_get_a_traceparent_and_keep_the_callers_trace(tmp_path, monkeypatch, api_env):
    incoming = f"00-{'1a' * 16}-{'2b' * 8}-01"
    r = api_env.client.get(f"{API}/health", headers={"traceparent": incoming})
    assert r.headers["traceparent"].startswith(f"00-{'1a' * 16}-") and r.headers["traceparent"] != incoming
    fresh = api_env.client.get(f"{API}/health").headers["traceparent"]
    assert re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-01", fresh)


# ── metrics (OD-160) ──────────────────────────────────────────────────────────────────────────────────────


def test_registry_renders_prometheus_text_and_bounds_labels():
    from cji.observability.metrics import Registry

    reg = Registry()
    c = reg.counter("x_total", "Things.", ("route",))
    c.inc(route="/a/{id}")
    c.inc(2, route="/a/{id}")
    c.inc(route="<script>")  # not a closed-set value
    h = reg.histogram("x_seconds", "Time.", (), buckets=(0.1, 1.0))
    h.observe(0.5)
    text = reg.render()
    assert 'x_total{route="/a/{id}"} 3' in text and 'x_total{route="invalid"} 1' in text
    assert 'x_seconds_bucket{le="0.1"} 0' in text and 'x_seconds_bucket{le="+Inf"} 1' in text
    assert "x_seconds_count 1" in text and "# TYPE x_seconds histogram" in text
    with pytest.raises(ValueError):
        c.inc(other="x")
    with pytest.raises(ValueError):
        c.inc(-1, route="/a")


def test_metrics_endpoint_is_admin_only_and_counts_requests(api_env):
    client = api_env.client
    from tests._api_harness import bearer

    client.get(f"{API}/journeys", headers=bearer(api_env.viewer))
    assert client.get(f"{API}/metrics", headers=bearer(api_env.operator)).status_code == 403
    assert client.get(f"{API}/metrics").status_code == 401
    r = client.get(f"{API}/metrics", headers=bearer(api_env.admin_all))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert 'cji_http_requests_total{service="cji-api",route="/api/v1/journeys",method="GET",status="200"}' in r.text
    assert api_env.viewer not in r.text and api_env.admin_all not in r.text


# ── readiness (OD-168) ────────────────────────────────────────────────────────────────────────────────────


def test_readiness_is_public_and_says_nothing_else(api_env):
    r = api_env.client.get(f"{API}/health/ready")
    assert r.status_code == 200 and r.json() == {"status": "ready"}


def test_readiness_fails_without_details_when_the_token_file_breaks(api_env):
    api_env.tokens_file.write_text("{not json", encoding="utf-8")
    r = api_env.client.get(f"{API}/health/ready")
    assert r.status_code == 503 and r.json() == {"status": "not_ready"}


# ── security audit and abuse controls (OD-162, OD-165) ────────────────────────────────────────────────────


def _security(api_env):
    path = api_env.audit_dir / "security.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_failed_tokens_are_audited_then_limited(api_env):
    client = api_env.client
    wrong = "cji_api_" + "x" * 43
    statuses = [
        client.get(f"{API}/journeys", headers={"Authorization": f"Bearer {wrong}"}).status_code for _ in range(4)
    ]
    assert statuses == [401, 401, 401, 429]  # CJI_API_AUTH_FAILURES_PER_MIN=3
    records = _security(api_env)
    assert [r["action"] for r in records] == ["auth.failed"] * 3 + ["auth.rate_limited"]
    assert all(wrong not in json.dumps(r) for r in records)
    assert all(
        set(r)
        <= {
            "ts",
            "kind",
            "service",
            "action",
            "actor",
            "outcome",
            "request_id",
            "trace_id",
            "span_id",
            "parent_id",
            "role",
            "target",
            "mode",
            "rows",
            "run_id",
        }
        for r in records
    )
    # a valid token is not affected by the failure bucket
    from tests._api_harness import bearer

    assert client.get(f"{API}/journeys", headers=bearer(api_env.viewer)).status_code == 200


def test_approval_audits_the_action_and_never_logs_the_comment(api_env, caplog):
    from tests._api_harness import bearer

    run_id = api_env.start_run()
    caplog.set_level(logging.INFO, logger="cji.api")
    comment = "customer said PRIVATE-NOTE-123"
    r = api_env.client.post(
        f"{API}/runs/{run_id}/approval",
        headers={**bearer(api_env.operator), "Idempotency-Key": "approve-0001"},
        json={"comment": comment},
    )
    assert r.status_code == 202
    assert "PRIVATE-NOTE-123" not in caplog.text and f"comment_chars={len(comment)}" in caplog.text
    approve = [x for x in _security(api_env) if x["action"] == "run.approve"]
    assert approve and approve[0]["target"] == run_id and "PRIVATE-NOTE" not in json.dumps(approve)


def test_security_actions_are_a_closed_set():
    from cji.integrations.audit import security_event

    with pytest.raises(ValueError):
        security_event("anything.else", actor="x", outcome="ok")
    with pytest.raises(ValueError):
        security_event("run.start", actor="x", outcome="ok", comment="free text")


def test_api_uses_its_own_proxy_hops_setting(tmp_path, monkeypatch):
    from cji.settings import make_test_settings

    s = make_test_settings(tmp_path, CJI_API_TRUSTED_PROXY_HOPS="1", CJI_COLLECTOR_TRUSTED_PROXY_HOPS="0")
    assert s.api.trusted_proxy_hops == 1 and s.collector.trusted_proxy_hops == 0
    text = (SRC / "api" / "middleware.py").read_text(encoding="utf-8")
    assert "settings.collector.trusted_proxy_hops" not in text


# ── token rotation (OD-163) ───────────────────────────────────────────────────────────────────────────────


def test_rotation_overlaps_then_the_old_token_stops(tmp_path, monkeypatch):
    from cji.api import auth

    path = tmp_path / "tokens.json"
    old = auth.create_token(path, label="svc", role="operator", journeys=[JOURNEY])
    old_id = auth.token_id_for(old)
    new_id, new = auth.rotate_token(path, old_id, overlap_hours=1)
    store = auth.TokenStore(path)
    assert store.authenticate(old) is not None and store.authenticate(new).role == "operator"
    entries = {e.id: e for e in auth.load_token_file(path).tokens}
    assert entries[new_id].label == "svc" and entries[new_id].journeys == [JOURNEY]
    later = datetime.now(UTC) + timedelta(hours=2)
    monkeypatch.setattr(auth, "_now", lambda: later)
    store = auth.TokenStore(path)
    assert store.authenticate(old) is None and store.authenticate(new) is not None
    with pytest.raises(LookupError):
        auth.rotate_token(path, old_id)


def test_rotate_cli_prints_the_value_once_and_audits(tmp_path, monkeypatch, capsys):
    from cji.api import auth, tokens_cli
    from cji.integrations import audit

    path = tmp_path / "tokens.json"
    old = auth.create_token(path, label="svc", role="viewer", journeys=[JOURNEY])
    seen = []
    monkeypatch.setattr(audit, "security_sink", lambda: type("S", (), {"write": lambda self, r: seen.append(r)})())
    assert tokens_cli.main(["--file", str(path), "rotate", auth.token_id_for(old), "--overlap-hours", "0"]) == 0
    out = capsys.readouterr().out
    assert out.count("cji_api_") == 1 and old not in out
    assert [r["action"] for r in seen] == ["token.rotate"]
    assert tokens_cli.main(["--file", str(path), "rotate", "tok_missing"]) == 1


def test_cursor_rotation_invalidates_open_cursors(tmp_path):
    from cji.api.app import build_context
    from cji.api.errors import ApiError
    from cji.settings import make_test_settings

    def codec(secret):
        settings = make_test_settings(tmp_path, CJI_MODE="demo", CJI_API_CURSOR_SECRET=secret)
        return build_context(settings, repository=object()).cursors

    filters = {"resource": "runs"}
    cursor = codec("a" * 40).encode(["2026-10-29", "r1"], filters)
    assert codec("a" * 40).decode(cursor, filters) == ["2026-10-29", "r1"]  # same key: survives a restart
    with pytest.raises(ApiError) as info:
        codec("b" * 40).decode(cursor, filters)
    assert (info.value.status, info.value.code) == (422, "invalid_cursor")


# ── production check (OD-171) and development-only behaviour (OD-172) ─────────────────────────────────────


def _production_env(tmp_path, **extra):
    from cji.api.auth import create_token

    tokens = tmp_path / "tokens.json"
    if not tokens.exists():
        create_token(tokens, label="ops", role="admin", journeys=["*"])
    env = {
        "CJI_ENV": "production",
        "CJI_MODE": "demo",
        "CJI_HOME": str(tmp_path),
        "CJI_LOG_FORMAT": "json",
        "CJI_API_CURSOR_SECRET": "k" * 40,
        "CJI_API_CORS_ORIGINS": "https://app.example.com",
        "CJI_API_TOKENS_FILE": str(tokens),
    }
    env.update(extra)
    return {k: v for k, v in env.items() if v is not None}


def _problems(tmp_path, **extra):
    from cji.settings import ConfigError, require
    from cji.settings.load import load_settings

    try:
        require(load_settings(_production_env(tmp_path, **extra), None), "production")
    except ConfigError as exc:
        return str(exc)
    return ""


def test_a_complete_production_configuration_passes(tmp_path):
    assert _problems(tmp_path) == ""


@pytest.mark.parametrize(
    "extra, expected",
    [
        ({"CJI_LOG_FORMAT": "text"}, "CJI_LOG_FORMAT must be json"),
        ({"CJI_AUDIT_DIR": "off"}, "CJI_AUDIT_DIR is off"),
        ({"CJI_LLM_RUN_MAX_COST_USD": "1.5"}, "no built-in prices"),
        ({"LANGCHAIN_TRACING_V2": "true"}, "LangSmith"),
        ({"CJI_API_TRUSTED_PROXY_HOPS": "1", "CJI_SERVICE_HOST": "0.0.0.0"}, "could forge X-Forwarded-For"),
        ({"CJI_API_CURSOR_SECRET": "short"}, "CJI_API_CURSOR_SECRET must be"),
        ({"CJI_API_CORS_ORIGINS": "http://app.example.com"}, "must use https"),
        ({"CJI_MODE": "realtime"}, "DATABASE_URL is not set"),
    ],
)
def test_each_production_rule_reports_its_violation(tmp_path, extra, expected):
    assert expected in _problems(tmp_path, **extra)


def test_production_needs_an_admin_token_and_an_explicit_mode(tmp_path):
    from cji.settings import ConfigError
    from cji.settings.load import load_settings

    (tmp_path / "tokens.json").write_text('{"tokens": []}', encoding="utf-8")
    assert "no active admin token" in _problems(tmp_path)
    env = _production_env(tmp_path)
    env.pop("CJI_MODE")
    with pytest.raises(ConfigError, match="CJI_MODE is not set"):
        load_settings(env, None)


def test_third_party_tracing_can_be_accepted_explicitly(tmp_path):
    assert "LangSmith" not in _problems(tmp_path, LANGCHAIN_TRACING_V2="true", CJI_ALLOW_THIRD_PARTY_TRACING="true")


def _inventory():
    text = (REPO / "docs" / "operations.md").read_text(encoding="utf-8")
    section = text.split("## Development-only behaviour", 1)[1].split("\n## ", 1)[0]
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"^\| `([\w/]+\.py)` \| (\d+) \|", section, re.MULTILINE)}


def _development_branches():
    found = {}
    for p in sorted(SRC.rglob("*.py")):
        n = 0
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Compare):
                for part in (node.left, *node.comparators):
                    elts = part.elts if isinstance(part, (ast.Tuple, ast.List, ast.Set)) else [part]
                    n += sum(isinstance(e, ast.Constant) and e.value == "development" for e in elts)
        if n:
            found[str(p.relative_to(SRC)).replace("\\", "/")] = n
    return found


def test_every_development_branch_is_in_the_inventory():
    assert _development_branches() == _inventory()


def test_production_settings_turn_off_development_behaviour(tmp_path):
    from cji.settings.load import load_settings

    s = load_settings(_production_env(tmp_path), None)
    assert s.app.env == "production" and s.cors.origins == () and s.api.cors_origins == ("https://app.example.com",)
    assert s.observability.log_format == "json" and s.storage.audit_dir is not None


# ── operations commands ───────────────────────────────────────────────────────────────────────────────────


def test_audit_retention_drops_only_old_lines(tmp_path):
    from cji.ops.cli import prune_audit

    now = datetime(2026, 10, 29, tzinfo=UTC)
    old = json.dumps({"ts": (now - timedelta(days=100)).isoformat(), "kind": "tool"})
    new = json.dumps({"ts": (now - timedelta(days=1)).isoformat(), "kind": "tool"})
    (tmp_path / "a.jsonl").write_text(f"{old}\n{new}\nnot json\n", encoding="utf-8")
    assert prune_audit(tmp_path, 90, dry_run=True, now=now) == {"a.jsonl": 1}
    assert prune_audit(tmp_path, 90, now=now) == {"a.jsonl": 1}
    assert (tmp_path / "a.jsonl").read_text(encoding="utf-8") == f"{new}\nnot json\n"


def test_trace_show_follows_a_request_into_its_run(tmp_path, capsys):
    from cji.ops import trace_cli

    run = "d4310139-7cec-4457-aecf-8ed2ef09db68"
    run_trace = run.replace("-", "")
    lines = [
        {
            "ts": "2026-10-29T01:00:00.000+00:00",
            "kind": "span",
            "service": "cji-api",
            "trace_id": "a" * 32,
            "span_id": "1" * 16,
            "name": "POST /api/v1/runs",
            "http_status": 202,
            "latency_ms": 40,
        },
        {
            "ts": "2026-10-29T01:00:00.010+00:00",
            "kind": "security",
            "service": "cji-api",
            "trace_id": "a" * 32,
            "action": "run.start",
            "actor": "tok_x",
            "run_id": run,
            "outcome": "ok",
        },
        {
            "ts": "2026-10-29T01:00:01.000+00:00",
            "kind": "step",
            "service": "workflow",
            "trace_id": run_trace,
            "span_id": "2" * 16,
            "worker": "data_worker",
            "attempt": 1,
            "outcome": "ok",
        },
        {
            "ts": "2026-10-29T01:00:01.100+00:00",
            "kind": "tool",
            "service": "cji-journey-data",
            "trace_id": run_trace,
            "span_id": "3" * 16,
            "parent_id": "2" * 16,
            "tool": "get_step_metrics",
            "outcome": "ok",
        },
        {"ts": "2026-10-29T01:00:02.000+00:00", "kind": "tool", "service": "other", "trace_id": "f" * 32},
    ]
    (tmp_path / "x.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    assert trace_cli.main(["show", "a" * 32, "--audit-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "4 records from 3 processes" in out and "tool get_step_metrics" in out and "other" not in out
    assert re.search(r"step data_worker attempt 1.*\n\s+.*tool get_step_metrics", out)
    assert trace_cli.main(["show", "b" * 32, "--audit-dir", str(tmp_path)]) == 1


def test_status_reports_every_service_down_when_nothing_runs(monkeypatch, capsys):
    from cji.ops import cli

    assert cli.main(["status", "--only", "api", "cji-insight", "--timeout", "0.5"]) == 1
    out = capsys.readouterr().out
    assert "api" in out and "down" in out and "cji-insight" in out


# ── fixtures ──────────────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    from cji.integrations.audit import reset_security_sink
    from cji.settings import override_settings

    audit_dir = tmp_path / "audit"
    reset_security_sink()
    env = ApiEnv(tmp_path, monkeypatch, CJI_AUDIT_DIR=str(audit_dir), CJI_API_AUTH_FAILURES_PER_MIN="3")
    env.audit_dir = audit_dir
    with override_settings(env.settings), env:
        yield env
    reset_security_sink()


# ── failure messages reach the API: no server paths (F-94; found by the recovery suite) ─────────────
def test_report_write_errors_name_no_server_path(tmp_path):
    from cji.reporting.output import ReportWriteError, write_report

    blocker = tmp_path / "reports"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ReportWriteError) as info:
        write_report("<p>report</p>", blocker, "cji_report_x.html")
    message = str(info.value)
    assert message.startswith("reports directory is not usable: ")
    assert str(tmp_path) not in message and "\\" not in message and "/" not in message


# ── every line of a service is a log record (found by the gate's live phase) ──────────────────────────────
def test_settings_warnings_before_logging_starts_are_emitted_later(monkeypatch, caplog):
    from cji import logs
    from cji.settings import load as settings_load

    monkeypatch.setattr(logging.root, "handlers", [])
    monkeypatch.setattr(settings_load, "PENDING_WARNINGS", [])
    settings_load._warn("held warning")
    settings_load._warn("held warning")  # once only
    assert settings_load.PENDING_WARNINGS == ["held warning"]
    monkeypatch.setattr(logs, "make_handler", lambda *a, **k: caplog.handler)
    with caplog.at_level(logging.WARNING, logger="cji.settings"):
        logs.configure_logging()
    assert [r.getMessage() for r in caplog.records if r.name == "cji.settings"] == ["held warning"]
    assert settings_load.PENDING_WARNINGS == []


def test_mcp_tool_calls_run_with_the_workflow_run_id(caplog):
    import asyncio
    import uuid
    from types import SimpleNamespace

    from cji.mcp_servers._serve import run_context_middleware
    from cji.observability.context import current_run_id

    run_id = str(uuid.uuid4())
    seen: list[str | None] = []

    async def call_next(_context):
        seen.append(current_run_id())
        return "result"

    middleware = run_context_middleware()
    message = SimpleNamespace(name="generate_insight", arguments={"run_context": {"correlation_id": run_id}})
    with caplog.at_level(logging.INFO, logger="cji.mcp"):
        assert asyncio.run(middleware.on_call_tool(SimpleNamespace(message=message), call_next)) == "result"
        plain = SimpleNamespace(name="get_funnel_metrics", arguments={"journey_id": "j"})
        asyncio.run(middleware.on_call_tool(SimpleNamespace(message=plain), call_next))
    assert seen == [run_id, None]
    assert [r.getMessage() for r in caplog.records if r.name == "cji.mcp"] == [
        "tool generate_insight called",
        "tool get_funnel_metrics called",
    ]
