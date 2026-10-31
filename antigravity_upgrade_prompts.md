# Antigravity Upgrade Prompt Pack

This is the finalized execution sequence for upgrading Customer Journey
Intelligence (CJI). Run the prompts in order. Use one prompt per Antigravity
task and commit only after its validation gate passes.

If implementation has moved to Kiro, use
[`kiro_upgrade_guide.md`](kiro_upgrade_guide.md) as the execution guide.
Kiro's native Specs replace Antigravity/GSD phase commands unless the Kiro
command palette explicitly provides those commands.

Skill-assisted execution order:

```text
GSD Core → Graphify checkpoint → Antigravity implementation
          → local validation → ChatGPT review → Caveman summary
          → GSD Core record/update → Git commit
```

Use the skills as layers, not competing agents. GSD Core owns phase state and
task sequencing. Graphify provides local architecture/dependency evidence.
Antigravity changes the code. Local tools prove whether it works. ChatGPT
reviews the evidence independently. Caveman may compress the final report
without removing failures, risks, file paths, or commands.

Optional skill policy:

- Use GSD Core as a workflow coordinator only after reviewing its source and
  generated artifacts.
- Use Graphify only as an optional local architecture/dependency discovery
  tool; never treat its graph as proof of correctness or security.
- Use Caveman only for concise communication and status compression.
- Do not allow either skill to override the repository's security, testing,
  branch, or source-of-truth rules.
- Do not install or use a skill that uploads repository content, secrets, or
  environment values.
- Do not maintain a second roadmap that contradicts this prompt pack.

If Graphify is installed, keep it outside the application runtime dependency
set. Analyze source and documentation locally, exclude `.env`, API keys,
database files, Parquet telemetry, ChromaDB data, generated reports, and
customer data, and do not commit `graphify-out/`.

## Explicit skill commands

Mentioning a skill is not enough to invoke it. Use the commands below when the
skill is installed and visible in Antigravity's command palette. Command names
can vary by installed release, so confirm them with `/` autocomplete or the
skill's help documentation before the first run.

### GSD Core

For this existing repository, prefer onboarding rather than creating a
greenfield project:

```text
/gsd-onboard --text
```

Then use the phase lifecycle:

```text
/gsd-spec-phase 1 --text
/gsd-discuss-phase 1 --text
/gsd-plan-phase 1
/gsd-execute-phase 1
/gsd-verify-phase 1
/gsd-progress
```

Use the corresponding phase number from the CJI sequence. Do not use
`/gsd-new-project` unless the repository has no existing GSD planning state and
you intentionally want to initialize a new project. GSD artifacts are planning
metadata; executable code, tests, and Git history remain authoritative.

### Graphify

`/graphify .` is an assistant instruction, not a shell command. Use it after
installing and registering Graphify:

```powershell
uv tool install graphifyy
graphify install
graphify --version
```

Then, in the Antigravity chat:

```text
/graphify .
```

For deterministic local CLI queries, use commands such as:

```powershell
graphify extract . --code-only
graphify god-nodes
graphify query "Which modules depend on duplicated event schemas?"
graphify path "tracker.js" "report_server.py"
graphify diagnose
```

Verify the installed version and supported flags before using examples. Keep
source-only analysis enabled and exclude secrets, telemetry, databases,
ChromaDB data, reports, and customer data.

### Caveman

Invoke Caveman explicitly as a response mode, only after detailed work and
validation are complete:

```text
/caveman lite
```

Use `/caveman full` when a concise but still detailed technical report is
needed. Use `stop caveman` or the runtime's documented normal-mode command
before the next task if you do not want the mode to persist. Caveman must
preserve commands, paths, identifiers, versions, numbers, quoted errors,
failed checks, and unresolved risks.

### Skill invocation rule

Do not write only “use GSD,” “use Graphify,” or “use Caveman” in a task and
assume execution occurred. The task report must state:

```text
Command invoked:
Command result:
Artifacts or graph output produced:
How the result affected this task:
```

If a command is unavailable, report that fact and continue only with an
equivalent manual process; never claim that the skill ran.

## Global execution rules

Paste these rules before every prompt if Antigravity does not retain them:

```text
You are the implementation owner for the Customer Journey Intelligence (CJI)
repository.

Work only within the current repository and active Git branch. Read
project_summary.md, refactoring.md, and free_plan_workflow.md before making
changes relevant to this task.

Operate at senior/principal software-engineering quality:
- preserve working behavior unless this task explicitly changes it;
- do not perform an unbounded rewrite;
- do not start later phases;
- do not change scoring weights, event taxonomy, or approval semantics without
  an explicit compatibility plan;
- do not silently swallow exceptions or create success-shaped fallbacks;
- do not commit secrets, credentials, generated dependency directories, or
  unrelated formatting changes;
- use existing project patterns and dependencies unless there is a documented
  reason to change them;
- add focused regression tests for every bug fixed;
- keep CLI, Streamlit, collector, MCP, and report behavior runnable until an
  approved replacement reaches parity.

Before editing:
1. inspect the relevant implementation and tests;
2. identify current behavior and dependencies;
3. state the files you intend to change;
4. state any ambiguity and choose the safest compatible interpretation.

After editing:
1. run the smallest relevant tests, lint, type checks, and smoke checks;
2. inspect the final diff and git diff --check;
3. report exact commands and results;
4. report changed files, remaining risks, and rollback concerns;
5. stop if validation fails for an unexplained reason.

If GSD Core is enabled, first load the current phase specification and update
its task state only after validation succeeds. If Graphify is enabled, use it
only for local source/documentation discovery and never as a correctness
oracle. If Caveman is enabled, use it only after the detailed report is
complete.
```

## Prompt 0 — Establish the baseline

```text
Create a verified baseline for the CJI repository. Do not refactor application
code yet.

GSD Core step:
- create or update the baseline phase specification, assumptions, risks, and
  completion criteria;
- do not create a second roadmap that conflicts with this prompt pack.

Graphify step, if installed:
- run a local graph over source code and documentation only;
- exclude .env files, API keys, databases, Parquet/telemetry, ChromaDB data,
  generated reports, and customer data;
- inspect graph report, central modules, communities, and dependency paths;
- keep graphify-out/ untracked and do not add Graphify to runtime dependencies.

Inspect:
- README.md
- project_summary.md
- refactoring.md
- Project_Memory.md
- Project_status.md
- cji_agent/
- docs/
- dependency and configuration files

Determine:
- supported Python and Node versions;
- how the CLI, Streamlit dashboard, collector, MCP services, and report flow
  are started;
- all service ports, transports, storage backends, and environment variables;
- the current test, lint, and type-check commands;
- which tests currently pass or fail;
- which documented claims contradict executable code.

Run available deterministic checks. If Python or dependencies are missing,
report the exact blocker and do not fabricate results.

Create or update only a concise baseline record in the repository, preferably
the existing project status/memory file rather than a new duplicate document.
Do not change runtime behavior.

Validation gate:
- baseline commands are reproducible;
- known failures are separated from newly introduced failures;
- service topology and entry points are documented from executable code.

Record in GSD Core:
- baseline status;
- known failures;
- architecture observations;
- the exact next approved task.

Optional Caveman step:
- compress the completed baseline report only after the full evidence is
  recorded; retain all failed commands and blockers.
```

## Prompt 1 — Fix P0 correctness and security issues

```text
Implement only the P0 findings R-01 through R-05 from refactoring.md.

Fix:
1. ingestion_worker.py calling the wrong MCP port;
2. demo-mode health checks using the PostgreSQL path;
3. SQL interpolation and ad-hoc placeholder replacement;
4. wildcard credentialed CORS, default administrator credentials, and seeded
   live API keys;
5. unsafe interpolation of untrusted content into generated HTML/JavaScript.

Requirements:
- prefer the existing MCP client/service mapping over another endpoint literal;
- bind SQL values and allow-list any dynamic identifiers;
- preserve demo mode as an offline path;
- fail closed outside explicit development mode;
- hash or otherwise avoid storing raw API keys where the current design permits;
- escape HTML and JavaScript contexts separately;
- add regression tests for each fixed issue;
- do not redesign the entire architecture in this task.

Validation gate:
- targeted tests cover all five findings;
- injection, CORS, credential, demo-mode, and report-rendering behavior is
  verified;
- no secrets or insecure production defaults remain in the changed paths.
```

## Prompt 2 — Introduce canonical domain contracts

```text
Create one authoritative domain-contract layer for CJI.

Before editing, use Graphify if available to trace all definitions and callers
of event, journey, friction, insight, report, and workflow state types. Treat
EXTRACTED/source-confirmed relationships as evidence and INFERRED relationships
as leads that must be verified in code.

Use GSD Core to record the chosen canonical contract, compatibility policy, and
migration slices before implementation.

Consolidate the duplicated definitions for:
- browser events and event types;
- journey/session identifiers;
- step metrics and funnel results;
- friction scores;
- insight results and recommendations;
- report results;
- workflow status, errors, and approval state.

Use the strongest existing typed validation patterns. Keep external API models,
internal domain models, and persistence models distinct where their concerns
differ, but define explicit conversions between them.

Requirements:
- preserve backward compatibility for current collector and workflow callers;
- identify and migrate duplicate models instead of leaving two sources of truth;
- preserve the existing event taxonomy and friction weights;
- reject invalid data explicitly;
- add contract and serialization tests;
- update only documentation that is directly made false by this change.

Validation gate:
- all changed callers use the canonical contracts;
- old and new representations have compatibility coverage;
- mypy/pyright or the repository's available type check passes for changed code.

Update the GSD Core phase record with the contract decision and migration
status. Do not use Caveman to shorten the contract itself; contract details
must remain explicit.
```

## Prompt 3 — Centralize typed configuration and service discovery

```text
Replace scattered runtime literals with validated configuration and a typed
service registry.

Before editing, use Graphify if available to identify hard-coded endpoints,
ports, provider names, storage paths, and configuration consumers. Verify every
candidate in source before changing it.

Use GSD Core to record the configuration contract and the development/test/
production behavior matrix.

Cover:
- application mode;
- service names and endpoints;
- ports and transports;
- database URLs and storage paths;
- LLM provider settings;
- timeouts, retry limits, and budgets;
- CORS origins;
- authentication and API-key configuration.

Requirements:
- use one source of truth for logical service names;
- support explicit development, test, and production behavior;
- never provide a known production secret as a default;
- validate configuration at startup and produce actionable errors;
- allow tests to inject local endpoints and temporary storage;
- preserve the documented offline demo path;
- migrate callers incrementally rather than adding a second parallel registry.

Validation gate:
- no changed production path contains duplicated service ports or provider
  literals;
- configuration validation tests cover missing, invalid, development, and
  production settings;
- all existing startup paths still resolve their required services.

Record the configuration migration and unresolved environment risks in GSD
Core. A Caveman summary may be produced only after the complete validation
output is preserved.
```

## Prompt 4 — Isolate data access behind repositories

```text
Introduce repository interfaces for demo and realtime event data, then migrate
the journey-data service and directly dependent workers.

Use Graphify, if available, to trace callers of journey-data functions and
storage clients before choosing the repository boundary. Use GSD Core to record
the boundary, adapter plan, and compatibility risks.

The repository boundary must cover the existing operations:
- health/readiness;
- step metrics;
- funnel drop-off;
- event queries/samples;
- live snapshots;
- ingestion writes where applicable.

Requirements:
- provide separate DuckDB/Parquet and PostgreSQL-compatible implementations;
- select the implementation once through typed configuration;
- remove repeated CJI_MODE branching from individual query functions;
- parameterize all values;
- preserve result shapes and numeric semantics;
- define transaction and idempotency behavior for writes;
- add unit tests for each implementation and contract-level parity tests.

Do not optimize concurrency or redesign the database schema in this task.

Validation gate:
- demo health checks work without PostgreSQL;
- realtime paths do not accidentally use demo storage;
- repository tests cover success, empty, invalid, and database-failure cases.

Update the GSD Core phase record with the selected repository contract and
parity results. Preserve the detailed test output before requesting an optional
Caveman summary.
```

## Prompt 5 — Remove dead code and reconcile documentation

```text
Perform a bounded dead-code and documentation cleanup based on evidence from
the current repository.

Use Graphify, if available, to identify disconnected nodes, stale references,
high-centrality modules, and documentation-to-code relationships. Treat the
graph as a discovery aid only and verify every removal with source search and
tests. Use GSD Core to record removal candidates before deleting anything.

Inspect:
- unused imports and variables;
- silent pass branches and broad exception handlers;
- test_dummy and non-production MCP tools;
- duplicate ingestion utilities;
- sys.path.insert runtime workarounds;
- stale entry points and unreachable code;
- README.md, Project_Memory.md, Project_status.md, and docs/.

Requirements:
- remove code only when search and tests prove it is unused or obsolete;
- preserve compatibility entry points that are still documented and used;
- replace broad catches with expected exception handling and structured errors;
- mark historical documents as superseded or update them to executable truth;
- do not silently delete user-facing functionality;
- do not mix architectural redesign into this cleanup.

Validation gate:
- repository search shows no remaining references to intentionally removed
  symbols;
- tests and startup smoke checks pass;
- documentation names the implemented system, not an earlier design generation.

Record removed and retained symbols in GSD Core. Use Caveman only to compress
the final cleanup report after the full evidence and unresolved candidates are
preserved.
```

## Prompt 6 — Harden the collector

```text
Harden the FastAPI collector without changing the public event meaning.

Use Graphify, if available, to trace collector routes, authentication helpers,
event models, write paths, and downstream consumers. Use GSD Core to record
the security scope, compatibility constraints, and batch-response contract
before editing.

Implement:
- strict request validation using the canonical event contract;
- explicit authentication and authorization boundaries;
- safe, configurable CORS;
- request size and batch-size limits;
- rate limiting using the existing project guardrail patterns where suitable;
- idempotency keys or deterministic event identifiers;
- accurate accepted/rejected/duplicate counts;
- durable write semantics instead of claiming persistence before it occurs;
- structured request correlation IDs;
- readiness and liveness endpoints.

Requirements:
- define the response contract for partial batch failure;
- do not log raw sensitive identifiers or secrets;
- preserve useful local development behavior behind explicit development
  configuration;
- add tests for authentication, limits, duplicates, partial failures, and
  database failures.

Validation gate:
- a failed persistence operation cannot be reported as successfully stored;
- retries do not create duplicate events;
- collector integration tests pass with a temporary test database.

Record security test results and any accepted development-only behavior in GSD
Core. Never use Caveman to omit a failed security test or unresolved risk.
```

## Prompt 7 — Unify LLM and MCP gateway behavior

```text
Create a single typed gateway layer for LLM and MCP calls used by insight,
report, and workflow workers.

Use Graphify, if available, to map provider/tool call sites and dependency
paths. Use GSD Core to record the gateway contract, error taxonomy, retry
policy, and budget policy before implementation.

The gateway must standardize:
- provider selection;
- request and response types;
- timeouts;
- bounded retries;
- cancellation;
- rate limits;
- token/cost budgets;
- correlation IDs;
- audit metadata;
- redaction and sanitization;
- provider/tool error classification.

Requirements:
- preserve existing guardrails before and after model calls;
- do not expose secrets in exceptions or logs;
- distinguish retryable, non-retryable, timeout, policy, and validation errors;
- provide deterministic test doubles;
- keep the deterministic friction engine independent from the LLM gateway;
- do not silently fall back to a different provider.

Validation gate:
- insight and report workers use the gateway;
- timeout, retry, budget, and malformed-response tests pass;
- logs and audit records contain correlation metadata but no sensitive payloads.

Update GSD Core with provider decisions and test evidence. A Caveman summary
must not remove provider, budget, timeout, or failure details.
```

## Prompt 8 — Make the LangGraph workflow durable

```text
Refactor the LangGraph workflow for reliable, resumable execution.

Use Graphify, if available, to trace graph construction, supervisor routing,
worker edges, state fields, checkpoint access, and all graph entry points. Use
GSD Core to record the state-transition and recovery design before editing.

Preserve:
- the current worker ordering;
- the human approval checkpoint;
- the iteration cutoff;
- deterministic friction calculations;
- compatibility with existing CLI and dashboard invocation.

Implement:
- durable checkpoint configuration;
- typed state transitions;
- explicit run and step identifiers;
- idempotent workers;
- bounded retries and timeouts;
- resumability after process failure;
- structured failure states;
- safe approval and resume semantics;
- workflow audit metadata.

Requirements:
- a rerun must not duplicate persisted insights, reports, or events;
- partially completed runs must be diagnosable;
- remove misleading parameters and dead persistence switches;
- add failure-injection tests for each worker boundary;
- do not introduce unbounded parallelism.

Validation gate:
- interrupted runs resume from a checkpoint;
- failed runs expose a structured error;
- duplicate execution is safe;
- approval and resume tests pass.

Record failure-injection results and known recovery limitations in GSD Core.
Do not let Caveman compress away state-transition or checkpoint evidence.
```

## Prompt 9 — Make reporting safe and deterministic

```text
Harden and simplify report generation.

Use Graphify, if available, to trace every report input, template, asset,
filesystem write, and download path. Use GSD Core to record the output-safety
threat model and rendering compatibility requirements.

Cover:
- typed report input and output contracts;
- HTML escaping by context;
- safe JavaScript data serialization;
- strict content-security policy;
- pinned or self-hosted frontend assets;
- deterministic report rendering;
- report size and content limits;
- safe filenames and output paths;
- report metadata and provenance.

Requirements:
- treat all narrative, insight, journey, and user-provided fields as untrusted;
- preserve the existing report content and chart meaning;
- do not allow path traversal or arbitrary file writes;
- make failed report generation explicit;
- add malicious-content and snapshot-style tests.

Validation gate:
- representative XSS payloads are rendered inert;
- generated reports open without external network access where the contract
  promises self-contained output;
- report tests pass for empty, large, malformed, and malicious inputs.

Record security payload results and report compatibility in GSD Core. Keep the
full malicious-input evidence even if using Caveman for the final summary.
```

## Prompt 10 — Package the Python application

```text
Convert the Python application into a supported installable package.

Use Graphify, if available, to identify import roots, sys.path workarounds,
entry points, and package-boundary violations. Use GSD Core to record the
packaging compatibility plan before changing imports or commands.

Implement:
- pyproject.toml with supported Python versions and project metadata;
- explicit package boundaries;
- console-script entry points for supported commands;
- development and test dependency groups;
- import-safe module execution;
- removal of sys.path.insert workarounds;
- reproducible lint, type-check, and test commands.

Requirements:
- preserve current user-facing commands through compatibility entry points;
- do not upgrade unrelated dependencies without evidence;
- pin or constrain security-sensitive dependencies appropriately;
- document local setup and environment variables;
- ensure package installation works in a clean virtual environment.

Validation gate:
- clean installation succeeds;
- CLI entry points work from outside the repository root;
- tests import the installed package rather than relying on checkout-path hacks.

Record clean-install output and compatibility commands in GSD Core. Do not
summarize away an installation failure.
```

## Prompt 11 — Establish the versioned backend API

```text
Create the first stable versioned backend API for the future Next.js frontend.

Use Graphify, if available, to trace existing API-like routes, CLI/dashboard
callers, MCP boundaries, and response-shape consumers. Use GSD Core to record
the API contract, compatibility adapters, and migration order before coding.

Design and implement the smallest complete vertical slice for:
- /api/v1/health;
- projects or journeys;
- events;
- journey metrics;
- friction results;
- insights;
- reports;
- workflow status and approval.

Requirements:
- define authentication and authorization;
- validate every request and response;
- provide pagination and bounded result sizes;
- use stable error envelopes;
- include request IDs;
- define idempotency for mutating operations;
- generate or maintain accurate OpenAPI documentation;
- keep existing CLI and Streamlit callers working through adapters where needed;
- do not build the full frontend in this task.

Validation gate:
- API contract tests cover success, validation, unauthorized, forbidden,
  not-found, conflict, rate-limit, and server-error cases;
- OpenAPI matches actual responses;
- no endpoint exposes raw internal exceptions or secrets.

Record the OpenAPI and contract-test evidence in GSD Core. Do not use Caveman
to shorten the actual API contract or error envelope definitions.
```

## Prompt 12 — Create the Next.js frontend foundation

```text
Create the Next.js frontend foundation against the versioned backend API.

Use Graphify, if available, to inspect the backend API surface and existing
Streamlit/CLI behavior before duplicating any presentation logic. Use GSD Core
to record the frontend slice, route/auth boundary, and parity criteria.

Use:
- TypeScript;
- strict type checking;
- an accessible component structure;
- a typed API client generated from or aligned with OpenAPI;
- environment-based backend configuration;
- secure authentication and protected routes;
- explicit loading, empty, retry, and error states.

Start with a thin vertical slice:
- application shell;
- authentication boundary;
- health/status view;
- journey list/detail view;
- friction summary;
- workflow/report status.

Requirements:
- do not duplicate business logic that belongs in the backend;
- do not embed secrets in browser code;
- preserve Streamlit as a compatibility client;
- add unit/component tests and one browser smoke test;
- make the frontend runnable independently in development.

Validation gate:
- type check, lint, unit tests, and browser smoke test pass;
- unauthenticated users cannot access protected data;
- API errors are visible and recoverable rather than silently ignored.

Record browser evidence and known UX differences in GSD Core. Caveman may
compress the status report only after the detailed accessibility and error
results are preserved.
```

## Prompt 13 — Reach behavioral parity and migrate gradually

```text
Expand the Next.js application feature by feature while preserving behavioral
parity with the existing Streamlit and CLI surfaces.

At the start of each feature slice, use Graphify if available to trace the
backend contract and existing surface behavior. Use GSD Core to track one
feature slice at a time, including parity evidence and rollback status.

For each feature:
1. define the backend contract;
2. implement or verify the API;
3. implement the Next.js UI;
4. compare results with the existing surface;
5. add browser and contract tests;
6. document any intentional UX difference.

Cover:
- ingestion status and validation feedback;
- journey and funnel analytics;
- friction drill-down;
- AI insight generation and provenance;
- approval/resume workflow;
- report preview and download;
- error, empty, and permission states.

Do not remove Streamlit or CLI until:
- core results match within documented tolerances;
- migration and rollback instructions exist;
- browser and integration tests pass;
- users have an operational fallback.

Record each parity result and intentional difference in GSD Core. Do not let a
Caveman summary replace the detailed comparison evidence.
```

## Prompt 14 — Production hardening and release readiness

```text
Prepare the upgraded CJI system for a controlled production release.

Use Graphify, if available, for a final local dependency and documentation
drift scan. Use GSD Core to maintain the release checklist, evidence links,
blockers, and rollback decision.

Implement and verify:
- structured logs with correlation IDs;
- metrics and traces;
- audit events for authentication, data access, AI calls, approvals, and
  report generation;
- secret management and rotation guidance;
- dependency, container, and secret scanning;
- rate limiting and abuse controls;
- database backups and restore verification;
- migration rollback;
- health/readiness checks;
- failure-injection and recovery tests;
- CI checks for formatting, lint, types, unit, integration, and browser tests;
- deployment documentation and environment validation.

Requirements:
- remove or explicitly isolate development-only defaults;
- verify no sensitive data appears in logs, reports, or client bundles;
- document operational limits and AI cost budgets;
- do not claim production readiness for an unverified control.

Validation gate:
- release checklist is executable;
- all failed checks are recorded with owners and blockers;
- rollback is tested, not merely documented.

Record the complete release evidence in GSD Core. Caveman may produce a short
release summary only after all blockers and failed checks remain visible.
```

## Prompt 15 — Final principal-engineer review

```text
Perform a final evidence-based principal-engineer review of the complete CJI
upgrade. Do not make broad changes automatically.

If Graphify is available, use its final local graph/report to identify
unexpected coupling, stale references, and central modules requiring manual
review. Verify every finding against source, tests, and Git history.

Use GSD Core to assemble the final phase history and completion evidence. Use
Caveman only for an optional concise executive summary after the complete
review findings have been recorded.

Review:
- project_summary.md;
- refactoring.md;
- free_plan_workflow.md;
- all changed source, tests, configuration, and documentation;
- Git history and migration path;
- API/OpenAPI contracts;
- security and production-readiness checks.

Check for:
- remaining P0/P1 findings;
- contract or documentation drift;
- insecure defaults and secret leakage;
- data-loss, duplication, retry, and concurrency risks;
- broken demo mode;
- broken CLI/Streamlit compatibility;
- incomplete Next.js behavior;
- missing rollback or observability;
- unsupported claims in documentation.

Produce:
1. release-blocking findings ranked by severity and confidence;
2. exact file and line evidence;
3. minimal remediation for every finding;
4. tests or operational checks needed to prove remediation;
5. a truthful readiness decision: ready, conditionally ready, or not ready;
6. a final list of deferred technical debt.

Do not declare the system production-ready merely because the build passes.

The final decision must cite local test results, security evidence, migration
and rollback checks, and unresolved risks. Neither Graphify, GSD Core, nor
Caveman can substitute for those checks.
```

## Execution order

Run:

```text
0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15
```

Do not start Prompt 12 before Prompt 11 has stable contracts. Do not remove
Streamlit or the CLI before Prompt 13 proves parity and rollback.

## Skill checkpoint for every prompt

Before implementation:

```text
GSD Core: load the current phase specification and define the bounded slice.
Graphify: inspect relevant local relationships when architecture discovery is
useful; exclude sensitive and generated data.
Antigravity: implement only the approved slice.
```

After implementation:

```text
Antigravity: run targeted tests and inspect the diff.
Local tools: run the authoritative checks.
ChatGPT: review the diff, failures, security, and compatibility evidence.
Antigravity: fix only confirmed findings.
Local tools: rerun validation.
GSD Core: mark the slice complete and record evidence.
Caveman: optionally compress the already-complete report.
Git: commit only after the validation gate passes.
```

If any skill produces a plan, graph, or summary that conflicts with the
repository code, tests, or this prompt pack, stop and resolve the conflict
from executable evidence. Never allow a compressed summary to hide a failure,
security issue, migration risk, or unverified claim.
