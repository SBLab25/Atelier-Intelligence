# Free-Plan Development Workflow

This guide defines a practical operating model for completing the Customer
Journey Intelligence (CJI) upgrade with Google Antigravity and ChatGPT Go while
minimizing paid usage and preventing conflicting or incomplete changes.

For Kiro-specific execution, use [`kiro_upgrade_guide.md`](kiro_upgrade_guide.md).
It uses Kiro Specs (`requirements.md`, `design.md`, and `tasks.md`) instead of
assuming Antigravity/GSD commands are available.

It complements:

- [`project_summary.md`](project_summary.md), the current and target architecture;
- [`refactoring.md`](refactoring.md), the prioritized refactoring audit.

## 0. Optional Antigravity skills

Use **GSD Core** as the project workflow only if its installed version is
trusted and its artifacts do not contradict the repository documents. It is
well suited to this project because it provides a repeatable
specify/clarify/plan/implement/verify loop and persistent phase context.

Use **Caveman** only as a communication aid for compact status reports,
clarified task statements, and high-signal summaries. It must not replace
security analysis, architecture decisions, detailed failure reports, or
verification evidence.

Before installing any third-party skill:

1. inspect its source, permissions, and installation scripts;
2. verify that it does not upload source code, credentials, or environment
   values;
3. test it on a separate Git branch;
4. check whether it writes files, changes prompts, runs shell commands, or
   installs dependencies;
5. confirm that its generated artifacts do not create a competing roadmap or
   source of truth.

Recommended ownership:

```text
GSD Core       = phase specifications and persistent execution state
Graphify       = local architecture and dependency discovery
Antigravity    = implementation, terminal work, and verification
ChatGPT Go     = independent architecture and security review
Caveman        = optional concise communication
Local tools    = authoritative tests, builds, and type checks
GitHub         = source of truth and rollback history
```

Do not combine multiple full workflow frameworks. Keep
`project_summary.md`, `refactoring.md`, this file, and
`antigravity_upgrade_prompts.md` aligned if GSD Core creates additional
metadata such as `.gsd/` or `.agent/`.

Graphify may be installed as an optional local developer tool for dependency
and architecture discovery. Do not add it to the CJI runtime dependencies or
use it as a substitute for tests, security review, type checks, or migration
verification.

Run Graphify only against source and documentation unless sensitive data has
been explicitly excluded. Do not send `.env` files, API keys, database files,
Parquet telemetry, ChromaDB data, generated reports, or customer data to an
external Graphify service. Keep generated `graphify-out/` artifacts out of
version control.

Useful review points are before refactoring, after P0 fixes, before the
Next.js migration, and before the final architecture review. Ask it to trace
event flow, service dependencies, duplicated contracts, hard-coded endpoints,
and stale documentation references.

### Invoke skills explicitly

Mentioning a skill in a prompt does not necessarily execute it. Confirm the
installed command from Antigravity's `/` command palette, then invoke it
explicitly.

For GSD Core on this existing repository:

```text
/gsd-onboard --text
/gsd-spec-phase 1 --text
/gsd-discuss-phase 1 --text
/gsd-plan-phase 1
/gsd-execute-phase 1
/gsd-verify-phase 1
```

Use the actual phase number. Do not run `/gsd-new-project` unless the
repository has no existing GSD state and new project initialization is
intentional.

For Graphify:

```powershell
uv tool install graphifyy
graphify install
graphify --version
graphify extract . --code-only
graphify diagnose
```

Then invoke the assistant skill in Antigravity with:

```text
/graphify .
```

For Caveman:

```text
/caveman lite
```

Use `/caveman full` only for a compact technical report after validation.
Caveman must not hide failed checks, unresolved risks, exact paths, commands,
versions, or quoted errors. If a command is unavailable, record that it did
not run rather than implying success.

## 1. Tool responsibilities

Use one tool as the implementation owner and the other as an independent
reviewer.

| Tool | Primary responsibility | Do not use it for |
|---|---|---|
| Google Antigravity | Repository inspection, code changes, terminal commands, tests, browser checks, commits | Unbounded “rewrite the whole repository” prompts |
| ChatGPT Go | Architecture critique, security review, debugging help, diff review, test-plan review | Concurrent edits to the same branch |
| Local development tools | Python/Node installation, tests, linting, type checks, migrations, Git history | Delegating deterministic checks to an AI agent |
| GitHub | Source of truth, branch history, rollback, issue tracking | Storing unreviewed generated code outside version control |

Google AI product limits and model availability are account- and
product-dependent. Do not design the process around a permanent model name.
In Antigravity, select the highest-quality, longest-context model available for
cross-cutting changes and the fast/efficient model for narrow maintenance work.

## 2. Model selection policy

### Use the strongest available Antigravity model for

- P0 security and correctness fixes;
- canonical domain and API contract design;
- LangGraph durability and failure handling;
- database/repository abstractions;
- authentication and authorization;
- Next.js integration across multiple backend endpoints;
- migrations and changes that affect many packages.

### Use Antigravity's efficient model for

- formatting and lint fixes;
- isolated bug fixes with a failing test;
- documentation updates;
- adding straightforward unit tests;
- mechanical renames after the contract is established.

### Use ChatGPT Go for

- reviewing a completed diff;
- challenging architecture decisions;
- identifying security and data-loss risks;
- investigating a test failure using supplied logs;
- comparing two implementation options;
- checking whether documentation still matches executable behavior.

Do not use model quality as a substitute for verification. The local test suite,
type checker, linter, migration checks, and browser tests remain authoritative.

## 3. Branch and ownership rules

Keep GitHub as the only source of truth. Use one branch per upgrade phase:

```text
main
  ├── phase-01-baseline
  ├── phase-02-security
  ├── phase-03-domain-models
  ├── phase-04-configuration-persistence
  ├── phase-05-workflow-reliability
  ├── phase-06-backend-api
  ├── phase-07-nextjs-frontend
  └── phase-08-production-hardening
```

Rules:

1. Antigravity owns implementation on the active phase branch.
2. ChatGPT Go reviews the diff and does not edit that branch.
3. Never allow both tools to modify the same branch concurrently.
4. Commit after each verified vertical slice.
5. Keep unrelated cleanup out of the current phase.
6. Preserve the CLI and Streamlit paths until their replacement has behavioral
   parity.
7. Stop at the first unclear test or migration failure; do not stack changes on
   an unexplained failure.

Recommended commit format:

```text
security: parameterize event query values
models: add canonical journey event contract
api: add versioned friction endpoint
frontend: add journey overview loading state
```

## 4. Phase gates

### Phase 0: establish a baseline

- Install Python 3.11+ and Node.js LTS.
- Run the existing tests and record failures without changing them.
- Verify the documented service startup commands and ports.
- Record the current CLI, Streamlit, collector, MCP, and report behavior.
- Create a baseline commit.

No refactor should begin until existing failures are distinguishable from new
failures.

### Phase 1: fix P0 correctness and security issues

Resolve the findings already documented as R-01 through R-05:

- ingestion/report port mismatch;
- demo-mode health-check path;
- SQL interpolation;
- wildcard credentialed CORS and default credentials;
- unsafe HTML and JavaScript interpolation.

Add regression tests before moving to the next phase.

### Phase 2: establish canonical contracts

Create one authoritative contract for:

- event types and payloads;
- journey and session identifiers;
- friction metrics;
- insight and report results;
- workflow status and error states.

Remove or derive duplicate models instead of maintaining parallel schemas.

### Phase 3: configuration and persistence

- Add typed settings with explicit development and production behavior.
- Centralize service discovery and ports.
- Introduce repository interfaces for demo and realtime data.
- Make migrations, rollback, and idempotency explicit.

### Phase 4: durable workflow execution

- Add durable checkpoints and resumable runs.
- Use typed state transitions.
- Add bounded retries and timeouts.
- Make workers idempotent.
- Add correlation IDs, audit metadata, and explicit failure states.
- Remove silent exception handling.

### Phase 5: versioned backend API

Stabilize authentication, authorization, validation, pagination, errors, rate
limits, and OpenAPI contracts before building the new frontend.

### Phase 6: Next.js frontend

- Use TypeScript and generated or shared API types.
- Implement loading, empty, retry, and error states.
- Keep Streamlit available for comparison.
- Compare key journey, friction, insight, and report results before retiring
  Streamlit.

### Phase 7: production hardening

Verify structured logs, metrics, tracing, dependency scanning, secret
scanning, rate limiting, audit events, backup/restore, migration rollback,
browser tests, integration tests, and failure-injection tests.

## 5. Antigravity prompt template

Use one prompt per phase or vertical slice:

```text
Work only on: <phase or issue>.

Read first:
- project_summary.md
- refactoring.md
- <specific implementation files>
- <specific tests>

Requirements:
- preserve existing behavior unless this task explicitly changes it;
- do not start later phases;
- do not rewrite unrelated modules;
- reuse existing project patterns;
- add or update targeted tests;
- surface errors explicitly;
- keep the application runnable at the end of the task.

Validation:
- run <exact test/lint/type-check commands>;
- inspect the final diff;
- report failures without hiding them.

Return:
1. changed files;
2. behavior and contract changes;
3. commands and results;
4. migration or rollback concerns;
5. remaining risks;
6. the smallest recommended next task.
```

## 6. ChatGPT Go review template

After Antigravity completes a slice, provide the diff summary, relevant diff,
test output, and changed contracts to ChatGPT Go:

```text
Act as an independent principal engineer reviewing this completed change.

Review only the supplied diff and test output for:
- correctness bugs;
- security vulnerabilities;
- data-loss or duplicate-write risks;
- race conditions and retry problems;
- API compatibility issues;
- missing tests;
- documentation drift.

Do not propose a broad rewrite without evidence.
Rank findings by severity and confidence.
For each real finding provide:
- file and line;
- why it is a defect;
- minimal safe fix;
- regression test required.
```

Only confirmed findings should be sent back to Antigravity for correction.

## 7. Daily operating loop

```text
1. Select one phase and one small vertical slice.
2. Ask Antigravity to inspect and implement only that slice.
3. Run local tests and inspect the diff.
4. Ask ChatGPT Go to review the supplied evidence.
5. Send confirmed findings back to Antigravity.
6. Run the tests again.
7. Commit the verified result.
8. Record the next task and any known risk.
```

## 8. Quota and context conservation

- Send file paths and diffs instead of the entire repository.
- Do not ask an agent to reread unchanged files.
- Keep a short worklog of decisions, failures, and next actions.
- Use local commands for deterministic operations.
- Prefer one implementation agent and one reviewer over several competing
  agents.
- Reserve the strongest model for cross-cutting changes.
- Break large features into reviewable vertical slices.
- Do not ask for speculative rewrites or premature optimization.
- Keep prompts explicit about scope and stop conditions.
- Commit before changing direction so rollback is cheap.

## 9. Definition of done for each slice

A slice is complete only when:

- the intended behavior is implemented;
- targeted tests pass;
- new failure cases have regression coverage;
- the diff contains no unrelated changes;
- configuration and documentation match the behavior;
- rollback or migration impact is understood;
- ChatGPT Go review findings are resolved or explicitly recorded;
- the commit is pushed to the phase branch.

The project should not be called production-ready until the complete
production-hardening phase and its verification gates pass.
