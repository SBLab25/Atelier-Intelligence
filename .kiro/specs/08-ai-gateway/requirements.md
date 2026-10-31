# Spec 08 — AI Gateway: Requirements
**Source:** `kiro_upgrade_prompts.md` Prompt 7. **Findings addressed:** `refactoring.md` R-12 (no unified timeout,
budget, correlation or audit contract for LLM and MCP calls), F-12 noted for this Spec in Spec 06, plus the survey
findings F-25 to F-30 below.
**Branch:** `phase-02-security` (no commits; patch files are the rollback points, as in Specs 02–07).
**Status:** written 2026-10-28; defaults OD-53 to OD-66 approved ("implement spec 08"); implemented and gated 2026-10-28 (see `tasks.md`).

## 1. Current state (surveyed after Spec 07)
| Area | Today | Problem |
|---|---|---|
| Where LLM calls run | Inside three MCP server processes: `insight_server.generate_insight`, `report_server.generate_narrative`, `ingestion_intelligence_server._call_llm_for_mapping` (mapping and quality check). Workers only call MCP tools. | Three separate HTTP implementations with `requests.post`; no shared types. |
| Provider selection | insight/report always call Groq. Ingestion calls Anthropic first, then Groq with a hard-coded `llama3-8b-8192`. | Ingestion switches provider silently (R-12). |
| Model selection | insight/report replace any `LLM_MODEL` not in a hard-coded list with `openai/gpt-oss-120b`. The settings default is `claude-sonnet-4-6`, so with defaults the configured model is never used (F-29). | Silent model switch; allow-list duplicated in two files. |
| Timeouts | Each attempt uses `CJI_LLM_TIMEOUT_S` (30 s). No overall deadline. MCP: SSE connect 5 s, read 300 s; no per-tool-call limit. | A tool call can wait 300 s; retries have no total bound. |
| Retries | `guardrails/rate_limiter.llm_retry` (tenacity), insight only. It retries every `requests.RequestException`, which includes `HTTPError` from `raise_for_status()`: 400, 401 and 404 are retried 3 times (F-26). report and ingestion: no retries. | Wrong classification; inconsistent. |
| Cancellation | Synchronous `requests` calls inside synchronous MCP tools. | A cancelled run cannot stop an in-flight LLM call. |
| Rate limits, budgets | None. `LLM_MAX_TOKENS` is read but not sent by insight/report. | No token or cost ceiling per run. |
| Correlation, audit | `main.py` creates a `thread_id` per run; it never reaches the servers. Logs only. | No record of which provider/model/tool produced a result. |
| Secrets | Keys come from settings (`SecretStr`). Errors are logged as `f"{type(e).__name__}: {e}"` with `exc_info`, and copied into `worker_statuses`/`errors` text. | Provider error text can reach logs and state; nothing scrubs it. |
| Guardrails | Pre-LLM: `guardrails/sanitiser.sanitise_for_llm` (insight only). Post-LLM: `guardrails/output_validator.validate_llm_output` (insight only). Fallback content when the LLM fails (insight, report). | Must be preserved. |
| Malformed responses | insight: `json.loads` failure → fallback insight. MCP client: non-JSON tool output becomes `{"text": ...}` silently. | Silent shape change on the tool side. |
| Tests | No test exercises `generate_insight`, `generate_narrative` or the ingestion LLM path. | Acceptance criteria need new tests. |
| Friction engine | `friction_engine_server.py` is pure and imports no LLM code. | Must stay that way. |

Survey findings:
| ID | Finding |
|---|---|
| F-25 | The local `.env` sets `LLM_MODEL=llama3-70b-8192`. Groq shut this model down on 2025-08-30 (Groq deprecations page, replacement `llama-3.3-70b-versatile`, itself shut down 2026-08-16; current recommendation `openai/gpt-oss-120b`). Every insight and narrative in this environment falls back to template text today. Ingestion's Groq fallback `llama3-8b-8192` was shut down the same day. |
| F-26 | `llm_retry` retries 4xx errors, including 401 (see above). |
| F-27 | Ingestion sends up to `INGESTION_SAMPLE_ROWS` raw source rows to the LLM; user-id and URL sanitising runs only after the mapping is applied. Raw rows may contain personal data. |
| F-28 | `OPENAI_API_KEY` is read into settings but no code uses it. |
| F-29 | Default `LLM_MODEL=claude-sonnet-4-6` is replaced by `openai/gpt-oss-120b` in insight/report and sent to Anthropic in ingestion. |
| F-30 | Worker error entries embed raw exception text (`f"{type(exc).__name__}: {exc}"`), so provider messages can reach workflow state and the dashboard. |

## 2. Decisions (defaults; confirm or change before implementation)
| ID | Topic | Default | Rejected alternatives |
|---|---|---|---|
| OD-53 | Placement | One package `cji_agent/integrations/` with two typed entry points: `LLMGateway`, used where LLM calls happen today (inside the insight, report and ingestion MCP servers), and `ToolGateway`, the MCP client used by every workflow worker through the existing `tools.mcp_client.mcp_session` / `call_tool` names. | Move LLM calls into the workers (changes the MCP topology; belongs to Spec 12). A separate gateway service (new process and network hop for 3 call sites). |
| OD-54 | Provider selection | `CJI_LLM_PROVIDER` = `groq` (default: what insight/report use today), `anthropic`, or `none` (LLM disabled; deterministic fallback content). One provider per process, fixed at startup; no fallback to another provider. `LLM_MODEL` is sent exactly as configured (a leading `groq/` is still accepted); the hard-coded allow-list substitution is removed. If `LLM_MODEL` is unset the provider default is used: groq `openai/gpt-oss-120b` (what runs today with default settings), anthropic `claude-sonnet-4-6` (today's settings default). Startup refuses an obvious mismatch: a `claude…` or `anthropic/…` model with groq, or a non-`claude` model with anthropic. **Behaviour change:** ingestion uses the configured provider instead of Anthropic-then-Groq. OpenAI is not added (F-28). | Keep the allow-list substitution (silent switch). Automatic failover between providers (explicitly forbidden by Prompt 7). Per-tool provider settings (more configuration than three call sites need). |
| OD-55 | Transport | `httpx.AsyncClient` (already installed as an `mcp` dependency; declared in `requirements.txt`). Two small adapters: Groq (OpenAI-compatible `/chat/completions`, JSON mode) and Anthropic (`/v1/messages`). The three LLM tools become `async def` (FastMCP supports both). | Vendor SDKs (new dependencies, each with its own retry layer). Keep `requests` (cannot be cancelled). LangChain chat models (heavier; retries hidden). |
| OD-56 | Timeouts and retries | Per attempt `CJI_LLM_TIMEOUT_S` (30 s, existing). New overall deadline `CJI_LLM_DEADLINE_S` (90 s) covering all attempts and waits. Attempts and backoff from the existing `CJI_LLM_RETRY_ATTEMPTS` (3) / `_MIN_S` (2) / `_MAX_S` (10), exponential, no jitter (deterministic). **Retryable:** connect/read timeout, connection error, 429, 500, 502, 503, 504, 529. **Not retryable:** other 4xx (400, 401, 403, 404, 413, 422), malformed response, budget exceeded, provider disabled, cancellation. A 429 `Retry-After` is honoured when it fits the deadline. `guardrails/rate_limiter.py` (tenacity) is deleted and `tenacity` leaves `requirements.txt`; the Spec 06 test that requires it is updated. | Keep tenacity (sync decorator, no deadline, F-26). Retry malformed JSON once (doubles cost for a model that ignores JSON mode; the fallback content already exists). |
| OD-57 | Cancellation | `asyncio` cancellation passes through both gateways: the HTTP request is aborted, no retry follows, an audit record with outcome `cancelled` is written, and `CancelledError` is re-raised. Cancelling a worker closes its MCP session. | A custom cancellation token (asyncio already provides one). |
| OD-58 | Rate limits | In-process token bucket per provider, `CJI_LLM_RATE_PER_MIN` (default 30). When empty, the call waits if the wait fits the deadline, otherwise fails as `rate_limited` (retryable class, but no time left). Limits are per server process (as in Spec 07). | Shared limiter (Redis): one process per server today. |
| OD-59 | Budgets | Per call: `max_tokens` = `LLM_MAX_TOKENS` (now actually sent). Per run: `CJI_LLM_RUN_MAX_CALLS` (20), `CJI_LLM_RUN_MAX_TOKENS` (50,000), optional `CJI_LLM_RUN_MAX_COST_USD`. The insight and report workers pass the remaining budget to the LLM tools in a `run_context` argument; each tool result returns the usage; workers keep the running total in a new state key `llm_usage`. Cost is computed only from `CJI_LLM_PRICE_INPUT_PER_MTOK` / `CJI_LLM_PRICE_OUTPUT_PER_MTOK`; a cost cap without prices is a configuration error. When a call would exceed the budget it is not sent; the tool returns its fallback content with code `budget_exceeded`. | A shared budget store across processes (durable run metadata is Spec 09). Built-in price tables (prices change; wrong numbers are worse than none). |
| OD-60 | Types | `LLMRequest`, `LLMResult`, `Usage`, `RunContext`, `LLMCallInfo` (pydantic, frozen) and an error hierarchy `GatewayError(code, retryable)` with `LLMTimeout`, `RateLimited`, `ProviderUnavailable`, `ProviderRejected` (4xx, incl. `model_not_found`, `auth_failed`), `MalformedResponse`, `BudgetExceeded`, `LLMDisabled`, `ToolTimeout`, `ToolFailed`, `MalformedToolResult`. `generate_insight` returns `{"insight": {...}, "llm": LLMCallInfo}`; `generate_narrative` keeps `narrative` and `generated_at` and adds `llm`. Workers remove `llm` before the existing domain contract checks, so `domain/insights.py` is unchanged. | Put call metadata inside the insight dict (it would flow into ChromaDB and the report). |
| OD-61 | Correlation | `correlation_id` = the LangGraph `thread_id` (`main.py` already creates one per run). Workers read it from the `config` argument LangGraph passes to nodes; when absent (direct calls, tests) a UUID4 is generated per worker call. Client side: a context variable read by `ToolGateway`. Server side: the `run_context` tool argument. Every gateway call gets its own `call_id`. | MCP request `_meta` (depends on mcp/FastMCP version support; harder to test). |
| OD-62 | Audit | One record per LLM call and per tool call: time, kind, correlation_id, call_id, worker, service, tool or purpose, provider, model, outcome (`ok`, `fallback`, `error`, `cancelled`), error code, retryable, attempts, latency_ms, input/output tokens, cost, prompt size in characters, argument key names. **Never:** prompt or response text, argument values, keys, user/session/event ids, URLs. Sinks: the `cji.audit` logger (one JSON line) and an append-only JSONL file per process, `<CJI_DATA_DIR>/audit/<service>.jsonl` (`CJI_AUDIT_DIR` overrides; `off` disables the file). `data/audit/` is gitignored. | A database table (schema change; Spec 09). Storing hashed prompts (not needed for the stated acceptance criteria). |
| OD-63 | Redaction and guardrails | Pre-LLM `sanitise_for_llm` stays on the insight input and is also applied to each insight passed to the narrative. Post-LLM `validate_llm_output` stays on insights; narratives are stripped, capped at 4,000 characters, and fall back when empty. Ingestion inputs are unchanged (F-27 is for the owner to decide). Gateway error messages are built from codes and HTTP status only, never from exception text or response bodies; a scrubber removes configured secret values and `Authorization` / `x-api-key` values from anything that reaches logs, exceptions or audit. Workers record gateway errors by code (fixes F-30 for these paths). | Redact by regex after the fact (misses provider formats). |
| OD-64 | Test doubles | `integrations/testing.py`: `ScriptedTransport` (an `httpx.MockTransport` returning scripted responses or exceptions per call), `ManualClock` and a recording `sleep` (no real waits), `MemoryAuditSink`, `FakeToolSession`. No randomness, no network, no real sleeps. An autouse test fixture makes any real provider HTTP call fail. | Live-provider tests (non-deterministic, cost money). |
| OD-65 | Friction engine | `friction_engine_server.py` imports nothing from `integrations` or LLM code; its tool calls from `friction_worker` go through `ToolGateway` (timeout, audit) only. An import-graph test enforces this. | — |
| OD-66 | MCP tool calls | Per-call timeout `CJI_MCP_CALL_TIMEOUT_S` (default 150 s: above the 90 s LLM deadline plus margin). Opening a session is retried up to 2 attempts on connection errors; tool calls themselves are **not** retried (several have side effects: `generate_*` cost money, `save_insight` writes; idempotent workers are Spec 09). A non-JSON or `isError` tool result raises `MalformedToolResult` instead of becoming `{"text": ...}`. | Retry read-only tools (needs a per-tool idempotency registry; Spec 09). |

## 3. Requirements
| ID | Requirement | Change visible to callers |
|---|---|---|
| AG-01 | All LLM HTTP calls go through `LLMGateway`; no module outside `integrations/` imports `requests` or `httpx` for LLM providers. | — |
| AG-02 | All workflow MCP calls go through `ToolGateway`; `tools.mcp_client.mcp_session` / `call_tool` keep their names and signatures. | Non-JSON tool output now raises |
| AG-03 | Provider and model per OD-54; startup and `python -m settings check` report mismatches. | Ingestion provider; allow-list removed |
| AG-04 | Timeouts, deadline, retries and classification per OD-56. | 4xx no longer retried |
| AG-05 | Cancellation per OD-57. | — |
| AG-06 | Rate limit per OD-58. | — |
| AG-07 | Per-call and per-run budgets per OD-59; `llm_usage` in workflow state. | New tool argument and result fields |
| AG-08 | Typed requests, results and errors per OD-60. | Tool result envelope |
| AG-09 | Correlation ids per OD-61. | — |
| AG-10 | Audit records per OD-62. | New `data/audit/` files |
| AG-11 | Guardrails preserved and redaction per OD-63. | — |
| AG-12 | Deterministic test doubles per OD-64. | — |
| AG-13 | Friction engine independence per OD-65. | — |
| AG-14 | New settings in `settings/load.py` `KNOWN_KEYS`, `.env.example`, README: `CJI_LLM_PROVIDER`, `CJI_LLM_DEADLINE_S`, `CJI_LLM_RATE_PER_MIN`, `CJI_LLM_RUN_MAX_CALLS`, `CJI_LLM_RUN_MAX_TOKENS`, `CJI_LLM_RUN_MAX_COST_USD`, `CJI_LLM_PRICE_INPUT_PER_MTOK`, `CJI_LLM_PRICE_OUTPUT_PER_MTOK`, `CJI_MCP_CALL_TIMEOUT_S`, `CJI_AUDIT_DIR`. | — |

## 4. Non-goals
- Parallel insight generation (R-13; stays sequential).
- Durable run records, resumable runs, idempotent workers (Spec 09).
- Changing prompts, the insight schema, report HTML, or the friction scores.
- Ingestion prompt content, including F-12 (the quality check reusing the mapping prompt): routed through the
  gateway with its own `purpose`, prompt unchanged.

## 5. Acceptance criteria (Prompt 7)
1. The insight and report workers use the gateway (`ToolGateway` for their tool calls; their LLM tools use `LLMGateway`).
2. Timeout, retry, budget, cancellation and malformed-response tests pass.
3. Audit records contain correlation metadata and no sensitive payloads.
