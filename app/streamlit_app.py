"""Surveillance Radar LK dashboard (placeholder until model outputs exist)."""

import streamlit as st

st.set_page_config(page_title="Surveillance Radar LK", layout="wide")
st.title("Surveillance Radar LK")
st.caption(
    "Population-level signals for planning and investigation only. "
    "No diagnosis, treatment or prophylaxis advice."
)

tabs = st.tabs(["This week", "Map", "Dengue outlook", "Track record"])
for t in tabs:
    with t:
        st.info("Waiting for validated model outputs.")

st.divider()
st.caption(
    "Sources: Epidemiology Unit, Ministry of Health, Sri Lanka (Weekly Epidemiological Report); "
    "National Dengue Control Unit, Ministry of Health, Sri Lanka."
)
