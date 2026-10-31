import pathlib
import re
import subprocess

REPO = pathlib.Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
EX = [":!.kiro", ":!graphify-out", ":!refactoring.md", ":!kiro_upgrade_guide.md", ":!kiro_upgrade_prompts.md",
      ":!antigravity_upgrade_prompts.md", ":!.gitignore", ":!cji_agent/tests/test_cleanup.py"]
pats = {
    "test_dummy": r"\btest_dummy\b", "ingest_json(": r"\bingest_json\(", "dashboard2": r"\bdashboard2\b",
    "run logs": r"\b(main_log[0-9]*\.txt|ingest_ga4_log\.txt|parquet_check\.txt|schema_report\.txt)\b",
    "attr-uses-in-tests": r"\b(ing|api|module|mod|rs|ij|j|ws|workers|graph|main)\.(CJI_MODE|DATA_DIR|DUCKDB_PATH|logger|os|duckdb|Any|Depends|JSONResponse|MIN_ADMIN_KEY_LENGTH|sqlite3|SqliteSaver|CHECKPOINTS_DB|Optional|Path|FRICTION_SCORE_THRESHOLD|json|Dict|List)\b",
}
out = []
for k, p in pats.items():
    r = subprocess.run(["git", "-C", str(REPO), "grep", "-n", "-I", "-E", "--untracked", p, "--", ".", *EX], capture_output=True, text=True)
    out.append(f"== {k}\n{r.stdout}")
# validate_collector_settings callers
r = subprocess.run(["git", "-C", str(REPO), "grep", "-n", "--untracked", "validate_collector_settings", "--", "cji_agent"], capture_output=True, text=True)
out.append("== validate_collector_settings\n" + r.stdout)
# do root diagnostics still import? (static: names they import from app modules)
import ast
import importlib
import sys
sys.path.insert(0, str(REPO / "cji_agent"))
for name in ["test_data_server.py", "test_server.py", "test_threads.py", "test_load.py"]:
    tree = ast.parse((REPO / name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and ("mcp_servers" in node.module or "config" in node.module or node.module == "dashboard"):
            mod = node.module.replace("cji_agent.", "")
            if mod == "dashboard":
                out.append(f"{name}: imports dashboard (runs the Streamlit page and connects to the database)")
                continue
            try:
                m = importlib.import_module(mod)
                missing = [a.name for a in node.names if not hasattr(m, a.name)]
                out.append(f"{name}: from {node.module} import {[a.name for a in node.names]} -> missing now: {missing}")
            except Exception as e:  # noqa: BLE001 - survey only
                out.append(f"{name}: import {mod} failed: {type(e).__name__}: {e}")
pathlib.Path(r"C:\Users\sovan\.kiro\s06_refs.txt").write_text("\n".join(out), encoding="utf-8")
