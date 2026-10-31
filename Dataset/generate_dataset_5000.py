"""
CJI PoC — Synthetic Dataset Generator (5000 users)
====================================================
Generates a large synthetic customer journey dataset across 5 sources:
  1. GA4 / Clickstream      — ~120,000+ events
  2. Hotjar                 — ~18,000+ session heatmap records
  3. UXCam                  — ~12,000+ mobile session records
  4. Surveys                — 1,000 NPS / CSAT / CES responses
  5. Support Tickets        — 500 Zendesk-style tickets

Also produces:
  - combined_signals.csv    — flat union of all non-clickstream sources
  - all_sources_bundle.json — single file containing every source

Output  : JSON + CSV files in ./output_5k/
Runtime : ~30 seconds
Usage   : python generate_dataset_5000.py
Requires: Python 3.8+  (stdlib only — no pip installs needed)

Journey has 8 steps. Friction deliberately injected at 'profile_setup'
and partially at 'email_verify' and 'payment_info' for realism.
"""

import json
import csv
import random
import uuid
import os
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────

random.seed(99)
NUM_USERS  = 5000
OUTPUT_DIR = "./output_5k"
os.makedirs(OUTPUT_DIR, exist_ok=True)

JOURNEY_STEPS = [
    {"step": "landing_page",    "order": 1, "drop_off": 0.16},
    {"step": "sign_up_form",    "order": 2, "drop_off": 0.14},
    {"step": "email_verify",    "order": 3, "drop_off": 0.27},
    {"step": "profile_setup",   "order": 4, "drop_off": 0.61},  # <-- primary friction
    {"step": "payment_info",    "order": 5, "drop_off": 0.22},  # <-- secondary friction
    {"step": "plan_selection",  "order": 6, "drop_off": 0.18},
    {"step": "confirm_details", "order": 7, "drop_off": 0.08},
    {"step": "onboarding_done", "order": 8, "drop_off": 0.00},
]

DEVICES   = ["desktop", "mobile", "tablet"]
BROWSERS  = ["Chrome", "Safari", "Firefox", "Edge", "Samsung Internet"]
COUNTRIES = ["IN", "US", "GB", "DE", "AU", "SG", "AE", "CA", "FR", "BR", "JP", "ZA"]
CHANNELS  = ["organic_search", "paid_ads", "email", "direct", "referral", "social", "app_store"]
OS_LIST   = ["Windows 11", "macOS 14", "Ubuntu 22", "iOS 17", "Android 14", "Android 13"]
PLANS     = ["free", "starter", "pro", "enterprise"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def rand_ts(days_back=60):
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
    """Create a synthetic user with device, browser, OS, country, and acquisition channel."""
    return {
        "user_id":    str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "device":     random.choice(DEVICES),
        "browser":    random.choice(BROWSERS),
        "os":         random.choice(OS_LIST),
        "country":    random.choice(COUNTRIES),
        "channel":    random.choice(CHANNELS),
        "plan":       random.choice(PLANS),
    }


def write_json(filename, payload):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    kb = os.path.getsize(path) / 1024
    print(f"  [JSON] {filename:<50} {kb:>8.0f} KB")


def write_csv(filename, rows):
    """Write rows to CSV. Handles variable keys across rows (e.g. GA4 events)."""
    if not rows:
        return
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
            clean = {k: "" if v is None else str(v).replace("\n", " ").replace("\r", " ") for k, v in r.items()}
            writer.writerow({k: clean.get(k, "") for k in all_keys})
    kb = os.path.getsize(path) / 1024
    print(f"  [CSV]  {filename:<50} {kb:>8.0f} KB  ({len(rows):,} rows)")


# ── 1. GA4 / Clickstream ──────────────────────────────────────────────────────

def generate_ga4(users):
    """
    Full GA4 event stream for all users.
    Each user walks through the journey emitting:
      session_start → page_view → step_reached → click(s) → [step_abandoned]
    """
    events = []
    for u in users:
        ts = datetime.strptime(rand_ts(), "%Y-%m-%dT%H:%M:%SZ")

        events.append({
            "event_name":           "session_start",
            "user_id":              u["user_id"],
            "session_id":           u["session_id"],
            "timestamp":            ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "device_category":      u["device"],
            "browser":              u["browser"],
            "os":                   u["os"],
            "country":              u["country"],
            "traffic_source":       u["channel"],
            "journey_name":         "user_onboarding",
            "page_location":        "https://app.cji.io/",
            "engagement_time_msec": random.randint(800, 4000),
        })

        active = True
        for step_cfg in JOURNEY_STEPS:
            if not active:
                break
            ts += timedelta(seconds=random.randint(5, 220))
            is_f = step_cfg["step"] == "profile_setup"
            is_p = step_cfg["step"] == "payment_info"

            events.append({
                "event_name":           "page_view",
                "user_id":              u["user_id"],
                "session_id":           u["session_id"],
                "timestamp":            ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "device_category":      u["device"],
                "browser":              u["browser"],
                "os":                   u["os"],
                "country":              u["country"],
                "traffic_source":       u["channel"],
                "journey_name":         "user_onboarding",
                "step_name":            step_cfg["step"],
                "step_order":           step_cfg["order"],
                "page_location":        f"https://app.cji.io/{step_cfg['step'].replace('_', '-')}",
                "engagement_time_msec": random.randint(90000, 320000) if is_f
                                        else random.randint(15000, 100000) if is_p
                                        else random.randint(5000, 90000),
                "scroll_depth_pct":     random.randint(30, 100),
            })

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

            # More clicks = more retries = more frustration at friction step
            n_clicks = random.randint(6, 14) if is_f else random.randint(3, 8) if is_p else random.randint(1, 4)
            for _ in range(n_clicks):
                ts += timedelta(seconds=random.randint(2, 18))
                events.append({
                    "event_name":   "click",
                    "user_id":      u["user_id"],
                    "session_id":   u["session_id"],
                    "timestamp":    ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "journey_name": "user_onboarding",
                    "step_name":    step_cfg["step"],
                    "element_id":   random.choice(
                        ["submit_btn", "form_field", "cta_button",
                         "help_icon", "next_btn", "back_btn", "retry_link"]
                    ),
                })

            if random.random() < step_cfg["drop_off"]:
                ts += timedelta(seconds=random.randint(5, 90))
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
    Heatmap, form analytics, hesitation signals, and NPS data.
    One record per (user, step) pair for every step the user reached.
    """
    # Build a quick lookup: session_id → set of steps reached
    session_steps = {}
    for e in ga4_events:
        sid  = e.get("session_id")
        step = e.get("step_name")
        if sid and step:
            session_steps.setdefault(sid, set()).add(step)

    rows = []
    for u in users:
        steps = session_steps.get(u["session_id"], set())
        for step in steps:
            is_f = step == "profile_setup"
            is_e = step == "email_verify"
            is_p = step == "payment_info"

            rows.append({
                "session_id":                      u["session_id"],
                "user_id":                         u["user_id"],
                "step_name":                       step,
                "journey_name":                    "user_onboarding",
                "device":                          u["device"],
                "country":                         u["country"],
                "recording_url":                   f"https://hotjar.com/rec/{u['session_id'][:8]}",
                "heatmap_total_clicks":            random.randint(18, 90) if is_f else random.randint(2, 18),
                "heatmap_dead_clicks":             random.randint(10, 30) if is_f else random.randint(0, 4),
                "heatmap_rage_clicks":             random.randint(4, 18)  if is_f else random.randint(0, 2),
                "scroll_max_depth_pct":            random.randint(40, 100),
                "hesitation_first_interaction_ms": random.randint(9000, 30000) if is_f
                                                   else random.randint(3000, 10000) if is_e
                                                   else random.randint(400, 4000),
                "hesitation_mouse_idle_periods":   random.randint(3, 12) if is_f else random.randint(0, 2),
                "hesitation_cursor_backtrack":     random.randint(5, 16) if is_f else random.randint(0, 3),
                "form_field_drop_off":             random.choice(
                    ["address_line1", "postcode", "phone", "date_of_birth"]
                ) if is_f else ("card_number" if is_p else None),
                "form_refill_count":               random.randint(3, 9) if is_f else random.randint(0, 1),
                "form_time_sec":                   random.randint(95, 300) if is_f else random.randint(8, 60),
                "form_blank_submit_attempts":      random.randint(1, 5) if is_f else 0,
                "nps_score":                       random.randint(1, 5)  if is_f else random.randint(7, 10),
                "nps_comment":                     random.choice([
                    "Form keeps rejecting my postcode",
                    "Address field broken on mobile",
                    "No error message shown — just failed silently",
                    "Submit button does nothing, tried many times",
                    "Gave up after 10 minutes on profile page",
                    "Date picker impossible to use on mobile",
                    "Back button reset all my form data",
                    "Keyboard covers the submit button and I cannot scroll",
                ]) if is_f and random.random() < 0.45 else None,
            })
    return rows


# ── 3. UXCam ──────────────────────────────────────────────────────────────────

def generate_uxcam(users, ga4_events):
    """
    Mobile gesture, performance, and frustration signals.
    Only generated for mobile and tablet users.
    """
    session_steps = {}
    for e in ga4_events:
        sid  = e.get("session_id")
        step = e.get("step_name")
        if sid and step:
            session_steps.setdefault(sid, set()).add(step)

    rows   = []
    mobile = [u for u in users if u["device"] in ["mobile", "tablet"]]

    for u in mobile:
        steps = session_steps.get(u["session_id"], set())
        for step in steps:
            is_f = step == "profile_setup"
            rows.append({
                "session_id":                 u["session_id"],
                "user_id":                    u["user_id"],
                "step_name":                  step,
                "journey_name":               "user_onboarding",
                "device_type":                u["device"],
                "os":                         u["os"],
                "app_version":                "2.5.0",
                "country":                    u["country"],
                "screen_recording_url":       f"https://uxcam.com/s/{u['session_id'][:8]}/{step}",
                "gesture_total_taps":         random.randint(18, 65) if is_f else random.randint(3, 16),
                "gesture_swipe_count":        random.randint(2, 12),
                "gesture_pinch_zoom":         random.randint(2, 9) if is_f else 0,
                "gesture_long_press":         random.randint(1, 6) if is_f else 0,
                "crash_occurred":             random.random() < 0.06 if is_f else False,
                "anr_occurred":               random.random() < 0.04 if is_f else False,
                "screen_load_ms":             random.randint(2800, 7000) if is_f else random.randint(300, 1600),
                "api_latency_ms":             random.randint(900, 3500)  if is_f else random.randint(100, 600),
                "frame_drop_count":           random.randint(6, 22)  if is_f else random.randint(0, 3),
                "frustration_score":          round(random.uniform(0.62, 1.0), 2) if is_f
                                              else round(random.uniform(0.0, 0.32), 2),
                "repeated_taps_same_element": random.randint(5, 14) if is_f else random.randint(0, 2),
                "keyboard_dismiss_count":     random.randint(3, 9)  if is_f else random.randint(0, 1),
                "screen_completed":           random.random() > 0.61 if is_f else random.random() > 0.10,
                "time_on_screen_sec":         random.randint(88, 280) if is_f else random.randint(8, 65),
            })
    return rows


# ── 4. Surveys ────────────────────────────────────────────────────────────────

def generate_surveys(n=1000):
    """
    NPS, CSAT, CES, and open-ended survey responses.
    Negative sentiment is weighted toward friction steps.
    """
    NEG = [
        "The profile page form is completely broken on mobile",
        "Couldn't complete the address field — keeps rejecting valid inputs",
        "Took 15 minutes on profile page because of constant errors",
        "Postcode field doesn't accept my PIN code even though it is correct",
        "I gave up on profile setup — too many unexplained errors",
        "Why does it need a landline number? I only have mobile",
        "Submit button did nothing three times in a row",
        "Error says invalid input but gives no explanation of what is wrong",
        "Verification email never arrived even after 4 resend attempts",
        "Resend email button seems completely broken",
        "App said I was verified but still showed me as unverified",
        "Payment form rejected my card with no reason given",
        "Profile photo upload fails silently every time",
        "Date picker on profile page is impossible to use on mobile",
        "The back button resets my entire form and I lost all my data",
        "Nothing happens when I tap submit on profile form",
        "I wasted 20 minutes trying to get past the profile page",
        "Form validation errors are not descriptive at all",
        "The help tooltip covers the form field I need to fill",
        "Keyboard covers the submit button and I cannot scroll down",
    ]
    NEUT = [
        "Process was okay but could be faster",
        "Sign up took longer than expected",
        "Some steps felt unnecessary",
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
        "Simple and clear steps throughout",
    ]

    rows = []
    for _ in range(n):
        step = random.choices(
            ["profile_setup", "email_verify", "payment_info", "sign_up_form", "landing_page", "confirm_details"],
            weights=[0.45, 0.20, 0.14, 0.11, 0.06, 0.04],
        )[0]
        is_neg_step = step in ["profile_setup", "email_verify", "payment_info"]
        sentiment   = random.choices(
            ["negative", "neutral", "positive"],
            weights=[0.75, 0.15, 0.10] if is_neg_step else [0.10, 0.20, 0.70],
        )[0]

        csat = {"negative": random.randint(1, 2), "neutral": 3, "positive": random.randint(4, 5)}[sentiment]
        nps  = {"negative": random.randint(0, 4), "neutral": random.randint(5, 6), "positive": random.randint(8, 10)}[sentiment]

        rows.append({
            "survey_id":         str(uuid.uuid4()),
            "user_id":           str(uuid.uuid4()),
            "timestamp":         rand_ts(),
            "channel":           random.choice(["in_app_popup", "email_survey", "exit_survey", "push_notification"]),
            "journey_name":      "user_onboarding",
            "triggered_at_step": step,
            "survey_type":       random.choice(["NPS", "CSAT", "CES", "open_ended"]),
            "nps_score":         nps,
            "csat_score":        csat,
            "ces_score":         random.randint(1, 3) if sentiment == "negative" else random.randint(4, 7),
            "sentiment":         sentiment,
            "verbatim_comment":  random.choice(NEG)  if sentiment == "negative"
                                 else random.choice(NEUT) if sentiment == "neutral"
                                 else random.choice(POS),
            "device":            random.choice(DEVICES),
            "country":           random.choice(COUNTRIES),
            "completion_rate":   round(random.uniform(0.15, 0.65), 2) if sentiment == "negative"
                                 else round(random.uniform(0.70, 1.0), 2),
        })
    return rows


# ── 5. Support Tickets ────────────────────────────────────────────────────────

def generate_tickets(n=500):
    """
    Zendesk / Freshdesk style support tickets.
    Heavily weighted toward profile_setup friction step.
    """
    SUBJECTS = {
        "profile_setup": [
            "Cannot complete my profile — form error",
            "Profile setup page broken",
            "Address field not accepting valid input",
            "Stuck on profile setup step",
            "Error on profile form with no explanation",
            "Form validation bug on profile page",
            "Submit button on profile form unresponsive",
            "Profile photo upload failing",
            "Date picker broken on mobile",
            "Back button clears entire profile form",
        ],
        "email_verify": [
            "Verification email not received",
            "Resend email not working",
            "Stuck on email verification",
            "OTP not arriving in inbox",
            "Verification loop — verified but still stuck",
        ],
        "payment_info": [
            "Card rejected with no reason shown",
            "Payment form throwing error",
            "Cannot add card to account",
            "UPI payment option missing from checkout",
        ],
        "sign_up_form": [
            "Sign up button not responding",
            "Password requirements unclear",
            "Duplicate account error on sign up",
        ],
        "general": [
            "App crashes during onboarding",
            "Slow loading pages during sign up",
            "Cannot log in after account created",
        ],
    }

    rows = []
    for _ in range(n):
        step    = random.choices(
            ["profile_setup", "email_verify", "payment_info", "sign_up_form", "general"],
            weights=[0.52, 0.20, 0.14, 0.09, 0.05],
        )[0]
        is_crit = step == "profile_setup"
        created = rand_ts()
        res_hrs = random.randint(1, 96)
        resolved = (
            datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=res_hrs)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        rows.append({
            "ticket_id":             f"TKT-{random.randint(10000, 99999)}",
            "user_id":               str(uuid.uuid4()),
            "created_at":            created,
            "resolved_at":           resolved if random.random() > 0.22 else None,
            "journey_name":          "user_onboarding",
            "step_name":             step,
            "subject":               random.choice(SUBJECTS.get(step, SUBJECTS["general"])),
            "category":              "bug_report" if is_crit else random.choice(
                ["bug_report", "usability_issue", "feature_request", "account_help"]
            ),
            "priority":              random.choice(["high", "critical"]) if is_crit
                                     else random.choice(["low", "medium", "high"]),
            "status":                random.choice(["resolved", "in_progress", "escalated", "closed_no_fix"]),
            "channel":               random.choice(["in_app_chat", "email", "whatsapp", "phone", "twitter"]),
            "device":                random.choice(DEVICES),
            "country":               random.choice(COUNTRIES),
            "agent_notes":           f"User stuck at {step}. Likely form validation issue." if is_crit
                                     else "Standard support interaction.",
            "resolution_time_hrs":   res_hrs,
            "csat_after_resolution": random.randint(1, 3) if is_crit else random.randint(3, 5),
            "tags":                  ["form_bug", "profile_setup", "high_volume"] if is_crit else [step],
            "escalated":             is_crit and random.random() < 0.32,
            "reopened":              random.random() < 0.12 if is_crit else False,
        })
    return rows


# ── Combined flat signal CSV ──────────────────────────────────────────────────

def build_combined_signals(hotjar, uxcam, surveys, tickets):
    """
    Union of all non-clickstream sources into one flat CSV.
    Ideal for direct pandas ingestion by the Layer 2 pipeline.
    Columns: source, user_id, session_id, step_name, journey_name,
             device, country, hesitation_ms, rage_clicks, dead_clicks,
             form_refill_count, form_time_sec, nps_score,
             frustration_score, sentiment, verbatim
    """
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
    return flat


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\nCJI Synthetic Dataset Generator — {NUM_USERS:,} users")
    print("=" * 58)

    print(f"\nGenerating {NUM_USERS:,} user profiles...")
    users = [new_user() for _ in range(NUM_USERS)]

    print("Generating GA4 clickstream (all users × all steps)...")
    ga4 = generate_ga4(users)
    print(f"  {len(ga4):,} events")

    print("Generating Hotjar sessions (per user per step)...")
    hotjar = generate_hotjar(users, ga4)
    print(f"  {len(hotjar):,} records")

    print("Generating UXCam sessions (mobile/tablet users only)...")
    uxcam = generate_uxcam(users, ga4)
    print(f"  {len(uxcam):,} records")

    print("Generating 1,000 survey responses...")
    surveys = generate_surveys(n=1000)
    print(f"  {len(surveys):,} responses")

    print("Generating 500 support tickets...")
    tickets = generate_tickets(n=500)
    print(f"  {len(tickets):,} tickets")

    print("Building combined signals flat view...")
    combined = build_combined_signals(hotjar, uxcam, surveys, tickets)
    print(f"  {len(combined):,} rows")

    # Master bundle JSON
    master = {
        "meta": {
            "project":              "Customer Journey Intelligence — PoC v2",
            "generated_at":        "2026-03-22T12:00:00Z",
            "journey":             "user_onboarding",
            "total_users":         NUM_USERS,
            "friction_injected_at":"profile_setup",
            "journey_steps":       [s["step"] for s in JOURNEY_STEPS],
            "data_sources":        ["GA4", "Hotjar", "UXCam", "Surveys", "Support Tickets"],
            "note":                "Synthetic data for CJI PoC. Friction deliberately injected at profile_setup.",
        },
        "ga4_clickstream": {"total": len(ga4),     "events":    ga4},
        "hotjar":          {"total": len(hotjar),  "sessions":  hotjar},
        "uxcam":           {"total": len(uxcam),   "sessions":  uxcam},
        "surveys":         {"total": len(surveys), "responses": surveys},
        "support_tickets": {"total": len(tickets), "tickets":   tickets},
    }

    print(f"\nWriting files to ./{OUTPUT_DIR}/")
    print("-" * 58)
    write_json("all_sources_bundle.json",  master)
    write_json("ga4_clickstream.json",     {"source": "GA4",     "total_events":    len(ga4),     "events":    ga4})
    write_json("hotjar.json",              {"source": "Hotjar",  "total_sessions":  len(hotjar),  "sessions":  hotjar})
    write_json("uxcam.json",               {"source": "UXCam",   "total_sessions":  len(uxcam),   "sessions":  uxcam})
    write_json("surveys.json",             {"source": "Surveys", "total_responses": len(surveys), "responses": surveys})
    write_json("support_tickets.json",     {"source": "Tickets", "total_tickets":   len(tickets), "tickets":   tickets})
    write_csv("ga4_clickstream.csv",       ga4)
    write_csv("hotjar.csv",                hotjar)
    write_csv("uxcam.csv",                 uxcam)
    write_csv("surveys.csv",               surveys)
    write_csv("support_tickets.csv",       tickets)
    write_csv("combined_signals.csv",      combined)

    total = len(ga4) + len(hotjar) + len(uxcam) + len(surveys) + len(tickets)
    print(f"\n{'=' * 58}")
    print(f"  Done!")
    print(f"  Total records generated : {total:,}")
    print(f"  Output directory        : ./{OUTPUT_DIR}/")
    print(f"  Files created           : 12 (6 JSON + 6 CSV)")
    print(f"{'=' * 58}\n")


if __name__ == "__main__":
    main()
