"""Outbreak-free (null) simulation: the true false-alert rate of every method.

For each modelled series, its fitted NB baseline (the NB-GLM fit at the latest refit point, i.e.
trained on all its data) generates `R` outbreak-free series of 156 weeks placed on the series' own
last 156 calendar weeks (so season and trend are realistic). Weeks 0-103 are history, weeks
104-155 one evaluated year. Every method then runs exactly as on real data (NB-GLM refitted every
4 weeks on all simulated weeks before t, with Farrington-style down-weighting; EARS with its
7-week baseline and 2-week guard; status quo against 52 weeks earlier). Because no outbreak was
injected, every alert is a false alert.

To make 200 x 13 refits per series affordable, the NB-GLM is fitted with a batched NumPy IRLS
(`fit_nb_batch`): the same estimator as `methods.fit_nb` (Poisson start, moment alpha, NB IRLS,
Anscombe-residual down-weighting, refit), checked against it in tests/test_radar.py.

Stored per evaluated week, so thresholds can be swept without refitting:
  nb_u     F(y - 1) under the NB predictive (alert at quantile q  <=>  y > ppf(q)  <=>  u >= q)
  c2, c3   EARS statistics
  ratio    y / (same week last year)   (status quo alerts when y >= factor x last year)
  y        the count (every method also needs y >= min_count)
"""

from __future__ import annotations

import numpy as np
from scipy import special, stats

from radar_lk.radar.methods import design

R_DEFAULT = 200
HIST, EVAL = 104, 52


# ------------------------------------------------------------------ batched NB-GLM


def _irls(Y, X, beta, alpha, vw, iters=30):
    """Batched IRLS for log-link NB2 (alpha=0 -> Poisson). Y (R,n), X (n,p), beta (R,p)."""
    p = X.shape[1]
    eye = np.eye(p) * 1e-8
    for _ in range(iters):
        eta = np.clip(beta @ X.T, -20, 15)
        mu = np.exp(eta)
        w = vw * mu / (1 + alpha[:, None] * mu)
        z = eta + (Y - mu) / mu
        A = np.einsum("rn,np,nq->rpq", w, X, X) + eye
        b = np.einsum("rn,np->rp", w * z, X)
        new = np.linalg.solve(A, b[..., None])[..., 0]
        if np.max(np.abs(new - beta)) < 1e-8:
            beta = new
            break
        beta = new
    return beta


def _alpha_mom(Y, mu, w=None):
    w = np.ones_like(Y) if w is None else w
    a = np.sum(w * ((Y - mu) ** 2 - mu), axis=1) / np.maximum(np.sum(w * mu**2, axis=1), 1e-9)
    return np.clip(a, 1e-4, 10.0)


def _anscombe_nb(Y, mu, alpha):
    a = alpha[:, None]

    def h(x):
        return special.hyp2f1(2 / 3.0, 1 / 3.0, 5 / 3.0, x)

    return (
        1.5
        * (Y ** (2 / 3) * h(-a * Y) - mu ** (2 / 3) * h(-a * mu))
        / (mu * (1 + a * mu)) ** (1 / 6)
    )


def fit_nb_batch(Y, X, reweight_threshold: float = 2.58):
    """Batched methods.fit_nb. Y (R, n) counts, X (n, p). Returns beta (R, p), alpha (R,)."""
    Y = np.asarray(Y, float)
    R, n = Y.shape
    p = X.shape[1]
    beta = np.zeros((R, p))
    beta[:, 0] = np.log(Y.mean(axis=1) + 0.1)
    ones = np.ones_like(Y)
    beta = _irls(Y, X, beta, np.zeros(R), ones)  # Poisson
    mu = np.exp(np.clip(beta @ X.T, -20, 15))
    alpha = _alpha_mom(Y, mu)
    beta = _irls(Y, X, beta, alpha, ones)
    mu = np.exp(np.clip(beta @ X.T, -20, 15))
    r = _anscombe_nb(Y, mu, alpha)
    w = np.where(r > reweight_threshold, 1.0 / np.maximum(r, 1e-9) ** 2, 1.0)
    w = w * n / w.sum(axis=1, keepdims=True)
    alpha = _alpha_mom(Y, mu, w)
    beta = _irls(Y, X, beta, alpha, w)
    # all-zero histories and failed fits: a near-zero / mean-only model, as in fit_nb
    zero = Y.sum(axis=1) == 0
    bad = ~np.all(np.isfinite(beta), axis=1)
    if zero.any():
        beta[zero] = 0.0
        beta[zero, 0] = np.log(1e-3)
        alpha[zero] = 1e-4
    if bad.any():
        beta[bad] = 0.0
        beta[bad, 0] = np.log(np.maximum(Y[bad].mean(axis=1), 1e-3))
    return beta, alpha


# ------------------------------------------------------------------ batched EARS


def ears_batch(Y, baseline=7, guard=2, sd_floor=1.0):
    """EARS C2 and C3 statistics for every row of Y (R, n); NaN where no baseline."""
    R, n = Y.shape
    c2 = np.full((R, n), np.nan)
    for t in range(guard + baseline, n):
        b = Y[:, t - guard - baseline : t - guard]
        m = b.mean(axis=1)
        sd = np.maximum(b.std(axis=1, ddof=1), sd_floor)
        c2[:, t] = (Y[:, t] - m) / sd
    pos = np.where(np.isnan(c2), 0.0, np.maximum(0.0, c2 - 1.0))
    c3 = np.full((R, n), np.nan)
    for t in range(n):
        if not np.isnan(c2[0, t]):
            c3[:, t] = pos[:, max(0, t - 2) : t + 1].sum(axis=1)
    return c2, c3


# ------------------------------------------------------------------ one series


def simulate_series(beta, alpha, t_index, cfg, R=R_DEFAULT, rng=None) -> dict:
    """Null statistics for one series' fitted baseline; arrays of shape (R, EVAL)."""
    rng = np.random.default_rng() if rng is None else rng
    X = design(np.asarray(t_index), cfg["nb_fourier_period"], cfg["nb_fourier_k"])
    mu = np.exp(np.clip(X @ beta, -20, 15))
    size = 1.0 / alpha
    Y = rng.negative_binomial(size, size / (size + mu), size=(R, len(mu))).astype(float)
    every = cfg["nb_refit_every"]
    u = np.full((R, EVAL), np.nan)
    for k in range(0, EVAL, every):
        r = HIST + k
        b, a = fit_nb_batch(Y[:, :r], X[:r], cfg["nb_reweight_threshold"])
        for j in range(k, min(k + every, EVAL)):
            t = HIST + j
            m = np.exp(np.clip(b @ X[t], -20, 15))
            s = 1.0 / a
            u[:, j] = stats.nbinom.cdf(Y[:, t] - 1, s, s / (s + m))
    c2, c3 = ears_batch(Y, cfg["ears_baseline"], cfg["ears_guard"], cfg["ears_sd_floor"])
    prev = Y[:, HIST - 52 : HIST - 52 + EVAL]
    y = Y[:, HIST:]
    return {
        "y": y,
        "nb_u": u,
        "c2": c2[:, HIST:],
        "c3": c3[:, HIST:],
        "prev": prev,
    }


# ------------------------------------------------------------------ thresholds


def alerts(stats_: dict, method: str, threshold: float, min_count: int) -> np.ndarray:
    """Boolean alerts of `method` at `threshold` from stored statistics (any array shape)."""
    y = stats_["y"]
    ok = y >= min_count
    if method == "nb_glm":
        return ok & (stats_["nb_u"] >= threshold)
    if method == "ears_c2":
        return ok & (stats_["c2"] > threshold)
    if method == "ears_c3":
        return ok & (stats_["c3"] > threshold)
    if method == "status_quo":
        return ok & (y >= threshold * stats_["prev"])
    raise ValueError(method)


GRIDS = {
    "nb_glm": [0.8, 0.9, 0.95, 0.975, 0.98, 0.99, 0.995, 0.998, 0.999, 0.9995, 0.9999],
    "ears_c2": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0],
    "ears_c3": [0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 13.0, 20.0, 30.0],
    "status_quo": [1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0, 25.0, 50.0],
}
DEFAULT_THRESHOLD = {"nb_glm": 0.98, "ears_c2": 3.0, "ears_c3": 2.0, "status_quo": 2.0}
