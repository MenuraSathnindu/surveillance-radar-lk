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


# ------------------------------------------------------------------ metrics


def _auc(y, p):
    from sklearn.metrics import average_precision_score, roc_auc_score

    if len(np.unique(y)) < 2:
        return np.nan, np.nan
    return float(roc_auc_score(y, p)), float(average_precision_score(y, p))


def metrics(fc: pd.DataFrame, eval_t: int) -> pd.DataFrame:
    """Per model x horizon x scope (all targets / targets in 2026), on the rows every model has."""
    e = fc[(fc["t"] >= eval_t) & fc["y"].notna()].copy()
    key = ["area_i", "t", "h"]
    full = e.pivot_table(index=key, columns="model", values="pred_count").dropna().index
    e = e.set_index(key).loc[lambda d: d.index.isin(full)].reset_index()
    rows = []
    for scope, sel in (("all", e), ("2026", e[e["target_year"] == 2026])):
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
                    ok = g[f"lo{k}"].notna()
                    r[f"coverage{k} %"] = (
                        100
                        * float(
                            (
                                (g.loc[ok, "y"] >= g.loc[ok, f"lo{k}"])
                                & (g.loc[ok, "y"] <= g.loc[ok, f"hi{k}"])
                            ).mean()
                        )
                        if ok.any()
                        else np.nan
                    )
                    r[f"width{k}"] = (
                        float((g.loc[ok, f"hi{k}"] - g.loc[ok, f"lo{k}"]).mean())
                        if ok.any()
                        else np.nan
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


def choose(tr: pd.DataFrame) -> pd.DataFrame:
    """Stop rule, per horizon (all-targets scope): LightGBM where it beats persistence, else the
    best baseline (persistence or climatology)."""
    a = tr[tr["scope"] == "all"]
    rows = []
    for h, g in a.groupby("h"):
        g = g.set_index("model")
        lc = g.at["lightgbm", "MAE"] < g.at["persistence", "MAE"]
        lb = g.at["lightgbm", "Brier"] < g.at["persistence", "Brier"]
        bc = g.loc[["persistence", "climatology"], "MAE"].idxmin()
        bb = g.loc[["persistence", "climatology"], "Brier"].idxmin()
        rows.append(
            {
                "h": int(h),
                "lightgbm beats persistence (count)": bool(lc),
                "lightgbm beats persistence (class)": bool(lb),
                "dashboard count model": "lightgbm" if lc else bc,
                "dashboard class model": "lightgbm" if lb else bb,
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ outputs


def finish(fc: pd.DataFrame, inp: features.Inputs, eval_t: int, choice: pd.DataFrame):
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
    fc["source_issues"] = [iss[(i, t)] for i, t in zip(fc["area_i"], fc["t"], strict=True)]
    fc = fc.rename(
        columns={"thr": "elevated_threshold", "y": "observed", "elevated": "elevated_obs"}
    )
    ch = choice.set_index("h")
    fc["dashboard_count"] = (
        fc["model"].to_numpy() == ch.loc[fc["h"], "dashboard count model"].to_numpy()
    )
    fc["dashboard_class"] = (
        fc["model"].to_numpy() == ch.loc[fc["h"], "dashboard class model"].to_numpy()
    )
    fc["area"] = fc["area"].astype(str)
    return fc


COLS = [
    "area", "disease", "origin_week", "target_week", "h", "model", "pred_count", "lo80", "hi80",
    "lo90", "hi90", "p_elevated", "p_lo", "p_hi", "elevated_threshold", "as_of", "source_issues",
    "kind", "observed", "elevated_obs", "p_raw", "target_year", "target_week_start",
    "dashboard_count", "dashboard_class", "t", "tau",
]  # fmt: skip


def run_one(d: str, cfg: dict):
    """Backtest + live forecast for one disease: (forecast rows, track record, live extras)."""
    inp = features.load_inputs(d, cfg)
    eval_t = t_of(inp.weeks, cfg["eval_from"])
    print(f"{d}: {inp.A} districts, latest reported week t={inp.last_t}; running ...", flush=True)
    fc, live = run_disease(inp, cfg)
    weeks = inp.weeks.set_index("t")
    fc["target_year"] = weeks.loc[fc["tau"], "epi_year"].to_numpy()
    tr = metrics(fc, eval_t)
    choice = choose(tr)
    out = finish(fc, inp, eval_t, choice)
    tr = tr.assign(disease=d).merge(choice, on="h", how="left")
    live = {**live, "areas": inp.areas, "last_t": inp.last_t, "weeks": inp.weeks}
    return out, tr, live


def main(reuse: bool = False) -> None:
    from radar_lk.outlook import report

    cfg = features.outlook_cfg()
    if reuse and FORECASTS.exists() and TRACK.exists() and CACHE.exists():
        fc_all, tr_all = pd.read_parquet(FORECASTS), pd.read_parquet(TRACK)
        with open(CACHE, "rb") as f:
            lives = pickle.load(f)
        report.write(cfg, fc_all, tr_all, lives)
        return
    from concurrent.futures import ProcessPoolExecutor

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ProcessPoolExecutor(len(cfg["diseases"])) as ex:
        res = list(ex.map(run_one, cfg["diseases"], [cfg] * len(cfg["diseases"])))
    fcs, trs, lives = [], [], {}
    for d, (out, tr, live) in zip(cfg["diseases"], res, strict=True):
        out["computed_at"] = now
        fcs.append(out)
        trs.append(tr)
        lives[d] = live
        hl = tr[(tr["scope"] == "all") & tr["h"].isin([1, 2, cfg["L"] + 1, cfg["H"]])]
        cols = ["model", "h", "MASE vs persistence", "BSS vs persistence", "coverage90 %"]
        print(d)
        print(hl[cols].round(3).to_string(index=False))
    fc_all = pd.concat(fcs, ignore_index=True)[COLS + ["computed_at"]]
    tr_all = pd.concat(trs, ignore_index=True)
    fc_all.to_parquet(FORECASTS, index=False)
    tr_all.to_parquet(TRACK, index=False)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(lives, f)
    store.refresh_db()
    print(f"wrote {FORECASTS} ({len(fc_all):,} rows) and {TRACK}")
    report.write(cfg, fc_all, tr_all, lives)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--reuse", action="store_true", help="rebuild the report from saved outputs")
    main(ap.parse_args().reuse)
