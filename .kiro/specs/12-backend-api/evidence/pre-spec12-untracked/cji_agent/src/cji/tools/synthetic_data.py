"""
CJI Synthetic Data Generator
=============================
Generates realistic synthetic journey events for demo mode.

Output: Parquet file at data/events.parquet.

Usage:
  python -m cji.tools.synthetic_data        # generates to the default path
  cji --mode demo --generate-data           # recommended entry point
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from cji.config import EVENTS_PARQUET, JOURNEY_CONFIG, logger
from cji.settings import get_settings

# ── Constants ─────────────────────────────────────────────────────────────────

ALLOWED_EVENT_TYPES: frozenset[str] = frozenset({
    "page_view",
    "click",
    "form_submit",
    "error",
    "rage_click",
    "abandon",
    "step_complete",
    "identify",
})

# Exact profiles — tests depend on these values. Do NOT change without updating tests.
# Keys MUST match JOURNEY_CONFIG["steps"] exactly.
STEP_PROFILES: dict[str, dict] = {
    "landing_page": {
        "drop_rate":   0.15,    # 15% of users abandon at this step
        "avg_dwell_s": 12,      # average time on step (seconds)
        "error_rate":  0.02,    # 2% of users encounter errors
        "rage_rate":   0.02,    # 2% of users rage-click
        "retry_rate":  0.01,    # avg retries per user
        "click_count": 2,       # avg clicks per user on this step
    },
    "sign_up_form": {
        "drop_rate":   0.25,
        "avg_dwell_s": 45,
        "error_rate":  0.18,
        "rage_rate":   0.08,
        "retry_rate":  0.30,
        "click_count": 5,
    },
    "email_verification": {
        "drop_rate":   0.42,    # highest friction — 42% abandon
        "avg_dwell_s": 180,     # 3 minutes average — users are stuck
        "error_rate":  0.35,    # 35% hit errors (expired tokens, etc.)
        "rage_rate":   0.25,    # 25% rage-click
        "retry_rate":  1.20,    # avg 1.2 retries per user
        "click_count": 4,
    },
    "profile_setup": {
        "drop_rate":   0.20,
        "avg_dwell_s": 60,
        "error_rate":  0.08,
        "rage_rate":   0.05,
        "retry_rate":  0.15,
        "click_count": 8,
    },
    "plan_selection": {
        "drop_rate":   0.30,    # 30% drop — users hesitate on pricing
        "avg_dwell_s": 90,      # 1.5 min comparing plans
        "error_rate":  0.05,
        "rage_rate":   0.04,
        "retry_rate":  0.10,
        "click_count": 6,
    },
    "payment_info": {
        "drop_rate":   0.38,    # high friction — payment anxiety
        "avg_dwell_s": 120,     # 2 min on payment form
        "error_rate":  0.22,    # card validation errors
        "rage_rate":   0.15,
        "retry_rate":  0.45,
        "click_count": 7,
    },
    "confirm_details": {
        "drop_rate":   0.08,    # low — users mostly confirm
        "avg_dwell_s": 20,
        "error_rate":  0.03,
        "rage_rate":   0.02,
        "retry_rate":  0.05,
        "click_count": 2,
    },
    "onboarding_done": {
        "drop_rate":   0.02,    # nearly zero — completion screen
        "avg_dwell_s": 8,
        "error_rate":  0.01,
        "rage_rate":   0.01,
        "retry_rate":  0.00,
        "click_count": 1,
    },
}

# Error codes used in error event metadata — must cover all STEP_PROFILES keys
ERROR_CODES: dict[str, list[str]] = {
    "landing_page":       ["UNDEFINED"],
    "sign_up_form":       ["EMAIL_ALREADY_EXISTS", "INVALID_PASSWORD", "FIELD_REQUIRED"],
    "email_verification": ["TOKEN_EXPIRED", "TOKEN_INVALID", "TOKEN_NOT_FOUND", "RESEND_FAILED"],
    "profile_setup":      ["UPLOAD_FAILED", "INVALID_FORMAT", "SIZE_LIMIT_EXCEEDED"],
    "plan_selection":     ["PLAN_UNAVAILABLE", "COUPON_INVALID"],
    "payment_info":       ["CARD_DECLINED", "INVALID_CARD_NUMBER", "CVV_MISMATCH", "EXPIRED_CARD"],
    "confirm_details":    ["SUBMISSION_FAILED", "SESSION_EXPIRED"],
    "onboarding_done":    ["TIMEOUT", "NETWORK_ERROR"],
}


# ── Generator ─────────────────────────────────────────────────────────────────

def generate_demo_data(
    n_sessions: int = 2000,
    seed: int = 42,
    output_path: Path = EVENTS_PARQUET,
) -> Path:
    """
    Generate synthetic journey events and save to Parquet.

    Args:
        n_sessions: Number of simulated user sessions (unique users).
        seed:       Random seed for reproducibility (same seed → same output).
        output_path: Where to write the Parquet file.

    Returns:
        Path to the written Parquet file.
    """
    Faker.seed(seed)
    random.seed(seed)

    journey_name = JOURNEY_CONFIG["name"]
    steps        = JOURNEY_CONFIG["steps"]
    all_events:  list[dict[str, Any]] = []

    now      = datetime.now(timezone.utc)
    base_ts  = now - timedelta(days=30)
    
    # Pools for analytics
    existing_users = []
    REGIONS = ["North America", "Europe", "Asia Pacific", "South America", "Middle East & Africa"]
    DEVICES = ["Desktop", "Mobile", "Tablet"]

    for _ in range(n_sessions):
        is_returning = random.random() < 0.25 and len(existing_users) > 0
        if is_returning:
            user_id = random.choice(existing_users)
        else:
            user_id = str(uuid.uuid4())
            existing_users.append(user_id)
            
        session_id = str(uuid.uuid4())
        session_region = random.choices(REGIONS, weights=[0.4, 0.3, 0.15, 0.1, 0.05])[0]
        session_device = random.choices(DEVICES, weights=[0.55, 0.40, 0.05])[0]
        
        # Base metadata applied to every event
        session_meta = {
            "region": session_region,
            "device": session_device,
        }

        # Assign a random start time within the 30-day window
        session_start = base_ts + timedelta(seconds=random.randint(0, 30 * 24 * 3600))
        current_ts = session_start

        for step_id in steps:
            profile = STEP_PROFILES.get(step_id, {})
            drop_rate  = profile.get("drop_rate", 0.10)
            avg_dwell  = profile.get("avg_dwell_s", 15)
            error_rate = profile.get("error_rate", 0.05)
            rage_rate  = profile.get("rage_rate", 0.02)
            retry_rate = profile.get("retry_rate", 0.05)
            click_count = profile.get("click_count", 2)

            # Dwell time: normally distributed around avg_dwell_s
            dwell_s = max(1, int(random.gauss(avg_dwell, avg_dwell * 0.4)))
            dwell_ms = dwell_s * 1000

            # ── page_view ──────────────────────────────────────────────────
            all_events.append(_make_event(
                user_id=user_id, session_id=session_id,
                journey_id=journey_name, step_id=step_id,
                event_type="page_view",
                timestamp=current_ts,
                duration_ms=0,
                metadata={**session_meta},
            ))
            current_ts += timedelta(seconds=1)

            # ── clicks ─────────────────────────────────────────────────────
            num_clicks = max(1, int(random.gauss(click_count, 1)))
            for _ in range(num_clicks):
                # Simulated viewport sizes and click coordinates
                vp_w = 1920 if session_device == "Desktop" else (390 if session_device == "Mobile" else 820)
                vp_h = 1080 if session_device == "Desktop" else (844 if session_device == "Mobile" else 1180)
                cx = random.randint(10, vp_w - 10)
                cy = random.randint(10, vp_h - 10)
                all_events.append(_make_event(
                    user_id=user_id, session_id=session_id,
                    journey_id=journey_name, step_id=step_id,
                    event_type="click",
                    timestamp=current_ts,
                    duration_ms=random.randint(50, 500),
                    metadata={**session_meta, "element": "button", "click_x": cx, "click_y": cy, "viewport_width": vp_w, "viewport_height": vp_h},
                ))
                current_ts += timedelta(milliseconds=random.randint(500, 3000))

            # ── errors ─────────────────────────────────────────────────────
            if random.random() < error_rate:
                codes = ERROR_CODES.get(step_id, ["UNKNOWN"])
                num_retries = max(0, int(random.gauss(retry_rate, retry_rate * 0.5)))
                for retry_num in range(max(1, num_retries)):
                    all_events.append(_make_event(
                        user_id=user_id, session_id=session_id,
                        journey_id=journey_name, step_id=step_id,
                        event_type="error",
                        timestamp=current_ts,
                        duration_ms=0,
                        metadata={
                            **session_meta,
                            "error_code":  random.choice(codes),
                            "retry_count": retry_num,
                            "message":     f"Error on {step_id}",
                        },
                    ))
                    current_ts += timedelta(seconds=random.randint(2, 15))

            # ── rage clicks ────────────────────────────────────────────────
            if random.random() < rage_rate:
                vp_w = 1920 if session_device == "Desktop" else (390 if session_device == "Mobile" else 820)
                vp_h = 1080 if session_device == "Desktop" else (844 if session_device == "Mobile" else 1180)
                cx = random.randint(10, vp_w - 10)
                cy = random.randint(10, vp_h - 10)
                all_events.append(_make_event(
                    user_id=user_id, session_id=session_id,
                    journey_id=journey_name, step_id=step_id,
                    event_type="rage_click",
                    timestamp=current_ts,
                    duration_ms=0,
                    metadata={
                        **session_meta,
                        "click_count":   random.randint(3, 8),
                        "element_tag":   "BUTTON",
                        "element_id":    f"{step_id}-submit",
                        "element_class": "btn btn-primary",
                        "click_x": cx, "click_y": cy, "viewport_width": vp_w, "viewport_height": vp_h
                    },
                ))
                current_ts += timedelta(seconds=1)

            # ── abandon (user leaves this step) ───────────────────────────
            if random.random() < drop_rate:
                all_events.append(_make_event(
                    user_id=user_id, session_id=session_id,
                    journey_id=journey_name, step_id=step_id,
                    event_type="abandon",
                    timestamp=current_ts,
                    duration_ms=dwell_ms,
                    metadata={**session_meta, "step": step_id, "reason": "beforeunload"},
                ))
                break  # user does not proceed further

            # ── step_complete (user moves to next step) ───────────────────
            # Form submit first (if applicable)
            if step_id in ("sign_up_form", "profile_setup"):
                all_events.append(_make_event(
                    user_id=user_id, session_id=session_id,
                    journey_id=journey_name, step_id=step_id,
                    event_type="form_submit",
                    timestamp=current_ts,
                    duration_ms=random.randint(100, 2000),
                    metadata={**session_meta, "form_id": f"{step_id}-form"},
                ))
                current_ts += timedelta(seconds=1)

            next_s = _next_step(steps, step_id)
            comp_meta = {**session_meta, "next_step": next_s}
            
            # Revenue simulation for the final step (e.g. completion/purchase equivalent)
            if step_id == "completion":
                comp_meta["purchase_value"] = round(random.uniform(19.99, 149.99), 2)

            all_events.append(_make_event(
                user_id=user_id, session_id=session_id,
                journey_id=journey_name, step_id=step_id,
                event_type="step_complete",
                timestamp=current_ts,
                duration_ms=dwell_ms,
                metadata=comp_meta,
            ))
            current_ts += timedelta(seconds=random.randint(1, 5))

    # ── Write Parquet ─────────────────────────────────────────────────────────
    df = pd.DataFrame(all_events)

    # Ensure all required columns exist with correct dtypes
    df["event_id"]    = df["event_id"].astype(str)
    df["user_id"]     = df["user_id"].astype(str)
    df["session_id"]  = df["session_id"].astype(str)
    df["journey_id"]  = df["journey_id"].astype(str)
    df["step_id"]     = df["step_id"].astype(str)
    df["event_type"]  = df["event_type"].astype(str)
    df["timestamp"]   = pd.to_datetime(df["timestamp"], utc=True)
    df["duration_ms"] = df["duration_ms"].astype(int)
    df["url"]         = df["url"].astype(str)
    df["metadata"]    = df["metadata"].apply(json.dumps)  # Store as JSON string

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False, compression="snappy")

    # Upload to Supabase/PostgreSQL only when a database is configured, and never
    # in the test environment (Spec 04): this replaces the demo_events table.
    settings = get_settings()
    db_url = settings.database.url_value()
    if settings.app.env == "test":
        logger.info("[synthetic_data] CJI_ENV=test: PostgreSQL upload skipped.")
    elif not db_url:
        logger.info("[synthetic_data] DATABASE_URL / SUPABASE_DATABASE_URL not set: PostgreSQL upload skipped.")
    else:
        try:
            engine = create_engine(db_url)
            df_sql = df.copy()
            # sqlalchemy works better when json/dict are just uploaded
            df_sql.to_sql(name="demo_events", con=engine, if_exists="replace", index=False)
            logger.info(f"[synthetic_data] Uploaded {len(df):,} events to Supabase 'demo_events' table.")
        except SQLAlchemyError as e:
            logger.error(f"[synthetic_data] Upload to PostgreSQL demo_events failed: {type(e).__name__}", exc_info=True)

    logger.info(
        f"[synthetic_data] Generated {len(df):,} events from {n_sessions:,} sessions "
        f"→ {output_path}"
    )
    return output_path


# ── Private Helpers ───────────────────────────────────────────────────────────

def _make_event(
    user_id:     str,
    session_id:  str,
    journey_id:  str,
    step_id:     str,
    event_type:  str,
    timestamp:   datetime,
    duration_ms: int,
    metadata:    dict,
) -> dict[str, Any]:
    """Build a complete event record dict."""
    return {
        "event_id":    str(uuid.uuid4()),
        "user_id":     user_id,
        "session_id":  session_id,
        "journey_id":  journey_id,
        "step_id":     step_id,
        "event_type":  event_type,
        "timestamp":   timestamp,
        "duration_ms": max(0, duration_ms),
        "url":         f"https://app.example.com/{journey_id}/{step_id}",
        "metadata":    metadata,
    }


def _next_step(steps: list[str], current: str) -> str:
    """Return the step that follows current in the journey, or 'end'."""
    try:
        idx = steps.index(current)
        return steps[idx + 1] if idx + 1 < len(steps) else "end"
    except ValueError:
        return "end"


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate CJI synthetic demo data")
    parser.add_argument("--sessions", type=int, default=2000, help="Number of user sessions")
    parser.add_argument("--seed",     type=int, default=42,   help="Random seed")
    parser.add_argument("--output",   type=str, default=str(EVENTS_PARQUET), help="Output path")
    args = parser.parse_args(argv)

    out = generate_demo_data(
        n_sessions=args.sessions,
        seed=args.seed,
        output_path=Path(args.output),
    )
    print(f"[OK] Generated data -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
