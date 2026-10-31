# Spec 08 — AI Gateway: Design

## 1. Module layout
```text
cji_agent/integrations/
  __init__.py     public names: LLMGateway, ToolGateway, LLMRequest, LLMResult, RunContext, GatewayError, ...
  types.py        LLMRequest, LLMResult, Usage, RunContext, RunBudget, LLMCallInfo (pydantic, frozen)
  errors.py       GatewayError(code, retryable) and subclasses; classify(status | exception) -> error
  policy.py       RetryPolicy (attempts, backoff, deadline), TokenBucket, budget check; clock/sleep injectable
  providers.py    GroqAdapter, AnthropicAdapter, DisabledAdapter: build request, parse response + usage
  llm.py          LLMGateway.complete(request, ctx) -> LLMResult; provider_from_settings()
  tools.py        ToolGateway: session(service), call(session, tool, args) with timeout, audit, correlation
  audit.py        AuditRecord, LogSink, JsonlSink, MemorySink; scrub(text, secrets)
  context.py      correlation context variable; new_call_id()
  testing.py      ScriptedTransport, ManualClock, MemoryAuditSink, FakeToolSession
```
`tools/mcp_client.py` keeps `mcp_session`, `call_tool`, `server_url`, `ping_all_servers` as thin wrappers over
`ToolGateway`, so `agents/workers.py`, `agents/ingestion_worker.py` and the existing test fakes keep working.

## 2. LLM call flow (`LLMGateway.complete`)
```text
complete(request, ctx):
  0. provider == none                      -> LLMDisabled (no audit of payload; outcome "fallback")
  1. budget check (ctx.budget vs request.max_tokens, calls, cost)  -> BudgetExceeded, nothing sent
  2. deadline = now + CJI_LLM_DEADLINE_S
  3. for attempt in 1..attempts:
       wait for rate-limit token (only if it fits the deadline, else RateLimited)
       POST via httpx.AsyncClient(timeout = min(per_attempt, deadline - now))
       ok -> adapter.parse(): text, usage; JSON mode: json.loads -> object required, else MalformedResponse
       error -> classify(): retryable and time left -> sleep(backoff or Retry-After) -> next attempt
                            otherwise raise
     CancelledError at any point: audit "cancelled", re-raise (no retry)
  4. audit one record (always, in finally): outcome, code, attempts, latency, usage, cost
```
`LLMRequest(purpose, system, user, response_format: "json" | "text", max_tokens, temperature)`.
`LLMResult(text, data: dict | None, info: LLMCallInfo)`;
`LLMCallInfo(call_id, provider, model, outcome, code, attempts, latency_ms, input_tokens, output_tokens, cost_usd)`.

Classification table (OD-56):
| Condition | Error | retryable |
|---|---|---|
| `httpx.TimeoutException` | `LLMTimeout` | yes |
| `httpx.TransportError` (connect, proxy, read) | `ProviderUnavailable` | yes |
| 429 | `RateLimited` (Retry-After parsed) | yes |
| 500, 502, 503, 504, 529 | `ProviderUnavailable` | yes |
| 401, 403 | `ProviderRejected(code="auth_failed")` | no |
| 404, or 400 whose error type is model-related | `ProviderRejected(code="model_not_found")` | no |
| other 4xx | `ProviderRejected(code="bad_request")` | no |
| body not JSON, missing fields, JSON mode content not an object | `MalformedResponse` | no |
Messages: `"groq call failed: HTTP 401 (auth_failed)"`, never response bodies or exception text.

## 3. Tool call flow (`ToolGateway`)
```text
session(service): open SSE session (connect retried once on transport error), audit "session_open"
call(session, tool, args):
  correlation_id from context; asyncio.timeout(CJI_MCP_CALL_TIMEOUT_S)
  result = await session.call_tool(tool, arguments=args)
  isError or non-JSON text -> MalformedToolResult; timeout -> ToolTimeout; other -> ToolFailed (cause chained,
  message from type name only)
  audit: service, tool, argument key names, outcome, latency (no values)
```

## 4. Server tools
- `generate_insight(friction_score, run_context=None)` async: sanitise (unchanged) -> same prompts ->
  `LLMGateway.complete(json)` -> `validate_llm_output` (unchanged) -> `{"insight": ..., "llm": info}`.
  Any `GatewayError` -> the existing fallback insight, `llm.outcome = "fallback"`, `llm.code = error.code`.
- `generate_narrative(..., run_context=None)` async: insights passed through `sanitise_for_llm` -> text mode ->
  strip, cap 4,000 characters -> existing fallback paragraph on error or empty text; adds `llm`.
- Ingestion `_call_llm_for_mapping` async via the gateway, `purpose="schema_mapping"` / `"quality_check"`; the
  Anthropic-then-Groq sequence is removed. Callers keep raising `RuntimeError` on failure, now with the code only.
- `run_context` = `{"correlation_id", "worker", "budget": {"calls_left", "tokens_left", "cost_left_usd"}}`,
  validated as `RunContext`; missing means a fresh correlation id and the configured per-run limits.

## 5. Workers
- `insight_worker(state, config=None)` and `report_worker(state, config=None)`: correlation id from
  `config["configurable"]["thread_id"]`, budget remaining from `state["llm_usage"]`; pass `run_context`;
  unwrap `{"insight", "llm"}`; add usage to `llm_usage`; keep `domain` contract checks on the unwrapped values.
- All workers: error entries use `GatewayError.code` / exception type, not raw exception text (F-30).
- `state.py`: `llm_usage: dict` (calls, input_tokens, output_tokens, cost_usd) with a merge reducer.
- Graph wiring unchanged: LangGraph passes `config` to node functions that accept it.

## 6. Settings
`LLMSettings` gains `provider`, `deadline_s`, `rate_per_min`, `price_input_per_mtok`, `price_output_per_mtok`;
`model` becomes optional (provider default). New `RunBudgetSettings(max_calls, max_tokens, max_cost_usd)`.
`MCPSettings.call_timeout_s`. `StorageSettings.audit_dir` (`off` disables files). Checks: provider/model mismatch,
cost cap without prices, deadline shorter than one attempt's timeout, MCP call timeout shorter than the LLM deadline.

## 7. Tests (`tests/test_gateway.py`, plus updates)
| Area | Cases |
|---|---|
| Provider selection | groq/anthropic/none chosen from settings; mismatched model refused at load; no second provider called after a failure (transport records every URL); allow-list substitution gone |
| Request/response | Groq and Anthropic request shapes (model, max_tokens, JSON mode); usage parsed; JSON object required in JSON mode |
| Timeouts | per-attempt timeout -> retried; deadline stops further attempts; MCP call timeout -> `ToolTimeout` |
| Retries | 429 with Retry-After, 503 retried up to attempts; 400/401/404 sent once; backoff sequence exact (recorded sleeps) |
| Cancellation | task cancelled during the request and during backoff: no further request, audit `cancelled`, `CancelledError` raised; worker cancellation closes the session |
| Rate limit | bucket of 1: second call waits on the manual clock or fails `rate_limited` when it would pass the deadline |
| Budgets | calls/tokens/cost exhausted -> nothing sent, fallback with `budget_exceeded`; cost cap without prices -> ConfigError; worker accumulates `llm_usage` across insights |
| Malformed | non-JSON body, missing `choices`, JSON mode returning text or a list; MCP non-JSON and `isError` results |
| Guardrails | `sanitise_for_llm` removes blocked fields from the prompt (captured request body); `validate_llm_output` still applied; fallback content unchanged |
| Secrets | sentinel key absent from exceptions, `repr`, logs, audit and worker state for 401, timeout and transport errors (also when the provider echoes the key in its body) |
| Audit | records carry correlation_id = thread_id, call_id, provider, model, attempts, tokens; contain no prompt text, argument values, user/session/event ids or URLs |
| Friction engine | import graph of `friction_engine_server` contains no `integrations` or LLM modules; scores unchanged (golden) |
| Workers | insight and report workers run against `FakeToolSession` + scripted LLM tools and use the gateway |
Existing tests updated: `test_cleanup` (tenacity no longer required), worker fakes if their signature changes.

## 8. Risks
| Risk | Mitigation |
|---|---|
| Ingestion stops using Anthropic when a user relied on it | Set `CJI_LLM_PROVIDER=anthropic`; documented in README and the startup message |
| Model strings that worked through the allow-list substitution now fail | The failure is visible (`model_not_found` in audit, worker status, `settings check`); F-25 documented |
| Sync → async MCP tools | FastMCP supports async tools; covered by tool-level tests and the demo pipeline in the gate |
| Per-process limits and budgets across three servers | Run budget travels with the call (`run_context`); shared accounting belongs to Spec 09 |

## 9. Rollback
`git apply -R evidence/spec08-tracked.patch`, then `git apply evidence/pre-spec08-tracked.patch`; restore untracked
files from `evidence/pre-spec08-untracked/`; delete `cji_agent/integrations/` and `tests/test_gateway.py`;
`data/audit/` may be deleted.
