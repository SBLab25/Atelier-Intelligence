# Spec 01 — Baseline and Onboarding: Design

Companion to `requirements.md` (evidence labels in its §0). This Spec changes no runtime code.
Conflicts are recorded with a proposed resolution and an owner; no existing document was edited.

## 1. Current architecture (verified at baseline)

```text
tracker.js ──POST /collect/batch, X-CJI-Key──► FastAPI collector :8000      ✗ cannot start (B-06)
                                                  └─► PostgreSQL (live_events, api_keys)
Dataset files ──► ingestion MCP :8005 (SSE)                                   ✗ unreachable from worker (B-04)
             └─► tools/ingest_json.py (dashboard's in-process path)
synthetic_data.py ──► data/events.parquet (tracked) + to_sql(demo_events) on DATABASE_URL

main.py ─► LangGraph supervisor (sync, 20-iteration cap), SQLite checkpoints
   ├─ ingestion_worker ─ HTTP POST localhost:8004/tools/<name>      ✗ wrong port and protocol
   ├─ data_worker      ─ SSE ─ journey-data :8001 ─ in-memory DuckDB over Parquet │ PostgreSQL
   ├─ friction_worker  ─ SSE ─ friction-engine :8002 (pure compute)
   ├─ insight_worker   ─ SSE ─ insight :8003 ─ Groq HTTPS (+retry) ─ ChromaDB
   └─ report_worker    ─ SSE ─ report :8004 ─ Groq HTTPS (no timeout) ─ reports/*.html
Streamlit dashboard.py :8501 ─ SQLAlchemy to PostgreSQL; subprocess .venv\Scripts\python.exe main.py
```

What works offline today `[RUN]`: all five MCP servers start; with `JOURNEY_NAME=user_onboarding`
the demo pipeline produces 8 step metrics, 4 critical steps, 4 fallback insights and an HTML report
in 49 s; 127 unit tests pass; the Streamlit server answers its health check.

Worth preserving: pure friction scoring; deterministic supervisor routing with an iteration cap;
pre-LLM sanitiser and post-LLM validator; LLM fallback path (exercised: the pipeline finished with
LLM calls blocked); demo/realtime split as two implementations of one interface.

## 2. Target architecture (decided vs proposed)

| Area | Status | Target |
|---|---|---|
| Python | **Decided** | CPython 3.12.x, `>=3.11,<3.13`, declared in `pyproject.toml` (Spec 11) |
| Realtime store | **Decided** | PostgreSQL only; DuckDB demo-only |
| Frontend | **Decided** | Next.js on Node 24 LTS, talking only to a versioned `/api/v1` (Specs 12–14) |
| Streamlit and CLI | **Decided** (process docs) | Kept until Spec 14 proves parity and rollback |
| Durable jobs, Redis, pgvector, object storage, OIDC | **Proposed** (`project_summary.md` §7) | Scope decided at Specs 09, 12, 15 |
| Internal MCP transport | Open (OD-2) | SSE today |
| LLM provider | Open (OD-4) | Groq calls today, Anthropic first in ingestion |

## 3. Audit findings re-checked (`refactoring.md`)

| ID | Claim | Status at baseline |
|---|---|---|
| R-01 | Ingestion worker uses port 8004 | **Confirmed at runtime**: `404 … http://localhost:8004/tools/detect_schema` |
| R-02 | Demo health check hits PostgreSQL | Confirmed in code (`journey_data_server.py` `get_system_info` → `execute_query`) |
| R-03 | Wildcard CORS with credentials, default admin key, seeded keys | Confirmed in code |
| R-04 | Interpolated SQL | Confirmed in code; bandit B608 ×22 |
| R-05 | Report HTML not escaped | **Not verified** (body not read); test first in Spec 02 |
| R-06 | Several event schemas | Confirmed in part (`journey_name` vs `journey_id`) |
| R-07 | False doc claims | Confirmed (D-13, D-16, D-17) |
| R-08 | Duplicated topology | Confirmed |
| R-09 | "Queued" before persistence | Confirmed in part |
| R-10 | Broad exception swallowing | Confirmed; also failures exit 0 (D-36) |
| R-11 | Dead or debug surfaces | Confirmed in part (`test_dummy`, loose scripts) |
| R-12 | No unified LLM contract | Confirmed; bandit B113 ×2 (requests without timeout) |
| R-13 | Sequential AI work | Not verified |
| R-14 | `sys.path` hacks, no packaging | Confirmed; collector also mixes import styles (D-33) |
| R-15 | Mixed-responsibility dashboard | Confirmed in part |

## 4. Baseline failure register (frozen 2026-10-27, commit `8523e47`)

These are the known failures. A later Spec may fix one, which should be noted against its ID.
Any failure not listed here is new: log it as **F-xx** in the Spec where it appeared.

| ID | Failure | Evidence | Handed to |
|---|---|---|---|
| B-01 | `tests/test_supervisor.py` fails to collect: `VALID_WORKERS` is not defined in `agents/supervisor.py`. 41 routing tests never run. | `b3-pytest-run.log` | Unassigned U-4 |
| B-02 | 2 integration tests fail without network or LLM keys (environmental). | `b3b-pytest-integration.log` | Opt-in only |
| B-03 | Default demo run analyses nothing: `JOURNEY_NAME=onboarding` vs Parquet `user_onboarding`. The friction worker fails until the supervisor cap; the CLI prints `[DONE] Analysis complete.` and exits 0. | `c3-demo-pipeline.log` | Spec 03 (journey identifiers), Spec 06 (exit codes), Spec 09 (fail fast) |
| B-04 | `--ingest` always fails (404 on the report server); the CLI exits 0. | `c4b-ingest-probe.log` | Spec 02 (R-01) |
| B-05 | `--ingest --file` without `--run` does nothing. | `c4-ingest-probe.log` | Spec 06 |
| B-06 | Collector cannot start: (a) the documented command fails on `cji_agent.config` import; (b) from the repo root it fails on the missing `psycopg` driver. | `c5-*`, `c5b-*` | Unassigned U-5 (blocks Spec 02 CORS tests) |
| B-07 | ruff: 266 findings | `b4-ruff-*.log` | Spec 06 → blocking in Spec 15 |
| B-08 | mypy: 52 errors in 18 files | `b5-mypy.log` | Per Spec for changed code (Prompt 2 rule) |
| B-09 | bandit: 25 medium, 300 low | `b6-bandit*.log` | Spec 02 (B608), Spec 08 (B113) |
| B-10 | pip-audit: 30 advisories in 8 packages; the fixes need versions outside `requirements.txt` caps | `b1-pip-audit.log` | Unassigned U-6 |
| B-11 | Dashboard page logic unverified; its Run button uses the incomplete `cji_agent/.venv` | `c6-*` | Spec 14 / OD-18 |
| B-12 | Realtime mode unverified (no PostgreSQL, missing driver) | — | Spec 05, Spec 07 |
| B-13 | `cji_agent/.venv` is incomplete (from an earlier session; untouched) | onboarding probe | OD-18 |

## 5. Conflict register

### 5.1 Repository documents vs code

D-01 to D-30 were found during onboarding and are summarised here. D-31 to D-36 are new from the
baseline runs.

| ID | Conflict (short) | Evidence | Spec |
|---|---|---|---|
| D-01 | Ingestion worker → 8004 REST; server is 8005 SSE | `[RUN]` | 02 |
| D-02 | Demo health check uses PostgreSQL; README says demo needs no external services | `[CODE]` | 02/05 |
| D-03 | Credentialed wildcard CORS; default admin key; keys seeded at startup | `[CODE]` | 02 |
| D-04 | Interpolated SQL | `[CODE]` | 02 |
| D-05 | Report escaping | `[UNVERIFIED]` | 02/10 |
| D-06 | Event schema variants | `[CODE]` | 03 |
| D-07 | Docs say 4 MCP servers; code has 5 | `[CODE]` | 06 |
| D-08 | Docs say stdio subprocess per call; code runs persistent SSE servers | `[RUN]` | 04 (OD-2) |
| D-09 | LLM provider: LiteLLM/Claude in docs, Groq in code | `[CODE]` | 08 (OD-4) |
| D-10 | Docs say DuckDB realtime; code and decision say PostgreSQL | `[CODE]` | 05 |
| D-11 | README collector contract (`/collect`, `X-Api-Key`, `CJITracker.init`) ≠ code | `[CODE]` | 06/07 |
| D-12 | Test counts (README 113, Project_Memory 50/13/16) vs actual 127 passing + 41 not collected | `[RUN]` | 06 |
| D-13 | Project_Memory says `cji_agent/` does not exist | `[DOC]` | 06 |
| D-14 | Stale paths and names in Project_Memory, Project_status, README | `[CODE]` | 06 |
| D-15 | 6 journey steps documented, 8 in code; dead `"completion"` branch in generator | `[CODE]` | 03 (OD-9) |
| D-16 | Project_Memory claims `quote_plus` encoding in `config.py`; absent | `[CODE]` | 04 |
| D-17 | README: "no hardcoded credentials", "all dependencies pinned"; both false | `[CODE]` | 02/11 |
| D-18 | Python version undeclared | resolved: 3.12 (owner) | 11 |
| D-19 | Node version undeclared | resolved: 24 LTS (owner) | 13 |
| D-20 | Two approval mechanisms (supervisor END and `interrupt_before`) | `[CODE]` | 09 |
| D-21 | Render keep-alive pings a dead host on every collector start | `[CODE]`, owner: not live | 07 |
| D-22 | Two dashboards, two ingestion paths; hard-coded `.venv` path | `[CODE]` | 06 (OD-7, OD-8) |
| D-23 | Undeclared `tenacity`; 4 declared packages with no import | `[CODE]` | 11 |
| D-24 | `.gitignore` vs tracked snippet files and `events.parquet`; no root `.gitignore` | `[RUN]` | U-3 |
| D-25 | `.env.example` missing `DATABASE_URL`, `GROQ_API_KEY`, `INGESTION_*`; still describes DuckDB and LiteLLM | `[CODE]` | 04 |
| D-26 | Project_Memory references a non-existent `docs/13-Phase3-…` | `[RUN]` | 06 |
| D-27 | README report name `cji_report_<timestamp>` vs code `cji_report_{journey}_{timestamp}` (`report_server.py:94`); README `--output-mode` flag does not exist | `[CODE]` | 06 |
| D-28 | `Project Details/` called "read-only reference" vs audit's "historical" | `[DOC]` | 06 (OD-11) |
| D-29 | The two input analyses order security differently | `[DOC]` | resolved: owner's Prompt order |
| D-30 | Provenance of `project_summary.md` / `refactoring.md` | resolved: owner's separate process docs | — |
| D-31 | Default `JOURNEY_NAME=onboarding` does not match the tracked Parquet (`user_onboarding`). README tracker example uses `user_onboarding`. Local reports from 02:37 today are named `cji_report_onboarding_*` (environment unknown). | `[RUN]` | 03 |
| D-32 | Project_status: `--ingest --file my_data.csv` = "just ingest"; code prints "No action specified" | `[RUN]` | 06 |
| D-33 | `collector/api.py` imports `cji_agent.config`; every other module uses flat imports; documented start command fails | `[RUN]` | U-5 / 11 |
| D-34 | `SQLAlchemy>=2.0.0` resolves to 2.1.6, whose default `postgresql://` driver is `psycopg`; only `psycopg2-binary` declared | `[RUN]` | U-5 / 11 |
| D-35 | `test_supervisor.py` expects `VALID_WORKERS`; the module does not define it | `[RUN]` | U-4 |
| D-36 | CLI exits 0 and prints success on failed analysis and failed ingestion | `[RUN]` | 06/09 |

### 5.2 Process documents vs each other

| ID | Conflict | Proposed resolution | Owner decision |
|---|---|---|---|
| P-1 | Numbering: `kiro_upgrade_prompts.md` Prompts 0–15; `kiro_upgrade_guide.md` Specs 01–15; `free_plan_workflow.md` Phases 0–7. Prompt N = Spec N+1 for N ≤ 14. Prompt 15 (review) has no Spec; guide Spec 15 "Production Release" = Prompt 14. | Spec folders use guide numbers (`01-baseline`); text cites both. | Accept or change |
| P-2 | Branches: `free_plan_workflow.md` lists 8 phase branches that group the 15 Specs differently. | One branch per Spec: `phase-02-security`, `phase-03-contracts`, … | OD-14 |
| P-3 | `free_plan_workflow.md` Phase 0 says "create a baseline commit", but this Spec changes no tracked file and process docs are not committed. | Baseline = `8523e47` plus this Spec's evidence; optional local tag `baseline-2026-10-27`. | OD-15 |
| P-4 | `free_plan_workflow.md` uses Antigravity/GSD commands; the guide says they may not exist in Kiro. | Guide wins inside Kiro (both docs say so). | None |
| P-5 | Guide §11: never commit `graphify-out/`; it is untracked and not ignored. | Local `.git/info/exclude` (not tracked) or root `.gitignore` in Spec 06. | Part of U-3 |
| P-6 | Prompt 1 requires CORS and credential tests, but the collector cannot be imported at baseline (B-06). | Let Spec 02 include the minimal unblock (U-5). | OD-19 |
| P-7 | Prompt 1 and Prompt 9 both cover R-05. | Spec 02 = minimal escaping plus test; Spec 10 = full hardening. | None |

## 6. Roadmap (owner's order: Prompts 0 → 15)

Each later Spec is created when it starts, from `kiro_upgrade_prompts.md`. This table lists
what the baseline hands to each one, not its tasks.

| Prompt | Spec | Scope | Baseline input |
|---|---|---|---|
| 0 | 01 Baseline | This Spec | — |
| 1 | 02 P0 Security | R-01…R-05 | D-01/B-04, D-02, D-03, D-04 (B608 ×22), D-05, D-17; P-6 |
| 2 | 03 Contracts | One contract layer | D-06, D-15 (OD-9), D-31/B-03 journey identifier |
| 3 | 04 Configuration | Typed settings and service registry | D-08 (OD-2), D-16, D-25, ports in 7 places |
| 4 | 05 Repositories | Demo/realtime isolation | D-02, D-10, unused `DUCKDB_PATH`, B-12 |
| 5 | 06 Cleanup | Dead code and docs | D-07, D-11–D-14, D-22 (OD-7/8), D-26–D-28, D-32, D-36, `test_dummy`, B-05, B-07 |
| 6 | 07 Collector | Hardening | R-09, D-21 (delete keep-alive), realtime tests on throwaway PostgreSQL (Docker present) |
| 7 | 08 AI Gateway | LLM/MCP policy | D-09 (OD-4), B113 ×2, model allow-list duplication |
| 8 | 09 Durable Workflow | Resumable runs | D-20, `use_persistence`, B-03 loop-to-cap behaviour |
| 9 | 10 Safe Reports | Report hardening | R-05 full, unpinned Chart.js, filename safety |
| 10 | 11 Packaging | `pyproject.toml` | D-18, D-23, D-33, D-34, `sys.path`, lockfile, dashboard `.venv` path |
| 11 | 12 Backend API | `/api/v1` | Auth method (OD-16) |
| 12 | 13 Next.js Foundation | Thin slice | Node 24 LTS, package manager (OD-17), `useCJITracker.js` |
| 13 | 14 Frontend Parity | Streamlit parity | B-11 |
| 14 | 15 Production Hardening | Release | CI; ruff, mypy, bandit, pip-audit as blocking checks; history rewrite for the tracked key |
| 15 | — | Final review | All registers |

### 6.1 Findings with no home in the owner's prompts

| ID | Finding | Proposed home |
|---|---|---|
| U-1 | Ingestion upload limits (size, rows, format, staging) | Spec 07 or 05 |
| U-2 | Retired `cji_live_…` key still in 6 tracked files (Prompt 1 covers code seeding only) | Spec 02 |
| U-3 | No root `.gitignore`; `graphify-out/`; tracked `Dataset/` (about 190 MB), logs, zip, `events.parquet` | Spec 06 (OD-13) |
| U-4 | Restore the 41 supervisor tests (B-01). They are the safety net for routing changes. | Before Spec 03, preferably in Spec 02 as a test-only change |
| U-5 | Collector import path and driver (B-06); blocks Spec 02's CORS tests | Spec 02 minimal unblock, full fix in Spec 11 |
| U-6 | 30 dependency advisories need upgrades past current caps | Assess in Spec 11; gate in Spec 15 |

## 7. Open decisions

Resolved: OD-1 Python 3.12 · OD-3 PostgreSQL · OD-5 key retired · OD-6 Render not live ·
OD-10 Next.js · OD-12 process docs not committed · Supabase not in use · Spec 01 branch.

| ID | Decision | Needed by |
|---|---|---|
| OD-14 | Branch naming for Specs 02–15 (P-2) | Spec 02 |
| OD-15 | Baseline marker: tag `8523e47` or record only (P-3) | Spec 02 |
| OD-18 | Old `cji_agent/.venv`: rebuild on 3.12 so the dashboard Run button works, or leave it | Spec 02 |
| OD-19 | Homes for U-1…U-6, especially U-4 and U-5 | Spec 02 |
| OD-9 | Journey step set (6 vs 8) and canonical journey ID (`onboarding` vs `user_onboarding`) | Spec 03 |
| OD-2 | Internal MCP transport | Spec 04 |
| OD-7, OD-8 | Canonical dashboard; canonical ingestion path | Spec 06 |
| OD-11, OD-13 | Historical docs; tracked artifacts | Spec 06 |
| OD-4 | LLM provider strategy | Spec 08 |
| OD-16 | API authentication method | Spec 12 |
| OD-17 | Next.js package manager | Spec 13 |
