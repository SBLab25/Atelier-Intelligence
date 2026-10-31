import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
sys.path.insert(0, r"C:\Users\sovan\Documents\Projects\TCS-CJI\cji_agent")
import logging; logging.disable(logging.CRITICAL)
import config
import pandas as pd
df = pd.read_parquet(config.EVENTS_PARQUET)
print("config JOURNEY_NAME =", config.JOURNEY_NAME)
print("config steps        =", config.JOURNEY_CONFIG["steps"])
print("parquet rows        =", len(df))
print("parquet journey_id  =", sorted(df["journey_id"].astype(str).unique())[:10])
print("parquet step_id     =", sorted(df["step_id"].astype(str).unique()))
print("parquet ts range    =", df["timestamp"].min(), "->", df["timestamp"].max())
from mcp_servers import journey_data_server as j
import inspect, re
src = inspect.getsource(j.get_step_metrics) if hasattr(j, "get_step_metrics") else ""
m = re.findall(r"(WHERE[^\n]*\n[^\n]*)", src)
print("demo WHERE clauses  =", [s.strip()[:160] for s in m[:3]])
