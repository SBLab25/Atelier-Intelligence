# Spec 02 — P0 Correctness and Security: Requirements

| | |
|---|---|
| Spec | **02 P0 Security** (`kiro_upgrade_guide.md` §7) = **Prompt 1** (`kiro_upgrade_prompts.md`) |
| Scope | `refactoring.md` findings **R-01 to R-05**, plus three baseline items assigned here (U-2, U-4, U-5) |
| Branch | `phase-02-security`, from `phase-01-baseline` (= `main` @ `8523e47`). **Not created yet.** |
| Baseline | `.kiro/specs/01-baseline/` (B register in its design §4) |
| Status | **Draft, awaiting owner review.** No code changed. |

## 1. Defaults applied (owner said "proceed"; change any of these before implementation)

| Decision | Default used |
|---|---|
| OD-14 branch names | One branch per Spec: `phase-02-security`, `phase-03-contracts`, … |
| OD-15 baseline marker | Record `8523e47` only; no tag |
| OD-18 old `cji_agent/.venv` | Leave untouched; validate with `C:\Users\sovan\.venvs\cji-baseline-312` |
| OD-19 unassigned items | U-2, U-4 and U-5 go in this Spec; U-1, U-3, U-6 stay unassigned |

## 2. Current behaviour (verified at baseline)

| ID | Current behaviour | Evidence |
|---|---|---|
| R-01 | `agents/ingestion_worker.py:27` posts to `http://localhost:8004/tools/<name>` (the report server, plain HTTP). The ingestion server is MCP-over-SSE on 8005. Every `--ingest` fails with a 404 and the CLI exits 0. A failed file stays in `ingestion_pending_files`, and the supervisor routes back to ingestion until the 20-iteration cap. | B-04, `c4b-ingest-probe.log` |
| R-02 | `journey_data_server.py:94` `get_system_info` runs `execute_query("SELECT 1")` against PostgreSQL in every mode. In demo mode it reports an error unless a database is reachable. | code |
| R-03 | `collector/api.py:19-25` sets `allow_origins=["*"]` with `allow_credentials=True`. `config.py:66` defaults `CJI_ADMIN_KEY` to `change-me-in-production`, compared with `!=` (`api.py:216`). `_create_tables` seeds `cji_dev_localtest` and a fixed `cji_live_…` key on every start (`api.py:58-70`). | code |
| R-04 | `journey_data_server.py` interpolates `journey_id`, `step_id`, `event_type`, the window, step names, `limit` and the Parquet path into SQL (bandit B608 at lines 20, 56, 129, 170, 217, 257, 299, 323, 349). `execute_query` (lines 65-79) substitutes `?` with quoted text. `collector/api.py:204` interpolates `minutes`. | code, bandit |
| R-05 | `report_server.py:90-185` puts `journey_name`, `mode` (also used as a CSS class), `narrative`, step IDs, titles, root causes and fixes into HTML unescaped. `json.dumps` output goes inside `<script>` without escaping `</script>`. | code; **XSS not demonstrated yet** (T8 proves it first) |
| U-2 | The retired `cji_live_…` key is in `snippets/api_key.json:2`, `embed_snippet.html:4`, `useCJITracker.js:7`, `verify_tracker.py:7`, `docs/6-API-Contracts.md:256,1127`. | grep |
| U-4 | `tests/test_supervisor.py:30` imports `VALID_WORKERS`, which `agents/supervisor.py` doesn't define, so 41 routing tests never run. The test expects the 4 analysis workers plus `__end__`; `route()` can also return `ingestion_worker`. | B-01 |
| U-5 | `collector/api.py:13` imports `cji_agent.config` (all other modules use `from config import`), so the documented `uvicorn collector.api:app` fails. `SQLAlchemy>=2.0.0` resolves to 2.1.6, whose default `postgresql://` driver is `psycopg`; only `psycopg2-binary` is declared. | B-06 |

## 3. Requirements and intended behaviour

Normative: **SHALL** is mandatory. Each requirement lists the only behaviour change it allows.

| ID | Requirement | Intended behaviour change |
|---|---|---|
| RS-01 | The ingestion worker SHALL call the ingestion service through `tools.mcp_client.mcp_session("cji-ingestion-intelligence")` and `call_tool`, like the other workers. No port or URL literal in the worker. | `--ingest` reaches the ingestion server. |
| RS-01b | The ingestion worker SHALL consume `ingestion_pending_files` (return it as `[]`) whether each file succeeds, fails or is flagged. | A failed ingest no longer loops to the iteration cap. Routing order unchanged. |
| RS-02 | In demo mode, `get_system_info` SHALL NOT touch PostgreSQL. It reports `ok` when the Parquet exists and DuckDB answers, and the existing error when the Parquet is missing. | Demo health is accurate offline. |
| RS-03a | The collector SHALL NOT combine credentials with wildcard origins. `allow_credentials=False` (the tracker uses a header key, not cookies). Origins come from a new `CJI_CORS_ORIGINS` (comma-separated). | Browser behaviour changes only for origins not listed. |
| RS-03b | A new `CJI_ENV` (`development` \| `test` \| `production`, default **`production`**) SHALL control fail-closed behaviour. At collector startup, outside explicit `development`, startup SHALL fail with an actionable message if `CJI_ADMIN_KEY` is unset, equals a known default, or is shorter than 32 characters, or if `CJI_CORS_ORIGINS` is empty. | The collector refuses to start until configured. CLI, MCP servers and dashboard are unaffected; checks run only at collector startup. |
| RS-03c | `POST /admin/api-keys` SHALL reject every request while the admin key is unset or a known default, in every environment, and SHALL compare keys with `secrets.compare_digest`. | Admin endpoint disabled until configured. |
| RS-03d | The collector SHALL NOT seed the `cji_live_…` key. It SHALL seed `cji_dev_localtest` only when `CJI_ENV=development`. | No credential is written outside development. |
| RS-04a | Every value in journey-data and collector SQL SHALL be a bound parameter (DuckDB `?` parameters; SQLAlchemy `:name`). `execute_query` SHALL take a params mapping and SHALL NOT edit SQL text. | None for valid input. |
| RS-04b | Dynamic identifiers (the `get_from_clause` table selection) SHALL come only from the existing fixed strings. The config-derived Parquet path SHALL be quote-escaped. | None. |
| RS-04c | `GET /live/stats?minutes=` SHALL bind `minutes` and validate `1 ≤ minutes ≤ 43200`. | Out-of-range values return 422 instead of running SQL. |
| RS-04d | Results for valid input SHALL be identical before and after: golden snapshot of `get_step_metrics`, `get_funnel_dropoff`, `query_events` on the tracked Parquet. | None. |
| RS-05a | `export_report` SHALL HTML-escape every text value and attribute. `mode` SHALL be allow-listed to `demo`/`realtime` (else `unknown`) before use as a CSS class. | Markup in data renders as text. |
| RS-05b | Data embedded in `<script>` SHALL be JSON encoded with `<`, `>`, `&`, U+2028 and U+2029 escaped. | `</script>` in a label cannot end the script block. |
| RS-U2 | The retired key SHALL be replaced with a placeholder in the 6 tracked locations. Git history is not rewritten here. | Snippets need a key supplied by the user. |
| RS-U4 | `agents/supervisor.py` SHALL define `VALID_WORKERS: frozenset` with all six `route()` targets. The stale test expectation SHALL be updated to include `ingestion_worker`, and a new test SHALL check that every `route()` result is in `VALID_WORKERS` and in `graph.py`'s edge map. | No runtime change; 41 tests run again. |
| RS-U5 | `collector/api.py` SHALL use `from config import …`. `requirements.txt` SHALL cap `SQLAlchemy>=2.0.0,<2.1` (keeps the psycopg2 default driver). | Collector imports with the documented command. |
| RS-T | Every finding SHALL get a regression test that fails before its fix and passes after (the guide's §9 rule). | — |

## 4. Non-goals (later Specs)

- Render keep-alive deletion, response semantics, limits, liveness/readiness split → Spec 07.
- Typed settings and service registry; `.env.example` rewrite beyond the two new variables → Spec 04.
- Repository interfaces; removing `CJI_MODE` branches → Spec 05.
- CSP, pinning or self-hosting Chart.js, report filename and path safety, size limits → Spec 10.
- LLM timeouts (B113 `report_server.py:73`), prompt-injection handling → Spec 08.
- Default `JOURNEY_NAME` mismatch (D-31) → Spec 03. Exit codes (D-36) → Spec 06.
- Dashboard SQL: its B608 sites build only `FROM` clauses from fixed strings, and values are passed as `params` (`dashboard.py:121-284`). Recorded, not changed.
- Git history rewrite for the retired key → Spec 15.

## 5. Acceptance criteria

1. The tests for all five findings and for U-2, U-4 and U-5 pass. Each failed against unchanged code first; the failing runs are kept as evidence.
2. Demo mode needs no PostgreSQL: `get_system_info` returns `ok` with the dead `DATABASE_URL`.
3. Injection, CORS, credential and report-rendering tests pass.
4. Golden journey-data snapshot identical before and after (RS-04d).
5. Demo pipeline with `JOURNEY_NAME=user_onboarding` still yields 8 step metrics, 4 critical steps and a report.
6. `--ingest` with the probe file reaches port 8005, records a structured error when the LLM is blocked, and routes on to `data_worker` without looping.
7. `python -c "import collector.api"` from `cji_agent/` succeeds.
8. Full unit suite: B-01 is gone, no new failures (any is logged as F-xx). ruff, mypy and bandit counts on changed files are no worse than baseline; bandit B608 count for `journey_data_server.py` and `collector/api.py` drops to 0 or each remaining site is justified.
9. No insecure production default remains in the changed paths. `git diff --check` is clean, and only the files listed in design §2 have changed.
