# Kiro Prompts for the CJI Upgrade

Use these prompts in Kiro one Spec at a time. Do not create one giant Spec for
the whole repository. Review `requirements.md`, `design.md`, and `tasks.md`
before implementation, and commit only after the validation gate passes.

Read these repository documents before starting:

- `project_summary.md`
- `refactoring.md`
- `kiro_upgrade_guide.md`
- `free_plan_workflow.md`

## Prompt 0 — Kiro onboarding and baseline

```text
Onboard this existing Customer Journey Intelligence repository for a staged
production refactor. Do not change runtime code yet.

Read:
- project_summary.md
- refactoring.md
- kiro_upgrade_guide.md
- README.md
- Project_Memory.md
- Project_status.md
- cji_agent/
- docs/

Create a Kiro Spec with requirements.md, design.md, and tasks.md that records:
- current startup commands;
- supported Python and Node.js versions;
- dependency installation requirements;
- test, lint, and type-check commands;
- CLI, Streamlit, collector, MCP, and report entry points;
- service ports and transports;
- storage backends and data paths;
- environment variables and secret requirements;
- documentation-versus-code contradictions;
- known test failures and missing tools;
- a safe phase order for the refactor.

Run available baseline checks without changing application code. If a tool or
dependency is missing, record the exact command and blocker. Do not claim a
check passed if it could not run.

Acceptance criteria:
- requirements.md, design.md, and tasks.md are complete;
- current behavior is distinguished from the target architecture;
- baseline failures are recorded separately from future failures;
- no runtime source file is modified.
```

## Prompt 1 — P0 correctness and security fixes

```text
Create a Kiro Bugfix Spec and implement only refactoring.md findings R-01
through R-05.

Fix:
1. ingestion_worker.py calling the wrong MCP port;
2. demo-mode health checks using the PostgreSQL path;
3. SQL interpolation and ad-hoc placeholder replacement;
4. wildcard credentialed CORS, unsafe default administrator credentials, and
   seeded live API keys;
5. unsafe interpolation of untrusted content into generated HTML/JavaScript.

Requirements:
- use the existing MCP service mapping or typed service configuration;
- bind SQL values and allow-list dynamic identifiers;
- preserve offline demo mode;
- fail closed outside explicit development mode;
- never seed known production credentials;
- escape HTML and JavaScript contexts correctly;
- add focused regression tests for every issue;
- do not perform the broader architecture refactor in this Spec.

Acceptance criteria:
- targeted tests cover all five findings;
- demo mode does not require PostgreSQL;
- injection, CORS, credential, and report-rendering tests pass;
- no insecure production default remains in the changed paths.
```

## Prompt 2 — Canonical domain contracts

```text
Create one authoritative contract layer for CJI.

Consolidate definitions for:
- browser events and event types;
- journey and session identifiers;
- step metrics and funnel results;
- friction scores;
- insight results and recommendations;
- report results;
- workflow status, errors, and approval state.

Use the strongest existing typed validation patterns. Keep external API,
internal domain, and persistence models distinct where necessary, but define
explicit conversions between them.

Requirements:
- preserve the current event taxonomy and friction weights;
- preserve collector and workflow compatibility;
- reject invalid data explicitly;
- remove duplicate sources of truth;
- add serialization, compatibility, and invalid-input tests;
- update only documentation made false by this change.

Acceptance criteria:
- all changed callers use the canonical contracts;
- old representations have compatibility coverage;
- type checking passes for changed code;
- no duplicate active schema remains without an explicit adapter reason.
```

## Prompt 3 — Typed configuration and service discovery

```text
Create a Kiro Feature Spec to centralize runtime configuration and service
discovery.

Cover:
- application mode;
- logical service names and endpoints;
- ports and transports;
- database URLs and storage paths;
- LLM provider settings;
- timeouts, retry limits, and budgets;
- CORS origins;
- authentication and API-key configuration.

Requirements:
- use one typed service registry;
- support explicit development, test, and production behavior;
- never use a known production secret as a default;
- validate configuration at startup;
- provide actionable configuration errors;
- allow tests to inject endpoints and temporary storage;
- preserve offline demo mode;
- migrate callers incrementally.

Acceptance criteria:
- changed production paths contain no duplicated service ports;
- missing and invalid configuration tests pass;
- development, test, and production settings are covered;
- all startup paths resolve required services.
```

## Prompt 4 — Repository and data-access isolation

```text
Create repository interfaces for demo and realtime event data, then migrate
the journey-data service and directly dependent workers.

The boundary must cover:
- health/readiness;
- step metrics;
- funnel drop-off;
- event queries and samples;
- live snapshots;
- ingestion writes where applicable.

Requirements:
- provide DuckDB/Parquet and PostgreSQL-compatible implementations;
- select the implementation once through typed configuration;
- remove repeated mode branching from query functions;
- parameterize all values;
- preserve result shapes and numeric semantics;
- define transaction and idempotency behavior for writes;
- add implementation tests and contract-level parity tests.

Do not optimize concurrency or redesign the database schema here.

Acceptance criteria:
- demo health checks work without PostgreSQL;
- realtime paths do not use demo storage accidentally;
- empty, invalid, and database-failure cases are tested.
```

## Prompt 5 — Dead code and documentation cleanup

```text
Perform a bounded cleanup based on evidence from the current repository.

Inspect:
- unused imports and variables;
- silent pass branches and broad exception handlers;
- test_dummy and non-production MCP tools;
- duplicate ingestion utilities;
- sys.path.insert workarounds;
- stale entry points and unreachable code;
- README.md, Project_Memory.md, Project_status.md, and docs/.

Requirements:
- remove code only when search and tests prove it is obsolete;
- preserve used compatibility entry points;
- replace broad catches with expected exception handling;
- surface structured errors;
- mark historical documents as superseded or update them to executable truth;
- do not delete user-facing functionality silently;
- do not mix architectural redesign into this Spec.

Acceptance criteria:
- removed symbols have no remaining references;
- startup smoke checks and tests pass;
- documentation matches implemented behavior.
```

## Prompt 6 — Collector hardening

```text
Harden the FastAPI collector without changing the meaning of public events.

Implement:
- strict validation using the canonical event contract;
- explicit authentication and authorization;
- safe configurable CORS;
- request and batch-size limits;
- rate limiting;
- idempotency keys or deterministic event identifiers;
- accurate accepted, rejected, and duplicate counts;
- durable write semantics;
- request correlation IDs;
- separate liveness and readiness endpoints.

Requirements:
- define partial-batch failure responses;
- do not log sensitive identifiers or secrets;
- preserve local development behavior only behind explicit configuration;
- test authentication, limits, duplicates, partial failures, and database
  failures.

Acceptance criteria:
- failed persistence is never reported as successful storage;
- retries do not duplicate events;
- collector integration tests pass with a temporary test database.
```

## Prompt 7 — Unified LLM and MCP gateway

```text
Create one typed gateway for LLM and MCP calls used by insight, report, and
workflow workers.

Standardize:
- provider selection;
- request and response types;
- timeouts;
- bounded retries;
- cancellation;
- rate limits;
- token and cost budgets;
- correlation IDs;
- audit metadata;
- redaction and sanitization;
- retryable and non-retryable error classification.

Requirements:
- preserve existing pre-LLM and post-LLM guardrails;
- never expose secrets in exceptions or logs;
- provide deterministic test doubles;
- keep the deterministic friction engine independent;
- do not silently switch providers.

Acceptance criteria:
- insight and report workers use the gateway;
- timeout, retry, budget, cancellation, and malformed-response tests pass;
- audit records contain correlation metadata without sensitive payloads.
```

## Prompt 8 — Durable LangGraph workflow

```text
Make the LangGraph workflow reliable, resumable, and idempotent.

Preserve:
- worker ordering;
- the human approval checkpoint;
- the iteration cutoff;
- deterministic friction calculations;
- CLI and Streamlit invocation compatibility.

Implement:
- durable checkpoint configuration;
- typed state transitions;
- run and step identifiers;
- idempotent workers;
- bounded retries and timeouts;
- resume after process failure;
- structured failure states;
- safe approval and resume behavior;
- workflow audit metadata.

Requirements:
- reruns must not duplicate events, insights, or reports;
- partial runs must be diagnosable;
- remove misleading persistence switches;
- add failure-injection tests for worker boundaries;
- do not introduce unbounded parallelism.

Acceptance criteria:
- interrupted runs resume from a checkpoint;
- failed runs expose structured errors;
- duplicate execution is safe;
- approval and resume tests pass.
```

## Prompt 9 — Safe deterministic reporting

```text
Harden and simplify report generation.

Cover:
- typed report input and output contracts;
- context-correct HTML escaping;
- safe JavaScript data serialization;
- strict content-security policy;
- pinned or self-hosted assets;
- deterministic rendering;
- report size and content limits;
- safe filenames and output paths;
- report metadata and provenance.

Requirements:
- treat all narrative, insight, journey, and user-provided values as untrusted;
- preserve report meaning and chart behavior;
- prevent path traversal and arbitrary file writes;
- make failed generation explicit;
- add malicious-content and snapshot-style tests.

Acceptance criteria:
- XSS payloads render inert;
- reports satisfy the self-contained output contract;
- empty, large, malformed, and malicious inputs are tested.
```

## Prompt 10 — Python packaging

```text
Convert the Python application into a supported installable package.

Implement:
- pyproject.toml;
- supported Python version metadata;
- explicit package boundaries;
- console-script entry points;
- development and test dependency groups;
- import-safe module execution;
- removal of sys.path.insert workarounds;
- reproducible lint, type-check, and test commands.

Requirements:
- preserve current user-facing commands;
- do not upgrade unrelated dependencies without evidence;
- constrain security-sensitive dependencies appropriately;
- document local setup and environment variables;
- verify installation in a clean virtual environment.

Acceptance criteria:
- clean installation succeeds;
- CLI entry points work outside the repository root;
- tests import the installed package rather than checkout-path hacks.
```

## Prompt 11 — Versioned backend API

```text
Create the first stable /api/v1 backend contract for the Next.js frontend.

Cover:
- health;
- projects or journeys;
- events;
- journey metrics;
- friction;
- insights;
- reports;
- workflow status and approval.

Requirements:
- define authentication and authorization;
- validate requests and responses;
- provide pagination and bounded result sizes;
- use stable error envelopes;
- include request IDs;
- define idempotency for mutations;
- maintain accurate OpenAPI documentation;
- keep CLI and Streamlit callers working through adapters;
- do not build the full frontend in this Spec.

Acceptance criteria:
- contract tests cover success, validation, unauthorized, forbidden,
  not-found, conflict, rate-limit, and server-error cases;
- OpenAPI matches actual responses;
- internal exceptions and secrets never reach clients.
```

## Prompt 12 — Next.js foundation

```text
Create the Next.js frontend foundation against the tested /api/v1 contract.

Use:
- TypeScript with strict checking;
- accessible components;
- a typed API client aligned with OpenAPI;
- environment-based backend configuration;
- secure authentication and protected routes;
- loading, empty, retry, and error states.

Implement a thin vertical slice:
- application shell;
- authentication boundary;
- health/status view;
- journey list/detail view;
- friction summary;
- workflow/report status.

Requirements:
- keep business logic in the backend;
- do not expose secrets in browser code;
- preserve Streamlit for comparison;
- add unit/component tests and one browser smoke test;
- make the frontend runnable independently.

Acceptance criteria:
- type check, lint, unit tests, and browser smoke test pass;
- unauthenticated users cannot access protected data;
- API errors are visible and recoverable.
```

## Prompt 13 — Feature parity and gradual migration

```text
Expand Next.js feature by feature while preserving parity with Streamlit and
the CLI.

For each feature:
1. define or verify the backend contract;
2. implement the API if needed;
3. implement the Next.js UI;
4. compare results with the existing surface;
5. add browser and contract tests;
6. document intentional UX differences.

Cover:
- ingestion status and validation feedback;
- journey and funnel analytics;
- friction drill-down;
- AI insight generation and provenance;
- approval and resume workflow;
- report preview and download;
- error, empty, and permission states.

Do not remove Streamlit or CLI until:
- core results match documented tolerances;
- migration and rollback instructions exist;
- browser and integration tests pass;
- users have an operational fallback.
```

## Prompt 14 — Production hardening

```text
Prepare CJI for a controlled production release.

Implement and verify:
- structured logs with correlation IDs;
- metrics and traces;
- audit events;
- secret management and rotation;
- dependency, container, and secret scanning;
- rate limiting and abuse controls;
- database backup and restore;
- migration rollback;
- health and readiness checks;
- failure-injection and recovery tests;
- CI for formatting, lint, types, unit, integration, and browser tests;
- deployment documentation and environment validation.

Requirements:
- isolate development-only defaults;
- verify no sensitive data appears in logs, reports, or client bundles;
- document operational limits and AI budgets;
- do not claim readiness for an unverified control.

Acceptance criteria:
- the release checklist is executable;
- failed checks have owners and blockers;
- rollback is tested, not merely documented.
```

## Prompt 15 — Final principal-engineer review

```text
Perform an evidence-based principal-engineer review of the complete CJI
upgrade. Do not make broad changes automatically.

Review:
- project_summary.md;
- refactoring.md;
- kiro_upgrade_guide.md;
- all Kiro Spec artifacts;
- changed source, tests, configuration, and documentation;
- Git history and migration path;
- API/OpenAPI contracts;
- security and production-readiness evidence.

Check for:
- remaining P0/P1 findings;
- contract and documentation drift;
- insecure defaults or secret leakage;
- data-loss, duplication, retry, and concurrency risks;
- broken demo mode;
- broken CLI/Streamlit compatibility;
- incomplete Next.js behavior;
- missing rollback or observability;
- unsupported readiness claims.

Return:
1. release-blocking findings ranked by severity and confidence;
2. exact file and line evidence;
3. minimal remediation for every finding;
4. tests or operational checks needed to prove remediation;
5. a truthful decision: ready, conditionally ready, or not ready;
6. deferred technical debt.

Do not declare production readiness merely because the build passes.
```

## Universal Kiro task-control prompt

Use this before implementation when a Spec task is ambiguous:

```text
Work only on the current Kiro task.

Before editing:
1. read the task acceptance criteria;
2. inspect the relevant source and tests;
3. list files you intend to change;
4. identify compatibility, security, and rollback risks;
5. stop and report any unresolved ambiguity.

During editing:
- make the smallest complete change;
- preserve existing behavior outside the task;
- do not add secrets or silent fallbacks;
- add regression tests;
- do not modify unrelated files.

After editing:
- run targeted tests, lint, type checks, and smoke checks;
- run git diff --check;
- inspect the final diff;
- report exact commands and results;
- report failed or skipped checks honestly;
- mark the task complete only when acceptance criteria have evidence.
```

## Execution order

```text
0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15
```

Use Graphify locally for architecture discovery before complex Specs when
available. Use ChatGPT Go after each verified slice for independent review.
Use Caveman only for optional concise reporting after the detailed evidence is
preserved.
