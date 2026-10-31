> **Historical design reference (v2.0, March 2026).** Kept unchanged as design intent. Where it differs from
> the code, the code and `README.md` win. Known divergences: `docs/README.md`.

# Product Requirements Document (PRD)
## Customer Journey Intelligence (CJI) — Dual-Mode System

**Version:** 2.0  
**Date:** March 2026  
**Status:** Active Development  
**Owner:** TCS Internship PoC Team  
**Classification:** Internal — Build Reference

---

## Table of Contents

1. [Product Vision and Intent](#1-product-vision-and-intent)
2. [Problem Statement](#2-problem-statement)
3. [Product Description](#3-product-description)
4. [Dual-Mode Architecture Intent](#4-dual-mode-architecture-intent)
5. [Goals and Success Criteria](#5-goals-and-success-criteria)
6. [Scope](#6-scope)
7. [User Personas](#7-user-personas)
8. [Functional Requirements — Demo Mode](#8-functional-requirements--demo-mode)
9. [Functional Requirements — Realtime Mode](#9-functional-requirements--realtime-mode)
10. [Functional Requirements — Shared (Both Modes)](#10-functional-requirements--shared-both-modes)
11. [Non-Functional Requirements](#11-non-functional-requirements)
12. [User Stories](#12-user-stories)
13. [Feature Specifications](#13-feature-specifications)
14. [Data Requirements](#14-data-requirements)
15. [Integration Requirements](#15-integration-requirements)
16. [Security and Compliance](#16-security-and-compliance)
17. [Constraints and Assumptions](#17-constraints-and-assumptions)
18. [Out of Scope](#18-out-of-scope)
19. [Risks and Mitigations](#19-risks-and-mitigations)
20. [Timeline and Milestones](#20-timeline-and-milestones)
21. [Acceptance Criteria](#21-acceptance-criteria)
22. [Glossary](#22-glossary)

---

## 1. Product Vision and Intent

### 1.1 What CJI Is

Customer Journey Intelligence (CJI) is an **AI-powered analytics platform** that automatically detects, analyses, and explains friction in digital customer journeys. It operates as an intelligent layer on top of user behaviour data — whether synthetic (for testing) or real-time (from live websites) — and uses an agentic AI system to produce actionable insights and CIO-ready reports.

CJI answers the three questions that existing analytics tools cannot:
- **Why** are users abandoning this step — not just that they are?
- **What is the root cause** — UX design flaw, system error, data quality issue, or process logic gap?
- **Which fix delivers the most business value** given limited engineering time?

### 1.2 Core Product Intention

CJI is designed as a **reusable, client-agnostic intelligence layer** that any organisation can deploy on top of their existing digital journey. The same system that analyses a banking onboarding flow can — with a config change — analyse an e-commerce checkout or an insurance claims journey. No new code, no re-architecture.

The product is intentionally **not another dashboard**. Its output is a **ranked, evidence-backed action plan** presented in business language that a CIO, Product Manager, and IT team can all act on immediately.

### 1.3 Technical Philosophy

The system is built on three converging paradigms:

1. **Agentic AI** — an LLM-powered supervisor orchestrates specialised worker agents that reason, call tools, and loop until a complete analysis is produced. This is AI doing work, not answering questions.

2. **Model Context Protocol (MCP)** — four independently deployable MCP servers expose analytical capabilities as typed tool interfaces. The agent consumes these tools. So can a human via CLI, or any future MCP-compatible client.

3. **Dual-Mode Data Layer** — a `tracker.js` browser script collects real-time events from live websites exactly like GA4 or Hotjar. A demo mode uses synthetic data for development, testing, and demonstrations without any live site dependency.

---

## 2. Problem Statement

### 2.1 The Core Problem

Every digital business loses customers silently. Users struggle, hesitate, retry, and abandon without filing complaints. This invisible friction costs revenue, drives support costs, and erodes trust — all without a clear data trail pointing to the cause.

The scale of this problem is large. On a typical onboarding journey:
- 30–50% of users who start never complete
- Most abandonment happens silently — no error, no complaint, no feedback
- When IT teams investigate, they find data fragmented across GA4, Hotjar, Zendesk, and internal logs — none of which talk to each other

### 2.2 Why Existing Tools Fail

| Tool Type | What It Shows | What It Misses |
|---|---|---|
| Google Analytics 4 | Event counts, funnel completion rates | Why users left, what they were trying to do |
| Hotjar / FullStory | Session recordings, heatmaps | Scale, correlation, root cause at step level |
| CRM / Tickets | Customer complaints after escalation | Silent majority who simply left |
| BI Dashboards | Aggregated metrics | Step-level signals, qualitative context |

None of these tools produce a **ranked, evidence-backed fix list**. They show numbers. CJI shows meaning.

### 2.3 The Missing Intelligence Layer

What is missing between raw analytics data and actionable product decisions is an **intelligence layer** that:
- Correlates signals across data sources (behaviour + experience + feedback)
- Scores friction quantitatively with transparent, auditable logic
- Explains root causes in plain English using LLM reasoning
- Ranks fixes by impact-to-effort ratio, not gut feeling
- Produces a CIO-ready narrative, not just a chart

CJI is that layer.

---

## 3. Product Description

### 3.1 Product Summary

CJI is a Python-based system with five major subsystems:

**1. Data Collection Layer**
- Demo mode: Faker-based synthetic event generator that produces realistic journey data
- Realtime mode: `tracker.js` browser script embedded on client websites, sending events to a FastAPI collector

**2. Four MCP Servers (the analytical core)**
- Journey Data MCP: queries and aggregates event data (mode-aware)
- Friction Engine MCP: deterministic rule-based friction scoring (mode-agnostic)
- Insight MCP: LLM-powered root cause analysis via LiteLLM (mode-agnostic)
- Report MCP: HTML report generation with charts and executive narrative (mode-agnostic)

**3. LangGraph Agent System**
- Supervisor agent with rule-based routing and LLM fallback
- Four worker agents (data, friction, insight, report)
- Human-in-loop approval gate before final report generation
- SQLite checkpoint persistence for pause-and-resume

**4. Streamlit Dashboard**
- Mode toggle (demo / realtime)
- Interactive friction charts and funnel visualisations
- Insight review panels with approval gate
- Live event feed (realtime mode)
- HTML report download

**5. CLI Entry Point**
- Full pipeline control from terminal
- Generate data, run analysis, approve, generate report
- Thread-based checkpoint/resume system

### 3.2 How the Product Works End-to-End

**Demo Mode:**
```
User runs --generate-data
  → Faker generates 2,000 synthetic sessions across 6 journey steps
  → Events stored as Parquet file
  → DuckDB VIEW created over Parquet

User runs --run
  → LangGraph supervisor starts
  → data_worker calls Journey Data MCP → reads Parquet via DuckDB
  → friction_worker calls Friction Engine MCP → scores each step
  → insight_worker calls Insight MCP → LLM explains root causes
  → Graph pauses for human review
User reviews findings, runs --approve
  → report_worker calls Report MCP → generates HTML report + narrative
  → CIO report delivered
```

**Realtime Mode:**
```
Developer runs snippet_generator.py
  → Generates client-specific API key and embed snippet

Developer pastes snippet into client website <head>
  → tracker.js loads on every page
  → Browser events (page_view, click, error, rage_click, abandon) sent to collector

Collector API receives events
  → Validates API key
  → Writes to DuckDB live_events table in real time

Analyst runs --mode realtime --run --window-mins 60
  → Same LangGraph graph runs
  → data_worker calls Journey Data MCP → reads live_events table
  → Same friction, insight, report pipeline runs
  → Same HTML report delivered, now based on real user behaviour
```

---

## 4. Dual-Mode Architecture Intent

### 4.1 Why Two Modes Exist

The dual-mode design is deliberate and serves distinct purposes:

**Demo mode** exists so the system can be:
- Developed and tested without any live website
- Demonstrated to evaluators without network dependencies
- Used offline (with Ollama LLM) in air-gapped environments
- Validated with known friction patterns (email_verification is hard-coded as high-friction)

**Realtime mode** exists so the system can be:
- Deployed on actual client websites to analyse real user behaviour
- Used in production to drive actual product decisions
- Extended to multiple journeys and multiple clients without code changes

### 4.2 The Hard Boundary Principle

The fundamental architectural rule is: **the mode boundary is drawn at the Journey Data MCP**.

- Everything above the Journey Data MCP (tracker, collector, synthetic data) is mode-specific
- Everything at or below the Journey Data MCP (friction engine, insight, report, supervisor, workers) is completely mode-agnostic

This means:
- Adding a new data source only requires changing the Journey Data MCP
- The analytical brain never needs to know or care where data came from
- The entire friction scoring, LLM insight, and report pipeline is identical in both modes
- Tests for the analytical logic work in both modes without modification

### 4.3 Mode Selection

Mode is controlled by a single environment variable: `CJI_MODE=demo` or `CJI_MODE=realtime`

No code changes are required to switch modes. All components read from `config.py` which reads from the environment.

---

## 5. Goals and Success Criteria

### 5.1 PoC Goals

| Priority | Goal | Measurable Outcome |
|---|---|---|
| P0 | Demo mode runs end-to-end without any API key | `LLM_MODEL=ollama/llama3.1 python main.py --run --auto-approve` succeeds |
| P0 | Realtime mode collects and analyses live events | tracker.js → collector → DuckDB → agent analysis completes |
| P0 | All 4 MCP servers independently callable | Each server runs standalone and responds to tool calls |
| P0 | LangGraph supervisor routes correctly | Correct worker called at each step, no infinite loops |
| P0 | Human-in-loop gate pauses and resumes | Graph pauses, state saved, approval resumes from checkpoint |
| P0 | HTML report opens in browser with 2+ charts | `open reports/cji_report_*.html` shows friction chart + funnel |
| P1 | tracker.js embeds and sends events to collector | Browser events reach DuckDB live_events table |
| P1 | Dashboard mode toggle works | Switching demo ↔ realtime shows correct data |
| P1 | Provider swap works | `LLM_MODEL=gpt-4o` runs without code changes |
| P1 | Tests pass offline | `pytest tests/ -v` with no network, no API key |
| P2 | Live event feed shows in dashboard | Realtime mode shows incoming events in sidebar |
| P2 | LangSmith traces capture every node | Traces visible at smith.langchain.com |

### 5.2 Evaluator Success Criteria

The PoC passes evaluation if all of the following are demonstrable in a live walkthrough:

1. Dashboard opens and shows mode toggle (demo/realtime)
2. Demo analysis runs and produces a friction score for each step
3. At least one step scores ≥ 60/100 (critical)
4. At least one insight has a root cause explanation with a category (UX/data/system/process)
5. Human approval gate visibly pauses the agent and requires user action
6. HTML report downloads and opens showing charts + executive narrative
7. tracker.js embed snippet is generated with a client API key
8. `pytest tests/ -v` passes with zero network calls

---

## 6. Scope

### 6.1 In Scope

**Data Collection:**
- Synthetic event generation (Faker, Parquet, 2,000 sessions, 6 steps)
- Browser tracking script (tracker.js): page_view, click, form_submit, error, rage_click, abandon
- FastAPI event collector with API key authentication
- DuckDB live_events table for real-time event storage
- Embed snippet generator with client-specific API keys

**MCP Servers (4):**
- Journey Data MCP: get_funnel_steps, query_events, get_step_metrics, get_funnel_dropoff, get_live_snapshot, get_system_info
- Friction Engine MCP: score_friction, score_all_steps, detect_dropoffs, correlate_signals
- Insight MCP: generate_insight, prioritise_fix, save_insight, search_insights, rank_all_fixes
- Report MCP: generate_narrative, export_report

**Agent System:**
- LangGraph supervisor with rule-based routing and LLM fallback
- Four worker agents (data, friction, insight, report)
- SQLite checkpoint persistence
- Human-in-loop interrupt_before=["report_worker"]
- LiteLLM provider abstraction
- LangSmith tracing

**Interfaces:**
- Streamlit dashboard with mode toggle, live feed, charts, approval gate, report download
- CLI with --mode, --generate-data, --run, --approve, --auto-approve, --window-mins flags
- HTML report with Chart.js friction heatmap and funnel chart

**Journeys:** One configured journey (onboarding, 6 steps) extensible via config

### 6.2 Phased Roadmap (Post-PoC)

| Phase | Feature |
|---|---|
| Phase 2 | Real GA4 connector as alternative data source |
| Phase 2 | Multi-journey support in single deployment |
| Phase 3 | Real-time streaming via Redis Streams |
| Phase 3 | PostgreSQL + pgvector replacing DuckDB + ChromaDB |
| Phase 3 | HTTP MCP transport replacing stdio |
| Phase 4 | Multi-client SaaS with tenant isolation |
| Phase 4 | Predictive drop-off ML model |
| Phase 4 | Automated A/B test integration |

---

## 7. User Personas

### 7.1 Primary Personas

**Persona 1: CIO / IT Leadership (Executive Consumer)**
- Goal: Understand journey failure costs and receive prioritised investment recommendations
- Pain: Conflicting reports from different teams, no unified picture, reactive decisions
- CJI Touchpoint: Receives HTML report and executive narrative. Does not operate the system.
- Success signal: Can articulate top 3 friction problems and their fix priority in a board meeting

**Persona 2: Product Manager (Primary Analyst)**
- Goal: Know which step to fix next with quantified justification for engineering prioritisation
- Pain: Gut feelings, anecdotal evidence, no way to compare severity across steps
- CJI Touchpoint: Operates the Streamlit dashboard, reviews insights, approves reports
- Success signal: Enters sprint planning with a ranked fix list backed by friction scores

**Persona 3: UX / CX Analyst (Investigation User)**
- Goal: Understand qualitative reasons behind quantitative drop-off
- Pain: Manual correlation of Hotjar recordings with analytics events is slow and subjective
- CJI Touchpoint: Reviews root cause categories and evidence in insight panels; queries insight store
- Success signal: Can explain why a specific step has friction using AI-generated evidence in stakeholder presentations

**Persona 4: IT Developer / Engineer (Actioner)**
- Goal: Receive concrete, categorised bug reports with business impact scores
- Pain: Vague tickets like "signup is broken" with no data on severity or cause
- CJI Touchpoint: Reads insight report with root cause category (UX/data/system/process) and priority ranking
- Success signal: Has an evidence-backed, priority-ordered fix list assigned to the correct team

**Persona 5: Client Website Owner (Data Provider)**
- Goal: Understand how users experience their website's key journeys
- Pain: Has GA4 numbers but no explanation of why users leave
- CJI Touchpoint: Embeds tracker.js, receives periodic reports from the analyst team
- Success signal: Gets a monthly CIO report with ranked action items from their site's real user data

### 7.2 Builder Persona

**Persona 6: Internship Developer (Builder)**
- Goal: Build a working PoC that demonstrates agentic AI + MCP on a real analytical problem
- Pain: New to LangGraph, MCP, FastAPI, and production system design patterns
- CJI Touchpoint: Owns all code, runs demos, explains architecture to evaluators
- Success signal: System runs end-to-end in demo, tracker.js sends real events in realtime mode, evaluators are impressed

---

## 8. Functional Requirements — Demo Mode

### FR-DEMO-01: Synthetic Data Generation

| ID | Requirement | Priority |
|---|---|---|
| FR-D-01-01 | System must generate synthetic events using Faker for 2,000+ user sessions | P0 |
| FR-D-01-02 | Synthetic data must cover 6 journey steps with distinct friction profiles per step | P0 |
| FR-D-01-03 | email_verification must have drop_rate ≥ 40%, avg_dwell ≥ 120s, error_rate ≥ 30% | P0 |
| FR-D-01-04 | Events must include: page_view, error, rage_click, abandon, step_complete | P0 |
| FR-D-01-05 | Error events must include metadata: error_code, retry_count | P0 |
| FR-D-01-06 | Output must be a Parquet file at config.EVENTS_PARQUET path | P0 |
| FR-D-01-07 | Generation must complete in under 30 seconds for 2,000 sessions | P1 |
| FR-D-01-08 | Random seed must be set for reproducible test results | P1 |

### FR-DEMO-02: DuckDB Parquet Integration

| ID | Requirement | Priority |
|---|---|---|
| FR-D-02-01 | Journey Data MCP must create a DuckDB VIEW over the Parquet file on startup | P0 |
| FR-D-02-02 | DuckDB connection must be a module-level singleton — one connection per process | P0 |
| FR-D-02-03 | SQL queries must use parameterised days_back window | P0 |
| FR-D-02-04 | All query results must be serialised as JSON-safe Python dicts | P0 |

---

## 9. Functional Requirements — Realtime Mode

### FR-RT-01: Browser Tracking Script (tracker.js)

| ID | Requirement | Priority |
|---|---|---|
| FR-RT-01-01 | tracker.js must be a single self-contained JavaScript file with no dependencies | P0 |
| FR-RT-01-02 | Script must auto-detect the current journey step by matching URL to window.CJI_CONFIG.stepMap | P0 |
| FR-RT-01-03 | Script must generate anonymous user_id (UUID, persisted in localStorage) and session_id (UUID, per-tab) | P0 |
| FR-RT-01-04 | Script must track: page_view (DOMContentLoaded), click (document click listener), form_submit, error (window.onerror + unhandledrejection), rage_click (3+ clicks on same element within 500ms), abandon (beforeunload with sendBeacon) | P0 |
| FR-RT-01-05 | Events must batch every 5 seconds OR when 20 events accumulate, whichever comes first | P0 |
| FR-RT-01-06 | sendBeacon must be used as fallback for abandon events to survive tab close | P0 |
| FR-RT-01-07 | Script must support SPA navigation by intercepting history.pushState and popstate | P0 |
| FR-RT-01-08 | Script must expose window.CJITracker.track(eventType, metadata) for manual event firing | P1 |
| FR-RT-01-09 | Script must strip query parameters and fragments from URL before sending (no PII in URLs) | P0 |
| FR-RT-01-10 | Script must be loadable via: `<script src="https://host/tracker.js" async>` | P0 |
| FR-RT-01-11 | Config must be set via window.CJI_CONFIG before the script tag | P0 |
| FR-RT-01-12 | Script must work on all modern browsers (Chrome, Firefox, Safari, Edge) | P0 |

### FR-RT-02: Event Collector API

| ID | Requirement | Priority |
|---|---|---|
| FR-RT-02-01 | Collector must be a FastAPI application runnable with uvicorn | P0 |
| FR-RT-02-02 | Collector must serve tracker.js at GET /tracker.js with Cache-Control: public, max-age=3600 | P0 |
| FR-RT-02-03 | Collector must accept event batches at POST /collect/batch with JSON body | P0 |
| FR-RT-02-04 | Collector must validate API key before writing any events | P0 |
| FR-RT-02-05 | Collector must validate event schema using Pydantic v2 models | P0 |
| FR-RT-02-06 | Collector must write validated events to DuckDB live_events table | P0 |
| FR-RT-02-07 | Event writes must be performed in a background task so POST response is fast (< 100ms) | P0 |
| FR-RT-02-08 | Collector must have CORS headers: allow_origins=["*"] for PoC (restrict in production) | P0 |
| FR-RT-02-09 | Collector must expose GET /live/stats for per-step event counts | P1 |
| FR-RT-02-10 | Collector must expose GET /live/feed as Server-Sent Events stream for dashboard | P1 |
| FR-RT-02-11 | Collector must expose POST /admin/api-keys (protected by admin key) to create new client keys | P1 |
| FR-RT-02-12 | Collector must expose GET /health returning event count and status | P1 |
| FR-RT-02-13 | DuckDB live_events table must have received_at column for time-window queries | P0 |

### FR-RT-03: Embed Snippet Generation

| ID | Requirement | Priority |
|---|---|---|
| FR-RT-03-01 | snippet_generator.py must generate a unique API key per client using secrets.token_hex | P0 |
| FR-RT-03-02 | Generator must produce: embed_snippet.html, verify_tracker.py, useCJITracker.js (React hook), api_key.json | P0 |
| FR-RT-03-03 | Embed snippet must include window.CJI_CONFIG with apiKey, journeyId, endpoint, stepMap | P0 |
| FR-RT-03-04 | API key must be stored in DuckDB api_keys table by the collector before snippets are valid | P0 |
| FR-RT-03-05 | Generator must accept --journey, --host, --output CLI flags | P0 |
| FR-RT-03-06 | React hook must support Next.js router integration for SPA route tracking | P1 |

### FR-RT-04: Realtime Journey Data MCP

| ID | Requirement | Priority |
|---|---|---|
| FR-RT-04-01 | In realtime mode, Journey Data MCP must read from live_events table, not Parquet | P0 |
| FR-RT-04-02 | Time window in realtime mode must use REALTIME_WINDOW_MINUTES (minutes), not days | P0 |
| FR-RT-04-03 | get_live_snapshot tool must return rolling counts for the last N minutes | P1 |
| FR-RT-04-04 | All 4 existing tools (get_funnel_steps, get_step_metrics, get_funnel_dropoff, query_events) must work identically in realtime mode | P0 |
| FR-RT-04-05 | get_system_info tool must report current mode, event count, and data source | P1 |

---

## 10. Functional Requirements — Shared (Both Modes)

### FR-SHARED-01: Friction Engine MCP

| ID | Requirement | Priority |
|---|---|---|
| FR-S-01-01 | score_friction must compute a 0–100 score using 5 weighted signals | P0 |
| FR-S-01-02 | Weights: abandon_rate 0.35, error_rate 0.25, avg_dwell_ms 0.15, avg_retries 0.15, avg_rage_clicks 0.10 | P0 |
| FR-S-01-03 | Baselines: abandon 10%, error 5%, dwell 15,000ms, retries 0.1, rage_clicks 0.05 | P0 |
| FR-S-01-04 | Signal names must be exact strings: high_drop_off, critical_drop_off, frequent_errors, extended_hesitation, severe_confusion, repeated_retries, rage_clicks_detected | P0 |
| FR-S-01-05 | Steps scoring ≥ FRICTION_SCORE_THRESHOLD (default 60) must be flagged is_critical=True | P0 |
| FR-S-01-06 | score_all_steps must return results sorted descending by score | P0 |
| FR-S-01-07 | correlate_signals must return: signal_frequency, co_occurring_patterns, systemic_signals | P0 |
| FR-S-01-08 | All functions must be unit-testable with zero external dependencies | P0 |

### FR-SHARED-02: Insight MCP

| ID | Requirement | Priority |
|---|---|---|
| FR-S-02-01 | generate_insight must call LLM via LiteLLM with provider-agnostic wrapper | P0 |
| FR-S-02-02 | LLM system prompt must demand JSON-only response with exact schema | P0 |
| FR-S-02-03 | JSON fallback must catch all JSONDecodeError and produce a valid structured dict | P0 |
| FR-S-02-04 | Insight must include: title, root_cause, category (UX/data/system/process), evidence, suggested_fix, fix_effort | P0 |
| FR-S-02-05 | prioritise_fix must compute priority 1–5 using impact×users/effort formula | P0 |
| FR-S-02-06 | save_insight must store to ChromaDB with all metadata as string types | P0 |
| FR-S-02-07 | search_insights must guard against querying empty collection (n=min(n_results, count)) | P0 |
| FR-S-02-08 | rank_all_fixes must call LLM to generate an executive action plan string | P1 |

### FR-SHARED-03: Report MCP

| ID | Requirement | Priority |
|---|---|---|
| FR-S-03-01 | export_report must produce a fully self-contained HTML file | P0 |
| FR-S-03-02 | HTML must embed Chart.js from CDN and render on open with no server | P0 |
| FR-S-03-03 | Friction bar chart must use colour coding: red ≥70, amber 50–69, green <50 | P0 |
| FR-S-03-04 | Report must include: mode indicator (DEMO/LIVE), journey name, timestamp, charts, insights table, narrative | P0 |
| FR-S-03-05 | File naming: cji_report_{journey}_{YYYYMMDD_HHMMSS}.html | P0 |
| FR-S-03-06 | generate_narrative must produce 3-paragraph CIO-level summary | P0 |

### FR-SHARED-04: LangGraph Agent System

| ID | Requirement | Priority |
|---|---|---|
| FR-S-04-01 | Supervisor must use rule-based routing as primary path | P0 |
| FR-S-04-02 | Routing order: no data → data_worker, no scores → friction_worker, no insights → insight_worker, insights + not approved → END(pause), approved + no report → report_worker, has report → END | P0 |
| FR-S-04-03 | Graph must pause before report_worker via interrupt_before=["report_worker"] | P0 |
| FR-S-04-04 | Human approval must use graph.update_state(config, {"human_approved": True}, as_node="supervisor") | P0 |
| FR-S-04-05 | Supervisor must have iteration safety cutoff at MAX_AGENT_ITERATIONS (default 20) | P0 |
| FR-S-04-06 | Workers must never raise exceptions — all errors caught and appended to state["errors"] | P0 |
| FR-S-04-07 | All workers must return next_worker="supervisor" | P0 |
| FR-S-04-08 | Graph must use SqliteSaver checkpointer for persistence | P0 |
| FR-S-04-09 | Graph must be resumable after crash by passing thread_id to graph.stream(None, config) | P0 |

### FR-SHARED-05: Streamlit Dashboard

| ID | Requirement | Priority |
|---|---|---|
| FR-S-05-01 | Dashboard must show a mode toggle (demo / realtime) that restarts state on change | P0 |
| FR-S-05-02 | Dashboard must show 4 metric cards: steps analysed, critical steps, avg friction score, insights count | P0 |
| FR-S-05-03 | Dashboard must show friction bar chart and funnel drop-off chart side by side | P0 |
| FR-S-05-04 | Dashboard must show expandable insight panels with root cause, fix, effort, score | P0 |
| FR-S-05-05 | Dashboard must show human approval gate with Approve and Re-run buttons | P0 |
| FR-S-05-06 | Dashboard must show download button for HTML report after approval | P0 |
| FR-S-05-07 | Realtime mode dashboard must show collector API status (online/offline) | P1 |
| FR-S-05-08 | Realtime mode dashboard must show live event feed panel (last 15 min) | P1 |
| FR-S-05-09 | Realtime mode dashboard must show Generate embed snippet button | P1 |

---

## 11. Non-Functional Requirements

### 11.1 Performance

| Requirement | Target |
|---|---|
| Demo data generation (2,000 sessions) | < 30 seconds |
| Full analysis pipeline (demo, 2,000 events) | < 3 minutes |
| Collector event write latency | < 100ms per batch |
| tracker.js script size | < 10 KB unminified |
| tracker.js load impact on page | Non-blocking (async attribute) |
| Dashboard initial load | < 5 seconds |
| Friction scoring (all 6 steps) | < 5 seconds |
| LLM insight generation (per step) | < 30 seconds |

### 11.2 Reliability

- Agent must not crash on LLM timeout — retry up to 3 times with exponential backoff
- Agent must not crash on malformed LLM JSON — fallback dict always returned
- Collector must not crash on invalid event — reject with 422, write valid events, continue
- MCP server failure must be isolated to the calling worker — other workers continue
- Graph checkpoint must allow resume after any crash

### 11.3 Maintainability

- All configuration in `.env` and `config.py` — no hardcoded values in business logic
- New journey: edit JOURNEY_CONFIG in config.py, add to STEP_PROFILES in synthetic_data.py
- New LLM provider: change LLM_MODEL env var — no code changes
- New data source: modify Journey Data MCP only — all agents remain unchanged
- New MCP tool: add @mcp.tool decorator, add to SERVER_REGISTRY — no agent code changes

### 11.4 Security

- API keys generated with secrets.token_hex(16) — cryptographically secure
- API keys validated on every collector POST before any data is written
- tracker.js strips URL query parameters before sending — no PII in event URLs
- User IDs are UUID v4 — no mapping to real individuals
- .env file in .gitignore — API keys never committed
- Admin endpoint requires separate CJI_ADMIN_KEY header

### 11.5 Testability

- Friction Engine MCP must be unit-testable with zero network calls and zero API keys
- All unit tests must pass in < 30 seconds
- tests/ directory must have sys.path.insert(0, "..") for all test files
- Test fixtures must include both low-friction and high-friction step dicts

### 11.6 Portability

- Python 3.11+ on macOS, Linux, and Windows (WSL)
- All dependencies installable via pip from requirements.txt
- Offline mode: LLM_MODEL=ollama/llama3.1 with local Ollama instance
- tracker.js works in all modern browsers without transpilation

---

## 12. User Stories

### Epic 1: Demo Mode Operation

**US-001** — As a developer, I want to generate 2,000 synthetic sessions with realistic friction patterns so that I can test and demonstrate the system without a live website.

**US-002** — As a developer, I want to run the full analysis pipeline with `--auto-approve` in a single command so that I can verify the system end-to-end quickly.

**US-003** — As a developer, I want to swap the LLM provider with one environment variable change so that the system works when specific API keys are unavailable.

### Epic 2: Realtime Mode Setup

**US-004** — As a client developer, I want to paste a single HTML snippet into my website's `<head>` to enable tracking, just like adding GA4, so that no custom instrumentation work is needed.

**US-005** — As a client developer, I want a generated React hook for Next.js/SPA integration so that tracking works correctly across client-side navigation without full page reloads.

**US-006** — As a system administrator, I want to generate a client-specific API key in 30 seconds so that each client's data is isolated and I can revoke access independently.

### Epic 3: Friction Discovery

**US-007** — As a Product Manager, I want to see friction scores for every journey step on one screen so that I can immediately identify the most problematic step.

**US-008** — As a UX Analyst, I want to understand which specific signals (rage clicks, high dwell time, errors) are driving friction at each step so that I can design targeted UX fixes.

**US-009** — As an IT Developer, I want friction issues categorised as UX, data, system, or process so that tickets are routed to the correct team without investigation overhead.

### Epic 4: Human Oversight

**US-010** — As a Product Manager, I want to review AI-generated insights before they are included in the final CIO report so that I can correct any incorrect inferences and maintain quality.

**US-011** — As a Product Manager, I want to reject an analysis and trigger a re-run without losing the original thread's state so that I can investigate data anomalies without starting over.

### Epic 5: Reporting

**US-012** — As a CIO, I want a 3-paragraph executive summary that explains the business impact, root causes, and prioritised recommendations so that I can brief the board without technical preparation.

**US-013** — As a Product Manager, I want to download a self-contained HTML report I can share via email so that stakeholders can view it without dashboard access.

---

## 13. Feature Specifications

### 13.1 tracker.js Event Capture Specification

| Event | Trigger | Key Metadata |
|---|---|---|
| page_view | DOMContentLoaded + SPA pushState/popstate | referrer, title, step_id |
| click | document addEventListener('click') | element_tag, element_id, element_class, text_preview (50 chars) |
| form_submit | form submit event | form_id, form_action |
| error | window.onerror + unhandledrejection | error_code, error_message (200 chars), source_file, line |
| rage_click | 3+ clicks on same element within 500ms | click_count, element_tag, element_id |
| abandon | beforeunload (sendBeacon) | dwell_reason: "page_unload", duration_ms computed |
| step_complete | SPA navigation away from step | dwell_reason: "spa_navigate", duration_ms |

**Batching logic:** Queue events → flush every 5s OR when queue.length >= 20 → POST /collect/batch. On beforeunload: flush remaining queue with sendBeacon to survive tab close.

### 13.2 Friction Scoring Algorithm

```
normalise(value, baseline) = min(value / max(baseline, 0.001), 3.0) / 3.0

raw_score = normalise(abandon_rate_pct, 10.0)  × 0.35
          + normalise(error_rate_pct,   5.0)   × 0.25
          + normalise(avg_dwell_ms,     15000) × 0.15
          + normalise(avg_retries,      0.1)   × 0.15
          + normalise(avg_rage_clicks,  0.05)  × 0.10

score = min(100, int(raw_score × 100))

Signal thresholds:
  "high_drop_off"       → abandon > 30%
  "critical_drop_off"   → abandon > 50%
  "frequent_errors"     → error > 15%
  "extended_hesitation" → dwell > 60,000ms
  "severe_confusion"    → dwell > 120,000ms
  "repeated_retries"    → retries > 1.0
  "rage_clicks_detected"→ rage_clicks > 0.5

confidence = min(0.5 + len(signals) × 0.1, 0.98)
```

### 13.3 Priority Ranking Algorithm

```
effort_map = {"low": 1, "medium": 2, "high": 4}
priority_score = (friction_score × unique_users) / effort_cost

priority 1: priority_score > 40,000
priority 2: priority_score > 20,000
priority 3: priority_score > 8,000
priority 4: priority_score > 2,000
priority 5: otherwise
```

### 13.4 LangGraph Supervisor Routing Logic

```
iteration ≥ 20                          → END (safety cutoff)
not state["event_summary"]              → data_worker
not state["friction_scores"]            → friction_worker
not state["insights"]                   → insight_worker
state["insights"] and not human_approved → END (human pause)
human_approved and not state["report_path"] → report_worker
state["report_path"]                    → END (complete)
none of above                           → LLM fallback routing
```

---

## 14. Data Requirements

### 14.1 Unified Journey Event Schema

Every event from both synthetic generation and tracker.js must conform to:

```
event_id:    UUID string          — unique event identifier
user_id:     UUID string          — anonymous user identifier
session_id:  UUID string          — anonymous session identifier  
journey_id:  string               — e.g. "onboarding"
step_id:     string               — e.g. "email_verification"
event_type:  string               — page_view|click|form_submit|error|rage_click|abandon|step_complete|identify
timestamp:   ISO-8601 UTC string  — e.g. "2026-03-15T14:30:00.123Z"
duration_ms: integer              — milliseconds; 0 for instant events
url:         string               — sanitised URL (no query params)
metadata:    JSON object          — source-specific payload
```

### 14.2 DuckDB Table Schemas

**Demo mode — events VIEW (over Parquet):**
All columns above except session_id and url (synthetic data doesn't include these)

**Realtime mode — live_events table:**
All columns above PLUS:
- received_at: TIMESTAMPTZ DEFAULT NOW() — for real-time window queries

**api_keys table (realtime mode):**
```
api_key:     VARCHAR PRIMARY KEY
journey_id:  VARCHAR NOT NULL
client_name: VARCHAR NOT NULL
created_at:  TIMESTAMPTZ DEFAULT NOW()
active:      BOOLEAN DEFAULT TRUE
```

### 14.3 FrictionScore Schema

```
step_id:          string
score:            integer (0-100)
drop_off_rate:    float (0.0-1.0)
avg_dwell_ms:     integer
retry_count:      float
rage_click_rate:  float
signals:          list[string]
confidence:       float (0.0-0.98)
is_critical:      boolean
```

### 14.4 Insight Schema

```
insight_id:     UUID string
step_id:        string
title:          string (max 8 words)
root_cause:     string (2-3 sentences)
category:       "UX" | "data" | "system" | "process" | "unknown"
evidence:       list[string]
priority:       integer (1-5)
fix_effort:     "low" | "medium" | "high"
suggested_fix:  string (1-2 sentences)
score:          integer
priority_score: float
```

### 14.5 Data Volumes

| Dataset | Demo Mode | Realtime Mode |
|---|---|---|
| Events | ~15,000 rows (Parquet, ~3MB) | Grows continuously (DuckDB table) |
| Step metrics | 6 rows | 6 rows |
| Friction scores | 6 rows | 6 rows |
| Insights | 2-4 rows | 2-4 rows per run |
| ChromaDB | Grows per run | Grows per run |
| Checkpoints | ~10KB per thread | ~10KB per thread |
| HTML reports | ~100KB per report | ~100KB per report |

---

## 15. Integration Requirements

### 15.1 Internal Integrations

| Integration | Protocol | Purpose |
|---|---|---|
| tracker.js → Collector API | HTTP POST (fetch + sendBeacon) | Event delivery from browser |
| Collector API → DuckDB | Python library (in-process) | Event persistence |
| Workers → MCP Servers | stdio JSON-RPC | Tool execution |
| Supervisor → LLM | LiteLLM → REST API | LLM fallback routing |
| Insight MCP → LLM | LiteLLM → REST API | Root cause generation |
| Report MCP → LLM | LiteLLM → REST API | Narrative generation |
| Graph → SQLite | LangGraph SqliteSaver | Checkpoint persistence |
| Insight MCP → ChromaDB | Python library (in-process) | Insight vector storage |

### 15.2 LLM Provider Support

| Provider | Model String | Setup |
|---|---|---|
| Anthropic Claude (default) | `claude-sonnet-4-6` | ANTHROPIC_API_KEY in .env |
| OpenAI | `gpt-4o` | OPENAI_API_KEY in .env |
| Local Ollama (offline) | `ollama/llama3.1` | `ollama serve && ollama pull llama3.1` |

### 15.3 External Service Dependency Matrix

| Service | Demo Mode | Realtime Mode | Optional |
|---|---|---|---|
| LLM API | Required (or Ollama) | Required (or Ollama) | Ollama replaces |
| LangSmith | Optional | Optional | Yes |
| Collector API | Not needed | Required | No |
| Client Website | Not needed | Required (for tracker.js) | No |

---

## 16. Security and Compliance

### 16.1 API Key Security

- Keys generated with `secrets.token_hex(16)` — 128-bit entropy, cryptographically secure
- Keys validated on every collector POST — invalid key returns 401 with no data written
- Keys stored in DuckDB api_keys table with active flag — can be revoked without deletion
- Admin key required to create new keys — separate from client API keys

### 16.2 Data Privacy

- User IDs: UUID v4, no PII, no mapping to real individuals
- Session IDs: UUID v4, new per browser tab
- URL sanitisation: query parameters and fragments stripped before event storage
- LLM prompts: contain only aggregated metrics, never raw event data or URLs
- No real names, emails, or identifiers ever enter the system

### 16.3 Code Security

- `.env` never committed — listed in `.gitignore`
- API keys never hardcoded — always read from environment variables
- DuckDB write operations use parameterised queries — no SQL injection risk
- CORS in PoC is open (`allow_origins=["*"]`) — must be restricted to client domains in production

---

## 17. Constraints and Assumptions

### 17.1 Constraints

- 6-week delivery sprint
- Only free/synthetic data in PoC — no real customer PII
- Local machine deployment — no cloud infrastructure for PoC
- tracker.js must be a single file with no build step or bundler
- Python 3.11+ required

### 17.2 Assumptions

- Evaluators have Python 3.11+ and can install pip packages
- At least one of: Anthropic API key, OpenAI API key, or Ollama installation is available
- For realtime demo: a test website or localhost app is available to embed tracker.js
- LangSmith free tier (1,000 traces/month) is sufficient for PoC demonstration
- The "onboarding" journey is representative enough for evaluation purposes

---

## 18. Out of Scope

- Real-time streaming with Kafka or Redis Streams
- Real GA4, Hotjar, or Mixpanel API connectors (future Phase 2)
- Multi-tenant SaaS deployment or user authentication
- Mobile app tracking (iOS, Android)
- Predictive ML model for drop-off forecasting
- Automated remediation or fix deployment
- WCAG accessibility compliance
- Multi-language UI support
- Cloud deployment or container orchestration

---

## 19. Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| LLM API unavailable during demo | Low | High | Ollama offline fallback; pre-generate data and run with cached insights |
| tracker.js CORS blocked on test site | Medium | Medium | Use localhost:8000 as collector with no CORS restriction; test with verify_tracker.py |
| DuckDB file lock between collector and MCP server | Low | Medium | Both must use the same process or separate DuckDB files; in PoC, collector and MCP run in same process space |
| LLM returns malformed JSON | Medium | Low | JSON fallback catches all errors; tests cover this case |
| Collector API not running in realtime demo | Medium | High | Dashboard shows clear "Collector offline" warning with start command |
| sendBeacon blocked by privacy extensions | Low | Low | fetch fallback always used first; abandon event is nice-to-have, not critical |
| sentence-transformers download blocks demo | Medium | Medium | Document expected 2-min wait on first run; subsequent runs instant |

---

## 20. Timeline and Milestones

| Week | Deliverable |
|---|---|
| Week 1 | config.py, state.py, synthetic_data.py, friction_engine_server.py working; pytest passing |
| Week 2 | All 4 MCP servers independently callable; journey_data_server.py demo mode complete |
| Week 3 | LangGraph graph compiles; supervisor routing correct; workers call MCP servers |
| Week 4 | tracker.js working; collector API receiving events; realtime mode end-to-end |
| Week 5 | Dashboard with mode toggle; HTML reports generating; LangSmith traces visible |
| Week 6 | Full demo rehearsal; README complete; both modes demonstrated; evaluator walkthrough |

---

## 21. Acceptance Criteria

### P0 — Must Pass All

1. `python main.py --mode demo --generate-data` completes without error
2. `python main.py --mode demo --run --auto-approve` produces an HTML report
3. The HTML report shows at least 2 charts and an executive narrative
4. At least 1 step has friction score ≥ 60
5. At least 1 insight has a root_cause and category field
6. `pytest tests/ -v` passes all tests with no network connection
7. `python tracker/snippet_generator.py` generates embed_snippet.html with a valid API key
8. `uvicorn collector.api:app` starts and responds to GET /health

### P1 — Must Pass 80%

1. tracker.js sends events to collector — visible in DuckDB live_events table
2. Realtime analysis runs with CJI_MODE=realtime and analyses live_events
3. Human-in-loop gate pauses and resumes via --approve flag
4. LLM provider swaps: LLM_MODEL=gpt-4o runs without code changes
5. Dashboard mode toggle switches between demo and realtime data
6. Dashboard shows live event feed in realtime mode
7. LangSmith shows complete trace of one agent run

---

## 22. Glossary

| Term | Definition |
|---|---|
| CJI | Customer Journey Intelligence — the name of this system |
| Demo mode | System operates on synthetic Faker-generated data; no live website needed |
| Realtime mode | System operates on live events from tracker.js embedded on a client website |
| tracker.js | JavaScript browser script that captures user events and sends them to the collector |
| Collector API | FastAPI server that receives events from tracker.js and stores them in DuckDB |
| Embed snippet | HTML code block containing window.CJI_CONFIG and a script tag; pasted into client website |
| MCP | Model Context Protocol — Anthropic's standard for connecting AI agents to external tools |
| MCP Server | An independent Python process exposing typed tool interfaces via JSON-RPC over stdio |
| FastMCP | Python framework for building MCP servers with function decorators |
| LangGraph | Graph-based agent orchestration framework supporting stateful multi-agent workflows |
| Supervisor | The routing node in LangGraph that decides which worker to call next |
| Worker | A specialised async function that calls one MCP server and updates shared state |
| CJIState | The TypedDict shared across all graph nodes, persisted to SQLite checkpoints |
| Human-in-loop | A design pattern where the graph pauses at a checkpoint for human review |
| LiteLLM | Python library providing a unified API for 100+ LLM providers |
| ChromaDB | Local persistent vector database for semantic search over insights |
| DuckDB | In-process analytical SQL engine that reads Parquet files and hosts the live_events table |
| Friction score | A 0–100 composite metric quantifying how hard a journey step is for users |
| Root cause | The underlying reason (UX/data/system/process) explaining a step's friction |
| Priority | A 1–5 rank assigned to each insight based on impact × users / effort |
| sendBeacon | Browser API that sends data reliably even as the tab closes |
| SPA | Single Page Application — JavaScript apps that navigate without full page reloads |
| stepMap | A JavaScript object mapping URL paths to journey step IDs in tracker.js config |
| API key | A cryptographically secure token (cji_live_xxxxxxxx) identifying a client |
| Thread ID | A UUID identifying one analysis run; used to resume from checkpoint |
