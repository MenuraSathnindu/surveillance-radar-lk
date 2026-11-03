"""Outlook models. Each returns, for the test rows, a count forecast and a raw P(elevated).

* persistence   count y_t; class 1{y_t >= threshold}
* climatology   the district's past mean (and elevated frequency) for tau's week of year (+-1)
* glm           NB GLM (log link; Poisson fit, moment alpha, NB refit) for counts; L2 logistic
                regression for the class. Same design, standardised on the training rows.
* lightgbm      LGBMRegressor(objective=poisson) and LGBMClassifier, small fixed settings

Hyperparameters are fixed in config (outlook.lightgbm, outlook.logistic_c); nothing is tuned.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from radar_lk.outlook.features import SEASON_FEATS, feature_names, weather_feats

MODELS = ["persistence", "climatology", "glm", "lightgbm"]
LOG_FEATS = ["y0", "y1", "y2", "y3", "m4", "m8", "ly", "neigh", "thr"]


def _glm_design(df: pd.DataFrame, cfg: dict, areas, ref: dict | None = None):
    """Design matrix for the GLM/logistic; `ref` holds the training means/sds and fill values."""
    X = pd.DataFrame(index=df.index)
    for c in LOG_FEATS:
        X[f"log_{c}"] = np.log1p(df[c].clip(lower=0))
    X["comp"] = df["comp"] / 100.0
    for c in SEASON_FEATS:
        X[c] = df[c]
    for c in weather_feats(cfg):
        X[c] = df[c]
    H = cfg["H"]
    X["log_y0_x_h"] = X["log_y0"] * df["h"] / H
    X["log_m4_x_h"] = X["log_m4"] * df["h"] / H
    for h in range(2, H + 1):
        X[f"h{h}"] = (df["h"] == h).astype(float)
    for a in areas[1:]:
        X[f"a_{a}"] = (df["area"] == a).astype(float).to_numpy()
    cont = [
        c
        for c in X.columns
        if not (c.startswith("h") and c[1:].isdigit()) and not c.startswith("a_")
    ]
    if ref is None:
        fill = X[cont].median()
        Z = X[cont].fillna(fill)
        mu, sd = Z.mean(), Z.std().replace(0, 1).fillna(1)
        ref = {"fill": fill, "mu": mu, "sd": sd}
    X[cont] = (X[cont].fillna(ref["fill"]) - ref["mu"]) / ref["sd"]
    return X.fillna(0.0), ref


def _nb_glm(Xtr, ytr, Xte):
    import statsmodels.api as sm

    Xtr1, Xte1 = sm.add_constant(Xtr, has_constant="add"), sm.add_constant(Xte, has_constant="add")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pois = sm.GLM(ytr, Xtr1, family=sm.families.Poisson()).fit(maxiter=100)
        mu = pois.predict(Xtr1)
        alpha = float(np.sum((ytr - mu) ** 2 - mu) / max(np.sum(mu**2), 1e-9))
        alpha = min(max(alpha, 1e-3), 10.0)
        try:
            nb = sm.GLM(ytr, Xtr1, family=sm.families.NegativeBinomial(alpha=alpha)).fit(
                maxiter=100
            )
            pred = nb.predict(Xte1)
        except Exception:  # noqa: BLE001 - fall back to the Poisson fit
            pred = pois.predict(Xte1)
    cap = 10 * max(float(np.max(ytr)), 1.0)
    return np.clip(np.asarray(pred, float), 0, cap)


def _logistic(Xtr, ytr, Xte, c):
    from sklearn.linear_model import LogisticRegression

    if len(np.unique(ytr)) < 2:
        return np.full(len(Xte), float(np.mean(ytr)))
    m = LogisticRegression(C=c, max_iter=3000)
    m.fit(Xtr.to_numpy(), ytr)
    return m.predict_proba(Xte.to_numpy())[:, 1]


def lgbm_frame(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    X = df[feature_names(cfg)].astype(float).copy()
    X["area"] = df["area"]
    return X


def fit_lightgbm(train: pd.DataFrame, cfg: dict):
    import lightgbm as lgb

    p = dict(cfg["lightgbm"])
    Xtr = lgbm_frame(train, cfg)
    reg = lgb.LGBMRegressor(objective="poisson", **p).fit(Xtr, train["y"].to_numpy())
    cls = None
    yb = train["elevated"].to_numpy()
    if len(np.unique(yb)) == 2:
        cls = lgb.LGBMClassifier(objective="binary", **p).fit(Xtr, yb.astype(int))
    return reg, cls


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, cfg: dict, areas) -> dict:
    """{model: (pred_count, p_raw)} for the test rows; plus '_lgbm' -> fitted LightGBM models."""
    out = {}
    out["persistence"] = (
        test["y0"].to_numpy(float),
        (test["y0"] >= test["thr"]).astype(float).to_numpy(),
    )
    out["climatology"] = (test["clim_mean"].to_numpy(float), test["clim_freq"].to_numpy(float))
    Xtr, ref = _glm_design(train, cfg, areas)
    Xte, _ = _glm_design(test, cfg, areas, ref)
    ytr = train["y"].to_numpy(float)
    out["glm"] = (
        _nb_glm(Xtr, ytr, Xte),
        _logistic(Xtr, train["elevated"].to_numpy(int), Xte, cfg["logistic_c"]),
    )
    reg, cls = fit_lightgbm(train, cfg)
    Xl = lgbm_frame(test, cfg)
    pc = np.clip(reg.predict(Xl), 0, None)
    pp = cls.predict_proba(Xl)[:, 1] if cls is not None else np.full(len(test), np.nan)
    out["lightgbm"] = (pc, pp)
    out["_lgbm"] = (reg, cls)
    return out
