"""This week: KPIs and the signal table for the as-of week, plus the weekly briefs."""

from __future__ import annotations

import common
import numpy as np
import pandas as pd
import streamlit as st

from radar_lk import views as v
from radar_lk.brief import build as brief

week = common.as_of()
issue = common.week_issue(week)
labels = common.cfg()["labels"]
x = v.signals_at(common.series(), week)
k = v.kpis(x)

st.title("This week")
st.caption(
    f"Signals for reporting week {week}. {common.src_caption(issue, week)}. Each signal is a "
    "prompt for investigation, judged against that district's own history and season."
)

src = f"WER {issue}, {week}"
c1, c2, c3, c4 = st.columns(4)
c1.metric("Active alerts", k["alerts"], help=f"NB-GLM above its 98% bound. {src}")
c2.metric(
    "Early warnings",
    k["early_warnings"],
    help=f"EARS C2 rising sharply while NB-GLM is not alerting. {src}",
)
c3.metric(
    "Held back",
    k["held_back"],
    help=f"Signals in weeks with low reporting completeness (shown greyed out). {src}",
)
c4.metric(
    "Districts affected", k["districts"], help=f"Districts with an alert or early warning. {src}"
)


def _fmt(x: pd.DataFrame) -> pd.DataFrame:
    def track(r):
        if r.past_signals == 0:
            return "first signal in this series"
        return f"{int(r.past_followed)} of {int(r.past_signals)} past signals had a 2nd high week"

    out = pd.DataFrame(
        {
            "Status": x["status"].map(common.STATUS_TEXT),
            "Disease": x["disease"].map(v.DISEASE_TEXT),
            "District": x["area"],
            "Cases": x["observed"].round(0).astype("Int64"),
            "Expected (range)": [
                f"{e:.0f} (up to {u:.0f})" if pd.notna(e) else ""
                for e, u in zip(x["expected"], x["upper"], strict=True)
            ],
            "Percentile": [
                (">99.9" if p >= 0.9995 else f"{100 * p:.1f}") if pd.notna(p) else ""
                for p in x["percentile"]
            ],
            "Weeks persisted": [
                f"{int(w)} (sustained)" if w >= 2 else f"{int(w)}" if pd.notna(w) else ""
                for w in x["weeks_persisted"]
            ],
            "Context": [
                lab if st_ == "held_back" else (b if b == labels["high_burden"] else "")
                for st_, lab, b in zip(x["status"], x["tier_label"], x["burden_label"], strict=True)
            ],
            "Revised": np.where(x["revised"].fillna(False).astype(bool), "revised", ""),
            "Series track record": [track(r) for r in x.itertuples()],
            "Source": [f"WER {s}, {w}" for s, w in zip(x["source_issue"], x["week"], strict=True)],
            "_status": x["status"],
        }
    )
    return out.reset_index(drop=True)


if x.empty:
    st.info(f"No alerts, early warnings or held-back signals in {week}.")
else:
    t = _fmt(x)

    def _style(row):
        s = row["_status"]
        if s == "held_back":
            return ["color: #8C8C8C; font-style: italic"] * len(row)
        return [""] * len(row)

    def _badge(val):
        key = {vv: kk for kk, vv in common.STATUS_TEXT.items()}.get(val, "none")
        if key in ("alert", "early_warning"):
            return f"background-color: {common.COLOR[key]}; color: white; font-weight: 600"
        if key == "held_back":
            return "background-color: #EFEFEC; color: #6B6B6B"
        return ""

    sty = t.style.apply(_style, axis=1).map(_badge, subset=["Status"])
    st.dataframe(
        sty,
        hide_index=True,
        width="stretch",
        column_order=[c for c in t.columns if c != "_status"],
        column_config={
            "Percentile": st.column_config.TextColumn(
                help="Where this count sits in the method's expected distribution (NB-GLM)."
            ),
            "Context": st.column_config.TextColumn(
                width="large",
                help="Held-back reason, or 'high burden, within expected range'.",
            ),
            "Series track record": st.column_config.TextColumn(
                width="medium", help="This district and disease's signals before this week."
            ),
            "Source": st.column_config.TextColumn(help="WER issue (Vol/No) and reporting week."),
        },
    )
    st.caption(
        "Sorted: alerts, then early warnings, then held back (greyed out, never hidden). "
        f'Held-back label: "{labels["held_back"].replace("{completeness_pct:.0f}", "X")}"'
    )

st.subheader("Weekly brief")
areas = sorted(common.wer()["area"].unique())
default = brief.most_interesting(common.series(), week) if not x.empty else areas[0]
area = st.selectbox("District", areas, index=areas.index(default), key="brief_area")
b = brief.build(area, week, common.series(), common.forecasts(), common.wer())
with st.expander(f"Brief for {area}, {week}", expanded=True):
    st.markdown("\n".join(f"- **{h}:** {t}" for h, t in b.lines))


@st.cache_data(show_spinner="Building PDF ...")
def _pdf(area: str, week: str) -> bytes:
    return brief.pdf_bytes(
        brief.build(area, week, common.series(), common.forecasts(), common.wer())
    )


@st.cache_data(show_spinner="Building all 26 briefs ...")
def _zip(week: str) -> bytes:
    return brief.zip_all(week, common.series(), common.forecasts(), common.wer())


d1, d2, d3 = st.columns(3)
d1.download_button(
    "Brief (Markdown)", b.markdown(), file_name=f"brief_{week}_{area}.md", mime="text/markdown"
)
d2.download_button(
    "Brief (PDF)", _pdf(area, week), file_name=f"brief_{week}_{area}.pdf", mime="application/pdf"
)
if d3.toggle("Prepare all 26 briefs", key="zip_toggle"):
    d3.download_button(
        "Download all 26 (zip)", _zip(week), file_name=f"briefs_{week}.zip", mime="application/zip"
    )
