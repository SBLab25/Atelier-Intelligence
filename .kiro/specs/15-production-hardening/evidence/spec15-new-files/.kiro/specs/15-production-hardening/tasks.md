# Spec 15 — Production Hardening: Tasks

Sequential. `[x]` means the checks ran and passed. No commits or pushes. **Environment:** protected environment for
tests and builds (dead proxy, dead database URLs, dummy keys); network only for `npm ci` and the dependency scans,
each in a separate process. PostgreSQL work uses throwaway pgserver databases only; the real
`SUPABASE_DATABASE_URL` is never read or used.

**Status:** implemented 2026-10-29 (approved: "implement spec 15", decisions OD-158 to OD-177 as written). Final gate
(12:54–13:14): every phase passed except the CI format step (`ci/release_check.py` was not reformatted after its last edit). The file was formatted afterwards and the format check passes on its own; the release check from that run says **NOT READY (6 blocked, 1 failed)** until a full gate rerun. Record below.

## T0 Preparation
- [x] Copies of the files this Spec changes in `evidence/pre-spec15-untracked/` (52 files); `frontend/` source in
      `evidence/pre-spec15-frontend/` (100 files).
- [x] Wheel 0.11.0 of the pre-Spec 15 code in `evidence/wheels/`. The wheelhouse was not built (D-10).
- [x] Baselines (survey, Spec 14 gate): pytest 1205 passed / 1 skipped; ruff 92; mypy 33 in 11 files; bandit
      L25/M10/H0; Vitest 124; OpenAPI 18 operations.

## T1 Logs and correlation (R1)
- [x] `observability/context.py`, JSON and text formatters, `CJI_LOG_FORMAT`/`CJI_LOG_LEVEL`; run id in the workflow;
      approval comment no longer logged (F-85).
- [x] Next.js `lib/log.ts`; `console.*` replaced.
- [x] Tests: formatter fields, production drops tracebacks, context propagation; every service line JSON (G-13).

## T2 Traces and metrics (R2)
- [x] `observability/trace.py`; `traceparent` in Next.js, API, collector, workflow, gateway, MCP `run_context`;
      `cji-trace show`.
- [x] `observability/metrics.py`; API `/api/v1/metrics` (admin), collector `/metrics` (admin key), MCP `/metrics`
      (loopback); OpenAPI snapshot (21 paths, 22 operations).
- [x] Tests: exposition format, label limits; one trace across 4 services in the gate's live phase.

## T3 Security audit (R3)
- [x] `security_event` with 16 actions; call sites; `cji-ops maintenance` retention.
- [x] Tests: each action writes one record; allow-list; no secret, comment or address. Live phase: 13 actions seen.

## T4 Secrets and rotation (R4)
- [x] `cji-api-token rotate`; `CJI_SESSION_SECRET_PREVIOUS` with re-issue; collector key revoke; cursor rotation.
- [x] Secret inventory in `docs/operations.md`.
- [x] Tests: rotations end to end; live phase: rotated token old 401 / new 200, revoked tracker key 401.

## T5 Scanning (R5)
- [x] `secret_scan.py` (tree + history, allow-list, never prints values) with `tests/test_secret_scan.py`;
      `ci/scans.py deps` with `ci/exceptions.json`.
- [x] Both ran: secret scan 0 open findings; a tracker key in git history and an example key in the docs were
      reported to you as owner items. Dependency scan: 23 Python advisories open (blocked, owner).

## T6 Abuse controls (R6)
- [x] `CJI_API_TRUSTED_PROXY_HOPS`; failed-auth limiter (`CJI_API_AUTH_FAILURES_PER_MIN`); Next.js forwards the
      client address; production check refuses hops with a non-loopback bind.
- [x] Tests: per-client sign-in limit, failed-auth 429; recovery case "rate-limit flood".

## T7 Migrations (R8)
- [x] Runner, `cji-db`, 0001 baseline, 0002 indexes; schema check in readiness; `--replace` as delete + append.
- [x] Tests on pgserver: fresh database, adopted database, duplicates stop 0002, up/down/up with data, changed file
      refused.

## T8 Backup and restore (R7)
- [x] `cji-backup create|verify|restore`.
- [x] Tests on pgserver; drill: restore into a fresh database and home, 3 tables and the token file equal.

## T9 Health and readiness (R9)
- [x] API `/health/ready`; MCP `/health`; Next.js `/healthz`, `/readyz`; `cji-ops status`.
- [x] Tests; live phase: 7 services ready, exit 1 with `cji-insight` stopped.

## T10 Production check and development defaults (R12, R13)
- [x] `cji-settings check --role production` rules; explicit `CJI_MODE` when `CJI_ENV=production` (D-1); frontend
      `check:env` and start validation.
- [x] One test per rule and the development-defaults inventory test (in `test_production_hardening.py`, D-16).

## T11 Recovery suite (R10)
- [x] `tests/_system.py`, `tests/test_recovery.py` (7 cases, 7 passed); `evidence/recovery.md`.

## T12 CI runner (R11)
- [x] `ci/run_ci.py`, ratchets, `ci/formatted.txt` (26 files), JUnit and summary; `.gitignore` for `ci/out/`.
- [ ] Final gate run: 14 of 15 steps (format failed, fixed afterwards); the run before: 15 of 15.

## T13 Documentation (R15)
- [x] `docs/deployment.md`, `docs/operations.md`; README, both `.env.example` files, `frontend/README.md`,
      `docs/README.md`; `test_operations_doc.py`.

## T14 Canary scan, release check, rollback drill (R14, R16, R17)
- [x] `ci/sensitive_scan.py`, `ci/release_check.py`, `ci/rollback_drill.py`; `docs/release-checklist.md` generated;
      `tests/test_ci_tools.py`.

## T15 Gate
- [x] `evidence/scripts/gate_spec15.ps1`; final run below.

## T16 Final record
- [x] This section. Scratch files in `C:\Users\sovan\.kiro` not deleted yet.

## Final gate (2026-10-29 12:54–13:14)
`evidence/scripts/gate_spec15.ps1` ran to the end; per-step exit codes in `evidence/gate-results.txt`, logs in
`evidence/gate-*.log`, release evidence in `evidence/release/`. Earlier runs failed on the canary scan (G-15) and
had an unreadable CI detail (G-16); both were fixed and the gate was run again. The parity phase (C2) was added
after a run that did not include it, and the gate was run again in full.

| Check | Result |
|---|---|
| `npm ci` (network) | exit 0 |
| Dependency scan (network): `pip-audit -r requirements.lock`, `npm audit` | 23 Python advisories, 0 npm, 0 scanner errors; none accepted (blocked, owner) |
| ruff format `--check` on `ci/formatted.txt` | FAIL in the final run (`ci/release_check.py`); after formatting 26 of 26 files pass |
| ruff / bandit | 92 findings (ratchet ≤ 92); Low 25 / Medium 10 / High 0 (ratchet) |
| mypy (project) / mypy `--strict` (Spec 14 set + `observability`, `ops`, `migrations`) | 33 errors (ratchet ≤ 33) / 0 errors |
| ESLint, `tsc --noEmit`, `api:check` | pass |
| pytest `-m "not integration and not recovery"` | 1288 passed, 1 skipped |
| Vitest | 138 passed (was 124) |
| pgserver tests + recovery suite | 24 passed; recovery 7 of 7 (`evidence/recovery.md`) |
| `next build`, Playwright fixture specs, bundle scan | pass; Playwright 19 passed, 4 skipped (the live specs) |
| Secret scan (tree and history) | 0 open findings, 22 allow-listed |
| Live phase (pgserver, collector, API, 5 MCP servers, Next.js production build, canary markers) | every line of 7 service logs is JSON; request → run → MCP lines linked; Next.js trace id found in API lines; trace across 4 services; 13 audit actions, no forbidden field; 7 metric series; rotation old 401 / new 200, revoked tracker key 401; readiness 7/7, exit 1 with one server stopped; live browser tests 5 passed |
| Parity (Spec 14 script on 0.15.0, demo data) | 31 of 31 checks passed |
| Rollback drill (`evidence/rollback-drill.md`) | 0.11.0 → backup → 0.15.0 + `migrate up` → `CJI_API_WRITE_OPERATIONS=false` → `migrate down --to 1` → 0.11.0 again → `migrate up`; results of all three runs equal; pre-Spec 15 frontend smoke test passed against the 0.15.0 API; restore equal |
| Canary scan (16 markers, 92 files: logs, home incl. audit/reports/databases, HTTP responses, Next.js log and bundle, restored home, backup except the dump) | 0 violations |
| Release check | **NOT READY (6 blocked, 1 failed)**: the failed row is CI (format step); `docs/release-checklist.md` |
| OpenAPI snapshot; `cji --help`; `cji-dashboard --help` | match; both work (CLI and Streamlit kept) |
| `git diff --check`; ports 8000–8006, 3100 after the gate | clean; none listening |

## Release check: owners and blockers
| Item | Result | Owner | Blocker |
|---|---|---|---|
| Dependency advisories: chromadb 1.5.9, langchain-core 0.3.86, langgraph 0.2.28, langgraph-checkpoint 1.0.12, langgraph-checkpoint-sqlite 1.0.4 (23 advisories) | blocked | Project owner | upgrade (needs a compatibility Spec) or accept each with reason and expiry in `ci/exceptions.json` |
| Tracker key in git history (`Live Web Demo Key`, journey `my_vercel_site`, fingerprint `8aa90e8de3b9c744`) | blocked | Project owner | revoke it (`POST /admin/api-keys/revoke`) or confirm it is inactive; record in `ci/owner-evidence.json` |
| Example key in `docs/6-API-Contracts.md` (fingerprint `54d5b3115cb8abb1`) | blocked | Project owner | confirm it was never issued |
| Supabase provider-side backups and restore | blocked | Project owner | check the backup schedule and do one restore test in the Supabase dashboard |
| Migrations on the real Supabase database | blocked | Project owner | `cji-backup create`, then `cji-db migrate up` (`docs/deployment.md`) |
| TLS proxy and process supervision on the release host | blocked | Project owner | host not provisioned; the guide has examples only |
| Container scanning | n/a | Project owner | no image is built (OD-158) |
| Hosted CI | n/a | Project owner | the project is not pushed; `ci/run_ci.py` is the local runner |

## Findings, gate findings and deviations
| ID | What | Resolution |
|---|---|---|
| G-1 | pgserver's PostgreSQL has no time-zone database, so `SET TIME ZONE 'UTC'` failed in the backup checksums. | Numeric offset `INTERVAL '+00:00' HOUR TO MINUTE`. |
| G-2 | `pg_ctl` started with captured pipes never returned (the server inherits the handles). | The harness passes `DEVNULL` handles. |
| G-3 | Vitest failed when the repository path had a lower-case drive letter (Vite on Windows). | Scripts use `C:\...`; documented. |
| G-4 | An unwritable reports directory made `POST /runs` answer 500 (`FileExistsError`). Found by the recovery suite. | `OSError` maps to 503 `storage_unavailable`; the report step fails with `report_write_failed` and resume completes after the fix. |
| G-5 | HTTP metric route labels lacked the `/api/v1` prefix. | Route templates include the prefix. |
| G-6 | The `report_write_failed` message returned by the API contained the server's filesystem path. Found by the recovery suite. | OS error text only; regression test. |
| G-7 | Next.js `headers()` called outside a request in `loaders.ts`. | `edgeHeaders` tolerates it. |
| G-8 | ESLint forbids `console.log` in `check-env.mjs`. | `console.info` / `console.error`. |
| G-9 | Recovery tests waited for `failed` right after resume (202 returns the run as it was) and started a second run while `CJI_API_MAX_ACTIVE_RUNS=1` was full (409). | Tests wait for `completed` and for the other run to end. Product behaviour is as designed. |
| G-10 | Rollback drill: realtime mode reads a window ending now, so the March–April demo data gave `no_step_metrics`. | The drill shifts the events to end 10 minutes ago and uses a 30-day window. No product change. |
| G-11 | Rollback drill: 0.11.0's journey-data server needs `live_events`, which 0.11.0 creates when the collector starts. | The drill starts the collector first, as a deployment does. |
| G-12 | Rollback drill: a venv with only a path line to the tested site-packages could not import `pywintypes` (its `.pth` was not processed). | `site.addsitedir`; the drill checks that `cji` comes from the installed wheel. |
| G-13 | Not every service line was JSON: uvicorn's own handlers (start-up and access lines), the FastMCP banner and rich handlers, settings warnings logged before logging started in the MCP servers. MCP lines had no run id. | `uvicorn.run(..., log_config=None)`; `mcp.run(show_banner=False, uvicorn_config={"log_config": None})`; FastMCP loggers propagate to the CJI handler; settings warnings are held until `configure_logging()`; `logging.captureWarnings(True)`; an MCP middleware binds the workflow's `run_context` per tool call and logs one line per call. Tests added. |
| G-14 | Spec 15 code added 14 ruff findings and 8 mypy errors (ratchets failed); the bandit JSON was not parsed (stderr after it). | Fixed to the baselines; `raw_decode` for bandit. |
| G-15 | Canary scan: the tracker key appeared in the recorded response of the key-creation request. That response hands the new key to the admin once, by design. | The gate does not record that one body. |
| G-16 | `run_ci.py` passed `-q` on top of `addopts = -q`, so pytest printed no summary and the CI detail showed only the exit code. | Single `-q`; ANSI codes stripped. |
| D-1 | Design: `CJI_MODE` required in production. | Required when `CJI_ENV=production` is set explicitly; an unset `CJI_ENV` still behaves as production but keeps the demo default (existing tests and local use). |
| D-2 | Design: schema check in `cji-settings check`. | In `cji-db migrate status --require-current`; the settings package must import only the standard library, pydantic and dotenv (existing test). |
| D-3 | Design: `invalid_cursor` 400. | 422; docs and requirements corrected. |
| D-4 | — | MCP servers serve `/metrics` (with the LLM series) and `/health` on their loopback ports. |
| D-5 | — | `GET /api/v1/health/ready` is public; its 503 keeps the plain JSON body in OpenAPI (`PLAIN_ERRORS`). |
| D-6 | — | The secret-scan allow-list excludes `.kiro/specs/` (local evidence copies of earlier trees). |
| D-7 | Design: `CJI_RECOVERY_LOG`. | `RECOVERY_LOG`: settings refuse unknown `CJI_` names in tests. |
| D-8 | — | The API maps `OSError` to 503 `storage_unavailable` (was 500). |
| D-9 | — | `docs/release-checklist.md` is generated by `ci/release_check.py`; owner evidence goes in `ci/owner-evidence.json`. |
| D-10 | Design: wheelhouse from `requirements.lock` for the drill. | Not built. The drill's venvs reuse the tested dependency set of the gate's interpreter (`site.addsitedir`) and install the CJI wheels with `--no-deps --no-index`; no network, same versions. |
| D-11 | Design §18 phase D (recovery suite) separate. | Runs in the CI runner's integration stage (phase B). |
| D-12 | — | The drill copies `node_modules` for the old frontend: Turbopack refuses a junction outside the project. |
| D-13 | — | The canary scan skips the database dump (it is the event store and holds `api_keys` by design) and allows user markers in `data/ingestion_uploads/` (staged uploads until they expire). |
| D-14 | — | `[tool.ruff] line-length = 120` (only `ruff format` uses it; E501 is not selected). |
| D-15 | Design: the request-id chain checked through the browser. | The gate seals a session cookie with the frontend's own code (`seal_session.mjs`) and sends a page request with its own `traceparent`; the trace id is found in the API's lines. |
| D-16 | Design: separate test files (`test_logging`, `test_trace`, `test_metrics`, `test_security_audit`, `test_rotation`, `test_health_ready`, `test_dev_defaults`, `test_production_check`). | One `test_production_hardening.py` with a section per control, plus `test_operations_doc`, `test_secret_scan`, `test_ci_tools`, `test_migrations`, `test_backup`, `test_recovery`. |
| D-17 | — | Gate phase C2 runs the Spec 14 parity script on the new code (R18). |

## Behaviour changes for users
- JSON logs when `CJI_ENV=production` (or `CJI_LOG_FORMAT=json`), with `service`, `request_id`, `run_id`, `trace_id`;
  production log lines carry the exception type, not the traceback.
- New commands: `cji-db`, `cji-backup`, `cji-ops`, `cji-trace`; `cji-api-token rotate`; collector
  `POST /admin/api-keys/revoke` and `GET /metrics`; API `GET /api/v1/metrics` (admin) and public
  `GET /api/v1/health/ready`; Next.js `/healthz`, `/readyz` and `npm run check:env`.
- Failed authentications are limited per client address; behind proxies set `CJI_API_TRUSTED_PROXY_HOPS` /
  `CJI_FRONTEND_TRUSTED_PROXY_HOPS`.
- `cji-ingest-json --replace` deletes and appends instead of recreating the table; rows repeating an `event_id` are
  written once.
- Version 0.15.0. Streamlit and the CLI are otherwise unchanged.

## Rollback
Tested by the drill (`evidence/rollback-drill.md`): `CJI_API_WRITE_OPERATIONS=false` for write operations;
`cji-db migrate down --to 1` and the 0.11.0 wheel for the code; `cji-backup restore` for data. Code from this tree:
copy `evidence/pre-spec15-untracked/` back, delete the files listed in `evidence/spec15-new-files/MANIFEST.txt` that
are not in the backup, and `pip install --no-deps -e cji_agent`.

## Findings carried forward
| ID | Finding | Owner |
|---|---|---|
| OD-102 / F-53 | 23 dependency advisories (LangGraph, LangChain-core, Chroma) | Project owner decision, later Spec |
| Owner items | Tracker key in history, example key, Supabase backups, Supabase migrations, release host | Project owner |
| F-76, F-78, F-79, F-49, run paging | Spec 14 carry-overs | Later Spec |
| Spec 12 "New" | Per-process rate limits, idempotency state and active-run count (one API process) | Later Spec |
| F-16, F-22 to F-25, F-27, F-28 | Owner checks | Owner |
