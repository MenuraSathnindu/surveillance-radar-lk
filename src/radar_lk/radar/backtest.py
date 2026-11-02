"""Radar backtest -> docs/RADAR_BACKTEST.md and docs/figures/ (proposal section 9).

    python -m radar_lk.radar.backtest      (after python -m radar_lk.radar.run)

a) True false-alert rate: outbreak-free years simulated from each series' fitted NB baseline
   (radar.nullsim), every method run on them; every alert there is false.
b) Injected outbreaks (k x SD, k = 1..10, 1-4 weeks, 2024 onwards), each method's statistic stored
   so thresholds can be swept: sensitivity vs null false-alert rate, sensitivity at 1 and 2 false
   alerts per 100 district-weeks, and by outbreak size.
c) Real-data alert rate per method (not a false-alert rate: real alerts include real rises).
d) Known-event replay against the status-quo rule (events located in our own data).
e) Completeness-gating evaluation.  f) External validation with NDCU 2026 lists.
g) 2026 separately.  h) Case studies, track record, persistence and burden.
"""

from __future__ import annotations

import pickle
from datetime import date

import numpy as np
import pandas as pd

from radar_lk import CLEAN_DIR, REPO_ROOT, load_config
from radar_lk.radar import evaluation as ev
from radar_lk.radar.nullsim import DEFAULT_THRESHOLD
from radar_lk.radar.run import CACHE, METHODS, radar_cfg
from radar_lk.radar.series import load_panel

DOC = REPO_ROOT / "docs" / "RADAR_BACKTEST.md"
FIG = REPO_ROOT / "docs" / "figures"
SEED = 20261104
N_PER_DISEASE = 200
EVAL_FROM = (2024, 1)
LABEL = {
    "status_quo": "Status quo (2x last year)",
    "ears_c2": "EARS C2",
    "ears_c3": "EARS C3",
    "nb_glm": "NB-GLM (Farrington-style)",
}
COLOR = {"status_quo": "#2a78d6", "ears_c2": "#eb6834", "ears_c3": "#1baf7a", "nb_glm": "#eda100"}
MARKER = {"status_quo": "o", "ears_c2": "s", "ears_c3": "^", "nb_glm": "D"}


def md(df: pd.DataFrame, index: bool = False, fmt: str = "{:.1f}") -> str:
    if index:
        df = df.reset_index()
    cols = [str(c) for c in df.columns]
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        cells = []
        for v in row:
            if isinstance(v, float):
                cells.append("" if np.isnan(v) else fmt.format(v))
            else:
                cells.append(str(v))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def alert_rates(sig: pd.DataFrame, by=None, year_from=EVAL_FROM[0], year_to=None) -> pd.DataFrame:
    """Real-data ALERT rate (alerts per 100 district-weeks). Not a false-alert rate: real alerts
    include real rises; the false-alert rate comes from the null simulation."""
    s = sig[sig["epi_year"] >= year_from]
    if year_to is not None:
        s = s[s["epi_year"] <= year_to]
    keys = ["method"] + ([by] if by else [])
    t = s.groupby(keys).agg(
        weeks=("alert", "size"), alerts=("alert", "sum"), shown=("alert_shown", "sum")
    )
    t["alert rate / 100 district-weeks"] = 100 * t["alerts"] / t["weeks"]
    t["shown / 100 (after gating)"] = 100 * t["shown"] / t["weeks"]
    return t


# ------------------------------------------------------------------ c) NDCU external validation


def ndcu_validation(sig: pd.DataFrame) -> dict:
    flags = pd.read_parquet(CLEAN_DIR / "ndcu_flags.parquet")
    n = flags.groupby(["district", "epi_year", "epi_week"]).size().rename("n_moh").reset_index()
    out = {}
    d = sig[(sig["disease"] == "dengue") & (sig["epi_year"] == 2026)]
    weeks = sorted(set(d["epi_week"]) & set(flags["epi_week"]))
    for m in METHODS:
        x = d[(d["method"] == m) & d["epi_week"].isin(weeks)][["area", "epi_week", "alert_shown"]]
        x = x.merge(n.rename(columns={"district": "area"}), on=["area", "epi_week"], how="left")
        x["n_moh"] = x["n_moh"].fillna(0).astype(int)
        res = {}
        for thr in (1, 3):
            x["ndcu"] = x["n_moh"] >= thr
            res[thr] = _concordance(x, thr)
        out[m] = (res, x.copy())
    out["_weeks"] = weeks
    return out


def _kappa(a, b) -> float:
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    po = (a == b).mean()
    pe = a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean())
    return float((po - pe) / (1 - pe)) if pe < 1 else float("nan")


def _concordance(x: pd.DataFrame, thr: int) -> dict:
    r, nd = x["alert_shown"].astype(bool), x["ndcu"].astype(bool)
    res = {
        "district-weeks": len(x),
        "both": int((r & nd).sum()),
        "radar only": int((r & ~nd).sum()),
        "NDCU only": int((~r & nd).sum()),
        "neither": int((~r & ~nd).sum()),
        "agreement %": 100 * float((r == nd).mean()),
        "kappa": f"{_kappa(r, nd):.2f}",
        "radar sensitivity vs NDCU %": 100 * float(r[nd].mean()) if nd.any() else float("nan"),
        "share of radar alerts with NDCU flag %": 100 * float(nd[r].mean())
        if r.any()
        else float("nan"),
    }
    # lead / lag: for each NDCU onset (district enters the list), the nearest radar alert
    lags, unmatched = [], 0
    for _, g in x.sort_values("epi_week").groupby("area"):
        wk = g["epi_week"].to_numpy()
        nd_on = g["ndcu"].to_numpy(bool)
        al = set(wk[g["alert_shown"].to_numpy(bool)])
        prev = np.concatenate([[False], nd_on[:-1]])
        for w in wk[nd_on & ~prev]:
            near = [a - w for a in al if abs(a - w) <= 4]
            if near:
                lags.append(min(near, key=lambda z: (abs(z), z)))
            else:
                unmatched += 1
    lags = np.array(lags)
    res.update(
        {
            "NDCU onsets": int(len(lags) + unmatched),
            "onsets with a radar alert within +-4 wk": int(len(lags)),
            "median lag (radar - NDCU, wk)": float(np.median(lags)) if len(lags) else float("nan"),
            "radar earlier": int((lags < 0).sum()),
            "same week": int((lags == 0).sum()),
            "radar later": int((lags > 0).sum()),
        }
    )
    # pooled cross-correlation of the two binary series at lags -4..4
    xc = {}
    for L in range(-4, 5):
        num = den = 0
        for _, g in x.groupby("area"):
            s = g.set_index("epi_week")
            r_, n_ = s["alert_shown"].astype(float), s["ndcu"].astype(float)
            sh = r_.reindex(r_.index - L).to_numpy()  # radar at week - L vs NDCU at week
            ok = ~np.isnan(sh)
            if ok.sum() > 2:
                num += (
                    np.corrcoef(sh[ok], n_.to_numpy()[ok])[0, 1] * ok.sum()
                    if np.std(sh[ok]) > 0 and np.std(n_.to_numpy()[ok]) > 0
                    else 0
                )
                den += ok.sum()
        xc[L] = num / den if den else float("nan")
    res["xcorr"] = xc
    return res


# ------------------------------------------------------------------ d) figures


INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, BAND, CRIT, SURF = "#2a78d6", "#cde2fb", "#d03b3b", "#fcfcfb"


def case_figure(sig, area, disease, year_from, path, title, method="nb_glm"):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    s = sig[
        (sig["area"] == area)
        & (sig["disease"] == disease)
        & (sig["method"] == method)
        & (sig["epi_year"] >= year_from)
    ].sort_values("t")
    # one row per week, so weeks with no valid data (e.g. quarantined issues) show as gaps
    full = pd.DataFrame({"t": range(int(s["t"].min()), int(s["t"].max()) + 1)})
    first = pd.Timestamp(s["week_start"].iloc[0]) - pd.Timedelta(weeks=int(s["t"].iloc[0]))
    s = full.merge(s, on="t", how="left")
    s["week_start"] = first + pd.to_timedelta(s["t"] * 7, unit="D")
    s["alert_shown"] = s["alert_shown"].fillna(False).astype(bool)
    s["suppressed"] = s["suppressed"].fillna(False).astype(bool)
    x = pd.to_datetime(s["week_start"])
    fig, ax = plt.subplots(figsize=(10, 4), dpi=150)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    ax.fill_between(
        x,
        0,
        s["upper"],
        color=BAND,
        step="mid",
        linewidth=0,
        label="expected range (up to the 98th-percentile bound)",
    )
    ax.plot(x, s["expected"], color="#86b6ef", linewidth=2, label="expected")
    ax.plot(
        x, s["observed"], color=BLUE, linewidth=2, label="observed weekly count (as first printed)"
    )
    a = s[s["alert_shown"]]
    ax.scatter(
        pd.to_datetime(a["week_start"]),
        a["observed"],
        s=64,
        color=CRIT,
        zorder=5,
        edgecolor=SURF,
        linewidth=2,
        label="alert",
    )
    sp = s[s["suppressed"]]
    if len(sp):
        ax.scatter(
            pd.to_datetime(sp["week_start"]),
            sp["observed"],
            s=64,
            facecolor=SURF,
            edgecolor=MUTED,
            linewidth=2,
            zorder=5,
            label="alert suppressed (low completeness)",
        )
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("cases per week", color=INK2, fontsize=9)
    ax.set_title(title, loc="left", color=INK, fontsize=12)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK2)
    fig.text(
        0.01,
        0.01,
        f"Source: Epidemiology Unit, WER Table 1 ({s['source_issue'].dropna().iloc[-1]} latest); "
        f"method {LABEL[method]}; as of {s['as_of'].dropna().iloc[-1]}; "
        "gaps = weeks without valid data",
        fontsize=7,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)


def pick_cases(sig, panel) -> list[tuple]:
    d = sig[(sig["method"] == "nb_glm")]
    c1 = max(
        ("Colombo", "Gampaha"),
        key=lambda a: d[(d.area == a) & (d.disease == "dengue") & (d.epi_year == 2026)][
            "alert_shown"
        ].sum(),
    )
    lep = panel[panel["disease"] == "leptospirosis"].groupby("area")["observed"].max()
    c2 = lep.idxmax()
    # quiet: the busiest series (mean count) on which the plotted NB-GLM never shows an alert
    tot = d.groupby(["area", "disease"]).agg(obs=("observed", "mean"), al=("alert_shown", "sum"))
    quiet = tot[tot["al"] == 0].sort_values("obs", ascending=False)
    if quiet.empty:
        quiet = tot.sort_values(["al", "obs"], ascending=[True, False])
    c3 = quiet.index[0]
    return [(c1, "dengue", 2026), (c2, "leptospirosis", 2022), (c3[0], c3[1], 2023)]


# ------------------------------------------------------------------ evaluation figures


def _style(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK2, labelsize=9)


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def roc_figure(sw: pd.DataFrame, path) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    for m in METHODS:
        g = sw[sw["method"] == m].sort_values("null_fa_per_100")
        ax.plot(
            g["null_fa_per_100"],
            g["sensitivity"],
            color=COLOR[m],
            linewidth=2,
            marker=MARKER[m],
            markersize=5,
            label=LABEL[m],
        )
        d = g[g["default"]]
        ax.scatter(
            d["null_fa_per_100"],
            d["sensitivity"],
            s=110,
            facecolor=SURF,
            edgecolor=COLOR[m],
            linewidth=2,
            zorder=5,
        )
    for x in (1, 2):
        ax.axvline(x, color=MUTED, linewidth=1, linestyle=":")
    ax.axvline(10, color=CRIT, linewidth=1, linestyle="--")
    ax.text(
        10.6,
        96,
        "10 alerts / 100:\nthe proposal's\nusability bar",
        color=INK2,
        fontsize=8,
        va="top",
    )
    ax.set_xscale("log")
    ax.set_xlim(0.05, 60)
    ax.set_ylim(0, 100)
    _style(ax)
    ax.set_xlabel(
        "false alerts per 100 district-weeks (outbreak-free simulation, log scale)",
        color=INK2,
        fontsize=9,
    )
    ax.set_ylabel("sensitivity on injected outbreaks (%)", color=INK2, fontsize=9)
    ax.set_title(
        "Sensitivity vs false-alert rate, threshold swept (hollow = default threshold)",
        loc="left",
        color=INK,
        fontsize=11,
    )
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK2)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)


def size_figure(sc: pd.DataFrame, path, target: float) -> None:
    plt = _plt()
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    ks = sorted(sc["k"].unique())
    # the status-quo rule cannot get down to the target rate at any factor (see _floor_note)
    shown = [m for m in METHODS if sc.loc[sc["method"] == m, "sensitivity"].notna().any()]
    width = 0.8 / len(shown)
    for i, m in enumerate(shown):
        g = sc[sc["method"] == m].set_index("k").reindex(ks)
        x = np.arange(len(ks)) + (i - (len(shown) - 1) / 2) * width
        ax.bar(x, g["sensitivity"], width=width - 0.03, color=COLOR[m], label=LABEL[m])
    ax.set_xticks(np.arange(len(ks)))
    ax.set_xticklabels([f"{k} x SD" for k in ks])
    ax.set_ylim(0, 100)
    _style(ax)
    ax.grid(axis="x", visible=False)
    ax.set_xlabel(
        "total outbreak size (multiples of the series' standard deviation)", color=INK2, fontsize=9
    )
    ax.set_ylabel("sensitivity (%)", color=INK2, fontsize=9)
    ax.set_title(
        f"Sensitivity by outbreak size, every method at {target:g} false alert / 100 "
        "district-weeks",
        loc="left",
        color=INK,
        fontsize=11,
    )
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK2)
    if len(shown) < len(METHODS):
        ax.text(
            0.99,
            0.97,
            "Status quo not shown: it never gets down to this false-alert rate",
            transform=ax.transAxes,
            ha="right",
            va="top",
            color=INK2,
            fontsize=8,
        )
    fig.tight_layout()
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)


def events_figure(rp: pd.DataFrame, path) -> None:
    """First-alert week relative to the event start; three methods (status quo, EARS C3, NB-GLM)
    to stay within the 3-series cap for point charts; the table has all four."""
    plt = _plt()
    show = ["status_quo", "ears_c3", "nb_glm"]

    def short(e: str) -> str:
        if e.startswith("After Cyclone Ditwah"):
            return "Ditwah floods, leptospirosis"
        return e.replace(", ", " ")

    labels = [f"{short(e)} | {d}" for e, d in zip(rp["event"], rp["district"], strict=True)]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(rp) + 1.6), dpi=150)
    fig.patch.set_facecolor(SURF)
    ax.set_facecolor(SURF)
    y = np.arange(len(rp))[::-1]
    for j, m in enumerate(show):
        x = rp[f"{m}_first"].to_numpy(float)
        cen = rp[f"{m}_censored"].to_numpy(bool)
        ax.scatter(
            x[~cen],
            (y + (j - 1) * 0.18)[~cen],
            s=40,
            color=COLOR[m],
            marker=MARKER[m],
            label=LABEL[m],
            edgecolor=SURF,
            linewidth=1,
            zorder=5,
        )
        ax.scatter(
            x[cen],
            (y + (j - 1) * 0.18)[cen],
            s=40,
            facecolor=SURF,
            edgecolor=COLOR[m],
            marker=MARKER[m],
            linewidth=1.3,
            zorder=5,
        )
    ax.axvline(0, color=MUTED, linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7)
    _style(ax)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel(
        "first alert, weeks relative to the event start (negative = before)", color=INK2, fontsize=9
    )
    ax.set_title(
        "Known events: first alert per method\nno marker = no alert\nhollow = already alerting "
        "when the look-back window opens\n(the true first alert is that week or earlier)",
        loc="left",
        color=INK,
        fontsize=10,
    )
    ax.legend(
        frameon=False,
        fontsize=8,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.06 - 1.2 / len(rp)),
        ncol=3,
        labelcolor=INK2,
    )
    fig.tight_layout()
    fig.savefig(path, facecolor=SURF)
    plt.close(fig)


# ------------------------------------------------------------------ main


def main(reuse: bool = False) -> None:
    cfg = radar_cfg()
    with open(CACHE, "rb") as f:
        fits_all = pickle.load(f)["fits"]
    sig = pd.read_parquet(CLEAN_DIR / "radar_signals.parquet")
    q = float(sig["quantile_used"].iloc[0])
    panel, skipped = load_panel(cfg["first_year"], cfg["min_history_weeks"])
    mc = cfg["min_count"]
    null_p = CLEAN_DIR / "radar_null_false_alerts.parquet"
    inj_p = CLEAN_DIR / "radar_injections.parquet"
    if reuse and null_p.exists() and inj_p.exists():
        print("reusing saved null simulation and injections")
        null, inj = pd.read_parquet(null_p), pd.read_parquet(inj_p)
    else:
        print("null simulation ...")
        null = ev.null_false_alerts(panel, fits_all, cfg)
        null.to_parquet(null_p, index=False)
        print("injections ...")
        inj = ev.inject_stats(panel, fits_all, cfg, np.random.default_rng(SEED), N_PER_DISEASE)
        inj.to_parquet(inj_p, index=False)
    sw = ev.sweep(inj, null, mc)
    mt = ev.matched(sw)
    sc = ev.size_curve(inj, sw, mc, target=1.0)
    clean = pd.read_parquet(CLEAN_DIR / "wer.parquet")
    weather = pd.read_parquet(CLEAN_DIR / "weather.parquet")
    events = ev.define_events(clean, weather)
    rp = ev.replay(sig, events)
    gt = ev.gating_eval(sig)
    nd = ndcu_validation(sig)
    FIG.mkdir(parents=True, exist_ok=True)
    roc_figure(sw, FIG / "radar_sensitivity_vs_false_alerts.png")
    size_figure(sc, FIG / "radar_sensitivity_by_size.png", 1.0)
    events_figure(rp, FIG / "radar_event_replay.png")
    figs = []
    for i, (a, dis, y0) in enumerate(pick_cases(sig, panel), 1):
        p = FIG / f"radar_case{i}_{dis}_{a.replace(' ', '_')}.png"
        title = {
            1: f"{a} dengue, {y0}: observed vs expected",
            2: f"{a} leptospirosis (largest 2022-26 peak: the Dec 2024 post-flood outbreak)",
            3: f"{a} {dis}: a busy but steady series stays quiet (NB-GLM)",
        }[i]
        case_figure(sig, a, dis, y0, p, title)
        figs.append((p, a, dis))
    tr = pd.read_parquet(CLEAN_DIR / "radar_track_record.parquet")
    write_doc(cfg, q, panel, skipped, null, inj, sw, mt, sc, events, rp, gt, nd, figs, tr, sig)


def _pct_table(sw, inj, null, sig, mc):
    rows = []
    rr = alert_rates(sig)
    for m in METHODS:
        th = DEFAULT_THRESHOLD[m]
        det, delay = ev.detect(inj, m, th, mc)
        detg, _ = ev.detect(inj, m, th, mc, gated=True)
        fa = null[(null["method"] == m) & (null["threshold"] == th) & (null["disease"] == "all")]
        fa = float(fa["fa_per_100"].iloc[0])
        rows.append(
            {
                "method": LABEL[m],
                "default threshold": f"{th:g}",
                "sensitivity %": 100 * det.mean(),
                "sensitivity after gating %": 100 * detg.mean(),
                "false alerts / 100 (null)": fa,
                "specificity % (null)": 100 - fa,
                "alert rate / 100 (real data)": rr.loc[m, "alert rate / 100 district-weeks"],
                "median delay (weeks)": float(np.nanmedian(delay)) if det.any() else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _floor_note(sw: pd.DataFrame) -> str:
    """Methods whose false-alert rate cannot be pushed down to 1 or 2 per 100 at any threshold."""
    notes = []
    for m in METHODS:
        lo = sw.loc[sw["method"] == m, "null_fa_per_100"].min()
        if lo > 1:
            notes.append(
                f"{LABEL[m]} never gets below {lo:.1f} false alerts per 100 at any threshold tried"
            )
    if not notes:
        return "Every method reaches 1 false alert per 100 within the thresholds tried."
    return (
        "; ".join(notes) + ". For the status-quo rule this is structural: when last year's same "
        "week was 0, any count >= 3 alerts whatever the multiplier, so raising the factor cannot "
        "remove those alerts; its matched sensitivity is therefore undefined (blank)."
    )


def write_doc(cfg, q, panel, skipped, null, inj, sw, mt, sc, events, rp, gt, nd, figs, tr, sig):
    mc = cfg["min_count"]
    n_series = panel.groupby(["area", "disease"]).ngroups
    last = panel.dropna(subset=["source_issue"]).sort_values("t").iloc[-1]
    lag = load_config().get("publication_lag_weeks")
    head = _pct_table(sw, inj, null, sig, mc)
    sq_rate = float(
        head.loc[head["method"] == LABEL["status_quo"], "alert rate / 100 (real data)"].iloc[0]
    )
    sq_null = float(
        head.loc[head["method"] == LABEL["status_quo"], "false alerts / 100 (null)"].iloc[0]
    )
    L = [
        "# Radar backtest",
        "",
        f"Generated {date.today()} by `python -m radar_lk.radar.run` then `python -m "
        f"radar_lk.radar.backtest`. "
        "Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (WER Table 1); external "
        "validation: National Dengue Control Unit (NDCU) Weekly Dengue Update; rainfall: "
        "Open-Meteo "
        "(CC BY 4.0). Evaluated against the proposal's section 9 (evaluation contract).",
        "",
        "## Highlighted finding: the source tables themselves are sometimes scrambled",
        "",
        "> In several WER issues the weekly column of Table 1 is printed against the wrong "
        "district rows "
        "(2026-W14 and W24, every disease; chickenpox in 2026-W03 and W07) or copied unchanged "
        "from the "
        "previous week (2022-W22 and 2025-W07, whole issues; 2024-W11 chickenpox, 2024-W39 "
        "tuberculosis, "
        "2026-W26 dengue). The national totals and cumulative columns are consistent with the "
        "wrong "
        "numbers, so every sum and cumulative check passes, and two independent extractors agree "
        "with "
        "each other because the error is in the PDF. Before this was caught, the radar was "
        "alerting on "
        "these weeks (e.g. Matale dengue 256 when the weeks around read about 20). Both patterns "
        "are now "
        "detected with past-only rules and queued (docs/EXTRACTION_REPORT.md section 5b). Anyone "
        "building on these PDFs should check for this.",
        "",
        "## Data and design",
        "",
        f"- **Post-COVID baseline.** Only `extraction_valid` RDHS rows from **2022-W01** to "
        f"{last['epi_year']}-W{int(last['epi_week']):02d} ({last['source_issue']}).",
        "- **Weekly counts as first printed** in each issue, never later back-filled values.",
        f"- **Series:** {n_series} RDHS x disease series with >= {cfg['min_history_weeks']} "
        f"observed "
        f"weeks; not modelled (insufficient history): {len(skipped)} "
        f"({', '.join(f'{d} x{c}' for d, c in skipped['disease'].value_counts().items())}).",
        "- **No lookahead.** Every method uses only weeks before t (tested).",
        f"- **Publication lag.** A week's table appears in the WER about **{lag} weeks** after "
        f"the week "
        "ends (median, from the PDFs' creation dates; docs/EXTRACTION_REPORT.md section 11), so "
        "these "
        "are retrospective early-warning signals on the published record.",
        "",
        "| method | rule (default threshold) |",
        "|---|---|",
        f"| Status quo | count >= {cfg['status_quo_factor']:g} x the same week last year and >= "
        f"{mc} |",
        f"| EARS C2 | (y - mean) / sd > {cfg['ears_c2_threshold']:g} over weeks t-9..t-3 (sd "
        f"floored at "
        f"{cfg['ears_sd_floor']:g}) |",
        f"| EARS C3 | sum over t, t-1, t-2 of max(0, C2 - 1) > {cfg['ears_c3_threshold']:g} |",
        f"| NB-GLM | log mu = intercept + trend + Fourier (K={cfg['nb_fourier_k']}), refitted "
        f"every "
        f"{cfg['nb_refit_every']} weeks on past weeks, Anscombe residual > "
        f"{cfg['nb_reweight_threshold']} "
        f"down-weighted; alert if y > the {100 * q:g}th-percentile NB bound |",
        "",
        f"Every method also needs observed >= {mc}. An alert in a week with `completeness_low` is "
        "suppressed (shown with the reason); a `revised` week keeps its alert with the marker.",
        "",
        "## a) False-alert rate (outbreak-free simulation) and the default-threshold headline",
        "",
        "For every series, 200 outbreak-free years are simulated from its own fitted NB baseline "
        "(season and trend of its last 156 weeks; 104 weeks of history then 52 evaluated weeks) "
        "and "
        "every method is run on them exactly as on real data (NB-GLM refitted every 4 weeks with "
        "down-weighting, via a batched IRLS checked against the statsmodels fit). No outbreak "
        "exists in "
        "these series, so **every alert is false**: this is the false-alert rate. It takes each "
        "series' fitted NB baseline as the truth. On the real series the NB-GLM alerts slightly "
        "LESS "
        "often than on its own null (compare the two rate columns): consistent with the real "
        "series "
        "being more over-dispersed than the fitted baseline, so the moment estimate of the "
        "dispersion widens the bound. That explanation is not proven here.",
        "",
        md(head),
        "",
        f"Sensitivity uses {len(inj)} injected outbreaks ({N_PER_DISEASE} per disease, seed "
        f"{SEED}): "
        "start 2024 onwards, 1-4 weeks, total size ~ NB (dispersion 2) with mean k x the series' "
        "SD, "
        "k uniform on 1..10. Delay = weeks from outbreak start to first alert (0 = first week). "
        "**Alert rate (real data)** counts all alerts on the real series; it is not a false-alert "
        "rate, because real rises are in it.",
        "",
        f"**Usability bar.** The proposal's bar is that an alert should fire in at most 10% of "
        f"district-weeks. The status-quo rule fires in {sq_rate:.1f} per 100 real district-weeks "
        f"({sq_null:.1f} per 100 even with no outbreak at all), so the rule currently used by eye "
        f"would "
        "itself break that bar.",
        "",
        "## b) Matched comparison: sensitivity at the same false-alert rate",
        "",
        "Each method's threshold is swept (status quo factor 1.25-50; EARS C2 1-15; C3 0.5-30; "
        "NB-GLM "
        "quantile 0.80-0.9999); for each threshold the null false-alert rate and the "
        "injected-outbreak "
        "sensitivity are computed, and sensitivity is read off each curve at 1 and 2 false alerts "
        "per "
        "100 district-weeks.",
        "",
        md(
            mt.assign(method=mt["method"].map(LABEL))
            .set_index("method")
            .loc[[LABEL[m] for m in METHODS]],
            index=True,
        ),
        "",
        "![sensitivity vs false-alert rate](figures/radar_sensitivity_vs_false_alerts.png)",
        "",
        "Sweep table (data behind the figure):",
        "",
        md(sw.assign(method=sw["method"].map(LABEL)).drop(columns=["default"]), fmt="{:.3g}"),
        "",
        _floor_note(sw),
        "",
        "By outbreak size, every method at the threshold that gives 1 false alert per 100 "
        "district-weeks (a method that cannot get that low is left blank):",
        "",
    ]
    piv = sc.pivot_table(index="k", columns="method", values="sensitivity").reindex(columns=METHODS)
    piv.columns = [LABEL[m] for m in METHODS]
    piv.index = [f"{k} x SD" for k in piv.index]
    L += [
        md(piv, index=True),
        "",
        f"Outbreaks per size: {sc.groupby('k')['outbreaks'].first().to_dict()}.",
        "",
        "![sensitivity by size](figures/radar_sensitivity_by_size.png)",
        "",
    ]
    rr = alert_rates(sig, "disease")
    t = rr["alert rate / 100 district-weeks"].unstack("method")[METHODS]
    t.columns = [LABEL[m] for m in METHODS]
    nd_ = null[(null["disease"] != "all")]
    nn = []
    for m in METHODS:
        x = nd_[(nd_["method"] == m) & (nd_["threshold"] == DEFAULT_THRESHOLD[m])].set_index(
            "disease"
        )
        nn.append(x["fa_per_100"].rename(f"{LABEL[m]} (null)"))
    t = t.join(pd.concat(nn, axis=1))
    L += [
        "## c) Real-data alert rates (2024 onwards) next to the null false-alert rates",
        "",
        "Per disease, alerts per 100 district-weeks at the default thresholds: real data, then the "
        "outbreak-free simulation. Where the real rate is far above the null rate, the series "
        "carry "
        "real rises (or model misfit); where they are close, most real alerts look like noise.",
        "",
        md(t, index=True),
        "",
        f"**Stop rule** (NB-GLM <= {100 * cfg['max_alert_rate']:.0f}% of district-weeks): "
        f"{alert_rates(sig).loc['nb_glm', 'shown / 100 (after gating)']:.2f} per 100 at the "
        f"{100 * q:g}th percentile; the a-priori quantile was kept.",
        "",
    ]
    L += [
        "## d) Known-event replay",
        "",
        "Each event is located **in our data** with an explicit rule (below), not assumed. For "
        "every "
        "affected district: the first week each method alerted, from 4 weeks before the event "
        "start "
        "(from the rain week itself for Ditwah) to its end; `gain` = status-quo first week minus "
        "the "
        "method's first week (positive = earlier than the status-quo rule).",
        "",
    ]
    for e in events:
        evd = e["evidence"].copy()
        L += [
            f"### {e['event']}",
            "",
            f"Rule: {e['rule']}.",
            "",
            md(evd.round(2), index=True, fmt="{:.2f}"),
            "",
        ]
    cols = (
        ["event", "district"] + [f"{m}_week" for m in METHODS] + [f"{m}_gain" for m in METHODS[1:]]
    )
    show = rp[cols].rename(
        columns={
            **{f"{m}_week": f"{LABEL[m]} first" for m in METHODS},
            **{f"{m}_gain": f"{LABEL[m]} gain (wk)" for m in METHODS[1:]},
        }
    )
    L += [
        "### Replay table",
        "",
        "`<=` marks a first alert in the very first week searched: the method may already have "
        "been "
        "alerting before (e.g. the early-2024 leptospirosis surge continues one that began in late "
        "2023), so that first week is censored and its gain is left empty.",
        "",
        md(show, fmt="{:+.0f}"),
        "",
        "![event replay](figures/radar_event_replay.png)",
        "",
    ]
    summ = []
    for m in METHODS[1:]:
        g = rp[f"{m}_gain"]
        summ.append(
            {
                "method": LABEL[m],
                "district-events": len(rp),
                "method alerted": int(rp[f"{m}_first"].notna().sum()),
                "status quo alerted": int(rp["status_quo_first"].notna().sum()),
                "comparable (both alerted, neither censored)": int(g.notna().sum()),
                "earlier than status quo": int((g > 0).sum()),
                "same week": int((g == 0).sum()),
                "later": int((g < 0).sum()),
                "median gain (wk, both alerted)": float(g.median()) if g.notna().any() else np.nan,
            }
        )
    L += [md(pd.DataFrame(summ)), ""]
    L += [
        "## e) Does completeness gating remove artefacts?",
        "",
        "The proposal's target: alerts suppressed for low reporting completeness should be the "
        "ones "
        "that later prove to be artefacts. For every raw alert, suppressed vs kept: was the NEXT "
        "week's cumulative revised (late reports added to earlier weeks), and did the next 2 weeks "
        "stay above expected (a real rise persists)?",
        "",
        md(gt.assign(method=gt["method"].map({**LABEL, "all": "all methods"}))),
        "",
    ]
    a_all = gt[gt["method"] == "all"].set_index("alerts")
    sup, kep = a_all.loc["suppressed"], a_all.loc["kept"]
    flag_ok = sup["next week revised %"] > kep["next week revised %"]
    persists = sup["next 2 weeks above expected %"] >= kep["next 2 weeks above expected %"] - 5
    L += [
        f"Result, all methods pooled (n = {int(sup['n'])} suppressed vs {int(kep['n'])} kept "
        f"alerts):",
        "",
        f"1. **The completeness flag does mark incomplete weeks.** After a suppressed alert the "
        f"next "
        f"week's cumulative was revised in {sup['next week revised %']:.0f}% of cases vs "
        f"{kep['next week revised %']:.0f}% after kept alerts, and raised (late cases added) in "
        f"{sup['next week cum raised % (delta > 0)']:.0f}% vs "
        f"{kep['next week cum raised % (delta > 0)']:.0f}%."
        + ("" if flag_ok else " (Not in this run: the difference goes the other way.)"),
        f"2. **But the suppressed alerts do not look like artefacts.** The next 2 weeks stayed "
        f"above "
        f"expected after {sup['next 2 weeks above expected %']:.0f}% of suppressed alerts vs "
        f"{kep['next 2 weeks above expected %']:.0f}% of kept ones. Late reports add cases, so a "
        f"rise "
        "seen in an incomplete week is, if anything, understated, not invented.",
        "",
        (
            "**Verdict: the proposal's target (gating removes alerts that prove to be artefacts) "
            "is not "
            "met.** Gating holds back alerts that persist as often as the others. The dashboard "
            "therefore "
            "shows them as 'possible rise, held back: low reporting completeness' with the "
            "reason, rather "
            "than hiding them, and gating is not counted as a precision gain."
            if persists
            else "**Verdict: suppressed alerts persist less often than kept ones, so gating "
            "removes alerts that behave more like artefacts, as the proposal intended.**"
        ),
        "The suppressed group is small, so these percentages are imprecise.",
        "",
    ]
    L += [
        "## f) External validation: dengue radar vs NDCU 2026 high-risk MOH lists",
        "",
        f"District x week pairs in 2026 where both exist (weeks "
        f"{nd['_weeks'][0]}-{nd['_weeks'][-1]}). "
        "A district is NDCU-positive when at least 1 (or 3) of its MOH areas is on the list. NDCU "
        "flags "
        "absolute burden; the radar flags what is unusual for the district and season.",
        "",
    ]
    for thr in (1, 3):
        rows = []
        for m in METHODS:
            r = nd[m][0][thr]
            rows.append({"method": LABEL[m], **{k: v for k, v in r.items() if k != "xcorr"}})
        L += [f"### NDCU-positive = >= {thr} MOH area(s) flagged", "", md(pd.DataFrame(rows)), ""]
        xc = nd["nb_glm"][0][thr]["xcorr"]
        peak = max(xc, key=lambda k: np.nan_to_num(xc[k], nan=-9))
        L += [
            "NB-GLM pooled correlation of the weekly 0/1 series at lag L (L < 0: radar leads): "
            + ", ".join(f"L={k}: {v:.2f}" for k, v in xc.items())
            + f". Peak at L = {peak}.",
            "",
        ]
    x = nd["nb_glm"][1]
    x["ndcu3"] = x["n_moh"] >= 3
    miss = x[x["ndcu3"] & ~x["alert_shown"]]
    obs = sig[
        (sig["method"] == "nb_glm") & (sig["disease"] == "dengue") & (sig["epi_year"] == 2026)
    ]
    mm = miss.merge(obs[["area", "epi_week", "burden_label"]], on=["area", "epi_week"], how="left")
    L += [
        f"Of the {len(miss)} district-weeks with >= 3 MOH areas flagged but no radar alert, "
        f"{100 * (mm['burden_label'] == 'high burden, within expected range').mean():.0f}% are "
        f"labelled "
        "'high burden, within expected range' on the dashboard (count in the district's own top "
        "10% "
        "but within the expected range for the season). That is how the two signals are reconciled "
        "for the user.",
        "",
    ]
    L += ["## g) 2026 separately (the proposal promised this)", ""]
    r26 = alert_rates(sig, year_from=2026)
    i26 = inj[inj["start_year"] == 2026]
    rows = []
    for m in METHODS:
        det, delay = ev.detect(i26, m, DEFAULT_THRESHOLD[m], mc)
        rows.append(
            {
                "method": LABEL[m],
                "alert rate / 100 (real 2026)": r26.loc[m, "alert rate / 100 district-weeks"],
                "shown / 100 (2026, after gating)": r26.loc[m, "shown / 100 (after gating)"],
                f"sensitivity % (outbreaks starting 2026, n={len(i26)})": 100 * det.mean(),
                "median delay (wk)": float(np.nanmedian(delay)) if det.any() else np.nan,
            }
        )
    L += [
        md(pd.DataFrame(rows)),
        "",
        "2026 contains the year's dengue epidemic and the most source-table errors (four of the "
        "quarantined issues/columns), so its extraction-valid share is the lowest (see "
        "docs/EXTRACTION_REPORT.md). The 2026 dengue replay is in section d, the NDCU comparison "
        "in f.",
        "",
    ]
    L += ["## h) Case studies, track record, persistence and burden", ""]
    for p, a, dis in figs:
        L += [f"![{a} {dis}](figures/{p.name})", ""]
    trn = tr[tr["method"] == "nb_glm"]
    wsum = np.nansum(trn["followed_by_second_high_week"] * trn["alerts"])
    nb = sig[(sig["method"] == "nb_glm") & sig["alert_shown"]]
    L += [
        "`data/clean/radar_signals.parquet` carries, per series-week and method: `weeks_persisted` "
        "(consecutive weeks up to and including this one above the bound; past weeks only), "
        "`sustained` (>= 2), `burden_pctl` (percentile of the count among the district's own past "
        "counts) and `burden_label` ('unusual for this district and season', 'high burden, within "
        "expected range', or held back for low completeness). `radar_track_record.parquet` has the "
        "per-series alert counts and the share followed by a second high week.",
        "",
        f"NB-GLM: {len(nb)} shown alerts; {100 * nb['sustained'].mean():.0f}% sustained (>= 2 "
        f"weeks); "
        f"{100 * wsum / max(trn['alerts'].sum(), 1):.0f}% followed by a second high week. "
        f"Weeks persisted: {nb['weeks_persisted'].value_counts().sort_index().head(6).to_dict()}.",
        "",
    ]
    L += [
        "## Deviations from the proposal",
        "",
        "| proposal | this build | why |",
        "|---|---|---|",
        "| Baselines from 2016 | From **2022-W01** | Post-COVID baseline: 2020-21 reporting was "
        "distorted, and 2016-21 PDFs were not processed in the compressed schedule. Seasonal terms "
        "rest on 1-4 seasons. |",
        "| Farrington Flexible (R `surveillance`) | **NB-GLM with Farrington-style "
        "down-weighting** "
        "(Anscombe residual > 2.58 -> weight r^-2), refitted every 4 weeks, in Python | No R in "
        "the "
        "build; the method keeps Farrington's key ideas (NB, trend, seasonality, outbreak "
        "down-weighting) but not its exact seasonal factor or its trend-dropping rule. |",
        "| Threshold chosen in evaluation | The **98th percentile fixed a priori** and never "
        "tuned; "
        "the sweep in section b only shows what other thresholds would give | Avoids optimising on "
        "the test data. |",
        "| Rates per population | **Counts**, not rates; population denominators not yet added | "
        "District populations were not ingested; signals are relative to each district's own "
        "history, "
        "so the radar does not need them, but maps of burden would. |",
        "| Real false-alert rate from labelled data | False-alert rate from **outbreak-free "
        "simulation** of each series' fitted baseline; real-data alert rate reported separately | "
        "There are no labelled outbreak/non-outbreak weeks. |",
        "",
        "## Limitations",
        "",
        "- The null simulation takes each series' fitted NB baseline as the truth; real series "
        "that "
        "depart from that model change the false-alert rate in either direction (section c).",
        "- Injected outbreaks are synthetic; real events of other shapes may be detected "
        "differently.",
        "- Known events are located from the same counts the radar uses (for Ditwah also from "
        "rainfall); "
        "the replay measures timing against the status-quo rule, not against an independent truth.",
        "- NB bounds ignore parameter uncertainty; TB starts in 2024, so its NB-GLM predicts only "
        "from 2025.",
        "",
    ]
    DOC.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {DOC}")
    print(md(head))
    print(md(mt))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--reuse", action="store_true", help="reuse the saved null simulation and injections"
    )
    main(ap.parse_args().reuse)
