"""Spec 11 survey (read-only): layout, config files, path hacks, entry points, dependencies, Python features."""
import collections
import importlib.metadata as md
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
APP = ROOT / "cji_agent"
SKIP = re.compile(r"[\\/](\.venv|venv|node_modules|__pycache__|\.mypy_cache|\.pytest_cache|\.ruff_cache|chroma\w*|data|reports)([\\/]|$)")
out = []


def section(name):
    out.append(f"\n===== {name}")


section("top level of cji_agent/")
for p in sorted(APP.iterdir()):
    if p.name.startswith(".") and p.name not in (".env.example", ".gitignore"):
        continue
    kind = "pkg" if (p / "__init__.py").exists() else ("dir" if p.is_dir() else "file")
    n = len(list(p.rglob("*.py"))) if p.is_dir() else ""
    out.append(f"  {kind:4} {p.name} {n}")

section("packaging / tool config files")
for base in (ROOT, APP):
    for name in ("pyproject.toml", "setup.py", "setup.cfg", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini",
                 "pytest.ini", "tox.ini", "Makefile", "requirements.txt", "requirements-dev.txt", "uv.lock",
                 "constraints.txt", "MANIFEST.in", ".python-version", "conftest.py", ".bandit"):
        p = base / name
        if p.exists():
            out.append(f"  {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")
for name in ("pyproject.toml", "requirements.txt", "requirements-dev.txt", "pytest.ini", "mypy.ini", "ruff.toml",
             "setup.cfg", ".python-version"):
    for base in (ROOT, APP):
        p = base / name
        if p.exists():
            out.append(f"----- {p.relative_to(ROOT)}")
            out += ["  " + line for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[:80]]

pyfiles = [p for p in APP.rglob("*.py") if not SKIP.search(str(p))]
section(f"python files: {len(pyfiles)}")

section("sys.path / PYTHONPATH / chdir hacks")
pat = re.compile(r"sys\.path\.(insert|append)|PYTHONPATH|os\.chdir|site\.addsitedir|importlib\.util\.spec_from_file")
for p in sorted(pyfiles):
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if pat.search(line):
            out.append(f"  {p.relative_to(APP)}:{i}: {line.strip()[:150]}")

section("__file__-based paths (APP_ROOT etc.) outside tests")
pat = re.compile(r"__file__")
for p in sorted(pyfiles):
    if "tests" in p.parts:
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if pat.search(line):
            out.append(f"  {p.relative_to(APP)}:{i}: {line.strip()[:150]}")

section("__main__ blocks and argparse (CLI candidates)")
for p in sorted(pyfiles):
    t = p.read_text(encoding="utf-8", errors="replace")
    if "__name__ == \"__main__\"" in t or "__name__ == '__main__'" in t:
        out.append(f"  {p.relative_to(APP)} argparse={'argparse' in t}")

section("subprocess / module launches / streamlit / uvicorn")
pat = re.compile(r"\"-m\"|'-m'|streamlit|uvicorn\.run|sys\.executable|Popen|subprocess\.run")
for p in sorted(pyfiles):
    if "tests" in p.parts:
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if pat.search(line):
            out.append(f"  {p.relative_to(APP)}:{i}: {line.strip()[:160]}")

section("first-party top-level import names")
first_party = {p.stem for p in APP.glob("*.py")} | {p.name for p in APP.iterdir() if (p / "__init__.py").exists()}
used = collections.Counter()
for p in pyfiles:
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*(?:from|import)\s+([A-Za-z_]\w*)", line)
        if m and m.group(1) in first_party:
            used[m.group(1)] += 1
out.append("  " + ", ".join(f"{k}:{v}" for k, v in sorted(used.items())))
out.append(f"  first-party names that also exist on PyPI-ish common names: "
           f"{sorted(n for n in first_party if n in {'config', 'state', 'graph', 'settings', 'domain', 'tools', 'agents', 'collector', 'tracker', 'integrations', 'repositories', 'guardrails', 'workflow', 'reporting', 'main', 'dashboard'})}")

section("non-python runtime assets referenced by code")
pat = re.compile(r"""["'][^"']*\.(parquet|json|js|html|csv|ndjson|yaml|yml|toml|sql|txt)["']""")
for p in sorted(pyfiles):
    if "tests" in p.parts:
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if pat.search(line) and ("Path" in line or "open(" in line or "/" in line or "DIR" in line):
            out.append(f"  {p.relative_to(APP)}:{i}: {line.strip()[:160]}")
for d in ("data", "tracker", "snippets", "static", "templates", "collector"):
    q = APP / d
    if q.exists():
        files = [f for f in q.rglob("*") if f.is_file() and f.suffix not in (".py", ".pyc")]
        out.append(f"  {d}/ non-py files: {len(files)}: {[str(f.relative_to(APP)) for f in files[:12]]}")

section("python feature use (minimum version hints)")
feats = {"match statement": r"^\s*match\s+\w.*:\s*$", "ExceptionGroup/except*": r"ExceptionGroup|except\*",
         "typing.Self": r"\bSelf\b", "tomllib": r"tomllib", "StrEnum": r"StrEnum", "datetime.UTC": r"datetime\.UTC\b",
         "X | Y types": r":\s*\w+\s*\|\s*None", "type statement": r"^\s*type\s+\w+\s*=", "TaskGroup": r"TaskGroup",
         "asyncio.timeout": r"asyncio\.timeout\(", "generic [T] syntax": r"def \w+\[\w+", "override": r"@override"}
for name, rx in feats.items():
    hits = [str(p.relative_to(APP)) for p in pyfiles if re.search(rx, p.read_text(encoding="utf-8", errors="replace"), re.M)]
    out.append(f"  {name}: {len(hits)} {hits[:4]}")

section("interpreter and tools")
out.append(f"  python {sys.version.split()[0]} at {sys.executable}")
for tool in ("uv", "pip", "pipx", "git"):
    out.append(f"  {tool}: {shutil.which(tool)}")
uv = shutil.which("uv")
if uv:
    for args in (["--version"], ["cache", "dir"]):
        r = subprocess.run([uv, *args], capture_output=True, text=True)
        out.append(f"  uv {' '.join(args)}: {(r.stdout or r.stderr).strip()}")

section("installed distributions in the baseline venv (name==version)")
dists = sorted({(d.metadata["Name"] or "").lower(): d.version for d in md.distributions()}.items())
out.append(f"  count: {len(dists)}")
out += [f"  {n}=={v}" for n, v in dists]

pathlib.Path(r"C:\Users\sovan\.kiro\s11_survey.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
