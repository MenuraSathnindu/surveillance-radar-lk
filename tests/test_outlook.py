import numpy as np
import pandas as pd
import pytest

from radar_lk.outlook import backtest as ob
from radar_lk.outlook import conformal, features
from radar_lk.radar.series import week_index


def _cfg(**kw):
    cfg = features.outlook_cfg()
    cfg = {**cfg, "lightgbm": {**cfg["lightgbm"], "n_estimators": 20}, "calib_min": 20, **kw}
    return cfg


def _inputs(cfg, A=4, T=180, seed=0):
    rng = np.random.default_rng(seed)
    weeks = week_index(2022, 2026, 52).iloc[:T].reset_index(drop=True)
    t = np.arange(T)
    rain = rng.gamma(2.0, 30.0, size=(A, T))
    mu = np.exp(1.5 + 0.6 * np.sin(2 * np.pi * t / 52.18))[None, :] * np.ones((A, 1))
    mu[:, 3:] *= np.exp(0.004 * rain[:, :-3])  # risk after rain (3 weeks)
    Y = rng.poisson(mu).astype(float)
    last_t = T - 1 - cfg["H"]
    Y[:, last_t + 1 :] = np.nan
    Y[1, 40] = np.nan  # a missing week
    areas = [f"D{i}" for i in range(A)]
    return features.Inputs(
        disease="toy",
        areas=areas,
        weeks=weeks,
        Y=Y,
        C=np.full((A, T), 95.0),
        rain=rain,
        temp=rng.normal(27, 1, (A, T)),
        rh=rng.normal(80, 5, (A, T)),
        issues=np.full((A, T), "Vol X", dtype=object),
        last_t=last_t,
        adjacency={a: [b for b in areas if b != a][:2] for a in areas},
    )


def test_weather_lag_below_two_is_refused():
    W = np.ones((2, 20))
    with pytest.raises(ValueError):
        features.weather_at(W, 10, [1, 2])
    with pytest.raises(ValueError):
        features.check_lags({"rain_lags": [1, 2], "rain_sum_lags": [2], "temp_rh_lags": [2]})


def test_weather_at_and_just_before_the_target_week_is_never_used():
    cfg = _cfg()
    inp = _inputs(cfg)
    origins = [120]
    F0 = features.build(inp, origins, cfg)
    for tau in range(121, 121 + cfg["H"]):
        for m in (inp.rain, inp.temp, inp.rh):
            m[:, tau - 1 : tau + 1] += 1000.0  # weeks tau-1 and tau
        F1 = features.build(inp, origins, cfg)
        cols = features.weather_feats(cfg)
        a = F0[F0["tau"] == tau][cols].to_numpy()
        b = F1[F1["tau"] == tau][cols].to_numpy()
        np.testing.assert_array_equal(a, b)
        inp = _inputs(cfg)  # reset


def test_elevated_threshold_is_past_only():
    cfg = _cfg()
    inp = _inputs(cfg)
    t = 130
    thr = features.elevated_threshold(inp.Y, t, cfg)
    Y2 = inp.Y.copy()
    Y2[:, t:] = 10_000.0  # week t itself and everything after
    np.testing.assert_array_equal(thr, features.elevated_threshold(Y2, t, cfg))
    win = inp.Y[:, t - cfg["elevated_window"] : t]
    expect = np.maximum(np.nanquantile(win, cfg["elevated_quantile"], axis=1), 1)
    np.testing.assert_allclose(thr, expect)


def test_no_lookahead_future_data_does_not_change_earlier_forecasts():
    cfg = _cfg()
    origins = list(range(110, 136))
    t0 = 122
    inp = _inputs(cfg)
    fc0, _ = ob.run_disease(inp, cfg, origins=origins, keep_live=False)
    inp2 = _inputs(cfg)
    inp2.Y[:, t0 + 1 :] = np.where(np.isnan(inp2.Y[:, t0 + 1 :]), np.nan, 999.0)
    # weather that is not yet observed when origins <= t0 are used (beyond t0 + H - 2)
    inp2.rain[:, t0 + cfg["H"] - 1 :] = 5000.0
    fc1, _ = ob.run_disease(inp2, cfg, origins=origins, keep_live=False)
    cols = ["pred_count", "p_raw", "lo80", "hi80", "lo90", "hi90", "p_elevated", "p_lo", "p_hi"]
    key = ["model", "area_i", "t", "h"]
    a = fc0[fc0["t"] <= t0].sort_values(key).reset_index(drop=True)
    b = fc1[fc1["t"] <= t0].sort_values(key).reset_index(drop=True)
    assert len(a) and len(a) == len(b)
    pd.testing.assert_frame_equal(a[key + cols], b[key + cols])
    # and the perturbation does change later forecasts (the test has teeth)
    later0 = fc0[fc0["t"] > t0 + 1]["pred_count"].to_numpy()
    later1 = fc1[fc1["t"] > t0 + 1]["pred_count"].to_numpy()
    assert not np.allclose(later0, later1)


def test_rolling_conformal_reaches_nominal_coverage():
    rng = np.random.default_rng(3)
    n_orig, per = 300, 30
    origin = np.repeat(np.arange(n_orig), per)
    pred = rng.gamma(2.0, 5.0, origin.size)
    y = np.maximum(pred + rng.normal(0, 1, origin.size) * 1.5 * np.sqrt(pred + 1), 0)
    iv = conformal.rolling_conformal(origin, pred, y, h=2, levels=[0.8, 0.9], window=52, min_n=100)
    ok = origin >= 60
    for lv, (lo, hi) in iv.items():
        cov = np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok]))
        assert abs(cov - lv) < 0.02, (lv, cov)
    assert np.isnan(iv[0.8][0][origin < 2]).all()  # no pool yet -> no interval


def test_conformal_quantile_is_the_finite_sample_one():
    s = np.arange(1, 11, dtype=float)  # n = 10
    assert conformal.conformal_q(s, 0.8) == 9.0  # ceil(11 * 0.8) = 9th smallest
    assert conformal.conformal_q(s, 0.95) == float("inf")  # ceil(11 * 0.95) = 11 > n


def _die_in_worker(d, cfg):
    """Dies abruptly (as when out of memory) in a worker process; works in the parent."""
    import os

    if os.getpid() != int(os.environ["OUTLOOK_TEST_PARENT"]):
        os._exit(9)
    return d, {"ran_in": "parent"}


def test_dead_worker_falls_back_to_one_disease_at_a_time(monkeypatch, capsys):
    import os

    monkeypatch.setenv("OUTLOOK_TEST_PARENT", str(os.getpid()))
    cfg = {"diseases": ["leptospirosis", "dengue"]}
    out = ob.fit_all_diseases(cfg, workers=2, run=_die_in_worker)
    assert out == [("leptospirosis", {"ran_in": "parent"}), ("dengue", {"ran_in": "parent"})]
    assert "an outlook worker died" in capsys.readouterr().out
