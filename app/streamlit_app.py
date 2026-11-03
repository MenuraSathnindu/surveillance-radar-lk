"""Surveillance Radar LK dashboard.

    streamlit run app/streamlit_app.py

Reads only data/clean (parquet) and data/geo. Every page shares the sidebar "As of week" selector
(replay), the stale-data banner and the footer. `?week=2024-W05` in the URL opens a replay week.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

st.set_page_config(
    page_title="Surveillance Radar LK",
    page_icon=":material/radar:",
    layout="wide",
    initial_sidebar_state="auto",
)

pages = [
    st.Page("pages/this_week.py", title="This week", icon=":material/notifications:", default=True),
    st.Page("pages/map.py", title="Map", icon=":material/map:"),
    st.Page("pages/outlook.py", title="Outlook", icon=":material/trending_up:"),
    st.Page("pages/track_record.py", title="Track record", icon=":material/fact_check:"),
    st.Page("pages/data_methods.py", title="Data & methods", icon=":material/description:"),
]
pg = st.navigation(pages)
with st.sidebar:
    st.markdown("### Surveillance Radar LK")
    st.caption("Weekly outbreak signals for Sri Lanka's 26 RDHS units.")
week = common.sidebar()
common.banner(week)
pg.run()
common.footer()
