"""
Spec 05 T1 probe: run today's realtime journey-data code and realtime ingestion against a
throwaway local PostgreSQL (pgserver). Never touches DATABASE_URL / Supabase.
usage (from cji_agent/): python probe_realtime_before.py <out.txt>
"""
import asyncio
import inspect
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.getcwd())
out: list[str] = []


def note(*parts):
    out.append(" ".join(str(p) for p in parts))


import pandas as pd  # noqa: E402
import pgserver  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="cji_pg_probe_"))
srv = pgserver.get_server(str(tmp), cleanup_mode="stop")
uri = srv.get_uri()
engine = create_engine(uri)
with engine.begin() as c:
    note("server:", c.execute(text("SELECT version()")).scalar())

# Tables exactly as production creates them: collector DDL and pandas to_sql of EventRecord rows.
LIVE_DDL = """CREATE TABLE IF NOT EXISTS live_events (
    timestamp TIMESTAMP, event_id VARCHAR PRIMARY KEY, session_id VARCHAR, user_id VARCHAR,
    journey_name VARCHAR, step_id VARCHAR, event_type VARCHAR, url VARCHAR,
    element_selectors VARCHAR, metadata JSONB)"""
with engine.begin() as c:
    c.execute(text(LIVE_DDL))
now = datetime.now(timezone.utc)
rows = []
for i, (step, etype, meta) in enumerate([
    ("landing_page", "page_view", {}), ("landing_page", "step_complete", {}),
    ("sign_up_form", "page_view", {}), ("sign_up_form", "error", {"retry_count": 2}),
    ("sign_up_form", "error", {"retry_count": 4}), ("sign_up_form", "abandon", {}),
]):
    rows.append({"event_id": str(uuid.uuid4()), "user_id": f"u{i % 3}", "session_id": f"s{i % 3}",
                 "journey_id": "user_onboarding", "step_id": step, "event_type": etype,
                 "timestamp": now - timedelta(minutes=5), "duration_ms": 1000 * (i + 1),
                 "url": "https://x.test", "metadata": json.dumps(meta)})
pd.DataFrame(rows).to_sql("tracking_events", engine, if_exists="replace", index=False)
with engine.begin() as c:
    cols = c.execute(text("SELECT column_name, data_type FROM information_schema.columns "
                          "WHERE table_name = 'tracking_events' ORDER BY ordinal_position")).fetchall()
note("tracking_events columns:", cols)

from mcp_servers import journey_data_server as j  # noqa: E402

j.CJI_MODE = "realtime"
j.JOURNEY_CONFIG = {"name": "user_onboarding", "steps": ["landing_page", "sign_up_form"]}
j._pg_engine = engine


def run(v):
    return asyncio.run(v) if inspect.isawaitable(v) else v


for name, call in [("get_system_info", lambda: j.get_system_info()),
                   ("get_step_metrics", lambda: j.get_step_metrics(minutes_back=60)),
                   ("get_funnel_dropoff", lambda: j.get_funnel_dropoff(minutes_back=60)),
                   ("query_events", lambda: j.query_events(limit=3)),
                   ("get_live_snapshot", lambda: j.get_live_snapshot(minutes=60))]:
    try:
        res = run(call())
        note(f"{name}:", json.dumps(res, default=str)[:700])
    except Exception as e:  # noqa: BLE001
        note(f"{name}: EXCEPTION {type(e).__name__}: {str(e)[:300]}")

# Raw types returned by the step-metrics SQL through pandas/psycopg2 (Decimal check)
try:
    df = pd.read_sql(text("SELECT ROUND(1 * 100.0 / NULLIF(3, 0), 2) AS r, COUNT(*) AS n FROM tracking_events"), engine)
    note("numeric types via read_sql:", {c: type(df[c].iloc[0]).__name__ for c in df.columns})
except Exception as e:  # noqa: BLE001
    note("types probe failed:", e)

# Today's realtime ingestion insert (F-06): run the exact statement pattern of ingest_to_store
from mcp_servers import ingestion_intelligence_server as ing  # noqa: E402

src = inspect.getsource(ing.ingest_to_store)
start = src.index('INSERT INTO live_events')
stmt = src[start: src.index('"""', start)]
records = [{**r, "timestamp": str(r["timestamp"])} for r in rows[:3]]
outcomes = []
with engine.begin() as c:
    for rec in records:
        try:
            c.execute(text(stmt), rec)
            outcomes.append("ok")
        except Exception as e:  # noqa: BLE001
            outcomes.append(type(e).__name__ + ": " + str(e).splitlines()[0][:120])
note("ingest_to_store realtime insert outcomes:", outcomes)
with engine.begin() as c:
    note("live_events rows after ingest:", c.execute(text("SELECT COUNT(*) FROM live_events")).scalar())

engine.dispose()
srv.cleanup()
Path(sys.argv[1]).write_text("\n".join(out), encoding="utf-8")
