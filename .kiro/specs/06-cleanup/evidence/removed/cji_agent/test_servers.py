import asyncio
from tools.mcp_client import mcp_session, call_tool

async def test_journey_data():
    try:
        async with mcp_session("cji-journey-data") as session:
            print("Testing journey data server...")
            res = await call_tool(session, "get_system_info")
            print("SUCCESS: get_system_info:", res)
    except Exception as e:
        print("FAILED cji-journey-data:", e)

async def test_friction_engine():
    try:
        async with mcp_session("cji-friction-engine") as session:
            print("\nTesting friction engine...")
            metrics = {
                "step_id": "test_step", "unique_users": 100, 
                "completion_rate_pct": 50.0,
                "abandon_rate_pct": 50.0, "error_rate_pct": 20.0,
                "avg_dwell_ms": 120000, "avg_rage_clicks": 1.0, "avg_retries": 2.0
            }
            res = await call_tool(session, "score_friction", {"step_metrics": metrics})
            print("SUCCESS: score_friction:", res)
    except Exception as e:
        print("FAILED cji-friction-engine:", e)

async def test_insight():
    try:
        async with mcp_session("cji-insight") as session:
            print("\nTesting insight server...")
            res = await call_tool(session, "search_insights", {"query": "test", "n_results": 1})
            print("SUCCESS: search_insights:", res)
    except Exception as e:
        print("FAILED cji-insight:", e)

async def test_report():
    try:
        async with mcp_session("cji-report") as session:
            print("\nTesting report server...")
            res = await call_tool(session, "export_report", {
                "journey_name": "test", "narrative": "test narrative", 
                "friction_scores": [], "insights": [], "funnel_data": [], "mode": "demo"
            })
            print("SUCCESS: export_report:", res)
    except Exception as e:
        print("FAILED cji-report:", e)

async def main():
    await test_journey_data()
    await test_friction_engine()
    await test_insight()
    await test_report()

if __name__ == "__main__":
    asyncio.run(main())
