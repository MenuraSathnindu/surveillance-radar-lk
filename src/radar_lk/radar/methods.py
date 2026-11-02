"""Aberration-detection methods on one weekly count series.

Every function works on a single series laid out on a continuous weekly index (missing weeks are
NaN) and, for each week t, uses only weeks before t. That is tested directly
(tests/test_radar.py::test_no_lookahead).

Output of every method: dict of equal-length arrays
    expected, upper, percentile, stat, alert
`alert` already includes the min-count rule; gating (completeness) is applied later.
"""

from __future__ import annotations

import warnings

import numpy as np
import statsmodels.api as sm
from scipy import stats

# ------------------------------------------------------------------ status-quo comparator


def status_quo(y, years, weeks, factor: float = 2.0, min_count: int = 3) -> dict:
    """Alert when this week's count is >= factor x the same week last year and >= min_count.

    'Same week last year' is the same epi week number one year earlier (week 53 compares with 52).
    """
    y = np.asarray(y, float)
    pos = {(int(a), int(b)): i for i, (a, b) in enumerate(zip(years, weeks, strict=True))}
    prev = np.full(len(y), np.nan)
    for i, (a, b) in enumerate(zip(years, weeks, strict=True)):
        j = pos.get((int(a) - 1, min(int(b), 52)))
        if j is not None and j < i:
            prev[i] = y[j]
    upper = factor * prev
    alert = (y >= upper) & (y >= min_count) & ~np.isnan(prev) & ~np.isnan(y)
    return {
        "expected": prev,
        "upper": upper,
        "percentile": np.full(len(y), np.nan),
        "stat": np.where(prev > 0, y / np.where(prev > 0, prev, 1), np.nan),
        "alert": alert,
    }


# ------------------------------------------------------------------ EARS (CDC)


def ears(
    y,
    baseline: int = 7,
    guard: int = 2,
    c2_threshold: float = 3.0,
    c3_threshold: float = 2.0,
    sd_floor: float = 1.0,
    min_count: int = 3,
    min_baseline: int = 5,
) -> dict[str, dict]:
    """EARS C2 and C3 (Hutwagner et al. 2003, as in the R `surveillance` package).

    C2_t = (y_t - mean) / sd over the `baseline` weeks ending `guard` weeks before t
           (weeks t-9 .. t-3 for 7/2); alarm if C2_t > c2_threshold.
    C3_t = sum over i = 0, 1, 2 of max(0, C2_(t-i) - 1); alarm if C3_t > c3_threshold.
    The standard deviation is floored at `sd_floor` because a count baseline of all zeros has
    sd 0. A baseline needs at least `min_baseline` observed weeks.
    """
    y = np.asarray(y, float)
    n = len(y)
    mean = np.full(n, np.nan)
    sd = np.full(n, np.nan)
    for t in range(n):
        lo, hi = t - guard - baseline, t - guard
        if lo < 0:
            continue
        b = y[lo:hi]
        b = b[~np.isnan(b)]
        if len(b) >= min_baseline:
            mean[t] = b.mean()
            sd[t] = max(b.std(ddof=1) if len(b) > 1 else 0.0, sd_floor)
    c2 = (y - mean) / sd
    c3 = np.full(n, np.nan)
    pos = np.where(np.isnan(c2), 0.0, np.maximum(0.0, c2 - 1.0))
    for t in range(n):
        if not np.isnan(c2[t]):
            c3[t] = pos[max(0, t - 2) : t + 1].sum()
    ok = ~np.isnan(y) & (y >= min_count)
    return {
        "ears_c2": {
            "expected": mean,
            "upper": mean + c2_threshold * sd,
            "percentile": stats.norm.cdf(c2),
            "stat": c2,
            "alert": ok & (c2 > c2_threshold),
        },
        "ears_c3": {
            "expected": mean,
            "upper": np.full(n, np.nan),
            "percentile": np.full(n, np.nan),
            "stat": c3,
            "alert": ok & (c3 > c3_threshold),
        },
    }


# ------------------------------------------------------------------ NB-GLM (Farrington-style)


def design(tidx, period: float = 52.18, k: int = 2) -> np.ndarray:
    """log mu = intercept + linear trend + K Fourier pairs (annual)."""
    t = np.asarray(tidx, float)
    cols = [np.ones_like(t), t / 52.0]
    for j in range(1, k + 1):
        cols += [np.sin(2 * np.pi * j * t / period), np.cos(2 * np.pi * j * t / period)]
    return np.column_stack(cols)


def _alpha_mom(y, mu, w=None) -> float:
    """Method-of-moments NB dispersion: Var = mu + alpha mu^2."""
    w = np.ones_like(y) if w is None else w
    a = float(np.sum(w * ((y - mu) ** 2 - mu)) / max(np.sum(w * mu**2), 1e-9))
    return float(np.clip(a, 1e-4, 10.0))


def fit_nb(y, X, reweight_threshold: float = 2.58) -> tuple[np.ndarray, float]:
    """Fit the NB-GLM on past weeks; returns (beta, alpha).

    Poisson fit -> moment estimate of alpha -> NB fit -> past weeks whose Anscombe residual
    exceeds `reweight_threshold` get weight r^-2 (renormalised to sum n, Farrington 1996 /
    Noufaily 2013) -> alpha and the NB fit are re-estimated with those weights.
    """
    y = np.asarray(y, float)
    p = X.shape[1]
    if y.sum() == 0:  # nothing ever reported: a near-zero mean
        beta = np.zeros(p)
        beta[0] = np.log(1e-3)
        return beta, 1e-4
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            pois = sm.GLM(y, X, family=sm.families.Poisson()).fit()
            alpha = _alpha_mom(y, pois.fittedvalues)
            nb = sm.GLM(y, X, family=sm.families.NegativeBinomial(alpha=alpha)).fit(
                start_params=pois.params
            )
            r = np.asarray(nb.resid_anscombe)
            w = np.where(r > reweight_threshold, 1.0 / np.maximum(r, 1e-9) ** 2, 1.0)
            w = w * len(w) / w.sum()
            alpha = _alpha_mom(y, nb.fittedvalues, w)
            nbw = sm.GLM(y, X, family=sm.families.NegativeBinomial(alpha=alpha), var_weights=w).fit(
                start_params=nb.params
            )
            beta = np.asarray(nbw.params)
            if not np.all(np.isfinite(beta)):
                raise ValueError("non-finite fit")
            return beta, alpha
        except Exception:  # noqa: BLE001 - fall back to a seasonal-free mean model
            beta = np.zeros(p)
            beta[0] = np.log(max(y.mean(), 1e-3))
            return beta, _alpha_mom(y, np.full_like(y, max(y.mean(), 1e-3)))


def refit_points(y, min_train: int = 52, every: int = 4) -> list[int]:
    """Weeks at which the NB-GLM is (re)fitted: once `min_train` past weeks are observed, then
    every `every` weeks. A fit at r uses weeks < r and serves weeks r .. r+every-1."""
    obs = np.cumsum(~np.isnan(np.asarray(y, float)))
    first = next((r for r in range(1, len(y) + 1) if obs[r - 1] >= min_train), None)
    return [] if first is None else list(range(first, len(y), every))


def nb_fits(y, cfg: dict, points: list[int] | None = None, base: dict | None = None) -> dict:
    """{refit point r: (beta, alpha)} fitted on the observed weeks before r.

    `points` restricts which refits to compute (others are copied from `base`): the backtest uses
    this to refit only where injected weeks enter the training window."""
    y = np.asarray(y, float)
    t = np.arange(len(y))
    X = design(t, cfg["nb_fourier_period"], cfg["nb_fourier_k"])
    schedule = refit_points(y, cfg["nb_min_train_weeks"], cfg["nb_refit_every"])
    out = dict(base or {})
    for r in schedule if points is None else [p for p in points if p in schedule]:
        m = ~np.isnan(y[:r])
        out[r] = fit_nb(y[:r][m], X[:r][m], cfg["nb_reweight_threshold"])
    return out


def nb_predict(y, fits: dict, cfg: dict, quantile: float, min_count: int = 3, weeks=None) -> dict:
    """Expected count, upper bound (NB `quantile`), predictive percentile and alert per week."""
    y = np.asarray(y, float)
    n = len(y)
    X = design(np.arange(n), cfg["nb_fourier_period"], cfg["nb_fourier_k"])
    out = {k: np.full(n, np.nan) for k in ("expected", "upper", "percentile", "stat")}
    out["alert"] = np.zeros(n, bool)
    if not fits:
        return out
    pts = sorted(fits)
    every = cfg["nb_refit_every"]
    idx = range(pts[0], n) if weeks is None else [t for t in weeks if t >= pts[0]]
    for t in idx:
        r = pts[0] + every * ((t - pts[0]) // every)
        if r not in fits:
            r = max(p for p in pts if p <= t)
        beta, alpha = fits[r]
        mu = float(np.exp(np.clip(X[t] @ beta, -20, 15)))
        size = 1.0 / alpha
        prob = size / (size + mu)
        out["expected"][t] = mu
        out["upper"][t] = stats.nbinom.ppf(quantile, size, prob)
        if not np.isnan(y[t]):
            out["percentile"][t] = stats.nbinom.cdf(y[t], size, prob)
            out["stat"][t] = (y[t] - mu) / np.sqrt(mu + alpha * mu**2)
            out["alert"][t] = (y[t] > out["upper"][t]) and (y[t] >= min_count)
    return out


def all_methods(y, years, weeks, cfg: dict, quantile: float, fits: dict | None = None) -> dict:
    """Run every method on one series; returns {method: arrays} and the NB fits used."""
    mc = cfg["min_count"]
    res = {"status_quo": status_quo(y, years, weeks, cfg["status_quo_factor"], mc)}
    res.update(
        ears(
            y,
            cfg["ears_baseline"],
            cfg["ears_guard"],
            cfg["ears_c2_threshold"],
            cfg["ears_c3_threshold"],
            cfg["ears_sd_floor"],
            mc,
        )
    )
    fits = nb_fits(y, cfg) if fits is None else fits
    res["nb_glm"] = nb_predict(y, fits, cfg, quantile, mc)
    return res, fits
