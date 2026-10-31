# Customer Journey Intelligence (CJI)

## Project summary

Customer Journey Intelligence (CJI) is an AI-assisted UX analytics platform for
turning browser and imported product telemetry into:

1. journey-level and step-level behavioral metrics;
2. deterministic friction scores;
3. AI-generated root-cause insights and recommended fixes;
4. prioritized remediation work; and
5. an executive HTML report for product and technology leadership.

The repository is currently a Python-first proof of concept. It supports a local
demo mode using synthetic Parquet data and a realtime mode using browser events
collected through FastAPI and persisted through a SQL-compatible backend. It also
contains a smart-ingestion path for CSV, JSON, JSONL, Excel, and Parquet files
from sources such as GA4, Hotjar, UXCam, surveys, and support exports.

The current system proves the core analytics and AI workflow. It is not yet a
production multi-tenant web product: the main user interface is Streamlit, data
contracts are duplicated in several places, runtime/database assumptions have
drifted between code and documents, and security and operational controls need
to be strengthened before a broad deployment.

---

## 1. Current product capabilities

| Capability | Current implementation |
|---|---|
| Browser telemetry | `cji_agent/tracker/tracker.js` captures journey events and batches them to the collector. |
| Realtime collection | FastAPI application in `cji_agent/collector/api.py`. |
| Demo data | Faker-based synthetic event generation to `cji_agent/data/events.parquet`. |
| File ingestion | Smart ingestion MCP accepts CSV, JSON, JSONL, Excel, and Parquet. |
| Schema mapping | LLM-assisted field mapping with a SHA-256 column-fingerprint registry cache. |
| Data quality | Pydantic validation, timestamp normalization, event-type coercion, URL sanitization, and user identifier anonymization. |
| Journey analytics | Mode-aware data MCP computes step metrics, funnel drop-off, event samples, and live snapshots. |
| Friction analysis | Pure deterministic scoring engine using abandonment, errors, dwell time, retries, and rage clicks. |
| AI insights | LLM root-cause analysis with pre-LLM sanitization and post-LLM output validation. |
| Prioritization | Impact/effort-based ranking of recommended fixes. |
| Persistence | Parquet/DuckDB or SQL event data, ChromaDB insight vectors, and SQLite LangGraph checkpoints. |
| Workflow orchestration | LangGraph supervisor/worker graph with ingestion, data, friction, insight, and report workers. |
| Human approval | Graph pauses before report generation unless auto-approval is selected. |
| Reporting | Self-contained HTML report with narrative, funnel chart, and prioritized insights. |
| Presentation | Streamlit dashboard, CLI, generated HTML report, and tracker embed snippets. |
| Observability | Python logging and optional LangSmith tracing configuration. |

---

## 2. Current repository structure

```text
TCS-CJI/
├── cji_agent/
│   ├── agents/
│   │   ├── supervisor.py
│   │   ├── workers.py
│   │   └── ingestion_worker.py
│   ├── collector/
│   │   ├── api.py
│   │   └── models.py
│   ├── guardrails/
│   │   ├── output_validator.py
│   │   ├── rate_limiter.py
│   │   └── sanitiser.py
│   ├── mcp_servers/
│   │   ├── journey_data_server.py
│   │   ├── friction_engine_server.py
│   │   ├── ingestion_intelligence_server.py
│   │   ├── insight_server.py
│   │   └── report_server.py
│   ├── tools/
│   │   ├── mcp_client.py
│   │   ├── ingest_json.py
│   │   └── synthetic_data.py
│   ├── tracker/
│   │   ├── tracker.js
│   │   └── snippet_generator.py
│   ├── tests/
│   ├── config.py
│   ├── state.py
│   ├── graph.py
│   ├── main.py
│   └── dashboard.py
├── Dataset/
├── docs/
├── Project Details/
├── .stitch/designs/
├── README.md
├── Project_Memory.md
└── Project_status.md
```

The repository contains both implementation and extensive design documentation.
`Project_Memory.md`, `Project_status.md`, and `docs/` should be treated as
historical/design references and reconciled with executable code during the
refactor.

---

## 3. Current architecture

### 3.1 Layered view

```text
Client websites / imported files
        │
        ├── tracker.js ──► FastAPI collector ──► SQL event store
        └── CSV/JSON/XLSX/Parquet ──► Smart ingestion
                                         │
                                         ▼
                              Canonical CJI event schema
                                         │
                                         ▼
                              Journey Data MCP boundary
                                         │
                                         ├──► Friction Engine MCP
                                         ├──► Insight MCP + vector store + LLM
                                         └──► Report MCP + LLM + HTML output
                                         │
                                         ▼
                         LangGraph supervisor/worker workflow
                                         │
                         Streamlit / CLI / HTML report
```

### 3.2 Data collection and ingestion

#### Browser tracking

The browser tracker is a dependency-light JavaScript IIFE. It produces events
such as `page_view`, `click`, `form_submit`, `error`, `rage_click`, `abandon`,
`step_complete`, and `identify`. It uses batching and browser delivery
mechanisms intended to reduce impact on the host application.

The collector validates event shape through Pydantic models. Important fields
include event ID, anonymous user ID, session ID, journey ID, step ID, event type,
timestamp, duration, URL, and metadata.

#### Smart ingestion

`ingestion_intelligence_server.py` loads supported files into pandas, samples
rows, asks an LLM to map source fields to the canonical CJI event schema, and
stores the mapping by a column fingerprint. The transformation stage:

- renames mapped fields;
- derives missing journey, step, session, and event identifiers;
- normalizes timestamps and durations;
- sanitizes URLs;
- anonymizes email-like or oversized user identifiers;
- coerces unknown event types to a safe default;
- packs unmapped fields into metadata; and
- validates transformed records with Pydantic.

Mappings below the configured confidence threshold are intended to be held for
human review rather than silently ingested.

### 3.3 Canonical event model

The intended canonical event shape is:

```text
event_id       unique event identifier
user_id        anonymous user identifier
session_id     browser/session identifier
journey_id     journey being analyzed
step_id        step within the journey
event_type     controlled event taxonomy
timestamp      UTC event timestamp
duration_ms    non-negative duration
url            sanitized URL
metadata       JSON event-specific attributes
```

The event taxonomy is currently:

```text
page_view
click
form_submit
error
rage_click
abandon
step_complete
identify
```

### 3.4 Analytics and friction scoring

The Journey Data MCP is the mode boundary. In demo mode it reads Parquet
through DuckDB. In realtime mode it queries a SQL backend. It exposes step
metrics, funnel drop-off, event samples, system information, and live snapshots.

The friction engine is deterministic and should remain independent of LLM
behavior. It combines normalized signals using the current documented weights:

```text
abandonment  35%
errors       25%
dwell time   15%
retries      15%
rage clicks  10%
```

The score is bounded to 0–100. Steps at or above the configured threshold are
marked critical and passed to the insight workflow.

### 3.5 AI insight and reporting flow

For each critical step:

1. friction data is sanitized before entering an LLM prompt;
2. the insight service requests structured root-cause output;
3. the response is validated and coerced to a safe schema;
4. the insight is prioritized by impact and effort;
5. the result is stored in ChromaDB for semantic search; and
6. the report service generates an executive narrative and HTML report.

The system has LLM retry and fallback behavior. LLM failure should produce an
explicit degraded result and workflow error rather than blocking the full
analysis graph.

### 3.6 LangGraph workflow

The graph uses a shared typed blackboard (`CJIState`):

```text
START
  │
  ▼
Supervisor
  ├── Ingestion Worker (when files are pending)
  ├── Data Worker
  ├── Friction Worker
  ├── Insight Worker
  ├── Human approval checkpoint
  └── Report Worker
          │
          ▼
         END
```

The supervisor routes based on state completion and iteration limits. Workers
return partial state updates and record status/errors. SQLite checkpoints are
used to pause and resume the graph around human approval.

---

## 4. Current technology stack

### Runtime and application

| Area | Technology | Role |
|---|---|---|
| Language | Python 3.11+ | Core application, analytics, orchestration, APIs |
| Browser client | Vanilla JavaScript | Lightweight telemetry tracker |
| API | FastAPI + Uvicorn | Event collector and operational endpoints |
| UI | Streamlit | Current dashboard and approval interface |
| CLI | Python `argparse` | Demo, ingestion, run, and approval commands |
| Validation | Pydantic v2 | Collector and ingestion contracts |

### AI and workflow

| Technology | Role |
|---|---|
| LangGraph | Stateful supervisor/worker workflow |
| LangChain Core | Message and graph integration |
| FastMCP / MCP | Domain tool boundaries and server interfaces |
| Groq and/or Anthropic HTTP APIs | LLM inference |
| Sentence Transformers | Local embeddings for semantic insight retrieval |
| LangSmith | Optional tracing and workflow observability |

### Data and persistence

| Technology | Current role | Production direction |
|---|---|---|
| Parquet | Demo event file | Retain for export/archive and offline fixtures |
| DuckDB | Local analytical querying | Retain for local analytics; isolate from production writes |
| SQLAlchemy + PostgreSQL-compatible backend | Realtime event persistence | Standardize on managed PostgreSQL/TimescaleDB |
| ChromaDB | Local insight vector store | Move to pgvector or a managed vector service |
| SQLite | LangGraph checkpoint persistence | Move to Redis/PostgreSQL-backed durable checkpoints |
| JSON registry | Ingestion mapping cache | Move to database-backed versioned registry |

### Development and testing

| Area | Current state |
|---|---|
| Tests | pytest unit and integration-oriented tests under `cji_agent/tests/` |
| Test focus | friction scoring, collector models, synthetic data, agent/worker behavior, ingestion |
| CI/CD | Not represented as a complete production pipeline in the repository |
| Packaging | requirements files and application-style imports rather than a packaged monorepo |
| Deployment | Local/Render-oriented operational notes; container and Kubernetes plans are documented but not implemented |

---

## 5. Current API and integration surfaces

### Collector API

The implemented collector includes:

```text
GET  /health
GET  /tracker.js
POST /collect/batch
GET  /live/stats
POST /admin/api-keys
```

The design documents also describe a live event feed endpoint and richer response
contracts. These must be checked against the actual running API before being
treated as supported public contracts.

### MCP services

The current repository contains five MCP-oriented services:

| Service | Responsibility |
|---|---|
| Ingestion Intelligence | Detect, map, validate, and ingest arbitrary source files |
| Journey Data | Read and aggregate canonical events |
| Friction Engine | Deterministic scoring and signal detection |
| Insight | LLM analysis, vector persistence, search, and ranking |
| Report | Executive narrative generation and HTML report export |

The code currently uses a mixture of SSE/HTTP-style MCP startup and direct HTTP
calls. The refactor should choose one production transport and document it as a
versioned internal contract.

---

## 6. Important implementation gaps found during analysis

These are upgrade risks, not claims that the PoC cannot demonstrate its core
workflow.

### Contract and architecture drift

- Several documents describe four MCP servers while the implementation includes
  a fifth smart-ingestion service.
- Some design documents describe DuckDB realtime tables, while collector code
  creates PostgreSQL-style tables through SQLAlchemy.
- Event schemas are duplicated across `collector/models.py`, collector API
  models, ingestion models, state types, tracker code, and documentation.
- Some module comments and operational documents describe older behavior, such
  as stdio MCP transport or LiteLLM-first provider routing, while implementation
  code uses HTTP requests and SSE-oriented services.
- Port assignments and service URLs are not fully centralized.

### Security and reliability risks to resolve before production

- CORS is permissive (`allow_origins=["*"]`) and allows credentials; this must
  be replaced with explicit origin policy.
- API-key handling is currently simple shared-key authentication. Production
  needs scoped, revocable, hashed credentials or signed tenant tokens.
- Development/live keys and deployment-specific values appear in application
  setup paths and must never be seeded into shared environments.
- SQL construction uses interpolated values in multiple analytics queries.
  Parameters and allow-listed identifiers must be used consistently.
- Uploaded files need size limits, content-type validation, safe staging,
  malware scanning, path isolation, and retention/deletion policy.
- Report HTML interpolates generated content and must escape untrusted text;
  external chart assets should be version-pinned or self-hosted.
- LLM prompts and tool calls need explicit trust boundaries, maximum payloads,
  prompt-injection defenses, model allow-lists, and audit records.
- Background tasks and keep-alive behavior require lifecycle management,
  cancellation, bounded retries, and health/readiness separation.
- Error shapes, status codes, and response models are not yet consistently
  versioned across the documented and implemented APIs.

### Operational risks

- Local file stores are not sufficient for concurrent multi-user production
  workloads.
- The workflow is mostly sequential; parallel-safe work and long-running jobs
  need a durable job model rather than request-bound execution.
- There is no clearly enforced idempotency contract for every ingestion and
  analysis operation.
- Observability is primarily logs; production needs structured traces, metrics,
  correlation IDs, audit events, queue visibility, and alerting.

---

## 7. Proposed production target architecture

The recommended refactor keeps the proven analytical core but replaces the
single-process presentation/runtime model with explicit web, API, worker, and
storage boundaries.

```text
Next.js web application
  ├── authenticated dashboard
  ├── journey configuration
  ├── ingestion upload/review
  ├── analysis run history
  ├── insight review and approval
  └── report/export experience
          │
          ▼
API gateway / backend-for-frontend
  ├── authentication and session validation
  ├── tenant/project authorization
  ├── rate limits and request validation
  ├── signed upload URLs
  ├── analysis job creation
  └── websocket/SSE job progress
          │
          ├── Event ingestion service
          ├── Analysis orchestration service
          ├── MCP tool services
          ├── Report/export service
          └── Background job workers
          │
          ├── PostgreSQL + TimescaleDB + pgvector
          ├── Redis queues/checkpoints/cache
          ├── Object storage for uploads/reports
          └── OpenTelemetry/LangSmith/central logs
```

### 7.1 Next.js frontend

Use Next.js with TypeScript as the product interface:

- server-side rendering for authenticated shell and shareable report views;
- client components for charts, live analysis progress, and interactive filters;
- route-level authorization checks;
- React Query or an equivalent server-state layer for API caching and retries;
- typed API client generated from OpenAPI;
- strict Content Security Policy and secure headers;
- accessible dashboard components with keyboard navigation and loading/error
  states;
- resumable upload UI with validation and human mapping review;
- live job progress through SSE or WebSocket, not polling-only loops;
- versioned report pages rather than direct filesystem paths.

The existing `useCJITracker.js` concept should become a maintained TypeScript
package/hook for Next.js route transitions, with a stable event contract and
privacy-safe defaults.

### 7.2 Backend-for-frontend and API

Create a versioned API boundary, for example `/api/v1`, with separate modules
for:

```text
/auth
/organizations
/projects
/journeys
/events
/ingestion
/analysis-runs
/insights
/reports
/admin
/health
/metrics
```

The API should own authorization, validation, idempotency, pagination, audit
events, and response contracts. The frontend must not call MCP servers or
databases directly.

### 7.3 Durable workflow execution

Move long-running analysis from an interactive request into a durable job:

1. API creates an analysis run and idempotency key.
2. Queue accepts the run.
3. Orchestrator loads canonical data and starts the graph.
4. Workers execute with bounded retries and checkpoint after each stage.
5. Human review changes run state to `awaiting_review`.
6. Approval resumes the same run.
7. Report generation stores an immutable report artifact and metadata.
8. UI receives state changes through SSE/WebSocket.

Every job needs a correlation ID, tenant/project ID, actor ID, status, timestamps,
attempt count, error code, and safe diagnostic message.

### 7.4 Storage model

Standardize the production model on PostgreSQL:

- tenant, organization, project, journey, API credential, and user tables;
- partitioned event tables with indexes on tenant, journey, timestamp, session,
  and step;
- JSONB metadata with controlled size and indexed fields only where justified;
- pgvector for insight retrieval and source-specific embeddings;
- immutable analysis-run and insight-version records;
- object storage for raw uploads and generated reports;
- Redis for queue coordination, short-lived cache, rate limits, and workflow
  coordination where appropriate.

DuckDB and Parquet remain valuable for local development, reproducible fixtures,
large offline exports, and migration validation, but should not be the primary
multi-user write path.

---

## 8. Industrial-grade security baseline

### Identity and access

- Use OIDC/OAuth2 through a trusted identity provider.
- Use short-lived access tokens and rotating refresh sessions.
- Enforce organization/project membership and role-based permissions.
- Separate platform administrators, project administrators, analysts, reviewers,
  and read-only users.
- Scope tracker credentials to a project/journey and rotate/revoke them.
- Hash stored API keys; display them only once.

### Tenant isolation and authorization

- Put tenant/project scope on every event, upload, run, insight, and report.
- Enforce authorization in the backend and database policies, not only in the UI.
- Use PostgreSQL row-level security where practical.
- Never trust tenant identifiers supplied by a browser without deriving them from
  the authenticated principal.

### Secrets and supply chain

- Use a managed secret store in deployed environments.
- Remove all real/development credentials from seed paths and tracked artifacts.
- Pin dependencies and scan them for vulnerabilities.
- Use signed container images and minimal runtime images.
- Run static analysis, dependency scanning, secret scanning, and SBOM generation
  in CI.

### Ingestion and data protection

- Enforce upload size, row count, timeout, and decompression limits.
- Allow-list file formats and inspect file signatures, not only extensions.
- Store uploads outside the application source tree with randomized object IDs.
- Scan uploads and delete temporary files according to retention policy.
- Encrypt data in transit and at rest.
- Minimize raw PII, hash or tokenize identifiers, and provide deletion workflows.
- Redact sensitive values from logs, traces, prompts, and error responses.

### API and browser security

- Replace wildcard CORS with explicit environment-specific origins.
- Use CSRF protection for cookie-authenticated mutations.
- Apply per-user, per-project, and per-key rate limits.
- Validate all inputs with strict schemas and parameterized queries.
- Add secure headers, CSP, HSTS, clickjacking protection, and safe cookie flags.
- Add request size limits, timeout budgets, replay protection, and idempotency
  keys to mutating endpoints.

### AI security and governance

- Treat imported data, retrieved documents, and model output as untrusted.
- Use fixed system instructions and structured tool schemas.
- Keep secrets and privileged tools out of model-visible context.
- Allow-list models and tools per environment.
- Validate model output against typed schemas; reject unsafe or incomplete output.
- Record model, prompt template version, tool calls, latency, token usage, and
  reviewer decision without retaining unnecessary raw PII.
- Require human approval for low-confidence mappings, destructive actions, and
  externally published reports.
- Maintain a kill switch and degraded deterministic fallback path.

---

## 9. Reliable AI workflow design

The target workflow must be restartable, observable, and safe under partial
failure.

### State machine

```text
created
  → validating
  → ingesting
  → awaiting_mapping_review
  → analyzing
  → awaiting_insight_review
  → generating_report
  → completed

Any active state
  → retrying
  → failed
  → cancelled
```

### Required workflow properties

- Durable state after every meaningful stage.
- Idempotent operations keyed by run ID and input fingerprint.
- Bounded retries with exponential backoff and jitter.
- Dead-letter handling for permanently failed jobs.
- Per-step timeouts and cancellation.
- Explicit partial-success semantics.
- Human review queues with expiration and reassignment.
- Deterministic friction scoring independent of model availability.
- Schema-versioned prompts and output contracts.
- Replayable fixtures for debugging and regression tests.
- No infinite agent loops; hard iteration and cost budgets.
- Safe fallback narrative/report when LLM services are unavailable.

---

## 10. Recommended migration sequence

### Phase 0 — Baseline and contract stabilization

- Make executable code the source of truth for current behavior.
- Consolidate event, insight, API, and workflow schemas.
- Add contract tests for collector, ingestion, MCP tools, and graph states.
- Centralize service URLs, ports, feature flags, and environment validation.
- Fix SQL parameterization, CORS, credential seeding, and output escaping.

**Exit gate:** current demo and realtime smoke flows pass with reproducible
fixtures and no known secret or injection issues in the changed surfaces.

### Phase 1 — Production data and job foundations

- Introduce PostgreSQL schema migrations and tenant/project ownership.
- Add object storage for uploads and reports.
- Add Redis-backed queueing and durable analysis-run records.
- Keep the current CLI and Streamlit dashboard operational as compatibility
  clients.

**Exit gate:** an analysis run can be created, resumed, retried, cancelled, and
audited without holding an HTTP request open.

### Phase 2 — Secure API platform

- Build `/api/v1` with OpenAPI contracts.
- Add OIDC authentication, RBAC, tenant isolation, rate limits, audit events,
  and idempotency.
- Wrap current analytical services behind internal authenticated interfaces.
- Add structured logs, metrics, traces, and correlation IDs.

**Exit gate:** API contract, authorization, security, and integration tests pass
for all supported roles and tenant boundaries.

### Phase 3 — Next.js application

- Build the authenticated dashboard and project/journey management screens.
- Add ingestion upload, mapping review, analysis run history, live progress,
  insight review, and report pages.
- Replace direct filesystem report access with authorized report artifacts.
- Publish the typed tracker package/hook for Next.js integrations.

**Exit gate:** Playwright tests cover the critical user journeys from login
through upload, review, analysis, approval, and report download.

### Phase 4 — Cutover and hardening

- Run old and new interfaces against the same backend for a controlled period.
- Compare scoring, insight schemas, report content, and run outcomes.
- Load-test event ingestion and concurrent analysis jobs.
- Perform threat modeling, dependency scanning, secret scanning, and penetration
  testing.
- Deprecate Streamlit/CLI paths only after operational parity is demonstrated.

**Exit gate:** production readiness review, rollback plan, disaster recovery
test, and documented on-call procedures are complete.

---

## 11. Testing and quality strategy

### Unit tests

- friction formula and threshold boundaries;
- canonical event validation and sanitization;
- ingestion transformations and fingerprint caching;
- supervisor routing and iteration limits;
- output validators and fallback behavior;
- authorization policy functions;
- report escaping and serialization.

### Integration tests

- collector with a temporary PostgreSQL-compatible database;
- ingestion against representative GA4/Hotjar/UXCam/survey fixtures;
- MCP tool contracts and transport;
- queue/orchestrator/checkpoint lifecycle;
- pgvector retrieval and report artifact persistence;
- tenant and role isolation.

### End-to-end tests

- tracker event collection;
- upload → mapping review → ingestion;
- analysis run → human approval → report;
- LLM unavailable/degraded mode;
- retry, cancellation, duplicate request, and partial failure behavior.

### Performance and resilience

- sustained event ingestion rate;
- concurrent analysis runs;
- large-file ingestion limits;
- queue backpressure;
- database query plans and retention jobs;
- service restart and checkpoint recovery;
- controlled provider timeout and outage tests.

Every deployment should require formatting, type checking, unit tests, contract
tests, security scans, and a smoke deployment check.

---

## 12. Definition of a successful refactor

The refactor is successful when:

- the Next.js application is the primary user experience;
- the backend exposes stable, typed, versioned APIs;
- every resource is authenticated, authorized, tenant-scoped, and auditable;
- event ingestion is durable, idempotent, rate-limited, and horizontally scalable;
- the AI workflow is checkpointed, resumable, cost-bounded, and safe under model or
  tool failure;
- deterministic analytics remain reproducible across environments;
- uploads, prompts, reports, and logs follow a documented privacy policy;
- PostgreSQL/pgvector/object storage/Redis provide production persistence;
- the legacy CLI/Streamlit experience can be removed without losing capability;
- CI/CD and observability provide evidence that the system works rather than only
  indicating that a process started.

---

## Evidence used for this summary

Primary implementation references:

- `cji_agent/config.py`
- `cji_agent/state.py`
- `cji_agent/graph.py`
- `cji_agent/agents/supervisor.py`
- `cji_agent/agents/workers.py`
- `cji_agent/agents/ingestion_worker.py`
- `cji_agent/collector/api.py`
- `cji_agent/collector/models.py`
- `cji_agent/mcp_servers/journey_data_server.py`
- `cji_agent/mcp_servers/ingestion_intelligence_server.py`
- `cji_agent/mcp_servers/insight_server.py`
- `cji_agent/mcp_servers/report_server.py`
- `cji_agent/guardrails/`
- `cji_agent/tracker/`
- `cji_agent/tests/`

Design and operational references:

- `README.md`
- `Project_Memory.md`
- `Project_status.md`
- `docs/4-System-Architecture.md`
- `docs/5-Database-Schema.md`
- `docs/6-API-Contracts.md`
- `docs/7-Monorepo-Structure.md`
- `docs/11-Environment-and-DevOps.md`
- `docs/12-Testing-Strategy.md`
