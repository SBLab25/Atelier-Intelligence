"""
Spec 08 — AI gateway (design §7): provider selection, request/response types, timeouts, retries,
cancellation, rate limits, budgets, malformed responses, guardrails, secrets, audit, friction engine.

Every provider call is scripted (integrations.testing.ScriptedTransport); conftest.py installs a
transport that fails any unscripted call. Waits use a manual clock, never real time.
"""
import asyncio
import contextlib
import inspect
import json
import logging
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from cji.integrations import (
    BudgetExceeded,
    LLMDisabled,
    LLMGateway,
    LLMRequest,
    LLMTimeout,
    MalformedResponse,
    MalformedToolResult,
    ProviderRejected,
    ProviderUnavailable,
    RateLimited,
    RunBudget,
    RunContext,
    ToolFailed,
    ToolGateway,
    ToolTimeout,
)
from cji.integrations import tools as tools_module
from cji.integrations.audit import JsonlSink, LogSink, default_sink, scrub
from cji.integrations.policy import RetryPolicy, Timing
from cji.integrations.testing import (
    FakeToolSession,
    ManualClock,
    MemoryAuditSink,
    ScriptedTransport,
    anthropic_response,
    groq_response,
    status_response,
    tool_result,
)
from cji.settings import (
    ConfigError,
    load_settings,
    make_test_settings,
    override_settings,
)

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src" / "cji"                       # the package sources (Spec 11)
KEY = "sk-SENTINEL-KEY-0001"
CTX = RunContext(correlation_id="run-0001", worker="test_worker")
REQ = LLMRequest(purpose="insight", system="You are CJI. Reply in JSON.", user="Step: SECRETPROMPT",
                 response_format="json")
TEXT_REQ = LLMRequest(purpose="narrative", system="sys", user="usr", response_format="text")


def run(value):
    return asyncio.run(value) if inspect.isawaitable(value) else value


def load(env=None):
    env = {"CJI_ENV": "test", **(env or {})}
    if env["CJI_ENV"] == "production":
        env.setdefault("CJI_MODE", "demo")          # Spec 15: a declared production host names its mode
    return load_settings(env, dotenv_path=None)


def gateway(*items, provider="groq", model=None, clock=None, audit=None, api_key=KEY, **kw):
    transport = ScriptedTransport(*items)
    clock = clock or ManualClock()
    audit = audit if audit is not None else MemoryAuditSink()
    gw = LLMGateway(
        provider=provider, model=model or ("claude-test" if provider == "anthropic" else "test-model"),
        api_key=api_key, service="test", audit=audit, transport=transport, timing=clock.timing(),
        retry=kw.pop("retry", RetryPolicy(3, 2.0, 10.0)), **kw,
    )
    return gw, transport, clock, audit


# ═════════════════════════════════════════════════════════════════════════════
# Provider selection (OD-54)
# ═════════════════════════════════════════════════════════════════════════════

def test_settings_select_one_provider_and_its_default_model():
    s = load()
    assert (s.llm.provider, s.llm.model) == ("groq", "openai/gpt-oss-120b")
    s = load({"CJI_LLM_PROVIDER": "anthropic"})
    assert (s.llm.provider, s.llm.model) == ("anthropic", "claude-sonnet-4-6")
    assert load({"CJI_LLM_PROVIDER": "none"}).llm.provider == "none"
    assert load({"LLM_MODEL": "llama-3.3-70b-versatile"}).llm.model == "llama-3.3-70b-versatile"


@pytest.mark.parametrize("env", [
    {"CJI_LLM_PROVIDER": "groq", "LLM_MODEL": "claude-sonnet-4-6"},
    {"LLM_MODEL": "anthropic/claude-x"},
    {"CJI_LLM_PROVIDER": "anthropic", "LLM_MODEL": "llama3-70b-8192"},
    {"CJI_LLM_PROVIDER": "openai"},
])
def test_mismatched_or_unknown_provider_is_refused(env):
    with pytest.raises(ConfigError, match="CJI_LLM_PROVIDER"):
        load(env)


def test_cost_cap_needs_prices():
    with pytest.raises(ConfigError, match="CJI_LLM_PRICE_INPUT_PER_MTOK"):
        load({"CJI_LLM_RUN_MAX_COST_USD": "1.5"})
    s = load({"CJI_LLM_RUN_MAX_COST_USD": "1.5", "CJI_LLM_PRICE_INPUT_PER_MTOK": "0.15",
              "CJI_LLM_PRICE_OUTPUT_PER_MTOK": "0.6"})
    assert s.llm.run_budget.max_cost_usd == 1.5 and s.llm.price_output_per_mtok == 0.6


def test_new_settings_have_documented_defaults():
    s = load()
    assert (s.llm.deadline_s, s.llm.rate_per_min, s.mcp.call_timeout_s) == (90.0, 30, 150.0)
    assert (s.llm.run_budget.max_calls, s.llm.run_budget.max_tokens, s.llm.run_budget.max_cost_usd) == (20, 50_000, None)
    assert s.storage.audit_dir is None                                  # tests: log sink only
    assert load({"CJI_ENV": "production"}).storage.audit_dir.name == "audit"
    assert load({"CJI_ENV": "production", "CJI_AUDIT_DIR": "off"}).storage.audit_dir is None
    described = s.describe()["llm"]
    assert described["provider"] == "groq" and described["run_budget"]["max_calls"] == 20


def test_a_failed_call_never_tries_another_provider():
    gw, transport, _, _ = gateway(status_response(503), status_response(503), status_response(503))
    with pytest.raises(ProviderUnavailable):
        run(gw.complete(REQ, CTX))
    assert {httpx.URL(u).host for u in transport.urls()} == {"api.groq.com"}
    assert len(transport.requests) == 3


@pytest.mark.parametrize("configured, sent", [
    ("llama3-70b-8192", "llama3-70b-8192"),          # no allow-list substitution any more
    ("groq/openai/gpt-oss-20b", "openai/gpt-oss-20b"),
])
def test_model_is_sent_as_configured(configured, sent):
    gw, transport, _, _ = gateway(groq_response('{"a": 1}'), model=configured)
    run(gw.complete(REQ, CTX))
    assert transport.bodies()[0]["model"] == sent


def test_gateway_from_settings_uses_the_configured_provider(tmp_path):
    transport = ScriptedTransport(anthropic_response('{"ok": true}'))
    with override_settings(make_test_settings(tmp_path, CJI_LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY=KEY,
                                              GROQ_API_KEY="other-key-0002")):
        gw = LLMGateway.from_settings("test", transport=transport, audit=MemoryAuditSink(),
                                      timing=ManualClock().timing())
        result = run(gw.complete(REQ, CTX))
    assert gw.provider == "anthropic" and result.data == {"ok": True}
    assert transport.requests[0].url.host == "api.anthropic.com"
    assert transport.requests[0].headers["x-api-key"] == KEY


def test_provider_none_and_missing_key_send_nothing():
    gw, transport, _, audit = gateway(provider="none")
    with pytest.raises(LLMDisabled):
        run(gw.complete(REQ, CTX))
    gw2, transport2, _, _ = gateway(api_key=None)
    with pytest.raises(ProviderRejected) as exc:
        run(gw2.complete(REQ, CTX))
    assert exc.value.code == "not_configured"
    assert transport.requests == [] and transport2.requests == []
    assert audit.records[0]["code"] == "llm_disabled"


# ═════════════════════════════════════════════════════════════════════════════
# Request and response types (OD-55 / OD-60)
# ═════════════════════════════════════════════════════════════════════════════

def test_groq_request_and_response():
    gw, transport, _, _ = gateway(groq_response('{"title": "t"}', prompt_tokens=120, completion_tokens=30),
                                  max_tokens=512, temperature=0.0)
    result = run(gw.complete(REQ, CTX))
    body = transport.bodies()[0]
    assert body["messages"] == [{"role": "system", "content": REQ.system}, {"role": "user", "content": REQ.user}]
    assert body["max_tokens"] == 512 and body["temperature"] == 0.0
    assert body["response_format"] == {"type": "json_object"}
    assert transport.requests[0].headers["authorization"] == f"Bearer {KEY}"
    assert result.data == {"title": "t"}
    info = result.info
    assert (info.outcome, info.attempts, info.input_tokens, info.output_tokens) == ("ok", 1, 120, 30)
    assert (info.provider, info.model) == ("groq", "test-model")


def test_anthropic_request_and_fenced_json():
    gw, transport, _, _ = gateway(anthropic_response('```json\n{"a": 1}\n```', input_tokens=7, output_tokens=3),
                                  provider="anthropic")
    result = run(gw.complete(REQ, CTX))
    body = transport.bodies()[0]
    assert body["system"] == REQ.system and body["messages"] == [{"role": "user", "content": REQ.user}]
    assert "response_format" not in body
    assert transport.requests[0].headers["anthropic-version"] == "2023-06-01"
    assert result.data == {"a": 1} and (result.info.input_tokens, result.info.output_tokens) == (7, 3)


def test_text_mode_returns_text_without_parsing():
    gw, _, _, _ = gateway(groq_response("Three paragraphs."))
    result = run(gw.complete(TEXT_REQ, CTX))
    assert (result.text, result.data) == ("Three paragraphs.", None)


# ═════════════════════════════════════════════════════════════════════════════
# Timeouts and deadline (OD-56)
# ═════════════════════════════════════════════════════════════════════════════

def test_attempt_timeout_is_retried():
    gw, transport, clock, _ = gateway(httpx.ReadTimeout("slow"), groq_response('{"a": 1}'))
    result = run(gw.complete(REQ, CTX))
    assert result.info.attempts == 2 and clock.sleeps == [2.0] and len(transport.requests) == 2


def test_attempt_timeout_is_bounded_by_the_deadline():
    seen = []

    def capture(request):
        seen.append(request.extensions["timeout"]["read"])
        return groq_response('{"a": 1}')

    gw, _, _, _ = gateway(capture, timeout_s=30.0, deadline_s=12.0)
    run(gw.complete(REQ, CTX))
    assert seen == [12.0]


def test_deadline_stops_further_attempts():
    gw, transport, clock, _ = gateway(status_response(503), status_response(503), status_response(503),
                                      deadline_s=3.0)
    with pytest.raises(ProviderUnavailable):
        run(gw.complete(REQ, CTX))
    assert len(transport.requests) == 2 and clock.sleeps == [2.0]


def test_every_attempt_timing_out_raises_timeout():
    gw, transport, clock, _ = gateway(httpx.ConnectTimeout("a"), httpx.ReadTimeout("b"), httpx.WriteTimeout("c"))
    with pytest.raises(LLMTimeout):
        run(gw.complete(REQ, CTX))
    assert len(transport.requests) == 3 and clock.sleeps == [2.0, 4.0]


# ═════════════════════════════════════════════════════════════════════════════
# Retries and classification (OD-56)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("status", [429, 500, 502, 503, 504, 529])
def test_retryable_statuses_are_retried_up_to_the_attempt_limit(status):
    gw, transport, clock, _ = gateway(*[status_response(status) for _ in range(3)])
    with pytest.raises((ProviderUnavailable, RateLimited)) as exc:
        run(gw.complete(REQ, CTX))
    assert exc.value.retryable is True
    assert len(transport.requests) == 3 and clock.sleeps == [2.0, 4.0]


@pytest.mark.parametrize("status, body, code", [
    (400, None, "bad_request"),
    (400, {"error": {"code": "model_decommissioned", "type": "invalid_request_error"}}, "model_not_found"),
    (401, None, "auth_failed"),
    (403, None, "auth_failed"),
    (404, None, "model_not_found"),
    (413, None, "bad_request"),
    (422, None, "bad_request"),
])
def test_client_errors_are_not_retried(status, body, code):
    gw, transport, clock, _ = gateway(status_response(status, body))
    with pytest.raises(ProviderRejected) as exc:
        run(gw.complete(REQ, CTX))
    assert (exc.value.code, exc.value.retryable, exc.value.status) == (code, False, status)
    assert len(transport.requests) == 1 and clock.sleeps == []


def test_retry_after_is_honoured():
    gw, _, clock, _ = gateway(status_response(429, headers={"retry-after": "7"}), groq_response('{"a": 1}'))
    run(gw.complete(REQ, CTX))
    assert clock.sleeps == [7.0]


def test_backoff_is_exponential_and_capped():
    gw, transport, clock, _ = gateway(*[httpx.ConnectError("down") for _ in range(5)],
                                      retry=RetryPolicy(5, 2.0, 5.0), deadline_s=1000)
    with pytest.raises(ProviderUnavailable):
        run(gw.complete(REQ, CTX))
    assert clock.sleeps == [2.0, 4.0, 5.0, 5.0] and len(transport.requests) == 5


# ═════════════════════════════════════════════════════════════════════════════
# Cancellation (OD-57)
# ═════════════════════════════════════════════════════════════════════════════

def test_cancellation_during_the_request_stops_the_call():
    async def scenario():
        started = asyncio.Event()

        async def hang(request):
            started.set()
            await asyncio.Event().wait()

        gw, transport, _, audit = gateway(hang, groq_response('{"never": 1}'))
        task = asyncio.create_task(gw.complete(REQ, CTX))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return transport, audit

    transport, audit = run(scenario())
    assert len(transport.requests) == 1
    assert audit.records[-1]["outcome"] == "cancelled"


def test_cancellation_during_backoff_sends_no_further_request():
    async def scenario():
        sleeping = asyncio.Event()

        async def hang_sleep(seconds):
            sleeping.set()
            await asyncio.Event().wait()

        clock = ManualClock()
        transport = ScriptedTransport(status_response(503), groq_response('{"never": 1}'))
        audit = MemoryAuditSink()
        gw = LLMGateway(provider="groq", model="m", api_key=KEY, service="test", audit=audit,
                        transport=transport, timing=Timing(now=clock.now, sleep=hang_sleep))
        task = asyncio.create_task(gw.complete(REQ, CTX))
        await sleeping.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return transport, audit

    transport, audit = run(scenario())
    assert len(transport.requests) == 1 and audit.records[-1]["outcome"] == "cancelled"


def test_cancelling_a_tool_call_closes_the_session():
    closed = []

    async def scenario():
        started = asyncio.Event()

        async def hang(args):
            started.set()
            await asyncio.Event().wait()

        @contextlib.asynccontextmanager
        async def opener(service):
            try:
                yield FakeToolSession({"generate_insight": hang})
            finally:
                closed.append(service)

        audit = MemoryAuditSink()
        gw = ToolGateway(opener=opener, audit=audit)

        async def worker():
            async with gw.session("cji-insight") as session:
                await gw.call(session, "generate_insight", {"friction_score": {}})

        task = asyncio.create_task(worker())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return audit

    audit = run(scenario())
    assert closed == ["cji-insight"]
    assert audit.of_kind("tool")[-1]["outcome"] == "cancelled"


# ═════════════════════════════════════════════════════════════════════════════
# Rate limit (OD-58)
# ═════════════════════════════════════════════════════════════════════════════

def test_rate_limit_waits_when_the_wait_fits_the_deadline():
    gw, transport, clock, _ = gateway(groq_response('{"a": 1}'), groq_response('{"b": 2}'), rate_per_min=1)
    run(gw.complete(REQ, CTX))
    run(gw.complete(REQ, CTX))
    assert clock.sleeps == [60.0] and len(transport.requests) == 2


def test_rate_limit_refuses_when_the_wait_exceeds_the_deadline():
    gw, transport, _, _ = gateway(groq_response('{"a": 1}'), rate_per_min=1, deadline_s=30.0)
    run(gw.complete(REQ, CTX))
    with pytest.raises(RateLimited):
        run(gw.complete(REQ, CTX))
    assert len(transport.requests) == 1


# ═════════════════════════════════════════════════════════════════════════════
# Budgets (OD-59)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("budget", [
    RunBudget(calls_left=0, tokens_left=100_000),
    RunBudget(calls_left=5, tokens_left=100),                       # max_tokens 2048 does not fit
    RunBudget(calls_left=5, tokens_left=100_000, cost_left_usd=0.000001),
])
def test_exhausted_budget_sends_nothing(budget):
    gw, transport, _, audit = gateway(price_input_per_mtok=1.0, price_output_per_mtok=2.0)
    with pytest.raises(BudgetExceeded):
        run(gw.complete(REQ, CTX.model_copy(update={"budget": budget})))
    assert transport.requests == []
    assert audit.records[-1]["code"] == "budget_exceeded"


def test_cost_is_computed_only_from_configured_prices():
    gw, _, _, _ = gateway(groq_response('{"a": 1}', prompt_tokens=10, completion_tokens=5),
                          price_input_per_mtok=1.0, price_output_per_mtok=2.0)
    assert run(gw.complete(REQ, CTX)).info.cost_usd == 0.00002
    gw2, _, _, _ = gateway(groq_response('{"a": 1}'))
    assert run(gw2.complete(REQ, CTX)).info.cost_usd is None


def test_generate_insight_falls_back_when_the_budget_is_exhausted(monkeypatch):
    from cji.mcp_servers import insight_server

    gw, transport, _, _ = gateway()
    monkeypatch.setattr(insight_server, "_llm", gw)
    out = run(insight_server.generate_insight(
        {"step_id": "sign_up_form", "signals": ["high_abandon"]},
        run_context={"correlation_id": "run-0002", "budget": {"calls_left": 0, "tokens_left": 0}},
    ))
    assert transport.requests == []
    assert out["llm"]["code"] == "budget_exceeded" and out["llm"]["outcome"] == "fallback"
    assert out["insight"]["root_cause"] == "LLM analysis unavailable. Manual investigation required."


# ═════════════════════════════════════════════════════════════════════════════
# Malformed responses
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("response", [
    httpx.Response(200, text="<html>gateway error</html>"),
    httpx.Response(200, json=[1, 2]),
    httpx.Response(200, json={"choices": []}),
    httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
    groq_response("this is not json"),
    groq_response("[1, 2, 3]"),
])
def test_malformed_llm_responses_are_not_retried(response):
    gw, transport, _, audit = gateway(response, groq_response('{"never": 1}'))
    with pytest.raises(MalformedResponse):
        run(gw.complete(REQ, CTX))
    assert len(transport.requests) == 1 and audit.records[-1]["code"] == "malformed_response"


@pytest.mark.parametrize("result, error, code", [
    (tool_result("plain text"), MalformedToolResult, "malformed_tool_result"),
    (tool_result([1, 2]), MalformedToolResult, "malformed_tool_result"),
    (tool_result("Error executing tool generate_insight", is_error=True), ToolFailed, "tool_error"),
])
def test_malformed_tool_results_raise(result, error, code):
    session = FakeToolSession({"t": lambda args: result})
    gw = ToolGateway(audit=MemoryAuditSink())
    with pytest.raises(error) as exc:
        run(gw.call(session, "t", {}))
    assert exc.value.code == code


def test_tool_exceptions_become_tool_failed_without_their_text():
    def boom(args):
        raise ValueError(f"token {KEY}")

    gw = ToolGateway(audit=MemoryAuditSink(), secrets=(KEY,))
    with pytest.raises(ToolFailed) as exc:
        run(gw.call(FakeToolSession({"t": boom}), "t", {}))
    assert KEY not in str(exc.value) and "ValueError" in str(exc.value)
    assert isinstance(exc.value, RuntimeError)            # old MCP client contract


def test_tool_call_timeout():
    async def slow(args):
        await asyncio.sleep(5)

    gw = ToolGateway(call_timeout_s=0.05, audit=MemoryAuditSink())
    with pytest.raises(ToolTimeout):
        run(gw.call(FakeToolSession({"t": slow}), "t", {}))


def test_session_open_is_retried_once():
    attempts = []

    def opener_factory(failures):
        @contextlib.asynccontextmanager
        async def opener(service):
            attempts.append(service)
            if len(attempts) <= failures:
                raise ConnectionError("refused")
            yield FakeToolSession({})
        return opener

    async def open_with(failures):
        gw = ToolGateway(opener=opener_factory(failures), audit=MemoryAuditSink())
        async with gw.session("cji-report"):
            return True

    assert run(open_with(1)) is True and len(attempts) == 2
    attempts.clear()
    with pytest.raises(ToolFailed) as exc:
        run(open_with(2))
    assert exc.value.code == "connect_failed" and len(attempts) == 2


def test_mcp_client_wrappers_use_the_gateway():
    from cji.tools import mcp_client

    audit = MemoryAuditSink()
    tools_module.reset_tool_gateway(ToolGateway(audit=audit))
    session = FakeToolSession({"get_system_info": lambda args: {"mode": "demo"}})
    assert run(mcp_client.call_tool(session, "get_system_info")) == {"mode": "demo"}
    assert audit.of_kind("tool")[0]["tool"] == "get_system_info"


# ═════════════════════════════════════════════════════════════════════════════
# Guardrails preserved (OD-63)
# ═════════════════════════════════════════════════════════════════════════════

FRICTION = {
    "step_id": "sign_up_form", "score": 82, "signals": ["high_abandon"], "abandon_rate_pct": 40.0,
    "user_id": "user-SECRETUSER", "session_id": "sess-SECRETSESS", "email": "someone@example.test",
}


def test_generate_insight_sanitises_input_and_validates_output(monkeypatch):
    from cji.mcp_servers import insight_server

    llm_json = json.dumps({"title": "Form too long", "root_cause": "Many fields.", "category": "bogus",
                           "evidence": "not a list", "suggested_fix": "Cut fields.", "fix_effort": "tiny"})
    gw, transport, _, _ = gateway(groq_response(llm_json))
    monkeypatch.setattr(insight_server, "_llm", gw)
    out = run(insight_server.generate_insight(FRICTION, run_context={"correlation_id": "run-0003"}))
    prompt = json.dumps(transport.bodies()[0])
    for secret in ("SECRETUSER", "SECRETSESS", "someone@example.test"):
        assert secret not in prompt
    insight = out["insight"]
    assert (insight["category"], insight["fix_effort"], insight["evidence"]) == ("unknown", "medium", [])
    assert insight["step_id"] == "sign_up_form" and insight["insight_id"]
    assert out["llm"]["outcome"] == "ok" and out["llm"]["provider"] == "groq"


def test_generate_insight_fallback_is_unchanged(monkeypatch):
    from cji.mcp_servers import insight_server

    gw, _, _, _ = gateway(status_response(401))
    monkeypatch.setattr(insight_server, "_llm", gw)
    out = run(insight_server.generate_insight(FRICTION))
    insight = out["insight"]
    assert {k: insight[k] for k in ("step_id", "title", "category", "evidence", "suggested_fix", "fix_effort")} == {
        "step_id": "sign_up_form", "title": "Friction at sign_up_form", "category": "unknown",
        "evidence": ["high_abandon"], "suggested_fix": "Review metrics manually.", "fix_effort": "medium"}
    assert out["llm"] == {**out["llm"], "outcome": "fallback", "code": "auth_failed", "attempts": 1}


@pytest.mark.parametrize("content, expect_fallback, code", [
    ("", True, "empty_response"),
    ("   \n ", True, "empty_response"),
    ("x" * 5000, False, None),
])
def test_generate_narrative_post_processing(monkeypatch, content, expect_fallback, code):
    from cji.mcp_servers import report_server

    gw, transport, _, _ = gateway(groq_response(content))
    monkeypatch.setattr(report_server, "_llm", gw)
    out = run(report_server.generate_narrative(
        insights=[{"title": "T", "category": "UX", "root_cause": "R", "suggested_fix": "F",
                   "user_id": "user-SECRETUSER"}],
        journey_name="user_onboarding", avg_score=55.0, critical_count=1, mode="demo"))
    assert "SECRETUSER" not in json.dumps(transport.bodies()[0])
    assert "response_format" not in transport.bodies()[0]
    if expect_fallback:
        assert out["narrative"].startswith("This analysis of the user_onboarding journey")
        assert out["llm"]["code"] == code
    else:
        assert len(out["narrative"]) == report_server.MAX_NARRATIVE_CHARS
    assert set(out) == {"narrative", "generated_at", "llm"}


def test_report_and_insight_servers_have_no_provider_code():
    for rel in ("mcp_servers/insight_server.py", "mcp_servers/report_server.py",
                "mcp_servers/ingestion_intelligence_server.py"):
        src = (SRC / rel).read_text(encoding="utf-8")
        for marker in ("api.groq.com", "api.anthropic.com", "import requests", "gpt-oss-120b", "llm_retry"):
            assert marker not in src, f"{rel} still contains {marker!r}"


def test_only_the_gateway_talks_to_providers():
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("integrations/") or "/." in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "api.groq.com" in text or "api.anthropic.com" in text:
            offenders.append(rel)
    assert offenders == []


# ═════════════════════════════════════════════════════════════════════════════
# Secrets never reach exceptions, logs or audit (OD-63)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("item", [
    status_response(401, {"error": {"message": f"Invalid API key {KEY}", "type": "auth"}}),
    httpx.ReadTimeout(f"timeout while sending {KEY}"),
    httpx.ConnectError(f"proxy refused Authorization: Bearer {KEY}"),
])
def test_secret_never_reaches_exceptions_logs_or_audit(item, caplog):
    caplog.set_level(logging.DEBUG)
    items = [item] if isinstance(item, httpx.Response) else [item, item, item]
    gw, _, _, audit = gateway(*items)
    with pytest.raises(Exception) as exc:
        run(gw.complete(REQ, CTX))
    blob = " ".join([str(exc.value), repr(exc.value), caplog.text, json.dumps(audit.records)])
    assert KEY not in blob


def test_scrub_removes_configured_secrets_and_auth_headers():
    text = f"Authorization: Bearer abc.def-123 x-api-key={KEY} plain {KEY}"
    clean = scrub(text, [KEY])
    assert KEY not in clean and "abc.def-123" not in clean and clean.count("[redacted]") >= 2


def test_worker_error_text_is_scrubbed(monkeypatch):
    import cji.agents.workers as w

    @contextlib.asynccontextmanager
    async def fake_session(name):
        yield object()

    async def failing_call(session, tool, arguments=None):
        raise RuntimeError("upstream said Authorization: Bearer live-token-123")

    monkeypatch.setattr(w, "mcp_session", fake_session)
    monkeypatch.setattr(w, "call_tool", failing_call)
    out = run(w.insight_worker({"friction_scores": [{"step_id": "s", "score": 90, "is_critical": True}]}))
    assert "live-token-123" not in json.dumps(out["errors"]) + json.dumps(out["worker_statuses"])


# ═════════════════════════════════════════════════════════════════════════════
# Audit records (OD-61 / OD-62)
# ═════════════════════════════════════════════════════════════════════════════

def test_llm_audit_record_has_correlation_metadata_and_no_payload():
    gw, _, _, audit = gateway(httpx.ConnectError("x"), groq_response('{"a": "SECRETRESPONSE"}', prompt_tokens=11,
                                                                      completion_tokens=4))
    run(gw.complete(REQ, CTX))
    (record,) = audit.records
    assert {k: record[k] for k in ("kind", "correlation_id", "worker", "purpose", "provider", "model", "outcome",
                                   "attempts", "input_tokens", "output_tokens", "prompt_chars", "http_status")} == {
        "kind": "llm", "correlation_id": "run-0001", "worker": "test_worker", "purpose": "insight",
        "provider": "groq", "model": "test-model", "outcome": "ok", "attempts": 2, "input_tokens": 11,
        "output_tokens": 4, "prompt_chars": REQ.prompt_chars, "http_status": 200}
    assert record["call_id"] and record["ts"]
    blob = json.dumps(record)
    for secret in ("SECRETPROMPT", "SECRETRESPONSE", KEY, "You are CJI"):
        assert secret not in blob


def _insight_handlers(seen):
    def generate(args):
        seen.append(args["run_context"])
        fs = args["friction_score"]
        return {"insight": {"insight_id": f"i-{fs['step_id']}", "step_id": fs["step_id"], "title": "T",
                            "root_cause": "R", "category": "UX", "evidence": [], "suggested_fix": "F",
                            "fix_effort": "low"},
                "llm": {"call_id": "c", "provider": "groq", "model": "m", "outcome": "ok", "attempts": 1,
                        "input_tokens": 100, "output_tokens": 50, "cost_usd": None}}

    return {
        "generate_insight": generate,
        "prioritise_fix": lambda args: {**args["insight"], "priority": 1, "priority_score": 1.0},
        "save_insight": lambda args: {"status": "success"},
        "rank_all_fixes": lambda args: {"ranked_fixes": [], "total": 0},
    }


def test_insight_worker_uses_the_gateway_with_correlation_and_budget(monkeypatch):
    import cji.agents.workers as w

    seen = []
    session = FakeToolSession(_insight_handlers(seen))
    audit = MemoryAuditSink()
    tools_module.reset_tool_gateway(ToolGateway(audit=audit))

    @contextlib.asynccontextmanager
    async def fake_session(name):
        yield session

    monkeypatch.setattr(w, "mcp_session", fake_session)
    state = {
        "friction_scores": [{"step_id": "a", "score": 90, "is_critical": True},
                            {"step_id": "b", "score": 80, "is_critical": True}],
        "event_summary": {"step_metrics": [{"step_id": "a", "unique_users": 5, "email": "x@example.test"}]},
        "llm_usage": {"calls": 1, "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0},
    }
    out = run(w.insight_worker(state, {"configurable": {"thread_id": "thread-abc-123"}}))

    assert out["worker_statuses"][0]["status"] == "success"
    assert out["llm_usage"] == {"calls": 3, "input_tokens": 210, "output_tokens": 105, "cost_usd": 0.0}
    assert [ctx["budget"]["calls_left"] for ctx in seen] == [19, 18]
    assert {ctx["correlation_id"] for ctx in seen} == {"thread-abc-123"}
    assert all("llm" not in ins for ins in out["insights"])
    tool_records = audit.of_kind("tool")
    assert [r["tool"] for r in tool_records] == ["generate_insight", "generate_insight", "prioritise_fix",
                                                 "prioritise_fix", "save_insight", "save_insight", "rank_all_fixes"]
    assert {r["correlation_id"] for r in tool_records} == {"thread-abc-123"}
    assert {r["worker"] for r in tool_records} == {"insight_worker"}
    assert "x@example.test" not in json.dumps(audit.records)
    assert tool_records[0]["arg_keys"] == ["friction_score", "run_context"]


def test_report_worker_uses_the_gateway_and_unwraps_the_narrative(monkeypatch):
    import cji.agents.workers as w

    seen = []

    def narrative(args):
        seen.append(args["run_context"])
        return {"narrative": "N", "generated_at": "2026-10-28T00:00:00Z",
                "llm": {"outcome": "ok", "attempts": 1, "input_tokens": 40, "output_tokens": 60}}

    session = FakeToolSession({
        "generate_narrative": narrative,
        "export_report": lambda args: {"report_path": "/tmp/r.html", "file_size_kb": 1.0},
    })
    tools_module.reset_tool_gateway(ToolGateway(audit=MemoryAuditSink()))

    @contextlib.asynccontextmanager
    async def fake_session(name):
        yield session

    monkeypatch.setattr(w, "mcp_session", fake_session)
    out = run(w.report_worker({"insights": [], "friction_scores": [], "llm_usage": {"calls": 2}},
                              {"configurable": {"thread_id": "thread-xyz-9"}}))
    assert out["narrative"] == "N" and out["llm_usage"]["calls"] == 3
    assert seen[0]["correlation_id"] == "thread-xyz-9" and seen[0]["budget"]["calls_left"] == 18


def test_graph_nodes_accept_the_langgraph_config():
    import cji.agents.ingestion_worker as iw
    import cji.agents.workers as w

    for node in (w.data_worker, w.friction_worker, w.insight_worker, w.report_worker, iw.ingestion_worker):
        assert list(inspect.signature(node).parameters) == ["state", "config"], node.__name__


def test_audit_sinks(tmp_path):
    sink = JsonlSink(tmp_path / "audit" / "svc.jsonl")
    sink.write({"kind": "llm", "outcome": "ok"})
    sink.write({"kind": "tool", "outcome": "error"})
    lines = (tmp_path / "audit" / "svc.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["kind"] for line in lines] == ["llm", "tool"]
    assert isinstance(default_sink("svc"), LogSink)         # tests: no audit directory


# ═════════════════════════════════════════════════════════════════════════════
# Friction engine stays independent (OD-65)
# ═════════════════════════════════════════════════════════════════════════════

def test_friction_engine_imports_no_ai_code():
    code = (
        "import sys; import cji.mcp_servers.friction_engine_server; "
        "bad = sorted(m for m in sys.modules if m.startswith(('cji.integrations', 'cji.guardrails')) "
        "or m.split('.')[0] == 'requests' "
        "or m in ('cji.mcp_servers.insight_server', 'cji.mcp_servers.report_server', 'cji.tools.mcp_client')); print(bad)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=APP_ROOT, capture_output=True, text=True,
                         timeout=120, check=False, env={**__import__("os").environ, "CJI_ENV": "test"})
    assert out.returncode == 0, out.stderr[-800:]
    assert out.stdout.strip().splitlines()[-1] == "[]"


# ═════════════════════════════════════════════════════════════════════════════════════════
# Spec 08 gate findings: mcp 2.x error field, anyio exception groups, ingestion correlation
# ═════════════════════════════════════════════════════════════════════════════════════════

def test_real_mcp_tool_error_results_are_tool_errors():
    from types import SimpleNamespace

    from mcp import types as mcp_types

    wire = {"content": [{"type": "text", "text": "Error executing tool t"}], "isError": True}
    real = mcp_types.CallToolResult.model_validate(wire)                  # as the client parses it
    assert real.is_error is True
    legacy = SimpleNamespace(isError=True, content=real.content)          # mcp 1.x field name
    for result in (real, legacy):
        gw = ToolGateway(audit=MemoryAuditSink())
        with pytest.raises(ToolFailed) as exc:
            run(gw.call(FakeToolSession({"t": lambda args, r=result: r}), "t", {}))
        assert exc.value.code == "tool_error"


def test_tool_session_unwraps_a_single_error_from_an_exception_group():
    @contextlib.asynccontextmanager
    async def grouping_opener(name):
        try:                                   # like the SSE client's anyio task group
            yield FakeToolSession({"t": lambda args: tool_result("Error executing tool t", is_error=True)})
        except Exception as exc:
            raise ExceptionGroup("unhandled errors in a TaskGroup", [exc]) from exc

    gw = ToolGateway(audit=MemoryAuditSink(), opener=grouping_opener)

    async def go():
        async with gw.session("cji-insight") as session:
            await gw.call(session, "t", {})

    with pytest.raises(ToolFailed) as exc:
        run(go())
    assert exc.value.code == "tool_error"


def test_tool_session_keeps_exception_groups_with_several_errors():
    @contextlib.asynccontextmanager
    async def grouping_opener(name):
        try:
            yield FakeToolSession({})
        except Exception as exc:
            raise ExceptionGroup("two", [exc, ValueError("other")]) from exc

    gw = ToolGateway(audit=MemoryAuditSink(), opener=grouping_opener)

    async def go():
        async with gw.session("cji-insight"):
            raise KeyError("body")

    with pytest.raises(ExceptionGroup):
        run(go())


def test_detect_schema_flags_the_file_for_review_when_the_llm_fails(monkeypatch, tmp_path):
    from cji.mcp_servers import ingestion_intelligence_server as ing

    gw, transport, _, audit = gateway(status_response(401, {"error": {"message": "bad key", "type": "auth"}}))
    monkeypatch.setattr(ing, "_llm", gw)
    monkeypatch.setattr(ing, "_load_registry", dict)
    path = tmp_path / "unknown.csv"
    path.write_text("colA,colB\n1,2\n", encoding="utf-8")
    out = run(ing.detect_schema(str(path), run_context=CTX.model_dump()))
    assert out["confidence"] == 0.0 and out["cached"] is False
    assert out["llm_error"] == audit.records[-1]["code"]
    assert audit.records[-1]["correlation_id"] == "run-0001"
    assert len(transport.requests) == 1


def test_ingestion_worker_sends_the_run_context(monkeypatch, tmp_path):
    import cji.agents.ingestion_worker as iw

    seen = []
    session = FakeToolSession({"detect_schema": lambda args: seen.append(args) or {"confidence": 0.0}})

    @contextlib.asynccontextmanager
    async def fake_session(name):
        yield session

    monkeypatch.setattr(iw, "mcp_session", fake_session)
    data = tmp_path / "f.csv"
    data.write_text("a\n1\n", encoding="utf-8")
    run(iw.ingestion_worker({"ingestion_pending_files": [{"file_path": str(data)}], "llm_usage": {}},
                            {"configurable": {"thread_id": "thread-ing-1"}}))
    assert seen[0]["run_context"]["correlation_id"] == "thread-ing-1"
    assert seen[0]["run_context"]["budget"]["calls_left"] == 20
