# Spec 08 — AI Gateway: Tasks

Sequential. `[x]` means evidence exists. No commits or pushes: each step is recorded as a patch file in `evidence/`.

**Environment:** protected environment (dummy LLM keys, dead proxy, dead database URLs). No test calls a real
provider; an autouse fixture (`tests/conftest.py::_no_real_llm_calls`) fails any provider HTTP call that is not
scripted.

**Status:** Implemented 2026-10-28 with the default decisions OD-53 to OD-66 (approved: "implement spec 08").
Final gate run 2026-10-28T05:44–05:50 (`evidence/gate-results.txt`, `evidence/final-numbers.txt`), post-gate
recheck in `evidence/gate-recheck-eol.log`.

## Tasks

- [x] **T0 Prepare.** `pre-spec08-tracked.patch` (353,972 bytes), `pre-spec08-untracked/` (32 files plus
  `MANIFEST.txt`); baseline = Spec 07 gate (583/594, F-01).
- [x] **T1 Tests.** `tests/test_gateway.py`, 80 tests (design §7). **Not done failing-first:** the old code had no
  gateway module to run them against, so the tests were written alongside `integrations/` and there is no
  "before" run. The scripted transport and manual clock make every test deterministic.
- [x] **T2 Settings.** `CJI_LLM_PROVIDER`, `CJI_LLM_TIMEOUT_S`, `CJI_LLM_DEADLINE_S`, `CJI_LLM_RETRY_*`,
  `CJI_LLM_RATE_PER_MIN`, `CJI_LLM_RUN_MAX_*`, `CJI_LLM_PRICE_*_PER_MTOK`, `CJI_AUDIT_DIR`,
  `CJI_MCP_CALL_TIMEOUT_S`; provider/model mismatch and "cost cap without prices" are configuration errors.
- [x] **T3 Gateway core.** `integrations/` (`types`, `errors`, `policy`, `providers`, `llm`, `audit`, `context`,
  `usage`, `testing`); `mypy --strict` and bandit clean.
- [x] **T4 Tool gateway.** `integrations/tools.py`; `tools/mcp_client.py` keeps `mcp_session` / `call_tool` /
  `ping_all_servers` as thin wrappers.
- [x] **T5 Servers.** `generate_insight`, `generate_narrative`, `detect_schema`, `validate_transformed_data` are
  async and call `LLMGateway`; guardrails and fallbacks kept; `guardrails/rate_limiter.py` deleted (copy in
  `evidence/removed/`); `tenacity` replaced by `httpx` in `requirements.txt`.
- [x] **T6 Workers and state.** `with_run` on every graph node (correlation id = LangGraph `thread_id`),
  `run_context` argument, `llm_usage` state key, `_error_text` (F-30); affected tests updated; README,
  `.env.example`, `.gitignore` (`data/audit/`).
- [x] **T7 Gate.** Below. Change set: `spec08-tracked.patch` (380,237 bytes) and `spec08-new-files/` (17 files
  with `MANIFEST.txt`).

## Gate (2026-10-28, protected environment)

| Check | Result | Spec 07 |
|---|---|---|
| Full suite (`-m "not integration"`) | 663/674 pass; the 11 failures are the F-01 set, identical | 583/594 |
| Tests added / removed | +81 / −1 (`test_requirements_declare_tenacity`, replaced by the `httpx` check) | |
| Spec 08 test set (`test_gateway.py` plus the affected suites) | 424/424 | |
| Collector smoke (Spec 07 regression) | pass | 16/16 |
| Golden snapshot | identical to Spec 07 | identical |
| ruff (whole tree) | 113 findings | 120 |
| ruff on new code (`integrations/`, `tests/test_gateway.py`) | All checks passed | |
| mypy (whole tree) | Found 34 errors in 13 files (checked 81 source files) | 42 in 15 (70) |
| mypy `--strict` integrations / repositories | no issues (11 files) / no issues (5 files) | |
| bandit integrations | no findings | |
| Static compare vs Spec 01 | no changed file worse than baseline | |
| `settings check`: groq provider with `claude-sonnet-4-6` | exit 2 with the mismatch message | |
| Demo pipeline, `CJI_LLM_PROVIDER=none` | completes; fallback content, audit code `llm_disabled` | |
| Demo pipeline, groq with dummy key (proxy dead) | completes; fallback content, audit code `provider_unavailable` | |
| Ingest probe | 0 processed, 1 flagged for review, 0 errors | same |
| Mode mismatch, `--help` smokes | as before | |
| Audit files (130 records, 4 files) | allow-listed fields only; no keys, prompts, ids or URLs; every LLM record's correlation id is used by a workflow tool call | |
| `git diff --check` | clean | clean |
| Tracked `data/events.parquet` | unchanged | unchanged |

### Gate findings fixed before the final run

The first gate run (05:22) failed the audit check and showed an ingestion regression. Both are fixed and covered
by tests (`test_gateway.py`, section "Spec 08 gate findings"):

1. **mcp 2.x field name.** The installed `mcp` 2.3.0 calls the error flag `CallToolResult.is_error`; the gateway
   read `isError` (mcp 1.x), so tool error results were reported as `malformed_tool_result`. The gateway now reads
   both, and the test double uses the 2.x name. Test: `test_real_mcp_tool_error_results_are_tool_errors` (parses a
   real `CallToolResult` from the wire format).
2. **Exception groups.** Errors raised inside an MCP session reached workers as "unhandled errors in a TaskGroup
   (1 sub-exception)" (anyio wraps them). `ToolGateway.session` now re-raises the single real error and leaves
   groups with several errors unchanged. Tests: `test_tool_session_unwraps_a_single_error_from_an_exception_group`,
   `test_tool_session_keeps_exception_groups_with_several_errors`.
3. **Ingestion when the LLM fails.** In Spec 07 a failed schema mapping became a low-confidence result (through the
   old client's `{"text": …}` fallback) and the file went to human review. With strict tool results it became a
   workflow error. `detect_schema` now returns an explicit unmapped config (`confidence` 0.0, `llm_error` code,
   not cached), so the file goes to review as before. Test:
   `test_detect_schema_flags_the_file_for_review_when_the_llm_fails`.
4. **Ingestion correlation.** `ingestion_worker` now sends `run_context` to `detect_schema`, so the ingestion LLM
   audit record carries the run's correlation id. Test: `test_ingestion_worker_sends_the_run_context`.

Post-gate fix: the fix scripts had written five files with LF endings (the tree uses CRLF). Restored to CRLF; the
tracked patch is byte-identical (380,237 bytes) and `gate-recheck-eol.log` shows `git diff --check` clean,
`test_gateway.py` + `test_ingestion_intelligence.py` exit 0, ruff and `mypy --strict` on new code clean.

## Acceptance criteria (Prompt 7)

| # | Criterion | Evidence |
|---|---|---|
| 1 | Insight and report workers use the gateway | `test_insight_worker_uses_the_gateway_with_correlation_and_budget`, `test_report_worker_uses_the_gateway_and_unwraps_the_narrative`, `test_mcp_client_wrappers_use_the_gateway`, `test_report_and_insight_servers_have_no_provider_code`, `test_only_the_gateway_talks_to_providers`; both demo pipelines in the gate |
| 2a | Timeout | `test_attempt_timeout_is_retried`, `test_attempt_timeout_is_bounded_by_the_deadline`, `test_deadline_stops_further_attempts`, `test_every_attempt_timing_out_raises_timeout`, `test_tool_call_timeout` |
| 2b | Retry | `test_retryable_statuses_are_retried_up_to_the_attempt_limit`, `test_client_errors_are_not_retried`, `test_retry_after_is_honoured`, `test_backoff_is_exponential_and_capped`, `test_session_open_is_retried_once`, `test_a_failed_call_never_tries_another_provider` |
| 2c | Budget | `test_exhausted_budget_sends_nothing`, `test_cost_is_computed_only_from_configured_prices`, `test_generate_insight_falls_back_when_the_budget_is_exhausted`, `test_cost_cap_needs_prices` |
| 2d | Cancellation | `test_cancellation_during_the_request_stops_the_call`, `test_cancellation_during_backoff_sends_no_further_request`, `test_cancelling_a_tool_call_closes_the_session` |
| 2e | Malformed responses | `test_malformed_llm_responses_are_not_retried` (6 cases), `test_malformed_tool_results_raise` (3 cases), `test_real_mcp_tool_error_results_are_tool_errors` |
| 3 | Audit records carry correlation metadata and no sensitive payloads | `test_llm_audit_record_has_correlation_metadata_and_no_payload`, `test_secret_never_reaches_exceptions_logs_or_audit`, `test_scrub_removes_configured_secrets_and_auth_headers`, `test_worker_error_text_is_scrubbed`; gate audit check over 130 real records |

Other Prompt 7 requirements: guardrails kept (`test_generate_insight_sanitises_input_and_validates_output`,
`test_generate_insight_fallback_is_unchanged`, `test_generate_narrative_post_processing`); deterministic test
doubles (`integrations/testing.py`); friction engine independent (`test_friction_engine_imports_no_ai_code`); no
silent provider switch (`test_a_failed_call_never_tries_another_provider`, `test_model_is_sent_as_configured`).

## Behaviour changes callers can see

- **Ingestion provider.** Ingestion uses `CJI_LLM_PROVIDER` (default groq). It no longer tries Anthropic first and
  then Groq. To keep Anthropic, set `CJI_LLM_PROVIDER=anthropic` with a Claude model.
- **Model strings.** `LLM_MODEL` is sent as configured (a `groq/` prefix is stripped). The old allow-list
  substitution is gone, so a retired model now fails visibly as `model_not_found` (F-25).
- **Tool results.** `generate_insight` returns `{"insight", "llm"}`; `generate_narrative` adds `llm`. Workers
  unwrap both. Non-JSON or error tool results raise `MalformedToolResult` / `ToolFailed` instead of turning into
  `{"text": …}`.
- **Retries.** 4xx responses other than 429 are no longer retried (F-26). MCP tool calls are never retried; opening
  a session is tried twice.
- **`run_context` argument** on the LLM tools (`generate_insight`, `generate_narrative`, `detect_schema`): correlation
  id, worker and remaining budget. Callers that omit it get a fresh correlation id and no run budget.
- **Audit files.** `data/audit/<service>.jsonl` (gitignored), plus the `cji.audit` logger. `CJI_AUDIT_DIR=off`
  disables the files.

## Findings

| ID | Finding | Status |
|---|---|---|
| F-01 | 11 obsolete tests in `test_supervisor.py` | Open (Spec 09, or delete) |
| F-12 | Ingestion quality check reuses the schema-mapping prompt | Routed through the gateway; prompt unchanged |
| F-20, F-21 | `event_id` global key; plain-text tracker keys | Open (later schema Spec) |
| F-22 to F-24 | Spec 07 owner checks (journey names, dev key snippet, per-process limits) | Open (owner) |
| F-25 | `.env` has `LLM_MODEL=llama3-70b-8192`, shut down by Groq on 2025-08-30 | Open (owner): set `LLM_MODEL`, e.g. `openai/gpt-oss-120b` |
| F-26 | Old retry helper retried 4xx (401, 404) | **Fixed** (OD-56) |
| F-27 | Ingestion sends raw source rows to the LLM before PII sanitising | Open (owner decision); unchanged |
| F-28 | `OPENAI_API_KEY` unused | Open; documented |
| F-29 | Default model silently replaced (insight/report) or sent to Anthropic (ingestion) | **Fixed** (OD-54) |
| F-30 | Raw exception text in worker error entries | **Fixed** (OD-63, `_error_text`) |
| F-31 | `mcp` 2.x renamed `isError` to `is_error` | **Fixed** in the gateway (gate finding 1) |

## Rollback

1. `git apply -R .kiro/specs/08-ai-gateway/evidence/spec08-tracked.patch`, then
   `git apply .kiro/specs/08-ai-gateway/evidence/pre-spec08-tracked.patch` (restores the pre-Spec-08 tracked state,
   including `guardrails/rate_limiter.py`).
2. Copy the files in `evidence/pre-spec08-untracked/` back over their paths (settings, tests).
3. Delete the files listed as `new` in `evidence/spec08-new-files/MANIFEST.txt` (`cji_agent/integrations/`,
   `tests/test_gateway.py`).
4. `cji_agent/data/audit/` may be deleted. No database change was made.
