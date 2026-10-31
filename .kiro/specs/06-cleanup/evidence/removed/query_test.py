import duckdb
import json

conn = duckdb.connect("cji_agent/data/cji.db")
conn.execute("CREATE OR REPLACE TEMP VIEW events AS SELECT * FROM read_parquet('cji_agent/data/events.parquet')")

try:
    # First: simple query without time filter
    df1 = conn.execute("SELECT step_id, COUNT(*) as c FROM events GROUP BY step_id").df()
    print("NO FILTER:")
    print(df1)
    
    # Second: with NOW()
    df2 = conn.execute("SELECT step_id, COUNT(*) as c FROM events WHERE timestamp >= NOW() - INTERVAL '30 days' GROUP BY step_id").df()
    print("\nWITH FILTER:")
    print(df2)
    
    # Third: using the exact string
    sql = """
    SELECT 
        step_id, 
        COUNT(DISTINCT user_id) AS unique_users,
        COUNT(*) FILTER (WHERE event_type = 'error') AS total_errors,
        COUNT(*) FILTER (WHERE event_type = 'rage_click') AS total_rage_clicks,
        COUNT(*) FILTER (WHERE event_type IN ('abandon', 'form_abandon')) AS absolute_drop_offs,
        COALESCE(ROUND(AVG(CASE WHEN event_type IN ('page_view','step_complete') 
                            THEN duration_ms ELSE NULL END), 0), 0) AS avg_dwell_ms
    FROM events
    WHERE journey_id = 'user_onboarding' AND timestamp >= NOW() - INTERVAL '30 days'
    GROUP BY step_id
    """
    df3 = conn.execute(sql).df()
    print("\nFULL QUERY:")
    print(df3)
    
except Exception as e:
    print("ERROR:", e)
finally:
    conn.close()
