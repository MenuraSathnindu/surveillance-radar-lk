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

PAGES = [
    ("this_week", "This week", ":material/notifications:"),
    ("map", "Map", ":material/map:"),
    ("outlook", "Outlook", ":material/trending_up:"),
    ("track_record", "Track record", ":material/fact_check:"),
    ("data_methods", "Data & methods", ":material/description:"),
]
# Every page has its own URL (/this_week, /map, ...). Streamlit always serves the DEFAULT page at
# "/" and ignores its url_path, so the default is a hidden landing page that forwards to
# /this_week (or to ?page=<slug>; in tests, the `start_page` session key) and keeps ?week=.
start = st.session_state.get("start_page") or st.query_params.get("page") or "this_week"
if start not in {p[0] for p in PAGES}:
    start = "this_week"
pages = {
    slug: st.Page(f"views/{slug}.py", title=title, icon=icon, url_path=slug)
    for slug, title, icon in PAGES
}


def _landing() -> None:
    week_q = st.query_params.get("week")
    st.switch_page(pages[start], query_params={"week": week_q} if week_q else None)


landing = st.Page(_landing, title="Surveillance Radar LK", url_path="home", default=True)
pg = st.navigation([landing, *pages.values()], position="hidden")
if pg.title == landing.title:
    pg.run()  # forwards; nothing below runs
with st.sidebar:
    for page in pages.values():
        st.page_link(page)
    st.divider()
    st.markdown("### Surveillance Radar LK")
    st.caption("Weekly outbreak signals for Sri Lanka's 26 RDHS units.")
week = common.sidebar()
common.banner(week)
pg.run()
common.footer()
