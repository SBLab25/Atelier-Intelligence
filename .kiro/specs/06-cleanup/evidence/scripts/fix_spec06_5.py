"""
Spec 06 follow-up edit 5: the boundary marker. BLE001 is not enabled in this ruff
configuration, so `# noqa: BLE001 - ...` is reported as an unused noqa (RUF100) and made
two files lint-worse. Boundaries are marked `# broad-except: <reason>` instead; the AST
policy test checks that marker.
"""
import pathlib

SPEC = pathlib.Path(__file__).resolve().parents[1].parent
REPO = SPEC.parents[2]
APP = REPO / "cji_agent"
FILES = {
    "agents/workers.py": 4, "agents/ingestion_worker.py": 1, "tools/mcp_client.py": 2,
    "repositories/duckdb_parquet.py": 1, "mcp_servers/insight_server.py": 3, "collector/api.py": 2,
}
for rel, count in FILES.items():
    p = APP / rel
    t = p.read_text(encoding="utf-8")
    assert t.count("# noqa: BLE001 - ") == count, (rel, t.count("# noqa: BLE001 - "))
    p.write_text(t.replace("# noqa: BLE001 - ", "# broad-except: "), encoding="utf-8")


def replace(path, old, new, count=1):
    t = path.read_text(encoding="utf-8")
    assert t.count(old) == count, (path.name, old[:60], t.count(old))
    path.write_text(t.replace(old, new), encoding="utf-8")


test = APP / "tests/test_cleanup.py"
replace(test, 'if _is_broad(h) and not re.search(r"noqa: BLE001 - \\S", line)', 'if _is_broad(h) and not re.search(r"# broad-except: \\S", line)')
replace(test, '"broad handlers need \'# noqa: BLE001 - <reason>\':\\n"', '"broad handlers need \'# broad-except: <reason>\':\\n"')
replace(SPEC / "requirements.md", "SHALL carry `# noqa: BLE001 - <reason>` and either", "SHALL carry `# broad-except: <reason>` and either")
replace(SPEC / "requirements.md", "Boundaries keep `except Exception` with `# noqa: BLE001 - <reason>`, log", "Boundaries keep `except Exception` with `# broad-except: <reason>`, log")
replace(SPEC / "design.md", "kept; `# noqa: BLE001 - <boundary>`; `exc_info=True` added where missing", "kept; `# broad-except: <boundary>`; `exc_info=True` added where missing")
replace(SPEC / "design.md", "annotated `# noqa: BLE001 - F-07, replaced in Spec 07`", "annotated `# broad-except: F-07, replaced in Spec 07`")
replace(SPEC / "design.md", "broad handler whose `except` line lacks `noqa: BLE001 - `, and", "broad handler whose `except` line lacks `# broad-except: <reason>`, and")
print("fix 5 applied")
