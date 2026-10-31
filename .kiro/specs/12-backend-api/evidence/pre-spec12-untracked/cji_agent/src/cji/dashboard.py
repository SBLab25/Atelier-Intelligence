"""
CJI Intelligence Hub — Dashboard
==================================
Style: Inter font, #F9FAFB, clean white cards
Data:  PostgreSQL (DATABASE_URL / SUPABASE_DATABASE_URL)  +  data/last_run.json  (written by `cji --run`)
Start: cji-dashboard (or `streamlit run dashboard.py` from cji_agent/)
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import html
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from pandas.errors import DatabaseError as PandasDatabaseError
from sqlalchemy import create_engine
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from cji.repositories.base import RepositoryError, describe_failure
from cji.settings import ConfigError, get_settings, require

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CJI Intelligence Hub",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Configuration (Spec 04): validated once; shown in the page on error ────────
try:
    SETTINGS = require(get_settings(), "dashboard")
except ConfigError as exc:
    st.error(f"Configuration error\n\n```\n{exc}\n```")
    st.stop()

# DATABASE_URL, or SUPABASE_DATABASE_URL when DATABASE_URL is unset
DB_URL = SETTINGS.database.url_value()
try:
    engine = create_engine(DB_URL, pool_pre_ping=True) if DB_URL else None
except (ArgumentError, ImportError) as exc:
    st.error(f"The database URL cannot be used ({type(exc).__name__}). Check DATABASE_URL / SUPABASE_DATABASE_URL.")
    engine = None


class DataLoadError(Exception):
    """A dashboard panel could not read its data (Spec 06, CL-08). The message has no credentials."""

    def __init__(self, panel: str, cause: BaseException):
        detail = RepositoryError(panel, describe_failure(cause)).message
        super().__init__(f"{panel}: {type(cause).__name__}: {detail}")
        self.panel = panel


_LOAD_FAILURES: list[str] = []


def _flush_load_failures() -> None:
    """Show the collected load failures as one warning."""
    if _LOAD_FAILURES:
        st.warning("Could not load: " + "; ".join(dict.fromkeys(_LOAD_FAILURES)))
        _LOAD_FAILURES.clear()


def _load(panel, loader, *args, default=None, flush=False):
    """Call a cached loader. A DataLoadError is recorded for the warning and `default` is returned."""
    try:
        return loader(*args)
    except DataLoadError as exc:
        _LOAD_FAILURES.append(str(exc))
        if flush:
            _flush_load_failures()
        return default

# ── Project paths ──────────────────────────────────────────────────────────────
HOME          = SETTINGS.storage.home       # runtime home (CJI_HOME), Spec 11
DATA_DIR      = SETTINGS.storage.data_dir
REPORTS_DIR   = SETTINGS.storage.reports_dir
LAST_RUN_FILE = SETTINGS.storage.last_run_file
PARQUET_PATH  = SETTINGS.storage.events_parquet

# ── CSS — card style ─────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
    background-color: #F9FAFB !important;
}

section[data-testid="stSidebar"] {
    background-color: #F1F5F9 !important;
    border-right: 1px solid #E2E8F0 !important;
}

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1400px !important;
}

/* ── Cards ── */
.metric-card {
    background: white;
    padding: 24px;
    border-radius: 12px;
    border: 1px solid #E5E7EB;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    margin-bottom: 0;
}
.section-card {
    background: white;
    padding: 24px;
    border-radius: 12px;
    border: 1px solid #E5E7EB;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    margin-bottom: 20px;
}
.insight-card {
    background: white;
    padding: 18px 20px;
    border-radius: 12px;
    border: 1px solid #E5E7EB;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

/* ── Tags ── */
.tag-critical { color: #DC2626; background: #FEF2F2; padding: 3px 10px; border-radius: 20px; font-weight: 700; font-size: 11px; }
.tag-urgent   { color: #D97706; background: #FFFBEB; padding: 3px 10px; border-radius: 20px; font-weight: 700; font-size: 11px; }
.tag-minor    { color: #6B7280; background: #F3F4F6; padding: 3px 10px; border-radius: 20px; font-weight: 700; font-size: 11px; }

/* ── Misc ── */
#MainMenu {visibility: hidden;}
footer    {visibility: hidden;}
header[data-testid="stHeader"] {display: none !important;}
</style>
""", unsafe_allow_html=True)


# ── Data helpers ───────────────────────────────────────────────────────────────
@st.cache_data(ttl=15)
def load_last_run():
    if LAST_RUN_FILE.exists():
        try:
            return json.loads(LAST_RUN_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DataLoadError("Last run (data/last_run.json)", exc) from exc
    return None


def get_from_clause(sel_property):
    te = "SELECT user_id, session_id, journey_id, step_id, event_type, timestamp, duration_ms, metadata::jsonb FROM tracking_events"
    le = "SELECT user_id, session_id, journey_name AS journey_id, step_id, event_type, timestamp, 0 AS duration_ms, metadata::jsonb FROM live_events"
    de = "SELECT user_id, session_id, journey_id, step_id, event_type, timestamp, duration_ms, metadata::jsonb FROM demo_events"
    if sel_property == "Live_event track":
        return f"({le}) AS unified_events"
    elif sel_property == "tracking_event track":
        return f"({te}) AS unified_events"
    elif sel_property == "demo_events track":
        return f"({de}) AS unified_events"
    else:
        return f"({te} UNION ALL {le} UNION ALL {de}) AS unified_events"

@st.cache_data(ttl=60)
def get_journeys():
    return ["Live_event track", "tracking_event track", "demo_events track"]

@st.cache_data(ttl=15)
def load_journey_df(journey_id=None):
    """Read step-level aggregates directly from Postgres."""
    if engine is None:
        return None
    try:
        from_clause = get_from_clause(journey_id)
        query = f"""
            SELECT
                step_id                                                        AS step,
                COUNT(DISTINCT user_id)                                        AS users_entered,
                COUNT(*) FILTER (WHERE event_type = 'abandon')                 AS dropped,
                COALESCE(AVG(duration_ms) / 1000.0, 0)                        AS avg_dwell_s,
                COUNT(*) FILTER (WHERE event_type = 'error')                   AS avg_errors,
                COUNT(*) FILTER (WHERE event_type = 'rage_click')              AS rage_clicks
            FROM {from_clause}
        """
        params = {}

        query += """
            GROUP BY step_id
            ORDER BY
                CASE step_id
                    WHEN 'landing_page'       THEN 1
                    WHEN 'sign_up_form'       THEN 2
                    WHEN 'email_verification' THEN 3
                    WHEN 'profile_setup'      THEN 4
                    WHEN 'first_action'       THEN 5
                    WHEN 'completion'         THEN 6
                    ELSE 7
                END
        """
        with engine.connect() as conn:
            return pd.read_sql(query, conn, params=params)
    except (SQLAlchemyError, PandasDatabaseError) as exc:
        raise DataLoadError("Journey funnel", exc) from exc

@st.cache_data(ttl=15)
def load_business_kpis(journey_id=None):
    if engine is None:
        return None
    try:
        from_clause = get_from_clause(journey_id)
        params = {}
            
        with engine.connect() as conn:
            total_users = pd.read_sql(f"SELECT COUNT(DISTINCT user_id) FROM {from_clause}", conn, params=params).iloc[0,0]
            total_sessions = pd.read_sql(f"SELECT COUNT(DISTINCT session_id) FROM {from_clause}", conn, params=params).iloc[0,0]
            
            returning_users = pd.read_sql(f"""
                SELECT COUNT(*) FROM (
                    SELECT user_id FROM {from_clause} GROUP BY user_id HAVING COUNT(DISTINCT session_id) > 1
                ) AS sub
            """, conn, params=params).iloc[0,0]
            new_users = total_users - returning_users
            
            revenue = pd.read_sql(f"""
                SELECT SUM(CAST(metadata->>'purchase_value' AS DOUBLE PRECISION))
                FROM {from_clause}
                WHERE event_type = 'step_complete' AND metadata->>'purchase_value' IS NOT NULL
            """, conn, params=params).iloc[0,0]
            revenue = revenue if pd.notna(revenue) else 0.0
            
            conflict_users = pd.read_sql(f"""
                SELECT COUNT(DISTINCT user_id) FROM {from_clause} WHERE event_type IN ('error', 'rage_click')
            """, conn, params=params).iloc[0,0]
            
        return {
            "total_users": total_users,
            "new_users": new_users,
            "returning_users": returning_users,
            "total_sessions": total_sessions,
            "revenue": revenue,
            "conflict_users": conflict_users
        }
    except (SQLAlchemyError, PandasDatabaseError) as exc:
        raise DataLoadError("Business KPIs", exc) from exc

@st.cache_data(ttl=15)
def load_audience_data(journey_id=None):
    if engine is None:
        return None
    try:
        from_clause = get_from_clause(journey_id)
        params = {}
        
        with engine.connect() as conn:
            regions_df = pd.read_sql(f"""
                SELECT metadata->>'region' as region, COUNT(DISTINCT session_id) as sessions
                FROM {from_clause} WHERE metadata->>'region' IS NOT NULL GROUP BY 1 ORDER BY 2 DESC
            """, conn, params=params)
            devices_df = pd.read_sql(f"""
                SELECT metadata->>'device' as device, COUNT(DISTINCT session_id) as sessions
                FROM {from_clause} WHERE metadata->>'device' IS NOT NULL GROUP BY 1 ORDER BY 2 DESC
            """, conn, params=params)
            
        return {"regions": regions_df, "devices": devices_df}
    except (SQLAlchemyError, PandasDatabaseError) as exc:
        raise DataLoadError("Audience", exc) from exc

@st.cache_data(ttl=15)
def load_heatmap_data(journey_id=None):
    if engine is None:
        return None
    try:
        from_clause = get_from_clause(journey_id)
        params = {}
        
        with engine.connect() as conn:
            coords_df = pd.read_sql(f"""
                SELECT 
                    CAST(NULLIF(metadata->>'click_x', '') AS NUMERIC) as click_x,
                    CAST(NULLIF(metadata->>'click_y', '') AS NUMERIC) as click_y,
                    event_type
                FROM {from_clause}
                WHERE metadata->>'click_x' IS NOT NULL AND metadata->>'click_x' != ''
            """, conn, params=params)
        return coords_df
    except (SQLAlchemyError, PandasDatabaseError) as exc:
        raise DataLoadError("Heatmap", exc) from exc


def load_reports():
    if not REPORTS_DIR.exists():
        return []
    return sorted(REPORTS_DIR.glob("*.html"), key=lambda f: f.stat().st_mtime, reverse=True)


@st.cache_data(ttl=30)
def compute_friction_from_db(journey_id=None):
    """Compute friction scores per step directly from Postgres (no pipeline needed)."""
    if engine is None:
        return [], []
    try:
        from_clause = get_from_clause(journey_id)
        with engine.connect() as conn:
            df = pd.read_sql(f"""
                SELECT
                    step_id,
                    COUNT(DISTINCT user_id)                                         AS total_users,
                    COUNT(*) FILTER (WHERE event_type = 'abandon')                  AS abandons,
                    COUNT(*) FILTER (WHERE event_type = 'error')                    AS errors,
                    COUNT(*) FILTER (WHERE event_type = 'rage_click')               AS rage_clicks,
                    COALESCE(AVG(duration_ms) FILTER (
                        WHERE event_type IN ('page_view','step_complete')), 0)      AS avg_dwell_ms
                FROM {from_clause}
                GROUP BY step_id
            """, conn)
        if df.empty:
            return [], []

        scores = []
        for _, row in df.iterrows():
            n = max(row["total_users"], 1)
            drop_rate   = min(row["abandons"] / n * 100, 100)
            error_rate  = min(row["errors"]   / n * 100, 100)
            rage_rate   = min(row["rage_clicks"] / n * 100, 100)
            dwell_s     = row["avg_dwell_ms"] / 1000.0
            # Dwell penalty: 0 if < 5s (too fast = friction), capped at 20
            dwell_penalty = max(0, (5 - dwell_s)) * 4 if dwell_s < 5 else 0

            raw = (
                drop_rate  * 0.40
                + error_rate * 0.30
                + rage_rate  * 0.20
                + dwell_penalty * 0.10
            )
            score = min(round(raw, 1), 100)
            is_critical = score > 50

            scores.append({
                "step_id":     row["step_id"],
                "score":       score,
                "is_critical": is_critical,
                "drop_rate":   round(drop_rate, 1),
                "error_rate":  round(error_rate, 1),
                "rage_rate":   round(rage_rate, 1),
                "dwell_s":     round(dwell_s, 1),
                "total_users": int(n),
            })

        critical = [s["step_id"] for s in scores if s["is_critical"]]
        return scores, critical
    except (SQLAlchemyError, PandasDatabaseError) as exc:
        raise DataLoadError("Friction scores", exc) from exc


@st.cache_data(ttl=30)
def compute_insights_from_db(journey_id=None):
    """Generate basic AI-style insights from DB data without requiring the LangGraph pipeline."""
    scores, critical = compute_friction_from_db(journey_id)
    if not scores:
        return [], []

    insights = []
    fixes    = []
    for i, s in enumerate(sorted(scores, key=lambda x: x["score"], reverse=True)):
        step  = s["step_id"]
        label = step.replace("_", " ").title()
        score = s["score"]
        priority = 1 if s["is_critical"] else 2 if score > 30 else 3

        # Root cause heuristic
        drivers = []
        if s["drop_rate"] > 20: drivers.append(f"high abandon rate ({s['drop_rate']}%")
        if s["error_rate"] > 10: drivers.append(f"error rate {s['error_rate']}%")
        if s["rage_rate"]  > 5:  drivers.append(f"rage-click rate {s['rage_rate']}%")
        if s["dwell_s"]    < 3:  drivers.append(f"low dwell time ({s['dwell_s']}s — users leaving fast)")
        driver_str = "; ".join(drivers) if drivers else "elevated friction signals"

        insights.append({
            "step_id":           step,
            "score":             score,
            "priority":          priority,
            "issue_description": f"Friction score {score} driven by {driver_str}.",
            "root_cause":        f"Users at {label} are experiencing {driver_str}.",
            "recommendation":    (
                "Simplify this step, improve error messaging, and reduce required inputs."
                if score > 50 else
                "Monitor closely and A/B test copy or UX changes."
            ),
        })
        fixes.append({
            "step_id":       step,
            "priority":      priority,
            "suggested_fix": (
                "Reduce form complexity, add inline validation, and A/B test shorter flows."
                if score > 50 else
                "Add micro-copy guidance and progress indicators."
            ),
        })

    return insights, fixes



def run_pipeline():
    """Launch `cji --run --auto-approve` (as python -m cji.main) and block until done."""
    mode = SETTINGS.app.mode
    result = subprocess.run(
        [sys.executable, "-m", "cji.main", "--mode", mode, "--run", "--auto-approve"],
        capture_output=True, text=True, timeout=SETTINGS.budgets.pipeline_timeout_s, cwd=str(HOME),
        env={**os.environ, "CJI_HOME": str(HOME)},
    )
    return result


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:8px 0 24px 0">
        <div style="font-size:22px;font-weight:800;color:#111827;letter-spacing:-0.5px;">Atelier</div>
        <div style="font-size:10px;font-weight:600;color:#94A3B8;letter-spacing:0.12em;margin-top:2px;">
            ANALYTICS INTELLIGENCE
        </div>
    </div>
    """, unsafe_allow_html=True)

    if "page" not in st.session_state:
        st.session_state.page = "Overview"

    def set_page(name):
        st.session_state.page = name

    nav_items = [
        ("📊", "Overview"),
        ("📈", "Journey"),
        ("⚠️", "Friction"),
        ("💡", "Insights"),
    ]
    for icon, name in nav_items:
        active = st.session_state.page == name
        st.button(
            f"{icon}  {name}",
            on_click=set_page, args=(name,),
            use_container_width=True,
            type="primary" if active else "secondary",
            key=f"nav_{name}",
        )

    st.markdown("<br>", unsafe_allow_html=True)

    last = _load("Last run", load_last_run, flush=True)
    if last:
        ts = last.get("timestamp", "")[:16].replace("T", " ")
        st.success(f"✅ Last run: {ts}")
    else:
        st.info("No run data yet.\nClick **▶ Run** to start.")

    # ── JSON Upload Section ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
    <div style="font-size:12px;font-weight:700;color:#374151;letter-spacing:0.05em;
                margin-bottom:8px;text-transform:uppercase;">📂 Upload Events</div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Drag & drop JSON events file",
        type=["json", "ndjson", "jsonl"],
        key="json_uploader",
        help="Upload NDJSON, JSON array, or {\"key\": [...]} files. Up to 1M+ records.",
        label_visibility="collapsed",
    )

    with st.expander("⚙️ Column mapping (optional)", expanded=False):
        st.caption("Map YOUR column names → CJI standard names")
        col_map_text = st.text_area(
            "One mapping per line: your_col=cji_col",
            placeholder="userId=user_id\nsessionId=session_id\nstepName=step_id\neventKind=event_type",
            height=100,
            key="col_map_input",
            label_visibility="collapsed",
        )
        root_key_input = st.text_input(
            "Root key (if JSON is {\"events\": [...]})",
            placeholder="events",
            key="root_key_input",
        )
        replace_mode = st.checkbox(
            "Replace all rows in tracking_events",
            key="replace_mode",
            help="Off (default): new events are appended; events already stored are skipped. "
                 "On: the whole tracking_events table is replaced by this file.",
        )
        if replace_mode:
            st.warning("This deletes every row in tracking_events in the configured database before writing the file.")

    if uploaded_file is not None:
        if st.button("⬆️ Ingest File", type="primary", use_container_width=True, key="btn_ingest"):
            st.session_state["_ingest_file"] = uploaded_file
            st.session_state["_col_map_text"] = col_map_text
            st.session_state["_root_key"]     = root_key_input.strip() or None
            st.session_state["_replace_mode"] = replace_mode
            st.rerun()

    st.markdown("---")
    st.markdown("""
    <div style="border:1px solid #E2E8F0;border-radius:10px;padding:12px 14px;
                display:flex;align-items:center;gap:12px;margin-top:4px;">
        <div style="width:34px;height:34px;border-radius:50%;background:#1D4ED8;
                    color:white;display:flex;align-items:center;justify-content:center;
                    font-weight:800;font-size:12px;">OA</div>
        <div>
            <div style="font-size:13px;font-weight:700;color:#111827;">Organization Admin</div>
            <div style="font-size:11px;color:#94A3B8;">atelier.premium</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Header ─────────────────────────────────────────────────────────────────────
PAGE_META = {
    "Overview": ("Intelligence Hub",    "Synthetic overview of user behavior and friction metrics across all platforms."),
    "Audience": ("Audience Overview",   "GA4-style breakdown of user demographics, sources, and regions."),
    "Heatmaps": ("Behavioral Heatmaps", "Hotjar-style click density and rage-click distribution visualization."),
    "Journey":  ("Journey Funnel",      "Step-by-step analysis of user progression through the onboarding journey."),
    "Friction": ("Friction Analysis",   "Per-step friction scores, critical bottlenecks, and drop-off drivers."),
    "Insights": ("AI Insights & Report","Generated insights, prioritized fixes, and full HTML analysis report."),
}

page          = st.session_state.page
title, subtitle = PAGE_META[page]

col_title, col_actions = st.columns([3, 1])
with col_title:
    st.markdown(f"""
    <div style="margin-bottom:12px;">
        <h1 style="font-weight:800;color:#111827;font-size:30px;margin:0 0 4px 0;line-height:1.1;">{title}</h1>
        <p  style="color:#6B7280;font-size:14px;margin:0;font-weight:500;">{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

with col_actions:
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    b1, b2, b3 = st.columns(3)
    b1.button("🌙", key="btn_dark",  help="Toggle dark mode (coming soon)")
    b2.button("🔔", key="btn_notif", help="Notifications (coming soon)")
    run_clicked = b3.button("▶ Run", type="primary", key="btn_run", help="Run full CJI analysis pipeline")

# Top filter bar
available_journeys = get_journeys()
prop_options = ["all_journeys"] + available_journeys

f1, f2 = st.columns([2, 1])
with f1:
    st.selectbox("Track", prop_options, label_visibility="collapsed", key="sel_property")
with f2:
    st.date_input("Date Range",
                  value=(datetime(2025, 10, 12), datetime(2025, 11, 11)),
                  label_visibility="collapsed", key="date_range")

st.markdown("---")


# ── Run pipeline ───────────────────────────────────────────────────────────────
if run_clicked:
    with st.spinner("🔄 Running full CJI analysis pipeline — this takes ~30 s …"):
        try:
            res = run_pipeline()
            if res.returncode == 0:
                st.cache_data.clear()
                st.success("✅ Analysis complete — data refreshed!")
                st.rerun()
            else:
                st.error(f"Pipeline failed (exit {res.returncode}).\n\n```\n{res.stderr[-800:]}\n```")
        except subprocess.TimeoutExpired:
            st.error(f"Pipeline timed out after {SETTINGS.budgets.pipeline_timeout_s:g} s.")
        except OSError as e:
            st.error(f"Error launching pipeline: {type(e).__name__}: {e}")


# ── JSON File Ingestion ─────────────────────────────────────────────────────────
if st.session_state.get("_ingest_file") is not None:
    uploaded     = st.session_state.pop("_ingest_file")
    col_map_text = st.session_state.pop("_col_map_text", "")
    root_key     = st.session_state.pop("_root_key", None)
    replace_mode = st.session_state.pop("_replace_mode", False)

    # Parse column map
    col_map = {}
    for line in (col_map_text or "").splitlines():
        line = line.strip()
        if "=" in line:
            src, dst = line.split("=", 1)
            col_map[src.strip()] = dst.strip()

    progress_placeholder = st.empty()
    status_placeholder   = st.empty()

    with progress_placeholder.container():
        st.info(f"📂 Processing **{uploaded.name}** ({uploaded.size / 1_048_576:.1f} MB) …")
        prog = st.progress(0, text="Saving upload…")

    tmp_path = None
    try:
        # Save the uploaded bytes to a temp file so ingest_json can stream it
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, dir=str(DATA_DIR)
        ) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)

        prog.progress(20, text="Parsing JSON records…")

        # Call ingest_file directly (same-process, no subprocess needed)
        from cji.tools.ingest_json import ingest_file

        prog.progress(40, text="Normalising columns & dtypes…")

        _, n_rows = ingest_file(
            input_path=tmp_path,
            output_path=PARQUET_PATH,
            col_map=col_map,
            root_key=root_key,
            chunk_size=100_000,
            append=not replace_mode,
            replace=replace_mode,
        )

        prog.progress(85, text="Writing to PostgreSQL…")

        # Cleanup temp file
        tmp_path.unlink(missing_ok=True)

        prog.progress(100, text="Done!")
        st.cache_data.clear()

        row_label = f"{n_rows:,} events"

        progress_placeholder.empty()
        st.success(
            f"✅ **Ingestion complete!** {row_label} written to PostgreSQL tracking_events.\n\n"
            f"Click **▶ Run** to analyse your data."
        )

    except (ConfigError, ValueError, OSError, SQLAlchemyError) as exc:
        progress_placeholder.empty()
        st.error(f"❌ Ingestion failed: {DataLoadError('Upload', exc).args[0]}")
        # Try to clean up temp file if it exists
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                st.caption(f"Temporary upload file was not removed: {cleanup_exc}")


# ── Shared data (available to every tab) ──────────────────────────────────────
_selected     = st.session_state.get("sel_property")
last          = _load("Last run", load_last_run)
journey_df    = _load("Journey funnel", load_journey_df, _selected)
kpis          = _load("Business KPIs", load_business_kpis, _selected)
reports       = load_reports()
audience_data = _load("Audience", load_audience_data, _selected)
heatmap_df    = _load("Heatmap", load_heatmap_data, _selected)
_flush_load_failures()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════
if page == "Overview":

    if kpis:
        total_sessions = kpis["total_sessions"]
        total_users = kpis["total_users"]
        new_users = kpis["new_users"]
        conflict_users = kpis["conflict_users"]
        revenue = kpis["revenue"]
        conflict_rate = round(conflict_users / total_users * 100, 1) if total_users > 0 else 0
        new_user_pct = round(new_users / total_users * 100, 1) if total_users > 0 else 0
    else:
        total_sessions = int(journey_df["users_entered"].max()) if journey_df is not None else 0
        total_users = total_sessions
        new_user_pct = 100.0
        revenue = 0.0
        conflict_rate = 0.0

    friction_list   = (last or {}).get("friction_scores", [])
    if not friction_list:
        friction_list, _ = _load("Friction scores", compute_friction_from_db, st.session_state.get("sel_property"), default=([], []), flush=True)
    avg_friction    = round(np.mean([s["score"] for s in friction_list]), 1) if friction_list else 0.0
    critical_steps  = (last or {}).get("critical_steps", [])
    insights_list   = (last or {}).get("insights", [])
    if not insights_list:
        insights_list, _ = _load("Insights", compute_insights_from_db, st.session_state.get("sel_property"), default=([], []), flush=True)

    def kpi_card(col, label, value, delta, delta_color):
        col.markdown(f"""
        <div class="metric-card">
            <p style="color:#6B7280;font-size:13px;margin:0 0 10px 0;font-weight:500;">
                {label}
                <span style="color:{delta_color};float:right;font-weight:600;font-size:12px;">{delta}</span>
            </p>
            <div style="font-size:40px;font-weight:800;color:#111827;line-height:1;">{value}</div>
        </div>
        """, unsafe_allow_html=True)

    k1, k2, k3, k4 = st.columns(4)
    kpi_card(k1, "Total Users",        f"{total_users:,}" if total_users else "—",
             f"{new_user_pct}% New"  if total_users else "No data", "#10B981")
    kpi_card(k2, "Revenue",            f"${revenue:,.2f}"  if kpis else "—",
             "Est. Conversions"              if kpis else "—", "#10B981")
    kpi_card(k3, "Users with Friction",f"{conflict_rate}%" if kpis else "—",
             "Experienced error/rage"      if kpis else "—", "#EF4444")
    kpi_card(k4, "Total Insights",     str(len(insights_list)) if last else "—",
             f"{len(insights_list)} ready" if last else "No data", "#3B82F6")

    st.markdown("<br>", unsafe_allow_html=True)
    k5, k6, k7, k8 = st.columns(4)
    kpi_card(k5, "Avg Friction Score", f"{avg_friction}" if avg_friction else "—",
             "Score out of 10", "#EF4444")
    kpi_card(k6, "Critical Steps",     f"{len(critical_steps)}" if critical_steps else "0",
             "Needs attention", "#EF4444")
    with k7:
        st.empty()
    with k8:
        st.empty()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Charts row ─────────────────────────────────────────────────────────────
    c_chart, c_funnel = st.columns([2, 1])

    with c_chart:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:16px;font-weight:700;color:#111827;margin-bottom:4px;'>Friction Score vs Rage Clicks</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:13px;color:#6B7280;margin-bottom:16px;'>Correlation of friction signals per journey step.</div>", unsafe_allow_html=True)

        if journey_df is not None:
            steps  = journey_df["step"].tolist()
            labels = [s.replace("_", " ").title() for s in steps]
            rage   = journey_df["rage_clicks"].tolist()

            # Use real friction scores if available, otherwise rage-click proxy
            score_map = {s.get("step_id", s.get("step", "")): s["score"] for s in friction_list} if friction_list else {}
            fscores   = [score_map.get(s, int(r * 3.5)) for s, r in zip(steps, rage)]

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=labels, y=fscores, name="Friction Score",
                marker_color="#3B82F6", opacity=0.85,
            ))
            fig.add_trace(go.Scatter(
                x=labels, y=rage, name="Rage Clicks",
                mode="lines+markers",
                line=dict(color="#EF4444", width=3),
                marker=dict(size=7),
                yaxis="y2",
            ))
            fig.update_layout(
                height=300, margin=dict(l=0, r=0, t=0, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", y=1.1, x=0, font=dict(size=12)),
                yaxis=dict(showgrid=True, gridcolor="#F3F4F6", title="Friction Score"),
                yaxis2=dict(overlaying="y", side="right", title="Rage Clicks", showgrid=False),
                xaxis=dict(showgrid=False),
                barmode="group",
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No journey data found. Run the pipeline or generate demo data first.")
        st.markdown("</div>", unsafe_allow_html=True)

    with c_funnel:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:16px;font-weight:700;color:#111827;margin-bottom:4px;'>Top Funnel Drop-offs</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:13px;color:#6B7280;margin-bottom:16px;'>High-churn stages identified by agent.</div>", unsafe_allow_html=True)

        if journey_df is not None:
            max_u = journey_df["users_entered"].max()
            for _, row in journey_df.iterrows():
                pct   = int(row["users_entered"] / max_u * 100)
                color = "#EF4444" if pct < 40 else "#F59E0B" if pct < 65 else "#3B82F6"
                label = row["step"].replace("_", " ").title()
                st.markdown(f"""
                <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
                    <span style="font-weight:600;color:#111827;">{label}</span>
                    <span style="font-weight:700;color:{color};">{pct}%</span>
                </div>
                <div style="background:#F3F4F6;height:8px;border-radius:4px;margin-bottom:12px;">
                    <div style="background:{color};width:{pct}%;height:100%;border-radius:4px;"></div>
                </div>
                """, unsafe_allow_html=True)
            if critical_steps:
                st.markdown(
                    f"<div style='color:#DC2626;font-size:12px;font-weight:600;margin-top:4px;'>"
                    f"⚠️ Critical: {', '.join(s.replace('_',' ').title() for s in critical_steps)}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No journey data found.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Audience and Heatmaps ──────────────────────────────────────────────────
    aud_data = _load("Audience", load_audience_data, st.session_state.get("sel_property"), flush=True)
    if aud_data is not None:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>Global Reach & Devices</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            fig_r = go.Figure(go.Pie(labels=aud_data["regions"]["region"], values=aud_data["regions"]["sessions"], hole=0.4))
            fig_r.update_layout(title="Sessions by Region", margin=dict(l=0, r=0, t=30, b=0), height=300)
            st.plotly_chart(fig_r, use_container_width=True, config={"displayModeBar": False})
        with c2:
            fig_d = go.Figure(go.Pie(labels=aud_data["devices"]["device"], values=aud_data["devices"]["sessions"], hole=0.4))
            fig_d.update_layout(title="Sessions by Device", margin=dict(l=0, r=0, t=30, b=0), height=300)
            st.plotly_chart(fig_d, use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)

    hm_data = _load("Heatmap", load_heatmap_data, st.session_state.get("sel_property"), flush=True)
    if hm_data is not None:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>Interactive Heatmaps</div>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:13px;color:#6B7280;margin-bottom:16px;'>Visualization of standard clicks vs rage clicks.</div>", unsafe_allow_html=True)
        
        if "event_type" in hm_data.columns and not hm_data.empty:
            hfig = go.Figure(go.Histogram2dContour(
                x=hm_data["click_x"], y=hm_data["click_y"],
                colorscale="Blues", contours=dict(showlines=False)
            ))
            
            rage_clicks = hm_data[hm_data["event_type"] == "rage_click"]
            if not rage_clicks.empty:
                hfig.add_trace(go.Scatter(
                    x=rage_clicks["click_x"], y=rage_clicks["click_y"],
                    mode="markers", marker=dict(color="red", size=6, opacity=0.8),
                    name="Rage Clicks"
                ))
                
            hfig.update_layout(
                height=500, margin=dict(l=0, r=0, t=0, b=0), showlegend=True,
                xaxis=dict(title="Viewport Width"), 
                yaxis=dict(title="Viewport Height", autorange="reversed")
            )
            st.plotly_chart(hfig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No click coordinates found in data.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Strategic insights ─────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:20px;font-weight:800;color:#111827;margin-bottom:16px;'>Strategic Insights</div>", unsafe_allow_html=True)

    if insights_list:
        for ins in insights_list[:3]:
            priority  = ins.get("priority", 2)
            tag_cls   = "tag-critical" if priority == 1 else "tag-urgent" if priority == 2 else "tag-minor"
            tag_lbl   = "CRITICAL"     if priority == 1 else "URGENT"     if priority == 2 else "MINOR"
            step_lbl  = ins.get("step_id", ins.get("step", "Unknown")).replace("_", " ").title()
            issue     = ins.get("issue_description", ins.get("summary", ""))[:110]
            st.markdown(f"""
            <div class="insight-card">
                <div style="display:flex;align-items:center;gap:14px;">
                    <div style="width:40px;height:40px;border-radius:10px;background:#EFF6FF;
                                display:flex;align-items:center;justify-content:center;font-size:20px;">💡</div>
                    <div>
                        <div style="font-weight:700;color:#111827;font-size:15px;margin-bottom:2px;">{step_lbl}</div>
                        <div style="font-size:12px;color:#6B7280;">{issue}</div>
                    </div>
                </div>
                <span class="{tag_cls}">{tag_lbl}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        placeholder_insights = [
            {"title": "Run analysis to see real agent insights", "desc": "Click ▶ Run in the top-right corner", "cls": "tag-minor", "lbl": "PENDING"},
            {"title": "Agent will score every journey step",     "desc": "Friction engine → Insight generator → Report writer", "cls": "tag-minor", "lbl": "PENDING"},
        ]
        for pi in placeholder_insights:
            st.markdown(f"""
            <div class="insight-card">
                <div><strong style="color:#111827;">{pi['title']}</strong><br>
                     <span style="color:#6B7280;font-size:13px;">{pi['desc']}</span></div>
                <span class="{pi['cls']}">{pi['lbl']}</span>
            </div>
            """, unsafe_allow_html=True)

    # ── Footer CTA ─────────────────────────────────────────────────────────────
    st.markdown("<br><br>", unsafe_allow_html=True)
    _, fc, _ = st.columns([1, 2, 1])
    with fc:
        if st.button("📄 Generate Full Analysis Report", use_container_width=True, type="primary", key="cta_report"):
            with st.spinner("Running CJI pipeline…"):
                try:
                    res = run_pipeline()
                    if res.returncode == 0:
                        st.cache_data.clear()
                        st.success("✅ Report generated!")
                        st.rerun()
                    else:
                        st.error("Pipeline error — are the MCP servers running?")
                except (OSError, subprocess.TimeoutExpired) as e:
                    st.error(f"Pipeline could not run: {type(e).__name__}: {e}")
        st.markdown(
            "<div style='text-align:center;font-size:10px;color:#9CA3AF;margin-top:8px;letter-spacing:0.06em;'>"
            "AVAILABLE AS HTML · POWERED BY CJI AGENTS"
            "</div>",
            unsafe_allow_html=True,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: JOURNEY
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Journey":

    if journey_df is None:
        st.warning("⚠️ No journey data found.")
        st.info("Generate demo data first:\n```\npython main.py --mode demo --generate-data\n```")
        st.stop()

    max_u     = journey_df["users_entered"].max()
    labels    = [s.replace("_", " ").title() for s in journey_df["step"]]
    retention = [int(u / max_u * 100) for u in journey_df["users_entered"]]
    bar_clrs  = ["#EF4444" if r < 40 else "#F59E0B" if r < 65 else "#3B82F6" for r in retention]

    # ── Funnel chart ───────────────────────────────────────────────────────────
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>User Funnel — All Steps</div>", unsafe_allow_html=True)

    fig_f = go.Figure()
    fig_f.add_trace(go.Bar(
        x=labels,
        y=journey_df["users_entered"],
        marker_color=bar_clrs,
        text=[f"{int(u):,}" for u in journey_df["users_entered"]],
        textposition="outside",
        textfont=dict(size=12, color="#374151"),
    ))
    fig_f.update_layout(
        height=360, margin=dict(l=0, r=0, t=20, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="#F3F4F6", title="Users"),
        xaxis=dict(showgrid=False),
        showlegend=False,
    )
    st.plotly_chart(fig_f, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Retention line ─────────────────────────────────────────────────────────
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>Step Retention %</div>", unsafe_allow_html=True)
    fig_r = go.Figure()
    fig_r.add_trace(go.Scatter(
        x=labels, y=retention,
        mode="lines+markers+text",
        line=dict(color="#3B82F6", width=3),
        marker=dict(size=9, color=bar_clrs, line=dict(width=2, color="white")),
        text=[f"{r}%" for r in retention],
        textposition="top center",
        textfont=dict(size=11),
        fill="tozeroy",
        fillcolor="rgba(59,130,246,0.08)",
    ))
    fig_r.update_layout(
        height=250, margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(showgrid=True, gridcolor="#F3F4F6", title="Retention %", range=[0, 115]),
        xaxis=dict(showgrid=False),
        showlegend=False,
    )
    st.plotly_chart(fig_r, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Metrics table ──────────────────────────────────────────────────────────
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>Step-by-Step Metrics</div>", unsafe_allow_html=True)
    display = journey_df.copy()
    display["Step"]           = labels
    display["Users Entered"]  = display["users_entered"].apply(lambda x: f"{int(x):,}")
    display["Retention %"]    = [f"{r}%" for r in retention]
    display["Avg Dwell (s)"]  = display["avg_dwell_s"].apply(lambda x: f"{x:.1f}s")
    display["Avg Errors"]     = display["avg_errors"].apply(lambda x: f"{x:.2f}")
    display["Rage Clicks"]    = display["rage_clicks"].apply(lambda x: f"{int(x):,}")
    st.dataframe(
        display[["Step", "Users Entered", "Retention %", "Avg Dwell (s)", "Avg Errors", "Rage Clicks"]],
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
    # PAGE: AUDIENCE (Merged into Journey)
    # ═══════════════════════════════════════════════════════════════════════════════

    st.markdown("<br><hr><br>", unsafe_allow_html=True)
    audience_data = _load("Audience", load_audience_data, st.session_state.get("sel_property"), flush=True)
    if audience_data is None:
        st.warning("⚠️ Could not load audience data. Check database connection.")
        audience_data = {}

    regions_df = audience_data.get("regions", pd.DataFrame())
    devices_df = audience_data.get("devices", pd.DataFrame())

    if regions_df.empty and devices_df.empty:
        st.info("No audience metadata in events yet. Ensure your tracker sends `region` and `device` fields in the metadata payload.")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>🌍 Sessions by Region</div>", unsafe_allow_html=True)
        if not regions_df.empty:
            fig_reg = go.Figure(go.Bar(
                x=regions_df["sessions"], y=regions_df["region"],
                orientation="h",
                marker_color="#3B82F6",
                text=regions_df["sessions"], textposition="outside",
            ))
            fig_reg.update_layout(
                height=max(200, len(regions_df) * 40),
                margin=dict(l=0, r=40, t=0, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor="#F3F4F6"),
                yaxis=dict(showgrid=False), showlegend=False,
            )
            st.plotly_chart(fig_reg, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No region data available.")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_b:
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>📱 Sessions by Device</div>", unsafe_allow_html=True)
        if not devices_df.empty:
            fig_dev = go.Figure(go.Pie(
                labels=devices_df["device"], values=devices_df["sessions"],
                hole=0.45,
                marker=dict(colors=["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"]),
                textinfo="label+percent",
            ))
            fig_dev.update_layout(
                height=300,
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
            )
            st.plotly_chart(fig_dev, use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("No device data available.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ── Summary table ──────────────────────────────────────────────────────────
    if not regions_df.empty:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div class='section-card'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>📊 Region Breakdown</div>", unsafe_allow_html=True)
        total_s = regions_df["sessions"].sum()
        regions_df["share"] = (regions_df["sessions"] / total_s * 100).round(1).astype(str) + "%"
        st.dataframe(
            regions_df.rename(columns={"region": "Region", "sessions": "Sessions", "share": "Share"}),
            use_container_width=True, hide_index=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


    # ═══════════════════════════════════════════════════════════════════════════════
    # PAGE: HEATMAPS (Merged into Journey)
    # ═══════════════════════════════════════════════════════════════════════════════

    st.markdown("<br><hr><br>", unsafe_allow_html=True)
    heatmap_df = _load("Heatmap", load_heatmap_data, st.session_state.get("sel_property"), flush=True)
    if heatmap_df is None or heatmap_df.empty:
        st.info(
            "🔥 **No click data yet.**\n\n"
            "To see heatmaps, your tracking snippet must send `click_x` and `click_y` values "
            "in the `metadata` object when recording click events. Example:\n\n"
            "```js\n"
            "trackEvent('click', 'landing_page', {\n"
            "  click_x: e.clientX,\n"
            "  click_y: e.clientY,\n"
            "  element: e.target.id\n"
            "});\n"
            "```"
        )
        heatmap_df = pd.DataFrame(columns=["click_x", "click_y", "event_type"])

    heatmap_df = heatmap_df.dropna(subset=["click_x", "click_y"])
    if heatmap_df.empty:
        st.warning("Click coordinates found but all values are null. Check `click_x`/`click_y` fields.")

    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>🔥 Click Density Heatmap</div>", unsafe_allow_html=True)

    # Color by event type
    color_map = {"rage_click": "#EF4444", "click": "#3B82F6", "page_view": "#10B981"}
    heatmap_df["color"] = heatmap_df["event_type"].map(color_map).fillna("#6366F1")

    fig_heat = go.Figure()
    for etype, grp in heatmap_df.groupby("event_type"):
        col = color_map.get(etype, "#6366F1")
        fig_heat.add_trace(go.Scatter(
            x=grp["click_x"], y=grp["click_y"],
            mode="markers",
            marker=dict(
                size=9,
                color=col,
                opacity=0.45,
                line=dict(width=0),
            ),
            name=etype.replace("_", " ").title(),
        ))

    fig_heat.update_layout(
        height=520,
        margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="#111827",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, title="X position", color="#9CA3AF"),
        yaxis=dict(showgrid=False, title="Y position", autorange="reversed", color="#9CA3AF"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    font=dict(size=11, color="#374151")),
    )
    st.plotly_chart(fig_heat, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Stats row ──────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    total_clicks = len(heatmap_df)
    rage_clicks  = (heatmap_df["event_type"] == "rage_click").sum()
    rage_pct     = round(rage_clicks / total_clicks * 100, 1) if total_clicks else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Click Events", f"{total_clicks:,}")
    c2.metric("Rage Clicks",        f"{rage_clicks:,}")
    c3.metric("Rage Click Rate",    f"{rage_pct}%")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: FRICTION
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Friction":

    friction_list  = (last or {}).get("friction_scores", [])
    critical_steps = (last or {}).get("critical_steps", [])

    # ── Fallback: compute friction directly from DB if pipeline hasn't run ─────
    if not friction_list:
        friction_list, critical_steps = _load(
            "Friction scores", compute_friction_from_db, st.session_state.get("sel_property"),
            default=([], []), flush=True,
        )
        if friction_list:
            st.info("📊 Showing computed friction scores from live data. Click **▶ Run** to get full AI-powered analysis.")

    if not friction_list:
        st.warning("⚠️ No friction data yet. Connect to the database or click **▶ Run** to run the analysis pipeline.")
        st.info("The friction engine scores each step using: drop rate, dwell time, error rate, and rage clicks.")
        st.stop()

    # ── Score cards ────────────────────────────────────────────────────────────
    cols = st.columns(max(1, len(friction_list)))
    for i, item in enumerate(friction_list):
        step  = item.get("step_id", item.get("step", f"Step {i+1}"))
        score = item.get("score", 0)
        crit  = step in critical_steps
        color = "#EF4444" if crit else "#F59E0B" if score > 60 else "#10B981"
        label = step.replace("_", " ").title()
        cols[i].markdown(f"""
        <div class="metric-card" style="text-align:center;border-top:4px solid {color};">
            <div style="font-size:11px;color:#6B7280;margin-bottom:8px;font-weight:600;letter-spacing:0.03em;">{label}</div>
            <div style="font-size:38px;font-weight:800;color:{color};line-height:1;">{score}</div>
            <div style="font-size:10px;color:{'#EF4444' if crit else '#94A3B8'};margin-top:6px;font-weight:600;">
                {'⚠️ CRITICAL' if crit else 'Normal'}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Horizontal bar chart ───────────────────────────────────────────────────
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>Friction Score by Step</div>", unsafe_allow_html=True)

    sorted_scores = sorted(friction_list, key=lambda x: x["score"], reverse=True)
    s_labels = [s.get("step_id", s.get("step", "")).replace("_", " ").title() for s in sorted_scores]
    s_values = [s["score"] for s in sorted_scores]
    s_colors = ["#EF4444" if s.get("step_id", s.get("step", "")) in critical_steps else "#3B82F6" for s in sorted_scores]

    fig_s = go.Figure()
    fig_s.add_trace(go.Bar(
        y=s_labels, x=s_values, orientation="h",
        marker_color=s_colors,
        text=[str(v) for v in s_values],
        textposition="outside",
        textfont=dict(size=12, color="#374151"),
    ))
    fig_s.update_layout(
        height=max(200, len(sorted_scores) * 55),
        margin=dict(l=0, r=40, t=0, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=True, gridcolor="#F3F4F6", range=[0, 115]),
        yaxis=dict(showgrid=False),
        showlegend=False,
    )
    st.plotly_chart(fig_s, use_container_width=True, config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Critical steps detail ──────────────────────────────────────────────────
    if critical_steps:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:16px;'>Critical Steps — Detail</div>", unsafe_allow_html=True)
        for step in critical_steps:
            s_data = next((s for s in friction_list if s.get("step_id", s.get("step")) == step), {})
            label  = step.replace("_", " ").title()
            score  = s_data.get("score", "—")
            st.markdown(f"""
            <div class="insight-card" style="border-left:4px solid #EF4444;">
                <div>
                    <div style="font-weight:700;color:#111827;font-size:15px;">⚠️ {label}</div>
                    <div style="color:#6B7280;font-size:13px;margin-top:3px;">
                        Friction Score: <strong style="color:#EF4444;">{score}</strong>
                    </div>
                </div>
                <span class="tag-critical">CRITICAL</span>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "Insights":

    insights_list = (last or {}).get("insights", [])
    fixes_list    = (last or {}).get("prioritized_fixes", [])
    narrative     = (last or {}).get("narrative", "")
    report_path   = (last or {}).get("report_path", "")

    # ── Fallback: compute insights from DB when pipeline hasn't run ────────────
    if not insights_list:
        insights_list, fixes_list = _load(
            "Insights", compute_insights_from_db, st.session_state.get("sel_property"),
            default=([], []), flush=True,
        )
        if insights_list:
            st.info("💡 Showing rule-based insights from live data. Click **▶ Run** for full LLM-powered AI analysis and report generation.")

    if not last:
        st.warning("⚠️ No insights available. Click **▶ Run** to run the full pipeline first.")

    # ── Executive narrative ────────────────────────────────────────────────────
    if narrative:
        st.markdown("<div class='section-card' style='margin-bottom:20px;'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:12px;'>📝 Executive Narrative</div>", unsafe_allow_html=True)
        # Report content is untrusted (LLM output): escape it before it goes into HTML (Spec 10, OD-92).
        st.markdown(f"<div style='color:#374151;font-size:14px;line-height:1.85;white-space:pre-wrap;'>{html.escape(narrative)}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ── AI-generated insights ──────────────────────────────────────────────────
    st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:12px;'>💡 AI-Generated Insights</div>", unsafe_allow_html=True)

    if insights_list:
        for i, ins in enumerate(insights_list):
            priority  = ins.get("priority", 2)
            tag_cls   = "tag-critical" if priority == 1 else "tag-urgent" if priority == 2 else "tag-minor"
            tag_lbl   = "CRITICAL"     if priority == 1 else "HIGH"       if priority == 2 else "MINOR"
            step_lbl  = ins.get("step_id", ins.get("step", "")).replace("_", " ").title()
            issue     = ins.get("issue_description", ins.get("summary", ""))
            root      = ins.get("root_cause", "")
            rec       = ins.get("recommendation", "")

            with st.expander(
                f"{'⚠️' if priority == 1 else '💡'} [{tag_lbl}] {step_lbl} — {issue[:80]}",
                expanded=(i < 2),
            ):
                c1, c2 = st.columns([5, 1])
                with c1:
                    if root:
                        st.markdown(f"**🔍 Root Cause:** {root}")
                    if rec:
                        st.markdown(f"**✅ Recommendation:** {rec}")
                    if not root and not rec:
                        st.markdown(issue)
                with c2:
                    st.markdown(f"<span class='{tag_cls}'>{tag_lbl}</span>", unsafe_allow_html=True)
    else:
        st.info("No insights found in last run output.")

    # ── Prioritized fixes ──────────────────────────────────────────────────────
    if fixes_list:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:12px;'>🔧 Prioritized Fixes</div>", unsafe_allow_html=True)
        
        # Create a quick lookup for journey data
        step_metrics = {}
        if journey_df is not None:
            for _, r in journey_df.iterrows():
                u_in = r["users_entered"]
                dropped = r["dropped"]
                drop_pct = (dropped / u_in * 100) if u_in > 0 else 0.0
                step_metrics[r["step"]] = {"users": int(u_in), "drop_pct": drop_pct}

        for i, fix in enumerate(fixes_list):
            step_id  = fix.get("step_id", fix.get("step", ""))
            step_lbl = step_id.replace("_", " ").title()
            action   = fix.get("suggested_fix", fix.get("recommendation", fix.get("action", fix.get("fix", ""))))
            priority = fix.get("priority", i + 1)
            
            users_entered = "—"
            drop_rate_str = "—"
            if step_id in step_metrics:
                users_entered = f"{step_metrics[step_id]['users']:,}"
                drop_rate_str = f"{step_metrics[step_id]['drop_pct']:.1f}%"
            
            st.markdown(f"""
            <div class="insight-card" style="display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex;align-items:center;gap:14px;flex-grow:1;">
                    <div style="width:34px;height:34px;border-radius:50%;background:#EFF6FF;color:#3B82F6;
                                font-weight:800;font-size:14px;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                        #{priority}
                    </div>
                    <div>
                        <div style="font-weight:700;color:#111827;font-size:14px;">{html.escape(step_lbl)}</div>
                        <div style="font-size:13px;color:#6B7280;margin-top:2px;">{html.escape(action)}</div>
                    </div>
                </div>
                <div style="display:flex;gap:8px;flex-shrink:0;align-items:center;flex-wrap:wrap;justify-content:flex-end;">
                    <span style="background:#F3F4F6;color:#374151;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:600;">👥 {users_entered} Users</span>
                    <span style="background:#FEF2F2;color:#DC2626;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:600;">📉 {drop_rate_str} Drop-off</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Report downloads ───────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:18px;font-weight:700;color:#111827;margin-bottom:12px;'>📄 Generated Reports</div>", unsafe_allow_html=True)

    if reports:
        for r in reports[:8]:
            c1, c2 = st.columns([4, 1])
            size_kb = r.stat().st_size // 1024
            mtime   = datetime.fromtimestamp(r.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            with c1:
                st.markdown(f"""
                <div style="padding:10px 14px;border:1px solid #E5E7EB;border-radius:8px;background:white;">
                    <div style="font-weight:600;color:#111827;font-size:13px;">📄 {html.escape(r.name)}</div>
                    <div style="font-size:11px;color:#94A3B8;margin-top:2px;">{mtime} · {size_kb} KB</div>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
                st.download_button(
                    "⬇️ Download",
                    data=r.read_bytes(),
                    file_name=r.name,
                    mime="text/html",
                    key=f"dl_{r.stem}",
                    use_container_width=True,
                )
    else:
        st.info("No reports generated yet. Run the analysis pipeline to create reports.")
        if st.button("▶ Run Pipeline Now", type="primary", key="insights_run"):
            with st.spinner("Running…"):
                try:
                    res = run_pipeline()
                    if res.returncode == 0:
                        st.cache_data.clear()
                        st.rerun()
                except (OSError, subprocess.TimeoutExpired) as e:
                    st.error(f"Pipeline could not run: {type(e).__name__}: {e}")
