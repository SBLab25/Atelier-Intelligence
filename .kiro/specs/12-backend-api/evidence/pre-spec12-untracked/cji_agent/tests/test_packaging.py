"""
Spec 11 — Python packaging (design §6).

The application is the installed package `cji` (src layout); the checkout itself is not importable. Old commands are
small launchers in cji_agent/ that call the package. No sys.path / PYTHONPATH manipulation anywhere. These tests
run against an editable install or, in the gate, against the built wheel (TEST_EXPECT_INSTALLED=wheel; not a
CJI_* name, because settings reject unknown CJI_* variables when CJI_ENV=test).
"""
import ast
import importlib.metadata as md
import importlib.util
import json
import os
import re
import subprocess
import sys
import sysconfig
import textwrap
import tomllib
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent          # cji_agent/
SRC = PROJECT / "src" / "cji"
TESTS = PROJECT / "tests"
PYPROJECT = PROJECT / "pyproject.toml"
WHEEL_MODE = os.environ.get("TEST_EXPECT_INSTALLED") == "wheel"

SCRIPTS = {
    "cji": "cji.main:main",
    "cji-servers": "cji.run_servers:main",
    "cji-settings": "cji.settings.__main__:main",
    "cji-dashboard": "cji.dashboard_launcher:main",
    "cji-collector": "cji.collector.serve:main",
    "cji-ingest-json": "cji.tools.ingest_json:main",
    "cji-snippet": "cji.tracker.snippet_generator:main",
    "cji-generate-diverse": "cji.tools.generate_diverse:main",
}
LAUNCHERS = ["_cji_launcher.py", "main.py", "run_servers.py", "dashboard.py", "generate_diverse.py",
             "tools/ingest_json.py", "tracker/snippet_generator.py", "settings/__init__.py", "settings/__main__.py",
             "collector/__init__.py", "collector/api.py"]
OLD_NAMES = {"config", "graph", "main", "state", "dashboard", "run_servers", "generate_diverse", "agents",
             "collector", "domain", "guardrails", "integrations", "mcp_servers", "reporting", "repositories",
             "settings", "tools", "workflow", "tracker"}
REMOVED = {"litellm", "anthropic", "langchain-community", "sentence-transformers", "torch", "transformers",
           "langchain", "langchain-text-splitters", "scikit-learn", "scipy", "pytest-asyncio", "pytest-cov"}
# Declared runtime dependencies that are used without an import statement (pandas engines, SQLAlchemy driver,
# the collector's ASGI server through cji-collector is imported) and the transitive security floor.
INDIRECT = {"openpyxl", "pyarrow", "psycopg2-binary", "filelock"}
ALIASES = {"fastmcp-slim": "fastmcp"}      # the `fastmcp` import comes from fastmcp-slim, required by fastmcp


def pyproject():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def req_name(req):
    return canonical(re.split(r"[<>=!~\[ ;(]", req.strip(), maxsplit=1)[0])


def own_python_files():
    files = list(SRC.rglob("*.py")) + list(TESTS.rglob("*.py")) + [PROJECT / rel for rel in LAUNCHERS]
    return [p for p in files if p.exists() and "__pycache__" not in p.parts]


def imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module, node.lineno


def child_env(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("CJI_") and k != "PYTHONPATH"}
    env.update({"CJI_ENV": "test", "CJI_HOME": str(tmp_path), "PYTHONIOENCODING": "utf-8", **extra})
    return env


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Metadata, groups, tool configuration
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_pyproject_metadata():
    data = pyproject()
    project = data["project"]
    assert project["name"] == "cji-agent"
    assert project["requires-python"] == ">=3.12"
    assert "Programming Language :: Python :: 3.12" in project["classifiers"]
    assert project["scripts"] == SCRIPTS
    assert data["build-system"]["build-backend"] == "setuptools.build_meta"


def test_dependency_groups():
    groups = pyproject()["dependency-groups"]

    def names(key):
        return {req_name(r) for r in groups[key] if isinstance(r, str)}

    assert names("test") == {"pytest", "pgserver"}
    assert names("lint") == {"ruff", "mypy", "bandit", "pip-audit"}
    assert names("build") == {"build"}
    assert {"include-group": "test"} in groups["dev"]
    assert {"include-group": "lint"} in groups["dev"]
    assert {"include-group": "build"} in groups["dev"]


def test_removed_dependencies_are_gone():
    data = pyproject()
    declared = {req_name(r) for r in data["project"]["dependencies"]}
    for group in data["dependency-groups"].values():
        declared |= {req_name(r) for r in group if isinstance(r, str)}
    assert declared & REMOVED == set()


def test_security_floor_for_filelock():
    reqs = {req_name(r): r for r in pyproject()["project"]["dependencies"]}
    assert re.search(r">=\s*4\.2\.1", reqs["filelock"])


def test_tool_configuration_lives_in_pyproject():
    tool = pyproject()["tool"]
    assert tool["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert tool["ruff"]["target-version"] == "py312"
    assert tool["mypy"]["python_version"] == "3.12"
    assert tool["bandit"]["exclude_dirs"] == ["tests"]
    assert not (PROJECT / "pytest.ini").exists()


def test_requirements_files_point_at_the_lock():
    for name in ("requirements.txt", "requirements-dev.txt"):
        lines = [line.strip() for line in (PROJECT / name).read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        assert lines == ["-r requirements.lock"], name


def lock_entries():
    entries, current = {}, None
    for line in (PROJECT / "requirements.lock").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            m = re.match(r"([A-Za-z0-9_.\-]+)==([^\s;\\]+)", line)
            assert m, line
            current = canonical(m.group(1))
            entries.setdefault(current, {"version": m.group(2), "hashes": 0})
        elif "--hash=" in line and current:
            entries[current]["hashes"] += 1
    return entries


def test_lock_pins_every_declared_dependency_with_hashes():
    lock = lock_entries()
    data = pyproject()
    wanted = {req_name(r) for r in data["project"]["dependencies"]}
    for group in data["dependency-groups"].values():
        wanted |= {req_name(r) for r in group if isinstance(r, str)}
    assert wanted - set(lock) == set()
    assert [n for n, e in lock.items() if e["hashes"] == 0] == []
    assert set(lock) & REMOVED == set()
    major, minor, patch = (int(x) for x in lock["filelock"]["version"].split(".")[:3])
    assert (major, minor, patch) >= (4, 2, 1)


@pytest.mark.skipif(not WHEEL_MODE, reason="the clean venv installs exactly the lock (gate)")
def test_installed_versions_match_the_lock():
    lock = lock_entries()
    installed = {canonical(d.metadata["Name"]): d.version for d in md.distributions()}
    wrong = {n: (e["version"], installed.get(n)) for n, e in lock.items()
             if n in installed and installed[n] != e["version"]}
    assert wrong == {}
    assert set(installed) & REMOVED == set()


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Package boundaries
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_layout_and_package_data():
    setuptools_cfg = pyproject()["tool"]["setuptools"]
    assert setuptools_cfg["packages"]["find"]["where"] == ["src"]
    assert "tracker/tracker.js" in setuptools_cfg["package-data"]["cji"]
    assert (SRC / "__init__.py").is_file() and (SRC / "tracker" / "tracker.js").is_file()


def test_old_top_level_names_hold_only_launchers():
    allowed = set(LAUNCHERS)
    for name in sorted(OLD_NAMES):
        for path in (PROJECT / name, PROJECT / f"{name}.py"):
            if path.is_dir():
                files = {p.relative_to(PROJECT).as_posix() for p in path.rglob("*")
                         if p.is_file() and "__pycache__" not in p.parts}
                assert files <= allowed, sorted(files - allowed)
            elif path.exists():
                assert path.name in allowed, path.name


@pytest.mark.parametrize("rel", LAUNCHERS)
def test_launchers_are_small_and_only_delegate(rel):
    text = (PROJECT / rel).read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 30
    assert "cji" in text or rel.endswith("__init__.py")
    for mod, _ in imports(PROJECT / rel):
        assert mod.split(".")[0] not in OLD_NAMES - {"cji"}, mod


def test_no_sys_path_or_pythonpath_manipulation():
    pattern = re.compile(r"sys\.path\.(insert|append|extend)\(|sys\.path\s*=|site\.addsitedir|[\"']PYTHONPATH[\"']")
    hits = [f"{p.relative_to(PROJECT)}:{i}: {line.strip()}"
            for p in own_python_files() if p.name != "test_packaging.py"
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if pattern.search(line)]
    assert hits == []


def test_first_party_imports_use_the_cji_package():
    bad = [f"{p.relative_to(PROJECT)}:{line}: {mod}"
           for p in list(SRC.rglob("*.py")) + list(TESTS.rglob("*.py"))
           for mod, line in imports(p) if mod.split(".")[0] in OLD_NAMES]
    assert bad == []


def test_checkout_modules_are_not_importable_by_their_old_names():
    for name in ("config", "graph", "state", "agents", "domain", "workflow", "reporting", "integrations",
                 "mcp_servers", "repositories", "guardrails"):
        assert importlib.util.find_spec(name) is None, name


def test_cji_is_imported_from_an_installation():
    import cji

    location = Path(cji.__file__).resolve()
    if WHEEL_MODE:
        assert "site-packages" in location.parts
        assert PROJECT.resolve() not in location.parents
    else:
        assert location == (SRC / "__init__.py").resolve() or "site-packages" in location.parts


def test_every_third_party_import_is_declared_and_every_dependency_is_used():
    declared = {req_name(r) for r in pyproject()["project"]["dependencies"]}
    mapping = md.packages_distributions()
    used, missing = set(), {}
    for p in SRC.rglob("*.py"):
        for mod, line in imports(p):
            top = mod.split(".")[0]
            if top in sys.stdlib_module_names or top in ("cji", "__future__"):
                continue
            dists = {ALIASES.get(canonical(d), canonical(d)) for d in mapping.get(top, [])}
            if dists & declared:
                used |= dists & declared
            else:
                missing.setdefault(top, f"{p.relative_to(PROJECT)}:{line}")
    assert missing == {}
    assert declared - used == INDIRECT


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Import safety and runtime home
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_importing_every_module_adds_no_handlers_threads_or_files(tmp_path):
    code = textwrap.dedent("""
        import importlib, json, logging, pkgutil, threading
        import chromadb, duckdb, fastapi, fastmcp, langgraph.graph, pandas, sqlalchemy  # warm third-party imports
        import cji
        skip = {"cji.dashboard"}                       # a Streamlit script: importing it runs the app
        names = sorted(m.name for m in pkgutil.walk_packages(cji.__path__, "cji.") if m.name not in skip)
        handlers, threads = len(logging.getLogger().handlers), threading.active_count()
        for name in names:
            importlib.import_module(name)
        print(json.dumps({"modules": len(names), "handlers": len(logging.getLogger().handlers) - handlers,
                          "threads": threading.active_count() - threads}))
    """)
    out = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=child_env(tmp_path), capture_output=True,
                         text=True, timeout=300, check=False)
    assert out.returncode == 0, out.stderr[-3000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["modules"] > 60
    assert result["handlers"] == 0 and result["threads"] == 0
    files = [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()]
    assert files == []


def test_home_defaults_to_the_working_directory(tmp_path, monkeypatch):
    from cji.settings import load_settings

    monkeypatch.chdir(tmp_path)
    s = load_settings({"CJI_ENV": "test"}, dotenv_path=None)
    assert s.storage.data_dir == tmp_path / "data"
    assert s.storage.reports_dir == tmp_path / "reports"


@pytest.mark.parametrize("relative", [True, False])
def test_cji_home_moves_data_reports_and_dotenv(tmp_path, monkeypatch, relative):
    from cji.settings import load_settings

    home = tmp_path / "home"
    home.mkdir()
    (home / ".env").write_text("CJI_ENV=development\nJOURNEY_NAME=from_home_dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    s = load_settings({"CJI_HOME": "home" if relative else str(home)})
    assert s.storage.data_dir == home / "data"
    assert s.storage.reports_dir == home / "reports"
    assert s.app.journey_name == "from_home_dotenv"
    s = load_settings({"CJI_HOME": str(home), "CJI_ENV": "test", "CJI_DATA_DIR": "elsewhere"}, dotenv_path=None)
    assert s.storage.data_dir == home / "elsewhere"


def test_tracker_js_is_package_data():
    from importlib.resources import files

    assert (files("cji.tracker") / "tracker.js").read_text(encoding="utf-8").strip()


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def script_path(name):
    folder = Path(sysconfig.get_path("scripts"))
    for candidate in (folder / f"{name}.exe", folder / name):
        if candidate.exists():
            return candidate
    pytest.fail(f"console script {name} is not installed in {folder}")


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_console_scripts_work_outside_the_project(script, tmp_path):
    out = subprocess.run([str(script_path(script)), "--help"], cwd=tmp_path, env=child_env(tmp_path),
                         capture_output=True, text=True, timeout=180, check=False)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "usage" in out.stdout.lower()


@pytest.mark.parametrize("command", [["main.py"], ["run_servers.py"], ["generate_diverse.py"],
                                     ["tools/ingest_json.py"], ["tracker/snippet_generator.py"], ["-m", "settings"]])
def test_old_commands_still_work_from_the_project(command, tmp_path):
    out = subprocess.run([sys.executable, *command, "--help"], cwd=PROJECT, env=child_env(tmp_path),
                         capture_output=True, text=True, timeout=180, check=False)
    assert out.returncode == 0, out.stderr[-2000:]
    assert "usage" in out.stdout.lower()


def test_collector_and_dashboard_launchers_point_at_the_package(tmp_path):
    code = "import collector.api as a, cji.collector.api as b; print(a.app is b.app)"
    out = subprocess.run([sys.executable, "-c", code], cwd=PROJECT, env=child_env(tmp_path), capture_output=True,
                         text=True, timeout=180, check=False)
    assert out.returncode == 0 and out.stdout.strip() == "True", out.stderr[-2000:]
    assert 'run_module("cji.dashboard"' in (PROJECT / "dashboard.py").read_text(encoding="utf-8")


def test_settings_check_reports_the_home(tmp_path):
    out = subprocess.run([str(script_path("cji-settings")), "check", "--no-dotenv"], cwd=tmp_path,
                         env=child_env(tmp_path), capture_output=True, text=True, timeout=180, check=False)
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.loads(out.stdout)["home"] == str(tmp_path)


def test_readme_documents_setup_scripts_and_home():
    readme = (PROJECT.parent / "README.md").read_text(encoding="utf-8")
    for text in ("pip install --no-deps -e .", "requirements.lock", "CJI_HOME", *SCRIPTS):
        assert text in readme, text
