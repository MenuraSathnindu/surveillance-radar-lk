"""Evaluation pieces for the radar backtest (proposal section 9).

* null_false_alerts  true false-alert rate per method and threshold, from outbreak-free simulation
* inject_stats       injected outbreaks, storing each method's statistic so thresholds can be swept
* sweep / matched    sensitivity vs null false-alert rate; sensitivity at 1 and 2 false alerts / 100
* define_events      known events, located in OUR data (case counts vs reference years; rainfall)
* replay             first alert week per method and district against the status-quo rule
* gating_eval        do completeness-suppressed alerts look more like artefacts than kept ones?
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy import stats

from radar_lk.radar.methods import design, ears, nb_fits, refit_points, status_quo
from radar_lk.radar.nullsim import (
    DEFAULT_THRESHOLD,
    GRIDS,
    R_DEFAULT,
    alerts,
    simulate_series,
)

METHODS = ["status_quo", "ears_c2", "ears_c3", "nb_glm"]

# ------------------------------------------------------------------ null simulation


def null_false_alerts(panel, fits_all, cfg, R=R_DEFAULT, seed=20261106) -> pd.DataFrame:
    """Alerts per 100 district-weeks on outbreak-free simulated years, per method x threshold x
    disease (and 'all').
    Returns a long table: method, threshold, disease, weeks, alerts, fa_per_100."""
    rng = np.random.default_rng(seed)
    rows = []
    mc = cfg["min_count"]
    for (a, d), g in panel.groupby(["area", "disease"], sort=True):
        fits = fits_all.get((a, d)) or {}
        if not fits:
            continue
        beta, alpha = fits[max(fits)]
        T = len(g)
        st = simulate_series(beta, alpha, np.arange(T - 156, T), cfg, R, rng)
        n = st["y"].size
        for m in METHODS:
            for th in GRIDS[m]:
                rows.append(
                    {
                        "area": a,
                        "disease": d,
                        "method": m,
                        "threshold": th,
                        "weeks": n,
                        "alerts": int(alerts(st, m, th, mc).sum()),
                    }
                )
    df = pd.DataFrame(rows)
    by = df.groupby(["method", "threshold", "disease"])[["weeks", "alerts"]].sum().reset_index()
    tot = df.groupby(["method", "threshold"])[["weeks", "alerts"]].sum().reset_index()
    tot["disease"] = "all"
    out = pd.concat([by, tot], ignore_index=True)
    out["fa_per_100"] = 100 * out["alerts"] / out["weeks"]
    return out


# ------------------------------------------------------------------ injections


def nb_u(y, fits, cfg, weeks) -> np.ndarray:
    """F(y-1) under the NB predictive for each week in `weeks` (alert at q <=> u >= q)."""
    X = design(np.arange(len(y)), cfg["nb_fourier_period"], cfg["nb_fourier_k"])
    pts = sorted(fits)
    out = np.full(len(weeks), np.nan)
    for i, t in enumerate(weeks):
        cand = [p for p in pts if p <= t]
        if not cand:
            continue
        beta, alpha = fits[max(cand)]
        mu = float(np.exp(np.clip(X[t] @ beta, -20, 15)))
        size = 1.0 / alpha
        out[i] = stats.nbinom.cdf(y[t] - 1, size, size / (size + mu))
    return out


def inject_stats(
    panel, fits_all, cfg, rng, n_per_disease=200, k_values=range(1, 11), eval_from=2024
) -> pd.DataFrame:
    """Simulated outbreaks added to the real series (start 2024 onwards, where the NB-GLM has a
    fit; 1-4 weeks; total size ~ NB(dispersion 2) with mean k x the series' SD, k uniform on
    `k_values`, spread evenly). Stores every method's statistic in the outbreak weeks."""
    rows = []
    k_values = list(k_values)
    for dis, gd in panel.groupby("disease"):
        series = {a: g.reset_index(drop=True) for a, g in gd.groupby("area")}
        areas = sorted(series)
        made = tries = 0
        while made < n_per_disease and tries < 50 * n_per_disease:
            tries += 1
            a = areas[rng.integers(len(areas))]
            g = series[a]
            y = g["observed"].to_numpy(float)
            fits = fits_all[(a, dis)]
            pts = refit_points(y, cfg["nb_min_train_weeks"], cfg["nb_refit_every"])
            if not pts:
                continue
            dur = int(rng.integers(1, 5))
            t_eval = int(g.index[g["epi_year"] >= eval_from].min())
            lo, hi = max(t_eval, pts[0]), len(y) - dur
            if hi <= lo:
                continue
            s = int(rng.integers(lo, hi + 1))
            window = np.arange(s, s + dur)
            if np.isnan(y[window]).any():
                continue
            sd = max(float(np.nanstd(y)), 1.0)
            k = int(k_values[rng.integers(len(k_values))])
            mean = k * sd
            size = 0
            while size < 1:
                size = int(rng.negative_binomial(2, 2 / (2 + mean)))
            add = rng.multinomial(size, np.full(dur, 1 / dur))
            y2 = y.copy()
            y2[window] += add
            redo = [r for r in pts if s < r <= window[-1]]
            f2 = nb_fits(y2, cfg, points=redo, base=fits) if redo else fits
            e = ears(
                y2,
                cfg["ears_baseline"],
                cfg["ears_guard"],
                cfg["ears_c2_threshold"],
                cfg["ears_c3_threshold"],
                cfg["ears_sd_floor"],
                cfg["min_count"],
            )
            prev = status_quo(y2, g["epi_year"].to_numpy(), g["epi_week"].to_numpy())["expected"]
            rows.append(
                {
                    "disease": dis,
                    "area": a,
                    "start_t": s,
                    "duration": dur,
                    "size": size,
                    "k": k,
                    "sd": sd,
                    "start_year": int(g["epi_year"][s]),
                    "start_week": f"{g['epi_year'][s]}-W{g['epi_week'][s]:02d}",
                    "y": y2[window].tolist(),
                    "nb_u": nb_u(y2, f2, cfg, window).tolist(),
                    "c2": e["ears_c2"]["stat"][window].tolist(),
                    "c3": e["ears_c3"]["stat"][window].tolist(),
                    "prev": prev[window].tolist(),
                    "low": g["completeness_low"]
                    .fillna(False)
                    .astype(bool)
                    .to_numpy()[window]
                    .tolist(),
                }
            )
            made += 1
    return pd.DataFrame(rows)


def _window(row) -> dict:
    return {k: np.asarray(row[k], float) for k in ("y", "nb_u", "c2", "c3", "prev")}


def detect(inj: pd.DataFrame, method: str, threshold: float, min_count: int, gated=False):
    """(detected bool array, delay array in weeks; NaN when not detected)."""
    det = np.zeros(len(inj), bool)
    delay = np.full(len(inj), np.nan)
    for i, (_, r) in enumerate(inj.iterrows()):
        st = _window(r)
        a = alerts(st, method, threshold, min_count)
        a = a & ~np.isnan(st["nb_u"] if method == "nb_glm" else st["y"])
        if gated:
            a = a & ~np.asarray(r["low"], bool)
        hit = np.flatnonzero(a)
        if len(hit):
            det[i] = True
            delay[i] = hit[0]
    return det, delay


def sweep(inj: pd.DataFrame, null: pd.DataFrame, min_count: int) -> pd.DataFrame:
    rows = []
    for m in METHODS:
        for th in GRIDS[m]:
            det, delay = detect(inj, m, th, min_count)
            fa = null[
                (null["method"] == m) & (null["threshold"] == th) & (null["disease"] == "all")
            ]
            rows.append(
                {
                    "method": m,
                    "threshold": th,
                    "null_fa_per_100": float(fa["fa_per_100"].iloc[0]),
                    "sensitivity": 100 * det.mean(),
                    "median_delay": float(np.nanmedian(delay)) if det.any() else np.nan,
                    "default": th == DEFAULT_THRESHOLD[m],
                }
            )
    return pd.DataFrame(rows)


def matched(sw: pd.DataFrame, targets=(1.0, 2.0)) -> pd.DataFrame:
    """Sensitivity at a fixed null false-alert rate, by linear interpolation along each curve."""
    rows = []
    for m, g in sw.groupby("method"):
        g = g.sort_values("null_fa_per_100")
        fa, se = g["null_fa_per_100"].to_numpy(), g["sensitivity"].to_numpy()
        r = {"method": m}
        for t in targets:
            r[f"sensitivity at {t:g} FA/100"] = (
                float(np.interp(t, fa, se)) if fa.min() <= t <= fa.max() else np.nan
            )
        rows.append(r)
    return pd.DataFrame(rows)


def thresholds_at(sw: pd.DataFrame, method: str, target: float):
    """Two grid thresholds bracketing `target` null FA and the interpolation weight of the first."""
    g = sw[sw["method"] == method].sort_values("null_fa_per_100").reset_index(drop=True)
    fa = g["null_fa_per_100"].to_numpy()
    if not (fa.min() <= target <= fa.max()):
        return None
    j = int(np.searchsorted(fa, target))
    j = min(max(j, 1), len(g) - 1)
    lo, hi = g.iloc[j - 1], g.iloc[j]
    w = (
        1.0
        if hi["null_fa_per_100"] == lo["null_fa_per_100"]
        else ((hi["null_fa_per_100"] - target) / (hi["null_fa_per_100"] - lo["null_fa_per_100"]))
    )
    return lo["threshold"], hi["threshold"], w


def size_curve(inj, sw, min_count, target=1.0, ks=(1, 2, 3, 4)) -> pd.DataFrame:
    """Sensitivity by outbreak size (k x SD) for each method at a matched null FA of `target`."""
    rows = []
    for m in METHODS:
        b = thresholds_at(sw, m, target)
        if b is None:
            continue
        lo, hi, w = b
        d_lo, _ = detect(inj, m, lo, min_count)
        d_hi, _ = detect(inj, m, hi, min_count)
        for k in ks:
            sel = inj["k"].to_numpy() == k
            rows.append(
                {
                    "method": m,
                    "k": k,
                    "outbreaks": int(sel.sum()),
                    "sensitivity": 100 * (w * d_lo[sel].mean() + (1 - w) * d_hi[sel].mean()),
                }
            )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ known events


def _key(y: int, w: int) -> int:
    return y * 100 + w


def _runs(above: pd.Series, min_run: int) -> list[list[int]]:
    """Runs of True in a week-indexed series; one missing week (NaN) inside a run is bridged."""

    def yes(v) -> bool:
        return not pd.isna(v) and bool(v)

    vals = list(above.items())
    flags = [yes(v) for _, v in vals]
    for i in range(1, len(vals) - 1):
        if pd.isna(vals[i][1]) and flags[i - 1] and flags[i + 1]:
            flags[i] = True
    runs, cur = [], []
    for (w, _), a in zip(vals, flags, strict=True):
        if a:
            cur.append(w)
        else:
            if len(cur) >= min_run:
                runs.append(cur)
            cur = []
    if len(cur) >= min_run:
        runs.append(cur)
    return runs


def _excess(c, disease, year, refs, weeks, ratio, min_excess) -> pd.DataFrame:
    d = c[(c["disease"] == disease) & c["epi_week"].isin(weeks)]
    obs = d[d["epi_year"] == year].groupby("area")["cases"].sum()
    ref = (
        d[d["epi_year"].isin(refs)]
        .groupby(["area", "epi_year"])["cases"]
        .sum()
        .groupby("area")
        .mean()
    )
    t = pd.DataFrame({"observed": obs, "reference_mean": ref}).fillna(0)
    t["ratio"] = t["observed"] / t["reference_mean"].replace(0, np.nan)
    t["excess"] = t["observed"] - t["reference_mean"]
    return t[(t["ratio"] >= ratio) & (t["excess"] >= min_excess)].sort_values(
        "excess", ascending=False
    )


def define_events(clean: pd.DataFrame, weather: pd.DataFrame, max_districts: int = 8) -> list[dict]:
    """Locate each named event in our own data, with the rule used, instead of assuming it."""
    c = clean[clean["area_level"] == "rdhs"]
    ev = []
    # 1. 2024 leptospirosis surge: weeks where the national weekly count exceeds 1.25 x the
    #    larger of 2022 and 2023 in the same week, >= 3 weeks in a row
    p = (
        c[c["disease"] == "leptospirosis"]
        .groupby(["epi_year", "epi_week"])["cases"]
        .sum()
        .unstack(0)
    )
    above = (p[2024] > 1.25 * p[[2022, 2023]].max(axis=1)).where(p[2024].notna())
    for run in _runs(above.astype(object), 3):
        dist = _excess(c, "leptospirosis", 2024, [2022, 2023], run, 1.5, 30)
        ev.append(
            {
                "event": f"Leptospirosis 2024, W{run[0]:02d}-W{run[-1]:02d}",
                "disease": "leptospirosis",
                "start": _key(2024, run[0]),
                "end": _key(2024, run[-1]),
                "districts": list(dist.index[:max_districts]),
                "evidence": dist.head(max_districts),
                "rule": "national weekly > 1.25 x max(2022, 2023) same week for >= 3 weeks; "
                "districts with >= 1.5 x their 2022-23 mean over the window and >= 30 excess cases",
            }
        )
    # 2. 2026 dengue outbreak: national weekly above every same week of 2023-2025, >= 3 weeks
    p = c[c["disease"] == "dengue"].groupby(["epi_year", "epi_week"])["cases"].sum().unstack(0)
    above = (p[2026] > p[[2023, 2024, 2025]].max(axis=1)).where(p[2026].notna())
    runs = _runs(above.astype(object), 3)
    run = max(runs, key=len)
    dist = _excess(c, "dengue", 2026, [2023, 2024, 2025], run, 1.5, 100)
    ev.append(
        {
            "event": f"Dengue 2026, W{run[0]:02d}-W{run[-1]:02d}",
            "disease": "dengue",
            "start": _key(2026, run[0]),
            "end": _key(2026, run[-1]),
            "districts": list(dist.index[:max_districts]),
            "evidence": dist.head(max_districts),
            "rule": "national weekly above every same week of 2023-2025 (longest run, "
            "a single missing week bridged); districts with >= 1.5 x their 2023-25 mean "
            "and >= 100 excess cases",
        }
    )
    # 3. Cyclone Ditwah: the rainfall week, from our weather data; then leptospirosis in the 12
    #    weeks after it, against the same weeks of the three previous seasons
    w = weather.copy()
    nat = w.groupby(["epi_year", "epi_week"])["precip_mm"].mean()
    late25 = nat.loc[(2025, 44) : (2025, 52)]
    wy, ww = late25.idxmax()
    p99 = w.groupby("area")["precip_mm"].quantile(0.99)
    rain = w[(w["epi_year"] == wy) & (w["epi_week"] == ww)].set_index("area")["precip_mm"]
    soaked = set(rain[rain >= 2 * p99.reindex(rain.index)].index)
    d = c[c["disease"] == "leptospirosis"].copy()
    d["season"] = np.where(d["epi_week"] >= 40, d["epi_year"], d["epi_year"] - 1)
    d["sw"] = np.where(d["epi_week"] >= 40, d["epi_week"] - 52, d["epi_week"])
    first = ww - 52 + 1
    win = d[(d["sw"] >= first) & (d["sw"] <= first + 11)]
    obs = win[win["season"] == wy].groupby("area")["cases"].sum()
    ref = (
        win[win["season"].isin([wy - 3, wy - 2, wy - 1])].groupby(["area", "season"])["cases"].sum()
    )
    ref = ref.groupby("area").mean()
    t = pd.DataFrame(
        {"observed": obs, "reference_mean": ref, "rain_mm": rain, "rain_p99_mm": p99}
    ).dropna(subset=["observed"])
    t["ratio"] = t["observed"] / t["reference_mean"]
    t["rain_x_p99"] = t["rain_mm"] / t["rain_p99_mm"]
    t = t[t.index.isin(soaked) & (t["ratio"] >= 1.5)].sort_values("ratio", ascending=False)
    end_monday = date.fromisocalendar(wy, ww, 1) + timedelta(weeks=12)
    ey, ewk = end_monday.isocalendar()[:2]
    ev.append(
        {
            "event": f"After Cyclone Ditwah (rain week {wy}-W{ww:02d}): leptospirosis",
            "disease": "leptospirosis",
            "start": _key(wy, ww),
            "end": _key(ey, ewk),
            "districts": list(t.index[:max_districts]),
            "evidence": t.head(max_districts),
            "rule": f"exposure = the wettest week of late 2025 in our Open-Meteo data "
            f"({wy}-W{ww:02d}, "
            f"national mean {late25.max():.0f} mm, the highest week since 2021); districts whose "
            f"rain "
            "that week was >= 2 x their own 2021-26 99th percentile AND whose leptospirosis in the "
            "next 12 weeks was >= 1.5 x the same weeks of the three previous seasons",
        }
    )
    return ev


def replay(sig: pd.DataFrame, events: list[dict], lead: int = 4) -> pd.DataFrame:
    """First week each method alerted per event and district, from `lead` weeks before the event
    start (the rain week itself for Ditwah) to its end; weeks gained = status quo first - method
    first (positive = earlier than the status-quo rule).

    A first alert in the very first week of that search window is left-censored (the method may
    already have been alerting before it, e.g. a surge that started earlier); it is shown as
    '<=week' and any gain involving it is left empty rather than guessed."""
    rows = []
    s = sig.assign(key=sig["epi_year"] * 100 + sig["epi_week"])
    for ev in events:
        start_t = s.loc[s["key"] == ev["start"], "t"].min()
        end_t = s.loc[s["key"] == ev["end"], "t"].max()
        if pd.isna(end_t):
            end_t = s["t"].max()
        lo = start_t if "Ditwah" in ev["event"] else start_t - lead
        for a in ev["districts"]:
            r = {"event": ev["event"], "district": a}
            g = s[(s["area"] == a) & (s["disease"] == ev["disease"]) & s["t"].between(lo, end_t)]
            for m in METHODS:
                h = g[(g["method"] == m) & g["alert_shown"]]
                r[f"{m}_first"] = (int(h["t"].min() - start_t)) if len(h) else np.nan
                r[f"{m}_censored"] = bool(len(h)) and int(h["t"].min()) == int(lo)
                r[f"{m}_week"] = (
                    (
                        ("<=" if r[f"{m}_censored"] else "")
                        + f"{int(h.sort_values('t')['epi_year'].iloc[0])}-W"
                        f"{int(h.sort_values('t')['epi_week'].iloc[0]):02d}"
                    )
                    if len(h)
                    else "none"
                )
            for m in METHODS[1:]:
                censored = r["status_quo_censored"] or r[f"{m}_censored"]
                r[f"{m}_gain"] = np.nan if censored else r["status_quo_first"] - r[f"{m}_first"]
            rows.append(r)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ completeness gating


def gating_eval(sig: pd.DataFrame) -> pd.DataFrame:
    """For every raw alert: was the NEXT week's cumulative revised (late reports added), by how
    much, and did the next two weeks stay above expected? Suppressed vs kept, per method."""
    s = sig.sort_values(["area", "disease", "method", "t"]).copy()
    g = s.groupby(["area", "disease", "method"])
    for k in (1, 2):
        s[f"t{k}"] = g["t"].shift(-k)
        s[f"obs{k}"] = g["observed"].shift(-k)
        s[f"exp{k}"] = g["expected"].shift(-k)
    s["rev1"] = g["revised"].shift(-1)
    s["delta1"] = g["revision_delta"].shift(-1)
    a = s[s["alert"]].copy()
    ok1 = a["t1"] == a["t"] + 1
    ok2 = ok1 & (a["t2"] == a["t"] + 2)
    a["next_revised"] = np.where(ok1 & a["rev1"].notna(), a["rev1"].astype(float), np.nan)
    a["next_delta_pos"] = np.where(
        ok1 & a["delta1"].notna(), (a["delta1"] > 0).astype(float), np.nan
    )
    a["next_delta"] = np.where(ok1, a["delta1"], np.nan)
    a["stayed_up_2wk"] = np.where(
        ok2, ((a["obs1"] > a["exp1"]) & (a["obs2"] > a["exp2"])).astype(float), np.nan
    )
    rows = []
    for m in METHODS + ["all"]:
        x = a if m == "all" else a[a["method"] == m]
        for grp, y in (("suppressed", x[x["suppressed"]]), ("kept", x[~x["suppressed"]])):
            rows.append(
                {
                    "method": m,
                    "alerts": grp,
                    "n": len(y),
                    "next week revised %": 100 * np.nanmean(y["next_revised"])
                    if len(y)
                    else np.nan,
                    "n (revision known)": int(y["next_revised"].notna().sum()),
                    "next week cum raised % (delta > 0)": 100 * np.nanmean(y["next_delta_pos"])
                    if len(y)
                    else np.nan,
                    "median next-week revision_delta": float(np.nanmedian(y["next_delta"]))
                    if y["next_delta"].notna().any()
                    else np.nan,
                    "next 2 weeks above expected %": 100 * np.nanmean(y["stayed_up_2wk"])
                    if len(y)
                    else np.nan,
                    "n (2-week follow-up known)": int(y["stayed_up_2wk"].notna().sum()),
                }
            )
    return pd.DataFrame(rows)
