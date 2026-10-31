# Spec 11 — Python Packaging: Tasks

Sequential. `[x]` means evidence exists. No commits or pushes: each step is recorded as a patch file in `evidence/`.

**Environment:** protected environment (dummy LLM keys, dead proxy, dead database URLs, `CJI_MODE=demo`). Network
was used only by uv (lock resolution, wheel build, clean venv) and by pip-audit (advisory lookup); no application
code ran with network access.

**Status:** approved 2026-10-28 ("implement spec 11", defaults OD-93 to OD-107); **implemented 2026-10-28**. Final
gate: `evidence/gate-results.txt`, numbers in `evidence/final-numbers.txt`.

## Tasks

- [x] **T0 Prepare.** `evidence/pre-spec11-tracked.patch` (432,348 bytes), `evidence/pre-spec11-untracked/` (61 files
  plus MANIFEST.txt), `evidence/t0.txt`. Baseline = Spec 10 gate (1036/1036).
- [x] **T1 Failing tests first.** `tests/test_packaging.py` against the old tree: 5/49 pass, 43 fail, 1 skipped
  (`evidence/before-tests-junit.xml`, `before-tests-summary.txt`). The 5 that passed are the old commands that
  already worked (`main.py`, `run_servers.py`, `-m settings --help`), one launcher-size check and a helper that
  pytest collected as a test (renamed `child_env` afterwards, so the final file has 48 tests).
- [x] **T2 Move.** `evidence/scripts/move_to_src.py`: dry run (`move-report-dryrun.txt`), then the move and rewrite
  (`move-report.txt`): 20 moves, 391 changed lines, 0 manual edits, 0 unqualified first-party imports. The 88 strings
  it lists for review are service names, roles, parameter names and file paths; each is accounted for in the review
  note at the end of the report.
- [x] **T3 Package.** `pyproject.toml` (setuptools, `cji-agent` 0.11.0, `>=3.12`, 26 runtime dependencies with
  ranges, 8 console scripts, 4 dependency groups, tool configuration); `requirements.lock` from
  `evidence/scripts/make_lock.py` (184 pins with hashes; `evidence/lock-diff.txt`: 39 packages removed, 2 added for
  other platforms, 1 version change: filelock 3.32.7 → 4.2.4, 0 unexpected); `CJI_HOME` (`settings.resolve_home`,
  `StorageSettings.home`, `.env` from the home, `cji-settings check` prints `home`); `cji/logs.py` and no logging
  setup at import; `sys.path.insert` removed from 5 modules; `main(argv)` for `cji`, `cji-ingest-json`,
  `cji-snippet`, `cji-generate-diverse`; `cji-servers` children get `CJI_HOME` and `cwd=home` (no `PYTHONPATH`);
  dashboard pipeline runs `-m cji.main`; collector serves `tracker.js` from package data; new
  `cji.dashboard_launcher` and `cji.collector.serve`; 10 launchers plus `_cji_launcher.py`; `pytest.ini` deleted;
  editable install in the baseline venv (`evidence/editable-install.txt`).
- [x] **T4 Tests updated.** conftest (no sys.path; `CJI_HOME` defaults to `cji_agent/`), source-reading tests use
  `SRC`, subprocess tests use `-m cji.main` / `-m cji.settings`, dashboard smoke test uses the installed
  `cji/dashboard.py`, settings defaults follow the home, import-policy tests map `cji.<pkg>` to `<pkg>`, the
  friction-engine isolation test checks `cji.integrations`/`cji.guardrails`, CL-11 tests replaced by
  `test_packaging.py`, README flag test covers the console scripts and the old commands.
- [x] **T5 Docs.** README: local setup (`pip install -r requirements.lock`, `pip install --no-deps -e .`), runtime
  home, command table (console scripts and old commands), every example uses the console scripts, environment table
  row for `CJI_HOME`, check commands (`pytest`, `ruff check`, `mypy`, `bandit -c pyproject.toml -r src`), FAQ entries.
  `.env.example` documents `CJI_HOME`. `.gitignore` already covered `*.egg-info/`, `build/`, `dist/` (unchanged).
- [x] **T6 Clean install.** Wheel `evidence/cji_agent-0.11.0-py3-none-any.whl` (82 entries: `cji/` and dist-info
  only, `tracker.js` included, 8 console scripts). Clean uv venv (CPython 3.12.13): `uv pip sync requirements.lock`
  installed 182 packages with hash checks, wheel installed with `--no-deps`, `uv pip check` clean. Full suite against
  the wheel 1079/1079 (`TEST_EXPECT_INSTALLED=wheel`). Every console script `--help` from a temporary directory: 8/8.
  Demo pipeline with `cji-servers` and `cji` started from a temporary directory with `CJI_HOME` set: completed,
  report in `CJI_HOME/reports`, no file written to the working directory.
- [x] **T7 Gate.** `evidence/scripts/gate_spec11.ps1` (Spec 10 gate plus design §7); `final_numbers.py` →
  `final-numbers.txt`; `save_spec11.py` → `spec11-tracked.patch` (512,160 bytes) and `spec11-new-files/` (100 files,
  MANIFEST.txt). Spec 11 copies of the gate helpers that imported the application: `golden.py`, `audit_check.py`,
  `audit_workflow_check.py`, `report_contract_check.py`.

## Final gate (2026-10-28 19:10–19:23)

| Check | Result | Spec 10 |
|---|---|---|
| Full suite, baseline venv (editable install), README command `pytest` | 1078 pass, 1 skipped (the wheel-only version check), 0 fail | 1036/1036 |
| Full suite, clean venv (installed wheel) | 1079/1079 | – |
| Spec 11 test set (7 modules) | 376 pass, 1 skipped, 0 fail | – |
| Tests added / removed | +54 (48 `test_packaging`, 6 README flag cases); −11 (CL-11 sys.path tests, old flag cases) | – |
| Golden snapshot (journey data via `cji.mcp_servers`) | identical to Spec 10 | – |
| Pipelines: none/pause/approve/groq/kill+resume/ingest/mode mismatch (old commands) | as Spec 10: all expected exit codes; kill during insight step resumed to completed | same |
| Report contract (5 gate reports), audit checks, collector smoke (16/16 via `uvicorn collector.api:app`) | PASS | PASS |
| ruff (`ruff check`, pyproject config) | 92 findings; new code clean | 97 |
| mypy (`mypy`, pyproject config with strict overrides) | 34 errors in 12 files (99 files checked) | 35 in 13 (94) |
| mypy `--strict`: workflow + domain/runs, reporting, integrations, repositories, new modules | 0 errors each | 0 |
| bandit `-c pyproject.toml -r src` | HIGH 0, MEDIUM 10 (B608 in dashboard.py, unchanged), LOW 25 | – |
| bandit, Spec 10 scope (`-r . -x ./.venv`) | HIGH 0, MEDIUM 12, LOW 1132 (+67: test asserts, one `subprocess` import) | 0 / 12 / 1065 |
| pip-audit on `requirements.lock` | 15 advisories in 5 packages (chromadb, langchain-core, langgraph, langgraph-checkpoint, langgraph-checkpoint-sqlite) | survey: 20 in 8 |
| tracked `data/events.parquet` | unchanged | unchanged |

The mypy change is scope: `snippets/verify_tracker.py` (generated) is no longer checked (`files = ["src", "tests"]`).
The ruff change: imports the move left unsorted were sorted in 5 touched files, which also fixed 5 older findings.

## Gate findings and deviations

- **G-1.** The design named the wheel switch `CJI_EXPECT_INSTALLED`. Settings reject unknown `CJI_*` variables when
  `CJI_ENV=test` (Spec 04), so the first gate's clean-venv suite stopped at conftest import. Renamed to
  `TEST_EXPECT_INSTALLED`; the whole gate was rerun.
- **G-2.** setuptools leaves `build/` and `src/cji_agent.egg-info/` in the source tree (gitignored) and reuses
  `build/lib`. The gate now removes them before and right after the build. In the final gate run they were still
  present during the Spec 10 scope bandit step; that step alone was rerun afterwards without `build/` (the numbers
  above are from the rerun log `gate-bandit-all.json.log`).
- **Moves are filesystem moves, not `git mv`** (design §2 said `git mv`): 61 of the moved files were never tracked, and
  the index was left alone. Git detects the renames by content when the work is committed (29 files moved unchanged,
  43 moved with import edits; see `spec11-new-files/MANIFEST.txt`).
- Launchers are 4 to 12 lines; the test limit is 30 (design said 10).
- `mypy` checks `src` and `tests` (design outline: `src/cji`), to keep the Spec 10 scope comparable.
- `cji-collector` is the console script; `uvicorn collector.api:app` keeps working through the launcher, and the
  collector configures logging on startup, not at import.

## Behaviour changes for users

- Setup is `pip install -r requirements.lock` then `pip install --no-deps -e .` from `cji_agent/`; the old
  `pip install -r requirements.txt` still works (it includes the lock).
- Paths follow the runtime home: `CJI_HOME`, else the working directory. Running from `cji_agent/` behaves as before.
- Removed dependencies (never imported): litellm, anthropic, langchain-community, sentence-transformers,
  pytest-asyncio, pytest-cov, and with them torch, transformers, scikit-learn, scipy, langchain,
  langchain-text-splitters, openai and 26 others (39 packages in total).
- Error messages say `Run: cji-settings check`; CLI hints say `cji --approve ...` instead of `python main.py ...`.

## Rollback

Reverse `spec11-tracked.patch`, apply `pre-spec11-tracked.patch`, restore `pre-spec11-untracked/`, delete the new
files (`pyproject.toml`, `requirements.lock`, `src/`, `_cji_launcher.py`, `tests/test_packaging.py`), and
`pip uninstall cji-agent` in the baseline venv.

## Findings carried forward

| ID | Finding | Owner |
|---|---|---|
| F-53 (part) | 15 advisories in chromadb 1.5.9, langchain-core 0.3.86, langgraph 0.2.28, langgraph-checkpoint 1.0.12, langgraph-checkpoint-sqlite 1.0.4; fixes need major upgrades; our use avoids the affected paths (OD-102) | Later Spec |
| F-49 | Dashboard renders data as HTML on pages other than Insights | Dashboard prompt |
| F-12, F-20, F-21 | Prompt reuse; `event_id` global key; plain-text tracker keys | Later Specs |
| F-22 to F-25, F-27, F-28 | Owner checks (journey names, dev key snippet, per-process limits, retired model, raw rows to the LLM, unused OpenAI key) | Owner |
