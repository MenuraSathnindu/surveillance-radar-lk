"""Outlook: P(elevated) per district for this week and next week (and h = 1, 2), with the
expected count and its interval, the model used and why, emerging / persistent labels, and a
rainfall panel. Venn-Abers ranges appear only in the tooltip, labelled 'calibration range'."""

from __future__ import annotations

import common
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from radar_lk import views as v

week = common.as_of()
c = common.cfg()
L = c["L"]
issue = common.week_issue(week)

st.title("Outlook")
dis = st.segmented_control(
    "Disease",
    c["diseases"],
    default=c["diseases"][0],
    format_func=lambda d: v.DISEASE_TEXT[d] + (" (primary)" if d == c["diseases"][0] else ""),
    key="outlook_disease",
)
dis = dis or c["diseases"][0]
this_w, next_w = v.add_weeks(week, L + 1), v.add_weeks(week, L + 2)
st.caption(
    f"Forecasts made from reporting week {week} ({common.src_caption(issue, week)}). The WER "
    f"appears about {L} weeks after a week ends, so at the time of use **this week is {this_w}** "
    f"and **next week is {next_w}**; weeks 1 and 2 after {week} are already over but not yet "
    "reported. 'Elevated' means at or above the district's own 80th percentile of the 104 weeks "
    "before. A forecast is a planning signal, not a prediction about any person."
)

o = v.outlook_wide(v.outlook_at(common.forecasts(), dis, week, L), L)
if o.empty:
    st.info(
        f"No outlook for {week}: the outlook backtest starts at 2024-W01. Pick a later week in "
        "the sidebar."
    )
    st.stop()

tr = common.outlook_track()
tr = tr[(tr["disease"] == dis)].drop_duplicates("h").set_index("h")

NAMES = {"persistence": "Persistence", "climatology": "Seasonal climatology",
         "glm": "NB GLM / logistic", "lightgbm": "LightGBM"}  # fmt: skip

# ranked bar: P(elevated) next week (proposal 7.3); calibration range only in the tooltip
o = o.sort_values("p_next", ascending=True)
col = [common.COLOR["alert"] if p >= 0.5 else common.COLOR["early_warning"] for p in o["p_next"]]
fig = go.Figure(
    go.Bar(
        x=o["p_next"] * 100,
        y=o["area"],
        orientation="h",
        marker_color=col,
        customdata=list(
            zip(
                [
                    f"calibration range: {100 * a:.0f}-{100 * b:.0f}%"
                    if pd.notna(a)
                    else "no calibration range (baseline model)"
                    for a, b in zip(o["plo_next"], o["phi_next"], strict=True)
                ],
                o["model_next"].map(NAMES),
                o["count_next"],
                o["lo_next"],
                o["hi_next"],
                o["pattern"].replace("", "-"),
                o["source_issue"],
                strict=True,
            )
        ),
        hovertemplate=(
            "<b>%{y}</b>: %{x:.0f}% chance of an elevated week<br>"
            "%{customdata[0]} · model: %{customdata[1]}<br>"
            "expected %{customdata[2]:.0f} cases (90%: %{customdata[3]:.0f}-%{customdata[4]:.0f})"
            "<br>pattern: %{customdata[5]}<br>"
            f"from WER %{{customdata[6]}}, {week}<extra></extra>"
        ),
    )
)
fig.add_vline(x=50, line_dash="dot", line_color="#898781")
fig.update_layout(
    height=24 * len(o) + 80,
    margin=dict(l=10, r=10, t=30, b=30),
    xaxis=dict(title=f"P(elevated) next week ({next_w}), %", range=[0, 100], gridcolor="#E9E8E2"),
    title=dict(text="Districts ranked by chance of an elevated week next week", x=0, font_size=14),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
)
left, right = st.columns([5, 7])
with left:
    st.plotly_chart(fig, width="stretch", key="outlook_bar")
    st.caption(
        "Hover for the calibration range (Venn-Abers): how sure the calibration is, not how "
        "uncertain the outbreak is; that is the count interval in the table."
    )

with right:
    t = o.sort_values("p_next", ascending=False)

    def p(x):
        return f"{100 * x:.0f}%" if pd.notna(x) else ""

    def cnt(r, k):
        return f"{r[f'count_{k}']:.0f} ({r[f'lo_{k}']:.0f}-{r[f'hi_{k}']:.0f})"

    tab = pd.DataFrame(
        {
            "District": t["area"],
            "Pattern": t["pattern"].str.capitalize(),
            f"This week {this_w}": [p(x) for x in t["p_this"]],
            f"Next week {next_w}": [p(x) for x in t["p_next"]],
            "Week +1": [p(x) for x in t["p_h1"]],
            "Week +2": [p(x) for x in t["p_h2"]],
            "Expected cases this week (90%)": [cnt(r, "this") for _, r in t.iterrows()],
            "Threshold": t["threshold"].round(0).astype(int),
            "Source": [f"WER {s}, {week}" for s in t["source_issue"]],
        }
    )
    st.dataframe(
        tab,
        hide_index=True,
        width="stretch",
        column_config={
            "Pattern": st.column_config.TextColumn(
                help="Persistent: elevated now and forecast elevated. Emerging: not elevated now "
                "but forecast elevated (this or next week). Easing: elevated now, not forecast."
            ),
            "Threshold": st.column_config.NumberColumn(
                help="Cases per week counted as elevated for this district (80th percentile)."
            ),
        },
    )
    interval = (
        "adaptive conformal (ACI)"
        if tr["interval_method"].iloc[0] == "aci"
        else ("split-conformal")
    )
    rows = []
    for h, name in ((L + 1, "This week"), (L + 2, "Next week"), (1, "Week +1"), (2, "Week +2")):
        if h in tr.index:
            r = tr.loc[h]
            pm, cm = NAMES[r["selected probability model"]], NAMES[r["selected count model"]]
            rows.append(
                f"- **{name} (h={h})**: probability from **{pm}** "
                f"({r['probability selection reason']}); counts from **{cm}** "
                f"({r['count selection reason']})."
            )
    st.markdown(
        "**Models used** (selected per horizon on 2024 origins, tested on 2025-26):\n"
        + "\n".join(rows)
    )
    st.caption(f"Count intervals: {interval}. {tr['interval reason'].iloc[0]}.")
    if dis == "dengue":
        y26 = common.outlook_track()
        y26 = y26[(y26["disease"] == "dengue") & (y26["scope"] == "2026 targets")]
        sel = y26[y26["model"] == y26["selected count model"]]
        w = sel["n"] / sel["n"].sum()
        st.warning(
            "2026 is an outlier year for dengue (a large epidemic). On 2026 targets the selected "
            f"count models' 90% intervals covered {(sel['coverage90 %'] * w).sum():.0f}% of "
            f"weeks (static) and {(sel['coverage90 ACI %'] * w).sum():.0f}% with adaptive "
            "conformal, against 90% intended. Read 2026 dengue ranges with care.",
            icon=":material/warning:",
        )

st.subheader("Rainfall")
area = st.selectbox("District", sorted(o["area"]), key="rain_area")
end = v.add_weeks(week, L)
r = v.rain_panel(common.weather(), area, end)
if r.empty:
    st.info("No rainfall data for this district and period.")
else:
    rf = go.Figure()
    rf.add_bar(x=r["week"], y=r["precip_mm"], name="rain (mm/week)", marker_color=common.RAIN,
               hovertemplate="%{x}: %{y:.0f} mm<extra></extra>")  # fmt: skip
    rf.add_scatter(x=r["week"], y=r["normal_mm"], name="normal for the week", mode="lines+markers",
                   line=dict(color=common.NORMAL, width=2, dash="dot"),
                   hovertemplate="%{x}: normal %{y:.0f} mm<extra></extra>")  # fmt: skip
    rf.update_layout(
        height=260,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", y=1.1, x=0),
        yaxis=dict(title="mm per week", gridcolor="#E9E8E2"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(rf, width="stretch", key="rain")
    st.caption(
        f"{area}: weekly rain for the 12 weeks to {end} (the time of use: rainfall is observed in "
        "near real time, unlike case reports), against the mean of the same weeks in earlier "
        f"years. Source: Open-Meteo (CC BY 4.0), as of {r['as_of'].iloc[-1]}."
    )
