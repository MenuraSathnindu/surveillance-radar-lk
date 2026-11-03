"""Map: districts coloured by their strongest signal this week; small multiples on click.

Kalmunai RDHS has no polygon (it is carved out of Ampara district in the HDX boundaries), so it
is drawn as a marker inside Ampara; data/geo/kalmunai_point.json holds its town point.
"""

from __future__ import annotations

import common
import numpy as np
import pandas as pd
import plotly.colors as pcolors
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from radar_lk import views as v

week = common.as_of()
issue = common.week_issue(week)
x = v.signals_at(common.series(), week)
gj, kal = common.geo()
areas = sorted(common.wer()["area"].unique())

st.title("Map")
st.caption(
    f"Districts coloured by the number of active signals (alerts + early warnings) in {week}; "
    f"held-back signals are listed on hover but not counted. {common.src_caption(issue, week)}. "
    "Kalmunai RDHS has no boundary of its own (it lies within Ampara district), so it is the "
    "marker inside Ampara."
)

lists = x.groupby("area").apply(
    lambda g: "<br>".join(
        f"{common.STATUS_TEXT[s]}: {v.DISEASE_TEXT.get(d, d)} ({o:.0f})"
        for s, d, o in zip(g["status"], g["disease"], g["observed"], strict=True)
    ),
    include_groups=False,
)
active = x[x["status"] != "held_back"].groupby("area").size()
m = pd.DataFrame({"area": areas})
m["n"] = m["area"].map(active).fillna(0).astype(int)
m["detail"] = m["area"].map(lists).fillna("no signal")
best = m.sort_values("n", ascending=False)
zmax = max(3, int(m["n"].max()))
# one sequential hue (light -> dark), 0 = near-white
SCALE = [[0.0, "#F4F3EF"], [0.001, "#FDE3CF"], [0.5, "#F08A3C"], [1.0, "#A83A00"]]

fig = go.Figure()
poly = m[m["area"] != "Kalmunai"]
fig.add_trace(
    go.Choropleth(
        geojson=gj,
        locations=poly["area"],
        featureidkey="id",
        z=poly["n"],
        zmin=0,
        zmax=zmax,
        colorscale=SCALE,
        marker_line_color="white",
        marker_line_width=1,
        colorbar=dict(title="active<br>signals", thickness=12, len=0.5, dtick=1),
        customdata=np.c_[poly["detail"]],
        hovertemplate="<b>%{location}</b>: %{z} active<br>%{customdata[0]}"
        f"<br>WER {issue}, {week}<extra></extra>",
    )
)
k = m[m["area"] == "Kalmunai"].iloc[0]
kcol = pcolors.sample_colorscale(SCALE, [k["n"] / zmax])[0]
fig.add_trace(
    go.Scattergeo(
        lon=[kal["lon"]],
        lat=[kal["lat"]],
        mode="markers+text",
        text=["Kalmunai"],
        textposition="middle left",
        textfont=dict(size=10, color="#52514E"),
        marker=dict(size=14, color=kcol, line=dict(color="#52514E", width=1.5)),
        customdata=[[int(k["n"]), k["detail"]]],
        hovertemplate="<b>Kalmunai</b> (RDHS within Ampara): %{customdata[0]} active<br>"
        f"%{{customdata[1]}}<br>WER {issue}, {week}<extra></extra>",
        showlegend=False,
    )
)
fig.update_geos(
    projection_type="mercator",
    fitbounds="locations",
    visible=False,
    bgcolor="rgba(0,0,0,0)",
)
fig.update_layout(
    height=620,
    margin=dict(l=0, r=0, t=10, b=0),
    paper_bgcolor="rgba(0,0,0,0)",
)

left, right = st.columns([5, 7])
with left:
    ev = st.plotly_chart(
        fig, width="stretch", on_select="rerun", selection_mode="points", key="map"
    )
picked = None
try:
    pts = ev.selection.points if ev else []
    if pts:
        picked = pts[0].get("location") or ("Kalmunai" if pts[0].get("curve_number") == 1 else None)
except AttributeError:
    picked = None
if picked in areas:
    st.session_state["map_area"] = picked
if "map_area" not in st.session_state:
    st.session_state["map_area"] = best["area"].iloc[0]
with right:
    area = st.selectbox(
        "District (or click the map)", areas, key="map_area", help="Small multiples below."
    )

    s = common.signals_raw()
    k_end = v.week_key(week)
    s = s[(s["area"] == area)]
    s = s[(s["epi_year"] * 100 + s["epi_week"]) <= k_end]
    ts = sorted(s["t"].unique())[-52:]
    s = s[s["t"].isin(ts)]
    nb = s[s["method"] == "nb_glm"]
    obs = s.drop_duplicates(["disease", "t"])
    dis = sorted(obs["disease"].unique(), key=lambda d: -obs[obs["disease"] == d]["observed"].sum())
    ncol = 3
    nrow = int(np.ceil(len(dis) / ncol)) or 1
    sm = make_subplots(
        rows=nrow,
        cols=ncol,
        subplot_titles=[v.DISEASE_TEXT.get(d, d) for d in dis],
        vertical_spacing=0.08,
        horizontal_spacing=0.06,
    )
    for i, d in enumerate(dis):
        r, c = i // ncol + 1, i % ncol + 1
        o = obs[obs["disease"] == d].sort_values("t")
        b = nb[nb["disease"] == d].sort_values("t")
        if len(b):
            sm.add_trace(
                go.Scatter(x=b["week"], y=b["upper"], mode="lines", line=dict(width=0),
                           showlegend=False, hoverinfo="skip"),
                row=r, col=c,
            )  # fmt: skip
            sm.add_trace(
                go.Scatter(x=b["week"], y=b["expected"], mode="lines", line=dict(width=0),
                           fill="tonexty", fillcolor=common.BAND, showlegend=i == 0,
                           name="expected range (NB-GLM)", hoverinfo="skip"),
                row=r, col=c,
            )  # fmt: skip
        sm.add_trace(
            go.Scatter(
                x=o["week"], y=o["observed"], mode="lines", line=dict(color=common.OBS, width=2),
                name="observed", showlegend=i == 0,
                customdata=o["source_issue"],
                hovertemplate="%{x}: %{y:.0f} cases<br>WER %{customdata}<extra></extra>",
            ),
            row=r, col=c,
        )  # fmt: skip
        for tier, sym in (("alert", "circle"), ("early_warning", "diamond")):
            a = o[(o["tier"] == tier) & ~o["held_back"].astype(bool)]
            if len(a):
                sm.add_trace(
                    go.Scatter(
                        x=a["week"], y=a["observed"], mode="markers",
                        marker=dict(color=common.COLOR[tier], size=8, symbol=sym,
                                    line=dict(color="white", width=1)),
                        name=common.STATUS_TEXT[tier], showlegend=False,
                        hovertemplate=common.STATUS_TEXT[tier]
                        + " %{x}: %{y:.0f}<extra></extra>",
                    ),
                    row=r, col=c,
                )  # fmt: skip
    sm.update_xaxes(showticklabels=False, showgrid=False)
    sm.update_yaxes(gridcolor="#E9E8E2", rangemode="tozero", tickfont=dict(size=9))
    sm.update_annotations(font_size=11)
    sm.update_layout(
        height=150 * nrow + 60,
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", y=1.04, x=0, yanchor="bottom"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(sm, width="stretch", key="multiples")
    first = obs["week"].min() if len(obs) else week
    st.caption(
        f"{area}: last 52 reported weeks ({first} to {week}); line = cases as first printed, "
        "band = NB-GLM expected range, circle = alert, diamond = early warning. Source: WER "
        "Table 1, issues as shown on hover."
    )
