# Kiro Upgrade Guide for CJI

This guide adapts the Customer Journey Intelligence (CJI) upgrade workflow to
Kiro. It replaces Antigravity-specific execution assumptions with Kiro's
native Specs workflow while preserving the engineering rules in:

- [`project_summary.md`](project_summary.md)
- [`refactoring.md`](refactoring.md)
- [`free_plan_workflow.md`](free_plan_workflow.md)
- [`antigravity_upgrade_prompts.md`](antigravity_upgrade_prompts.md)

## 1. First verify the model name

Kiro's model catalog distinguishes **Claude Fable 5.1** from **Claude Opus
5.5**. Fable 5.1 is documented as an Enterprise model requiring administrator
model governance, while Opus 5.5 is a separate model. If your Kiro picker
literally displays “Fable 5.5”, trust the picker for your account but verify
the exact identifier in Kiro's model details before planning around it.

Do not assume that a model name, quota, context size, region, or plan
entitlement is permanent. Confirm the current selection in Kiro before each
major phase.

## 2. Recommended Kiro model policy

| Work | Preferred model |
|---|---|
| Architecture, P0 security, repositories, workflow durability, API design | Highest-quality long-context model visible in Kiro |
| Large multi-file implementation | Opus/Fable/Sol-class model available to the account |
| Scoped feature slice and debugging | Sonnet/Terra-class model |
| Documentation, tests, formatting, mechanical changes | Haiku/Luna/efficient model |
| Automatic routing when model choice is unclear | Kiro Auto |

For a free or quota-limited account, use the strongest model only for design
and cross-cutting changes. Use Auto or an efficient model for routine work.
Do not use a high-cost model to run tests, format files, or make mechanical
renames.

## 3. Kiro should be the implementation owner

Use the tools this way:

```text
Kiro          = requirements, design, implementation, terminal work, tests
ChatGPT Go    = independent architecture/security/diff review
Graphify      = optional local dependency and architecture discovery
Caveman       = optional concise reporting, only if supported by Kiro
Local tools   = authoritative tests, builds, type checks, migrations
GitHub        = source of truth, review history, and rollback
```

Do not let Kiro and ChatGPT edit the same branch concurrently. Kiro owns the
active implementation branch. ChatGPT receives a diff, test output, and
specific questions, then returns review findings. Confirmed findings are sent
back to Kiro.

## 4. Use Kiro Specs instead of Antigravity GSD commands

Kiro Specs produce three durable artifacts:

```text
requirements.md
design.md
tasks.md
```

Use one Kiro Spec for each bounded phase or vertical slice. Do not create one
massive Spec for the entire CJI transformation.

Recommended Kiro workflow:

```text
Create Spec
→ Requirements review
→ Design review
→ Task review
→ Implement one task or dependency wave
→ Run validation
→ Review diff
→ Mark tasks complete
→ Commit
```

Kiro can execute independent task waves concurrently. Use parallel execution
only when tasks have no shared files, shared migrations, shared contracts, or
ordering dependency. Keep security fixes, schema changes, migrations, and
cross-cutting refactors sequential.

The previous commands such as `/gsd-plan-phase` and `/gsd-execute-phase` are
GSD/Antigravity workflow commands. They may not exist in Kiro. Do not paste
them into Kiro unless Kiro's command palette explicitly supports them. Kiro's
native Specs are the source of planning state for this environment.

## 5. Kiro project setup

Before creating the first Spec:

1. Open the CJI repository in Kiro.
2. Create or switch to a dedicated upgrade branch.
3. Read `project_summary.md`, `refactoring.md`, and this guide.
4. Confirm Python, Node.js, package-manager, database, and browser-test
   prerequisites.
5. Run the existing tests without changing application code.
6. Record baseline failures separately from future failures.
7. Check the Git worktree for unrelated changes.

Do not initialize a new project template over the existing repository. This is
a brownfield refactor.

## 6. The first Kiro Spec: baseline and onboarding

Create a **Bugfix/maintenance or Feature Spec**, depending on how Kiro labels
the workflow, with this request:

```text
Onboard this existing Customer Journey Intelligence repository for a staged
production refactor. Do not change runtime code yet.

Read:
- project_summary.md
- refactoring.md
- README.md
- Project_Memory.md
- Project_status.md
- cji_agent/
- docs/

Produce requirements.md, design.md, and tasks.md that document:
- current startup commands;
- supported Python and Node versions;
- test, lint, and type-check commands;
- collector, MCP, Streamlit, CLI, and report entry points;
- service ports and storage backends;
- environment variables and secret requirements;
- known code/documentation drift;
- baseline failures and missing dependencies;
- a safe phase order for the refactor.

Do not rewrite code. Do not claim tests passed if the environment cannot run
them. Keep the existing repository documents as inputs and identify conflicts
instead of silently replacing them.
```

Review all three artifacts before allowing implementation.

## 7. Phase map for Kiro Specs

Create these Specs in order:

| Spec | Scope | Main output |
|---|---|---|
| 01 Baseline | Runtime and test inventory | Reproducible baseline |
| 02 P0 Security | R-01 through R-05 | Correct and secure foundations |
| 03 Canonical Contracts | R-06 | One domain model boundary |
| 04 Configuration | R-08 | Typed settings and service registry |
| 05 Repositories | R-02 and data access | Demo/realtime isolation |
| 06 Cleanup | R-07, R-10, R-11 | Dead-code and documentation cleanup |
| 07 Collector | R-09 | Durable, authenticated ingestion |
| 08 AI Gateway | R-12 | Unified LLM/MCP policy |
| 09 Durable Workflow | LangGraph reliability | Restartable, idempotent runs |
| 10 Safe Reports | R-05 and report hardening | Safe deterministic output |
| 11 Packaging | R-14 | Installable Python package |
| 12 Backend API | Stable `/api/v1` | Frontend-ready contracts |
| 13 Next.js Foundation | Frontend vertical slice | Authenticated web UI |
| 14 Frontend Parity | Streamlit migration | Feature-by-feature parity |
| 15 Production Release | Observability and operations | Evidence-based release decision |

Do not start Spec 13 until Spec 12 has tested API contracts. Do not remove
Streamlit or the CLI until Spec 14 proves parity and rollback.

## 8. Reusable Kiro Spec prompt

Use this when creating each phase Spec:

```text
Implement only this bounded CJI phase: <phase name>.

Read:
- project_summary.md
- refactoring.md
- kiro_upgrade_guide.md
- the relevant existing source files
- the relevant tests

Requirements:
- preserve existing behavior unless this phase explicitly changes it;
- do not start a later phase;
- do not perform an unbounded rewrite;
- preserve CLI and Streamlit compatibility;
- add focused regression tests;
- surface errors explicitly;
- do not commit secrets or generated dependency directories;
- keep migrations and writes reversible where possible.

The Spec must include:
1. current behavior;
2. intended behavior;
3. non-goals;
4. affected files and boundaries;
5. security and data-integrity risks;
6. task dependencies;
7. acceptance criteria;
8. exact validation commands;
9. rollback or compatibility concerns.

If requirements conflict with executable code, tests, or refactoring.md,
document the conflict and resolve it using evidence. Do not silently guess.
```

## 9. Kiro task execution rules

For each task:

```text
1. Read the task and its acceptance criteria.
2. Inspect the specific implementation and tests.
3. State the intended files before editing.
4. Make the smallest complete change.
5. Add or update regression tests.
6. Run targeted validation.
7. Inspect the diff and git diff --check.
8. Report exact commands and results.
9. Mark the task complete only when evidence exists.
```

Use Kiro's parallel task execution only for genuinely independent work. Good
parallel candidates include separate documentation updates or isolated test
modules. Bad parallel candidates include:

- canonical model changes and API implementation;
- database migrations and repository rewrites;
- authentication changes and frontend route protection;
- multiple workers editing shared workflow state;
- tasks that modify the same configuration or dependency files.

## 10. Prompts for the most important Specs

### Spec 02 — P0 security and correctness

```text
Fix only refactoring.md findings R-01 through R-05.

Fix:
- ingestion_worker.py using the wrong MCP port;
- demo health checks using PostgreSQL;
- SQL interpolation and placeholder replacement;
- wildcard credentialed CORS and unsafe default credentials;
- unsafe HTML/JavaScript interpolation in reports.

Requirements:
- use service names and typed configuration rather than new endpoint literals;
- bind SQL values and allow-list identifiers;
- preserve offline demo mode;
- fail closed outside explicit development mode;
- never seed known production keys;
- escape HTML and JavaScript contexts correctly;
- add regression tests for every issue.

Do not redesign the entire architecture in this Spec.
```

### Spec 03 — canonical contracts

```text
Create one authoritative contract layer for browser events, journeys,
friction, insights, reports, and workflow status.

Preserve the current event taxonomy, friction weights, approval semantics, and
compatible collector callers. Keep external, domain, and persistence models
distinct where needed, but define explicit conversions. Remove duplicate
sources of truth and add serialization/compatibility tests.
```

### Spec 09 — durable LangGraph workflow

```text
Make the LangGraph workflow restartable and idempotent.

Preserve worker order, approval checkpoint, iteration cutoff, deterministic
friction scoring, and CLI/Streamlit invocation.

Add durable checkpoints, typed transitions, run/step IDs, bounded retries,
timeouts, structured failure states, safe approval/resume behavior, and
failure-injection tests. A rerun must not duplicate events, insights, or
reports.
```

### Spec 12 — versioned backend API

```text
Create a stable /api/v1 contract for health, journeys, events, metrics,
friction, insights, reports, workflow status, and approval.

Define authentication, authorization, validation, pagination, bounded result
sizes, stable error envelopes, request IDs, idempotency, and OpenAPI output.
Keep CLI and Streamlit callers working through adapters. Add contract tests
for success, validation, unauthorized, forbidden, not-found, conflict, rate
limit, and server-error cases.
```

### Spec 13 — Next.js foundation

```text
Build a thin Next.js TypeScript vertical slice against the tested /api/v1 API.

Include the application shell, authentication boundary, health view, journey
view, friction summary, and workflow/report status. Add loading, empty, retry,
error, and permission states. Do not duplicate backend business logic or place
secrets in browser code. Keep Streamlit available for comparison.
```

## 11. Graphify with Kiro

Graphify is optional and should remain a local developer tool, not a CJI
runtime dependency.

Install and inspect it outside the application environment:

```powershell
uv tool install graphifyy
graphify install
graphify --version
graphify extract . --code-only
graphify diagnose
```

Use `/graphify .` only if Kiro recognizes Graphify's assistant integration.
Otherwise use the shell CLI. Do not invent a Kiro-specific slash command.

Useful local queries:

```powershell
graphify query "Which modules depend on duplicated event schemas?"
graphify path "tracker.js" "report_server.py"
graphify god-nodes
```

Exclude `.env`, API keys, databases, Parquet telemetry, ChromaDB data,
generated reports, and customer data. Do not commit `graphify-out/`.

Use Graphify before Specs 02, 03, 04, 05, 08, 09, 12, 13, and 15. Treat graph
relationships as discovery evidence, not proof of correctness or security.

## 12. Caveman with Kiro

Kiro may not support the same Caveman command integration as Antigravity.
Check Kiro's command palette before invoking:

```text
/caveman lite
```

Use it only after detailed work and validation are complete. If unsupported,
ask Kiro directly:

```text
Compress the completed report into a concise technical summary. Preserve exact
commands, paths, identifiers, versions, quoted errors, failed checks,
unresolved risks, and next actions. Do not omit blockers.
```

Never use concise mode for security analysis, migration design, API contracts,
or failure diagnosis where compression could hide important details.

## 13. ChatGPT Go review gate

After each Kiro Spec task or small group of related tasks, send ChatGPT:

```text
Act as an independent principal engineer reviewing this Kiro implementation.

Context:
- Customer Journey Intelligence;
- project_summary.md;
- refactoring.md;
- the Spec requirements, design, and completed task;
- the supplied diff and test output.

Find only evidence-based:
- correctness bugs;
- security issues;
- data-loss or duplicate-write risks;
- retry and concurrency problems;
- API compatibility issues;
- missing regression tests;
- documentation drift.

Rank each finding by severity and confidence. Include file/line evidence,
minimal safe remediation, and the test required to prove it. Do not propose a
broad rewrite without evidence. If no issue is found, state what was checked
and what remains unverified.
```

Send only confirmed findings back to Kiro. Do not paste secrets, `.env` values,
customer telemetry, private keys, or production database content into ChatGPT.

## 14. Validation gate

Kiro must not mark a task complete until the applicable checks pass:

```text
git diff --check
Python unit and integration tests
lint and type checks
API contract/OpenAPI checks
database migration and rollback checks
browser tests for frontend work
security and dependency scans for release work
```

If a tool or dependency is unavailable, Kiro must report the exact command and
blocker. A skipped check is not a passing check.

## 15. Daily Kiro operating loop

```text
1. Select one phase and one bounded Spec/task slice.
2. Review requirements.md, design.md, and tasks.md.
3. Use Graphify locally if the slice has unfamiliar dependencies.
4. Let Kiro implement only the approved task.
5. Run local validation and inspect the diff.
6. Ask ChatGPT Go for an independent review.
7. Send confirmed findings back to Kiro.
8. Re-run validation.
9. Commit the verified slice.
10. Update the Spec task and record evidence.
```

## 16. Definition of done

A Kiro task is complete only when:

- acceptance criteria are satisfied;
- targeted tests pass;
- new failure modes have regression coverage;
- no unrelated files changed;
- documentation and configuration match behavior;
- compatibility and rollback impact are understood;
- review findings are resolved or recorded;
- exact validation evidence is stored in the Spec or Git history.

The project is not production-ready merely because Kiro completes all tasks.
Production readiness requires verified security, observability, migration
rollback, backup/restore, browser, integration, and failure-recovery checks.

## 17. Recommended first action

Start with the baseline Spec, not the Next.js frontend:

```text
Create the baseline/onboarding Spec using the prompt in section 6.
Do not edit runtime code until requirements.md, design.md, and tasks.md have
been reviewed and the current test baseline is recorded.
```
