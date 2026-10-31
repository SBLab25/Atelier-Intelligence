"""
Spec 14 (OD-142, F-70, F-71, F-77): measure how Streamlit's own SQL panels differ from the engine on the same events.

Streamlit's `load_journey_df` and `compute_friction_from_db` run PostgreSQL SQL over `tracking_events` (no time window).
The gate has no PostgreSQL (the configured database is the real Supabase project), so the two aggregations are
repeated here in pandas over the demo Parquet events, which have the same columns. The engine side is
`services.analytics` with the API's default window and with a window covering all data. Report only: no pass/fail.

usage: streamlit_diff.py --out DIR [--journey user_onboarding]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def streamlit_journey(df: Any) -> dict[str, dict[str, float]]:
    """dashboard.load_journey_df: per step distinct users, abandon count, mean duration (s), error and rage counts."""
    out: dict[str, dict[str, float]] = {}
    for step, g in df.groupby("step_id"):
        out[str(step)] = {
            "users_entered": int(g["user_id"].nunique()),
            "dropped": int((g["event_type"] == "abandon").sum()),
            "avg_dwell_s": float(g["duration_ms"].fillna(0).mean() / 1000.0) if len(g) else 0.0,
            "avg_errors": int((g["event_type"] == "error").sum()),           # a count, labelled "Avg Errors" (F-77)
            "rage_clicks": int((g["event_type"] == "rage_click").sum()),
        }
    return out


def streamlit_friction(df: Any) -> dict[str, dict[str, Any]]:
    """dashboard.compute_friction_from_db: drop*0.40 + error*0.30 + rage*0.20 + dwell penalty*0.10, critical > 50."""
    out: dict[str, dict[str, Any]] = {}
    for step, g in df.groupby("step_id"):
        n = max(int(g["user_id"].nunique()), 1)
        drop = min((g["event_type"] == "abandon").sum() / n * 100, 100)
        error = min((g["event_type"] == "error").sum() / n * 100, 100)
        rage = min((g["event_type"] == "rage_click").sum() / n * 100, 100)
        views = g[g["event_type"].isin(["page_view", "step_complete"])]["duration_ms"]
        dwell_s = float(views.mean() / 1000.0) if len(views) else 0.0
        penalty = max(0, (5 - dwell_s)) * 4 if dwell_s < 5 else 0
        score = min(round(drop * 0.40 + error * 0.30 + rage * 0.20 + penalty * 0.10, 1), 100)
        out[str(step)] = {"score": float(score), "is_critical": bool(score > 50)}
    return out


def main(argv: list[str]) -> int:
    import pandas as pd

    from cji.repositories import event_repository
    from cji.services import analytics, journeys
    from cji.settings import get_settings

    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--journey", default="user_onboarding")
    args = p.parse_args(argv)
    settings = get_settings()
    df = pd.read_parquet(settings.storage.events_parquet)
    journey = journeys.get_journey(settings, args.journey)
    if journey is None:
        print(f"journey {args.journey} not configured", file=sys.stderr)
        return 1
    df = df[df["journey_id"].astype(str) == journey.name] if "journey_id" in df.columns else df
    s_journey, s_friction = streamlit_journey(df), streamlit_friction(df)
    threshold = settings.budgets.friction_score_threshold
    repo = event_repository(settings)
    engine: dict[str, Any] = {}
    try:
        for label, days in (("api_default_30d", 30), ("all_data_365d", 365)):
            window = analytics.window_for(days, None)
            metrics = analytics.journey_metrics(repo, journey, window)
            friction = analytics.journey_friction(repo, journey, window, threshold)
            engine[label] = {
                "steps": {m["step_id"]: m for m in metrics.steps},
                "funnel": {f["step_id"]: f for f in metrics.funnel},
                "friction": {f["step_id"]: f for f in friction["scores"]},
            }
    finally:
        repo.close()

    rows = []
    for step in journey.steps:
        s_j, s_f = s_journey.get(step, {}), s_friction.get(step, {})
        for label, e in engine.items():
            m, f, fun = e["steps"].get(step, {}), e["friction"].get(step, {}), e["funnel"].get(step, {})
            rows.append({
                "step": step, "engine_window": label,
                "users_streamlit": s_j.get("users_entered"), "users_engine_unique": m.get("unique_users"),
                "users_engine_funnel": fun.get("users"),
                "errors_streamlit_count": s_j.get("avg_errors"), "error_rate_engine_pct": m.get("error_rate_pct"),
                "dwell_streamlit_s": round(s_j["avg_dwell_s"], 1) if s_j else None,
                "dwell_engine_s": round(m["avg_dwell_ms"] / 1000, 1) if m else None,
                "friction_streamlit_fallback": s_f.get("score"), "critical_streamlit_fallback": s_f.get("is_critical"),
                "friction_engine": f.get("score"), "critical_engine": f.get("is_critical"),
            })
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "streamlit-diff.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    header = ("| Step | Engine window | Users (Streamlit) | Unique users (engine) | Errors (Streamlit count) | "
              "Error rate % (engine) | Dwell s (Streamlit) | Dwell s (engine) | Friction (Streamlit fallback, critical >50) | "
              f"Friction (engine, critical >= {threshold}) |")
    lines = [f"Events: {settings.storage.events_parquet.name}, {len(df)} rows, journey {journey.name}.", "", header,
             "|" + "---|" * 10]
    for r in rows:
        lines.append(
            f"| {r['step']} | {r['engine_window']} | {r['users_streamlit']} | {r['users_engine_unique']} | "
            f"{r['errors_streamlit_count']} | {r['error_rate_engine_pct']} | {r['dwell_streamlit_s']} | "
            f"{r['dwell_engine_s']} | {r['friction_streamlit_fallback']} ({'critical' if r['critical_streamlit_fallback'] else 'not critical'}) | "
            f"{r['friction_engine']} ({'critical' if r['critical_engine'] else 'not critical'}) |")
    (args.out / "streamlit-diff.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
