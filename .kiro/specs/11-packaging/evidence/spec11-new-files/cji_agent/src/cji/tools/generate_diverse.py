"""
Optional: generate a large, high-friction demo dataset (about 1M events).

Run:  cji-generate-diverse   (or `python generate_diverse.py` from cji_agent/)
Overwrites data/events.parquet in the runtime home (the default demo data, also read
by the golden snapshot) and, when a database URL is configured outside CJI_ENV=test,
replaces the demo_events table, as `cji --mode demo --generate-data` does.
Restore the default data with:  cji --mode demo --generate-data
"""
from __future__ import annotations

import argparse

from cji.tools.synthetic_data import ERROR_CODES, STEP_PROFILES, generate_demo_data

# Create highly diverse and problematic step profiles with very specific "personas" of friction
diverse_profiles = {
    "landing_page": {
        "drop_rate": 0.08,       
        "avg_dwell_s": 8,        
        "error_rate": 0.05,      
        "rage_rate": 0.25,       # High rage clicks, meaning users click aggressively on something unclickable
        "retry_rate": 0.0,
        "click_count": 5,
    },
    "sign_up_form": {
        "drop_rate": 0.45,       # Massive drop off
        "avg_dwell_s": 120,      # Takes way too long, meaning friction in form fields
        "error_rate": 0.55,      # Huge error rate
        "rage_rate": 0.10,
        "retry_rate": 3.0,       # People try to fix their password or captcha over and over
        "click_count": 8,
    },
    "email_verification": {
        "drop_rate": 0.60,       # Most people never verify (loss of leads)
        "avg_dwell_s": 300,      # Huge dwell time (users tab away)
        "error_rate": 0.35,      # Token issues
        "rage_rate": 0.30,       # Frustrated clicking "Resend Token" repeatedly
        "retry_rate": 2.5,
        "click_count": 6,
    },
    "profile_setup": {
        "drop_rate": 0.30,
        "avg_dwell_s": 90,
        "error_rate": 0.40,      # Uploads keep failing
        "rage_rate": 0.60,       # Extreme rage clicking on file upload or "Save"
        "retry_rate": 5.0,       # Retrying uploads many times
        "click_count": 10,
    },
    "first_action": {
        "drop_rate": 0.15,
        "avg_dwell_s": 45,
        "error_rate": 0.20,      # Permission or state issues
        "rage_rate": 0.05,
        "retry_rate": 1.0,
        "click_count": 4,
    },
    "completion": {
        "drop_rate": 0.02,
        "avg_dwell_s": 15,
        "error_rate": 0.10,      # Weird final step crashes
        "rage_rate": 0.05,
        "retry_count": 0.0,
        "retry_rate":  0.5,
        "click_count": 2,
    },
}

diverse_errors = {
    "landing_page":       ["HERO_IMAGE_NOT_LOADED", "CORS_ERROR_ON_TRACKING"],
    "sign_up_form":       ["OAUTH_PROVIDER_TIMEOUT", "PASSWORD_POLICY_TOO_STRICT", "CAPTCHA_FAILED_INVISIBLE", "RATE_LIMIT_EXCEEDED"],
    "email_verification": ["GMAIL_BOUNCE", "SPAM_FILTER_REJECTED", "TOKEN_ALREADY_USED_RACE_CONDITION"],
    "profile_setup":      ["IMAGE_TOO_LARGE_CLIENT_SIDE_FREEZE", "UNSUPPORTED_FILE_TYPE_HEIC", "S3_UPLOAD_TIMEOUT"],
    "first_action":       ["ONBOARDING_MODAL_Z_INDEX_BUG", "API_503_SERVICE_UNAVAILABLE"],
    "completion":         ["STRIPE_WEBHOOK_DELAYED", "CONFIRMATION_EMAIL_FAILED"],
}

def apply_profiles() -> None:
    """Patch the generator's step profiles and error codes with the high-friction personas."""
    for step, profile in diverse_profiles.items():
        if step in STEP_PROFILES:
            STEP_PROFILES[step].update(profile)
    for step, codes in diverse_errors.items():
        if step in ERROR_CODES:
            ERROR_CODES[step] = codes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cji-generate-diverse",
        description="Generate a large, high-friction demo dataset (about 1M events) into data/events.parquet.",
    )
    # 45000 sessions * ~23 events/session ~= 1,000,000+ records
    parser.add_argument("--sessions", type=int, default=45000, help="number of user sessions (default: 45000)")
    parser.add_argument("--seed", type=int, default=12345, help="random seed (default: 12345)")
    args = parser.parse_args(argv)
    apply_profiles()
    print("Generating 1M+ records of diverse, highly-insightful synthetic data...")
    out_path = generate_demo_data(n_sessions=args.sessions, seed=args.seed)
    print(f"Done! Written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
