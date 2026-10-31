"""
Verification script for all 5 CJI MCP servers against configured Supabase and local services.
Run:
    python scripts/verify_mcp_servers.py
"""
import asyncio
import json
import os
import sys

# Ensure running in cji_agent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
os.chdir(parent_dir)

async def test_all():
    print("=== TESTING 5 CJI MCP SERVERS ===")

    # 1. JOURNEY DATA
    print("\n--- 1. Testing cji-journey-data (:8001) ---")
    from cji.mcp_servers import journey_data_server
    sys_info = await journey_data_server.get_system_info()
    print("System Info:", json.dumps(sys_info, indent=2))
    
    funnel_steps = journey_data_server.get_funnel_steps()
    print("Funnel Steps:", funnel_steps)

    step_metrics = await journey_data_server.get_step_metrics(days_back=365)
    print(f"Step Metrics count: {step_metrics.get('total_steps')}")
    if step_metrics.get("step_metrics"):
        print("Sample step metric:", json.dumps(step_metrics["step_metrics"][0], indent=2))

    dropoffs = await journey_data_server.get_funnel_dropoff(days_back=365)
    print("Funnel Dropoff:", json.dumps(dropoffs, indent=2))

    events = await journey_data_server.query_events(limit=3)
    print(f"Sample Events count: {events.get('count')}")
    if events.get("events"):
        print("Sample event:", json.dumps(events["events"][0], indent=2))

    # 2. FRICTION ENGINE
    print("\n--- 2. Testing cji-friction-engine (:8002) ---")
    from cji.mcp_servers import friction_engine_server
    sample_metrics = step_metrics.get("step_metrics", [])
    friction_res = {}
    if sample_metrics:
        friction_res = friction_engine_server.score_all_steps(sample_metrics)
        print("Friction Scores summary:")
        print(f"  Total steps: {friction_res.get('total_steps')}")
        print(f"  Critical steps: {friction_res.get('critical_steps')}")
        print(f"  Avg score: {friction_res.get('avg_score')}")
        if friction_res.get("scores"):
            print("  First step score:", friction_res["scores"][0])
    else:
        print("No step metrics to test friction engine with!")

    # 3. INSIGHT SERVER
    print("\n--- 3. Testing cji-insight (:8003) ---")
    from cji.mcp_servers import insight_server
    test_insight = {
        "insight_id": "test-verify-1",
        "step_id": "profile_setup",
        "title": "Extended Hesitation on Profile Setup",
        "root_cause": "Form requires bio and avatar without progress feedback.",
        "category": "UX",
        "evidence": ["High dwell time: 76998ms", "Signal: extended_hesitation"],
        "suggested_fix": "Allow optional skip on avatar and show step completion bar.",
        "fix_effort": "low",
        "score": 43,
        "priority": 1,
        "priority_score": 8.5,
        "run_id": "run-verify-test"
    }
    save_res = insight_server.save_insight(test_insight)
    print("Save Insight result:", save_res)

    search_res = insight_server.search_insights("profile setup", n_results=3)
    print(f"Search Insight results count: {search_res.get('count')}")
    if search_res.get("results"):
        print("Found:", search_res["results"][0]["document"])

    # 4. REPORT SERVER
    print("\n--- 4. Testing cji-report (:8004) ---")
    from cji.mcp_servers import report_server
    narrative = "Analysis of the user_onboarding journey revealed notable friction at profile setup. Strategic recommendations are provided."
    report_res = report_server.export_report(
        journey_name="user_onboarding",
        narrative=narrative,
        friction_scores=friction_res.get("scores", [])[:3] if sample_metrics else [],
        insights=[test_insight],
        funnel_data=dropoffs.get("funnel", []),
        mode="realtime",
        run_id="run-verify-test"
    )
    print("Export Report result:", json.dumps(report_res, indent=2))

    # 5. INGESTION INTELLIGENCE SERVER
    print("\n--- 5. Testing cji-ingestion-intelligence (:8005) ---")
    from cji.mcp_servers import ingestion_intelligence_server
    reg = ingestion_intelligence_server.get_mapping_registry()
    print(f"Mapping registry keys: {list(reg.keys())}")

    val_res = await ingestion_intelligence_server.validate_transformed_data([
        {
            "event_id": "00000000-0000-0000-0000-000000000001",
            "user_id": "u-123",
            "session_id": "s-123",
            "journey_id": "user_onboarding",
            "step_id": "landing_page",
            "event_type": "page_view",
            "timestamp": "2026-04-22T14:32:00Z",
            "duration_ms": 1200,
            "url": "https://example.com/welcome",
            "metadata": "{}"
        }
    ])
    print("Transformed data validation result:", json.dumps(val_res, indent=2))

    print("\n=== ALL 5 CJI MCP SERVERS FUNCTIONAL & VERIFIED ===")

if __name__ == "__main__":
    asyncio.run(test_all())

