"""Track record: how often past alerts and forecasts were right, in plain language.

Every claim on this page is a row of docs/HEADLINES.md shown verbatim (common.claim), so the
dashboard, report, summary and video quote the same numbers.
"""

from __future__ import annotations

import common
import streamlit as st

FIG = common.ROOT / "docs" / "figures"

st.title("Track record")
st.caption(
    "How far to trust the signals: tested week by week on data the methods had not seen, as "
    "they would have been used live. Every number below is quoted from docs/HEADLINES.md."
)


def section(title: str, intro: str, labels: list[str]) -> None:
    st.subheader(title)
    st.markdown(intro)
    for lab in labels:
        common.claim(lab)


section(
    "Radar: more early signals for the same number of false alarms",
    "We simulated years with no outbreak to count false alarms, and added synthetic outbreaks "
    "to count how many each method finds. Compared at the same false-alarm rate:",
    [
        "Matched comparison at 1 false alert / 100",
        "Matched comparison at 2 false alerts / 100",
        "Status-quo rule false alerts",
    ],
)
c1, c2 = st.columns(2)
c1.image(
    str(FIG / "radar_sensitivity_vs_false_alerts.png"),
    caption="Share of injected outbreaks found vs false alerts per 100 district-weeks.",
)
c2.image(
    str(FIG / "radar_sensitivity_by_size.png"),
    caption="Share found by outbreak size, every method at 1 false alert per 100.",
)

section(
    "Known events: was the radar earlier than today's rule?",
    "The 2024 leptospirosis waves, the 2026 dengue outbreak and the weeks after Cyclone Ditwah, "
    "located in the data with written rules; every affected district is included.",
    ["Two-tier vs status quo", "EARS C2 vs status quo", "NB-GLM vs status quo"],
)
with st.expander("Event replay figure (first signal per method and district)"):
    st.image(str(FIG / "radar_event_replay.png"), width="stretch")

section(
    "Two tiers: alert and early warning",
    "An alert is the seasonal model above its bound; an early warning is a sharp rise against "
    "the last few weeks that the seasonal model has not confirmed yet.",
    [
        "Two-tier decision",
        "Two-tier null false alerts",
        "Two-tier sensitivity",
        "Two-tier first signal in the replay",
    ],
)

section(
    "Low reporting completeness: why held-back signals stay visible",
    "Signals in weeks with unusually low reporting are held back, but shown greyed out:",
    ["Revision after a held-back vs kept alert", "Held-back alerts that persisted"],
)

st.subheader("Outlook: are the forecasts right?")
st.markdown(
    "Forecast models were chosen on 2024 and then tested, untouched, on 2025-26. A forecast "
    "probability of 70% should come true about 70% of the time; the reliability charts check "
    "that."
)
st.markdown(f"> {common.headline_sentence('At h=9–10')}")
tab_l, tab_d = st.tabs(["Leptospirosis (primary)", "Dengue"])
with tab_l:
    for lab in (
        "Leptospirosis: selected models",
        "Leptospirosis, h=1 / 2 (test)",
        "Leptospirosis, this week / next week (h=9 / 10, test)",
        "Leptospirosis, 90% interval coverage (test)",
        "Rainfall lag",
    ):
        common.claim(lab)
    st.image(str(FIG / "outlook_leptospirosis_skill.png"), width="stretch")
    st.image(str(FIG / "outlook_leptospirosis_reliability.png"), width="stretch")
    st.image(str(FIG / "outlook_leptospirosis_rain_lag.png"), width="stretch")
with tab_d:
    for lab in (
        "Dengue: selected models",
        "Dengue, what selection cost on the test",
        "Dengue 2026, count interval coverage",
        "ACI interval width cost",
    ):
        common.claim(lab)
    st.image(str(FIG / "outlook_dengue_skill.png"), width="stretch")
    st.image(str(FIG / "outlook_dengue_reliability.png"), width="stretch")

section(
    "Against the National Dengue Control Unit's high-risk lists (2026)",
    "NDCU lists MOH areas with a high absolute burden; the radar and the outlook flag what is "
    "unusual for a district. These are different questions, so partial agreement is expected.",
    [
        "Radar vs NDCU agreement / kappa",
        "Radar alerts NDCU also flagged",
        "NDCU onsets caught within ±4 weeks",
        "NDCU-only weeks explained",
        "Dengue vs NDCU (h=1, ≥ 3 MOH areas, selected model)",
    ],
)
