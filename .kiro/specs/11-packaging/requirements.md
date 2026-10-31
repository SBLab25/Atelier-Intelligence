# Spec 11 — Python Packaging: Requirements

Source: `kiro_upgrade_prompts.md`, Prompt 10 ("Convert the Python application into a supported installable
package"); guide row "11 Packaging" (R-14). Builds on Spec 04 (settings), Spec 05 (cleanup, sys.path policy CL-11)
and Specs 08–10.

**Status:** written 2026-10-28; approved 2026-10-28 (defaults OD-93 to OD-107); **implemented 2026-10-28** (final record in `tasks.md`).

## 1. Current state (surveyed after Spec 10)

`cji_agent/` is a flat directory of 94 Python files run from that directory: 7 top-level modules (`config`,
`graph`, `main`, `state`, `dashboard`, `run_servers`, `generate_diverse`) and 12 packages (`agents`, `collector`,
`domain`, `guardrails`, `integrations`, `mcp_servers`, `reporting`, `repositories`, `settings`, `tools`,
`workflow`, `tests`). There is no `pyproject.toml`; setup is `pip install -r requirements.txt` and commands are
`python main.py …`, `python run_servers.py`, `streamlit run dashboard.py`, `python -m settings check`,
`python -m uvicorn collector.api:app`, `python tools/ingest_json.py`, `python tracker/snippet_generator.py`,
`python generate_diverse.py`. Python is 3.12.13 in the test venv (`cji-baseline-312`, 221 distributions).

Evidence: `evidence/survey/` (scripts and their output, the baseline freeze, `pip-audit.json`).

### Findings

| ID | Finding | Evidence |
|---|---|---|
| F-50 | **Path workarounds.** `sys.path.insert` in 6 files (`mcp_servers/friction_engine_server.py`, `mcp_servers/insight_server.py`, `tools/ingest_json.py`, `tools/synthetic_data.py`, `tracker/snippet_generator.py`, `tests/conftest.py`); `run_servers.py` and one workflow test set `PYTHONPATH`; earlier gate scripts insert the working directory. | survey.txt |
| F-51 | **Nothing is installable.** No packaging metadata. Installing the current layout would put 19 generic top-level names (`config`, `settings`, `state`, `graph`, `main`, `tools`, `domain`, `agents`, …) into `site-packages`. | survey.txt |
| F-52 | **Declared dependencies do not match imports.** Imported but undeclared: `aiosqlite`, `numpy`, `starlette`, `typing-extensions` (and `pgserver` in tests). Declared but never imported: `litellm`, `anthropic`, `langchain-community`, `sentence-transformers` (which pulls `torch` 2.14.1, `transformers`, `scikit-learn`, `scipy`), `pytest-asyncio`, `pytest-cov`. `ruff`, `mypy` and `bandit` are not declared. `requirements.txt` says "Python 3.11+", but the installed `numpy` 2.5.4 and `scipy` 1.18.1 require ≥ 3.12. | survey2.txt, survey7.txt |
| F-53 | **Known vulnerabilities in the installed set.** `pip-audit` on the 221 pinned packages: 30 advisory entries (20 distinct IDs) in 8 packages: `chromadb` 1.5.9 (4, server/RBAC mode, no fixed release), `filelock` 3.32.7 (3, fixed in 4.2.1), `langchain` 0.3.30 and `langchain-text-splitters` 0.3.11 (2, only via the unused `langchain-community`), `langchain-core` 0.3.86 (2), `langgraph` 0.2.28 (2), `langgraph-checkpoint` 1.0.12 (3), `langgraph-checkpoint-sqlite` 1.0.4 (4). Exposure in §2, OD-102. | survey5.txt, pip-audit.json |
| F-54 | **Paths tied to the source location.** `settings/load.py` resolves data, reports and `.env` from its own file location; `config.ROOT`, `dashboard.py` (runs `ROOT/main.py`), `run_servers.py` (`cwd` + `PYTHONPATH`), `collector/api.py` (`ROOT/tracker/tracker.js`) and `tracker/snippet_generator.py` (`ROOT/<output>`) do the same. `config.py` calls `load_dotenv()` without a path, which searches upward from the calling file: once installed it would never find the project's `.env`. | survey4.txt |
| F-55 | **Import side effects.** `logging.basicConfig` at import in `mcp_servers/insight_server.py`, `mcp_servers/report_server.py`, `run_servers.py`, `tools/mcp_client.py`; `generate_diverse.py` generates about 1M events on import (no `main()`). | survey6.txt |
| F-56 | **Lint, type-check and test settings are not in the repository.** Ruff runs with its built-in rule set (407 rules, 97 findings) and mypy and bandit with defaults; only the local venv fixes their versions. Pytest settings live in a separate `pytest.ini`. | survey7.txt |

Not findings: every console command already has a `main()` (except `generate_diverse.py`); the uv cache holds every
wheel of the baseline set (offline dry run resolved all 221), and PyPI is reachable.

## 2. Decisions (defaults; confirm or change before implementation)

| ID | Decision | Default | Alternatives (rejected by default) |
|---|---|---|---|
| OD-93 | Layout and names | **src layout**: all application code moves to `cji_agent/src/cji/` (import package `cji`, distribution `cji-agent`). Tests stay in `cji_agent/tests/`. Imports become `cji.…`. The checkout itself is no longer importable, so tests can only use the installed package. | (b) Make `cji_agent/` itself the package (no moves, but the checkout stays importable and tests could silently import it). (c) Install the 19 current top-level names (collisions in `site-packages`). |
| OD-94 | Project root | `cji_agent/pyproject.toml`; the README keeps `cd cji_agent`. | Repository root. |
| OD-95 | Build backend | setuptools ≥ 77 (in the uv cache), package data declared explicitly. | hatchling. |
| OD-96 | Python versions | `requires-python = ">=3.12"`, classifier 3.12, tested on 3.12.13. No upper cap. | `>=3.11` (would need older numpy and scipy: unrelated downgrades). |
| OD-97 | Console scripts | `cji` (today's `main.py`, same arguments), `cji-servers`, `cji-settings`, `cji-dashboard`, `cji-collector`, `cji-ingest-json`, `cji-snippet`, `cji-generate-diverse`. Each module also runs as `python -m cji.<module>`. | One `cji` command with sub-commands (changes every argument list). |
| OD-98 | Current commands | Kept as **compatibility launchers** in `cji_agent/`: `main.py`, `run_servers.py`, `dashboard.py`, `generate_diverse.py`, `tools/ingest_json.py`, `tracker/snippet_generator.py`, `settings/__main__.py` (for `python -m settings check`) and `collector/api.py` (for `uvicorn collector.api:app`). Each is a few lines that call the installed package; package code never imports them (test). The README shows the console scripts first. | Remove the old commands. |
| OD-99 | Where runtime files live | New setting `CJI_HOME`, defaulting to the **current working directory**. `data/`, `reports/`, `.env`, snippet output and the checkpoint file resolve against it, so running from `cji_agent/` behaves exactly as today. `tracker.js` becomes package data. `cji-servers` and the dashboard pass an absolute `CJI_HOME` to the processes they start. | The package directory (writes into `site-packages`). A per-user directory such as `~/.cji` (the checkout's `data/` would no longer be used). |
| OD-100 | Dependency set | Declare every direct import (adds `aiosqlite`, `numpy`, `starlette`, `typing-extensions`). **Remove** the never-imported `litellm`, `anthropic`, `langchain-community`, `sentence-transformers`, `pytest-asyncio`, `pytest-cov`; with them go `torch`, `transformers`, `scikit-learn`, `scipy`, `langchain`, `langchain-text-splitters`, `openai` and others. Keep `openpyxl`, `pyarrow`, `psycopg2-binary`, `uvicorn` (used through pandas, SQLAlchemy and the collector). | Keep the unused packages. |
| OD-101 | Version constraints | Direct dependencies keep today's ranges, tightened to a floor at the tested version for security-sensitive packages (web server, HTTP clients, database drivers, MCP, checkpointing, settings parsing), each capped below the next major. `filelock>=4.2.1` as a security floor for a transitive package. The exact tested set goes in **`requirements.lock`** (`uv pip compile --universal --generate-hashes`, constrained to the baseline freeze), so nothing else changes version. | Unpinned ranges only. Bump everything to latest. |
| OD-102 | Vulnerable packages that stay | `langgraph` 0.2.28, `langgraph-checkpoint` 1.0.12, `langgraph-checkpoint-sqlite` 1.0.4, `langchain-core` 0.3.86 and `chromadb` 1.5.9 stay. Every fix needs a major upgrade (or none exists), and our use avoids the vulnerable paths: a local SQLite checkpointer with no store, cache or list filters; `langchain_core` messages only; embedded `PersistentClient`, no Chroma server. The remaining risk is "someone who can write the checkpoint or Chroma files can run code". It is recorded with a recommended LangGraph upgrade Spec. The gate runs `pip-audit` on the lock. | Upgrade LangGraph/LangChain now (rewrites Spec 09's driver). |
| OD-103 | Dependency groups | PEP 735 groups in `pyproject.toml`: `test` (pytest, pgserver), `lint` (ruff, mypy, bandit, pip-audit), `build` (build), `dev` = all three. All are pinned in `requirements.lock`. | Optional extras (`pip install cji-agent[dev]`), which publish dev tools as package metadata. |
| OD-104 | Tool configuration | Moved into `pyproject.toml`: pytest (from `pytest.ini`), ruff (`target-version = "py312"`, the built-in rule set of the pinned ruff), mypy (Python 3.12; strict for `cji.reporting`, `cji.workflow`, `cji.integrations`, `cji.repositories`, `cji.domain.runs`, as the gates already run them), bandit (skip tests). Reproducible commands: `ruff check`, `mypy`, `bandit -c pyproject.toml -r src`, `pytest`. | Separate config files. |
| OD-105 | Import safety | No logging setup at import (moved into each `main()`/`serve()`); `generate_diverse` gets a `main()`; `config.py` loads `CJI_HOME/.env` explicitly; every runnable module ends with `if __name__ == "__main__": raise SystemExit(main())`. | — |
| OD-106 | Clean-install proof | Gate: new venv (uv, Python 3.12) → `uv pip sync requirements.lock` → build the wheel → install the wheel without dependencies → run the test suite from `cji_agent/` and assert `cji` comes from that venv's `site-packages` → run every console script from a temporary directory → a demo pipeline from a temporary directory with `CJI_HOME` set → `pip-audit` on the lock. | Editable install only. |
| OD-107 | `requirements*.txt` | Kept for the old setup command: both become `-r requirements.lock` (hash-checked). The project itself is installed with `pip install --no-deps -e .` (one extra documented step). The launchers explain what to run when `cji` is not installed. | Unhashed lock with `-e .` inside `requirements.txt` (one step, no integrity check). Delete the files. |

## 3. Requirements

**R1 Package.** `pyproject.toml` (PEP 621) with name, version, description, readme, license, `requires-python`,
classifiers, dependencies, console scripts, package data (`cji/tracker/tracker.js`) and PEP 735 groups. The wheel
contains only `cji/**` and package data: no tests, data, reports, `.env` or snippets.

**R2 Boundaries.** All first-party imports are `cji.…` (absolute) or relative inside a subpackage. No module imports
a launcher. No `sys.path` or `PYTHONPATH` manipulation anywhere in `src/`, `tests/` or the launchers.

**R3 Import-safe.** Importing any `cji` module has no side effects beyond defining names, apart from the existing
lazy settings load on first use; `python -m cji.<module>` works for every runnable module.

**R4 Commands.** Every command in §1 still works from `cji_agent/` once the package is installed, with the same
arguments and exit codes. The console scripts of OD-97 work from any directory; `CJI_HOME` selects the runtime
directory.

**R5 Dependencies.** As OD-100, OD-101; `requirements.lock` is the exact tested set; a test checks that every
third-party import in `src/` maps to a declared dependency, and that each group matches `requirements-dev.txt`.

**R6 Security constraints.** As OD-101, OD-102; the gate's `pip-audit` result is recorded, with each remaining
advisory and the reason it remains.

**R7 Reproducible checks.** As OD-104: the same four commands run lint, type check, security scan and tests, with
the tool versions pinned in the lock.

**R8 Documentation.** README: local setup (venv, lock, editable install), the console scripts, `CJI_HOME`, the
environment variables table, the check commands; `.env.example` gains `CJI_HOME`.

**R9 Verified install.** As OD-106.

## 4. Non-goals

- Publishing to PyPI, versioning policy, release automation, Docker images (later prompts).
- Upgrading LangGraph, LangChain or Chroma (OD-102).
- Supporting Python 3.11 or 3.13 (not tested).
- Deleting the tracked stray outputs `test_output.txt` and `test_results.txt` (no effect on packaging; can be removed
  separately). The tracked `snippets/api_key.json` is owner item F-23.

## 5. Acceptance criteria (Prompt 10)

| Criterion | How it is shown |
|---|---|
| Clean installation succeeds | Gate: a new venv with only `requirements.lock` and the built wheel; `pip check` clean; import and `--help` of every console script. |
| CLI entry points work outside the repository root | Gate: every console script run from a temporary directory; a demo pipeline from a temporary directory with `CJI_HOME`. Tests run the console scripts with `cwd=tmp_path`. |
| Tests import the installed package rather than checkout-path hacks | No `sys.path` / `PYTHONPATH` anywhere (test); src layout so the checkout is not importable; the gate runs the suite against the wheel and asserts `cji.__file__` is in that venv's `site-packages`. |
| Current user-facing commands preserved | The gate's existing pipeline steps use the old commands (`python main.py …`, `python run_servers.py`, `python -m settings check`); tests run each launcher's `--help`. |
| Security-sensitive dependencies constrained | `pip-audit` on the lock in the gate; remaining advisories listed with exposure (OD-102). |
