"""
Utility script to emit live test events directly into the Supabase 'live_events' table.
Usage:
    python scripts/emit_live_event.py [--journey user_onboarding] [--step email_verification] [--type rage_click]
"""
import argparse
import datetime
import json
import os
import sys
import uuid

# Ensure working directory is cji_agent
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
os.chdir(parent_dir)

from sqlalchemy import text
from cji.repositories import get_repository

def emit_event(journey_name: str, step_id: str, event_type: str, user_id: str | None = None):
    repo = get_repository()
    engine = repo._get_engine("emit_live_event")
    
    event_id = str(uuid.uuid4())
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    uid = user_id or f"usr_{uuid.uuid4().hex[:6]}"
    now = datetime.datetime.now(datetime.timezone.utc)
    meta_dict = {"source": "live_cli_emitter", "retry_count": 0, "client": "dashboard_test"}

    sql = text("""
        INSERT INTO live_events (
            timestamp, event_id, session_id, user_id, journey_name, step_id, event_type, url, element_selectors, metadata
        ) VALUES (
            :timestamp, :event_id, :session_id, :user_id, :journey_name, :step_id, :event_type, :url, :element_selectors, CAST(:metadata AS jsonb)
        )
    """)

    with engine.begin() as conn:
        conn.execute(sql, {
            "timestamp": now,
            "event_id": event_id,
            "session_id": session_id,
            "user_id": uid,
            "journey_name": journey_name,
            "step_id": step_id,
            "event_type": event_type,
            "url": f"https://app.example.com/{step_id}",
            "element_selectors": f"#{step_id}-submit-button",
            "metadata": json.dumps(meta_dict)
        })
        count = conn.execute(text("SELECT count(*) FROM live_events")).scalar()

    print(f"[OK] Successfully emitted live event to Supabase 'live_events' table!")
    print(f"     Event ID:     {event_id}")
    print(f"     Journey:      {journey_name}")
    print(f"     Step:         {step_id}")
    print(f"     Type:         {event_type}")
    print(f"     User ID:      {uid}")
    print(f"     Timestamp:    {now.isoformat()}")
    print(f"     Total rows in live_events: {count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Emit a live test event into Supabase live_events table.")
    parser.add_argument("--journey", default="user_onboarding", help="Journey name (e.g. user_onboarding, my_vercel_site)")
    parser.add_argument("--step", default="payment_info", help="Step ID (e.g. landing_page, email_verification, payment_info)")
    parser.add_argument("--type", default="rage_click", choices=["page_view", "click", "form_submit", "error", "rage_click", "abandon", "step_complete"], help="Event type")
    parser.add_argument("--user", default=None, help="User ID (optional)")
    args = parser.parse_args()

    emit_event(args.journey, args.step, args.type, args.user)
