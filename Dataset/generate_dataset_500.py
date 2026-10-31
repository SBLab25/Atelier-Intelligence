"""
CJI PoC — Synthetic Dataset Generator (500 users)
===================================================
Generates synthetic customer journey data across 5 sources:
  1. GA4 / Clickstream
  2. Hotjar
  3. UXCam
  4. Surveys
  5. Support Tickets

Output  : JSON + CSV files in ./output/
Runtime : ~5 seconds
Usage   : python generate_dataset_500.py
Requires: Python 3.8+  (stdlib only — no pip installs needed)

Friction is deliberately injected at 'profile_setup' step so your
Layer 3 engine has something concrete to detect.
"""

import json
import csv
import random
import uuid
import os
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────

random.seed(42)
NUM_USERS  = 500
OUTPUT_DIR = "./output_500"
os.makedirs(OUTPUT_DIR, exist_ok=True)

JOURNEY_STEPS = [
    {"step": "landing_page",    "order": 1, "drop_off": 0.18},
    {"step": "sign_up_form",    "order": 2, "drop_off": 0.15},
    {"step": "email_verify",    "order": 3, "drop_off": 0.28},
    {"step": "profile_setup",   "order": 4, "drop_off": 0.62},  # <-- friction injected
    {"step": "confirm_details", "order": 5, "drop_off": 0.09},
    {"step": "onboarding_done", "order": 6, "drop_off": 0.00},
]

DEVICES   = ["desktop", "mobile", "tablet"]
BROWSERS  = ["Chrome", "Safari", "Firefox", "Edge"]
COUNTRIES = ["IN", "US", "GB", "DE", "AU", "SG", "AE"]
CHANNELS  = ["organic_search", "paid_ads", "email", "direct", "referral", "social"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def rand_ts(days_back=30):
    """Return a random ISO-8601 timestamp within the last N days."""
    base  = datetime(2026, 3, 22, 12, 0, 0)
    delta = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return (base - delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_user():
    """Create a synthetic user profile."""
    return {
        "user_id":    str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "device":     random.choice(DEVICES),
        "browser":    random.choice(BROWSERS),
        "country":    random.choice(COUNTRIES),
        "channel":    random.choice(CHANNELS),
    }


def write_json(filename, payload):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    kb = os.path.getsize(path) / 1024
    print(f"  [JSON] {filename:<45} {kb:>7.0f} KB")


def write_csv(filename, rows):
    if not rows:
        return
    # Collect all keys across all rows (handles variable schema per event type)
    all_keys = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            clean = {k: "" if v is None else str(v).replace("\n", " ") for k, v in r.items()}
            writer.writerow({k: clean.get(k, "") for k in all_keys})
    kb = os.path.getsize(path) / 1024
    print(f"  [CSV]  {filename:<45} {kb:>7.0f} KB  ({len(rows):,} rows)")


# ── 1. GA4 / Clickstream ──────────────────────────────────────────────────────

def generate_ga4(users):
    """
    Simulates Google Analytics 4 event stream.
    Events: session_start | page_view | click | step_reached | step_abandoned
    """
    events = []
    for u in users:
        ts = datetime.strptime(rand_ts(), "%Y-%m-%dT%H:%M:%SZ")

        # Session start
        events.append({
            "event_name":           "session_start",
            "user_id":              u["user_id"],
            "session_id":           u["session_id"],
            "timestamp":            ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "device_category":      u["device"],
            "browser":              u["browser"],
            "country":              u["country"],
            "traffic_source":       u["channel"],
            "journey_name":         "user_onboarding",
            "page_location":        "https://app.example.com/",
            "engagement_time_msec": random.randint(1000, 3000),
        })

        active = True
        for step_cfg in JOURNEY_STEPS:
            if not active:
                break
            ts       += timedelta(seconds=random.randint(8, 240))
            is_friction = step_cfg["step"] == "profile_setup"

            # page_view
            events.append({
                "event_name":           "page_view",
                "user_id":              u["user_id"],
                "session_id":           u["session_id"],
                "timestamp":            ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "device_category":      u["device"],
                "browser":              u["browser"],
                "country":              u["country"],
                "traffic_source":       u["channel"],
                "journey_name":         "user_onboarding",
                "step_name":            step_cfg["step"],
                "step_order":           step_cfg["order"],
                "page_location":        f"https://app.example.com/{step_cfg['step'].replace('_', '-')}",
                "engagement_time_msec": random.randint(90000, 320000) if is_friction else random.randint(5000, 90000),
                "scroll_depth_pct":     random.randint(30, 100),
            })

            # step_reached custom event
            events.append({
                "event_name":      "step_reached",
                "user_id":         u["user_id"],
                "session_id":      u["session_id"],
                "timestamp":       ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "journey_name":    "user_onboarding",
                "step_name":       step_cfg["step"],
                "step_order":      step_cfg["order"],
                "device_category": u["device"],
            })

            # Clicks — more clicks at friction step (retries)
            n_clicks = random.randint(6, 14) if is_friction else random.randint(1, 4)
            for _ in range(n_clicks):
                ts += timedelta(seconds=random.randint(2, 15))
                events.append({
                    "event_name":   "click",
                    "user_id":      u["user_id"],
                    "session_id":   u["session_id"],
                    "timestamp":    ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "journey_name": "user_onboarding",
                    "step_name":    step_cfg["step"],
                    "element_id":   random.choice(
                        ["submit_btn", "form_field", "cta_button", "help_icon", "next_btn", "back_btn"]
                    ),
                })

            # Drop-off decision
            if random.random() < step_cfg["drop_off"]:
                ts += timedelta(seconds=random.randint(5, 60))
                events.append({
                    "event_name":      "step_abandoned",
                    "user_id":         u["user_id"],
                    "session_id":      u["session_id"],
                    "timestamp":       ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "journey_name":    "user_onboarding",
                    "step_name":       step_cfg["step"],
                    "step_order":      step_cfg["order"],
                    "device_category": u["device"],
                    "exit_reason":     random.choice(
                        ["timeout", "back_navigation", "tab_close", "idle", "error"]
                    ),
                })
                active = False

    return events


# ── 2. Hotjar ─────────────────────────────────────────────────────────────────

def generate_hotjar(users, ga4_events):
    """
    Simulates Hotjar heatmap, form analytics, hesitation, and NPS data.
    One record per (session, step) pair.
    """
    rows = []
    for u in users:
        sess_evts  = [e for e in ga4_events if e.get("session_id") == u["session_id"] and "step_name" in e]
        steps_hit  = list({e["step_name"] for e in sess_evts})

        for step in steps_hit:
            is_f = step == "profile_setup"
            is_e = step == "email_verify"

            rows.append({
                "session_id":                      u["session_id"],
                "user_id":                         u["user_id"],
                "step_name":                       step,
                "journey_name":                    "user_onboarding",
                "device":                          u["device"],
                "country":                         u["country"],
                "recording_url":                   f"https://hotjar.com/recordings/{u['session_id'][:8]}",
                "heatmap_total_clicks":            random.randint(18, 90) if is_f else random.randint(2, 18),
                "heatmap_dead_clicks":             random.randint(10, 30) if is_f else random.randint(0, 4),
                "heatmap_rage_clicks":             random.randint(4, 18)  if is_f else random.randint(0, 2),
                "scroll_max_depth_pct":            random.randint(40, 100),
                "hesitation_first_interaction_ms": random.randint(9000, 28000) if is_f
                                                   else random.randint(3000, 10000) if is_e
                                                   else random.randint(400, 4000),
                "hesitation_mouse_idle_periods":   random.randint(3, 12) if is_f else random.randint(0, 2),
                "hesitation_cursor_backtrack":     random.randint(5, 16) if is_f else random.randint(0, 3),
                "form_field_drop_off":             random.choice(
                    ["address_line1", "postcode", "phone", "date_of_birth"]
                ) if is_f else None,
                "form_refill_count":               random.randint(3, 9) if is_f else random.randint(0, 1),
                "form_time_sec":                   random.randint(95, 300) if is_f else random.randint(8, 60),
                "form_blank_submit_attempts":      random.randint(1, 5) if is_f else 0,
                "nps_score":                       random.randint(1, 5)  if is_f else random.randint(7, 10),
                "nps_comment":                     random.choice([
                    "Form keeps rejecting my postcode",
                    "Address field broken on mobile",
                    "No error message shown — just failed silently",
                    "Submit button does nothing, tried 5 times",
                    "Gave up after 10 minutes on profile page",
                ]) if is_f and random.random() < 0.45 else None,
            })
    return rows


# ── 3. UXCam ──────────────────────────────────────────────────────────────────

def generate_uxcam(users, ga4_events):
    """
    Simulates UXCam mobile session data — gestures, performance, frustration.
    Only for mobile/tablet users.
    """
    OS_LIST = ["iOS 17", "Android 14", "Android 13"]
    rows    = []
    mobile  = [u for u in users if u["device"] in ["mobile", "tablet"]]

    for u in mobile:
        sess_evts = [e for e in ga4_events if e.get("session_id") == u["session_id"] and "step_name" in e]
        steps_hit = list({e["step_name"] for e in sess_evts})

        for step in steps_hit:
            is_f = step == "profile_setup"
            rows.append({
                "session_id":                  u["session_id"],
                "user_id":                     u["user_id"],
                "step_name":                   step,
                "journey_name":                "user_onboarding",
                "device_type":                 u["device"],
                "os":                          random.choice(OS_LIST),
                "app_version":                 "2.4.1",
                "country":                     u["country"],
                "screen_recording_url":        f"https://uxcam.com/s/{u['session_id'][:8]}/{step}",
                "gesture_total_taps":          random.randint(18, 65) if is_f else random.randint(3, 16),
                "gesture_swipe_count":         random.randint(2, 12),
                "gesture_pinch_zoom":          random.randint(2, 9) if is_f else 0,
                "gesture_long_press":          random.randint(1, 6) if is_f else 0,
                "crash_occurred":              random.random() < 0.06 if is_f else False,
                "anr_occurred":                random.random() < 0.04 if is_f else False,
                "screen_load_ms":              random.randint(2800, 7000) if is_f else random.randint(300, 1600),
                "api_latency_ms":              random.randint(900, 3500)  if is_f else random.randint(100, 600),
                "frame_drop_count":            random.randint(6, 22)  if is_f else random.randint(0, 3),
                "frustration_score":           round(random.uniform(0.62, 1.0), 2) if is_f
                                               else round(random.uniform(0.0, 0.32), 2),
                "repeated_taps_same_element":  random.randint(5, 14) if is_f else random.randint(0, 2),
                "keyboard_dismiss_count":      random.randint(3, 9)  if is_f else random.randint(0, 1),
                "screen_completed":            random.random() > 0.61 if is_f else random.random() > 0.10,
                "time_on_screen_sec":          random.randint(88, 280) if is_f else random.randint(8, 65),
            })
    return rows


# ── 4. Surveys ────────────────────────────────────────────────────────────────

def generate_surveys(n=250):
    """Simulates NPS / CSAT / CES survey responses with verbatim comments."""
    NEG = [
        "The profile page form is completely broken on mobile",
        "Couldn't complete the address field — keeps rejecting valid inputs",
        "Took 15 minutes on profile page because of constant errors",
        "Postcode field doesn't accept my PIN code even though it is correct",
        "I gave up on profile setup — too many unexplained errors",
        "Why does it need a landline? I only have a mobile number",
        "Submit button did nothing three times in a row",
        "Error says invalid input but gives no explanation of what is wrong",
        "Verification email never arrived even after 4 resend attempts",
        "Resend email button seems completely broken",
        "App said I was verified but still showed me as unverified",
        "The back button resets my entire form and I lost all my data",
        "Nothing happens when I tap submit on profile form",
    ]
    NEUT = [
        "Process was okay but could be faster",
        "Sign up took longer than expected",
        "UI is clean but the form needs work",
        "Average experience, nothing special",
    ]
    POS = [
        "Very smooth and easy to use",
        "Loved how intuitive the sign-up was",
        "Quick and painless onboarding experience",
        "Great UX overall, very clean design",
        "Finished in under 2 minutes, impressive",
        "Best onboarding I have seen in any app",
    ]

    rows = []
    for _ in range(n):
        step = random.choices(
            ["profile_setup", "email_verify", "sign_up_form", "landing_page", "confirm_details"],
            weights=[0.50, 0.20, 0.12, 0.10, 0.08],
        )[0]
        is_neg_step = step in ["profile_setup", "email_verify"]
        sentiment   = random.choices(
            ["negative", "neutral", "positive"],
            weights=[0.75, 0.15, 0.10] if is_neg_step else [0.10, 0.20, 0.70],
        )[0]

        csat = {"negative": random.randint(1, 2), "neutral": 3, "positive": random.randint(4, 5)}[sentiment]
        nps  = {"negative": random.randint(0, 4), "neutral": random.randint(5, 6), "positive": random.randint(8, 10)}[sentiment]

        rows.append({
            "survey_id":           str(uuid.uuid4()),
            "user_id":             str(uuid.uuid4()),
            "timestamp":           rand_ts(),
            "channel":             random.choice(["in_app_popup", "email_survey", "exit_survey"]),
            "journey_name":        "user_onboarding",
            "triggered_at_step":   step,
            "survey_type":         random.choice(["NPS", "CSAT", "CES", "open_ended"]),
            "nps_score":           nps,
            "csat_score":          csat,
            "ces_score":           random.randint(1, 3) if sentiment == "negative" else random.randint(4, 7),
            "sentiment":           sentiment,
            "verbatim_comment":    random.choice(NEG)  if sentiment == "negative"
                                   else random.choice(NEUT) if sentiment == "neutral"
                                   else random.choice(POS),
            "device":              random.choice(DEVICES),
            "country":             random.choice(COUNTRIES),
            "completion_rate":     round(random.uniform(0.15, 0.65), 2) if sentiment == "negative"
                                   else round(random.uniform(0.70, 1.0), 2),
        })
    return rows


# ── 5. Support Tickets ────────────────────────────────────────────────────────

def generate_tickets(n=180):
    """Simulates Zendesk / Freshdesk support ticket data."""
    SUBJECTS = {
        "profile_setup": [
            "Cannot complete my profile — form error",
            "Profile setup page broken",
            "Address field not accepting valid input",
            "Stuck on profile setup step",
            "Error on profile form with no explanation",
            "Form validation bug on profile page",
            "Submit button on profile form unresponsive",
        ],
        "email_verify": [
            "Verification email not received",
            "Resend email not working",
            "Stuck on email verification",
            "Link expired immediately",
        ],
        "sign_up_form": [
            "Sign up button not responding",
            "Password requirements unclear",
        ],
        "general": [
            "App crashes during onboarding",
            "Slow loading pages during sign up",
        ],
    }

    rows = []
    for _ in range(n):
        step = random.choices(
            ["profile_setup", "email_verify", "sign_up_form", "general"],
            weights=[0.58, 0.22, 0.12, 0.08],
        )[0]
        is_crit   = step == "profile_setup"
        created   = rand_ts()
        res_hrs   = random.randint(1, 96)
        resolved  = (
            datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=res_hrs)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows.append({
            "ticket_id":              f"TKT-{random.randint(10000, 99999)}",
            "user_id":                str(uuid.uuid4()),
            "created_at":             created,
            "resolved_at":            resolved if random.random() > 0.25 else None,
            "journey_name":           "user_onboarding",
            "step_name":              step,
            "subject":                random.choice(SUBJECTS.get(step, SUBJECTS["general"])),
            "category":               "bug_report" if is_crit else random.choice(
                ["bug_report", "usability_issue", "feature_request", "account_help"]
            ),
            "priority":               random.choice(["high", "critical"]) if is_crit
                                      else random.choice(["low", "medium", "high"]),
            "status":                 random.choice(["resolved", "in_progress", "escalated", "closed_no_fix"]),
            "channel":                random.choice(["in_app_chat", "email", "whatsapp", "phone"]),
            "device":                 random.choice(DEVICES),
            "country":                random.choice(COUNTRIES),
            "agent_notes":            f"User stuck at {step}. Likely form validation issue." if is_crit
                                      else "Standard query.",
            "resolution_time_hrs":    res_hrs,
            "csat_after_resolution":  random.randint(1, 3) if is_crit else random.randint(3, 5),
            "tags":                   ["form_bug", "profile_setup", "high_volume"] if is_crit else [step],
            "escalated":              is_crit and random.random() < 0.30,
        })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nCJI Synthetic Dataset Generator — 500 users")
    print("=" * 52)

    print("\nGenerating users...")
    users = [new_user() for _ in range(NUM_USERS)]

    print("Generating GA4 clickstream...")
    ga4 = generate_ga4(users)
    print(f"  {len(ga4):,} events")

    print("Generating Hotjar sessions...")
    hotjar = generate_hotjar(users, ga4)
    print(f"  {len(hotjar):,} records")

    print("Generating UXCam sessions...")
    uxcam = generate_uxcam(users, ga4)
    print(f"  {len(uxcam):,} records")

    print("Generating surveys...")
    surveys = generate_surveys(n=250)
    print(f"  {len(surveys):,} responses")

    print("Generating support tickets...")
    tickets = generate_tickets(n=180)
    print(f"  {len(tickets):,} tickets")

    # Build master bundle
    master = {
        "meta": {
            "project":              "Customer Journey Intelligence — PoC",
            "generated_at":         "2026-03-22T12:00:00Z",
            "journey":              "user_onboarding",
            "total_users":          NUM_USERS,
            "friction_injected_at": "profile_setup",
            "journey_steps":        [s["step"] for s in JOURNEY_STEPS],
            "data_sources":         ["GA4", "Hotjar", "UXCam", "Surveys", "Support Tickets"],
            "note":                 "Synthetic data for CJI PoC. Friction deliberately injected at profile_setup.",
        },
        "ga4_clickstream": {"total": len(ga4),     "events":    ga4},
        "hotjar":          {"total": len(hotjar),  "sessions":  hotjar},
        "uxcam":           {"total": len(uxcam),   "sessions":  uxcam},
        "surveys":         {"total": len(surveys), "responses": surveys},
        "support_tickets": {"total": len(tickets), "tickets":   tickets},
    }

    # Build combined flat CSV
    flat = []
    for r in hotjar:
        flat.append({
            "source": "hotjar", "user_id": r["user_id"], "session_id": r["session_id"],
            "step_name": r["step_name"], "journey_name": r["journey_name"],
            "device": r["device"], "country": r["country"],
            "hesitation_ms": r["hesitation_first_interaction_ms"],
            "rage_clicks": r["heatmap_rage_clicks"], "dead_clicks": r["heatmap_dead_clicks"],
            "form_refill_count": r["form_refill_count"], "form_time_sec": r["form_time_sec"],
            "nps_score": r["nps_score"], "frustration_score": None,
            "sentiment": None, "verbatim": r["nps_comment"],
        })
    for r in uxcam:
        flat.append({
            "source": "uxcam", "user_id": r["user_id"], "session_id": r["session_id"],
            "step_name": r["step_name"], "journey_name": r["journey_name"],
            "device": r["device_type"], "country": r["country"],
            "hesitation_ms": None, "rage_clicks": None, "dead_clicks": None,
            "form_refill_count": None, "form_time_sec": r["time_on_screen_sec"],
            "nps_score": None, "frustration_score": r["frustration_score"],
            "sentiment": None, "verbatim": None,
        })
    for r in surveys:
        flat.append({
            "source": "survey", "user_id": r["user_id"], "session_id": None,
            "step_name": r["triggered_at_step"], "journey_name": r["journey_name"],
            "device": r["device"], "country": r["country"],
            "hesitation_ms": None, "rage_clicks": None, "dead_clicks": None,
            "form_refill_count": None, "form_time_sec": None,
            "nps_score": r["nps_score"], "frustration_score": None,
            "sentiment": r["sentiment"], "verbatim": r["verbatim_comment"],
        })
    for r in tickets:
        flat.append({
            "source": "ticket", "user_id": r["user_id"], "session_id": None,
            "step_name": r["step_name"], "journey_name": r["journey_name"],
            "device": r["device"], "country": r["country"],
            "hesitation_ms": None, "rage_clicks": None, "dead_clicks": None,
            "form_refill_count": None, "form_time_sec": None,
            "nps_score": None, "frustration_score": None,
            "sentiment": None, "verbatim": r["subject"],
        })

    print(f"\nWriting files to ./{OUTPUT_DIR}/")
    print("-" * 52)
    write_json("all_sources_bundle.json",  master)
    write_json("ga4_clickstream.json",     {"source": "GA4", "total_events": len(ga4), "events": ga4})
    write_json("hotjar.json",              {"source": "Hotjar", "total_sessions": len(hotjar), "sessions": hotjar})
    write_json("uxcam.json",               {"source": "UXCam", "total_sessions": len(uxcam), "sessions": uxcam})
    write_json("surveys.json",             {"source": "Surveys", "total_responses": len(surveys), "responses": surveys})
    write_json("support_tickets.json",     {"source": "Tickets", "total_tickets": len(tickets), "tickets": tickets})
    write_csv("ga4_clickstream.csv",       ga4)
    write_csv("hotjar.csv",                hotjar)
    write_csv("uxcam.csv",                 uxcam)
    write_csv("surveys.csv",               surveys)
    write_csv("support_tickets.csv",       tickets)
    write_csv("combined_signals.csv",      flat)

    total = len(ga4) + len(hotjar) + len(uxcam) + len(surveys) + len(tickets)
    print(f"\n{'=' * 52}")
    print(f"  Done. Grand total: {total:,} records across 5 sources.")
    print(f"  Output directory : ./{OUTPUT_DIR}/")
    print(f"{'=' * 52}\n")


if __name__ == "__main__":
    main()
