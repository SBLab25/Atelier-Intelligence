# Spec 11 — Python Packaging: Design

Defaults from requirements §2 (OD-93 to OD-107), approved and implemented. Deviations found while implementing are listed in `tasks.md` (gate findings and deviations).

## 1. Layout after the change

```
cji_agent/
  pyproject.toml            new: metadata, dependencies, groups, scripts, tool config (pytest, ruff, mypy, bandit)
  requirements.lock         new: exact tested set with hashes (runtime + dev), generated
  requirements.txt          "-r requirements.lock" (old setup command)
  requirements-dev.txt      "-r requirements.lock"
  src/cji/                  all application code (moved, history kept by git rename detection)
    __init__.py             __version__
    config.py graph.py main.py state.py dashboard.py run_servers.py
    agents/ collector/ domain/ guardrails/ integrations/ mcp_servers/ reporting/ repositories/
    settings/ tools/ workflow/
    tools/generate_diverse.py        (was cji_agent/generate_diverse.py, now with main())
    tracker/__init__.py tracker/snippet_generator.py tracker/tracker.js (package data)
    dashboard_launcher.py            cji-dashboard: `streamlit run <path of cji/dashboard.py>`
    collector/serve.py               cji-collector: uvicorn on the configured collector endpoint
  tests/                    unchanged location; imports cji.*
  main.py run_servers.py dashboard.py generate_diverse.py      launchers (OD-98)
  tools/ingest_json.py  tracker/snippet_generator.py           launchers
  settings/__init__.py settings/__main__.py                    launcher for `python -m settings check`
  collector/__init__.py collector/api.py                       launcher for `uvicorn collector.api:app`
  data/ reports/ snippets/ .env .env.example                   runtime files (CJI_HOME when run from here)
  pytest.ini                deleted (moved into pyproject)
```

A launcher is at most 10 lines:

```python
"""Compatibility launcher: same as `cji` (installed by `pip install -e .`). Spec 11, OD-98."""
from _cji_launcher import run   # tiny helper next to the launchers: clear message if cji is not installed
run("cji.main")
```

`_cji_launcher.py` imports the target module with `importlib.import_module` and calls its `main()`; on
`ModuleNotFoundError: cji` it prints the install command and exits 2. The `collector/api.py` launcher does
`from cji.collector.api import app` (uvicorn needs the attribute), `settings/__main__.py` calls
`cji.settings.__main__.main`. `dashboard.py` runs `runpy.run_module("cji.dashboard", run_name="__main__")` so
`streamlit run dashboard.py` keeps working (Streamlit re-runs the script, which re-runs the module).

## 2. The move (T2, scripted)

`evidence/scripts/move_to_src.py` (idempotent, dry-run mode first):
1. `git mv` every application module and package into `src/cji/` (keeps history); `generate_diverse.py` →
   `src/cji/tools/generate_diverse.py`; `tracker/snippet_generator.py`, `tracker/tracker.js` → `src/cji/tracker/`.
2. Rewrite imports in `src/` and `tests/` with a token-level pass over `import`/`from` statements only:
   `from config import X` → `from cji.config import X`; `import agents.workers as w` →
   `import cji.agents.workers as w`; bare `import config` → `from cji import config`. Relative imports untouched.
3. Rewrite first-party module strings (31 found): `"mcp_servers.journey_data_server"` → `"cji.mcp_servers…"`
   (settings service registry, `importlib.import_module`, `sys.modules.get`, `monkeypatch` targets, `-m` args),
   `"collector.api:app"` → `"cji.collector.api:app"`, `"dashboard.py"` in the service registry → the module name.
4. Report every line it changed (`evidence/move-report.txt`) and every first-party name left unqualified (must be
   empty).

Remaining edits are by hand (T3): path roots, side effects, launchers, tests that read source files (`APP_ROOT /
"mcp_servers"` → `SRC = APP_ROOT / "src" / "cji"`), subprocess commands in tests (`[sys.executable, "main.py", …]`
→ `[sys.executable, "-m", "cji.main", …]`).

## 3. Runtime home (OD-99)

`settings/load.py`:
- `home()` = `Path(CJI_HOME)` if set (relative values resolve against the working directory once), else
  `Path.cwd()`; resolved to an absolute path when settings load.
- Defaults: `data_dir = home/data`, `reports_dir = home/reports`, `.env` = `home/.env`, checkpoints and audit under
  `data_dir` as today; relative `CJI_DATA_DIR`/`CJI_REPORTS_DIR` resolve against home.
- `APP_ROOT` is renamed `HOME`-based in settings; `config.ROOT` becomes the home directory (kept as an alias for old
  imports).
- `CJI_HOME` is a known key (settings check lists it); `.env.example` documents it.

Callers:
- `run_servers.py`: children run `[sys.executable, "-m", <module>]` with `cwd=home` and `CJI_HOME=<absolute home>`
  in their environment; no `PYTHONPATH`.
- `dashboard.py`: pipeline subprocess `[sys.executable, "-m", "cji.main", …]`, `cwd=home`, `CJI_HOME` set.
- `collector/api.py`: `tracker.js` read with `importlib.resources.files("cji.tracker") / "tracker.js"`.
- `tracker/snippet_generator.py`: `--output` relative to home.
- `config.py`: `load_dotenv(home/.env)` (outside `CJI_ENV=test`, as today).

## 4. pyproject.toml (outline)

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "cji-agent"
version = "0.11.0"
requires-python = ">=3.12"
dependencies = [ ...direct imports, ranges per OD-101... ]

[project.scripts]
cji = "cji.main:main"
cji-servers = "cji.run_servers:main"
cji-settings = "cji.settings.__main__:main"
cji-dashboard = "cji.dashboard_launcher:main"
cji-collector = "cji.collector.serve:main"
cji-ingest-json = "cji.tools.ingest_json:main"
cji-snippet = "cji.tracker.snippet_generator:main"
cji-generate-diverse = "cji.tools.generate_diverse:main"

[dependency-groups]
test = ["pytest", "pgserver"]
lint = ["ruff", "mypy", "bandit", "pip-audit"]
build = ["build"]
dev = [{include-group = "test"}, {include-group = "lint"}, {include-group = "build"}]

[tool.setuptools.packages.find]   where = ["src"]
[tool.setuptools.package-data]    cji = ["tracker/tracker.js"]
[tool.pytest.ini_options]         (from pytest.ini; testpaths = ["tests"])
[tool.ruff]                       target-version = "py312"; src = ["src", "tests"]
[tool.mypy]                       python_version = "3.12"; files = ["src/cji"]; strict overrides (OD-104)
[tool.bandit]                     exclude_dirs = ["tests"]
```

Direct dependencies (versions = tested; ranges keep today's caps):
`langchain-core>=0.3.86,<0.4`, `langgraph>=0.2.28,<0.3`, `langgraph-checkpoint-sqlite>=1.0.4,<2`,
`aiosqlite>=0.20,<0.21`, `mcp>=2.3,<3`, `fastmcp>=4.1.4,<5`, `duckdb>=1.5,<2`, `SQLAlchemy>=2.0.55,<2.1`,
`psycopg2-binary>=2.9.13,<3`, `chromadb>=1.5.9,<2`, `faker>=40,<41`, `pandas>=3.1,<4`, `numpy>=2.5,<3`,
`pyarrow>=26,<27`, `openpyxl>=3.1.5,<4`, `fastapi>=0.162,<0.163` (0.x: minor = breaking), `starlette>=1.10,<2`,
`uvicorn[standard]>=0.54,<0.55`, `pydantic>=2.14,<3`, `python-dotenv>=1.2,<2`, `requests>=2.34,<3`,
`httpx>=0.28.1,<0.29`, `streamlit>=1.66,<2`, `plotly>=7.1,<8`, `typing-extensions>=4.16`, and the security floor
`filelock>=4.2.1`.

## 5. Lock (OD-101)

`evidence/scripts/make_lock.py`:
1. `uv pip freeze` of the baseline venv → constraints, minus the packages OD-100 removes and minus `filelock`.
2. `uv pip compile pyproject.toml --group dev --universal --python-version 3.12 --generate-hashes
   -c constraints.txt -o requirements.lock`.
3. Diff the lock against the baseline freeze and write `evidence/lock-diff.txt`: removed packages, added packages,
   changed versions. Expected changes: the removals of OD-100, `filelock` 3.32.7 → ≥ 4.2.1, `pip-audit` and its
   dependencies added, platform-specific packages for other systems. Any other version change stops the task.

## 6. Tests (new and changed)

New `tests/test_packaging.py`:
- `pyproject.toml` parses; `requires-python`, scripts, groups and package data as OD-96/97/103.
- Every third-party import in `src/` (AST scan) maps to a declared dependency (via
  `importlib.metadata.packages_distributions()`); no declared runtime dependency is unused.
- No `sys.path`/`PYTHONPATH` manipulation in `src/`, `tests/`, launchers (replaces the CL-11 tests in
  `test_cleanup.py`).
- No module in `src/cji` imports a launcher name or a non-`cji` first-party name.
- Importing every `cji` module in a fresh interpreter changes no logging handlers, writes no files and starts no
  threads (import-safety check).
- Every console script and every launcher answers `--help` with exit 0, run with `cwd=tmp_path` (launchers from
  `cji_agent/`).
- `CJI_HOME` resolution: unset → `cwd`; relative and absolute values; data, reports and `.env` follow it.
- `cji` is imported from an installed location (not `src/` when the wheel is installed; the gate runs this test
  against the wheel with `CJI_EXPECT_INSTALLED=wheel`).
- `requirements-dev.txt`/`requirements.txt` point at the lock; the lock pins every declared dependency.

Changed: tests that read sources use `SRC`; subprocess tests use `-m cji.main`/`-m cji.settings`; the dashboard smoke
test uses the packaged file path; settings tests expect home-based defaults; CL-11 tests move to
`test_packaging.py`.

## 7. Gate additions (T7)

The Spec 10 gate (unchanged pipeline steps, so the old commands are exercised), plus:
- `uv build --wheel` and a wheel content check (only `cji/` and `tracker.js`; no tests/data/.env).
- Clean venv: `uv venv` (3.12) → `uv pip sync requirements.lock` → `uv pip install --no-deps <wheel>` →
  `pip check` → full test suite from `cji_agent/` with `CJI_EXPECT_INSTALLED=wheel` → every console script `--help`
  from a temporary directory → `cji --mode demo --run --auto-approve` from a temporary directory with `CJI_HOME`
  pointing at a copy of `data/events.parquet` (servers started with `cji-servers` from the same venv).
- `pip-audit -r requirements.lock` (recorded; remaining advisories compared with OD-102).
- `ruff check`, `mypy`, `bandit -c pyproject.toml -r src`, `pytest` run as the README documents them.
- Golden snapshot (journey data server outputs) compared with Spec 10 using a copy of the golden script that
  imports `cji.mcp_servers`.

## 8. Risks

| Risk | Mitigation |
|---|---|
| A missed import or string reference breaks at runtime only | Move script reports every unqualified first-party name; full suite, all pipelines and the clean-venv run; `python -m compileall`; import-every-module test. |
| `cwd` as default home surprises someone who runs a command from another directory | `cji-settings check` prints the resolved home and data directory; README states it; `CJI_HOME` overrides. |
| Removing packages breaks an indirect use (e.g. a pandas engine) | Removal limited to packages never imported and not optional engines of imported ones; clean-venv suite and pipelines without them. |
| The editable install in the baseline venv changes the gate environment | Recorded; the baseline venv only gains `cji-agent` (editable) and loses nothing. The clean venv is the acceptance proof. |
| Lock resolution changes versions | Constrained to the baseline freeze; `lock-diff.txt` must show only the expected changes. |

## 9. Rollback

Reverse `spec11-tracked.patch`, apply `pre-spec11-tracked.patch`, restore `pre-spec11-untracked/`, delete the new
files (`pyproject.toml`, `requirements.lock`, `src/`, launchers, `tests/test_packaging.py`), and
`pip uninstall cji-agent` in any venv where it was installed.
