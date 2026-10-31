import importlib.metadata as md
import pathlib
import re

ROOT = pathlib.Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
APP = ROOT / "cji_agent"
OUT = pathlib.Path(r"C:\Users\sovan\.kiro\s11_survey6.txt")
out = []


def grep(rx, files, ctx=0, limit=40):
    n = 0
    for p in files:
        if not p.exists():
            out.append(f"  (missing {p})")
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if re.search(rx, line):
                for j in range(max(0, i - ctx), min(len(lines), i + ctx + 1)):
                    out.append(f"  {p.relative_to(ROOT)}:{j + 1}: {lines[j].rstrip()[:170]}")
                n += 1
                if n >= limit:
                    return


out.append("===== main.py structure")
grep(r"^def |^async def |^if __name__|sys\.exit|raise SystemExit|argparse\.ArgumentParser|^[A-Z_]+ *=", [APP / "main.py"], limit=60)
out.append("===== run_servers.py structure")
grep(r"^def |^if __name__|module_name|SERVERS|mcp_servers\.", [APP / "run_servers.py"], limit=40)
out.append("===== settings/services.py module strings")
grep(r"mcp_servers|collector|module", [APP / "settings" / "services.py"], limit=30)
out.append("===== settings/__main__.py")
grep(r"^def |^if __name__|import", [APP / "settings" / "__main__.py"], limit=20)
out.append("===== pytest-asyncio / pytest-cov usage")
tests = sorted((APP / "tests").glob("*.py"))
grep(r"pytest\.mark\.asyncio|asyncio_mode|pytest_asyncio|--cov|anyio", tests + [APP / "pytest.ini"], limit=20)
out.append("===== string module paths in tests and app (patch/import_module/-m)")
grep(r"""["'](agents|collector|config|domain|graph|guardrails|integrations|mcp_servers|reporting|repositories|settings|state|tools|workflow|main|run_servers|dashboard|tracker)(\.[A-Za-z_]+)+["']""",
     sorted(p for p in APP.rglob("*.py") if ".venv" not in p.parts and "__pycache__" not in p.parts), limit=60)
out.append("===== import-time side effects (module level calls)")
for p in sorted(APP.rglob("*.py")):
    if any(x in p.parts for x in (".venv", "__pycache__", "tests")) or p.name == "dashboard.py":
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if re.match(r"(logging\.basicConfig|load_dotenv\(|print\(|os\.makedirs|\w+\.mkdir\(|os\.environ\[.*\]\s*=|warnings\.filterwarnings|sys\.exit)", line):
            out.append(f"  {p.relative_to(APP)}:{i}: {line.strip()[:150]}")
out.append("===== checkpoint APIs used by workflow (CVE exposure)")
grep(r"\.alist\(|\.list\(|filter=|aget_tuple|AsyncSqliteStore|SqliteStore|BaseStore|cache=|serde|JsonPlusSerializer",
     sorted((APP / "workflow").glob("*.py")) + [APP / "graph.py"], limit=30)
out.append("===== chromadb client type")
grep(r"chromadb\.\w+Client|HttpClient|PersistentClient", sorted((APP / "mcp_servers").glob("*.py")), limit=10)
out.append("===== who requires filelock / langchain / langchain-text-splitters / huggingface-hub / torch")
for dist in md.distributions():
    for r in dist.requires or []:
        name = re.split(r"[ ;<>=!~\[(]", r, 1)[0].lower().replace("_", "-")
        if name in ("filelock", "langchain", "langchain-text-splitters", "huggingface-hub", "torch", "transformers",
                    "tokenizers", "langgraph-checkpoint", "openai", "scikit-learn", "scipy") and "extra ==" not in r:
            out.append(f"  {dist.metadata['Name']} -> {r}")
out.append("===== old gate helper scripts: imports and sys.path")
for rel in ("02-p0-security/evidence/scripts/golden.py", "02-p0-security/evidence/scripts/compare_static.py",
            "07-collector/evidence/scripts/collector_smoke.py", "08-ai-gateway/evidence/scripts/audit_check.py",
            "09-durable-workflow/evidence/scripts/audit_workflow_check.py"):
    p = ROOT / ".kiro" / "specs" / rel
    grep(r"sys\.path|^from |^import |APP\b|cwd=", [p], limit=15)
out.append("===== README env var section and test_docs checks")
grep(r"^## |CJI_DATA_DIR|CJI_REPORTS_DIR|\.env", [ROOT / "README.md"], limit=40)
grep(r"def test_|REPO_ROOT|tokens|re\.findall", [APP / "tests" / "test_docs.py"], limit=30)
OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
