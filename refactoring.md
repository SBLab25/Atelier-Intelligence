# CJI Refactoring and Documentation Audit

**Audit scope:** repository implementation, tests, runtime helpers, configuration,
and project documentation.

**Audit posture:** senior-production review. Findings are based on the checked-in
code and documents, not on assumptions about future architecture. This document
does not claim that every PoC shortcut is unacceptable; it identifies what must
be corrected, what should be simplified, and what should be deliberately
retained because it is a good boundary.

**Overall assessment:** the project has a sound analytical concept and several
good foundations—typed validation, a deterministic scoring engine, explicit
workflow state, MCP domain separation, PII sanitization, and tests for the core
algorithm. It is not yet a coherent production codebase. The main problem is
not the number of lines; it is architectural drift. The implementation, tests,
and documentation describe multiple generations of the system at the same time.
Refactoring should begin by establishing one executable contract, then removing
obsolete paths and making all runtime boundaries explicit.

---

## 1. Executive findings

| ID | Priority | Area | Finding | Recommended action |
|---|---|---|---|---|
| R-01 | P0 | Functional correctness | `ingestion_worker.py` calls port 8004, but `run_servers.py` starts ingestion on port 8005 and report on 8004. | Centralize service discovery and fix the endpoint before any production workflow work. |
| R-02 | P0 | Data access | `get_system_info()` calls the PostgreSQL query path even in demo mode. | Use an explicit repository abstraction and make demo health checks use DuckDB/Parquet. |
| R-03 | P0 | Security | Collector accepts wildcard CORS with credentials and exposes a default admin key. | Make origins and secrets mandatory configuration; fail closed outside development. |
| R-04 | P0 | Security/data integrity | Several SQL statements interpolate request/configuration values. | Parameterize values and allow-list identifiers; add injection regression tests. |
| R-05 | P0 | Output safety | `report_server.py` interpolates narrative, journey names, modes, and insight fields directly into HTML. | Escape HTML text/attributes and use a templating layer with a strict CSP. |
| R-06 | P1 | Contract integrity | Collector API models duplicate `collector/models.py` and use different field names (`journey_name` vs `journey_id`). | Define one canonical schema module and derive request/response models from it. |
| R-07 | P1 | Documentation truth | `Project_Memory.md` says application code does not exist, while the repository contains the implementation and tests. | Archive historical design docs or mark them as superseded; generate status from code/tests. |
| R-08 | P1 | Runtime topology | Ports, MCP transport, provider strategy, and storage assumptions are duplicated and contradictory. | Replace literals with a validated service registry and one architecture contract. |
| R-09 | P1 | Reliability | Background writes return “queued” before persistence and errors are only logged; duplicate inserts are counted as accepted. | Introduce an ingestion result model, durable queue, idempotency semantics, and accurate counters. |
| R-10 | P1 | Maintainability | Broad exception handling and silent `pass` branches in CLI/dashboard obscure failures. | Catch expected exceptions only, preserve causes, and surface structured errors. |
| R-11 | P1 | Dead code | `test_dummy`, legacy utility scripts, unused imports, unused parameters, and duplicate ingestion paths increase ambiguity. | Inventory entry points, delete obsolete utilities, and enforce lint/type checks. |
| R-12 | P1 | AI workflow | LLM calls and MCP calls do not have a unified timeout, budget, correlation, or audit contract. | Introduce provider/tool adapters and durable run metadata. |
| R-13 | P2 | Performance | Insight generation, prioritization, saving, and report calls are sequential per step. | Bound concurrency after idempotency and rate-limit controls are in place. |
| R-14 | P2 | Packaging | Application imports depend on `sys.path.insert`, and the repository is not an installable package. | Add `pyproject.toml`, package boundaries, and a supported CLI entry point. |
| R-15 | P2 | Frontend direction | Streamlit is doing data access, orchestration, and UI fallback work in one large module. | Keep it as a compatibility client while moving product UX to Next.js/BFF. |

### Priority definitions

- **P0:** correctness, security, or data-integrity issue that should block a
  production claim.
- **P1:** major maintainability or reliability issue that should be resolved
  during the foundation refactor.
- **P2:** worthwhile modernization or performance work after contracts are stable.

---

## 2. What is already good and should be preserved

Refactoring should not flatten the project into a single service or replace
working deterministic behavior with unnecessary abstractions.

### Good boundaries

- `mcp_servers/friction_engine_server.py` keeps score computation pure and
  independently testable.
- `collector/models.py` uses Pydantic validators for event type, duration,
  metadata, and URL sanitization.
- `guardrails/sanitiser.py` and `guardrails/output_validator.py` establish a
  useful pre-LLM/post-LLM safety boundary.
- `state.py` makes the graph blackboard explicit instead of relying on hidden
  mutable globals.
- `agents/supervisor.py` has a deterministic routing order and an iteration
  cutoff.
- `tests/test_friction_engine.py` provides meaningful boundary coverage for the
  scoring algorithm.
- The ingestion fingerprint cache is a sensible optimization when its registry
  becomes versioned and concurrency-safe.
- Demo mode and realtime mode are valuable test seams; they should become
  repository implementations behind a common interface rather than disappear.

### Refactoring principle

Preserve behavior first, simplify second, optimize third. Do not change scoring
weights, event taxonomy, or approval semantics during mechanical cleanup unless
the change is explicitly versioned and covered by compatibility tests.

---

## 3. P0 correctness and security findings

### R-01 — Ingestion worker uses the wrong MCP port

**Evidence**

- `cji_agent/agents/ingestion_worker.py:27` sets
  `INGESTION_MCP_URL = "http://localhost:8004"`.
- `cji_agent/run_servers.py:11-15` lists ingestion first, and the executable
  service files assign:
  - ingestion server: `cji_agent/mcp_servers/ingestion_intelligence_server.py:648`
    → port 8005;
  - report server: `cji_agent/mcp_servers/report_server.py:203`
    → port 8004.
- `cji_agent/tools/mcp_client.py:20-24` separately maps ingestion to 8005 and
  report to 8004.

**Impact**

The ingestion worker can call the report service with ingestion tool names.
This is a deterministic runtime failure for `--ingest` workflows and is exactly
the kind of broken handoff the refactor must eliminate.

**Choices**

| Choice | Use when | Assessment |
|---|---|---|
| Fix the literal to 8005 | Immediate emergency patch | Necessary but insufficient; leaves topology duplicated. |
| Reuse `mcp_client.mcp_session()` | Transitional codebase | Better; removes direct HTTP assumptions from the worker. |
| Inject a typed service registry/config object | Production target | Recommended; one source of truth, test override, no hidden localhost dependency. |

**Recommended refactor**

Remove `_call_tool()` from `ingestion_worker.py`. Use the same MCP client
abstraction as other workers, or define a common typed `ToolGateway`. Make the
service name, not the port, the dependency. Add a test asserting every logical
service resolves to the intended endpoint.

---

### R-02 — Demo health check uses the realtime database path

**Evidence**

- `cji_agent/mcp_servers/journey_data_server.py:90-111` implements
  `get_system_info()`.
- Line 95 calls `execute_query("SELECT 1")` before checking `CJI_MODE`.
- `execute_query()` at lines 65-77 creates the PostgreSQL engine and reads
  `DATABASE_URL`.
- Demo mode is otherwise intended to use Parquet through DuckDB.

**Impact**

Demo mode can report an error or require a configured PostgreSQL backend even
when the documented promise is “demo mode requires no external services.”
This creates false diagnostics and makes local setup more fragile.

**Choices**

1. Add a conditional branch in `get_system_info()` — smallest repair.
2. Introduce `EventRepository` with `DemoEventRepository` and
   `RealtimeEventRepository` — recommended foundation.
3. Use a single SQL engine for both modes — simple operationally, but weakens
   the offline demo and makes tests slower.

**Recommended refactor**

Define a repository protocol with `health()`, `step_metrics()`,
`funnel_dropoff()`, `query_events()`, and `live_snapshot()`. Select the
implementation once at application startup. Do not branch on `CJI_MODE` inside
every query function.

---

### R-03 — Permissive CORS and unsafe default administrator secret

**Evidence**

- `cji_agent/collector/api.py:21-27` uses `allow_origins=["*"]` together with
  `allow_credentials=True`.
- `cji_agent/config.py:66` defaults `CJI_ADMIN_KEY` to
  `"change-me-in-production"`.
- `collector/api.py:58-70` seeds fixed development/live API keys during table
  creation.

**Impact**

This is unsafe for any internet-reachable deployment. Credentialed wildcard
CORS is an invalid/unsafe browser policy, and a known admin secret or seeded
live key turns deployment configuration into a security liability.

**Choices**

| Choice | Assessment |
|---|---|
| Document “do not use in production” | Not sufficient; insecure defaults are copied. |
| Require explicit `CJI_ADMIN_KEY` and origin list | Minimum acceptable repair. |
| Replace admin key with OIDC/RBAC | Recommended production target. |

**Recommended refactor**

- Fail startup when a non-development environment has no strong admin
  credential.
- Never seed a live key from application startup.
- Store only hashes of API keys.
- Configure explicit origins from an environment list.
- Separate readiness from liveness so a missing database is not hidden behind
  an “OK” response.

---

### R-04 — SQL interpolation creates injection and correctness risk

**Evidence**

- `journey_data_server.py:123-202`, `207-285`, and `287-337` interpolate
  journey IDs, step IDs, event types, and time windows into SQL.
- `collector/api.py:202-211` interpolates `minutes` into an interval string.
- `execute_query()` at `journey_data_server.py:65-77` performs ad-hoc string
  replacement for `?` placeholders instead of binding parameters.

**Impact**

Even when some values are configuration-derived, request-derived values and
future changes can become SQL injection paths. String replacement also breaks
when values contain quotes and makes query review difficult.

**Choices**

1. Validate and quote values manually — avoid.
2. Use SQLAlchemy bind parameters for PostgreSQL and DuckDB parameters for
   DuckDB — recommended transitional solution.
3. Replace dynamic SQL with query objects/repository methods — recommended
   long-term solution.

**Recommended refactor**

Separate dynamic identifiers from values. Identifiers must come from an
allow-list; all values must be bound parameters. Replace `execute_query(sql,
params)` with typed repository methods so callers cannot construct arbitrary SQL.
Add tests for quotes, negative/large windows, unknown steps, and malicious input.

---

### R-05 — Generated HTML is not escaped

**Evidence**

- `cji_agent/mcp_servers/report_server.py:90-194` interpolates `journey_name`,
  `mode`, `narrative`, step IDs, titles, root causes, and suggestions into
  HTML/JavaScript.
- `dropoffs` is calculated at line 98 but never used.
- Chart.js is loaded from an unpinned CDN at line 108.

**Impact**

Imported data and LLM output are untrusted. A report can contain markup or
script content that executes when opened. The report also has a supply-chain
dependency on a mutable third-party URL.

**Choices**

| Choice | Assessment |
|---|---|
| Escape with `html.escape` and JSON-safe serialization | Minimum repair. |
| Use Jinja2 with autoescape and a CSP | Recommended for the current HTML path. |
| Move reports to a React/Next.js renderer | Production target; retain server-side escaping. |

**Recommended refactor**

Use an autoescaping template. Serialize chart data with a safe JSON encoder,
never interpolate raw text into JavaScript, and either bundle Chart.js or pin
its integrity hash. Add tests containing `<script>`, quotes, backslashes, and
Unicode in every user/model-controlled field.

---

## 4. P1 contract and architecture findings

### R-06 — Multiple incompatible event schemas

**Evidence**

- `collector/models.py:36-100` defines `TrackerEvent` with `journey_id`,
  `duration_ms`, and strict event validation.
- `collector/api.py:100-116` defines a second `EventItem`/`BatchPayload` with
  `journey_name`, `element_selectors`, no event-type validator, and no
  duration field.
- `state.py:25-37` defines `JourneyEvent` with `journey_id` and metadata as a
  string.
- `ingestion_intelligence_server.py:82-108` defines another `CanonicalEvent`.
- `README.md` and `docs/6-API-Contracts.md` describe still more variants.

**Impact**

The project has no single authoritative contract. A tracker payload can validate
under one model and fail or change meaning under another. This is a high-cost
source of silent analytics corruption.

**Recommended refactor**

Create a package such as:

```text
cji_agent/domain/
  events.py
  insights.py
  analysis_runs.py
  errors.py
```

Define canonical Pydantic models once. Derive database serialization and API
models from those types. Use explicit adapters only at external boundaries.
Version breaking changes (`v1`, `v2`) instead of silently changing field names.

---

### R-07 — Documentation contains false current-state claims

**Evidence**

- `Project_Memory.md:32-35` says `cji_agent/` does not exist and no application
  code has been written.
- The same file later documents completed implementation and lists the actual
  modules.
- `Project Details/SYSTEM_DESIGN.md:30-49` describes four MCP servers and
  DuckDB realtime storage, while the repository contains five MCP services and
  SQLAlchemy/PostgreSQL code.
- `README.md:3` says four MCP micro-servers, while `Project_status.md:64-150`
  describes five.

**Impact**

False documentation causes engineers and agents to implement against an obsolete
architecture. It also makes reviews unreliable because “complete” and “not
started” statements coexist.

**Choices**

1. Keep all documents and add dates — insufficient.
2. Mark old documents as historical — acceptable short-term.
3. Consolidate current truth into versioned architecture/API docs and archive
   obsolete design — recommended.

**Recommended refactor**

- Mark `Project Details/` as historical source material.
- Make `project_summary.md` the current high-level baseline.
- Generate API/schema reference from executable models where possible.
- Add `docs/adr/` for deliberate architecture decisions.
- Remove “single source of truth” claims from files that are not maintained as
  current truth.
- Add a documentation verification checklist to CI.

---

### R-08 — Runtime topology is duplicated and contradictory

**Evidence**

- Ports are hard-coded in each MCP server, `tools/mcp_client.py`,
  `agents/ingestion_worker.py`, and `run_servers.py`.
- Transport comments differ: `friction_engine_server.py:9` describes stdio,
  while the executable entrypoint at line 312 uses SSE.
- `requirements.txt:11-17` still describes LiteLLM/Anthropic as the LLM layer,
  while insight/report/ingestion code makes direct Groq/Anthropic HTTP calls.
- `graph.py:38` exposes `use_persistence` but says persistence is attached
  elsewhere, making the parameter misleading.

**Impact**

Changing a port or provider requires search-and-replace across code and docs.
This is how the ingestion port defect survived. Misleading parameters also
make APIs appear more stable than they are.

**Recommended refactor**

Introduce typed settings:

```python
class ServiceSettings(BaseModel):
    name: str
    base_url: AnyHttpUrl
    transport: Literal["sse", "streamable_http"]
    timeout_seconds: float
```

Load one validated registry from environment/config. Expose a single
`MCPServiceRegistry` to clients and workers. Remove unused compatibility
parameters such as `use_persistence` unless they change behavior.

---

### R-09 — Collector response semantics are inaccurate

**Evidence**

- `collector/api.py:188-199` queues `write_events()` in a background task and
  immediately returns `accepted=len(payload.events)`.
- `write_events()` at lines 129-165 increments `accepted` after executing
  `ON CONFLICT DO NOTHING`, without checking whether a row was inserted.
- Errors after the response are only logged.

**Impact**

Clients receive a success-shaped response before persistence succeeds. Duplicate
events can be reported as accepted, and the API cannot communicate partial
failure. This damages retry and monitoring behavior.

**Choices**

| Choice | Assessment |
|---|---|
| Keep FastAPI `BackgroundTasks` and change wording to `queued` | Suitable only for a best-effort PoC. |
| Return an ingestion job ID and expose status | Recommended transitional model. |
| Use a durable queue and idempotent consumer | Production target. |

**Recommended refactor**

Define explicit statuses (`queued`, `accepted`, `duplicate`, `rejected`,
`failed`) and an idempotency key. For synchronous development mode, return the
actual result. For production, enqueue a job and let clients query or subscribe
to its result.

---

### R-10 — Broad exception handling hides operational failures

**Evidence**

- `main.py:247-258`, `main.py:279-280`, `main.py:340-342` silently ignore
  exceptions or use `pass`.
- `dashboard.py` contains multiple broad `except Exception` branches.
- `collector/api.py:84-86` suppresses keep-alive failures.
- Worker-level broad catches are useful as a boundary, but they currently
  collapse many failure classes into free-form strings.

**Impact**

The application can print “complete” while state persistence, dashboard output,
or approval handling failed. Broad catches also make incident diagnosis harder.

**Recommended refactor**

- Catch expected exceptions at each boundary.
- Convert external errors into typed error codes with causes and retryability.
- Log structured fields (`run_id`, `worker`, `service`, `attempt`).
- Preserve exception chaining.
- Treat checkpoint/report persistence failures as failed operations, not
  successful runs with missing output.
- Use a top-level CLI error handler for final exit codes.

---

### R-11 — Dead code, duplicate utilities, and debug surfaces

**Evidence**

- `journey_data_server.py:84-87` exposes `test_dummy()` as a production MCP
  tool.
- `agents/workers.py:15` imports `json` but does not use it.
- `agents/ingestion_worker.py:16` imports `json` and `COLLECTOR_URL` but does
  not use them.
- `report_server.py:5-7` imports `Path`, `Dict`, and `List` without needing
  them in the shown implementation; `dropoffs` is unused.
- `graph.py:38` accepts an unused `use_persistence` parameter.
- `test_servers.py`, `test_duckdb.py`, `test_pg.py`, `test_metadata_query.py`,
  and root-level diagnostic scripts are ad-hoc checks rather than isolated
  pytest tests.
- `tools/ingest_json.py` is a second ingestion implementation alongside the
  smart-ingestion MCP.

**Impact**

Dead surfaces confuse maintainers, increase attack surface, and make it unclear
which path is supported. Duplicate ingestion logic can produce different
canonical records from the same source.

**Recommended refactor**

1. Remove `test_dummy` from the runtime server.
2. Run an unused-import/lint pass and remove imports/variables.
3. Move diagnostics to `tests/`, `scripts/`, or delete them.
4. Choose one supported ingestion path; retain the legacy parser only as an
   explicitly tested compatibility adapter if required.
5. Add a test that enumerates public MCP tools and rejects debug-only tools.

---

### R-12 — AI and tool calls lack a unified operational contract

**Evidence**

- `insight_server.py:43-46` has a retry decorator for one Groq call.
- `report_server.py:73-82` performs a direct request without an explicit
  timeout.
- `ingestion_intelligence_server.py:231-253` has provider-specific requests
  and a separate fallback implementation.
- `tools/mcp_client.py:40-62` has no request budget, correlation ID, or
  structured tool audit record.
- Model allow-list/fallback logic is duplicated in insight and report code.

**Impact**

Latency, cost, retries, and provider behavior are inconsistent. A report call
can hang longer than the insight call. There is no reliable audit trail for
which model or tool produced a result.

**Recommended refactor**

Create:

```text
cji_agent/integrations/
  llm_client.py
  mcp_gateway.py
  retry_policy.py
  telemetry.py
```

The adapters should own timeouts, retries, model allow-lists, JSON parsing,
token/cost budgets, correlation IDs, redaction, and metrics. Business services
should receive typed interfaces, not call `requests` directly.

---

## 5. P2 quality and performance findings

### R-13 — Sequential per-step AI work

`agents/workers.py:175-253` generates, prioritizes, saves, and ranks insights
one operation at a time. This is simple and safe for a PoC but will become slow
as critical steps increase.

**Refactoring choice**

- Retain sequential execution for deterministic ordering and provider safety.
- Add bounded concurrency with an async semaphore after idempotency and rate
  limits exist.
- Batch model requests where the provider and output schema support it.

**Recommendation:** do not parallelize first. Establish run IDs, deduplication,
retry semantics, and provider budgets before adding concurrency.

### R-14 — Import path manipulation and missing package metadata

Files such as `friction_engine_server.py`, `synthetic_data.py`,
`guardrails/output_validator.py`, tests, and utility scripts modify `sys.path`
at runtime.

**Impact**

Import behavior depends on the working directory and entrypoint. This is
fragile in Uvicorn, subprocesses, test runners, IDEs, and deployment images.

**Recommended refactor**

Add a root `pyproject.toml`, make `cji_agent` an installable package, define
console scripts, and use absolute package imports. Keep script wrappers only for
backward compatibility.

### R-15 — Streamlit dashboard is a mixed-responsibility compatibility client

`cji_agent/dashboard.py` contains UI, direct data access helpers, fallback
analytics, pipeline execution, and session-state management in one large
module. This is acceptable for a prototype but not a durable product boundary.

**Recommended refactor**

Extract:

```text
dashboard/
  app.py
  api_client.py
  view_models.py
  charts.py
  session.py
```

Then make the dashboard call the same API contracts as the future Next.js
frontend. Do not allow the dashboard to become a second business-logic
implementation.

---

## 6. Documentation cleanup plan

### Current-state documents

Keep and maintain:

- `project_summary.md` — current architecture and target direction.
- `README.md` — supported local setup and verified demo workflow.
- `docs/6-API-Contracts.md` — versioned API contract.
- `docs/5-Database-Schema.md` — executable schema/migration reference.
- `docs/12-Testing-Strategy.md` — test policy and CI gates.

### Historical documents

Move or clearly label:

- `Project Details/PRD.md`
- `Project Details/ARCHITECTURE.md`
- `Project Details/MVP_TECH_DOC.md`
- `Project Details/SYSTEM_DESIGN.md`

These are useful design history, but they must not be presented as the current
implementation contract.

### Files requiring immediate correction

| File | Problem |
|---|---|
| `Project_Memory.md` | Contradicts itself about whether code exists and whether phases are complete. |
| `Project_status.md` | Claims v2 feature completeness while noting unfinished live validation and uses stale paths. |
| `README.md` | Describes four MCP services and provider behavior that no longer match all implementation paths. |
| `docs/4-System-Architecture.md` | Mixes PoC stdio/DuckDB assumptions with future HTTP/PostgreSQL architecture. |
| `docs/5-Database-Schema.md` | Describes schemas that do not consistently match `collector/api.py` and journey queries. |
| `docs/6-API-Contracts.md` | Documents endpoints and response models not all implemented by the collector. |
| `docs/7-Monorepo-Structure.md` | Describes an older file tree and omits the current ingestion implementation. |
| `docs/11-Environment-and-DevOps.md` | Lists future Docker/CI behavior as documentation but lacks executable configuration. |

### Documentation standard going forward

Every current-state claim must have one of:

1. an executable test;
2. an executable configuration/schema;
3. a source-code reference with a checked line range; or
4. an explicit “planned” label.

Avoid phrases such as “complete,” “production-ready,” or “single source of
truth” unless CI verifies the claim.

---

## 7. Recommended target structure

This is an incremental target, not a requirement to rewrite every module at
once.

```text
cji_agent/
├── domain/
│   ├── events.py
│   ├── metrics.py
│   ├── insights.py
│   ├── runs.py
│   └── errors.py
├── application/
│   ├── ingestion_service.py
│   ├── analysis_service.py
│   ├── report_service.py
│   └── policies.py
├── infrastructure/
│   ├── settings.py
│   ├── repositories/
│   ├── llm/
│   ├── mcp/
│   ├── queues/
│   ├── storage/
│   └── telemetry/
├── interfaces/
│   ├── api/
│   ├── cli/
│   └── dashboard/
├── workers/
├── mcp_servers/
├── tests/
└── pyproject.toml
```

The domain/application layers must not import FastAPI, Streamlit, requests,
DuckDB, ChromaDB, or provider SDKs directly. Infrastructure implements those
interfaces. This makes the deterministic scoring engine and workflow policies
testable without network services.

---

## 8. Refactoring sequence with safety gates

### Stage 1 — Establish a clean baseline

- Run the current test suite and record the result.
- Add lint/type-check tooling without changing behavior.
- Remove unused imports and `test_dummy`.
- Fix obvious endpoint mismatch R-01.
- Correct current documentation labels.

**Gate:** tests pass; no public behavior changes except the ingestion endpoint
correction and removal of debug-only tools.

### Stage 2 — Consolidate contracts

- Create canonical event/insight/run/error models.
- Replace duplicate collector and ingestion models with adapters.
- Version API responses.
- Add contract tests for every MCP tool and collector endpoint.

**Gate:** fixture payloads produce identical canonical records through tracker,
collector, file ingestion, and test factories.

### Stage 3 — Isolate infrastructure

- Add typed settings and service registry.
- Introduce repository interfaces for demo and realtime data.
- Remove SQL string replacement and interpolate-free query construction.
- Centralize LLM/MCP calls with timeouts, retries, budgets, and telemetry.

**Gate:** demo mode runs without external services; realtime mode fails clearly
when its dependency is unavailable; all failures have correlation IDs.

### Stage 4 — Secure runtime boundaries

- Explicit CORS and required secrets.
- Hashed/revocable API keys.
- Upload limits and safe staging.
- HTML escaping/CSP.
- Role/tenant authorization groundwork.
- Secret/dependency scanning in CI.

**Gate:** security tests cover authentication, injection, file handling, output
escaping, and tenant boundaries.

### Stage 5 — Durable jobs and frontend migration

- Move background work to a durable queue.
- Persist analysis runs and approvals.
- Expose a versioned backend API.
- Build Next.js as the primary frontend.
- Keep Streamlit/CLI as compatibility clients until parity is proven.

**Gate:** end-to-end browser tests pass through ingestion, review, analysis,
approval, report generation, retry, and cancellation.

### Stage 6 — Optimize and delete

- Add bounded concurrency where measured.
- Add caching only with invalidation rules.
- Delete superseded adapters, diagnostic scripts, and historical runtime paths.
- Update architecture docs from the final deployed topology.

**Gate:** no unused public tools, no undocumented entrypoints, no stale
configuration names, and no unresolved P0/P1 findings.

---

## 9. Definition of done for senior-level code quality

The codebase should not be considered professionally refactored until all of
the following are true:

- one canonical schema exists per domain concept;
- one service registry defines runtime endpoints and transport;
- all external values use typed validation and parameterized persistence;
- no production endpoint uses wildcard credentialed CORS;
- no known/default secret can authenticate a shared deployment;
- generated HTML and JavaScript safely encode untrusted content;
- all background work has durable status and accurate result semantics;
- broad exception handlers are limited to deliberate process boundaries;
- failures preserve causes, classify retryability, and carry correlation IDs;
- demo and realtime data sources share repository contracts;
- public MCP tools contain no debug/test methods;
- the package can be installed and invoked from any working directory;
- tests cover contracts, failure modes, and security-sensitive boundaries;
- current documentation is generated or verified from executable contracts;
- old implementation paths are removed rather than left “temporarily” forever.

---

## 10. Suggested tooling

Add only what the repository can enforce:

| Tool | Purpose |
|---|---|
| Ruff | Formatting, unused imports, common Python correctness checks |
| Pyright or mypy | Static type checking of domain and application layers |
| pytest + coverage | Unit, contract, integration, and coverage gates |
| Bandit | Python security linting |
| pip-audit | Dependency vulnerability checks |
| detect-secrets or equivalent | Secret scanning |
| pre-commit | Consistent local quality hooks |
| OpenTelemetry | Cross-service traces and metrics |
| Playwright | Next.js and collector end-to-end tests |

Tooling should be introduced in warning mode, then promoted to required CI
checks after the first cleanup pass.

