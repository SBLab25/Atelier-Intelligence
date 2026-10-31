"""Spec 14 survey part 2 -> s14_survey2.txt (compact)."""
import ast
import json
from pathlib import Path

ROOT = Path(r"C:\Users\sovan\Documents\Projects\TCS-CJI")
APP = ROOT / "cji_agent"
SRC = APP / "src" / "cji"
out = []

# 1. API package: files, functions, route decorators
for p in sorted((SRC / "api").rglob("*.py")):
    tree = ast.parse(p.read_text(encoding="utf-8"))
    out.append(f"== {p.relative_to(SRC).as_posix()} ({len(p.read_text(encoding='utf-8').splitlines())} lines)")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            decos = []
            for d in node.decorator_list:
                try:
                    decos.append(ast.unparse(d)[:90])
                except Exception:
                    pass
            out.append(f"  {node.lineno}: {type(node).__name__[:5]} {node.name} {' | '.join(decos)}")

# 2. last_run.json shape
lr = json.loads((APP / "data" / "last_run.json").read_text(encoding="utf-8"))
out.append("== last_run.json keys: " + ", ".join(f"{k}:{type(v).__name__}" for k, v in lr.items()))
for k in ("friction_scores", "insights", "prioritized_fixes"):
    v = lr.get(k) or []
    if v:
        out.append(f"  {k}[0] keys: {sorted(v[0].keys())} n={len(v)}")
out.append(f"  narrative chars={len(lr.get('narrative') or '')}")

# 3. grep provenance fields in agents/ and servers
for p in sorted(SRC.rglob("*.py")):
    rel = p.relative_to(SRC).as_posix()
    if rel.startswith("api/") or "dashboard" in rel:
        continue
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if any(t in s for t in ('"fallback"', "narrative_source", "narrative_model", '"confidence"', '"model":')):
            out.append(f"{rel}:{i}: {s[:150]}")

# 4. run index columns
idx = SRC / "workflow" / "index.py"
for i, line in enumerate(idx.read_text(encoding="utf-8").splitlines(), 1):
    if "CREATE TABLE" in line or "def " in line:
        out.append(f"workflow/index.py:{i}: {line.strip()[:200]}")

# 5. domain/ and repositories listing
for d in ("domain", "repositories", "analytics", "services"):
    dd = SRC / d
    if dd.exists():
        out.append(f"== {d}: " + ", ".join(sorted(x.name for x in dd.glob('*.py'))))

# 6. openapi tags/paths summary
spec = json.loads((APP / "openapi" / "v1.json").read_text(encoding="utf-8"))
for path, ops in spec["paths"].items():
    for m, op in ops.items():
        out.append(f"OP {m.upper()} {path} -> {sorted((op.get('responses') or {}).keys())}")
out.append("SCHEMAS: " + ", ".join(sorted(spec.get("components", {}).get("schemas", {}).keys())))

(Path(r"C:\Users\sovan\.kiro") / "s14_survey2.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
