import importlib.metadata as md
import pathlib
import subprocess

ROOT = pathlib.Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
PY = r"C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe"
out = ["===== Requires-Python of key distributions"]
for d in ("numpy", "pandas", "pyarrow", "langgraph", "langgraph-checkpoint-sqlite", "chromadb", "streamlit", "fastmcp",
          "fastmcp-slim", "mcp", "fastapi", "pydantic", "duckdb", "sqlalchemy", "plotly", "faker", "httpx",
          "langchain-core", "scipy", "onnxruntime", "pgserver", "mypy", "ruff", "bandit", "pytest"):
    try:
        out.append(f"  {d}=={md.version(d)} requires-python={md.metadata(d).get('Requires-Python')}")
    except md.PackageNotFoundError:
        out.append(f"  {d}: not installed")
out.append("===== ruff: where do the 407 enabled rules come from?")
r = subprocess.run([PY, "-m", "ruff", "check", "--isolated", "--show-settings", "config.py"], cwd=ROOT / "cji_agent",
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
lines = r.stdout.splitlines()
i = next((k for k, l in enumerate(lines) if l.startswith("linter.rules.enabled")), None)
n = 0
if i is not None:
    for l in lines[i + 1:]:
        if l.strip().startswith("]"):
            break
        n += 1
out.append(f"  --isolated (no config files at all): {n} enabled rules")
r = subprocess.run([PY, "-m", "ruff", "check", "--no-cache", "--statistics", "."], cwd=ROOT / "cji_agent",
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
out.append("  current statistics:")
out += ["    " + l for l in r.stdout.splitlines()[-40:]]
r = subprocess.run([PY, "-m", "ruff", "check", "--no-cache", "--statistics", "--target-version", "py312", "."],
                   cwd=ROOT / "cji_agent", capture_output=True, text=True, encoding="utf-8", errors="replace")
out.append("  with --target-version py312:")
out += ["    " + l for l in r.stdout.splitlines()[-6:]]
out.append("===== tracked stray / generated files")
for rel in ("cji_agent/test_output.txt", "cji_agent/test_results.txt", "cji_agent/snippets/api_key.json",
            "cji_agent/snippets/verify_tracker.py", "cji_agent/pytest.ini", "cji_agent/requirements.txt",
            "cji_agent/tracker/tracker.js", "cji_agent/data/events.parquet"):
    t = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--error-unmatch", rel], capture_output=True).returncode == 0
    out.append(f"  {rel}: tracked={t} exists={(ROOT / rel).exists()}")
gi = ROOT / "cji_agent" / ".gitignore"
out.append("===== cji_agent/.gitignore")
out += ["  " + l for l in gi.read_text(encoding="utf-8").splitlines()]
pathlib.Path(r"C:\Users\sovan\.kiro\s11_survey7.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
