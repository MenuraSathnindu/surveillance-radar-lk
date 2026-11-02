"""Run the radar on every eligible (RDHS, disease) series and write the signals.

    python -m radar_lk.radar.run

Outputs: data/clean/radar_signals.parquet (one row per series x week x method),
data/clean/radar_track_record.parquet, data/cache/radar_nb_fits.pkl (NB fits, reused by the
backtest), DuckDB views refreshed.

Gating: an alert in a week flagged `completeness_low` (C** below the RDHS's own past 10th
percentile) is kept but `suppressed`, with the reason. A `revised` week keeps its alert and
carries the marker.
"""

from __future__ import annotations

import pickle
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from radar_lk import CLEAN_DIR, DATA_DIR, load_config, store
from radar_lk.radar.methods import all_methods, nb_fits, nb_predict
from radar_lk.radar.series import load_panel

METHODS = ["status_quo", "ears_c2", "ears_c3", "nb_glm"]
CACHE = DATA_DIR / "cache" / "radar_nb_fits.pkl"
QUANTILE_STEPS = [0.98, 0.99, 0.995, 0.999]


def radar_cfg() -> dict:
    cfg = load_config()
    r = dict(cfg["radar"])
    r["quantile"] = cfg["thresholds"]["radar_alert_quantile"]
    r["max_alert_rate"] = cfg["thresholds"]["max_alert_rate"]
    return r


def _fit_one(args):
    key, y, cfg = args
    return key, nb_fits(np.asarray(y, float), cfg)


def fit_all(panel: pd.DataFrame, cfg: dict, workers: int = 4) -> dict:
    jobs = [
        ((a, d), g["observed"].to_numpy(), cfg)
        for (a, d), g in panel.groupby(["area", "disease"], sort=True)
    ]
    with ProcessPoolExecutor(workers) as ex:
        return dict(ex.map(_fit_one, jobs, chunksize=8))


def signals(panel: pd.DataFrame, fits: dict, cfg: dict, quantile: float) -> pd.DataFrame:
    frames = []
    for (a, d), g in panel.groupby(["area", "disease"], sort=True):
        y = g["observed"].to_numpy()
        res, _ = all_methods(
            y, g["epi_year"].to_numpy(), g["epi_week"].to_numpy(), cfg, quantile, fits[(a, d)]
        )
        for m in METHODS:
            r = res[m]
            f = g[
                [
                    "area",
                    "disease",
                    "t",
                    "epi_year",
                    "epi_week",
                    "week_start",
                    "observed",
                    "completeness_low",
                    "completeness_pct",
                    "completeness_p10",
                    "revised",
                    "source_file",
                    "source_issue",
                ]
            ].copy()
            f["method"] = m
            for k in ("expected", "upper", "percentile", "stat"):
                f[k] = r[k]
            f["alert"] = r["alert"]
            frames.append(f[~np.isnan(f["expected"].to_numpy(float)) & f["observed"].notna()])
    s = pd.concat(frames, ignore_index=True)
    low = s["completeness_low"].fillna(False).astype(bool)
    s["suppressed"] = s["alert"] & low
    s["suppress_reason"] = np.where(
        s["suppressed"],
        "reporting completeness C**="
        + s["completeness_pct"].round(0).astype("Int64").astype(str)
        + "% is below this RDHS's own past 10th percentile ("
        + s["completeness_p10"].round(0).astype("Int64").astype(str)
        + "%)",
        "",
    )
    s["revised"] = s["revised"].astype("boolean")
    s["alert_shown"] = s["alert"] & ~s["suppressed"]
    return s


def alert_rate(s: pd.DataFrame, method: str = "nb_glm") -> float:
    m = s[s["method"] == method]
    return float(m["alert_shown"].mean()) if len(m) else 0.0


def track_record(s: pd.DataFrame) -> pd.DataFrame:
    """Per series and method: shown alerts, and how often the next week was also high
    (observed above that next week's upper bound, or the method alerting again)."""
    s = s.sort_values(["area", "disease", "method", "t"]).copy()
    g = s.groupby(["area", "disease", "method"])
    nxt_t = g["t"].shift(-1)
    s["next_high"] = (nxt_t == s["t"] + 1) & (
        g["alert"].shift(-1).fillna(False).astype(bool)
        | (g["observed"].shift(-1) > g["upper"].shift(-1)).fillna(False)
    )
    a = s[s["alert_shown"]]
    tr = a.groupby(["area", "disease", "method"]).agg(
        alerts=("t", "size"),
        followed_by_second_high_week=("next_high", "mean"),
        first_alert=("week_start", "min"),
        last_alert=("week_start", "max"),
    )
    weeks = s.groupby(["area", "disease", "method"]).size().rename("weeks_evaluated")
    tr = weeks.to_frame().join(tr, how="left").reset_index()
    tr["alerts"] = tr["alerts"].fillna(0).astype(int)
    tr["alerts_per_100_weeks"] = 100 * tr["alerts"] / tr["weeks_evaluated"]
    return tr


def run(workers: int = 4) -> pd.DataFrame:
    cfg = radar_cfg()
    panel, skipped = load_panel(cfg["first_year"], cfg["min_history_weeks"])
    print(
        f"series: {panel.groupby(['area', 'disease']).ngroups}; skipped: {len(skipped)} "
        f"({skipped['disease'].value_counts().to_dict()})"
    )
    fits = fit_all(panel, cfg, workers)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump({"fits": fits, "cfg": cfg}, f)
    # stop rule: NB-GLM must not flag more than max_alert_rate of district-weeks
    q = cfg["quantile"]
    steps = [x for x in QUANTILE_STEPS if x >= q]
    for q in steps:
        s = signals(panel, fits, cfg, q)
        rate = alert_rate(s)
        print(f"NB-GLM quantile {q}: alert rate {100 * rate:.2f}% of district-weeks")
        if rate <= cfg["max_alert_rate"]:
            break
    s["quantile_used"] = q
    as_of = panel.dropna(subset=["week_end"])["week_end"].max()
    s["as_of"] = as_of
    s["computed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cols = [
        "area",
        "disease",
        "epi_year",
        "epi_week",
        "week_start",
        "observed",
        "expected",
        "upper",
        "percentile",
        "stat",
        "method",
        "alert",
        "suppressed",
        "suppress_reason",
        "alert_shown",
        "revised",
        "completeness_pct",
        "completeness_low",
        "source_file",
        "source_issue",
        "as_of",
        "computed_at",
        "quantile_used",
        "t",
    ]
    s = s[cols].sort_values(["area", "disease", "method", "t"]).reset_index(drop=True)
    s.to_parquet(CLEAN_DIR / "radar_signals.parquet", index=False)
    tr = track_record(s)
    tr.to_parquet(CLEAN_DIR / "radar_track_record.parquet", index=False)
    skipped.to_parquet(CLEAN_DIR / "radar_skipped_series.parquet", index=False)
    store.refresh_db()
    print(f"wrote {len(s):,} signal rows, as of {as_of}; track record {len(tr)} rows")
    print(s.groupby("method")["alert_shown"].mean().mul(100).round(2).to_string())
    return s


def recompute_nb(y, fits, cfg, quantile, weeks=None):
    """Helper for the backtest: NB predictions from given fits."""
    return nb_predict(y, fits, cfg, quantile, cfg["min_count"], weeks)


if __name__ == "__main__":
    run()
