# Spec 04 — Typed Configuration and Service Discovery: Requirements

**Source:** `kiro_upgrade_prompts.md` Prompt 3. **Findings addressed:** `refactoring.md` R-08 (duplicated
topology), the configuration part of R-12 (timeouts, retries), the remaining part of R-03 (secret defaults),
baseline drift D-08 (OD-2 transport), D-16 (`quote_plus` claim), D-25 (`.env.example` gaps).
**Branch:** `phase-02-security` (no commits; patch files are the rollback points, as in Specs 02–03).
**Approved:** owner, 2026-10-28 ("implement spec 04"), with OD-26 revised; all other decisions as proposed.

## 1. Current state (surveyed 2026-10-27, after Spec 03)

| Concern | Where it is defined today | Problem |
|---|---|---|
| Application environment and mode | `config.py`: `CJI_ENV` (default `production`), `CJI_MODE` (`assert`) | No `test` environment; an invalid mode raises a bare `AssertionError` at import |
| MCP endpoints | `tools/mcp_client.py` `SERVER_URLS` (5 literal URLs) | Second copy of every port |
| MCP listen ports | `mcp.run(transport="sse", port=800x)` in each of the 5 servers | Third copy; transport repeated 5 times |
| Server launch list | `run_servers.py` `SERVERS` (5 module names) | Not linked to the endpoint map |
| Collector | `COLLECTOR_HOST` + `COLLECTOR_PORT` (URL only); uvicorn takes its own `--port` | Two sources for one port |
| Local UI ports | `config._DEV_CORS_ORIGINS` (3000, 8501), Streamlit default 8501 | Fourth place with ports |
| Database | `DATABASE_URL` default `postgresql://postgres:password@localhost:5432/cji`; `dashboard.py` also reads `SUPABASE_DATABASE_URL` | Default contains a well-known credential; two variable names |
| Storage paths | `config.py` constants under `cji_agent/data`, `cji_agent/reports`; `dashboard.py` recomputes them | Not injectable; directories created on import |
| LLM settings | `config.py` (`LLM_MODEL`, temperature, max tokens, keys); `insight_server.py` and `report_server.py` read `GROQ_API_KEY` with `os.getenv` | Keys read in three ways |
| Timeouts and retries | 30 s literals in insight and ingestion servers; **no timeout** on the report server's Groq call; `rate_limiter.py` 3 attempts, 2–10 s; dashboard subprocess 180 s; MCP client none (library defaults) | Unbounded report call; values scattered |
| Budgets | `MAX_AGENT_ITERATIONS` 20, LangGraph `recursion_limit` = 3 × that (`main.py`, twice); ingestion LLM `max_tokens` 1500 literal vs `LLM_MAX_TOKENS` 2048 | Partly configurable |
| CORS | `CJI_CORS_ORIGINS` (Spec 02) | Origins not validated for form |
| Authentication | `CJI_ADMIN_KEY` default `change-me-in-production` (rejected at use since Spec 02); dev tracker key `cji_dev_localtest` literal | A known secret is still the code default |
| Outbound keep-alive | `collector/api.py` pings a hard-coded Render URL every 5 min | The Render collector is not live (owner, 2026-10-27) |
| Validation | Collector only (`validate_collector_settings`, Spec 02); everything else reads values lazily | Misconfiguration is found when a call fails |

Startup paths: `main.py` (`--run`, `--resume`, `--generate-data`, `--ingest`), `run_servers.py` → 5 MCP server
modules, the collector (`uvicorn collector.api:app`), `streamlit run dashboard.py`.

## 2. Decisions (defaults; confirm or change before implementation)

| ID | Question | Default | Alternatives considered |
|---|---|---|---|
| OD-22 | Settings mechanism | **pydantic models + an explicit loader** that reads a mapping (process env merged over `.env`). No new dependency. | `pydantic-settings`: idiomatic, but a new dependency, and its implicit env reading makes injection less direct. Hand-written dataclasses: no field validation. |
| OD-23 | Where it lives | New pure package `cji_agent/settings/` (stdlib, pydantic, python-dotenv). `config.py` becomes a **compatibility facade** that re-exports the old constants from the loaded settings. | Rewrite every caller at once (not incremental; contradicts the Prompt). |
| OD-24 | Environments | `CJI_ENV ∈ {development, test, production}`, default **`production`** (keeps Spec 02's fail-closed rule). `CJI_MODE ∈ {demo, realtime}` stays orthogonal. | Default `development`: friendlier locally but fails open. |
| OD-25 | `.env` loading | Loaded in development and production when present; process environment wins (unchanged). **Never loaded in `test`.** | Load nowhere in production: safer, but breaks hosts that rely on `.env` today. |
| OD-2 | Internal MCP transport (open since Spec 01) | **Keep SSE** in this Spec; the registry stores the transport per service, so a later change is one place. | Move to Streamable HTTP now: the newer MCP transport, but it changes client and server code and is not a configuration task. |
| OD-26 | Database URL | **Revised by the owner (2026-10-28): keep `SUPABASE_DATABASE_URL`; the Supabase database is live again.** `DATABASE_URL` is primary; `SUPABASE_DATABASE_URL` is used when `DATABASE_URL` is unset, for every caller (previously only the dashboard). Neither has a default. Both set to different values → warning naming both (values never shown). `postgres://` is normalised to `postgresql://`. | Drop the alias (the original default; rejected by the owner). |
| OD-27 | Render keep-alive | Disabled unless `CJI_KEEPALIVE_URL` is set. | Keep the hard-coded URL: it pings a service that is not live. |
| OD-28 | Legacy variable names | `COLLECTOR_HOST`/`COLLECTOR_PORT` still accepted, with a deprecation warning naming the replacement. | Hard rename: breaks the owner's current `.env`. |

## 3. Requirements

| ID | Requirement | Intended behaviour change |
|---|---|---|
| CF-01 | One typed `Settings` object SHALL hold application environment and mode, journey name, storage paths, database, LLM provider settings, timeouts, retry policies, budgets, CORS, authentication and observability. It is immutable after loading and can be built from an explicit mapping. | — |
| CF-02 | One typed `ServiceRegistry` SHALL define every logical service (5 MCP services, collector, dashboard, frontend): name, kind, transport, host, port, path, full URL, launch module and timeouts. Default ports appear **only** in the registry module. Callers use logical names. | — |
| CF-03 | The MCP client, the server launcher and each MCP server SHALL resolve endpoints, ports and transport from the registry. `run_servers.py` starts exactly the registry's MCP services. | Port and transport literals removed from 7 files |
| CF-04 | Endpoints SHALL be overridable per service (`CJI_<SERVICE>_PORT`, or `CJI_<SERVICE>_URL` for a remote service), and the bind/connect host via `CJI_SERVICE_HOST`. Duplicate ports, out-of-range ports and malformed URLs are configuration errors. | New variables |
| CF-05 | Behaviour SHALL be explicit per environment (development, test, production), as tabulated in design §4. | `test` environment is new |
| CF-06 | No setting SHALL default to a secret or a credential-bearing value. `CJI_ADMIN_KEY`, the LLM keys, `LANGCHAIN_API_KEY` and `DATABASE_URL` default to unset; secrets are held as `SecretStr` and never printed or included in error messages. | `CJI_ADMIN_KEY` and `DATABASE_URL` lose their placeholder defaults |
| CF-07 | Configuration SHALL be validated in two stages: **types and forms at load** (every entry point, including import of the `config` facade), and **role requirements at startup** (`require(role)`: `cli`, `launcher`, `mcp:<service>`, `collector`, `dashboard`), so a role checks only what it needs. | An invalid value fails at startup instead of at first use |
| CF-08 | Configuration errors SHALL be collected, not stopped at the first: one `ConfigError` (a `RuntimeError`) lists every problem with the variable name, what is wrong, and how to fix it. CLI entry points exit with code 2. Unknown `CJI_*` variables produce a warning with the closest known name. | Clearer failures; exit code 2 for configuration errors |
| CF-09 | Tests SHALL be able to build settings from a mapping, override the active settings within a context, inject an endpoint for one service, and point all storage at a temporary directory, with no `.env` read and no import-time side effects. Directories are created by `ensure_storage()` at startup, not on import. | `import config` no longer creates directories by itself (the facade calls `ensure_storage()` for compatibility until callers migrate; see design §6) |
| CF-10 | Offline demo mode SHALL work with no LLM key, no `DATABASE_URL` and no network beyond loopback: `cli` (demo), `launcher` and `mcp:*` roles must pass with an empty environment. | — |
| CF-11 | LLM and MCP timeouts and retry policies SHALL come from settings. The report server's Groq call gets the LLM timeout. MCP client timeouts default to the current library values. | Report LLM call bounded at 30 s (was unbounded) |
| CF-12 | Callers SHALL migrate incrementally: the `config` facade keeps every current name working; this Spec migrates the production paths listed in design §6; the rest are listed with their owning Spec. | — |
| CF-13 | `python -m settings check [--role R]` SHALL print the resolved, redacted configuration and any errors, exiting 0 or 2. | New diagnostic command |
| CF-14 | `.env.example` SHALL list every supported variable with its default and the environments that require it (closes D-25). | — |

## 4. Non-goals

- Changing the MCP transport (OD-2 keeps SSE). Recorded for a later Spec; the registry makes it a local change.
- Provider strategy, model allow-lists, token/cost **enforcement**, correlation IDs and telemetry: Spec 08 (R-12).
  This Spec only centralises the values that already exist.
- Packaging and import paths (`sys.path` hacks, `pyproject.toml`): Spec 11 (R-14).
- Browser-side endpoints: `tracker/tracker.js` default URL and the generated `snippets/*` (they cannot read server
  settings): Specs 07/13. Listed as exceptions in the port scan.
- Legacy scripts (`test_pg.py`, `test_metadata_query.py`, `generate_diverse.py`, `dashboard2.py`): Spec 06 inventory.
- Rewriting documents (`README.md`, `docs/11-Environment-and-DevOps.md`, Project_Memory). Conflicts are recorded in
  design §8; only `.env.example` and `config.py`'s own header are updated.

## 5. Acceptance criteria (Prompt 3)

1. **No duplicated service ports in changed production paths.** A test scans the production modules (design §7)
   for port literals and transport strings and finds them only in `settings/services.py`; the browser and legacy
   exceptions are listed by name.
2. **Missing and invalid configuration tests pass**: every rule in design §5 has a test that asserts the variable
   name and fix text appear in the error and that no secret value does.
3. **Development, test and production are covered**: a parametrised test runs each role against each environment
   and checks the table in design §4.
4. **All startup paths resolve required services**: tests prove `run_servers.py` launches exactly the registry's MCP
   services, each MCP server listens on its registry port, `ping_all_servers` checks every service the graph uses,
   the collector startup validates through `require("collector")`, and the dashboard resolves its database and paths.
   Smoke runs (launcher, demo pipeline, ingest probe) give the Spec 03 results.
5. Regression: golden journey-data snapshot identical to Spec 03; full suite has no failures beyond F-01; mypy/ruff
   no worse on changed files; `settings/` is mypy `--strict` clean and imports only stdlib, pydantic, python-dotenv.
