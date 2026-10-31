# Spec 15 — Production Hardening: Design

Implements the defaults in `requirements.md` §2. New Python code lives in `cji_agent/src/cji/observability/`,
`cji_agent/src/cji/ops/` and `cji_agent/src/cji/migrations/`; repository-level tooling in `ci/`. No new runtime
dependency.

## 1. Process map (OD-158)

| Process | Port (loopback) | Exposed through the proxy | Liveness | Readiness | Metrics |
|---|---|---|---|---|---|
| Next.js (`npm start`) | 3000 | yes (`/`) | `/healthz` | `/readyz` → API readiness | — |
| `cji-api` | 8006 | yes (`/api/v1`) | `/api/v1/health` | `/api/v1/health/ready` | `/api/v1/metrics` (admin token) |
| `cji-collector` (realtime) | 8000 | yes (`/collect/batch`, `/tracker.js`) | `/health/live` | `/health/ready` | `/metrics` (admin key) |
| MCP servers (5) | 8001–8005 | no | `/health` | `/health` (+ repository check for journey-data) | `/metrics` (loopback, no auth; LLM series on insight, report, ingestion) |
| `cji-dashboard` (optional) | 8501 | optional | Streamlit `/_stcore/health` | same | — |

`cji-ops status` reads the service registry and calls each readiness URL.

## 2. Logging (OD-159)

- `cji/logs.py`: `configure_logging()` reads `CJI_LOG_FORMAT`, `CJI_LOG_LEVEL` and `CJI_ENV` from the process
  environment (it must work before settings load, as today) and installs either the current text formatter (now
  with `request_id`) or `JsonFormatter`.
- `cji/observability/context.py`: context variables `run_id`, `trace_id`, `span_id` next to the existing
  `request_id` (`http/request_id.py`); `ContextFilter` adds all four to every record.
- `JsonFormatter`: `{"ts","level","logger","message","service","request_id","run_id","trace_id","exc_type"}`.
  In production the traceback text is dropped (`exc_type` only); in development it is kept.
- Workflow driver (`workflow/runtime.py`) sets `run_id` for the duration of a step.
- Next.js: `src/lib/log.ts` (`log(level, event, fields)`), JSON when `NODE_ENV=production`; the six existing
  `console.*` calls move to it. Fields are named, never interpolated user input.
- Settings: `CJI_LOG_FORMAT`, `CJI_LOG_LEVEL` added to known keys and the README table.
- Fix F-85: `runs.py:250` logs `comment_chars=<n>`.

## 3. Traces (OD-161)

- `cji/observability/trace.py`: parse and format W3C `traceparent` (`00-<32 hex>-<16 hex>-01`); `new_trace()`,
  `child_span(name)` context manager that records start, end, outcome and writes a `kind=span` audit record.
- API and collector middleware: take a valid incoming `traceparent` or create one; set `trace_id`/`span_id`; write
  the request span; return `traceparent` in the response.
- Next.js `lib/api/client.ts`: creates the trace at the edge and sends `traceparent` with `X-Request-ID`.
- Runs: the API stores `trace_id` and the request span id in the run's initial state (`trace_parent`); the CLI creates a
  new trace. Workflow steps are child spans; the gateway's tool and LLM calls are child spans of the step.
- MCP calls: `run_context` (already passed to the insight and report tools) gains `trace_parent`; the MCP servers' own
  gateway calls use it as parent, so their spans join the same trace from another process.
- `cji-trace show TRACE_ID [--audit-dir DIR]`: reads every `*.jsonl` in the audit directory and prints the span
  tree with latencies and outcomes.

## 4. Metrics (OD-160)

- `cji/observability/metrics.py`: `Counter`, `Gauge`, `Histogram` (buckets 0.005–30 s), label validation (fixed
  label names per series, values limited to route templates, status codes and enum values, so no user input becomes
  a label), thread-safe, `render()` in Prometheus text format 0.0.4. One registry per process.
- Series and where they are counted:

| Series | Process | Counted in |
|---|---|---|
| `cji_http_requests_total{route,method,status}`, `cji_http_request_seconds{route}` | API, collector | middleware (route = matched template, else `unmatched`) |
| `cji_rate_limited_total{limiter}` | API, collector | limiter rejections |
| `cji_auth_failures_total{reason}` | API | authentication |
| `cji_runs_active`, `cji_runs_finished_total{status}` | API | run service (API-driven runs only; CLI runs are not counted) |
| `cji_llm_calls_total{provider,outcome}`, `cji_llm_tokens_total{direction}`, `cji_llm_cost_usd_total` | MCP servers that call LLMs | gateway usage hook |
| `cji_tool_calls_total{service,tool,outcome}` | process calling tools (API, CLI) | gateway |
| `cji_collector_events_total{outcome}` | collector | `/collect/batch` |
| `cji_ingestion_rows_total{mode}` | API | ingestion commit |

- API route `GET /api/v1/metrics` (admin role; `text/plain; version=0.0.4`), added to the OpenAPI snapshot. Collector
  `GET /metrics` with `X-CJI-Admin-Key`. MCP servers `GET /metrics` through `custom_route` on their loopback port.

## 5. Security audit (OD-162)

- `integrations/audit.py`: `AUDIT_FIELDS` gains `actor`, `role`, `action`, `target`, `mode`, `rows`, `trace_id`,
  `span_id`, `parent_id`, `name`. New `security_event(action, *, actor, outcome, target=None, **fields)` writing to
  `default_sink("security")`. Unknown fields stay a programming error.
- Call sites: `tokens_cli` (create, revoke, rotate), API middleware (auth failed, auth rate limited), runs routes
  (start, resume, approve), ingestion routes (validate, write), collector (key create, key revoke, admin denied),
  `cji-backup` (create, restore), `cji-db` (apply).
- `cji-ops maintenance`: deletes audit lines older than `CJI_AUDIT_RETENTION_DAYS` by rewriting each file atomically,
  purges expired uploads and idempotency rows (already done at API start), and reports sizes.

## 6. Secrets (OD-163)

- `api/auth.py`: `rotate_token(path, token_id, overlap_hours)` returns the new token value; the old entry gets
  `expires_at = now + overlap` (or keeps an earlier expiry). `cji-api-token rotate`.
- Next.js `session-core.ts`: `openSession(cookie, secret, previous?)` tries the current key, then
  `CJI_SESSION_SECRET_PREVIOUS`; `proxy.ts` re-issues a cookie opened with the previous key using the current key.
  Config check: the previous key, if set, must also be ≥ 32 characters and differ from the current one.
- Collector: `POST /admin/api-keys/revoke` body `{api_key}`; admin key required; `UPDATE api_keys SET is_active=false`;
  404 when unknown; audit with fingerprint.
- `docs/operations.md` § "Secrets": table of every secret (from `settings` secret fields plus `CJI_SESSION_SECRET*`
  and API tokens): consumers, rotation steps, overlap, blast radius, tested by which test.

## 7. Scanning (OD-164)

- `cji_agent/scripts/secret_scan.py` (stdlib only): rules as regular expressions with names; scans (a) `git ls-files`
  and `git ls-files --others --exclude-standard`, (b) every added line in `git log -p --all --no-color` with the
  commit id. Output: `rule file:line [commit]` and a SHA-256 of the match (to allow-list without storing it).
  Allow-list `ci/secret-scan-allow.txt` (`rule path sha256`). Exit 1 on any unlisted finding. Never prints the match.
  Self-test: `tests/test_secret_scan.py` with generated fake keys in a temporary git repository.
- `ci/scans.py deps`: `pip-audit -r cji_agent/requirements.lock --format json` and `npm audit --json`; compares with
  `ci/exceptions.json` (`id`, `package`, `reason`, `owner`, `expires`); expired or missing exceptions fail.
- Container scanning: `release_check.py` reports `n/a` with reason and owner.

## 8. Abuse controls (OD-165)

- Settings: `CJI_API_TRUSTED_PROXY_HOPS` (API middleware stops reading the collector's setting),
  `CJI_API_AUTH_FAILURES_PER_MIN` (default 10), `CJI_FRONTEND_TRUSTED_PROXY_HOPS` (frontend env).
- API middleware: a third `RateLimiter` keyed by client address, checked **after** a failed token check; on rejection
  429 + `Retry-After` + `auth.rate_limited`.
- Next.js: `lib/client-address.ts` derives the client address from the socket peer or `x-forwarded-for` with the
  configured hops (same rule as `collector/security.client_address`); the API client sends it as `X-Forwarded-For`.
- `cji-settings check --role production` fails when `CJI_API_TRUSTED_PROXY_HOPS > 0` and the API binds a non-loopback
  host (anyone could then forge the header).

## 9. Backup and restore (OD-166)

`cji/ops/backup.py`, console script `cji-backup`.

- `create --out DIR [--include-audit] [--include-chroma]`: writes `DIR/cji-backup-<UTC time>/` with `postgres.dump`
  (`pg_dump --format=custom --no-owner --no-privileges --table=...` with the URL passed through the environment
  variable `PGPASSWORD` split from the URL, never on the command line), `sqlite/<name>.db` through
  `sqlite3.Connection.backup`, `files/...`, `manifest.json`. A secret scan of the manifest is part of the tests.
- `verify DIR`: hashes; `pg_restore --list postgres.dump` succeeds; SQLite `PRAGMA integrity_check`.
- `restore DIR --database-url URL --home DIR --confirm-database NAME [--replace]`: checks the target tables are absent
  or empty (else needs `--replace`, which truncates them in one transaction first), `pg_restore --no-owner
  --no-privileges --single-transaction`, copies SQLite and files, writes `restore-report.json` with row counts and
  table checksums (`md5(string_agg(row::text ORDER BY event_id))`).
- `pg_dump`/`pg_restore` location: `CJI_PG_BIN` or `PATH`; tests use pgserver's `pginstall/bin`. Major-version
  compatibility (client ≥ server) is checked and reported.

## 10. Migrations (OD-167)

- `cji/migrations/runner.py`: discovers `postgres/NNNN_name.{up,down}.sql` (package data), table
  `cji_schema_migrations(version int primary key, name text, checksum text, applied_at timestamptz)`, each migration in
  one transaction under `pg_advisory_xact_lock(<constant>)`; refuses when an applied file's checksum changed.
- `REQUIRED_SCHEMA_VERSION` constant in the package; readiness compares it with the database (realtime mode only).
- `0001_baseline.up.sql`: `CREATE TABLE IF NOT EXISTS` for `live_events`, `api_keys` (as the collector creates them)
  and `tracking_events` with the columns `ingest_json` writes. `0001_baseline.down.sql`: raises an exception (data
  tables are never dropped by a migration).
- `0002_indexes.up.sql`: duplicate check on `tracking_events.event_id` (raises with the count), unique index on it,
  indexes on the columns the repository queries filter and order by (taken from `repositories/queries.py` at
  implementation). `0002_indexes.down.sql`: drops those indexes.
- `cji-db migrate status` also compares column names and types with the baseline and lists differences (an existing
  table created by pandas may differ; differences are reported, not changed).
- `tools/ingest_json._write_tracking_events(replace=True)`: `DELETE FROM tracking_events` and append in one
  transaction; creates the table through migration 0001 if it does not exist instead of `to_sql(if_exists=...)`.
- The collector keeps `_create_tables()` for development; in production it requires the schema version instead.

## 11. Health (OD-168)

- API `routes/health.py`: `GET /health/ready` (public, no details, rate-limited like other public paths).
- MCP `_serve.py`: registers `@mcp.custom_route("/health")` and `/metrics` before `mcp.run`.
- Next.js: `src/app/healthz/route.ts`, `src/app/readyz/route.ts` (no session needed; excluded from the session gate in
  `proxy.ts`; `readyz` returns 503 when the API is not ready or unreachable, without the API's details).
- `cji/ops/status.py` → `cji-ops status [--json]`.

## 12. Recovery suite (OD-169)

- `tests/_system.py`: starts pgserver, migrates, starts the collector, the API and the MCP servers as subprocesses
  with a temporary `CJI_HOME`, protected-environment variables and free ports; waits for readiness; can kill and
  restart one process; collects their logs for the canary scan.
- `tests/test_recovery.py`: the seven cases of OD-169 (marker `recovery`). LLM unreachable = provider URL set to a dead
  local port. Unwritable reports = `CJI_REPORTS_DIR` pointing at a file. Each test appends its observed result to
  `RECOVERY_LOG` (written to `evidence/recovery.md` by the gate).

## 13. CI runner (OD-170)

`ci/run_ci.py [--stage NAME ...] [--network]`; stages and commands:

| Stage | Commands |
|---|---|
| format | `ruff format --check` on `ci/formatted.txt` |
| lint | `ruff check` (≤ 92), `bandit -c pyproject.toml -r src` (≤ L25/M10/H0), `npm run lint` |
| types | `mypy` (≤ 33), `mypy --strict` on the Spec 14 strict set plus `observability`, `ops`, `migrations`, `npm run typecheck`, `npm run api:check` |
| unit | `pytest -m "not integration and not recovery"`, `npm test` |
| integration | `pytest -m recovery` (pgserver and real processes) |
| browser | `next build`, Playwright fixture specs, `npm run bundle:scan` |
| scans | `secret_scan.py`; with `--network`: `ci/scans.py deps` |

It runs in the protected environment (dead proxy, dead database URLs, dummy keys) except the `--network` scan step,
writes `ci/out/<stage>.log`, JUnit XML and `summary.md`, and exits 1 if any stage fails. `ci/out/` is git-ignored.

## 14. Deployment and environment validation (OD-171, OD-172)

- `settings/roles.py`: role `production` = union of the roles of the processes named by `--processes`
  (default all) plus the OD-171 rules; each rule is a function with a message and a test.
- `CJI_MODE` without a value in production → configuration error ("set CJI_MODE=realtime or demo explicitly").
- `frontend/scripts/check-env.ts` (run with Node 24 type stripping) imports `config-core.ts` and the new
  `client-address`/session rules; `npm run check:env`; `instrumentation.ts` validates at server start and exits on
  error.
- `docs/deployment.md`, `docs/operations.md` (limits, AI budgets, secrets, development-only behaviour, runbooks:
  rotate, restore, migrate, roll back, incident first steps), `docs/release-checklist.md` (generated).
- `tests/test_dev_defaults.py`: production settings snapshot; AST scan of `src/` for comparisons with
  `"development"` compared against the inventory list in `docs/operations.md`.
- `tests/test_operations_doc.py`: every settings field and known key appears in the limits table, and every key in
  the table exists.

## 15. Canary scan (OD-173)

`ci/sensitive_scan.py --markers FILE --paths ...`: markers are generated per gate run (`cji-canary-<random>` style
values that are valid for each secret's format rules, e.g. ≥ 32 characters). The gate sets them, runs the live flow and
the recovery suite, then scans text files, SQLite files (as bytes), the `.next/static` bundle and captured HTTP
responses. Report: per marker, the files where it was found; exit 1 on any secret marker, or a user marker outside
the event store and the backup dump.

## 16. Release check (OD-174)

`ci/release_check.py [--evidence DIR]` maps every control to a check:

| Control | Check | Pass when |
|---|---|---|
| Logs | gate JSON-log assertion (`evidence/logs-check.json`) | every service line parses; a request id links Next.js → API → run → MCP |
| Metrics/traces | `/metrics` scrape files; `cji-trace show` output | series present; one trace spans ≥ 3 processes |
| Audit | `security.jsonl` from the gate | every OD-162 action seen; field allow-list holds |
| Secrets | rotation tests in JUnit | all pass |
| Dependency scan | `ci/scans.py deps` JSON | no advisory without a valid exception |
| Secret scan | `secret_scan.py` | no unlisted finding (tree and history) |
| Container scan | — | `n/a` (no image), owner recorded |
| Abuse controls | tests | pass |
| Backup/restore | drill report | counts and checksums equal |
| Migration rollback | drill report | up/down/up and old release on rolled-back schema pass |
| Health/readiness | `cji-ops status --json` from the gate | all ready; failure cases flip to not ready |
| Recovery | `evidence/recovery.md` + JUnit | 7/7 |
| CI | `ci/out/summary.md` | every stage passed |
| Deployment docs/env validation | tests | pass; docs exist |
| Sensitive data | canary report | clean |
| Owner items | requirements §4 | listed as `blocked`/`n/a` until the owner records evidence in `ci/owner-evidence.json` |

Output: table in `docs/release-checklist.md` and `ci/out/release-check.json`; final line `READY` or `NOT READY (n
blocked, m failed)`; exit 0 only for READY. The gate records the result without requiring READY (§4 items are
expected to block).

## 17. Rollback drill (OD-175)

`ci/rollback_drill.py --old-wheel W011 --new-wheel W015 --old-frontend DIR`: temporary venvs (`uv`/`venv` with
`pip install --no-index --find-links` from a local wheelhouse built at T0 from `requirements.lock`, so no network),
temporary home, pgserver. Steps and comparisons as in OD-175; writes `evidence/rollback-drill.md` with every
command, exit code and compared value.

## 18. Gate (`evidence/scripts/gate_spec15.ps1`)

A: network process: `npm ci`, wheelhouse check, `ci/scans.py deps`. B: `ci/run_ci.py` (all stages). C: live system
with canary markers (pgserver, migrations, collector, API, MCP servers, Next.js production build): Spec 14 live
Playwright specs, parity check, metrics scrape, trace check, JSON-log check, rotation checks, `cji-ops status`.
D: recovery suite. E: backup/restore and rollback drill. F: canary scan over everything from C–E. G: release check,
OpenAPI snapshot, `cji --help`/`cji-dashboard --help`, `git diff --check`, git status. Ports freed and temporary
databases removed at the end.

## 19. Files

New: `observability/{__init__,context,trace,metrics}.py`, `ops/{__init__,backup,status,maintenance,cli}.py`,
`migrations/{__init__,runner}.py` + `migrations/postgres/*.sql`, `ci/{run_ci,scans,sensitive_scan,release_check,
rollback_drill}.py`, `ci/{formatted.txt,exceptions.json,secret-scan-allow.txt,owner-evidence.json}`,
`cji_agent/scripts/secret_scan.py`, tests (`test_logging`, `test_trace`, `test_metrics`, `test_security_audit`,
`test_rotation`, `test_secret_scan`, `test_backup`, `test_migrations`, `test_health_ready`, `test_recovery`,
`test_dev_defaults`, `test_operations_doc`, `test_production_check`, `_system.py`), frontend (`lib/log.ts`,
`lib/client-address.ts`, `app/healthz`, `app/readyz`, `instrumentation.ts`, `scripts/check-env.ts`, tests), docs
(`deployment.md`, `operations.md`, `release-checklist.md`).

Changed: `logs.py`, `http/request_id.py`, `integrations/{audit,tools,llm,usage}.py`, `workflow/runtime.py`,
`api/{app,middleware,auth,tokens_cli,openapi}.py`, `api/routes/{health,runs,ingestions}.py`, `collector/{api,serve}.py`,
`mcp_servers/_serve.py`, `settings/{load,model,roles}.py`, `tools/ingest_json.py`, `services/{runs,ingestion}.py`,
`pyproject.toml` (version 0.15.0, console scripts `cji-backup`, `cji-db`, `cji-ops`, `cji-trace`, package data, pytest
marker `recovery`), `openapi/v1.json`, frontend (`proxy.ts`, `session-core.ts`, `config-core.ts`,
`lib/api/client.ts`, `app/actions.ts`, loaders, report proxy, `package.json` scripts, `.env.example`), README,
`.env.example`, `docs/README.md`, `.gitignore` (`ci/out/`).

## 20. Risks

| Risk | Mitigation |
|---|---|
| Changing `--replace` from drop-and-recreate to delete-and-append changes how a table with a different pandas-inferred schema behaves | `migrate status` reports differences; replace into a mismatching table fails with a clear message instead of silently recreating; documented in the migration notes |
| JSON logs change what operators see | Text stays the default outside production; `CJI_LOG_FORMAT=text` restores it anywhere |
| Unique index on `event_id` fails on a database with duplicates | 0002 counts duplicates first and stops with the count and a cleanup query in the docs |
| Session re-issue in `proxy.ts` | Unit tests for both keys; cookie options unchanged |
| The rollback drill needs the old wheel's dependencies offline | Wheelhouse built at T0 in the network process; the drill fails loudly if a wheel is missing |
| Recovery tests are slow or flaky | Fixed waits replaced by readiness polling with deadlines; each case isolated with its own ports and home |

## 21. As implemented (differences from this design)
Details in `tasks.md` (D-1 to D-17, G-1 to G-16).
- §6, §14: `CJI_MODE` is required only when `CJI_ENV=production` is set explicitly. The schema-version check is
  `cji-db migrate status --require-current`, not part of `cji-settings check` (the settings package imports only the
  standard library, pydantic and dotenv).
- §2: uvicorn, FastMCP and early settings warnings log through the CJI handler, so every line of every service is one
  JSON object in production. MCP servers bind the workflow's `run_context` for each tool call (run id in their lines).
- §4, §11: MCP servers serve `/metrics` and `/health` on their loopback ports; `GET /api/v1/health/ready` is public.
- §12, §18: the recovery suite runs in the CI runner's integration stage; the gate has an extra phase C2 that runs the
  Spec 14 parity script on the new code.
- §15: the canary scan skips the database dump and the key-creation response, and allows user markers in staged
  uploads; the Next.js → API link is checked with a sealed session cookie and a caller `traceparent`.
- §17: no wheelhouse. The drill's venvs reuse the tested dependency set of the gate's interpreter and install the CJI
  wheels without dependencies or network; it starts the collector before 0.11.0's servers and shifts the demo events
  into the realtime window.
- §19: tests are grouped in `test_production_hardening.py` instead of one file per control; `test_secret_scan.py` and
  `test_ci_tools.py` cover the scripts.

