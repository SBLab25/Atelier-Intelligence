"""Spec 06 follow-up edit 2: remaining dashboard loader calls go through _load(); ingest id read via SQLAlchemy."""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"


def edit(rel, pairs):
    p = APP / rel
    t = p.read_text(encoding="utf-8")
    for pattern, repl, count in pairs:
        found = len(re.findall(pattern, t))
        assert found == count, (rel, pattern, found)
        t = re.sub(pattern, repl, t)
    p.write_text(t, encoding="utf-8")


SEL = r'st\.session_state\.get\("sel_property"\)'
edit("dashboard.py", [
    (r"(?m)^(\s+)last = load_last_run\(\)$", r'\1last = _load("Last run", load_last_run, flush=True)', 1),
    (rf"(?m)^(\s+)(aud_data|audience_data) = load_audience_data\({SEL}\)$",
     r'\1\2 = _load("Audience", load_audience_data, st.session_state.get("sel_property"), flush=True)', 2),
    (rf"(?m)^(\s+)(hm_data|heatmap_df) = load_heatmap_data\({SEL}\)$",
     r'\1\2 = _load("Heatmap", load_heatmap_data, st.session_state.get("sel_property"), flush=True)', 2),
])
edit("tools/ingest_json.py", [
    (re.escape('''    ids = pd.read_sql("SELECT event_id FROM tracking_events", engine)
    return set(ids["event_id"].astype(str))'''),
     '''    with engine.connect() as conn:
        rows = conn.execute(text("SELECT event_id FROM tracking_events")).scalars()
        return {str(r) for r in rows}''', 1),
    (re.escape("from sqlalchemy import create_engine, inspect\n"), "from sqlalchemy import create_engine, inspect, text\n", 1),
])
print("fix 2 applied")
