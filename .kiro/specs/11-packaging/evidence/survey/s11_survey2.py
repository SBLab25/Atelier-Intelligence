"""Spec 11 survey part 2 (read-only except a scratch venv under C:\\Users\\sovan\\.kiro\\s11_scratch)."""
import ast
import importlib.metadata as md
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
APP = ROOT / "cji_agent"
PY = r"C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
SCRATCH = pathlib.Path(r"C:\Users\sovan\.kiro\s11_scratch")
SKIP = re.compile(r"[\\/](\.venv|venv|__pycache__|\.mypy_cache|\.pytest_cache|\.ruff_cache|data|reports)([\\/]|$)")
out = []


OUTFILE = pathlib.Path(r"C:\Users\sovan\.kiro\s11_survey2.txt")


def section(name):
    out.append(f"\n===== {name}")
    OUTFILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def run(cmd, **kw):
    out.append(f"  $ {' '.join(map(str, cmd))[:160]}")
    OUTFILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, **kw)
    return r.returncode, (r.stdout + r.stderr).strip()


section("README commands (lines with python / streamlit / pip / uv / cji)")
for i, line in enumerate((ROOT / "README.md").read_text(encoding="utf-8").splitlines(), 1):
    s = line.strip()
    if re.match(r"^(python|py |streamlit|pip|uv |cji|\.\\|source|cd |pytest|ruff|mypy)", s):
        out.append(f"  {i}: {s[:170]}")
docs = ROOT / "docs"
if docs.exists():
    out.append(f"  docs/: {[p.name for p in docs.iterdir()]}")

section("ruff / mypy configuration actually in effect")
for p in (pathlib.Path(os.environ.get("APPDATA", "")) / "ruff", pathlib.Path.home() / ".config" / "ruff",
          pathlib.Path(os.environ.get("APPDATA", "")) / "mypy", pathlib.Path.home() / ".config" / "mypy"):
    if p.exists():
        out.append(f"  {p}: {[q.name for q in p.iterdir()]}")
for name in ("pyproject.toml", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini", "setup.cfg"):
    for base in (ROOT.parent, ROOT.parent.parent, pathlib.Path.home()):
        if (base / name).exists():
            out.append(f"  found {base / name}")
code, txt = run([PY, "-m", "ruff", "check", "--show-settings", "config.py"], cwd=APP)
cfg = [l for l in txt.splitlines() if re.search(r"Settings path|^linter\.rules\.enabled|line-length|target_version|Resolved settings for", l)]
out += ["  ruff: " + l.strip()[:200] for l in cfg[:8]]
m = re.search(r"linter\.rules\.enabled = \[(.*?)\]", txt, re.S)
if m:
    rules = sorted({re.sub(r"\s*\(.*", "", r.strip().strip(",")) for r in m.group(1).splitlines() if r.strip()})
    prefixes = sorted({re.match(r"[A-Z]+", r).group(0) for r in rules if re.match(r"[A-Z]+", r)})
    out.append(f"  ruff enabled rules: {len(rules)}; prefixes: {prefixes}")
code, txt = run([PY, "-m", "mypy", "--version"], cwd=APP)
out.append(f"  mypy: {txt}")
for tool in ("ruff", "mypy", "bandit", "pytest", "pip", "setuptools", "wheel", "hatchling", "build", "pip-tools",
             "pytest-asyncio", "pytest-cov", "coverage"):
    try:
        out.append(f"  {tool}=={md.version(tool)}")
    except md.PackageNotFoundError:
        out.append(f"  {tool}: not installed")

section("uv pythons and cache")
uv = shutil.which("uv")
code, txt = run([uv, "python", "list", "--only-installed"])
out += ["  " + l for l in txt.splitlines()[:12]]

section("third-party imports in app code vs declared requirements")
stdlib = set(sys.stdlib_module_names)
first = {p.stem for p in APP.glob("*.py")} | {p.name for p in APP.iterdir() if p.is_dir()}
imports = {}
for p in APP.rglob("*.py"):
    if SKIP.search(str(p)):
        continue
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module.split(".")[0]]
        for n in names:
            if n not in stdlib and n not in first and n != "__future__":
                imports.setdefault(n, set()).add(("tests" if "tests" in p.parts else "app"))
pkg_to_dist = md.packages_distributions()
declared = set()
for f in ("requirements.txt", "requirements-dev.txt"):
    for line in (APP / f).read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Za-z0-9_.\-]+)", line.split("#")[0])
        if m:
            declared.add(m.group(1).lower().replace("_", "-"))
for n in sorted(imports):
    dists = [d.lower().replace("_", "-") for d in pkg_to_dist.get(n, [])]
    flag = "declared" if any(d in declared for d in dists) else "NOT DECLARED"
    out.append(f"  {n:22} -> {dists} [{', '.join(sorted(imports[n]))}] {flag}")
imported_dists = {d.lower().replace("_", "-") for n in imports for d in pkg_to_dist.get(n, [])}
out.append(f"  declared but never imported: {sorted(d for d in declared if d not in imported_dists)}")

section("declared requirement -> installed version")
for d in sorted(declared):
    try:
        out.append(f"  {d}=={md.version(d)}")
    except md.PackageNotFoundError:
        out.append(f"  {d}: NOT INSTALLED")

section("string references to first-party module paths (rename scale)")
modref = re.compile(r"""["']((?:agents|collector|config|domain|graph|guardrails|integrations|mcp_servers|reporting|repositories|settings|state|tools|workflow|main|run_servers|dashboard|tracker)(?:\.[a-z_]+)+)["']""")
count = 0
files = set()
for p in APP.rglob("*.py"):
    if SKIP.search(str(p)):
        continue
    for line in p.read_text(encoding="utf-8").splitlines():
        for m in modref.finditer(line):
            count += 1
            files.add(str(p.relative_to(APP)))
out.append(f"  {count} string references in {len(files)} files: {sorted(files)[:20]}")
imp = 0
for p in APP.rglob("*.py"):
    if SKIP.search(str(p)):
        continue
    for line in p.read_text(encoding="utf-8").splitlines():
        if re.match(r"\s*(from|import)\s+(agents|collector|config|domain|graph|guardrails|integrations|mcp_servers|reporting|repositories|settings|state|tools|workflow|main|run_servers|dashboard|tracker)\b", line):
            imp += 1
out.append(f"  first-party import lines: {imp}")

section("data files")
for p in sorted((APP / "data").glob("*")):
    if p.is_file():
        out.append(f"  data/{p.name} {p.stat().st_size} bytes tracked={run(['git', '-C', str(ROOT), 'ls-files', '--error-unmatch', str(p)])[0] == 0}")
out.append(f"  tracker/tracker.js {(APP / 'tracker' / 'tracker.js').stat().st_size} bytes")
out.append(f"  stray files: {[p.name for p in APP.glob('test_*.txt')]}")

section("offline install feasibility (scratch venv)")
if SCRATCH.exists():
    shutil.rmtree(SCRATCH)
code, txt = run([uv, "venv", str(SCRATCH / "venv"), "--python", "3.12", "--offline"])
out.append(f"  uv venv: {code} {txt[-300:]}")
freeze = SCRATCH / "freeze.txt"
code, txt = run([uv, "pip", "freeze", "--python", PY])
freeze.write_text(txt + "\n", encoding="utf-8")
out.append(f"  baseline freeze lines: {len(txt.splitlines())}")
code, txt = run([uv, "pip", "install", "--dry-run", "--offline", "--python", str(SCRATCH / "venv" / "Scripts" / "python.exe"),
                 "-r", str(freeze)])
out.append(f"  dry-run offline install of the baseline freeze: exit {code}")
out += ["    " + l for l in txt.splitlines()[-15:]]
code, txt = run([uv, "pip", "install", "--dry-run", "--offline", "--python", str(SCRATCH / "venv" / "Scripts" / "python.exe"),
                 "setuptools>=69", "wheel", "hatchling"])
out.append(f"  dry-run offline build backends: exit {code}")
out += ["    " + l for l in txt.splitlines()[-8:]]

pathlib.Path(r"C:\Users\sovan\.kiro\s11_survey2.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
