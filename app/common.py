"""Shared pieces of the dashboard: cached data, the as-of week, banner, footer, palette.

The app reads only data/clean (parquet) and data/geo; never PDFs.
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from radar_lk import load_config  # noqa: E402
from radar_lk import views as v  # noqa: E402
from radar_lk.radar import labels as lb  # noqa: E402

# Okabe-Ito based, checked for colour-vision deficiency; every status also carries a text label.
COLOR = {
    "alert": "#D55E00",
    "early_warning": "#0072B2",
    "held_back": "#8C8C8C",
    "none": "#E9E8E2",
}
OBS, BAND, RAIN, NORMAL = "#0072B2", "#CFE3F3", "#56B4E9", "#52514E"
STATUS_TEXT = {**v.TIER_TEXT, "none": "No signal"}
FOOTER = (
    "Sources: Epidemiology Unit, Ministry of Health, Sri Lanka (WER); National Dengue Control "
    "Unit; Open-Meteo (CC BY 4.0); OCHA HDX boundaries. Population-level signals for planning "
    "and investigation only. No diagnosis, treatment or prophylaxis advice."
)
JUMPS = {
    "Latest": None,
    "2024 leptospirosis wave (2024-W05)": "2024-W05",
    "Post-flood leptospirosis, Jaffna (2024-W51)": "2024-W51",
    "2026 dengue outbreak (2026-W25)": "2026-W25",
}
OUTAGE = (
    "epid.gov.lk was unavailable to scripted downloads from late October into early November "
    "2026; it answered again on 3 November, when the data were frozen."
)


@st.cache_data(show_spinner=False)
def cfg() -> dict:
    c = load_config()
    return {
        "L": int(c["publication_lag_weeks"]),
        "labels": lb.labels(),
        "diseases": c["outlook"]["diseases"],
        "freeze": c.get("data_freeze") or {},
    }


@st.cache_data(show_spinner="Loading signals ...")
def series() -> pd.DataFrame:
    return v.add_track_record(v.series_weeks(v.load_signals()))


@st.cache_data(show_spinner=False)
def signals_raw() -> pd.DataFrame:
    s = v.load_signals()
    keep = ["area", "disease", "t", "week", "epi_year", "epi_week", "method", "observed",
            "expected", "upper", "alert", "tier", "held_back", "source_issue"]  # fmt: skip
    return s[s["method"].isin(["nb_glm", "ears_c2"])][keep]


@st.cache_data(show_spinner="Loading outlook ...")
def forecasts() -> pd.DataFrame:
    return v.load_forecasts()


@st.cache_data(show_spinner=False)
def outlook_track() -> pd.DataFrame:
    return v.load_outlook_track()


@st.cache_data(show_spinner=False)
def wer() -> pd.DataFrame:
    return v.load_wer()


@st.cache_data(show_spinner=False)
def weather() -> pd.DataFrame:
    return v.load_weather()


@st.cache_data(show_spinner=False)
def geo():
    return v.load_geo()


@st.cache_data(show_spinner=False)
def weeks() -> list[str]:
    return v.weeks_available(series())


@st.cache_data(show_spinner=False)
def headlines() -> dict[str, tuple[str, str, str]]:
    """{number label: (value, meaning, source)} parsed verbatim from docs/HEADLINES.md."""
    out = {}
    for line in (ROOT / "docs" / "HEADLINES.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| number") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if len(cells) == 4:
            out[cells[0]] = (cells[1], cells[2], cells[3])
    return out


@st.cache_data(show_spinner=False)
def headline_sentence(start: str) -> str:
    """A prose line of docs/HEADLINES.md that starts with `start`, verbatim."""
    for line in (ROOT / "docs" / "HEADLINES.md").read_text(encoding="utf-8").splitlines():
        if line.startswith(start):
            return line
    return ""


def claim(label: str) -> None:
    """Show one HEADLINES.md row verbatim: value, meaning, and its source."""
    h = headlines().get(label)
    if h is None:
        st.warning(f"'{label}' is not in docs/HEADLINES.md")
        return
    value, meaning, src = h
    st.markdown(f"**{label}:** {value}. {meaning}")
    st.caption(f"Source: {re.sub(r'`', '', src)} · quoted from docs/HEADLINES.md")


# ------------------------------------------------------------------ as-of week


def as_of() -> str:
    return st.session_state.get("as_of") or weeks()[-1]


def _jump():
    target = JUMPS[st.session_state["jump"]]
    st.session_state["as_of"] = target or weeks()[-1]


def sidebar() -> str:
    ws = weeks()
    if "as_of" not in st.session_state:
        q = st.query_params.get("week")
        st.session_state["as_of"] = q if q in ws else ws[-1]
    with st.sidebar:
        st.selectbox(
            "As of week",
            ws,
            key="as_of",
            help="The latest REPORTED week. Changing it replays the system as it would have "
            "looked then, using only signals and forecasts available that week.",
        )
        st.selectbox("Jump to", list(JUMPS), key="jump", on_change=_jump)
        st.caption(
            "Replay uses only what was known that week: radar signals are computed past-only "
            "and the outlook shows the forecasts made at that week."
        )
    w = st.session_state["as_of"]
    if st.query_params.get("week") != w:
        st.query_params["week"] = w
    return w


def week_end(label: str) -> date:
    y, k = label.split("-W")
    return date.fromisocalendar(int(y), int(k), 1) + timedelta(days=6)


def banner(week: str) -> None:
    c = cfg()
    w = wer()
    latest = w.sort_values(["epi_year", "epi_week"]).iloc[-1]
    lw = v.week_label(latest["epi_year"], latest["epi_week"])
    today = date.today()
    lag_days = (today - week_end(lw)).days
    msg = (
        f"Latest WER issue: **{latest['source_issue']}**, reporting week **{lw}** (ended "
        f"{week_end(lw):%d %b %Y}). Today is {today:%d %b %Y}, {lag_days} days later; the WER "
        f"normally appears about {c['L']} weeks after the week ends. {OUTAGE}"
    )
    fz = c["freeze"]
    if fz:
        d = fz["date"] if isinstance(fz["date"], date) else date.fromisoformat(str(fz["date"]))
        msg = f"**Data freeze: {fz['week']}, {d.day} {d:%b %Y}.** " + msg
    if week != lw:
        msg = f"**Replay: viewing as of {week}.** " + msg
    if lag_days > 7 * (c["L"] + 2):
        st.warning("Data may be stale. " + msg, icon=":material/schedule:")
    else:
        st.info(msg, icon=":material/info:")


def footer() -> None:
    st.divider()
    st.caption(FOOTER)


def src_caption(issue: str, week: str) -> str:
    return f"Source: WER {issue} · as of {week}" if issue else f"As of {week}"


def week_issue(week: str) -> str:
    w = wer()
    s = w.loc[w["week"] == week, "source_issue"]
    return str(s.iloc[0]) if len(s) else ""
