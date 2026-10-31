import sys
import os
from pathlib import Path

# Add cji_agent to sys.path
sys.path.append(str(Path("cji_agent").resolve()))

os.environ['CJI_MODE'] = 'demo'

from mcp_servers.journey_data_server import get_step_metrics, get_funnel_dropoff

print("Step Metrics:")
print(get_step_metrics(30))

print("\nFunnel:")
print(get_funnel_dropoff(30))
