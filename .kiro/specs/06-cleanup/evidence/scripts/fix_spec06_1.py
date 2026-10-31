"""Spec 06 follow-up edit 1: `derived` became unused once the ignored journey_id hint was removed (F-13)."""
import pathlib

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
p = APP / "mcp_servers" / "ingestion_intelligence_server.py"
t = p.read_text(encoding="utf-8")
old = '    derived       = mapping_config.get("derived_fields", {})\n'
assert t.count(old) == 1, t.count(old)
p.write_text(t.replace(old, ""), encoding="utf-8")
print("fix 1 applied")
