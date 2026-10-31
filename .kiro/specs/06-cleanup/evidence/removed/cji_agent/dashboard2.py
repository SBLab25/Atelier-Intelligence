import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(layout="wide", page_title="Atelier Intelligence Hub", page_icon="📊")

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #F9FAFB;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #F1F5F9;
        padding-top: 20px;
    }
    
    /* Card Styling */
    .metric-card {
        background-color: white;
        padding: 24px;
        border-radius: 12px;
        border: 1px solid #E5E7EB;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    
    .insight-card {
        background-color: white;
        padding: 16px;
        border-radius: 12px;
        border: 1px solid #E5E7EB;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }

    /* Funnel Styling */
    .funnel-bar {
        height: 8px;
        border-radius: 4px;
        background-color: #E5E7EB;
        margin-bottom: 15px;
    }
    .funnel-fill {
        height: 100%;
        border-radius: 4px;
    }

    /* Hide default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("Atelier")
    st.caption("ANALYTICS INTELLIGENCE")
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Navigation Buttons (Simple State logic)
    if 'page' not in st.session_state:
        st.session_state.page = 'Overview'
        
    def set_page(name):
        st.session_state.page = name

    st.button("📊 Overview", on_click=set_page, args=('Overview',), use_container_width=True, type="primary" if st.session_state.page == 'Overview' else "secondary")
    st.button("📈 Journey", on_click=set_page, args=('Journey',), use_container_width=True)
    st.button("⚠️ Friction", on_click=set_page, args=('Friction',), use_container_width=True)
    st.button("💡 Insights", on_click=set_page, args=('Insights',), use_container_width=True)
    
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)
    st.info("👤 Organization Admin\natelier.premium")

# --- HEADER SECTION ---
col_t1, col_t2 = st.columns([3, 1])
with col_t1:
    st.title("Intelligence Hub")
    st.markdown("<p style='color: #6B7280;'>Synthetic overview of user behavior and friction metrics across all platforms.</p>", unsafe_allow_html=True)

with col_t2:
    st.markdown("<br>", unsafe_allow_html=True)
    cols_h = st.columns([1, 1, 1])
    with cols_h[0]: st.button("🌙")
    with cols_h[1]: st.button("🔔")
    with cols_h[2]: 
        if st.button("Run Analysis", type="primary"):
            st.toast("Running Analysis...")

# Top Filters
c1, c2 = st.columns([2, 1])
with c1:
    st.selectbox("Property", ["The Analytical Atelier", "Mobile App v2", "Marketing Site"], label_visibility="collapsed")
with c2:
    st.date_input("Date Range", value=(datetime(2023, 10, 12), datetime(2023, 11, 11)), label_visibility="collapsed")

st.markdown("---")

# --- KPI METRICS ROW ---
m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown("""
        <div class="metric-card">
            <p style='color: #6B7280; font-size: 14px;'>Total Sessions <span style='color: #10B981; float: right;'>+12.4%</span></p>
            <h1 style='margin: 0;'>142k</h1>
        </div>
    """, unsafe_allow_html=True)

with m2:
    st.markdown("""
        <div class="metric-card">
            <p style='color: #6B7280; font-size: 14px;'>Avg. Friction Score <span style='color: #EF4444; float: right;'>-2.1%</span></p>
            <h1 style='margin: 0;'>3.8</h1>
        </div>
    """, unsafe_allow_html=True)

with m3:
    st.markdown("""
        <div class="metric-card">
            <p style='color: #6B7280; font-size: 14px;'>Critical Steps <span style='color: #94A3B8; float: right;'>Stable</span></p>
            <h1 style='margin: 0;'>12</h1>
        </div>
    """, unsafe_allow_html=True)

with m4:
    st.markdown("""
        <div class="metric-card">
            <p style='color: #6B7280; font-size: 14px;'>Total Insights <span style='color: #3B82F6; float: right;'>+5 New</span></p>
            <h1 style='margin: 0;'>86</h1>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- MAIN CHARTS ROW ---
col_chart, col_funnel = st.columns([2, 1])

with col_chart:
    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
    st.subheader("Friction Trends vs Rage Clicks")
    st.caption("Correlation analysis of user frustration signals.")
    
    # Mock data for line chart
    dates = pd.date_range(start="2023-10-12", end="2023-11-11", freq='D')
    friction = np.sin(np.linspace(0, 5, len(dates))) * 10 + 40 + np.random.normal(0, 2, len(dates))
    rage = np.sin(np.linspace(0, 5, len(dates))) * 5 + 20 + np.random.normal(0, 1, len(dates))
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dates, y=friction, mode='lines', name='Friction Score', line=dict(color='#3B82F6', width=3)))
    fig.add_trace(go.Scatter(x=dates, y=rage, mode='lines', name='Rage Clicks', line=dict(color='#EF4444', width=3)))
    
    fig.update_layout(
        margin=dict(l=0, r=0, t=20, b=0),
        height=300,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor='#F3F4F6')
    )
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

with col_funnel:
    st.markdown("<div class='metric-card'>", unsafe_allow_html=True)
    st.subheader("Top Funnel Drop-offs")
    st.caption("Identification of high-churn stages.")
    
    funnel_data = [
        ("Landing Page", 84, "#3B82F6"),
        ("Product Configurator", 52, "#3B82F6"),
        ("Checkout (Step 1)", 21, "#EF4444"),
        ("Payment Auth", 18, "#3B82F6"),
    ]
    
    for label, val, color in funnel_data:
        st.markdown(f"""
            <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px;">
                <span>{label}</span>
                <span style="font-weight: bold; color: {color}">{val}% Retention</span>
            </div>
            <div class="funnel-bar">
                <div class="funnel-fill" style="width: {val}%; background-color: {color};"></div>
            </div>
        """, unsafe_allow_html=True)
        
    st.warning("⚠️ Critical drop at Checkout: Users are exiting due to unexpected shipping cost reveals.")
    st.markdown("</div>", unsafe_allow_html=True)

# --- STRATEGIC INSIGHTS ---
st.markdown("<br>", unsafe_allow_html=True)
st.subheader("Strategic Insights")

insights = [
    {"title": "Predictive Friction Spike: Checkout Redesign", "desc": "Detected 2h ago • Impacts 14% of mobile users", "status": "CRITICAL", "color": "#EF4444"},
    {"title": "API Latency Impacting Conversion", "desc": "Detected 5h ago • High correlation with Rage Clicks", "status": "URGENT", "color": "#F59E0B"},
    {"title": "New Persona Discovery: 'Casual Explorer'", "desc": "Detected 1d ago • Potential growth segment (8k users)", "status": "MINOR", "color": "#94A3B8"}
]

for insight in insights:
    with st.container():
        st.markdown(f"""
            <div class="insight-card">
                <div>
                    <strong style="font-size: 16px;">{insight['title']}</strong><br>
                    <span style="color: #6B7280; font-size: 13px;">{insight['desc']}</span>
                </div>
                <div style="color: {insight['color']}; font-weight: bold; font-size: 12px; letter-spacing: 1px;">
                    {insight['status']} ⌄
                </div>
            </div>
        """, unsafe_allow_html=True)

# --- FOOTER ---
st.markdown("<br><br>", unsafe_allow_html=True)
c_f1, c_f2, c_f3 = st.columns([1, 2, 1])
with c_f2:
    if st.button("📄 Generate Full Analysis Report", use_container_width=True):
        st.success("Report generated! Check your downloads.")
    st.caption("<center>AVAILABLE IN PDF, CSV, AND SLIDE DECK FORMATS</center>", unsafe_allow_html=True)