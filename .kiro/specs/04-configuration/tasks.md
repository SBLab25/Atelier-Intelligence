# Spec 04 — Typed Configuration and Service Discovery: Tasks

Sequential. `[x]` means evidence exists. No commits or pushes: each step is recorded as a patch file in `evidence/`.

**Environment:** protected environment from `01-baseline/requirements.md` §8 plus `JOURNEY_NAME=user_onboarding`;
interpreter `C:\Users\sovan\.venvs\cji-baseline-312`. **The Supabase database is live again (owner, 2026-10-28):** every
run in this Spec set both `DATABASE_URL` and `SUPABASE_DATABASE_URL` to a dead local port, so nothing reached it.

**Status:** implemented 2026-10-28 after approval ("implement spec 04", OD-26 revised: keep `SUPABASE_DATABASE_URL`).

## Tasks

- [x] **T0 Prepare.** `pre-spec04-tracked.patch` (69,511 bytes, identical in size to Spec 03's final patch). Survey
  of every config read, port, URL, timeout and secret: requirements §1. Library check: fastmcp 4.1.4 `run(transport,
  host=, port=)`; mcp 2.3.0 `sse_client(timeout=5.0, sse_read_timeout=300.0)` (the defaults now made explicit).
- [x] **T1 Failing tests first.** `tests/test_settings.py` (105 tests) run before any caller was migrated:
  **86 pass, 19 fail** (`before-settings.log`, `before-settings-junit.xml`). The 19 are the caller-side contracts:
  `mcp_client.server_url`, launcher `main(argv)`, 5 × `serve(...)` entry points, collector `UnconfiguredDatabase`,
  CLI exit 2, dashboard role, `config.SETTINGS`, report/insight timeouts, generator upload in test, keep-alive
  URL, and the port scan (14 literals found). *Deviation:* the `settings/` package was written before this first
  run, so its own load/validation tests passed at the first run rather than failing first.
- [x] **T2 `settings/` package.** `errors`, `services` (only place with default ports), `model`, `load`, `roles`,
  `__init__` (`get_settings`, `override_settings`, `make_test_settings`), `__main__` (`python -m settings check`).
  mypy `--strict` clean; ruff clean; imports only stdlib, pydantic, python-dotenv (test enforced).
- [x] **T3 Service discovery.** `tools/mcp_client.py` resolves endpoints at call time and passes MCP timeouts;
  `ping_all_servers` iterates the registry. `run_servers.py` launches the registry's MCP services and exits 2 on a
  configuration error. New `mcp_servers/_serve.py`; all 5 servers start with `serve(mcp, "<name>")`.
- [x] **T4 Collector.** Settings for env, admin key, CORS, database (`UnconfiguredDatabase` when unset) and dev key;
  startup reports admin key, CORS, database and http-in-production problems together as one `ConfigError`;
  `validate_collector_settings` kept as a wrapper (Spec 02 tests unchanged and passing). Render keep-alive removed;
  optional `CJI_KEEPALIVE_URL`.
- [x] **T5 Other startup paths and callers.** `main.py` (`require("cli")`, exit 2, `recursion_limit`,
  `collector_url`); `dashboard.py` (`require("dashboard")`, database via settings incl. `SUPABASE_DATABASE_URL`,
  paths, `sys.executable`, pipeline timeout); insight/report Groq key and timeout from settings (report call was
  unbounded, now 30 s); ingestion LLM timeouts and realtime database; `rate_limiter` retry policy;
  `journey_data_server` database; `synthetic_data` (no upload in `test` or without a database);
  `ingest_json` (database required, actionable error); `snippet_generator` default host.
- [x] **T6 Facade and docs.** `config.py` is a facade over settings (same names; `DATABASE_URL`/`CJI_ADMIN_KEY` are
  `""` when unset). `tests/conftest.py` sets `CJI_ENV=test` and adds `cji_settings`. `.env.example` lists every
  variable (D-25 closed). Spec files updated for the revised OD-26 and the collector rule in `test`.
- [x] **T7 Gate.** Results below. Rollback files saved.

## Gate results (T7)

Logs in `evidence/`; summary in `final-numbers.txt` and `gate-results.txt` (second full run, 2026-10-28 00:51–00:55,
after lint fixes in `settings/load.py`, `settings/roles.py`, `tests/conftest.py`, `tests/test_settings.py`,
`tracker/snippet_generator.py`).

| Check | Result | Spec 03 |
|---|---|---|
| `tests/test_settings.py` | **105/105** (before migration 86/105) | — |
| Full suite (`-m "not integration"`) | **344/355**; the 11 failures are exactly the F-01 set | 239/250 |
| Golden journey-data snapshot | **identical** to Spec 03 | — |
| ruff | **246** total; no changed file worse than baseline; `settings/`, `_serve.py`, `test_settings.py` clean | 255 |
| mypy | **46** total; no changed file worse; `settings/` clean with `--strict` | 49 |
| bandit (medium+) | none in any changed file; `report_server.py` B113 (request without timeout) 1 → 0 | — |
| `python -m settings check` with the owner's `.env` | exit 0 (cli and launcher); 2 deprecation warnings | — |
| Launcher | 5 servers listening; each logged `Starting <name> on 127.0.0.1:<registry port> (sse)` | same ports |
| Demo pipeline | exit 0; 8 step metrics, 4 critical, 4 insights, report written; 0 contract violations | same |
| Ingest probe | exit 0; 4 posts to 8005, 0 × 404, no iteration-cap hit; file flagged | same |
| `git -c core.whitespace=cr-at-eol diff --check` | clean | clean |
| Tracked `data/events.parquet` | unchanged | unchanged |

Acceptance criteria (requirements §5):
1. **No duplicated ports:** the scan over all production modules finds none; ports appear only in
   `settings/services.py`. Not scanned, by name: `tracker/tracker.js`, `snippets/*` (Specs 07/13), legacy scripts (Spec 06).
2. **Missing/invalid configuration:** 16 invalid-value cases plus missing-secret, missing-database, unknown-key,
   unknown-role/service cases; each checks variable name, fix hint, and that sentinel secrets never appear.
3. **Development, test, production:** role × environment matrix (offline demo for every role in every environment,
   realtime database requirement, collector secrets per environment, http-in-production rule).
4. **Startup paths:** launcher plan = registry; every server file starts through `serve` with its own name; `serve`
   binds the registry endpoint (override honoured); preflight pings every service the workers use; collector startup
   passes in development and lists all three problems in production; CLI realtime without a database exits 2;
   dashboard resolves through its role; plus the live smoke runs above.

## Behaviour changes to know about

- Neither `DATABASE_URL` nor `CJI_ADMIN_KEY` has a default any more (they used a `postgres:password` URL and
  `change-me-in-production`). `SUPABASE_DATABASE_URL` now works for every caller when `DATABASE_URL` is unset.
- In `CJI_ENV=test` (set by `conftest.py`), `.env` is not read and the demo-data generator never uploads to
  PostgreSQL. Before this Spec, a plain `pytest` run loaded `.env` and replaced the `demo_events` table in whatever
  database it named.
- Configuration errors now stop `main.py` and `run_servers.py` with exit code 2 and a numbered list of fixes.
- The report narrative LLM call times out at 30 s (`CJI_LLM_TIMEOUT_S`).
- The collector no longer pings the Render URL; set `CJI_KEEPALIVE_URL` to enable a ping.
- The CLI's `collector_url` default is `http://127.0.0.1:8000` (was `http://localhost:8000`); the owner's `.env`
  sets `COLLECTOR_HOST`, which still wins.

## Rollback (no git)

- `evidence/spec04-tracked.patch` (111,594 bytes): cumulative tracked diff after Spec 04 (Specs 02–04).
- `evidence/spec04-new-files/`: copies of `settings/*.py`, `mcp_servers/_serve.py`, `tests/test_settings.py`.
- Back to Spec 03: `git apply -R evidence/spec04-tracked.patch`, `git apply evidence/pre-spec04-tracked.patch`,
  delete `cji_agent/settings/`, `cji_agent/mcp_servers/_serve.py`, `cji_agent/tests/test_settings.py`. Rewrites the
  working tree, so it needs the owner's approval.

## Validation commands

```powershell
$py = "C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
& $py -m pytest tests/test_settings.py -v -p no:cacheprovider
& $py -m pytest tests -m "not integration" -p no:cacheprovider        # only F-01 may fail
& $py -m mypy settings --strict
& $py -m ruff check settings mcp_servers/_serve.py tests/test_settings.py
& $py -m settings check                                               # exit 0 for offline demo
& $py -m settings check --role collector                              # exit 2 until secrets are set
powershell -NoProfile -ExecutionPolicy Bypass -File ..\.kiro\specs\04-configuration\evidence\scripts\gate_spec04.ps1
```

## Findings

| ID | Finding | Owner |
|---|---|---|
| F-01 | 11 obsolete tests in `test_supervisor.py` (unchanged) | Spec 09, or delete |
| F-02 | `errors` has no reducer | Spec 09 |
| F-03 | Step rates exceed 100 % | Analytics Spec |
| F-04 | The collector's own port is still chosen on the uvicorn command line and the dashboard's by Streamlit; the registry defines them for URLs and CORS, but cannot bind them. A launcher entry point for both belongs with packaging. | Spec 11 |
| F-05 | The Supabase database is live again. Spec 02 removed the startup code that seeded a `cji_live_…` key, but a key seeded earlier may still be active in its `api_keys` table. | Owner |

## Owner actions

- **Supabase `api_keys`:** check for a row whose key starts with `cji_live_` and was seeded by the old collector
  startup; set `is_active = false` if it is not yours (F-05).
- `cji_agent/.env`: `JOURNEY_NAME=onboarding` still overrides the default (open since Spec 03). Optionally rename
  `COLLECTOR_HOST`/`COLLECTOR_PORT` to `CJI_COLLECTOR_URL` to silence the two deprecation warnings.
- Before running the collector outside development: set `CJI_ADMIN_KEY` (≥ 32 random characters; the current one
  is 19) and `CJI_CORS_ORIGINS`.
