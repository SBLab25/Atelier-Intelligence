"""Spec 14 survey: what Streamlit and the CLI do today, what /api/v1 and the frontend cover, and the gaps."""
import ast
import json
import re
from pathlib import Path

REPO = Path(r"C:\Users\sovan\Documents\Projects\TCS-CJI")
SRC = REPO / "cji_agent" / "src" / "cji"
out = []


def section(title):
    out.append(f"\n== {title}")


# ── Streamlit dashboard ────────────────────────────────────────────────────────
dash = (SRC / "dashboard.py").read_text(encoding="utf-8")
tree = ast.parse(dash)
section("dashboard.py functions (name, line, decorators)")
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        decos = [ast.unparse(d) for d in node.decorator_list]
        doc = (ast.get_docstring(node) or "").splitlines()[0:1]
        out.append(f"  {node.lineno:5} {node.name} {decos} {doc}")
section("dashboard.py widgets (st.<widget> counts)")
widgets = {}
for m in re.finditer(r"\bst\.(sidebar\.)?(\w+)\(", dash):
    widgets[m.group(2)] = widgets.get(m.group(2), 0) + 1
out.append("  " + ", ".join(f"{k}={v}" for k, v in sorted(widgets.items(), key=lambda kv: -kv[1])))
section("dashboard.py headers/subheaders/tabs/buttons/uploaders (text)")
for m in re.finditer(r"st\.(?:sidebar\.)?(title|header|subheader|tabs|button|file_uploader|radio|selectbox|download_button|"
                     r"expander|markdown)\(\s*(f?\"[^\"]{0,90}|f?'[^']{0,90}|\[[^\]]{0,160})", dash):
    line = dash.count("\n", 0, m.start()) + 1
    if m.group(1) == "markdown" and not m.group(2).lstrip("f\"'").startswith("#"):
        continue
    out.append(f"  {line:5} {m.group(1)}: {m.group(2)[:150]}")
section("dashboard.py SQL / data sources")
for m in re.finditer(r"(SELECT[\s\S]{0,160}?FROM\s+\w+|read_parquet\([^)]*\)|last_run\.json|subprocess\.run\(\s*\[[^\]]{0,200}\]"
                     r"|REPORTS_DIR|get_settings\(\)\.\w+)", dash):
    line = dash.count("\n", 0, m.start()) + 1
    out.append(f"  {line:5} {' '.join(m.group(1).split())[:180]}")

# ── CLI ────────────────────────────────────────────────────────────────────────
main = (SRC / "main.py").read_text(encoding="utf-8")
section("CLI flags (main.py)")
for m in re.finditer(r'add_argument\(\s*"(--[\w-]+)"(.*?)\)\n', main, re.S):
    help_ = re.search(r'help\s*=\s*(\(?\s*"[^"]*"(?:\s*"[^"]*")*)', m.group(2))
    out.append(f"  {m.group(1)}: {' '.join((help_.group(1) if help_ else '').split())[:160]}")
section("CLI ingest path")
for m in re.finditer(r".*(ingest|pending_files|detect_schema|apply_mapping|confidence).*", main):
    out.append(f"  {main.count(chr(10), 0, m.start()) + 1:5} {m.group(0).strip()[:160]}")

# ── Workflow / state / insights / provenance ──────────────────────────────────
runtime = (SRC / "workflow" / "runtime.py").read_text(encoding="utf-8")
section("Workflow public methods")
for m in re.finditer(r"\n    (async )?def (\w+)\(self[^)]*\)[^:]*:", runtime):
    if not m.group(2).startswith("_"):
        out.append(f"  {m.group(2)}: {' '.join(m.group(0).split())[:200]}")
init = re.search(r"def initial_state\([\s\S]*?\) -> [^:]+:", runtime)
out.append("  initial_state: " + " ".join(init.group(0).split())[:500] if init else "  initial_state: ?")
state_py = SRC / "state.py"
if state_py.exists():
    st = state_py.read_text(encoding="utf-8")
    section("state.py TypedDicts (fields)")
    for m in re.finditer(r"class (\w+)\(TypedDict[^)]*\):([\s\S]*?)(?=\nclass |\Z)", st):
        fields = re.findall(r"^\s{4}(\w+)\s*:", m.group(2), re.M)
        out.append(f"  {m.group(1)}: {fields}")
section("insight fields produced (insight_server / workers)")
for f in [SRC / "mcp_servers" / "insight_server.py", SRC / "agents" / "workers.py"]:
    if f.exists():
        t = f.read_text(encoding="utf-8")
        keys = sorted(set(re.findall(r'"(insight_id|step_id|title|root_cause|category|evidence|suggested_fix|fix_effort|'
                                     r'priority|priority_score|score|source|provider|model|generated_by|fallback|'
                                     r'llm_used|confidence|prompt_version|created_at)"', t)))
        out.append(f"  {f.name}: {keys}")
        for m in re.finditer(r".*(fallback|rule[_-]based|provider|model).*", t):
            if len(out) > 0 and "def " in m.group(0) or "source" in m.group(0):
                out.append(f"    {t.count(chr(10), 0, m.start()) + 1:5} {m.group(0).strip()[:150]}")
section("audit record kinds and fields (integrations/audit.py)")
audit = SRC / "integrations" / "audit.py"
if audit.exists():
    t = audit.read_text(encoding="utf-8")
    out.append("  kinds: " + ", ".join(sorted(set(re.findall(r'"kind":\s*"(\w+)"', t)))))
    out.append("  fields: " + ", ".join(sorted(set(re.findall(r'"(\w+)":', t)))[:80]))
audit_dir = REPO / "cji_agent" / "data" / "audit"
if audit_dir.exists():
    for f in sorted(audit_dir.glob("*.jsonl")):
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        sample = json.loads(lines[-1]) if lines else {}
        out.append(f"  {f.name}: {len(lines)} records; keys of last: {sorted(sample)}")

# ── Ingestion ──────────────────────────────────────────────────────────────────
section("ingestion: MCP tools and worker")
ing = SRC / "mcp_servers" / "ingestion_intelligence_server.py"
t = ing.read_text(encoding="utf-8")
for m in re.finditer(r"@mcp\.tool\(\)\s*\n(async )?def (\w+)\(([^)]*)\)", t):
    out.append(f"  tool {m.group(2)}({' '.join(m.group(3).split())[:160]})")
wk = SRC / "agents" / "ingestion_worker.py"
if wk.exists():
    t = wk.read_text(encoding="utf-8")
    out.append("  ingestion_worker state keys: " + ", ".join(sorted(set(re.findall(r'state\[?\.?get\(\s*"(\w+)"|state\["(\w+)"\]', t)
                                                                              and [a or b for a, b in re.findall(r'state\.get\(\s*"(\w+)"|state\["(\w+)"\]', t)]))))
    out.append("  ingestion result keys: " + ", ".join(sorted(set(re.findall(r'"(ingestion_\w+|records_\w+|confidence\w*|'
                                                                          r'flagged\w*|review\w*|mapping\w*|ready_to_ingest)"', t)))))
tools_ing = SRC / "tools" / "ingest_json.py"
if tools_ing.exists():
    t = tools_ing.read_text(encoding="utf-8")
    out.append("  cji-ingest-json flags: " + ", ".join(re.findall(r'add_argument\(\s*"(--[\w-]+)"', t)))

# ── API + frontend coverage ────────────────────────────────────────────────────
section("API operations (openapi/v1.json)")
doc = json.loads((REPO / "cji_agent" / "openapi" / "v1.json").read_text(encoding="utf-8"))
for path, item in doc["paths"].items():
    for method, op in item.items():
        params = [p["name"] for p in op.get("parameters", [])]
        out.append(f"  {method.upper():5} {path} params={params}")
section("frontend pages and loaders")
fe = REPO / "frontend" / "src"
for p in sorted(fe.rglob("page.tsx")) + sorted(fe.rglob("route.ts")):
    out.append("  " + str(p.relative_to(fe)).replace("\\", "/"))
loaders = (fe / "lib" / "api" / "loaders.ts").read_text(encoding="utf-8")
out.append("  loaders: " + ", ".join(re.findall(r"export function (\w+)", loaders)))
section("tests")
tests = REPO / "cji_agent" / "tests"
out.append(f"  python test files: {len(list(tests.glob('test_*.py')))}; dashboard tests: "
           f"{[p.name for p in tests.glob('test_dashboard*.py')]}")
out.append(f"  frontend test files: {[str(p.relative_to(REPO / 'frontend')) for p in (REPO / 'frontend' / 'tests').rglob('*.test.ts*')]}")

Path(__file__).with_suffix(".txt").write_text("\n".join(out) + "\n", encoding="utf-8")
