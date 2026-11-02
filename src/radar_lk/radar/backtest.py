"""Radar backtest -> docs/RADAR_BACKTEST.md and docs/figures/.

    python -m radar_lk.radar.backtest      (after python -m radar_lk.radar.run)

a) Injected-outbreak evaluation: simulated outbreaks added to the real series (sizes negative-
   binomial, scaled to each series' SD, spread over 1-4 weeks, start in 2024-2026), 200 per disease.
   Sensitivity and median detection delay per method; specificity and false alerts per 100
   district-weeks from the real (un-injected) 2024-2026 data.
b) Real-data alert rate per method, per disease and overall (+ the 10% stop rule).
c) External validation of the dengue radar against NDCU 2026 high-risk MOH lists.
d) Case-study figures.  e) The per-series track record is written by radar.run.
"""

from __future__ import annotations

import pickle
from datetime import date

import numpy as np
import pandas as pd

from radar_lk import CLEAN_DIR, REPO_ROOT
from radar_lk.radar.methods import ears, nb_fits, nb_predict, refit_points, status_quo
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


# ------------------------------------------------------------------ a) injected outbreaks


def _method_alerts(y, years, weeks, fits, cfg, q, window):
    """Alerts of every method on (modified) series y, only for weeks in `window`."""
    mc = cfg["min_count"]
    out = {"status_quo": status_quo(y, years, weeks, cfg["status_quo_factor"], mc)["alert"]}
    e = ears(
        y,
        cfg["ears_baseline"],
        cfg["ears_guard"],
        cfg["ears_c2_threshold"],
        cfg["ears_c3_threshold"],
        cfg["ears_sd_floor"],
        mc,
    )
    out["ears_c2"], out["ears_c3"] = e["ears_c2"]["alert"], e["ears_c3"]["alert"]
    out["nb_glm"] = nb_predict(y, fits, cfg, q, mc, weeks=window)["alert"]
    return {m: a[window] for m, a in out.items()}


def inject(panel, fits_all, cfg, q, rng) -> pd.DataFrame:
    rows = []
    t_eval = panel.loc[(panel["epi_year"] > EVAL_FROM[0] - 1), "t"].min()
    for dis, gd in panel.groupby("disease"):
        series = {a: g.reset_index(drop=True) for a, g in gd.groupby("area")}
        areas = sorted(series)
        made = tries = 0
        while made < N_PER_DISEASE and tries < 50 * N_PER_DISEASE:
            tries += 1
            a = areas[rng.integers(len(areas))]
            g = series[a]
            y = g["observed"].to_numpy(float)
            fits = fits_all[(a, dis)]
            pts = refit_points(y, cfg["nb_min_train_weeks"], cfg["nb_refit_every"])
            if not pts:
                continue
            dur = int(rng.integers(1, 5))
            lo = max(int(t_eval), pts[0])
            hi = len(y) - dur
            if hi <= lo:
                continue
            s = int(rng.integers(lo, hi + 1))
            window = np.arange(s, s + dur)
            if np.isnan(y[window]).any():
                continue
            sd = max(float(np.nanstd(y)), 1.0)
            k = int(rng.integers(2, 11))
            mean = k * sd
            size = 0
            while size < 1:
                size = int(rng.negative_binomial(2, 2 / (2 + mean)))
            add = rng.multinomial(size, np.full(dur, 1 / dur))
            y2 = y.copy()
            y2[window] += add
            # NB refits whose training window now contains injected weeks
            redo = [r for r in pts if s < r <= window[-1]]
            f2 = nb_fits(y2, cfg, points=redo, base=fits) if redo else fits
            al = _method_alerts(
                y2, g["epi_year"].to_numpy(), g["epi_week"].to_numpy(), f2, cfg, q, window
            )
            low = g["completeness_low"].fillna(False).astype(bool).to_numpy()[window]
            rec = {
                "disease": dis,
                "area": a,
                "start_t": s,
                "duration": dur,
                "size": size,
                "k": k,
                "sd": sd,
                "start_week": f"{g['epi_year'][s]}-W{g['epi_week'][s]:02d}",
            }
            for m, v in al.items():
                hit = np.flatnonzero(v)
                hit_g = np.flatnonzero(v & ~low)
                rec[f"{m}_detected"] = len(hit) > 0
                rec[f"{m}_delay"] = int(hit[0]) if len(hit) else np.nan
                rec[f"{m}_detected_gated"] = len(hit_g) > 0
            rows.append(rec)
            made += 1
    return pd.DataFrame(rows)


def real_rates(sig: pd.DataFrame, by=None) -> pd.DataFrame:
    s = sig[(sig["epi_year"] >= EVAL_FROM[0])]
    keys = ["method"] + ([by] if by else [])
    t = s.groupby(keys).agg(
        weeks=("alert", "size"), alerts=("alert", "sum"), shown=("alert_shown", "sum")
    )
    t["alerts per 100 district-weeks"] = 100 * t["alerts"] / t["weeks"]
    t["shown per 100 (after gating)"] = 100 * t["shown"] / t["weeks"]
    return t


def headline(inj: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    rr = real_rates(sig)
    rows = []
    for m in METHODS:
        det = inj[f"{m}_detected"]
        rows.append(
            {
                "method": LABEL[m],
                "sensitivity %": 100 * det.mean(),
                "sensitivity after gating %": 100 * inj[f"{m}_detected_gated"].mean(),
                "specificity %": 100 - rr.loc[m, "alerts per 100 district-weeks"],
                "false alerts / 100 district-weeks": rr.loc[m, "alerts per 100 district-weeks"],
                "median delay (weeks)": float(inj.loc[det, f"{m}_delay"].median()),
            }
        )
    return pd.DataFrame(rows)


def by_disease(inj: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    rr = real_rates(sig, "disease")
    rows = []
    for dis, g in inj.groupby("disease"):
        r = {"disease": dis, "outbreaks": len(g)}
        for m in METHODS:
            r[f"{m} sens %"] = 100 * g[f"{m}_detected"].mean()
            r[f"{m} FA/100"] = rr.loc[(m, dis), "alerts per 100 district-weeks"]
        rows.append(r)
    return pd.DataFrame(rows)


def by_size(inj: pd.DataFrame) -> pd.DataFrame:
    inj = inj.assign(k_band=pd.cut(inj["k"], [1, 3, 6, 10], labels=["2-3 SD", "4-6 SD", "7-10 SD"]))
    t = inj.groupby("k_band", observed=True)[[f"{m}_detected" for m in METHODS]].mean() * 100
    t.columns = [LABEL[m] for m in METHODS]
    t.index.name = "outbreak size (x series SD)"
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


# ------------------------------------------------------------------ report


def main() -> None:
    cfg = radar_cfg()
    with open(CACHE, "rb") as f:
        fits_all = pickle.load(f)["fits"]
    sig = pd.read_parquet(CLEAN_DIR / "radar_signals.parquet")
    q = float(sig["quantile_used"].iloc[0])
    panel, skipped = load_panel(cfg["first_year"], cfg["min_history_weeks"])
    rng = np.random.default_rng(SEED)
    inj = inject(panel, fits_all, cfg, q, rng)
    inj.to_parquet(CLEAN_DIR / "radar_injections.parquet", index=False)
    head = headline(inj, sig)
    perd = by_disease(inj, sig)
    size = by_size(inj)
    rr = real_rates(sig, "disease")
    nb_rate = real_rates(sig).loc["nb_glm", "shown per 100 (after gating)"]
    nd = ndcu_validation(sig)
    FIG.mkdir(parents=True, exist_ok=True)
    figs = []
    for i, (a, dis, y0) in enumerate(pick_cases(sig, panel), 1):
        p = FIG / f"radar_case{i}_{dis}_{a.replace(' ', '_')}.png"
        title = {
            1: f"{a} dengue, {y0}: observed vs expected",
            2: f"{a} leptospirosis (largest 2022-26 peak): observed vs expected",
            3: f"{a} {dis}: a busy but steady series stays quiet (NB-GLM)",
        }[i]
        case_figure(sig, a, dis, y0, p, title)
        figs.append((p, a, dis))
    tr = pd.read_parquet(CLEAN_DIR / "radar_track_record.parquet")
    write_doc(cfg, q, panel, skipped, inj, head, perd, size, rr, nb_rate, nd, figs, tr, sig)


def write_doc(cfg, q, panel, skipped, inj, head, perd, size, rr, nb_rate, nd, figs, tr, sig):
    n_series = panel.groupby(["area", "disease"]).ngroups
    last = panel.dropna(subset=["source_issue"]).sort_values("t").iloc[-1]
    L = [
        "# Radar backtest",
        "",
        f"Generated {date.today()} by `python -m radar_lk.radar.run` then `python -m "
        f"radar_lk.radar.backtest`. "
        "Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (WER Table 1); external "
        "validation: National Dengue Control Unit (NDCU) Weekly Dengue Update.",
        "",
        "## Data and design",
        "",
        f"- **Post-COVID baseline.** Only `extraction_valid` RDHS rows from **2022-W01** to "
        f"{last['epi_year']}-W{int(last['epi_week']):02d} ({last['source_issue']}). 2020-2021 "
        f"reporting was "
        "distorted by COVID-19, so the baselines deliberately start in 2022; the cost is that "
        "seasonal "
        "models have at most ~3.5 years of history.",
        "- **Weekly counts as first printed** in each issue (what a Regional Epidemiologist saw "
        "that week), "
        "never later back-filled values.",
        f"- **Series:** {n_series} RDHS x disease series with >= {cfg['min_history_weeks']} "
        f"observed weeks. "
        f"Not modelled (insufficient history): {len(skipped)} series "
        f"({', '.join(f'{d} x{c}' for d, c in skipped['disease'].value_counts().items())}).",
        "- **No lookahead.** Every method uses only weeks before t; `tests/test_radar.py::"
        "test_no_lookahead` changes future weeks and checks no earlier signal moves.",
        "",
        "| method | rule |",
        "|---|---|",
        f"| Status quo | alert if count >= {cfg['status_quo_factor']:g} x the same week last year "
        f"and >= "
        f"{cfg['min_count']} |",
        f"| EARS C2 | baseline = {cfg['ears_baseline']} weeks ending {cfg['ears_guard']} weeks "
        f"before t "
        f"(t-9..t-3); alert if (y - mean) / sd > {cfg['ears_c2_threshold']:g} (sd floored at "
        f"{cfg['ears_sd_floor']:g}) |",
        f"| EARS C3 | sum over t, t-1, t-2 of max(0, C2 - 1) > {cfg['ears_c3_threshold']:g} |",
        f"| NB-GLM | log mu = intercept + linear trend + Fourier (period "
        f"{cfg['nb_fourier_period']}, "
        f"K={cfg['nb_fourier_k']}); fitted on past weeks only, refitted every "
        f"{cfg['nb_refit_every']} "
        f"weeks after {cfg['nb_min_train_weeks']} observed weeks; past weeks with Anscombe "
        f"residual > "
        f"{cfg['nb_reweight_threshold']} down-weighted (r^-2); alert if observed > the "
        f"{100 * q:g}th-percentile NB bound |",
        "",
        f"Every method also needs observed >= {cfg['min_count']}. **Gating:** an alert in a week "
        f"whose "
        "completeness is below the RDHS's own past 10th percentile is kept but `suppressed` with "
        "the "
        "reason; a `revised` week keeps its alert and carries the marker. Parameter uncertainty "
        "of the "
        "NB fit is not added to the bound (it slightly narrows the band).",
        "",
        "## a) Injected-outbreak evaluation",
        "",
        f"{len(inj)} simulated outbreaks ({N_PER_DISEASE} per disease, seed {SEED}) added to the "
        f"real "
        "series: start week uniform over 2024-W01 onwards (where the NB-GLM already has a fit), "
        "duration "
        "1-4 weeks, total size ~ negative binomial (dispersion 2) with mean k x the series' SD, k "
        "uniform on 2..10, spread evenly over the weeks. **Sensitivity** = share of outbreaks "
        "with an "
        "alert in an outbreak week; **delay** = weeks from outbreak start to the first such alert "
        "(0 = first week). **Specificity / false alerts** come from the real 2024-2026 data, "
        "counting "
        "every real alert as false: a conservative bound, since some real alerts are real rises.",
        "",
        md(head),
        "",
        "Sensitivity by outbreak size:",
        "",
        md(size, index=True),
        "",
        "Per disease (sensitivity % on injected outbreaks; FA/100 = real alerts per 100 "
        "district-weeks):",
        "",
        md(perd),
        "",
        "## b) Real-data alert rates (2024 onwards)",
        "",
        md(real_rates(sig).rename(index=LABEL), index=True),
        "",
        f"**Stop rule** (NB-GLM must not flag more than {100 * cfg['max_alert_rate']:.0f}% of "
        f"district-"
        f"weeks): NB-GLM shows alerts in {nb_rate:.2f} per 100 district-weeks at the "
        f"{100 * q:g}th percentile, "
        + (
            "so the configured quantile was kept."
            if q == cfg["quantile"]
            else f"after tightening the quantile from {cfg['quantile']} to {q}."
        ),
        "",
        "Per disease, alerts per 100 district-weeks (shown after gating):",
        "",
    ]
    t = rr["shown per 100 (after gating)"].unstack("method")[METHODS]
    t.columns = [LABEL[m] for m in METHODS]
    L += [md(t, index=True), ""]
    L += [
        "## c) External validation: dengue radar vs NDCU 2026 high-risk MOH lists",
        "",
        f"District x week pairs in 2026 where both exist (weeks "
        f"{nd['_weeks'][0]}-{nd['_weeks'][-1]}). "
        "NDCU flags an MOH area as high-risk from its own case counts; a district is "
        "'NDCU-positive' "
        "when at least 1 (or at least 3) of its MOH areas is on the list. The two signals answer "
        "different questions (NDCU: absolute burden; radar: unusual for this district and "
        "season), so "
        "high concordance is not expected; the lead/lag is the more useful number.",
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
            "NB-GLM pooled correlation of the two weekly 0/1 series at lag L (radar shifted by L "
            "weeks; L < 0 means the radar leads): "
            + ", ".join(f"L={k}: {v:.2f}" for k, v in xc.items())
            + f". Peak at L = {peak}.",
            "",
        ]
    x = nd["nb_glm"][1]
    x["ndcu3"] = x["n_moh"] >= 3
    miss = x[x["ndcu3"] & ~x["alert_shown"]].sort_values("n_moh", ascending=False)
    extra = x[x["alert_shown"] & (x["n_moh"] == 0)]
    L += [
        "### Disagreements (NB-GLM)",
        "",
        f"- NDCU >= 3 MOH flagged but no radar alert: {len(miss)} district-weeks; largest: "
        + ", ".join(f"{r.area} W{r.epi_week} ({r.n_moh} MOH)" for r in miss.head(12).itertuples())
        + ".",
        f"- Radar alert but no MOH flagged: {len(extra)} district-weeks: "
        + ", ".join(f"{r.area} W{r.epi_week}" for r in extra.head(20).itertuples())
        + ".",
        "",
    ]
    obs = sig[
        (sig["method"] == "nb_glm") & (sig["disease"] == "dengue") & (sig["epi_year"] == 2026)
    ]
    obs = obs[["area", "epi_week", "observed", "expected", "upper"]]
    mm = miss.merge(obs, on=["area", "epi_week"], how="left")
    top = mm["area"].value_counts()
    within = 100 * float(
        ((mm["observed"] > mm["expected"]) & (mm["observed"] <= mm["upper"])).mean()
    )
    below = 100 * float((mm["observed"] <= mm["expected"]).mean())
    ex = extra.merge(obs, on=["area", "epi_week"], how="left")
    med_obs = float(ex["observed"].median()) if len(ex) else float("nan")
    by_wk = ex["epi_week"].value_counts()
    L += [
        f"What the data say about the disagreements: of the {len(mm)} NDCU-only district-weeks, "
        f"{100 * top.head(3).sum() / max(len(mm), 1):.0f}% are {', '.join(top.head(3).index)}. In "
        f"{within:.0f}% the observed count was above the radar's expected value but within its "
        f"upper "
        f"bound, and in {below:.0f}% at or below the expected value: high in absolute terms "
        f"(NDCU's "
        "view) but within what the radar expects for that district and season. The "
        f"{len(ex)} radar-only district-weeks have a median observed count of {med_obs:.0f} "
        f"(rises from a low base); the busiest weeks are "
        + ", ".join(f"W{w} ({n})" for w, n in by_wk.head(3).items())
        + ". 2026-W14 and W24 are no longer among them because those issues are now queued as "
        "`scrambled_weekly_column` (see docs/EXTRACTION_REPORT.md section 5b).",
        "",
    ]
    L += ["## d) Case studies", ""]
    for p, a, dis in figs:
        L += [f"![{a} {dis}](figures/{p.name})", ""]
    trn = tr[tr["method"] == "nb_glm"]
    weighted = np.nansum(trn["followed_by_second_high_week"] * trn["alerts"])
    second_share = 100 * weighted / max(trn["alerts"].sum(), 1)
    L += [
        "## e) Track record (for the dashboard)",
        "",
        "`data/clean/radar_track_record.parquet`: per series and method, shown alerts, alerts "
        "per 100 "
        "weeks, and the share of alerts followed by a second high week (the next week also "
        "alerting "
        "or above its bound).",
        "",
        f"NB-GLM: {int(trn['alerts'].sum())} shown alerts over "
        f"{int(trn['weeks_evaluated'].sum()):,} "
        f"series-weeks; "
        f"{second_share:.0f}% "
        "followed by a second high week.",
        "",
        "## Limitations",
        "",
        "- Injected outbreaks are synthetic; detection of real events of other shapes may differ.",
        "- Real alerts are all counted as false for specificity, which understates specificity.",
        "- NB bounds ignore parameter uncertainty; with 1-3 seasons of post-COVID history the "
        "seasonal terms are estimated from few cycles.",
        "- TB starts in 2024, so its NB-GLM only predicts from 2025.",
        "",
    ]
    DOC.write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {DOC}")
    print(md(head))


if __name__ == "__main__":
    main()
