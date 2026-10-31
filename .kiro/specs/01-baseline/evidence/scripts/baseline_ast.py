"""Syntax-only check: parse every .py file under cji_agent/ (excluding .venv) with ast.
Writes no bytecode and imports nothing from the project."""
import ast, pathlib, sys

root = pathlib.Path(r"C:\Users\sovan\Documents\Projects\TCS-CJI")
ok, bad = 0, []
for p in sorted(root.rglob("*.py")):
    parts = set(p.parts)
    if ".venv" in parts or ".git" in parts or "node_modules" in parts:
        continue
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        ok += 1
    except SyntaxError as e:
        bad.append(f"{p.relative_to(root)}:{e.lineno}: {e.msg}")
    except UnicodeDecodeError as e:
        bad.append(f"{p.relative_to(root)}: not UTF-8 ({e.reason})")
print(f"interpreter={sys.version.split()[0]} parsed_ok={ok} failed={len(bad)}")
for b in bad:
    print("  FAIL", b)
