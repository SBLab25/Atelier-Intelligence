"""Spec 11 survey part 3 (read-only except the scratch venv)."""
import importlib.metadata as md
import pathlib
import re
import shutil
import subprocess

ROOT = pathlib.Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
APP = ROOT / "cji_agent"
PY = r"C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
SCRATCH = pathlib.Path(r"C:\Users\sovan\.kiro\s11_scratch")
OUT = pathlib.Path(r"C:\Users\sovan\.kiro\s11_survey4.txt")
SKIP = re.compile(r"[\\/](\.venv|venv|__pycache__|\.mypy_cache|\.pytest_cache|\.ruff_cache|data|reports)([\\/]|$)")
uv = shutil.which("uv")
out = []


def flush():
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")


def section(name):
    out.append(f"\n===== {name}")
    flush()


def run(cmd, timeout=300, **kw):
    out.append(f"  $ {' '.join(map(str, cmd))[:170]}")
    flush()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, **kw)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -9, "", "TIMEOUT"


def grep(rx, files, ctx=0, limit=40):
    n = 0
    for p in files:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if re.search(rx, line):
                for j in range(max(0, i - ctx), min(len(lines), i + ctx + 1)):
                    out.append(f"  {p.relative_to(ROOT)}:{j + 1}: {lines[j].rstrip()[:170]}")
                n += 1
                if n >= limit:
                    return


py = [p for p in APP.rglob("*.py") if not SKIP.search(str(p))]

section("generate_diverse.py, stray files, snippets")
gd = APP / "generate_diverse.py"
out += ["  " + l[:160] for l in gd.read_text(encoding="utf-8").splitlines()[:25]]
grep(r"generate_diverse", py + [ROOT / "README.md"])
grep(r"output_dir|add_argument", [APP / "tracker" / "snippet_generator.py"])

section("settings: APP_ROOT, dotenv, defaults")
grep(r"APP_ROOT|load_dotenv|dotenv_values|\.env\b|_path\(", [APP / "settings" / "load.py", APP / "settings" / "__init__.py",
                                                            APP / "settings" / "__main__.py", APP / "config.py"], limit=60)

section("ROOT / __file__ uses in app code (what they locate)")
grep(r"\bROOT\b|ROOT_DIR|APP_ROOT", [p for p in py if "tests" not in p.parts and p.name != "load.py"], limit=60)

section("tests: how they locate the app (APP_ROOT / source reads / subprocess env)")
grep(r"APP_ROOT\s*=|PYTHONPATH|sys\.executable|read_text\(encoding=.utf-8.\)\s*$|cwd=APP_ROOT", [p for p in py if "tests" in p.parts], limit=80)
out.append("  tests reading app source files (APP_ROOT / ...):")
grep(r"APP_ROOT\s*/\s*\"", [p for p in py if "tests" in p.parts], limit=80)

section("import X.sub forms and dynamic imports of first-party modules")
first = r"(agents|collector|config|domain|graph|guardrails|integrations|mcp_servers|reporting|repositories|settings|state|tools|workflow|main|run_servers|dashboard|tracker)"
grep(rf"^\s*import\s+{first}\.\w+", py, limit=40)
grep(rf"import_module\(|__import__\(|importlib\.reload|patch\([\"']{first}\.|setattr\([\"']{first}\.", py, limit=60)

section("pytest import mode / rootdir / conftest sys.path")
out += ["  " + l for l in (APP / "tests" / "conftest.py").read_text(encoding="utf-8").splitlines()[:40]]
grep(r"sys\.path|conftest", [APP / "tests" / "test_cleanup.py"], ctx=2)

section("git: tracked files under cji_agent by top-level entry")
code, so, se = run(["git", "-C", str(ROOT), "ls-files", "cji_agent"])
counts = {}
for line in so.splitlines():
    parts = line.split("/")
    key = parts[1] if len(parts) > 2 else parts[-1]
    counts[key] = counts.get(key, 0) + 1
out.append("  " + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items())))
code, so, se = run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"])
out.append(f"  modified tracked files now: {len(so.splitlines())}")
flush()
