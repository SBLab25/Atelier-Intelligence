# Spec 01 — Baseline and Onboarding: Requirements

| | |
|---|---|
| Spec | **01 Baseline** (`kiro_upgrade_guide.md` §7) = **Prompt 0** (`kiro_upgrade_prompts.md`) |
| Branch | `phase-01-baseline`, created from `main` at `8523e47` (tag `v2.0`). No commits on it. |
| Date | 2026-10-27 |
| Scope | Record current behaviour and a reproducible baseline. **No runtime source file modified** (git status identical before and after every run; see `evidence/b0-*`, `c8-*`). |
| Not in scope | Any fix. Every defect here is handed to a later Spec (design §5). |

Companion files: `design.md` (current vs target, registers, roadmap) and `tasks.md`
(this Spec's tasks and gate evidence). Raw logs and scripts are in `evidence/`.

## 0. Evidence labels

| Label | Meaning |
|---|---|
| `[CODE]` | Read in source or config in this repo. |
| `[RUN]` | Observed by running a command; log in `evidence/`. |
| `[DOC]` | Stated only in a document; not confirmed against code. |
| `[UNVERIFIED]` | Not checked (needs network, credentials, a person, or an unread file). |

## 1. Inputs

| Input | Status |
|---|---|
| `project_summary.md`, `refactoring.md` | Read in full. Generated analyses; findings re-checked against code where marked in design §3. |
| `kiro_upgrade_guide.md`, `kiro_upgrade_prompts.md`, `free_plan_workflow.md` | Read in full. These define the process: one Spec per phase, Prompts 0–15. |
| `README.md`, `Project_Memory.md`, `Project_status.md` | Read in full. |
| `docs/` | `11-Environment-and-DevOps.md`, `development_status.md` read; `12-Testing-Strategy.md` searched for commands; `1`–`10` **not read**. |
| `cji_agent/` | Config, entry points, launch lines, collector, supervisor routing, generator upload block, tracker header read. Not read in full: `workers.py`, `state.py`, `guardrails/*`, bodies of `insight_server.py`, `report_server.py`, `friction_engine_server.py`, `ingestion_intelligence_server.py`, `dashboard.py`, test bodies. |

The process documents and `.kiro/` stay **outside git** (owner, 2026-10-27: "this project is
completely separate from the repo"). Stage files by name; never `git add .`.

## 2. Owner decisions recorded

| Date | Decision | Status |
|---|---|---|
| 2026-10-27 | Python: "use the best version". Chosen: CPython **3.12.x**, declared range `>=3.11,<3.13`. | **Verified by install**: fresh install on 3.12.13 succeeded (§4). |
| 2026-10-27 | Next.js frontend wanted → **Node 24 LTS**, `engines.node >=22`. | Recorded. No Node project exists yet. |
| 2026-10-27 | **PostgreSQL** is the realtime store. DuckDB stays demo-only over Parquet. | Recorded. |
| 2026-10-27 | Render collector is **not live**. | Recorded. Its keep-alive is dead code. |
| 2026-10-27 | Supabase database in `.env` is **not in use**. | Recorded. The seeded keys in it need no deactivation unless that database is reused. |
| 2026-10-27 | Process docs are **not committed**. | Recorded. |
| 2026-10-27 | Branch name `phase-01-baseline`. | Done. Later branch names are open (OD-14). |

## 3. Current startup commands (run from `cji_agent/` unless stated)

Every command ran with the protected environment in §8 (offline, dummy keys).

| Purpose | Command | Baseline result |
|---|---|---|
| Start all 5 MCP servers | `python run_servers.py [--mode demo\|realtime]` | **Works** `[RUN]`: ports 8001–8005 listening within 8 s. |
| Demo pipeline | `python main.py --mode demo --run --auto-approve` | **Exit 0 but analyses nothing** `[RUN]`: resolved `JOURNEY_NAME=onboarding`, tracked Parquet holds only `user_onboarding`. 0 step metrics; friction worker fails repeatedly; supervisor stops at its 20-iteration cap; CLI prints `[DONE] Analysis complete.` No report. (B-03) |
| Demo pipeline, journey override | `JOURNEY_NAME=user_onboarding` + same command | **Works** `[RUN]`, 49 s: 8 step metrics, 4 critical steps, 4 insights, 14 fixes ranked, 4.5 KB report in `reports/`. LLM calls were blocked, so insight and narrative text came from the fallback path. |
| Human-approval flow | `python main.py --mode demo --run` → `python main.py --approve --thread-id <id>` | Not run `[CODE]` only. |
| Ingest then analyse | `python main.py --mode demo --ingest --file <f> --source-hint "..." --run --auto-approve` | **Ingestion fails, exit 0** `[RUN]`: `404 Not Found for url: http://localhost:8004/tools/detect_schema`; "Processed 0 file(s)"; pipeline continues. (B-04, D-01) |
| Ingest only | `python main.py --mode demo --ingest --file <f>` | **Does nothing** `[RUN]`: "No action specified." exit 0. Project_status documents it as "just ingest". (B-05, D-32) |
| Generate demo data | `python main.py --mode demo --generate-data [--sessions N] [--seed N]` | **Not run on purpose**: overwrites the tracked `data/events.parquet` and runs `to_sql("demo_events", if_exists="replace")` against `DATABASE_URL` (`tools/synthetic_data.py:329-337`) `[CODE]`. |
| Collector, as documented | `uvicorn collector.api:app --port 8000` | **Fails at import** `[RUN]`: `ModuleNotFoundError: No module named 'cji_agent'` (`collector/api.py:13` imports `cji_agent.config`; every other module uses flat imports). (B-06) |
| Collector from repo root | `uvicorn cji_agent.collector.api:app --port 8000` (from `TCS-CJI/`) | **Fails at import** `[RUN]`: `No module named 'psycopg'`. SQLAlchemy 2.1.6's default `postgresql://` driver is `psycopg`, but only `psycopg2-binary` is declared. (B-06, D-34) |
| Streamlit | `streamlit run dashboard.py` | **Server starts** `[RUN]`: `/_stcore/health` = `ok` on 8501. Page code runs only per browser session, so dashboard logic is **unverified**. (B-10) |
| Tracker snippet | `python tracker/snippet_generator.py --journey <name>` | Not run. |
| Unit tests | see §5 | 127 passed, 1 module error. |

## 4. Supported runtimes and dependency installation

### 4.1 Versions

| Runtime | Decision | Evidence |
|---|---|---|
| Python | **3.12.x**, range `>=3.11,<3.13` | Baseline env: uv-managed CPython 3.12.13 `[RUN]`. Nothing in the repo declares a version `[CODE]`. System `python` is 3.15.2 (unsupported); `py -0p` also lists a uv CPython 3.11.15. The old `cji_agent/.venv` (3.12.14 from a Codex runtime cache) is **left untouched and is incomplete** (no pandas, pydantic, fastapi, langgraph). |
| Node.js | **24 LTS**, `engines.node >=22` (Next.js needs ≥ 20.9) | Installed: node 24.18.1, npm 11.16.0. No `package.json` `[CODE]`. `tracker.js` and `snippets/useCJITracker.js` pass `node --check` (syntax only) `[RUN]`. |

### 4.2 Install procedure used for the baseline (reproducible)

```powershell
git switch -c phase-01-baseline
uv python install 3.12                                    # uv 0.12.2 -> CPython 3.12.13
uv venv C:\Users\sovan\.venvs\cji-baseline-312 --python 3.12 --seed
cd cji_agent
uv pip install --python C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe `
    -r requirements.txt -r requirements-dev.txt           # 196 packages, 70 s, exit 0
uv pip freeze --python ... > evidence\constraints-baseline-2026-10-27.txt
uv pip install --python ... ruff mypy bandit pip-audit    # tools: baseline venv only
```

The venv sits **outside the repo** so no untracked files appear and the old `.venv` stays intact.
Exact resolved versions are in `evidence/constraints-baseline-2026-10-27.txt`. Notable ones:
`sqlalchemy 2.1.6`, `psycopg2-binary 2.9.13`, `langgraph 0.2.28`, `langchain-core 0.3.86`,
`fastmcp 4.1.4`, `mcp 2.3.0`, `fastapi 0.162.0`, `pydantic 2.14.1`, `pandas 3.1.0`,
`chromadb 1.5.9`, `streamlit 1.66.1`, `sentence-transformers 6.2.0` (pulls `torch 2.14.1`),
`litellm 1.106.4`, `anthropic 2.3.0`, `tenacity 9.2.1`.

### 4.3 Installation requirements and gaps

| Requirement | Detail |
|---|---|
| Network for install | PyPI (packages), GitHub (uv Python build). Expect a large download: `torch` comes in via `sentence-transformers`. |
| **Missing driver** | `requirements.txt` has `SQLAlchemy>=2.0.0` (unpinned) and `psycopg2-binary`. A fresh resolve gives SQLAlchemy 2.1.6, whose default `postgresql://` driver is `psycopg` (v3), which is not installed `[RUN]`. Every `postgresql://` path fails at `create_engine`: collector, realtime journey data, dashboard DB queries, generator upload. (D-34) |
| Undeclared | `tenacity` (imported by `guardrails/rate_limiter.py`) arrives only transitively `[CODE][RUN]`. |
| Declared, no import found | `litellm`, `anthropic`, `langchain-community`, `sentence-transformers` `[CODE]`. Together they bring most of the install weight. |
| Unpinned | Every requirement is a `>=` range or capped range. No lockfile. The baseline constraints file is the only record of a working set. |
| Caps block security fixes | `langgraph<0.3`, `langchain-core<0.4` and `langgraph-checkpoint-sqlite<2` exclude the fixed versions pip-audit reports (§5). |
| External services | Demo mode: none (verified with the journey override). Realtime: PostgreSQL plus a `psycopg` driver, not verified. Real insights and narratives: a Groq or Anthropic key, not used in the baseline. |
| Optional local tools | uv 0.12.2, Docker 29.6.2 (could host a throwaway PostgreSQL for Prompt 6), Graphify on PATH. Absent: `psql`, `pnpm`, `yarn`, Playwright. |
| Windows specifics | `dashboard.py` launches `ROOT/.venv/Scripts/python.exe` directly, so its Run button uses the old incomplete `.venv`, not the baseline venv (OD-18). |

## 5. Test, lint, type-check, and security commands

All run from `cji_agent/` with the baseline venv and protected environment. "Report-only" means
findings are recorded, not fixed.

| Check | Exact command | Exit | Result |
|---|---|---|---|
| Unit tests | `python -m pytest tests -p no:cacheprovider -m "not integration" -rfE --continue-on-collection-errors --junitxml=...` | 1 | **127 passed, 1 error, 2 deselected** in 5.4 s. The error: `tests/test_supervisor.py` cannot import `VALID_WORKERS` from `agents.supervisor` (not defined there), so none of its 41 test functions run. (B-01) |
| Integration tests | `python -m pytest tests -m integration` | 1 | 2 failed: the network is blocked by design, so both LLM providers fail. **Not a product result** (B-02). |
| Plain run (no flag) | `python -m pytest tests -p no:cacheprovider` | 2 | Stops at collection on the same import error. The README's command reports no results. |
| Lint | `python -m ruff check . --no-cache --statistics` | 1 | **266 findings**, 123 auto-fixable. No ruff config in the repo; `--isolated` gives the same 266. Top codes: BLE001 51, C408 48, F401 44, I001 36, UP017 16, UP006 12. |
| Type check | `python -m mypy . --exclude "(^\|/)\.venv/"` | 1 | **52 errors in 18 files** (45 checked). Most in `insight_server.py` 14, `dashboard.py` 7, `mcp_client.py` 5. By code: union-attr 18, import-untyped 14, assignment 7. |
| Security lint | `python -m bandit -r . -x ./.venv` | 1 | **0 high, 25 medium, 300 low** (6,997 LOC). Medium: B608 SQL string building ×22, B113 request without timeout ×2, B108 hard-coded temp path ×1. Low is mostly B101 `assert` ×270. |
| Dependency audit | `python -m pip_audit -r constraints-baseline-2026-10-27.txt --no-deps --disable-pip` | 1 | **30 advisories in 8 packages**: chromadb 1.5.9, filelock 3.32.7, langchain 0.3.30, langchain-core 0.3.86, langchain-text-splitters 0.3.11, langgraph 0.2.28, langgraph-checkpoint 1.0.12, langgraph-checkpoint-sqlite 1.0.4. |
| Python syntax | `ast.parse` over all 56 `.py` files | 0 | All parse on 3.12. Syntax only. |
| JS syntax | `node --check tracker/tracker.js`, `node --check snippets/useCJITracker.js` | 0 | Syntax only. |
| Whitespace | `git diff --check` | 0 | Clean. |
| CI | — | — | None exists (no `.github`, Makefile, pre-commit, Dockerfile). |

## 6. Entry points

| Surface | Entry point | Notes |
|---|---|---|
| CLI | `cji_agent/main.py::main()` | Flags: `--mode`, `--generate-data`, `--sessions`, `--seed`, `--ingest`, `--file`, `--source-hint`, `--run`, `--auto-approve`, `--approve`, `--thread-id`, `--window-mins`, `--window-days`. |
| Collector | `cji_agent/collector/api.py::app` | Routes `GET /health`, `GET /tracker.js`, `POST /collect/batch`, `GET /live/stats`, `POST /admin/api-keys`. Key via body `api_key` or header `X-CJI-Key`; admin via `X-CJI-Admin-Key`. **Cannot start today** (B-06). |
| MCP servers | `mcp_servers/{journey_data,friction_engine,insight,report,ingestion_intelligence}_server.py` via `run_servers.py` (`python -m mcp_servers.<name>`, `PYTHONPATH=cji_agent`) | All 5 start (§3). |
| Streamlit | `dashboard.py` (primary); `dashboard2.py` (no references) | Server starts; page logic unverified. |
| Report | `report_server.py` tool `export_report` → `reports/cji_report_{journey}_{timestamp}.html` (`report_server.py:94`) | Produced in the override run. |
| Browser tracker | `tracker/tracker.js`, served at `GET /tracker.js`; config `window.CJI_CONFIG` | Posts to `/collect/batch`. |
| Loaders / generators | `tools/synthetic_data.py`, `tools/ingest_json.py` (second ingestion path, used by dashboard), `tracker/snippet_generator.py`, `Dataset/generate_dataset_{500,5000}.py` | — |
| Unclassified scripts | root: `check_parquet.py`, `create_zip.py`, `inspect_schemas.py`, `query_test.py`, `test_*.py`; `cji_agent/`: `fix.py`, `generate_diverse.py`, `verify_data.py`, `test_*.py` | Ad-hoc diagnostics; some hit the database. |

## 7. Service ports, transports, storage, and data paths

| Service | Port | Transport | Defined in |
|---|---|---|---|
| Collector | 8000 (`COLLECTOR_PORT` builds URLs only; uvicorn takes `--port`) | HTTP | `config.py`, command line |
| `cji-journey-data` | 8001 | MCP over SSE | hard-coded in server |
| `cji-friction-engine` | 8002 | MCP over SSE | hard-coded |
| `cji-insight` | 8003 | MCP over SSE | hard-coded |
| `cji-report` | 8004 | MCP over SSE | hard-coded |
| `cji-ingestion-intelligence` | 8005 | MCP over SSE | hard-coded; `ingestion_worker.py` wrongly targets `localhost:8004/tools/<name>` over plain HTTP |
| Streamlit | 8501 | HTTP | framework default |

| Store | Path / config | Notes |
|---|---|---|
| Parquet (demo events) | `cji_agent/data/events.parquet` | **Tracked in git** although `data/` is gitignored. 45,283 rows, `journey_id` only `user_onboarding`, 8 steps, 2026-03-21 → 2026-04-20 `[RUN]`. |
| DuckDB (demo queries) | in-memory, view over the Parquet | `DUCKDB_PATH=data/cji.duckdb` is defined but unused by demo `[CODE]`. |
| PostgreSQL (realtime) | `DATABASE_URL` | Tables `live_events`, `api_keys` (created at collector start); `tracking_events` is read but its creator wasn't found; `demo_events` written by the generator. |
| ChromaDB | `data/chroma/` | Local persistent. |
| SQLite checkpoints | `data/cji_checkpoints.db` | Written by each run. |
| Mapping registry | `data/mapping_registry.json` | JSON, no locking `[DOC]`. |
| Other runtime paths | `data/ingestion_uploads/`, `data/last_run.json`, `reports/` | `data/`, `reports/`, `data/ingestion_uploads/` are created on `import config`. |
| Datasets | `Dataset/` (20 files, about 190 MB) | **Tracked in git** `[RUN]`. |

## 8. Environment variables, secrets, and baseline run safety

`config.py` loads `cji_agent/.env` at import (`load_dotenv()`, which does not override variables
already set) and asserts `CJI_MODE ∈ {demo, realtime}`. `.env` exists, is gitignored and untracked,
and was never read. The names below are from the code.

| Variable | Secret | Default in code | In `.env.example` |
|---|---|---|---|
| `CJI_MODE` | no | `demo` | yes |
| `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_MAX_TOKENS` | no | `claude-sonnet-4-6`, `0.0`, `2048` | yes |
| `GROQ_API_KEY` | yes | `""` | **no** |
| `ANTHROPIC_API_KEY` | yes | `""` | yes |
| `OPENAI_API_KEY` | yes | `""` (no code path uses it) | commented |
| `DATABASE_URL` | yes (password) | placeholder localhost URL | **no** |
| `SUPABASE_DATABASE_URL` | yes | — (dashboard fallback only) | **no** |
| `CJI_ADMIN_KEY` | yes | `change-me-in-production` | yes (same) |
| `COLLECTOR_HOST`, `COLLECTOR_PORT` | no | `http://localhost`, `8000` | yes |
| `REALTIME_WINDOW_MINUTES`, `REALTIME_AUTO_RUN_INTERVAL` | no | `60`, `0` | yes |
| `MAX_AGENT_ITERATIONS`, `FRICTION_SCORE_THRESHOLD` | no | `20`, `60` | yes |
| `JOURNEY_NAME` | no | `onboarding` (**does not match the tracked Parquet**, D-31) | yes |
| `INGESTION_SAMPLE_ROWS`, `INGESTION_CONFIDENCE_THRESHOLD` | no | `30`, `0.80` | **no** |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` | key yes | `false`, `""`, `cji-poc` | yes |

Tracked secrets: a `cji_live_…` key appears in 6 tracked files (`collector/api.py`, `snippets/*` ×4,
`docs/6-API-Contracts.md`). It is treated as retired (collector and Supabase not in use). The README
FAQ contains a password-like example string.

**Protected environment (required for every baseline or regression run):**

```powershell
$env:HTTPS_PROXY="http://127.0.0.1:9"; $env:HTTP_PROXY="http://127.0.0.1:9"; $env:NO_PROXY="localhost,127.0.0.1"
$env:DATABASE_URL="postgresql://baseline:baseline@127.0.0.1:1/baseline"; $env:SUPABASE_DATABASE_URL=$env:DATABASE_URL
$env:GROQ_API_KEY="baseline-offline-dummy"; $env:ANTHROPIC_API_KEY="baseline-offline-dummy"
$env:OPENAI_API_KEY="baseline-offline-dummy"; $env:LANGCHAIN_API_KEY="baseline-offline-dummy"
$env:LANGCHAIN_TRACING_V2="false"; $env:CJI_MODE="demo"; $env:CJI_ADMIN_KEY="baseline-local-only"
$env:PYTHONDONTWRITEBYTECODE="1"
```

Why it is needed: tests and `--generate-data` call `generate_demo_data`, which replaces `demo_events`
in whatever `DATABASE_URL` points to. The dead proxy blocks LLM, LangSmith and Render calls, so runs are
offline and deterministic. Network calls made during the baseline: uv (Python build), PyPI (packages),
and pip-audit (package names and versions only).

## 9. Requirements for this Spec

- **RB-1** Record current behaviour; do not change runtime source. *Met*: git status unchanged.
- **RB-2** Install from a declared interpreter and record the exact resolved set. *Met*: 3.12.13 + constraints file.
- **RB-3** Run every available check; record exact command, exit code, and result; record missing tools as blockers. *Met*: §5. Remaining blockers: no real PostgreSQL, no LLM keys allowed, no browser session.
- **RB-4** Keep **baseline failures (B-xx)** separate from future failures. Later Specs log new failures as **F-xx** in their own Spec. A failure on the B list is not a regression; any failure not on it is. (design §4)
- **RB-5** Distinguish current behaviour from the target architecture. (design §1–2)
- **RB-6** Record document-vs-code contradictions without editing the documents. (design §3)
- **RB-7** Every baseline or regression run uses the protected environment in §8.
- **RB-8** Hand every finding to a numbered later Spec, or list it as unassigned for the owner. (design §5)
