import sys
from pathlib import Path
import traceback
import pandas as pd

sys.path.insert(0, str(Path("cji_agent").resolve()))
from dashboard import engine

def get_from_clause(sel_property):
    te = "SELECT user_id, session_id, journey_id, step_id, event_type, timestamp, duration_ms, metadata::jsonb FROM tracking_events"
    le = "SELECT user_id, session_id, journey_name AS journey_id, step_id, event_type, timestamp, 0 AS duration_ms, metadata::jsonb FROM live_events"
    de = "SELECT user_id, session_id, journey_id, step_id, event_type, timestamp, duration_ms, metadata::jsonb FROM demo_events"
    if sel_property == "Live_event track":
        return f"({le}) AS unified_events"
    elif sel_property == "tracking_event track":
        return f"({te}) AS unified_events"
    elif sel_property == "demo_events track":
        return f"({de}) AS unified_events"
    else:
        return f"({te} UNION ALL {le} UNION ALL {de}) AS unified_events"

try:
    from_clause = get_from_clause("all_journeys")
    with engine.connect() as conn:
        regions_df = pd.read_sql(f"""
            SELECT metadata->>'region' as region, COUNT(DISTINCT session_id) as sessions
            FROM {from_clause} WHERE metadata->>'region' IS NOT NULL GROUP BY 1 ORDER BY 2 DESC
        """, conn)
        print(regions_df)
except Exception as e:
    traceback.print_exc()
