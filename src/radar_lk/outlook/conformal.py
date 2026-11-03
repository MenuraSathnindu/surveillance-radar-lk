"""Uncertainty for the outlook, from past out-of-sample forecasts only.

Counts: rolling split-conformal. For a forecast made at origin o for horizon h, the calibration
pool is every earlier forecast of the same model and horizon whose target is already observed at
o (origin in [o - h - window + 1, o - h]). Score = |y - pred| / sqrt(pred + 1) (larger forecasts
get wider intervals); the interval is pred +- q * sqrt(pred + 1), q = the
ceil((n + 1) * level) / n empirical quantile of the scores, lower end clipped at 0.

Probabilities: inductive Venn-Abers (`venn-abers` package) on the same pool of
(raw probability, observed elevated): a calibrated probability plus the [p0, p1] range. The range
is the Venn-Abers multiprobability, i.e. calibration uncertainty, not a confidence interval for
the outbreak itself.
"""

from __future__ import annotations

import math

import numpy as np


def conformal_q(scores: np.ndarray, level: float) -> float:
    s = np.sort(np.asarray(scores, float))
    n = len(s)
    k = math.ceil((n + 1) * level)
    return float("inf") if k > n else float(s[k - 1])


def _pools(origin: np.ndarray, h: int, window: int):
    """Yield (origin value, test mask, pool mask) for one model x horizon group."""
    for o in np.unique(origin):
        test = origin == o
        pool = (origin >= o - h - window + 1) & (origin <= o - h)
        yield o, test, pool


def rolling_conformal(origin, pred, y, h, levels, window, min_n):
    """Intervals for one model x horizon. Returns {level: (lo, hi)} arrays aligned with pred."""
    origin, pred, y = (np.asarray(v, float) for v in (origin, pred, y))
    score = np.abs(y - pred) / np.sqrt(np.clip(pred, 0, None) + 1)
    out = {lv: (np.full(len(pred), np.nan), np.full(len(pred), np.nan)) for lv in levels}
    for _, test, pool in _pools(origin, h, window):
        s = score[pool & ~np.isnan(score)]
        if len(s) < min_n:
            continue
        w = np.sqrt(np.clip(pred[test], 0, None) + 1)
        for lv in levels:
            q = conformal_q(s, lv)
            out[lv][0][test] = np.maximum(pred[test] - q * w, 0)
            out[lv][1][test] = pred[test] + q * w
    return out


def rolling_venn_abers(origin, p_raw, label, h, window, min_n):
    """(p_cal, p_lo, p_hi) for one model x horizon; NaN where the pool is too small or one-class."""
    from venn_abers import VennAbers

    origin, p_raw, label = (np.asarray(v, float) for v in (origin, p_raw, label))
    n = len(p_raw)
    p_cal, lo, hi = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    for _, test, pool in _pools(origin, h, window):
        ok = pool & ~np.isnan(label) & ~np.isnan(p_raw)
        if ok.sum() < min_n or len(np.unique(label[ok])) < 2:
            continue
        tp = p_raw[test]
        good = ~np.isnan(tp)
        if not good.any():
            continue
        pc = np.clip(p_raw[ok], 1e-6, 1 - 1e-6)
        va = VennAbers()
        va.fit(np.c_[1 - pc, pc], label[ok].astype(int))
        tt = np.clip(tp[good], 1e-6, 1 - 1e-6)
        pp, p01 = va.predict_proba(np.c_[1 - tt, tt])
        idx = np.flatnonzero(test)[good]
        p_cal[idx], lo[idx], hi[idx] = pp[:, 1], p01[:, 0], p01[:, 1]
    return p_cal, lo, hi


def rolling_aci(origin, pred, y, h, levels, window, min_n, gamma):
    """Adaptive conformal inference (Gibbs & Candes 2021) on top of the rolling split-conformal
    pool, for one model x horizon. For each level the working miscoverage a starts at 1 - level
    and is updated online from past-only misses: when the forecasts issued at origin o - h are
    resolved (their target is reported at origin o), a <- a + gamma * sum(1 - level - miss_i)
    over those forecasts (per observation, gamma fixed a priori). The interval at origin o uses
    the ceil((n + 1)(1 - a)) / n quantile of the pool scores, with a clipped so the interval stays
    finite (between the smallest and the largest past score).
    Returns {level: (lo, hi, a_used)}."""
    origin, pred, y = (np.asarray(v, float) for v in (origin, pred, y))
    score = np.abs(y - pred) / np.sqrt(np.clip(pred, 0, None) + 1)
    w_all = np.sqrt(np.clip(pred, 0, None) + 1)
    out = {}
    for lv in levels:
        target = 1 - lv
        a = target
        lo, hi = np.full(len(pred), np.nan), np.full(len(pred), np.nan)
        used = np.full(len(pred), np.nan)
        issued: dict[float, np.ndarray] = {}
        for o, test, pool in _pools(origin, h, window):
            back = issued.pop(o - h, None)
            if back is not None:
                ok = back[~np.isnan(lo[back]) & ~np.isnan(y[back])]
                miss = (y[ok] < lo[ok]) | (y[ok] > hi[ok])
                a += gamma * float(np.sum(target - miss))
            idx = np.flatnonzero(test)
            issued[o] = idx
            used[idx] = a
            s = np.sort(score[pool & ~np.isnan(score)])
            n = len(s)
            if n < min_n:
                continue
            k = min(max(math.ceil((n + 1) * (1 - a)), 1), n)
            q = s[k - 1]
            lo[idx] = np.maximum(pred[idx] - q * w_all[idx], 0)
            hi[idx] = pred[idx] + q * w_all[idx]
        out[lv] = (lo, hi, used)
    return out
