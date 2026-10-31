# Spec 04 — Typed Configuration and Service Discovery: Design

## 1. Package layout

```text
cji_agent/settings/
  __init__.py   get_settings(), load_settings(), override_settings(), require(), ConfigError, ServiceName
  model.py      Settings and its sections (frozen pydantic models)
  services.py   ServiceEndpoint, ServiceRegistry, DEFAULT_SERVICES  ← the only place with default ports
  load.py       mapping → Settings: .env merge, aliases, parsing, unknown-key warnings
  roles.py      require(settings, role): role-specific checks, all problems collected
  __main__.py   python -m settings check [--role R]
```

Imports: stdlib, pydantic, python-dotenv only (a test enforces it, as for `domain/`). No import-time I/O except
reading the environment when `get_settings()` is first called.

```python
settings = load_settings(environ=os.environ, dotenv_path=ROOT / ".env")  # explicit, testable
settings = get_settings()                  # cached process-wide instance (lazy)
with override_settings(test_settings): …   # tests; restores the previous instance
require(settings, "collector")             # raises ConfigError listing every problem
```

## 2. Settings model

| Section | Fields (env variable → default) |
|---|---|
| `app` | `env` (`CJI_ENV` → `production`), `mode` (`CJI_MODE` → `demo`), `journey_name` (`JOURNEY_NAME` → `user_onboarding`) |
| `storage` | `data_dir` (`CJI_DATA_DIR` → `cji_agent/data`), `reports_dir` (`CJI_REPORTS_DIR` → `cji_agent/reports`); derived: `events_parquet`, `duckdb_path`, `chroma_dir`, `checkpoints_db`, `uploads_dir`, `mapping_registry`, `last_run_file` |
| `database` | `url: SecretStr \| None` (`DATABASE_URL`, else `SUPABASE_DATABASE_URL` → unset; `postgres://` normalised), `source` (which variable supplied it) |
| `services` | `ServiceRegistry` (§3) |
| `llm` | `model` (`LLM_MODEL` → current), `temperature`, `max_tokens`; keys `groq_api_key`, `anthropic_api_key`, `openai_api_key` (`SecretStr \| None`); `timeout_s` (`CJI_LLM_TIMEOUT_S` → 30); `retry` = `RetryPolicy(attempts=3, min_wait_s=2, max_wait_s=10)` (`CJI_LLM_RETRY_*`) |
| `mcp` | `connect_timeout_s` (`CJI_MCP_CONNECT_TIMEOUT_S` → 5), `read_timeout_s` (`CJI_MCP_READ_TIMEOUT_S` → 300): today's `sse_client` defaults, made explicit |
| `budgets` | `max_agent_iterations` (20), `recursion_limit` (derived: 3 × iterations), `pipeline_timeout_s` (`CJI_PIPELINE_TIMEOUT_S` → 180, dashboard subprocess), `ingestion_sample_rows` (30), `ingestion_confidence_threshold` (0.80), `friction_score_threshold` (60), `realtime_window_minutes` (60), `realtime_auto_run_interval` (0) |
| `cors` | `origins: tuple[str, ...]` (`CJI_CORS_ORIGINS`) |
| `auth` | `admin_key: SecretStr \| None` (`CJI_ADMIN_KEY` → unset), `MIN_ADMIN_KEY_LENGTH = 32`, `KNOWN_DEFAULT_ADMIN_KEYS`, `dev_tracker_key = "cji_dev_localtest"` (seeded in development only, unchanged) |
| `keepalive` | `url` (`CJI_KEEPALIVE_URL` → unset = disabled), `interval_s` (300) |
| `observability` | `langchain_tracing` (bool), `langchain_api_key` (`SecretStr \| None`), `langchain_project` |

Existing variable names are kept. New ones carry the `CJI_` prefix. `Settings.describe()` returns a redacted
dict (`"set (43 chars)"` / `"unset"` for secrets) for logs and `python -m settings check`.

## 3. Service registry

| Logical name | Kind | Transport | Default port | Path | Launch module |
|---|---|---|---|---|---|
| `cji-journey-data` | mcp | sse | 8001 | `/sse` | `mcp_servers.journey_data_server` |
| `cji-friction-engine` | mcp | sse | 8002 | `/sse` | `mcp_servers.friction_engine_server` |
| `cji-insight` | mcp | sse | 8003 | `/sse` | `mcp_servers.insight_server` |
| `cji-report` | mcp | sse | 8004 | `/sse` | `mcp_servers.report_server` |
| `cji-ingestion-intelligence` | mcp | sse | 8005 | `/sse` | `mcp_servers.ingestion_intelligence_server` |
| `collector` | http | http | 8000 | `/` | `collector.api:app` (uvicorn) |
| `dashboard` | ui | http | 8501 | `/` | `dashboard.py` (streamlit) |
| `frontend` | ui | http | 3000 | `/` | — (Next.js, Spec 13; used for development CORS) |

- `ServiceName` is a `Literal` of these names; `registry.get(name)` on an unknown name raises `ConfigError` listing
  the known names.
- Host: `CJI_SERVICE_HOST` → `127.0.0.1` (loopback, as today). Per-service `CJI_<SERVICE>_PORT`, or
  `CJI_<SERVICE>_URL` for a service elsewhere (e.g. `CJI_REPORT_URL`). `<SERVICE>` is the logical name without
  `cji-`, upper-cased, `-` → `_`.
- `CJI_COLLECTOR_URL` is the collector's public URL (state `collector_url`, snippet generator). Legacy
  `COLLECTOR_HOST` + `COLLECTOR_PORT` still work and log a deprecation warning (OD-28).
- Registry checks: ports in 1–65535 and unique per host; URL scheme http/https with a host; transport known.
- Every MCP server entry point becomes `serve(mcp, "cji-report")`: it runs `require(…, "mcp:cji-report")`, then
  `mcp.run(transport=endpoint.transport, host=endpoint.host, port=endpoint.port)`.
- `tools/mcp_client.py` resolves the URL **at call time** from `get_settings()` (so overrides apply) and passes
  the MCP timeouts to `sse_client`. `SERVER_URLS` stays as a read-only compatibility view built from the registry.
- `run_servers.py` launches `registry.mcp_services()` in registry order.

## 4. Behaviour per environment

| Aspect | development | test | production (default) |
|---|---|---|---|
| `.env` | loaded if present | **never** | loaded if present |
| Process env over `.env` | yes | n/a | yes |
| CORS default | registry `dashboard` + `frontend` local origins | none; collector requires a list | none; collector requires a list |
| `*` in CORS | rejected | rejected | rejected |
| Admin key | optional; if unset the admin endpoint stays disabled | collector requires ≥ 32 chars, not a known default (Spec 02 rule: only `development` relaxes it) | collector requires ≥ 32 chars, not a known default |
| Dev tracker key seeded | yes | no | no |
| `DATABASE_URL` / `SUPABASE_DATABASE_URL` | required by `collector`; by `cli`, `dashboard`, `mcp:cji-journey-data` in realtime | same; the demo-data generator never uploads | same |
| Non-loopback `http://` endpoint | allowed | allowed | error, except loopback MCP services |
| Unknown `CJI_*` variable | warning | **error** (catches typos in tests) | warning |
| Storage default | `cji_agent/data`, `cji_agent/reports` | same unless injected (fixture uses `tmp_path`) | same |

`CJI_MODE=demo` needs neither a database nor LLM keys in any environment (CF-10). Without keys the existing
fallback insights and narrative are used, as today.

## 5. Validation rules and messages

Load stage (types and forms) runs in `load_settings`; role stage runs in `require`. Both collect all problems.

| Rule | Stage | Example message (one numbered line in the `ConfigError`) |
|---|---|---|
| Unknown `CJI_ENV` / `CJI_MODE` | load | `CJI_MODE='relatime' is not valid. Use 'demo' or 'realtime'.` |
| Non-integer or out-of-range number | load | `CJI_MCP_READ_TIMEOUT_S='5m' must be a number of seconds > 0, e.g. 300.` |
| Port out of range / duplicate | load | `CJI_REPORT_PORT=8003 is already used by cji-insight. Choose a free port.` |
| Malformed URL | load | `CJI_REPORT_URL='localhost:8004' needs a scheme and host, e.g. http://127.0.0.1:8004/sse.` |
| CORS entry not an origin | load | `CJI_CORS_ORIGINS entry 'https://app.example.com/path' must be scheme://host[:port] with no path.` |
| `*` in CORS | load | `CJI_CORS_ORIGINS must list origins explicitly; '*' is not allowed.` |
| `DATABASE_URL` not a PostgreSQL URL | load | `DATABASE_URL must start with postgresql:// (value not shown). Percent-encode special characters in the password.` |
| Admin key missing/short/default (production collector) | role | `CJI_ADMIN_KEY must be a random value of at least 32 characters. Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| CORS empty (production collector) | role | `CJI_CORS_ORIGINS is empty. List the browser origins allowed to call the collector, e.g. https://app.example.com.` |
| `DATABASE_URL` missing (collector, dashboard, realtime CLI) | role | `DATABASE_URL is not set. The collector stores events in PostgreSQL: postgresql://USER:PASSWORD@HOST:5432/DB.` |
| Plain-http public endpoint (production) | role | `CJI_COLLECTOR_URL must use https in production.` |
| Unknown service name | call | `Unknown service 'cji-reports'. Known: cji-friction-engine, cji-ingestion-intelligence, …` |
| Unknown `CJI_*` key | load | warning, or error in test: `CJI_CORS_ORIGIN is not a known setting. Did you mean CJI_CORS_ORIGINS?` |

The error header names the role and environment and ends with
`Run: python -m settings check --role <role>`. Secret values never appear; tests assert this with sentinel values.
`ConfigError` subclasses `RuntimeError`, so Spec 02's collector tests (`pytest.raises(RuntimeError, match=…)`) keep
passing; `validate_collector_settings` becomes a thin wrapper over `require(…, "collector")`.

## 6. Caller migration

**Migrated in this Spec (production paths):**

| File | Change |
|---|---|
| `config.py` | Facade: `SETTINGS = get_settings()`; every current constant re-exported from it (same names and types; `DATABASE_URL`/`CJI_ADMIN_KEY` become `""` when unset). Calls `ensure_storage()` to keep today's directories-on-import behaviour until the last caller migrates. Header rule updated: imports stdlib, python-dotenv and `settings/`. |
| `tools/mcp_client.py` | Registry lookup at call time; MCP timeouts; `ping_all_servers` iterates `registry.mcp_services()` |
| `run_servers.py` | Launch list from the registry; `require(…, "launcher")` before spawning; exit 2 on `ConfigError` |
| 5 × `mcp_servers/*_server.py` | `serve(mcp, "<name>")` replaces `mcp.run(transport="sse", port=…)`; insight/report read Groq key, model and timeout from settings; report call gets a timeout |
| `mcp_servers/ingestion_intelligence_server.py` | LLM keys and timeout from settings; database resolved only on the realtime write path |
| `guardrails/rate_limiter.py` | Retry policy from `settings.llm.retry` |
| `collector/api.py` | CORS, admin key, DB URL, dev key from settings; startup calls `require(…, "collector")`; engine created without requiring a URL at import (tests still patch `api.engine`); keep-alive only when `CJI_KEEPALIVE_URL` is set |
| `main.py` | `require(…, "cli")` after `--mode` is applied; `recursion_limit` and `collector_url` from settings; exit 2 on `ConfigError` |
| `dashboard.py` | Database URL and paths from settings; `sys.executable` instead of the hard-coded `.venv\Scripts\python.exe`; pipeline timeout from settings; `require(…, "dashboard")` |
| `tracker/snippet_generator.py` | `--host` default from `CJI_COLLECTOR_URL` |
| `tools/synthetic_data.py`, `tools/ingest_json.py` | Database upload only when `DATABASE_URL` is set; otherwise one log line (no attempt against a placeholder host) |
| `tests/conftest.py` | `CJI_ENV=test` by default; fixture `cji_settings(tmp_path)` with temporary storage and `override_settings` |
| `.env.example` | Every variable, grouped, with defaults and the environments that require it |
| `mcp_servers/_serve.py` (new) | `serve(mcp, name)`: role check, name check, `ensure_storage()`, `mcp.run(transport, host, port)` from the registry |

**Left on the facade (no behaviour change; later Specs):** `graph.py`, `agents/*`, `journey_data_server.py` path
constants, `guardrails/output_validator.py` (journey config): Specs 05/09. Browser endpoints in `tracker/tracker.js`
and `snippets/*`: Specs 07/13. Legacy scripts: Spec 06.

## 7. Tests (`tests/test_settings.py`, plus additions to existing files)

- **Load:** defaults from an empty mapping; each variable parsed; legacy aliases with warnings; `postgres://`
  normalisation; `.env` merged under process env; `.env` ignored in `test`.
- **Invalid and missing:** one parametrised case per rule in §5; each asserts the variable name, the fix hint, the
  collected count (several problems → one error) and the absence of sentinel secret values.
- **Environments × roles:** matrix over `development`, `test`, `production` × `cli` (demo, realtime), `launcher`,
  `mcp:*`, `collector`, `dashboard`, with an empty environment and with a complete one; offline demo passes with
  an empty environment (CF-10).
- **Registry:** unique ports; per-service port/URL overrides; unknown name error; `mcp_client` uses an injected
  endpoint inside `override_settings`.
- **Startup paths:** `run_servers` launch list equals `registry.mcp_services()` (subprocess spawning patched);
  each MCP module's `serve` call receives its registry name (AST check + patched `mcp.run` records the port);
  `ping_all_servers` covers every service in graph routes; collector startup with a fake engine passes in
  development and fails with a full `ConfigError` in production; dashboard resolution via the role check.
- **Port scan (acceptance 1):** production modules — `main.py`, `run_servers.py`, `graph.py`, `dashboard.py`,
  `config.py`, `agents/`, `collector/`, `mcp_servers/`, `tools/`, `guardrails/`, `tracker/snippet_generator.py` —
  contain no `80\d\d`, `8501`, `3000` port literals and no `transport="sse"`; only `settings/services.py` does.
  Exceptions by name: `tracker/tracker.js`, `snippets/*`, Spec 06 legacy scripts.
- **Isolation:** `settings/` imports only stdlib, pydantic, python-dotenv; importing it performs no file I/O.
- **CLI:** `python -m settings check` exits 0 for offline demo, 2 for a broken production collector, and redacts
  secrets.

## 8. Conflicts with existing documents (recorded, not rewritten)

| Document | Statement | This Spec |
|---|---|---|
| `config.py` header | "Imports ONLY stdlib + python-dotenv" | Facade also imports `settings/` (pure package); header updated |
| `config.py` header | "Creates data/ and reports/ directories on import" | Kept through the facade for now; new code calls `ensure_storage()` |
| Project_Memory (D-16) | URL components encoded with `quote_plus` in `config.py` | Not done and not adopted: the full URL is supplied; error text tells users to percent-encode |
| `docs/11-Environment-and-DevOps.md`, README env tables | Older variable lists, DuckDB realtime, LiteLLM | `.env.example` becomes the reference; docs updated in Spec 06 |
| Docs (D-08) | stdio subprocess per call | SSE persistent servers recorded as the decided transport (OD-2) |
| `pytest.ini` marker text | "running collector on port 8000" | Text only; unchanged |

## 9. Risks

| Risk | Mitigation |
|---|---|
| Removing the `DATABASE_URL` default changes failures from "connection refused" to "not configured" | Intended; demo paths never need it (CF-10 tests); messages say what to set |
| `CJI_ENV=test` in `conftest.py` changes Spec 02 tests that relied on the production default | Those tests pass the environment explicitly; T1 runs the suite first to find any that do not |
| Unknown-key errors in `test` break tests that set unrelated `CJI_*` variables | The known-key list includes every variable read anywhere; the scan test keeps it complete |
| Import order (`main.py` sets `CJI_MODE` before importing `config`) | `get_settings()` is lazy; the facade reads it on first import, which still happens after `--mode` is applied |
| Report LLM call now times out at 30 s | Same bound as the insight call; demo/offline unaffected (fallback path) |
| Facade hides incomplete migration | §6 lists every remaining caller with its owning Spec |

## 10. Rollback

`evidence/pre-spec04-tracked.patch` before T1; `evidence/spec04-tracked.patch` and copies of new files after the
gate. Reverting to Spec 03: `git apply -R spec04-tracked.patch`, `git apply pre-spec04-tracked.patch`, delete
`cji_agent/settings/` and `tests/test_settings.py`. Owner approval required (rewrites the working tree).
