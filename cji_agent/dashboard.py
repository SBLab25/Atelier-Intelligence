"""Compatibility launcher: `streamlit run dashboard.py` (from cji_agent/) runs the installed dashboard, as
`cji-dashboard` does (Spec 11, OD-98). Streamlit re-runs this file on every interaction, which re-runs the module."""
import runpy

runpy.run_module("cji.dashboard", run_name="__main__")
