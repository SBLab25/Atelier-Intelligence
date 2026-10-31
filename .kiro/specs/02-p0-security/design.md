# Spec 02 — P0 Correctness and Security: Design

Companion to `requirements.md`. Each fix is the smallest complete change. No new abstractions;
those belong to Specs 04 and 05.

## 1. Approach per finding

### R-01 Ingestion worker (RS-01, RS-01b)
- Make `ingestion_worker` `async def` and call `mcp_session("cji-ingestion-intelligence")` +
  `call_tool(session, "detect_schema" | "ingest_to_store", …)`, the same pattern as `workers.py:43-58`.
  The graph already runs through `astream` (`main.py:217`), so an async node is supported.
- Delete `_call_tool`, `INGESTION_MCP_URL`, the `requests` import and the unused `json`/`COLLECTOR_URL` imports.
- Open one session per file so a dropped connection affects only that file.
- Return `"ingestion_pending_files": []` on every path. `state.py:137` has no reducer, so this overwrites.
  `route()` (`supervisor.py:83`) is unchanged; it stops matching because the list is empty.

### R-02 Demo health check (RS-02)
- In `get_system_info`, branch before any query: demo checks the Parquet exists and runs `SELECT 1`
  on `get_demo_conn()`; realtime keeps `execute_query`. The returned dict keeps the same keys.

### R-03 Collector security (RS-03a–d)
- `config.py` gains three constants (stdlib only, per its own rule): `CJI_ENV` (default `production`),
  `CJI_CORS_ORIGINS` (list parsed from comma-separated text) and `KNOWN_DEFAULT_ADMIN_KEYS`.
  Nothing validates on import, so the CLI and MCP servers behave as before.
- `collector/api.py`:
  - `validate_collector_settings(env, admin_key, origins) -> None` raises `RuntimeError` naming the
    variable to set. Called first in `startup_event`, before `_create_tables`.
  - CORS: `allow_origins=CJI_CORS_ORIGINS`, `allow_credentials=False`, methods `GET, POST, OPTIONS`,
    headers `Content-Type, X-CJI-Key, X-CJI-Admin-Key`.
  - Admin endpoint: `admin_key_usable()` check, then `secrets.compare_digest`.
  - `_create_tables`: drop the live-key insert; dev-key insert only when `CJI_ENV == "development"`.
- `.env.example`: add `CJI_ENV=development` and `CJI_CORS_ORIGINS=http://localhost:3000,http://localhost:8501`,
  and say the admin key must be ≥ 32 random characters outside development.

### R-04 SQL binding (RS-04a–d)
- `execute_demo_query(sql, params: list | None)` → `conn.execute(sql, params)`.
- `execute_query(sql, params: dict | None)` → `conn.execute(text(sql), params)`. The `?` text
  substitution is removed. The `json_extract_string` rewrite stays (fixed text, no values).
- Demo queries: `journey_id = ?`, `step_id = ?`, `event_type = ?`, `LIMIT ?`. The step-order `CASE`
  becomes `CASE step_id WHEN ? THEN 0 …` with the step names as parameters.
- Realtime queries: `:journey_id`, `:step_id`, `:event_type`, `:limit`, and the time filter
  `timestamp >= NOW() - (:window * INTERVAL '1 minute')`.
- Parquet view: the path is config-derived; escape `'` as `''`. DuckDB does not accept parameters
  in `CREATE VIEW`.
- Collector `live_stats`: `minutes: int = Query(60, ge=1, le=43200)`, bound as `:minutes`.
- `get_from_clause` is unchanged; it selects among fixed strings.

### R-05 Report escaping (RS-05a–b)
- Local helpers in `report_server.py`: `_h(value) = html.escape(str(value), quote=True)` and
  `_js(obj) = json.dumps(obj)` with `<`, `>`, `&`, U+2028 and U+2029 replaced by `\u` escapes.
- Apply `_h` to the title, journey name, mode label, narrative, and every insight field.
  `mode` goes through `{"demo", "realtime"}` → else `"unknown"`.
- Chart `labels` and `data` use `_js`. CSS, layout and the CDN tag are unchanged (Spec 10).

### U-2, U-4, U-5
- U-2: replace the key with `YOUR_TRACKER_API_KEY` in the four snippet files and with
  `cji_live_<redacted>` in `docs/6-API-Contracts.md` (two lines). No other doc edits.
- U-4: `VALID_WORKERS = frozenset({"ingestion_worker", "data_worker", "friction_worker",
  "insight_worker", "report_worker", "__end__"})` in `supervisor.py`. Update the one stale expectation
  in `test_supervisor.py:291-293` with a comment noting v2 added `ingestion_worker`. Add a test tying
  `VALID_WORKERS` to `graph.py`'s conditional edge map.
- U-5: `collector/api.py:13` → `from config import DATABASE_URL, CJI_ADMIN_KEY, ROOT`;
  `requirements.txt`: `SQLAlchemy>=2.0.0,<2.1`. Then re-run pip-audit for the resolved 2.0.x.
  If 2.0.x has advisories, switch to adding `psycopg[binary]` instead and record why.

## 2. Affected files

| File | Change |
|---|---|
| `cji_agent/agents/ingestion_worker.py` | R-01 |
| `cji_agent/mcp_servers/journey_data_server.py` | R-02, R-04 |
| `cji_agent/collector/api.py` | R-03, R-04 (`live_stats`), U-5 import |
| `cji_agent/config.py` | 3 new constants (R-03) |
| `cji_agent/mcp_servers/report_server.py` | R-05 |
| `cji_agent/agents/supervisor.py` | U-4 constant |
| `cji_agent/requirements.txt` | U-5 cap |
| `cji_agent/.env.example` | 2 new variables + admin key note |
| `cji_agent/snippets/{api_key.json,embed_snippet.html,useCJITracker.js,verify_tracker.py}`, `docs/6-API-Contracts.md` | U-2 placeholders |
| `cji_agent/tests/test_supervisor.py` | U-4 expectation |
| `cji_agent/tests/test_p0_security.py` (new) | All regression tests |

Nothing else may change. `git diff --stat` is checked against this table at the gate.

## 3. Tests (new file `tests/test_p0_security.py`, offline, no database)

| Area | Test |
|---|---|
| R-01 | Fake `mcp_session`/`call_tool` record the server name and tool names; assert `cji-ingestion-intelligence`, `detect_schema`, `ingest_to_store`. Source check: no `localhost`, `127.0.0.1`, `:800` or `requests` in the worker. Failure path: `call_tool` raises → error recorded, `ingestion_pending_files == []`, `route()` on the merged state ≠ `ingestion_worker`. |
| R-02 | Patch `get_pg_engine` to raise; demo `get_system_info` → `status == "ok"`. Missing Parquet → existing error text. |
| R-03 | `validate_collector_settings`: development passes with defaults; production fails for unset, default and short keys and for empty origins; production passes with a 40-character key and an origin. `TestClient(app)` (no lifespan, so no database): preflight from a non-listed origin gets no `Access-Control-Allow-Origin`; no response carries `Access-Control-Allow-Credentials: true`; admin endpoint returns 403 with the default key; `_create_tables` against a fake connection inserts no `cji_live_` row (and no dev row outside development). |
| R-04 | Demo: `query_events(step_id="x' OR '1'='1")` returns 0 events (baseline returns all). A journey name containing `'` runs without SQL error. Realtime: a fake engine captures `(sql, params)`; assert no test value appears in the SQL text and all appear in `params`. `live_stats` with `minutes=0` and `minutes=10**9` returns 422. |
| R-04d | Golden snapshot captured from **unchanged** code (T0) and compared after T5. |
| R-05 | Insight fields, narrative and journey name set to `<script>alert(1)</script>`, `"><img src=x onerror=alert(1)>`, `</script><script>`, quotes, backslashes and Unicode. Assert the raw payloads are absent, escaped forms are present, the `labels` JSON contains `\u003c/script`, and the CSS class is `unknown` for a bad mode. `REPORTS_DIR` points at `tmp_path`. |
| U-4 | Every `route()` return over a state matrix ∈ `VALID_WORKERS`; `VALID_WORKERS` == keys of `graph.py`'s conditional edges. |
| U-5 | `importlib.import_module("collector.api")` succeeds with `cji_agent` on `sys.path`. |

## 4. Security and data-integrity risks

| Risk | Mitigation |
|---|---|
| `CJI_ENV` defaulting to `production` stops local collector starts | Intended (fail closed). `.env.example` sets `development`; the startup message names the fix. |
| Bound parameters change numeric results or types | Golden snapshot (RS-04d), plus the demo pipeline still reports 8 metrics and 4 critical steps. |
| DuckDB parameter limits (`LIMIT ?`, `CASE WHEN ?`) | Verified by the golden test. If unsupported, use `int()` for `LIMIT` and record it. |
| Async ingestion worker changes graph behaviour | Graph-compile test plus the `--ingest` smoke run (acceptance 6). |
| `SQLAlchemy<2.1` reintroduces advisories | pip-audit after the change (T1); fall back to `psycopg[binary]`. |
| Snippet placeholder breaks a copied embed | Snippets are generated by `snippet_generator.py`; the placeholder is explicit. |
| Retired key still in git history | Out of scope; Spec 15. The key is not accepted anywhere after RS-03d, and neither the collector nor Supabase is live. |

## 5. Rollback and compatibility

- One commit per task on `phase-02-security`; revert per commit. No migrations, no data changes.
  Rows already seeded in any database stay untouched.
- CLI flags, MCP tool names and signatures, response shapes, routing order, scoring and the event
  taxonomy are unchanged. Streamlit is untouched.
- Collector compatibility break (intended): outside development it needs `CJI_ADMIN_KEY` and
  `CJI_CORS_ORIGINS`.
