"""Spec 12 survey: API surface, auth, data sources the /api/v1 contract would expose."""
import ast
import pathlib
import re

ROOT = pathlib.Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
APP = ROOT / "cji_agent"
SRC = APP / "src" / "cji"
out = []


def sec(t):
    out.append(f"\n===== {t}")


sec("collector routes (decorators)")
for p in sorted((SRC / "collector").glob("*.py")):
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if re.match(r"\s*@app\.(get|post|put|delete|patch|middleware|exception_handler|on_event)", line):
            out.append(f"  {p.name}:{i}: {line.strip()}")

sec("HTTPException / JSONResponse status codes in collector")
for p in sorted((SRC / "collector").glob("*.py")):
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"HTTPException\(|JSONResponse\(|status_code=", line):
            out.append(f"  {p.name}:{i}: {line.strip()[:150]}")

sec("public functions/classes per module (repositories, workflow, reporting, domain, settings.roles, collector)")
for sub in ("repositories", "workflow", "reporting", "domain", "collector"):
    for p in sorted((SRC / sub).glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        names = []
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_"):
                args = [a.arg for a in n.args.args]
                names.append(f"def {n.name}({', '.join(args)})")
            elif isinstance(n, ast.ClassDef) and not n.name.startswith("_"):
                methods = [m.name for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and not m.name.startswith("_")]
                names.append(f"class {n.name}: {methods}")
        out.append(f"  {sub}/{p.name}: " + "; ".join(names))

sec("settings roles / services (frontend, cors, auth)")
for f in ("settings/roles.py", "settings/services.py", "settings/model.py"):
    for i, line in enumerate((SRC / f).read_text(encoding="utf-8").splitlines(), 1):
        if re.search(r"frontend|cors|admin|auth|ROLE|def |class ", line, re.I):
            out.append(f"  {f}:{i}: {line.strip()[:150]}")

sec("dashboard data access (SQL tables, files, subprocess)")
dash = (SRC / "dashboard.py").read_text(encoding="utf-8").splitlines()
for i, line in enumerate(dash, 1):
    if re.search(r"FROM \w+|read_sql|last_run|LAST_RUN|REPORTS_DIR|subprocess|requests\.|\.glob\(|def load_|@st\.cache", line):
        out.append(f"  dashboard.py:{i}: {line.strip()[:150]}")

sec("main.py: workflow calls")
for i, line in enumerate((SRC / "main.py").read_text(encoding="utf-8").splitlines(), 1):
    if re.search(r"workflow\.|Workflow\(|write_last_run|initial_state", line):
        out.append(f"  main.py:{i}: {line.strip()[:150]}")

sec("insight storage (chroma) functions")
for i, line in enumerate((SRC / "mcp_servers" / "insight_server.py").read_text(encoding="utf-8").splitlines(), 1):
    if re.search(r"^@mcp|^def |^async def |collection\.(add|upsert|get|query)", line):
        out.append(f"  insight_server.py:{i}: {line.strip()[:150]}")

sec("tests touching the collector app / TestClient")
for p in sorted((APP / "tests").glob("*.py")):
    t = p.read_text(encoding="utf-8")
    n = len(re.findall(r"TestClient\(", t))
    if n:
        out.append(f"  {p.name}: TestClient x{n}")

sec("frontend directory / Next.js presence")
for cand in ("frontend", "web", "cji_frontend", "ui", "app"):
    for base in (ROOT, APP):
        if (base / cand).exists():
            out.append(f"  exists: {(base / cand).relative_to(ROOT)}")
for pj in ROOT.rglob("package.json"):
    if "node_modules" not in pj.parts:
        out.append(f"  package.json: {pj.relative_to(ROOT)}")

sec("installed versions")
import importlib.metadata as md  # noqa: E402
for d in ("fastapi", "starlette", "pydantic", "httpx", "uvicorn", "sqlalchemy", "openapi-spec-validator",
          "jsonschema", "schemathesis", "hypothesis", "pgserver"):
    try:
        out.append(f"  {d}=={md.version(d)}")
    except md.PackageNotFoundError:
        out.append(f"  {d}: not installed")

sec("kiro_upgrade_guide.md rows mentioning API / frontend / Spec 12")
for name in ("kiro_upgrade_guide.md", "kiro_upgrade_prompts.md"):
    lines = (ROOT / name).read_text(encoding="utf-8", errors="replace").splitlines()
    for i, line in enumerate(lines, 1):
        if re.search(r"/api/v1|Next\.js|frontend|\b12\b.*API|API contract|Prompt 11|Prompt 12", line):
            out.append(f"  {name}:{i}: {line.strip()[:200]}")

pathlib.Path(r"C:\Users\sovan\.kiro\s12_survey.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("ok", len(out))
