# Spec 02 — P0 Correctness and Security: Tasks

Sequential by design (guide §4, §9). `[x]` = evidence exists in `evidence/`.

**Protected environment:** `01-baseline/requirements.md` §8, plus `JOURNEY_NAME=user_onboarding` for
pipeline runs (D-31 is open until Spec 03). **Interpreter:** `C:\Users\sovan\.venvs\cji-baseline-312`.

## Tasks

- [x] **T0 Prepare.** Branch `phase-02-security` from `8523e47`. Golden snapshot from unchanged code → `golden-before.json` (8 metrics, 8 funnel rows, 50/20/20 events). Baseline suite matched B-01. Logs: `t0-*`.
- [x] **Failing tests first.** `tests/test_p0_security.py` against unchanged code: every R-01…R-05, U-4 and U-5 test failed or errored. The R-05 run is the first proof of the XSS (raw `<script>` in the report). Log: `before-fix-p0-tests.log`.
- [x] **T1 U-5** collector uses `from config import …`; `SQLAlchemy>=2.0.0,<2.1` resolves to 2.0.55 with psycopg2. `import collector.api` OK.
- [x] **T2 U-4** `VALID_WORKERS` added (6 targets, equal to the graph's edge map); stale expectation updated. `test_supervisor.py` now collects: 30/41 pass, 11 fail (F-01).
- [x] **T3 R-01** ingestion worker is async, uses `mcp_session("cji-ingestion-intelligence")`, no endpoint literals, always consumes `ingestion_pending_files`.
- [x] **T4 R-02** demo `get_system_info` checks the Parquet and DuckDB only.
- [x] **T5 R-04** all values bound (DuckDB `?`, SQLAlchemy `:name`); step order via a bound list (`list_position` / `array_position`); `live_stats` minutes 1–43200. Golden snapshot identical after the change.
- [x] **T6 R-03** `CJI_ENV` (default `production`), `CJI_CORS_ORIGINS`, fail-closed startup check, `allow_credentials=False`, admin key `compare_digest` + default rejection, no live-key seeding, dev key only in development.
- [x] **T7 U-2** retired key replaced in 4 snippet files and `docs/6-API-Contracts.md`; `git grep` finds 0 `cji_live_<hex>` in tracked files.
- [x] **T8 R-05** report text and attributes escaped, `mode` allow-listed, script data `\u003c`-encoded.
- [x] **T9 Gate**, see below.
- [x] **T10 Record the result without git.** Owner decision 2026-10-27: no commits and no pushes; this project is kept separate from GitHub. Rollback point instead: `evidence/spec02-tracked.patch` (`git diff --binary` of all 14 tracked files, 39,110 bytes) plus `evidence/spec02-new-file-test_p0_security.py`. Undo with `git apply -R evidence/spec02-tracked.patch` and delete `cji_agent/tests/test_p0_security.py`.

## Gate evidence (2026-10-27)

| Check | Command | Result | Baseline |
|---|---|---|---|
| P0 tests | `pytest tests/test_p0_security.py` | **47/47 pass** | all failed or errored before the fix |
| Unit suite | `pytest tests -m "not integration"` | **204/215 pass**; the 11 failures are all in `test_supervisor.py` (F-01) | 127 pass, 1 collection error |
| Other modules | same | agent 13/13, collector models 31/31, friction 50/50, ingestion 14/14, synthetic 19/19 | unchanged |
| Golden snapshot | `scripts/golden.py` before vs after | **identical** (57,436 chars) | — |
| Demo pipeline | `main.py --mode demo --run --auto-approve` | exit 0, 8 metrics, 4 critical, 4 insights, report written | same |
| Ingest probe | `main.py --ingest --file probe.csv --run --auto-approve` | **8005 reached** (4 message posts), 0 × 404, 0 calls to `8004/tools`, routed to ingestion once, no iteration-cap hit; file flagged (confidence 0.0, LLM blocked), pipeline continued to report | 404 on 8004; looped to the cap |
| Collector import | `python -c "import collector.api"` | OK | ModuleNotFoundError |
| ruff (changed files) | `ruff check .` | no changed file worse; total 266 → 263 | 266 |
| mypy (changed files) | `mypy .` | no changed file worse; total 52 → 49 | 52 |
| bandit B608 (journey data + collector) | `bandit -r .` | **10 → 0** (two justified `# nosec`: fixed `FROM` strings and the quote-escaped Parquet path) | 10 |
| pip-audit | `pip-audit -r constraints-spec02.txt` | 30 advisories in 8 packages; none for SQLAlchemy 2.0.55 | 30 |
| Diff hygiene | `git -c core.whitespace=cr-at-eol diff --check` | exit 0; 14 files changed + 1 new test file | — |
| NOT RUN | realtime SQL against PostgreSQL, collector startup against a database, browser check of the report | needs PostgreSQL / a browser (B-12) | — |

Notes:
- `git diff --check` without `cr-at-eol` flags 4 snippet lines because those files are stored with CRLF in the index (`i/crlf`). It is not real trailing whitespace.
- The baseline venv now has SQLAlchemy 2.0.55 (was 2.1.6). The new resolved set is in `constraints-spec02.txt`; Spec 01's constraints file stays unchanged as history.
- "ranked N fixes" grows across runs (14 → 26) because ChromaDB in `data/chroma/` (gitignored) keeps insights from earlier runs. Not caused by this Spec.

## New failures

| ID | Failure | Classification | Handed to |
|---|---|---|---|
| F-01 | 11 of the 41 restored supervisor tests fail. They expect an older supervisor: `supervisor()` returning `next_worker` and `messages`, an `_llm_route()` fallback, a `CJIState` annotation, and the cutoff preserving earlier errors. | **Pre-existing**, hidden by B-01 (the module never collected). Not caused by Spec 02: no routing code changed except adding `VALID_WORKERS`. | Spec 09 (Durable Workflow), which owns supervisor behaviour. Owner may choose to delete the obsolete tests instead. |
