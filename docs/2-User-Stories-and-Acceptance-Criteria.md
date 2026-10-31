> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# User Stories and Acceptance Criteria
## Customer Journey Intelligence (CJI)

**Version:** 2.0
**Date:** March 2026
**Status:** Active Development

---

## Table of Contents

1. [Epic Structure Overview](#1-epic-structure-overview)
2. [Epic 1: Demo Mode Operation](#2-epic-1-demo-mode-operation)
3. [Epic 2: Realtime Mode Setup](#3-epic-2-realtime-mode-setup)
4. [Epic 3: Friction Discovery](#4-epic-3-friction-discovery)
5. [Epic 4: Human Oversight and Approval](#5-epic-4-human-oversight-and-approval)
6. [Epic 5: Reporting and Delivery](#6-epic-5-reporting-and-delivery)
7. [Epic 6: Agent Resilience and Correctness](#7-epic-6-agent-resilience-and-correctness)
8. [Epic 7: Dashboard and UX](#8-epic-7-dashboard-and-ux)
9. [Cross-Cutting Acceptance Gates](#9-cross-cutting-acceptance-gates)

---

## 1. Epic Structure Overview

| Epic | Description | Personas | Priority |
|---|---|---|---|
| Epic 1 | Demo Mode Operation | Developer (Builder) | P0 |
| Epic 2 | Realtime Mode Setup | Client Developer, Admin | P0/P1 |
| Epic 3 | Friction Discovery | PM, UX Analyst, IT Developer | P0 |
| Epic 4 | Human Oversight and Approval | Product Manager | P0 |
| Epic 5 | Reporting and Delivery | CIO, Product Manager | P0 |
| Epic 6 | Agent Resilience | Developer (Builder) | P0 |
| Epic 7 | Dashboard and UX | All Personas | P0/P1 |

---

## 2. Epic 1: Demo Mode Operation

### US-001: Synthetic Session Generation

**As a** developer,
**I want to** generate 2,000 synthetic user sessions with realistic friction patterns across 6 journey steps,
**So that** I can test and demonstrate the full analysis pipeline without requiring a live website.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-001-01 | Running `python main.py --mode demo --generate-data` creates a file at `data/events.parquet` | File system check |
| AC-001-02 | The generated Parquet file contains ≥ 2,000 unique user_id values | DuckDB COUNT(DISTINCT user_id) |
| AC-001-03 | The generated data covers all 6 journey steps: landing_page, sign_up_form, email_verification, profile_setup, first_action, completion | DuckDB SELECT DISTINCT step_id |
| AC-001-04 | email_verification step has abandon_rate ≥ 40% when queried | DuckDB computed metric query |
| AC-001-05 | email_verification step has avg_dwell ≥ 120 seconds | DuckDB aggregation |
| AC-001-06 | email_verification step has error_rate ≥ 30% | DuckDB aggregation |
| AC-001-07 | Events include all required types: page_view, error, rage_click, abandon, step_complete | DuckDB DISTINCT event_type |
| AC-001-08 | Error events include metadata with error_code and retry_count fields | Inspect sample events |
| AC-001-09 | Generation completes in under 30 seconds | Timed execution |
| AC-001-10 | Running generation twice with same seed produces identical files | md5sum comparison |
| AC-001-11 | All events conform to the unified schema: event_id, user_id, journey_id, step_id, event_type, timestamp, duration_ms, metadata | Schema validation |

**Edge Cases:**
- Running --generate-data when data/events.parquet already exists: file is overwritten without error
- Running with 0 sessions: raises ValueError with descriptive message
- Disk full: raises IOError with path information

---

### US-002: End-to-End Demo Pipeline with Auto-Approve

**As a** developer,
**I want to** run the full analysis pipeline with `--auto-approve` in a single command,
**So that** I can verify the system end-to-end quickly without manual intervention.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-002-01 | `python main.py --mode demo --run --auto-approve` exits with code 0 | Exit code check |
| AC-002-02 | Command creates a file matching pattern `reports/cji_report_*.html` | Glob check |
| AC-002-03 | The LangGraph graph traverses all 4 workers: data_worker → friction_worker → insight_worker → report_worker | Console output inspection |
| AC-002-04 | No unhandled exceptions are raised during the run | No traceback in output |
| AC-002-05 | At least 1 friction score ≥ 60 appears in the output | Console output |
| AC-002-06 | At least 1 insight with category field appears in the output | Console output |
| AC-002-07 | Reports directory is created automatically if it does not exist | Test without pre-existing reports/ |
| AC-002-08 | Pipeline completes in under 3 minutes (excluding LLM call time) | Timed execution |
| AC-002-09 | state["errors"] list is empty on successful run | State inspection |
| AC-002-10 | Thread ID is printed to console and is a valid UUID | UUID format check |

**Edge Cases:**
- Running --run without prior --generate-data: clear error message "Run --generate-data first"
- LLM API unavailable: system falls back gracefully, insight has category="unknown"
- MAX_AGENT_ITERATIONS reached: graph ends with safety cutoff message, partial report produced

---

### US-003: LLM Provider Swap via Environment Variable

**As a** developer,
**I want to** swap the LLM provider by changing a single environment variable,
**So that** the system works regardless of which API key is available.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-003-01 | Setting `LLM_MODEL=ollama/llama3.1` and running pipeline uses Ollama | LangSmith trace or console output |
| AC-003-02 | Setting `LLM_MODEL=gpt-4o` uses OpenAI GPT-4o | Provider in LiteLLM trace |
| AC-003-03 | Setting `LLM_MODEL=claude-sonnet-4-6` uses Anthropic Claude | Provider in LiteLLM trace |
| AC-003-04 | No code changes are needed between provider swaps — only .env change | Code review |
| AC-003-05 | Wrong LLM_MODEL value produces a clear LiteLLM error, not a crash in agent code | Error message check |
| AC-003-06 | All insight fields are populated regardless of provider (JSON fallback covers failures) | Inspect insight output |

**Edge Cases:**
- Ollama not installed: LiteLLM raises ConnectionError, fallback dict produced
- API key missing for chosen provider: LiteLLM AuthenticationError, fallback dict produced

---

## 3. Epic 2: Realtime Mode Setup

### US-004: One-Line Website Embed

**As a** client developer,
**I want to** paste a single HTML snippet into my website's `<head>` to enable CJI tracking,
**So that** no custom instrumentation or SDK integration work is needed.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-004-01 | `python tracker/snippet_generator.py --journey onboarding --host http://localhost:8000` produces a file named `embed_snippet.html` | File existence check |
| AC-004-02 | The embed snippet contains a correctly formatted `window.CJI_CONFIG` object with apiKey, journeyId, endpoint, and stepMap | File content inspection |
| AC-004-03 | Pasting the embed snippet into a blank HTML page and opening it in a browser does not throw JavaScript errors | Browser dev console check |
| AC-004-04 | Upon page load with the snippet, tracker.js loads asynchronously (async attribute present) | HTML inspection |
| AC-004-05 | A page_view event is sent to the collector within 2 seconds of the page loading | DuckDB live_events query |
| AC-004-06 | tracker.js loads without blocking page render (async loading) | Browser Network tab waterfall |
| AC-004-07 | tracker.js works in Chrome, Firefox, Safari, and Edge | Manual browser test |
| AC-004-08 | No JavaScript errors are thrown on pages where window.CJI_CONFIG is missing (script exits gracefully) | Browser console |

**Edge Cases:**
- stepMap path not matching current URL: step_id = "unknown_step"
- API key not yet in api_keys table: events returned 401, tracked in browser console as warning
- localStorage unavailable (private browsing): UUID generated in-memory without error

---

### US-005: React/SPA Hook Integration

**As a** client developer building a Next.js SPA,
**I want to** use a generated React hook for CJI tracking,
**So that** tracking works correctly across client-side navigation without full page reloads.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-005-01 | `snippet_generator.py` generates a `useCJITracker.js` file | File existence check |
| AC-005-02 | The hook listens for Next.js router events and fires step_complete + page_view on navigation | Code inspection |
| AC-005-03 | Each SPA route change creates exactly one step_complete event for the departing step and one page_view for the new step | DuckDB event sequence query |
| AC-005-04 | No duplicate page_view events are fired on initial page load | DuckDB COUNT check |
| AC-005-05 | The hook correctly fires step_complete with dwell_ms computed from time-on-page | DuckDB duration_ms inspection |

**Edge Cases:**
- Rapid back-forward navigation: events batched and sent without duplication
- Route changes faster than 50ms timeout: step_complete records only partial dwell time

---

### US-006: Client API Key Management

**As a** system administrator,
**I want to** generate a client-specific API key in under 30 seconds,
**So that** each client's data is isolated and I can revoke access independently.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-006-01 | `snippet_generator.py` generates a key in format `cji_live_{32 hex chars}` (36 chars total) | Key format regex check |
| AC-006-02 | Each run generates a different key (no repeats) | Run twice, compare |
| AC-006-03 | Generated key is stored in `api_key.json` in the output directory | File content check |
| AC-006-04 | POST /admin/api-keys with valid CJI_ADMIN_KEY creates a new key in api_keys table | DuckDB query after create |
| AC-006-05 | Setting active=FALSE on a key (DuckDB UPDATE) causes subsequent events with that key to receive 401 | Curl test after deactivation |
| AC-006-06 | POST /admin/api-keys with missing or wrong CJI_ADMIN_KEY returns 403 | HTTP status check |
| AC-006-07 | Dev key `cji_dev_localtest` is inserted automatically when collector starts for the first time | DuckDB api_keys query on fresh start |
| AC-006-08 | Key generation uses secrets.token_hex(16), not random.randint | Code review |

**Edge Cases:**
- Creating a duplicate key (same value already in table): INSERT OR IGNORE used, 200 returned
- Deactivated key reactivated: set active=TRUE, events immediately accepted

---

### US-007: Live Event Collection and Visibility

**As an** analyst,
**I want to** see that tracker.js events are arriving in the DuckDB live_events table after embedding on a test site,
**So that** I can confirm the realtime data pipeline is working before running analysis.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-007-01 | Events from tracker.js appear in DuckDB live_events table within 10 seconds of browser action | DuckDB SELECT COUNT (*) comparison before/after |
| AC-007-02 | GET /live/stats returns per-step event counts | Curl /live/stats |
| AC-007-03 | GET /health returns {"status": "ok", "live_events_count": N} where N increases as events arrive | Curl before and after page views |
| AC-007-04 | Events in live_events have received_at column set to server timestamp | DuckDB inspection |
| AC-007-05 | verify_tracker.py (from snippet generator) sends a test event and reports success | Script output |
| AC-007-06 | SSE stream from GET /live/feed shows new events in real time | curl --no-buffer /live/feed |

---

## 4. Epic 3: Friction Discovery

### US-008: Per-Step Friction Scores

**As a** Product Manager,
**I want to** see friction scores for every journey step on one screen,
**So that** I can immediately identify the most problematic step without analysing raw data.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-008-01 | All 6 journey steps have a friction score computed (0–100) | State inspection / dashboard view |
| AC-008-02 | Scores are displayed sorted descending (highest friction first) | score_all_steps output |
| AC-008-03 | email_verification step has score ≥ 60 (critical) in demo mode | score assertion |
| AC-008-04 | landing_page step has score < 60 (non-critical) in demo mode | score assertion |
| AC-008-05 | Each score has an is_critical flag matching the FRICTION_SCORE_THRESHOLD (60) rule | FrictionScore.is_critical check |
| AC-008-06 | Each score has a confidence value between 0.0 and 0.98 | Range assertion |
| AC-008-07 | Each score has a non-empty signals list when score > 0 | signal list length check |
| AC-008-08 | Scores are reproducible — same input always produces same score | Run twice, compare |

---

### US-009: Signal-Level Friction Explanation

**As a** UX Analyst,
**I want to** understand which specific signals (rage clicks, high dwell time, errors) are driving friction at each step,
**So that** I can design targeted UX fixes for the precise issue.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-009-01 | Signals appear as exact strings from the defined set: high_drop_off, critical_drop_off, frequent_errors, extended_hesitation, severe_confusion, repeated_retries, rage_clicks_detected | String equality check |
| AC-009-02 | email_verification step signal includes "critical_drop_off" in demo mode | Signal list check |
| AC-009-03 | Steps with abandon > 50% have both "high_drop_off" and "critical_drop_off" signals | Logic check |
| AC-009-04 | Steps with dwell > 120,000ms have both "extended_hesitation" and "severe_confusion" signals | Logic check |
| AC-009-05 | correlate_signals returns signal_frequency counting how many steps trigger each signal | Output structure check |
| AC-009-06 | correlate_signals identifies systemic_signals (signals appearing in 2+ steps) | Output structure check |
| AC-009-07 | Zero-input metrics produce zero score and empty signals list | Unit test |

---

### US-010: Root Cause Categorisation

**As an** IT Developer,
**I want to** have friction issues categorised as UX, data, system, or process,
**So that** tickets are automatically routed to the correct team without investigation overhead.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-010-01 | Each insight has a category field with value from: "UX", "data", "system", "process", "unknown" | Schema validation |
| AC-010-02 | Category "unknown" is used only when LLM fails to produce a valid response | Fallback scenario test |
| AC-010-03 | The LLM system prompt explicitly defines the four categories and their meanings | Prompt code review |
| AC-010-04 | Category is preserved through save_insight → ChromaDB → search_insights correctly typing | Round-trip test |
| AC-010-05 | Each insight has an evidence list with at least one supporting data point | insight["evidence"] length check |
| AC-010-06 | Each insight has a suggested_fix field with 1-2 sentences | Length and content check |
| AC-010-07 | Each insight has a fix_effort field: "low", "medium", or "high" | Enum validation |

---

## 5. Epic 4: Human Oversight and Approval

### US-011: Review Gate Before Report Generation

**As a** Product Manager,
**I want to** review AI-generated insights before they are included in the final CIO report,
**So that** I can correct any incorrect inferences and maintain quality control.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-011-01 | After insight_worker completes, graph pauses and prints a "waiting for approval" message | Console output inspection |
| AC-011-02 | `graph.get_state(config).next` returns `("report_worker",)` after pause — confirming paused state | State inspection |
| AC-011-03 | report_worker does NOT execute without human approval | Run without --approve → no report file created |
| AC-011-04 | The thread ID is displayed so the user can reference it for --approve | Console output |
| AC-011-05 | Graph state is checkpointed to SQLite during pause — process can be killed and resumed | Kill + resume test |
| AC-011-06 | Running `python main.py --approve --thread-id <UUID>` resumes from checkpoint and runs report_worker | Report file created after approve |
| AC-011-07 | human_approved field starts as False and is only set True via graph.update_state() | State field check |
| AC-011-08 | Running --auto-approve sets human_approved=True at graph initialization, skipping pause | One-command test |

**Edge Cases:**
- Approving a thread that doesn't exist: KeyError with descriptive message
- Approving a thread where report already generated: idempotent — no second report created
- Approving a thread mid-data_worker run: error returned, approval only valid after insights are present

---

### US-012: Re-run Without Losing State

**As a** Product Manager,
**I want to** reject an analysis and trigger a re-run without losing the original thread's state,
**So that** I can investigate data anomalies without starting over from scratch.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-012-01 | Starting a new run with a new thread_id produces fresh state | thread_id comparison |
| AC-012-02 | Old thread checkpoint remains in SQLite after a new run is started | SQLite inspection |
| AC-012-03 | Resuming an old thread via --thread-id shows the old insights, not new ones | Thread ID check in state |
| AC-012-04 | worker_statuses list shows full history of completed workers for a thread | State inspection |
| AC-012-05 | errors list is preserved across checkpoint resumes | State after restart check |

---

## 6. Epic 5: Reporting and Delivery

### US-013: CIO-Ready Executive Summary

**As a** CIO,
**I want to** receive a 3-paragraph executive summary that explains business impact, root causes, and prioritised recommendations,
**So that** I can brief the board without technical preparation.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-013-01 | The generate_narrative tool produces exactly 3 paragraphs | Paragraph split + count |
| AC-013-02 | Paragraph 1 describes business impact (quantified friction, user loss) | Content review |
| AC-013-03 | Paragraph 2 describes root causes by category (UX/data/system/process) | Content review |
| AC-013-04 | Paragraph 3 provides prioritised, actionable recommendations | Content review |
| AC-013-05 | The narrative uses business language — no technical jargon (score, DuckDB, MCP, etc.) | Language review |
| AC-013-06 | The narrative mentions journey name, number of critical steps, and average friction score | Content presence check |
| AC-013-07 | Narrative is generated even if LLM is unavailable (fallback template produced) | Disconnect LLM, check output |

---

### US-014: Downloadable Self-Contained HTML Report

**As a** Product Manager,
**I want to** download a self-contained HTML report I can share via email,
**So that** stakeholders can view it without dashboard access.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-014-01 | export_report produces a file at `reports/cji_report_{journey}_{YYYYMMDD_HHMMSS}.html` | File existence and name format |
| AC-014-02 | Opening the HTML file locally in a browser shows all content without a server | Manual open + inspect |
| AC-014-03 | The report contains a friction bar chart with colour-coded bars (red/amber/green) | Visual inspection |
| AC-014-04 | The report contains a funnel drop-off bar chart in blue | Visual inspection |
| AC-014-05 | The report header shows mode badge (DEMO or LIVE) | HTML content search |
| AC-014-06 | The report includes an insights table with step, issue, category, priority, effort, fix columns | Table row count |
| AC-014-07 | The report includes the 3-paragraph executive narrative | Paragraph presence check |
| AC-014-08 | The report includes journey name, timestamp, and model name in footer | Footer content check |
| AC-014-09 | Chart.js CDN renders charts (requires internet) or falls back to static image | CDN test |
| AC-014-10 | Report file is ~100KB in size (not bloated) | File size check |
| AC-014-11 | Dashboard shows a download button for the report after approval | UI inspection |

---

## 7. Epic 6: Agent Resilience and Correctness

### US-015: Worker Fault Isolation

**As a** developer,
**I want to** ensure that a single worker failure does not crash the entire analysis pipeline,
**So that** partial results are always delivered and the system is production-grade.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-015-01 | An exception thrown inside data_worker is caught and appended to state["errors"], not propagated | Inject exception, check errors list |
| AC-015-02 | After data_worker exception, supervisor is still called with next_worker="supervisor" | State inspection |
| AC-015-03 | An exception thrown inside insight_worker still produces a report if data and friction scores exist | Inject exception, check report |
| AC-015-04 | All workers return next_worker="supervisor" in both success and failure paths | Code review + test |
| AC-015-05 | call_tool() re-raises as RuntimeError so workers' outer try/except catches it | Unit test with mock MCP failure |
| AC-015-06 | The Supervisor safety cutoff at MAX_AGENT_ITERATIONS=20 stops infinite loops | Simulate loop, check cutoff message |
| AC-015-07 | Supervisor safety cutoff adds error message to state["errors"] | errors list inspection |

**Edge Cases:**
- MCP server process dies mid-conversation: RuntimeError caught, error in state
- LiteLLM rate limit hit: tenacity retries 3 times with exponential backoff, then fallback dict

---

### US-016: Supervisor Routing Correctness

**As a** developer,
**I want to** ensure the supervisor always routes to the correct worker in the correct order,
**So that** the analysis pipeline produces consistent, reliable results.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-016-01 | First supervisor call with empty state routes to data_worker | State flow trace |
| AC-016-02 | Second supervisor call with event_summary but no friction_scores routes to friction_worker | State flow trace |
| AC-016-03 | Third supervisor call with friction_scores but no insights routes to insight_worker | State flow trace |
| AC-016-04 | Fourth supervisor call with insights and human_approved=False routes to END (pause) | State snapshot.next inspection |
| AC-016-05 | After setting human_approved=True, supervisor routes to report_worker | Resume + trace |
| AC-016-06 | Supervisor call with report_path set routes to END (complete) | State inspection |
| AC-016-07 | Supervisor is a synchronous (not async) function | Code review |
| AC-016-08 | route() function reads state["next_worker"] and returns it directly | Code review |
| AC-016-09 | LLM fallback in supervisor is only called when none of the deterministic conditions match | Code coverage check |
| AC-016-10 | LLM fallback output is sanitised against VALID_NEXT set before use | Code review |

---

### US-017: JSON Fallback for LLM Failures

**As a** developer,
**I want to** ensure that even when the LLM returns malformed JSON, the system produces a usable insight,
**So that** the pipeline never fails due to LLM output format issues.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-017-01 | If LLM returns malformed JSON, generate_insight returns a valid dict with all required keys | Mock malformed LLM response |
| AC-017-02 | Fallback insight has category="unknown" and fix_effort="medium" | Fallback dict inspection |
| AC-017-03 | Fallback insight's title is "Friction at {step_id}" | Title field check |
| AC-017-04 | Fallback insight's root_cause contains up to 300 chars of raw LLM output (or "Analysis unavailable") | root_cause check |
| AC-017-05 | JSON markdown fences (```json```) are stripped before json.loads() | Unit test with fenced response |
| AC-017-06 | Missing required fields in LLM JSON response triggers fallback, not KeyError | Unit test |
| AC-017-07 | Fallback is applied after every LLM call — no exception propagates | Code review |

---

## 8. Epic 7: Dashboard and UX

### US-018: Mode Toggle in Dashboard

**As a** Product Manager,
**I want to** switch between demo and realtime modes from the dashboard,
**So that** I can demonstrate the system in both scenarios from a single interface.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-018-01 | Dashboard shows radio toggle: "demo" | "realtime" | UI inspection |
| AC-018-02 | Switching mode clears thread_id and state_snap (fresh state) | Session state inspection |
| AC-018-03 | Switching mode sets CJI_MODE environment variable before re-running | os.environ check |
| AC-018-04 | Switching mode calls st.rerun() to re-execute the script from top | Streamlit behavior |
| AC-018-05 | In realtime mode, dashboard shows collector API status: online ✓ or offline ✗ | UI indicator |
| AC-018-06 | In realtime mode, collector health check has 2-second timeout (non-blocking) | Network inspection |
| AC-018-07 | asyncio.run() is NEVER called inside dashboard code | Code review |

---

### US-019: Friction Charts and Metrics

**As a** Product Manager,
**I want to** see friction scores visualised as bar charts alongside key metrics,
**So that** the severity of each step is immediately clear at a glance.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-019-01 | Dashboard shows 4 metric cards: steps analysed, critical steps, avg friction score, insights count | UI inspection |
| AC-019-02 | Friction bar chart shows all 6 steps sorted by score descending | Chart inspection |
| AC-019-03 | Bars are colour-coded: red (≥70), amber (50–69), green (<50) | Colour check |
| AC-019-04 | Funnel drop-off chart shows all 6 steps in journey order with drop-off % | Chart inspection |
| AC-019-05 | Charts render within 5 seconds of analysis completion | Performance check |
| AC-019-06 | Charts are built with Plotly (not static images) | Code inspection |

---

### US-020: Insight Review Panel

**As a** UX Analyst,
**I want to** expand each insight to see root cause, fix recommendation, effort, and score,
**So that** I can review AI findings in context before approving the final report.

**Acceptance Criteria:**

| ID | Criterion | Test Method |
|---|---|---|
| AC-020-01 | Dashboard shows one expandable panel per insight | UI count |
| AC-020-02 | Expanded panel shows: title, root_cause, category, evidence list, fix, effort, priority, score | All fields visible |
| AC-020-03 | Panel label includes step_id and priority (e.g., "[P1] email_verification") | Label text check |
| AC-020-04 | Approve button appears when insights exist and report has not been generated | UI state check |
| AC-020-05 | Clicking Approve calls graph.update_state with human_approved=True | State change check |
| AC-020-06 | After approval, report_worker runs and report path appears in UI | File path displayed |
| AC-020-07 | Download button is shown after report is generated | UI button presence |

---

## 9. Cross-Cutting Acceptance Gates

These must be satisfied across all epics for the PoC to pass evaluation.

### Gate 1: Zero-Network Test Suite

| ID | Criterion |
|---|---|
| CG-01 | `pytest tests/ -v` runs without any network connection |
| CG-02 | `pytest tests/ -v` runs without any API key in environment |
| CG-03 | `pytest tests/ -v` completes in under 30 seconds |
| CG-04 | All friction engine tests pass (minimum 12 tests) |
| CG-05 | All collector model validation tests pass (minimum 6 tests) |
| CG-06 | All synthetic data tests pass (minimum 4 tests) |
| CG-07 | Any sys.path.insert(0, "..") is present at top of every test file |

### Gate 2: Schema Compliance

| ID | Criterion |
|---|---|
| CG-08 | Every browser event sent by tracker.js has all 10 required fields |
| CG-09 | Every FrictionScore dict has all 9 required keys |
| CG-10 | Every Insight dict has all 11 required keys |
| CG-11 | Every WorkerStatus dict has all 3 keys: worker, status, message |
| CG-12 | All ChromaDB metadata values are strings (not int, float, or list) |

### Gate 3: Security Baseline

| ID | Criterion |
|---|---|
| CG-13 | No API key appears in any committed code file |
| CG-14 | .env is listed in .gitignore |
| CG-15 | API keys generated with secrets.token_hex(16) (verifiable by code review) |
| CG-16 | Every collector POST validates API key before writing any events |
| CG-17 | User IDs are UUID v4 format only — no email or name patterns |
| CG-18 | No URL query parameters appear in stored event URLs |

### Gate 4: Configuration Compliance

| ID | Criterion |
|---|---|
| CG-19 | All paths and thresholds are in config.py — not hardcoded in business logic |
| CG-20 | CJI_MODE env var controls mode — no other switch needed |
| CG-21 | LLM_MODEL env var is the only change required to switch providers |
| CG-22 | All config.py values have documented defaults in .env.example |
| CG-23 | data/ and reports/ directories are created in config.py at import time |

### Gate 5: Architecture Compliance

| ID | Criterion |
|---|---|
| CG-24 | agents/ code never imports from mcp_servers/ directly (only through tools/mcp_client.py) |
| CG-25 | No direct anthropic.Anthropic() calls exist in production code |
| CG-26 | Workers are async functions; supervisor is a synchronous function |
| CG-27 | No asyncio.run() is called inside dashboard.py |
| CG-28 | Every MCP server is independently runnable as python mcp_servers/server.py |
| CG-29 | graph.update_state() for human approval always includes as_node="supervisor" |
| CG-30 | All initial state keys from CJIState TypedDict are present in initial_state dict |
