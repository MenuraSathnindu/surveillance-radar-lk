import numpy as np
import pytest

from radar_lk.radar.methods import all_methods, ears, nb_fits, nb_predict, status_quo
from radar_lk.radar.run import radar_cfg
from radar_lk.radar.series import week_index

CFG = radar_cfg()


def _weeks(n):
    idx = week_index(2022, 2030, 1).iloc[:n]
    return idx["epi_year"].to_numpy(), idx["epi_week"].to_numpy()


def _simulate(n=260, base=2.0, amp=0.5, alpha=0.1, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    mu = np.exp(base + amp * np.sin(2 * np.pi * t / 52.18))
    size = 1 / alpha
    y = rng.negative_binomial(size, size / (size + mu)).astype(float)
    return y, mu


# ------------------------------------------------------------------ EARS


def test_ears_c2_c3_on_a_toy_series_match_the_hand_computation():
    base = [4, 6, 4, 6, 4, 6, 4]
    y = np.array(base + [5, 5, 12], float)  # weeks 7, 8 are the 2-week guard band
    out = ears(y, baseline=7, guard=2, c2_threshold=3, c3_threshold=2, sd_floor=1.0, min_count=3)
    mean, sd = np.mean(base), np.std(base, ddof=1)
    expected_c2 = (12 - mean) / sd
    assert out["ears_c2"]["stat"][9] == pytest.approx(expected_c2)
    assert out["ears_c2"]["expected"][9] == pytest.approx(mean)
    assert out["ears_c2"]["alert"][9]
    assert np.isnan(out["ears_c2"]["stat"][:9]).all()  # needs 7 baseline weeks + 2 guard weeks
    # C3 sums the positive parts of C2 - 1 over t, t-1, t-2 (only t has a C2 here)
    assert out["ears_c3"]["stat"][9] == pytest.approx(max(0, expected_c2 - 1))
    assert out["ears_c3"]["alert"][9]


def test_ears_sd_floor_and_min_count():
    zeros = [0.0] * 9
    small = ears(np.array(zeros + [2.0]), sd_floor=1.0, min_count=3)
    big = ears(np.array(zeros + [4.0]), sd_floor=1.0, min_count=3)
    assert small["ears_c2"]["stat"][9] == pytest.approx(2.0) and not small["ears_c2"]["alert"][9]
    assert big["ears_c2"]["stat"][9] == pytest.approx(4.0) and big["ears_c2"]["alert"][9]


def test_status_quo_compares_with_the_same_week_last_year():
    years, weeks = _weeks(60)
    y = np.full(60, 2.0)
    y[52 + 3] = 4.0  # same week as t=3 last year (2.0): 4 >= 2 x 2 and >= 3
    y[52 + 4] = 3.0  # 3 < 2 x 2
    out = status_quo(y, years, weeks, 2.0, 3)
    assert out["alert"][55] and not out["alert"][56]
    assert np.isnan(out["expected"][:52]).all()


# ------------------------------------------------------------------ NB-GLM


def test_nb_glm_recovers_a_known_mean():
    y, mu = _simulate(n=312, seed=3)
    fits = nb_fits(y, CFG)
    out = nb_predict(y, fits, CFG, 0.98, CFG["min_count"])
    t = np.arange(208, 312)  # predictions after 4 years of training
    rel = np.abs(out["expected"][t] - mu[t]) / mu[t]
    assert rel.mean() < 0.15
    # the upper bound sits above the truth almost always and is a real NB quantile
    assert (out["upper"][t] >= mu[t]).mean() > 0.95


def test_nb_glm_downweights_a_past_outbreak():
    y, _ = _simulate(n=200, seed=4)
    spiked = y.copy()
    spiked[120:124] += 80  # a past outbreak inside the training window
    f_clean = nb_fits(y, CFG)
    f_spiked = nb_fits(spiked, CFG)
    r = max(f_clean)
    from radar_lk.radar.methods import design

    X = design(np.arange(200), CFG["nb_fourier_period"], CFG["nb_fourier_k"])
    m_clean = np.exp(X[r - 1] @ f_clean[r][0])
    m_spiked = np.exp(X[r - 1] @ f_spiked[r][0])
    assert m_spiked < 1.5 * m_clean  # without down-weighting the spike would drag the mean up more


def test_large_injected_outbreak_is_detected():
    y, mu = _simulate(n=260, seed=5)
    years, weeks = _weeks(260)
    y2 = y.copy()
    y2[230] += 60  # roughly 8 x the series SD in one week
    res, _ = all_methods(y2, years, weeks, CFG, 0.98)
    assert res["nb_glm"]["alert"][230]
    assert res["ears_c2"]["alert"][230]
    assert res["nb_glm"]["percentile"][230] > 0.99
    res0, _ = all_methods(y, years, weeks, CFG, 0.98)
    assert not res0["nb_glm"]["alert"][230]


def test_no_lookahead_changing_future_weeks_does_not_change_earlier_signals():
    y, _ = _simulate(n=240, seed=6)
    years, weeks = _weeks(240)
    cut = 170
    future = y.copy()
    future[cut + 1 :] = future[cut + 1 :] * 7 + 50  # a wildly different future
    future[cut + 5] = np.nan
    a, _ = all_methods(y, years, weeks, CFG, 0.98)
    b, _ = all_methods(future, years, weeks, CFG, 0.98)
    for method in a:
        for key in ("expected", "upper", "percentile", "stat", "alert"):
            x, z = np.asarray(a[method][key])[: cut + 1], np.asarray(b[method][key])[: cut + 1]
            assert (
                np.array_equal(x, z, equal_nan=True) if x.dtype.kind == "f" else (x == z).all()
            ), (
                method,
                key,
            )
