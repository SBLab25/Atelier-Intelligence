import sys, os
from pathlib import Path
root_dir = Path("cji_agent").resolve()
sys.path.append(str(root_dir))
import asyncio
from cji_agent.mcp_servers.journey_data_server import get_step_metrics, query_events, CJI_MODE, EVENTS_PARQUET

async def main():
    print(f"CJI_MODE={CJI_MODE}")
    print(f"EVENTS_PARQUET={EVENTS_PARQUET}")
    print("STEP METRICS:", await get_step_metrics())
    print("QUERY EVENTS:", await query_events(limit=5))

asyncio.run(main())
