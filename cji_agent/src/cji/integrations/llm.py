"""
LLMGateway (Spec 08): the only way CJI calls an LLM provider.

One provider per process, fixed at construction (OD-54). Per-attempt timeout plus an overall deadline,
bounded retries for retryable errors only, a per-process rate limit, run budgets, cancellation, and one
audit record per call (OD-56 to OD-62).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .audit import AuditSink, default_sink, make_record
from .context import new_call_id
from .errors import (
    GatewayError,
    LLMDisabled,
    LLMTimeout,
    ProviderRejected,
    ProviderUnavailable,
    classify_status,
)
from .policy import RetryPolicy, Timing, TokenBucket, check_budget, cost_usd
from .providers import ADAPTERS, DEFAULT_MODELS, normalise_model, parse_json_object
from .types import LLMCallInfo, LLMRequest, LLMResult, Outcome, RunContext, Usage

log = logging.getLogger("cji.integrations")

# Tests replace this with a transport that refuses unscripted requests (tests/conftest.py).
DEFAULT_TRANSPORT: httpx.AsyncBaseTransport | None = None



def _count(provider: str, outcome: str, info: LLMCallInfo) -> None:
    """Process metrics for one LLM call (Spec 15, OD-160): calls by outcome, tokens and cost."""
    from cji.observability import metrics

    metrics.LLM_CALLS.inc(provider=provider, outcome=outcome)
    if info.input_tokens:
        metrics.LLM_TOKENS.inc(info.input_tokens, direction="input")
    if info.output_tokens:
        metrics.LLM_TOKENS.inc(info.output_tokens, direction="output")
    if info.cost_usd:
        metrics.LLM_COST.inc(info.cost_usd)

class LLMGateway:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str | None,
        service: str,
        timeout_s: float = 30.0,
        deadline_s: float = 90.0,
        retry: RetryPolicy | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
        rate_per_min: int = 30,
        price_input_per_mtok: float | None = None,
        price_output_per_mtok: float | None = None,
        audit: AuditSink | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        timing: Timing | None = None,
    ) -> None:
        if provider != "none" and provider not in ADAPTERS:
            raise ValueError(f"unknown LLM provider {provider!r}")
        self.provider = provider
        self.model = normalise_model(provider, model or DEFAULT_MODELS[provider])
        self._api_key = api_key
        self.service = service
        self.timeout_s = timeout_s
        self.deadline_s = deadline_s
        self.retry = retry or RetryPolicy()
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.price_in = price_input_per_mtok
        self.price_out = price_output_per_mtok
        self.audit = audit or default_sink(service)
        self._transport = transport
        self.timing = timing or Timing()
        self._bucket = TokenBucket(rate_per_min, self.timing)

    @classmethod
    def from_settings(cls, service: str, **overrides: Any) -> LLMGateway:
        from cji.settings import get_settings, secret_value

        llm = get_settings().llm
        keys = {"groq": llm.groq_api_key, "anthropic": llm.anthropic_api_key}
        kwargs: dict[str, Any] = {
            "provider": llm.provider,
            "model": llm.model,
            "api_key": secret_value(keys.get(llm.provider)) or None,
            "service": service,
            "timeout_s": llm.timeout_s,
            "deadline_s": llm.deadline_s,
            "retry": RetryPolicy(llm.retry.attempts, llm.retry.min_wait_s, llm.retry.max_wait_s),
            "max_tokens": llm.max_tokens,
            "temperature": llm.temperature,
            "rate_per_min": llm.rate_per_min,
            "price_input_per_mtok": llm.price_input_per_mtok,
            "price_output_per_mtok": llm.price_output_per_mtok,
        }
        kwargs.update(overrides)
        return cls(**kwargs)

    @property
    def available(self) -> bool:
        """True when calls can be attempted (a provider is selected and its key is configured)."""
        return self.provider != "none" and bool(self._api_key)

    def secrets(self) -> tuple[str, ...]:
        return (self._api_key,) if self._api_key else ()

    async def complete(self, request: LLMRequest, ctx: RunContext) -> LLMResult:
        call_id = new_call_id()
        started = self.timing.now()
        state: dict[str, Any] = {"attempts": 0, "usage": Usage(), "status": None}
        outcome: Outcome = "error"
        error: GatewayError | None = None
        try:
            result = await self._complete(request, ctx, call_id, started, state)
            outcome = "ok"
            return result
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except GatewayError as exc:
            error = exc
            exc.info = self._info(call_id, "error", exc.code, started, state)
            raise
        finally:
            info = self._info(call_id, outcome, error.code if error else None, started, state)
            self.audit.write(make_record(
                kind="llm", service=self.service, correlation_id=ctx.correlation_id, call_id=call_id,
                worker=ctx.worker, purpose=request.purpose, provider=self.provider, model=self.model,
                outcome=outcome, code=info.code, retryable=error.retryable if error else None,
                attempts=info.attempts, latency_ms=info.latency_ms, input_tokens=info.input_tokens,
                output_tokens=info.output_tokens, cost_usd=info.cost_usd, prompt_chars=request.prompt_chars,
                http_status=state["status"],
            ))
            _count(self.provider, outcome, info)

    def _info(self, call_id: str, outcome: Outcome, code: str | None, started: float,
              state: dict[str, Any]) -> LLMCallInfo:
        usage: Usage = state["usage"]
        return LLMCallInfo(
            call_id=call_id, provider=self.provider, model=self.model, outcome=outcome, code=code,
            attempts=state["attempts"], latency_ms=int((self.timing.now() - started) * 1000),
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            cost_usd=cost_usd(usage.input_tokens, usage.output_tokens, self.price_in, self.price_out),
        )

    async def _complete(self, request: LLMRequest, ctx: RunContext, call_id: str, started: float,
                        state: dict[str, Any]) -> LLMResult:
        if self.provider == "none":
            raise LLMDisabled("LLM calls are disabled: CJI_LLM_PROVIDER=none (llm_disabled)")
        if not self._api_key:
            raise ProviderRejected(f"{self.provider} API key is not configured (not_configured)",
                                   code="not_configured")
        adapter = ADAPTERS[self.provider]
        max_tokens = request.max_tokens or self.max_tokens
        temperature = self.temperature if request.temperature is None else request.temperature
        check_budget(ctx.budget, prompt_chars=request.prompt_chars, max_tokens=max_tokens,
                     price_in=self.price_in, price_out=self.price_out)
        body = adapter.body(request, self.model, max_tokens, temperature)
        headers = adapter.headers(self._api_key)
        deadline = started + self.deadline_s
        transport = self._transport or DEFAULT_TRANSPORT

        async with httpx.AsyncClient(transport=transport) as client:
            for attempt in range(1, self.retry.attempts + 1):
                time_left = deadline - self.timing.now()
                if time_left <= 0:
                    raise LLMTimeout(f"{self.provider} call exceeded the {self.deadline_s:g}s deadline (timeout)")
                await self._bucket.acquire(time_left, self.provider)
                time_left = deadline - self.timing.now()
                state["attempts"] = attempt
                error = await self._attempt(client, adapter, body, headers, min(self.timeout_s, time_left),
                                            request, state)
                if isinstance(error, LLMResult):
                    return error.model_copy(update={"info": self._info(call_id, "ok", None, started, state)})
                if not error.retryable or attempt == self.retry.attempts:
                    raise error
                wait = error.retry_after if error.retry_after is not None else self.retry.backoff(attempt)
                if self.timing.now() + wait >= deadline:
                    raise error
                log.warning("%s call %s attempt %d failed (%s); retrying in %.1fs",
                            self.provider, call_id, attempt, error.code, wait)
                await self.timing.sleep(wait)
        raise LLMTimeout(f"{self.provider} call made no attempt (timeout)")   # attempts >= 1 by settings

    async def _attempt(self, client: httpx.AsyncClient, adapter: Any, body: dict[str, Any],
                       headers: dict[str, str], timeout: float, request: LLMRequest,
                       state: dict[str, Any]) -> LLMResult | GatewayError:
        """One HTTP attempt: an LLMResult, or the classified error (raised only when not retryable by kind)."""
        try:
            response = await client.post(adapter.url, headers=headers, json=body, timeout=timeout)
        except httpx.TimeoutException:
            return LLMTimeout(f"{self.provider} call timed out after {timeout:.0f}s (timeout)")
        except httpx.TransportError as exc:
            return ProviderUnavailable(f"{self.provider} call failed: {type(exc).__name__} (provider_unavailable)")
        state["status"] = response.status_code
        if response.status_code >= 400:
            try:
                error_body: Any = response.json()
            except ValueError:
                error_body = None
            return classify_status(self.provider, response.status_code, error_body,
                                   response.headers.get("retry-after"))
        try:
            payload = response.json()
        except ValueError:
            payload = None
        text, usage = adapter.parse(payload)              # MalformedResponse: raised, not retried
        state["usage"] = usage
        data = parse_json_object(text, self.provider) if request.response_format == "json" else None
        placeholder = LLMCallInfo(call_id="-", provider=self.provider, model=self.model, outcome="ok")
        return LLMResult(text=text, data=data, info=placeholder)

