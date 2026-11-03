"""Run the radar on every eligible (RDHS, disease) series and write the signals.

    python -m radar_lk.radar.run

Outputs: data/clean/radar_signals.parquet (one row per series x week x method),
data/clean/radar_track_record.parquet, data/cache/radar_nb_fits.pkl (NB fits, reused by the
backtest), DuckDB views refreshed.

Gating: an alert in a week flagged `completeness_low` (C** below the RDHS's own past 10th
percentile) is kept but `suppressed` (held back): it is shown greyed out, never hidden, with the
shared `held_back` label (radar.labels). A `revised` week keeps its alert and carries the marker.

Tiers (series-week, same value on every method's row): `tier` = 'alert' when NB-GLM alerts,
'early_warning' when EARS C2 alerts and NB-GLM does not (only if config
radar_display.tiers_adopted, decided by the backtest), else ''. `held_back` = a tier signal in a
completeness_low week. `tier_label` is the dashboard/brief wording.
"""

from __future__ import annotations

import pickle
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from radar_lk import CLEAN_DIR, DATA_DIR, load_config, store
from radar_lk.radar import labels as lb
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
                    "revision_delta",
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


def add_persistence(s: pd.DataFrame) -> pd.DataFrame:
    """weeks_persisted: consecutive weeks up to and including t whose count was above the method's
    upper bound (or, for EARS C3, which has no bound in count units, that alerted); a missing week
    breaks the run. Past and current weeks only, so it is available in real time.
    sustained = weeks_persisted >= 2."""
    s = s.sort_values(["area", "disease", "method", "t"]).copy()
    above = np.where(s["upper"].notna(), s["observed"] > s["upper"], s["alert"]).astype(bool)
    run = np.zeros(len(s), int)
    key = (s["area"] + "|" + s["disease"] + "|" + s["method"]).to_numpy()
    t = s["t"].to_numpy()
    for i in range(len(s)):
        if above[i]:
            cont = i > 0 and key[i] == key[i - 1] and t[i] == t[i - 1] + 1 and run[i - 1] > 0
            run[i] = run[i - 1] + 1 if cont else 1
    s["weeks_persisted"] = run
    s["sustained"] = run >= 2
    return s


def burden_percentiles(panel: pd.DataFrame, min_past: int = 26) -> pd.DataFrame:
    """burden_pctl: where this week's count ranks among the same district's (and disease's) PAST
    weekly counts since 2022 (mid-rank percentile, 0-100), needs `min_past` past weeks. It
    describes absolute burden for that district, independent of season and of any method."""
    out = []
    for (a, d), g in panel.groupby(["area", "disease"], sort=False):
        y = g["observed"].to_numpy(float)
        pct = np.full(len(y), np.nan)
        past: list[float] = []
        for i, v in enumerate(y):
            if not np.isnan(v):
                if len(past) >= min_past:
                    arr = np.asarray(past)
                    pct[i] = 100 * ((arr < v).mean() + 0.5 * (arr == v).mean())
                past.append(v)
        out.append(
            pd.DataFrame({"area": a, "disease": d, "t": g["t"].to_numpy(), "burden_pctl": pct})
        )
    return pd.concat(out, ignore_index=True)


def _held_back_text(s: pd.DataFrame, template: str) -> pd.Series:
    return s["completeness_pct"].map(lambda v: lb.held_back(v, template))


def burden_label(s: pd.DataFrame, labels: dict | None = None) -> pd.Series:
    """Per-method dashboard wording that separates 'unusual' from 'high but expected'; a held-back
    alert gets the held-back label with that week's completeness."""
    labels = labels or lb.labels()
    lab = np.where(
        s["alert_shown"],
        labels["alert"],
        np.where(s["burden_pctl"] >= 90, labels["high_burden"], ""),
    )
    lab = np.where(s["suppressed"], _held_back_text(s, labels["held_back"]), lab)
    return pd.Series(lab, index=s.index)


def add_tiers(s: pd.DataFrame, adopted: bool, labels: dict | None = None) -> pd.DataFrame:
    """Series-week tier from the raw NB-GLM and EARS C2 alerts (see module docstring)."""
    labels = labels or lb.labels()
    key = ["area", "disease", "t"]
    w = (
        s[s["method"].isin(["nb_glm", "ears_c2"])]
        .pivot_table(index=key, columns="method", values="alert", aggfunc="any")
        .reindex(columns=["nb_glm", "ears_c2"])
        .fillna(False)
        .astype(bool)
    )
    tier = np.where(w["nb_glm"], "alert", np.where(w["ears_c2"] & adopted, "early_warning", ""))
    w = pd.DataFrame({"tier": tier}, index=w.index).reset_index()
    s = s.drop(columns=["tier"], errors="ignore").merge(w, on=key, how="left")
    s["tier"] = s["tier"].fillna("")
    low = s["completeness_low"].fillna(False).astype(bool)
    s["held_back"] = (s["tier"] != "") & low
    lab = np.select(
        [
            s["held_back"],
            s["tier"] == "alert",
            s["tier"] == "early_warning",
            s["burden_pctl"] >= 90,
        ],
        [
            _held_back_text(s, labels["held_back"]),
            labels["alert"],
            labels["early_warning"],
            labels["high_burden"],
        ],
        "",
    )
    s["tier_label"] = lab
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
        sustained_share=("sustained", "mean"),
        first_alert=("week_start", "min"),
        last_alert=("week_start", "max"),
    )
    weeks = s.groupby(["area", "disease", "method"]).size().rename("weeks_evaluated")
    tr = weeks.to_frame().join(tr, how="left").reset_index()
    tr["alerts"] = tr["alerts"].fillna(0).astype(int)
    tr["alerts_per_100_weeks"] = 100 * tr["alerts"] / tr["weeks_evaluated"]
    return tr


def run(workers: int = 4, reuse_fits: bool = False) -> pd.DataFrame:
    cfg = radar_cfg()
    panel, skipped = load_panel(cfg["first_year"], cfg["min_history_weeks"])
    print(
        f"series: {panel.groupby(['area', 'disease']).ngroups}; skipped: {len(skipped)} "
        f"({skipped['disease'].value_counts().to_dict()})"
    )
    cached = None
    if reuse_fits and CACHE.exists():
        with open(CACHE, "rb") as f:
            cached = pickle.load(f)
        keys = set(panel.groupby(["area", "disease"]).groups)
        if cached["cfg"] != cfg or set(cached["fits"]) != keys:
            print("cached NB fits do not match the current data/config; refitting")
            cached = None
    if cached:
        fits = cached["fits"]
        print("reusing cached NB fits")
    else:
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
    s = add_persistence(s)
    s = s.merge(burden_percentiles(panel), on=["area", "disease", "t"], how="left")
    labels = lb.labels()
    s["burden_label"] = burden_label(s, labels)
    s = add_tiers(s, lb.tiers_adopted(), labels)
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
        "weeks_persisted",
        "sustained",
        "burden_pctl",
        "burden_label",
        "tier",
        "held_back",
        "tier_label",
        "revised",
        "revision_delta",
        "completeness_pct",
        "completeness_p10",
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
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--reuse-fits", action="store_true", help="reuse data/cache NB fits if current")
    run(reuse_fits=ap.parse_args().reuse_fits)
