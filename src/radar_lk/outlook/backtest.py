"""Outlook engine: rolling-origin backtest + live forecast, for every disease in config.

    python -m radar_lk.outlook.backtest            # all diseases, then the report
    python -m radar_lk.outlook.backtest --reuse    # rebuild the report from saved forecasts

Rolling origin, expanding window: origins from outlook.warmup_from (2023-W01; those forecasts
only feed the calibration pools) and evaluated from outlook.eval_from (2024-W01) to the latest
reported week. Models are refitted every `refit_every` weeks on rows whose TARGET week is <= the
refit origin (strictly past-only); the latest origin always gets a fresh fit (the live forecast).

Outputs: data/clean/outlook_forecasts.parquet (backtest + live), outlook_track_record.parquet
(metrics per disease x model x horizon x scope, and the model the dashboard uses at each horizon
under the stop rule), docs/OUTLOOK_BACKTEST.md + figures; DuckDB views refreshed.
"""

from __future__ import annotations

import pickle
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from radar_lk import CLEAN_DIR, DATA_DIR, store
from radar_lk.outlook import conformal, features
from radar_lk.outlook.models import MODELS, fit_predict

FORECASTS = CLEAN_DIR / "outlook_forecasts.parquet"
TRACK = CLEAN_DIR / "outlook_track_record.parquet"
CACHE = DATA_DIR / "cache" / "outlook_live_models.pkl"
CALIBRATED = {"glm", "lightgbm"}  # Venn-Abers on these; baselines keep their own probability


def t_of(weeks: pd.DataFrame, yw) -> int:
    y, w = yw
    s = weeks[(weeks["epi_year"] == y) & (weeks["epi_week"] == w)]["t"]
    return int(s.iloc[0])


def run_disease(inp: features.Inputs, cfg: dict, origins=None, keep_live=True):
    """Raw + calibrated forecasts for every origin; returns (forecasts, live extras)."""
    F = features.build(inp, range(8, inp.last_t + 1), cfg)
    t_warm = t_of(inp.weeks, cfg["warmup_from"])
    if origins is None:
        origins = list(range(t_warm, inp.last_t + 1))
    origins = sorted(origins)
    every = cfg["refit_every"]
    refits = list(range(origins[0], origins[-1] + 1, every))
    if origins[-1] not in refits:
        refits.append(origins[-1])  # the latest origin always gets a fresh fit
    assign = {o: max(r for r in refits if r <= o) for o in origins}
    trainable = F[F["y"].notna() & F["thr"].notna() & (F["t"] >= cfg["min_train_origin_weeks"])]
    parts, live = [], {}
    for r in refits:
        test = F[F["t"].isin([o for o in origins if assign[o] == r])]
        if test.empty:
            continue
        train = trainable[trainable["t"] + trainable["h"] <= r]
        res = fit_predict(train, test, cfg, inp.areas)
        keys = test[["area", "area_i", "t", "h", "tau", "y", "elevated", "thr"]].reset_index(
            drop=True
        )
        for m in MODELS:
            pc, pr = res[m]
            parts.append(keys.assign(model=m, pred_count=pc, p_raw=pr))
        if keep_live and r == origins[-1]:
            live = {"lgbm": res["_lgbm"], "train": train, "test": test}
    fc = pd.concat(parts, ignore_index=True)
    return calibrate(fc, cfg), live


def calibrate(fc: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    fc = fc.sort_values(["model", "h", "t", "area_i"]).reset_index(drop=True)
    for c in ("lo80", "hi80", "lo90", "hi90", "p_elevated", "p_lo", "p_hi"):
        fc[c] = np.nan
    w, mn = cfg["calib_origins"], cfg["calib_min"]
    for (m, h), g in fc.groupby(["model", "h"], sort=False):
        iv = conformal.rolling_conformal(
            g["t"], g["pred_count"], g["y"], h, cfg["conformal_levels"], w, mn
        )
        for lv, (lo, hi) in iv.items():
            k = int(round(100 * lv))
            fc.loc[g.index, f"lo{k}"], fc.loc[g.index, f"hi{k}"] = lo, hi
        if m in CALIBRATED:
            pc, lo, hi = conformal.rolling_venn_abers(g["t"], g["p_raw"], g["elevated"], h, w, mn)
            fc.loc[g.index, "p_elevated"], fc.loc[g.index, "p_lo"], fc.loc[g.index, "p_hi"] = (
                pc,
                lo,
                hi,
            )
        else:
            fc.loc[g.index, "p_elevated"] = g["p_raw"]
    return fc


# ------------------------------------------------------------------ ACI


def add_aci(fc: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Adaptive conformal intervals (`lo80_aci` ...) next to the static ones, per model x
    horizon (see conformal.rolling_aci)."""
    fc = fc.sort_values(["model", "h", "t", "area_i"]).reset_index(drop=True)
    for (_, h), g in fc.groupby(["model", "h"], sort=False):
        iv = conformal.rolling_aci(
            g["t"],
            g["pred_count"],
            g["y"],
            h,
            cfg["conformal_levels"],
            cfg["calib_origins"],
            cfg["calib_min"],
            cfg["aci_gamma"],
        )
        for lv, (lo, hi, a) in iv.items():
            k = int(round(100 * lv))
            fc.loc[g.index, f"lo{k}_aci"] = lo
            fc.loc[g.index, f"hi{k}_aci"] = hi
            fc.loc[g.index, f"alpha{k}_aci"] = a
    return fc


# ------------------------------------------------------------------ display probabilities

PRIOR_WEIGHT = 2.0  # pseudo-weeks of the 20% base rate added to a district's own frequency


def display_probabilities(fc: pd.DataFrame, base_rate: float) -> pd.DataFrame:
    """`p_display`: the probability shown on the dashboard and in the brief (post-hoc, display
    only; evaluation and model selection keep using `p_elevated`).

    GLM / LightGBM: their Venn-Abers probability (= p_elevated). Persistence and climatology are
    0/1 or a frequency over a few past weeks, so they would print as 0% or 100%. Shown instead,
    both estimated PAST-ONLY:
    * persistence: P(elevated at t+h | elevated status at t), per disease and horizon, from every
      earlier forecast whose target was already reported at the origin (expanding window, warm-up
      included), Laplace-smoothed (k + 1) / (n + 2);
    * climatology: the district's own past frequency of elevated weeks at that time of year
      (k of n past weeks, +-1 week), smoothed with PRIOR_WEIGHT pseudo-weeks at the base rate
      (20% by construction: the threshold is the past 80th percentile): (k + w r) / (n + w)."""
    fc = fc.copy()
    fc["p_display"] = fc["p_elevated"]
    cl = fc["model"] == "climatology"
    n = fc.loc[cl, "clim_n"].fillna(0).to_numpy(float)
    k = fc.loc[cl, "p_raw"].to_numpy(float) * n
    fc.loc[cl, "p_display"] = (k + PRIOR_WEIGHT * base_rate) / (n + PRIOR_WEIGHT)
    for h, g in fc[fc["model"] == "persistence"].groupby("h", sort=False):
        raw = g["p_raw"].to_numpy(float)
        grp = np.where(np.isnan(raw), -1, raw >= 0.5).astype(int)
        t, lab = g["t"].to_numpy(), g["elevated"].to_numpy(float)
        out = np.full(len(g), np.nan)
        for o in np.unique(t):
            test = t == o
            pool = (t + h <= o) & ~np.isnan(lab)
            for kk in (0, 1):
                sel = pool & (grp == kk)
                out[test & (grp == kk)] = (lab[sel].sum() + 1) / (sel.sum() + 2)
        fc.loc[g.index, "p_display"] = np.where(np.isnan(out), g["p_elevated"], out)
    return fc


# ------------------------------------------------------------------ metrics

SIMPLE = ["persistence", "climatology", "glm", "lightgbm"]  # simplest first (tie-break)
TIE = 0.01


def _auc(y, p):
    from sklearn.metrics import average_precision_score, roc_auc_score

    if len(np.unique(y)) < 2:
        return np.nan, np.nan
    return float(roc_auc_score(y, p)), float(average_precision_score(y, p))


def _cover(g: pd.DataFrame, k: int, suffix: str = "") -> tuple[float, float]:
    lo, hi = g[f"lo{k}{suffix}"], g[f"hi{k}{suffix}"]
    ok = lo.notna() & hi.notna()
    if not ok.any():
        return np.nan, np.nan
    y = g.loc[ok, "y"]
    cov = 100 * float(((y >= lo[ok]) & (y <= hi[ok])).mean())
    return cov, float((hi[ok] - lo[ok]).mean())


def scopes(fc: pd.DataFrame, cfg: dict, weeks: pd.DataFrame) -> dict:
    """Named row selections. Selection uses 2024 ORIGINS only; 2025-26 origins are the untouched
    test; 'all' and the target-year scopes are reported for reference."""
    eval_t = t_of(weeks, cfg["eval_from"])
    t25 = t_of(weeks, (cfg["eval_from"][0] + 1, 1))
    return {
        "select (2024 origins)": (fc["t"] >= eval_t) & (fc["t"] < t25),
        "test (2025-26 origins)": fc["t"] >= t25,
        "all (2024-26 origins)": fc["t"] >= eval_t,
        "2026 targets": (fc["t"] >= eval_t) & (fc["target_year"] == 2026),
        "2024-25 targets": (fc["t"] >= eval_t) & fc["target_year"].isin([2024, 2025]),
    }


def metrics(fc: pd.DataFrame, cfg: dict, weeks: pd.DataFrame) -> pd.DataFrame:
    """Per scope x model x horizon, on the rows every model has (observed targets only)."""
    key = ["area_i", "t", "h"]
    obs = fc[fc["y"].notna()]
    full = obs.pivot_table(index=key, columns="model", values="pred_count").dropna().index
    e = obs.set_index(key).loc[lambda d: d.index.isin(full)].reset_index()
    rows = []
    for scope, mask in scopes(e, cfg, weeks).items():
        sel = e[mask.to_numpy()]
        for h, gh in sel.groupby("h"):
            base = {}
            for m in ("persistence", "climatology"):
                b = gh[gh["model"] == m]
                base[m] = (
                    float(np.mean(np.abs(b["y"] - b["pred_count"]))),
                    float(np.mean((b["p_elevated"] - b["elevated"]) ** 2)),
                )
            for m, g in gh.groupby("model"):
                err = g["y"] - g["pred_count"]
                mae = float(np.mean(np.abs(err)))
                c = g.dropna(subset=["p_elevated", "elevated"])
                yb, pb = c["elevated"].to_numpy(int), c["p_elevated"].to_numpy(float)
                brier = float(np.mean((pb - yb) ** 2)) if len(c) else np.nan
                pred = pb >= 0.5
                auroc, prauc = _auc(yb, pb)
                r = {
                    "scope": scope,
                    "model": m,
                    "h": int(h),
                    "n": len(g),
                    "MAE": mae,
                    "RMSE": float(np.sqrt(np.mean(err**2))),
                    "MASE vs persistence": mae / base["persistence"][0],
                    "n_class": len(c),
                    "base rate %": 100 * float(yb.mean()) if len(c) else np.nan,
                    "Brier": brier,
                    "BSS vs persistence": 1 - brier / base["persistence"][1],
                    "BSS vs climatology": 1 - brier / base["climatology"][1],
                    "recall": float(pred[yb == 1].mean()) if (yb == 1).any() else np.nan,
                    "precision": float(yb[pred].mean()) if pred.any() else np.nan,
                    "AUROC": auroc,
                    "PR-AUC": prauc,
                }
                for k in (80, 90):
                    r[f"coverage{k} %"], r[f"width{k}"] = _cover(g, k)
                    r[f"coverage{k} ACI %"], r[f"width{k} ACI"] = _cover(g, k, "_aci")
                cd = g.dropna(subset=["p_display", "elevated"])
                r["Brier (display)"] = (
                    float(np.mean((cd["p_display"] - cd["elevated"]) ** 2)) if len(cd) else np.nan
                )
                if m in CALIBRATED:
                    ok = g["p_lo"].notna()
                    r["mean p range"] = (
                        float((g.loc[ok, "p_hi"] - g.loc[ok, "p_lo"]).mean())
                        if ok.any()
                        else np.nan
                    )
                rows.append(r)
    return pd.DataFrame(rows)


def _pick(g: pd.Series) -> tuple[str, str]:
    """Lowest score in `g` (index = model); any model within TIE of the best counts as a tie and
    the simplest of them is kept."""
    top = g.idxmin()
    near = [m for m in SIMPLE if m in g.index and g[m] - g[top] <= TIE]
    pick = near[0]
    if pick == top:
        why = f"best on 2024 origins ({g[pick]:.3f})"
    else:
        why = (
            f"within {TIE:g} of the best on 2024 origins ({top} {g[top]:.3f}, {pick} "
            f"{g[pick]:.3f}); the simpler model is kept"
        )
    return pick, why


def select(tr: pd.DataFrame) -> pd.DataFrame:
    """Per horizon: count model by MASE and probability model by Brier, on 2024 origins only."""
    a = tr[tr["scope"] == "select (2024 origins)"]
    rows = []
    for h, g in a.groupby("h"):
        g = g.set_index("model")
        cm, cw = _pick(g["MASE vs persistence"])
        pm, pw = _pick(g["Brier"])
        rows.append(
            {
                "h": int(h),
                "selected count model": cm,
                "count selection reason": f"MASE {cw}",
                "selected probability model": pm,
                "probability selection reason": f"Brier {pw}",
            }
        )
    return pd.DataFrame(rows)


def aci_decision(tr: pd.DataFrame, sel: pd.DataFrame, cfg: dict) -> dict:
    """Use ACI on the dashboard if, for the selected count models pooled over horizons, it brings
    2026 coverage closer to nominal at both levels without moving 2024-25 coverage more than
    `aci_tolerance_pp` from nominal."""
    pick = sel.set_index("h")["selected count model"]
    tol = cfg["aci_tolerance_pp"]
    cov = {}
    for scope in ("2026 targets", "2024-25 targets"):
        a = tr[tr["scope"] == scope]
        a = a[a["model"].to_numpy() == pick.reindex(a["h"]).to_numpy()]
        w = a["n"] / a["n"].sum()
        for k in (80, 90):
            cov[(scope, k, "static")] = float((a[f"coverage{k} %"] * w).sum())
            cov[(scope, k, "aci")] = float((a[f"coverage{k} ACI %"] * w).sum())
    s26, s25 = "2026 targets", "2024-25 targets"
    better = all(abs(cov[(s26, k, "aci")] - k) < abs(cov[(s26, k, "static")] - k) for k in (80, 90))
    safe = all(abs(cov[(s25, k, "aci")] - k) <= tol for k in (80, 90))
    use = better and safe
    why = (
        f"ACI {'used' if use else 'not used'}: 2026 coverage 80/90 static "
        f"{cov[(s26, 80, 'static')]:.1f}/{cov[(s26, 90, 'static')]:.1f}% -> ACI "
        f"{cov[(s26, 80, 'aci')]:.1f}/{cov[(s26, 90, 'aci')]:.1f}% "
        f"({'closer to' if better else 'not closer to'} nominal); 2024-25 ACI "
        f"{cov[(s25, 80, 'aci')]:.1f}/{cov[(s25, 90, 'aci')]:.1f}% "
        f"({'within' if safe else 'outside'} +-{tol:g} pp of nominal)"
    )
    return {"use": use, "why": why, "coverage": cov}


# ------------------------------------------------------------------ outputs


def finish(fc: pd.DataFrame, inp: features.Inputs, eval_t: int, sel: pd.DataFrame, aci: dict):
    weeks = inp.weeks.set_index("t")
    fc = fc[fc["t"] >= eval_t].copy()
    fc["disease"] = inp.disease
    fc["origin_week"] = features.week_label(inp.weeks, fc["t"].to_numpy())
    fc["target_week"] = features.week_label(inp.weeks, fc["tau"].to_numpy())
    fc["target_year"] = weeks.loc[fc["tau"], "epi_year"].to_numpy()
    fc["target_week_start"] = weeks.loc[fc["tau"], "week_start"].to_numpy()
    ws = pd.to_datetime(weeks.loc[fc["t"], "week_start"].to_numpy())
    fc["as_of"] = (ws + timedelta(days=6)).date
    fc["kind"] = np.where(fc["t"] == inp.last_t, "live", "backtest")
    iss = {}
    for i in range(inp.A):
        for t in np.unique(fc["t"]):
            v = [s for s in inp.issues[i, max(0, t - 7) : t + 1] if s]
            iss[(i, t)] = "; ".join(dict.fromkeys(v))
    ai = fc["area_i"].to_numpy()
    tt = fc["t"].to_numpy()
    fc["source_issues"] = [iss[(i, t)] for i, t in zip(ai, tt, strict=True)]
    fc["source_issue"] = [v.split("; ")[-1] if v else "" for v in fc["source_issues"]]
    fc = fc.rename(
        columns={"thr": "elevated_threshold", "y": "observed", "elevated": "elevated_obs"}
    )
    s = sel.set_index("h")
    fc["dashboard_count"] = (
        fc["model"].to_numpy() == s.loc[fc["h"], "selected count model"].to_numpy()
    )
    fc["dashboard_class"] = (
        fc["model"].to_numpy() == s.loc[fc["h"], "selected probability model"].to_numpy()
    )
    fc["interval_method"] = "aci" if aci["use"] else "static"
    fc["area"] = fc["area"].astype(str)
    return fc


COLS = [
    "area", "disease", "origin_week", "target_week", "h", "model", "pred_count", "lo80", "hi80",
    "lo90", "hi90", "lo80_aci", "hi80_aci", "lo90_aci", "hi90_aci", "p_elevated", "p_lo", "p_hi",
    "elevated_threshold", "as_of", "source_issues", "source_issue", "kind", "observed",
    "elevated_obs", "p_raw", "p_display", "target_year", "target_week_start", "dashboard_count",
    "dashboard_class", "interval_method", "t", "tau",
]  # fmt: skip
RAW = DATA_DIR / "cache" / "outlook_raw.parquet"


def run_one(d: str, cfg: dict):
    """Rolling-origin forecasts (warm-up included) for one disease: (raw rows, live extras)."""
    inp = features.load_inputs(d, cfg)
    print(f"{d}: {inp.A} districts, latest reported week t={inp.last_t}; running ...", flush=True)
    fc, live = run_disease(inp, cfg)
    fc["disease"] = d
    live = {**live, "areas": inp.areas, "last_t": inp.last_t, "weeks": inp.weeks}
    return fc, live


def post(cfg: dict, raw: pd.DataFrame, lives: dict) -> None:
    """From the raw forecasts: ACI, metrics, model selection, outputs, report."""
    from radar_lk.outlook import report

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fcs, trs = [], []
    for d in cfg["diseases"]:
        inp = features.load_inputs(d, cfg)
        fc = raw[raw["disease"] == d].drop(columns="disease").copy()
        fc["area"] = pd.Categorical(fc["area"].astype(str), categories=inp.areas)
        weeks = inp.weeks.set_index("t")
        fc["target_year"] = weeks.loc[fc["tau"], "epi_year"].to_numpy()
        fc = add_aci(fc, cfg)
        cn = features.build(inp, sorted(fc["t"].unique()), cfg)[["area_i", "t", "h", "clim_n"]]
        fc = fc.merge(cn, on=["area_i", "t", "h"], how="left")
        fc = display_probabilities(fc, 1 - cfg["elevated_quantile"])
        tr = metrics(fc, cfg, inp.weeks)
        sel = select(tr)
        aci = aci_decision(tr, sel, cfg)
        out = finish(fc, inp, t_of(inp.weeks, cfg["eval_from"]), sel, aci)
        out["computed_at"] = now
        fcs.append(out)
        tr = tr.assign(disease=d, interval_method="aci" if aci["use"] else "static")
        tr["interval reason"] = aci["why"]
        trs.append(tr.merge(sel, on="h", how="left"))
        print(f"{d}: {aci['why']}")
        print(sel.to_string(index=False))
    fc_all = pd.concat(fcs, ignore_index=True)[COLS + ["computed_at"]]
    tr_all = pd.concat(trs, ignore_index=True)
    fc_all.to_parquet(FORECASTS, index=False)
    tr_all.to_parquet(TRACK, index=False)
    store.refresh_db()
    print(f"wrote {FORECASTS} ({len(fc_all):,} rows) and {TRACK}")
    report.write(cfg, fc_all, tr_all, lives)


THREAD_VARS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")


def fit_all_diseases(cfg: dict, workers: int, run=None) -> list:
    """run_one for every disease: in `workers` processes (BLAS/OpenMP capped at 2 threads each,
    so two fits do not exhaust memory), and if a worker dies anyway (BrokenProcessPool, e.g. out
    of memory) the diseases are redone one after another in this process."""
    import os
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool

    run = run or run_one
    diseases = cfg["diseases"]
    if workers > 1:
        for v in THREAD_VARS:  # inherited by the spawned workers
            os.environ.setdefault(v, "2")
        try:
            with ProcessPoolExecutor(min(workers, len(diseases))) as ex:
                return list(ex.map(run, diseases, [cfg] * len(diseases)))
        except BrokenProcessPool as e:
            print(
                f"WARNING: an outlook worker died ({e}); probably out of memory. Rerunning the "
                "diseases one after another (about twice as long).",
                flush=True,
            )
    return [run(d, cfg) for d in diseases]


def main(reuse: bool = False, workers: int = 2) -> None:
    cfg = features.outlook_cfg()
    if reuse and RAW.exists() and CACHE.exists():
        with open(CACHE, "rb") as f:
            lives = pickle.load(f)
        post(cfg, pd.read_parquet(RAW), lives)
        return
    res = fit_all_diseases(cfg, workers)
    raw = pd.concat([fc for fc, _ in res], ignore_index=True)
    raw["area"] = raw["area"].astype(str)
    lives = {d: live for d, (_, live) in zip(cfg["diseases"], res, strict=True)}
    RAW.parent.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(RAW, index=False)
    with open(CACHE, "wb") as f:
        pickle.dump(lives, f)
    post(cfg, raw, lives)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--reuse", action="store_true", help="reuse saved raw forecasts (no refit)")
    ap.add_argument("--workers", type=int, default=2, help="processes (1 = one disease at a time)")
    a = ap.parse_args()
    main(a.reuse, a.workers)
