"""Outlook inputs and features (disease-agnostic).

Origin t = the latest REPORTED week (WER). Target tau = t + h, h = 1..H with H = L + 2 and
L = publication_lag_weeks: the WER reports a week about L weeks after it ends, but rainfall is
observed in near real time, so at the time of use (about t + L) the outlook estimates the weeks
the reports have not covered yet; h = L+1 is "this week" and h = L+2 "next week" then.

Past-only by construction:
* count features use weeks <= t only (forward-filled within the past for missing weeks);
* the elevated threshold uses the 104 weeks BEFORE t (t-104 .. t-1);
* weather is taken relative to the TARGET week at lags >= MIN_WEATHER_LAG (2). For tau <= now + 2
  every such week has already been observed at the time of use. `weather_at` refuses lag < 2.

Data: RDHS x canonical week from 2022-W01, `extraction_valid` rows only, weekly counts as first
printed (`cases`); weather from data/clean/weather.parquet (Open-Meteo, CC BY 4.0).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from radar_lk import CLEAN_DIR, load_config
from radar_lk.radar.series import week_index

MIN_WEATHER_LAG = 2
COUNT_FEATS = ["y0", "y1", "y2", "y3", "m4", "m8", "ly", "neigh", "comp", "thr"]
SEASON_FEATS = ["sin1", "cos1", "sin2", "cos2"]


def outlook_cfg() -> dict:
    cfg = load_config()
    o = dict(cfg["outlook"])
    o["L"] = int(cfg["publication_lag_weeks"])
    o["H"] = o["L"] + 2
    check_lags(o)
    return o


def check_lags(cfg: dict) -> None:
    lags = list(cfg["rain_lags"]) + list(cfg["rain_sum_lags"]) + list(cfg["temp_rh_lags"])
    if min(lags) < MIN_WEATHER_LAG:
        raise ValueError(f"weather lags must be >= {MIN_WEATHER_LAG} weeks before the target")


def weather_feats(cfg: dict) -> list[str]:
    return [f"rain_l{k}" for k in cfg["rain_lags"]] + ["rain4", "temp", "rh"]


def feature_names(cfg: dict) -> list[str]:
    return COUNT_FEATS + SEASON_FEATS + weather_feats(cfg) + ["h"]


@dataclass
class Inputs:
    disease: str
    areas: list[str]
    weeks: pd.DataFrame  # t, week_start, epi_year, epi_week (runs H weeks past the last report)
    Y: np.ndarray  # (A, T) first-printed weekly counts, NaN = no extraction_valid row / future
    C: np.ndarray  # completeness C** at t
    rain: np.ndarray
    temp: np.ndarray
    rh: np.ndarray
    issues: np.ndarray  # (A, T) source issue of each count, '' if none
    last_t: int  # index of the latest reported week
    adjacency: dict = field(default_factory=dict)

    @property
    def A(self) -> int:
        return len(self.areas)


def week_label(weeks: pd.DataFrame, t) -> np.ndarray:
    w = weeks.set_index("t")
    t = np.asarray(t)
    return np.array(
        [f"{w.at[i, 'epi_year']}-W{w.at[i, 'epi_week']:02d}" for i in t.ravel()]
    ).reshape(t.shape)


def load_inputs(disease: str, cfg: dict) -> Inputs:
    from radar_lk.outlook import neighbours

    c = pd.read_parquet(CLEAN_DIR / "wer.parquet")
    c = c[
        (c["area_level"] == "rdhs")
        & c["validated"]
        & (c["epi_year"] >= cfg["first_year"])
        & (c["disease"] == disease)
    ]
    areas = sorted(c["area"].unique())
    last = c[["epi_year", "epi_week"]].drop_duplicates().sort_values(["epi_year", "epi_week"])
    ly, lw = (int(v) for v in last.iloc[-1])
    idx = week_index(cfg["first_year"], ly, lw)
    last_t = int(idx["t"].iloc[-1])
    # extend the grid H weeks past the last report (targets with weather but no counts yet)
    extra = week_index(cfg["first_year"], ly + 1, 52)
    idx = extra[extra["t"] <= last_t + cfg["H"]].reset_index(drop=True)
    key = idx.set_index(["epi_year", "epi_week"])["t"]
    A, T = len(areas), len(idx)
    ai = {a: i for i, a in enumerate(areas)}

    def mat(df, col, dtype=float, fill=np.nan):
        m = np.full((A, T), fill, dtype=dtype)
        k = df.set_index(["epi_year", "epi_week"]).index
        ok = k.isin(key.index)
        d = df[ok]
        tt = key.reindex(k[ok]).to_numpy()
        m[[ai[a] for a in d["area"]], tt] = d[col].to_numpy()
        return m

    w = pd.read_parquet(CLEAN_DIR / "weather.parquet")
    w = w[w["area"].isin(areas)]
    return Inputs(
        disease=disease,
        areas=areas,
        weeks=idx,
        Y=mat(c, "cases"),
        C=mat(c, "completeness_pct"),
        rain=mat(w, "precip_mm"),
        temp=mat(w, "temp_c"),
        rh=mat(w, "rh_pct"),
        issues=mat(c.assign(si=c["source_issue"].astype(str)), "si", object, ""),
        last_t=last_t,
        adjacency=neighbours.load(),
    )


# ------------------------------------------------------------------ building blocks


def ffill(m: np.ndarray) -> np.ndarray:
    """Forward fill along time (past values only)."""
    return pd.DataFrame(m).ffill(axis=1).to_numpy()


def elevated_threshold(Y: np.ndarray, t: int, cfg: dict) -> np.ndarray:
    """Per district: the `elevated_quantile` of its counts in the `elevated_window` weeks BEFORE t
    (t-window .. t-1), floored at `elevated_min_floor`; NaN with fewer than
    `min_train_origin_weeks` observed weeks."""
    lo = max(0, t - cfg["elevated_window"])
    win = Y[:, lo:t]
    n = np.sum(~np.isnan(win), axis=1)
    out = np.full(Y.shape[0], np.nan)
    ok = n >= cfg["min_train_origin_weeks"]
    if ok.any():
        q = np.nanquantile(win[ok], cfg["elevated_quantile"], axis=1)
        out[ok] = np.maximum(q, cfg["elevated_min_floor"])
    return out


def weather_at(W: np.ndarray, tau: int, lags) -> np.ndarray:
    """Columns W[:, tau - lag] for each lag; refuses any lag < MIN_WEATHER_LAG."""
    lags = list(lags)
    if min(lags) < MIN_WEATHER_LAG:
        raise ValueError(f"weather lag {min(lags)} < {MIN_WEATHER_LAG}: not observable in time")
    T = W.shape[1]
    out = np.full((W.shape[0], len(lags)), np.nan)
    for j, k in enumerate(lags):
        s = tau - k
        if 0 <= s < T:
            out[:, j] = W[:, s]
    return out


def _same_weeks_past(tau: int, t: int) -> list[int]:
    """Weeks at the same time of year as tau in earlier years (+-1 week), all <= t."""
    out = []
    k = 1
    while tau - 52 * k + 1 >= 0:
        out += [s for s in (tau - 52 * k - 1, tau - 52 * k, tau - 52 * k + 1) if 0 <= s <= t]
        k += 1
    return out


def build(inp: Inputs, origins, cfg: dict) -> pd.DataFrame:
    """One row per (area, origin t, horizon h): features (past-only), target y at tau = t + h,
    the elevated threshold at t, and the climatology baseline."""
    H = cfg["H"]
    Yf, Cf = ffill(inp.Y), ffill(inp.C)
    A, T = inp.Y.shape
    nb = np.zeros((A, A))
    for i, a in enumerate(inp.areas):
        for b in inp.adjacency.get(a, []):
            if b in inp.areas:
                nb[i, inp.areas.index(b)] = 1.0
    ew = inp.weeks["epi_week"].to_numpy()
    blocks = []
    for t in origins:
        t = int(t)
        if t < 8:
            continue
        thr = elevated_threshold(inp.Y, t, cfg)
        with np.errstate(all="ignore"):
            m4 = np.nanmean(Yf[:, t - 3 : t + 1], axis=1)
            m8 = np.nanmean(Yf[:, t - 7 : t + 1], axis=1)
            yt = Yf[:, t]
            neigh = np.where(
                nb.sum(1) > 0,
                np.nansum(nb * np.where(np.isnan(yt), 0, yt)[None, :], 1)
                / np.maximum(nb @ (~np.isnan(yt)).astype(float), 1),
                np.nan,
            )
        base = {
            "area_i": np.arange(A),
            "t": t,
            "y0": yt,
            "y1": Yf[:, t - 1],
            "y2": Yf[:, t - 2],
            "y3": Yf[:, t - 3],
            "m4": m4,
            "m8": m8,
            "neigh": neigh,
            "comp": Cf[:, t],
            "thr": thr,
        }
        for h in range(1, H + 1):
            tau = t + h
            if tau >= T:
                break
            b = dict(base)
            b["h"] = h
            b["tau"] = tau
            b["ly"] = Yf[:, tau - 52] if tau - 52 >= 0 else np.full(A, np.nan)
            wk = ew[tau]
            for k in (1, 2):
                b[f"sin{k}"] = np.sin(2 * np.pi * k * wk / 52.18)
                b[f"cos{k}"] = np.cos(2 * np.pi * k * wk / 52.18)
            r = weather_at(inp.rain, tau, cfg["rain_lags"])
            for j, k in enumerate(cfg["rain_lags"]):
                b[f"rain_l{k}"] = r[:, j]
            b["rain4"] = weather_at(inp.rain, tau, cfg["rain_sum_lags"]).sum(axis=1)
            with np.errstate(all="ignore"):
                b["temp"] = np.nanmean(weather_at(inp.temp, tau, cfg["temp_rh_lags"]), axis=1)
                b["rh"] = np.nanmean(weather_at(inp.rh, tau, cfg["temp_rh_lags"]), axis=1)
            past = _same_weeks_past(tau, t)
            with np.errstate(all="ignore"):
                if past:
                    v = inp.Y[:, past]
                    cm = np.nanmean(v, axis=1)
                    hit = np.where(np.isnan(v), np.nan, (v >= thr[:, None]).astype(float))
                    cf = np.nanmean(hit, axis=1)
                    cn = np.sum(~np.isnan(hit), axis=1).astype(float)
                else:
                    cm = cf = np.full(A, np.nan)
                    cn = np.zeros(A)
            b["clim_mean"] = np.where(np.isnan(cm), m8, cm)
            b["clim_freq"] = np.where(np.isnan(cf), 1 - cfg["elevated_quantile"], cf)
            b["clim_n"] = cn  # past same-time-of-year weeks behind clim_freq
            y = inp.Y[:, tau] if tau <= inp.last_t else np.full(A, np.nan)
            b["y"] = y
            b["elevated"] = np.where(np.isnan(y) | np.isnan(thr), np.nan, (y >= thr).astype(float))
            blocks.append(pd.DataFrame(b))
    F = pd.concat(blocks, ignore_index=True)
    F["area"] = pd.Categorical(np.asarray(inp.areas)[F["area_i"]], categories=inp.areas)
    return F
