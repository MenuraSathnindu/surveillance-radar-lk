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


# ------------------------------------------------------------------ null simulation


def test_batched_nb_fit_matches_the_reference_fit():
    from radar_lk.radar.methods import design, fit_nb
    from radar_lk.radar.nullsim import fit_nb_batch

    rng = np.random.default_rng(10)
    t = np.arange(104)
    X = design(t, 52.18, 2)
    mu = np.exp(2 + 0.6 * np.sin(2 * np.pi * t / 52.18))
    Y = rng.negative_binomial(5, 5 / (5 + mu), size=(20, 104)).astype(float)
    Y[3, 40:44] += 80  # an outbreak in the history, so the down-weighting step matters
    B, A = fit_nb_batch(Y, X)
    for i in range(20):
        b, a = fit_nb(Y[i], X)
        assert np.allclose(b, B[i], atol=1e-4) and a == pytest.approx(A[i], abs=1e-4)


def test_batched_ears_matches_the_reference():
    from radar_lk.radar.nullsim import ears_batch

    y, _ = _simulate(n=80, seed=11)
    c2, c3 = ears_batch(y[None, :])
    ref = ears(y, min_count=0)
    assert np.allclose(c2[0], ref["ears_c2"]["stat"], equal_nan=True)
    assert np.allclose(c3[0], ref["ears_c3"]["stat"], equal_nan=True)


def test_null_false_alert_rate_of_nb_glm_is_near_nominal():
    from radar_lk.radar.methods import design, fit_nb
    from radar_lk.radar.nullsim import alerts, simulate_series

    y, _ = _simulate(n=200, base=2.5, seed=12)  # mean ~12, so min_count rarely binds
    beta, alpha = fit_nb(y, design(np.arange(200), 52.18, 2))
    st = simulate_series(beta, alpha, np.arange(44, 200), CFG, R=200, rng=np.random.default_rng(1))
    assert st["y"].shape == (200, 52) and not np.isnan(st["nb_u"]).any()
    rate = alerts(st, "nb_glm", 0.98, 0).mean()
    assert 0.01 < rate < 0.06  # nominal 2%, plus estimation error of 104-week fits
    # thresholds are monotone: a stricter threshold never gives more alerts
    rates = [alerts(st, "nb_glm", q, 3).mean() for q in (0.9, 0.98, 0.999)]
    assert rates[0] >= rates[1] >= rates[2]
    c2 = [alerts(st, "ears_c2", th, 3).mean() for th in (2, 3, 5)]
    assert c2[0] >= c2[1] >= c2[2]


def test_threshold_equivalence_for_the_nb_bound():
    # y > ppf(q)  <=>  F(y - 1) >= q, which is what lets the sweep avoid refitting
    from scipy import stats

    size, prob = 3.0, 3.0 / (3.0 + 7.0)
    for q in (0.9, 0.98, 0.995):
        ub = stats.nbinom.ppf(q, size, prob)
        for y in range(0, 40):
            assert (y > ub) == (stats.nbinom.cdf(y - 1, size, prob) >= q)


# ------------------------------------------------------------------ persistence and burden


def test_weeks_persisted_counts_consecutive_weeks_above_the_bound():
    import pandas as pd

    from radar_lk.radar.run import add_persistence

    obs = [1, 9, 9, 9, 1, 9, 9]
    t = [0, 1, 2, 3, 4, 5, 7]  # week 6 missing: the run restarts at t=7
    s = pd.DataFrame(
        {
            "area": "A",
            "disease": "d",
            "method": "nb_glm",
            "t": t,
            "observed": obs,
            "upper": 5.0,
            "alert": [o > 5 for o in obs],
        }
    )
    out = add_persistence(s)
    assert out["weeks_persisted"].tolist() == [0, 1, 2, 3, 0, 1, 1]
    assert out["sustained"].tolist() == [False, False, True, True, False, False, False]


def test_burden_percentile_uses_past_weeks_only():
    import pandas as pd

    from radar_lk.radar.run import burden_percentiles

    vals = list(range(1, 31)) + [100.0, 0.0]
    panel = pd.DataFrame({"area": "A", "disease": "d", "t": range(32), "observed": vals})
    b = burden_percentiles(panel, min_past=26).set_index("t")["burden_pctl"]
    assert b.iloc[:26].isna().all()
    assert b[30] == 100.0  # 100 is above all 30 past weeks
    assert b[31] == 0.0  # 0 is below all 31 past weeks (the 100 does not change that)
    assert b[26] == pytest.approx(100 * 26 / 26)  # 27 > the 26 past values 1..26


# ------------------------------------------------------------------ tiers and labels

LABELS = {
    "alert": "A",
    "early_warning": "EW",
    "high_burden": "HB",
    "held_back": "Possible rise, held back: reporting completeness low ({completeness_pct:.0f}%). "
    "Late reports usually add cases, so the true rise may be larger.",
}


def test_tier_alerts_split_nb_and_c2_into_disjoint_tiers():
    from radar_lk.radar.nullsim import tier_alerts

    st = {
        "y": np.array([10.0, 10, 10, 10, 1]),
        "nb_u": np.array([0.99, 0.99, 0.5, 0.5, 0.999]),
        "c2": np.array([5.0, 0.0, 5.0, 0.0, 5.0]),
        "c3": np.zeros(5),
        "prev": np.ones(5),
    }
    t = tier_alerts(st, min_count=3)
    assert t["tier_alert"].tolist() == [True, True, False, False, False]  # last: below min_count
    assert t["tier_early_warning"].tolist() == [False, False, True, False, False]
    assert (t["tier_union"] == (t["tier_alert"] | t["tier_early_warning"])).all()
    assert not (t["tier_alert"] & t["tier_early_warning"]).any()


def test_detect_tiers_reports_the_tier_of_the_first_signal():
    import pandas as pd

    from radar_lk.radar.evaluation import detect_tiers

    inj = pd.DataFrame(
        {
            "k": [2, 2, 3],
            "start_year": 2025,
            "y": [[10.0, 10.0], [10.0, 10.0], [10.0, 10.0]],
            "nb_u": [[0.5, 0.99], [0.99, 0.5], [0.5, 0.5]],
            "c2": [[5.0, 0.0], [5.0, 5.0], [0.0, 0.0]],
            "c3": [[0.0, 0.0]] * 3,
            "prev": [[1.0, 1.0]] * 3,
        }
    )
    d = detect_tiers(inj, 3)
    assert d["first_tier"].tolist() == ["early_warning", "alert", ""]  # NB wins a same-week tie
    assert d["tier_union"].tolist() == [True, True, False]
    assert d["union_delay"].iloc[0] == 0 and np.isnan(d["union_delay"].iloc[2])


def test_add_tiers_and_held_back_label():
    import pandas as pd

    from radar_lk.radar.run import add_tiers

    rows = []
    # t=0: NB alert; t=1: C2 only; t=2: C2 only, low completeness; t=3: nothing, high burden
    for t, nb, c2, low, pct, bp in [
        (0, True, True, False, 90.0, 50),
        (1, False, True, False, 90.0, 50),
        (2, False, True, True, 41.6, 50),
        (3, False, False, False, 90.0, 95),
    ]:
        for m, a in (("nb_glm", nb), ("ears_c2", c2), ("status_quo", True)):
            rows.append(
                {
                    "area": "A",
                    "disease": "d",
                    "t": t,
                    "method": m,
                    "alert": a,
                    "completeness_low": low,
                    "completeness_pct": pct,
                    "burden_pctl": bp,
                }
            )
    s = pd.DataFrame(rows)
    on = add_tiers(s, adopted=True, labels=LABELS).drop_duplicates("t").set_index("t")
    assert on["tier"].tolist() == ["alert", "early_warning", "early_warning", ""]
    assert on["held_back"].tolist() == [False, False, True, False]
    assert on.loc[2, "tier_label"] == (
        "Possible rise, held back: reporting completeness low (42%). "
        "Late reports usually add cases, so the true rise may be larger."
    )
    assert on.loc[3, "tier_label"] == "HB"
    off = add_tiers(s, adopted=False, labels=LABELS).drop_duplicates("t").set_index("t")
    assert off["tier"].tolist() == ["alert", "", "", ""]  # NB-GLM only when not adopted
    # the status-quo alert never creates a tier
    assert len(add_tiers(s, adopted=True, labels=LABELS)) == len(s)


def test_held_back_label_comes_from_config_and_tier_decision_is_written(tmp_path, monkeypatch):
    from radar_lk.radar import labels as lb

    text = lb.labels()["held_back"]
    assert "{completeness_pct" in text and "never" not in text
    assert lb.held_back(55.4).startswith(
        "Possible rise, held back: reporting completeness low (55%)."
    )
    cfg = tmp_path / "sources.yaml"
    cfg.write_text("radar_display:\n  tiers_adopted: null\n  labels: {}\n", encoding="utf-8")
    monkeypatch.setattr(lb, "CONFIG_PATH", cfg)
    lb.write_tiers_adopted(True, "union 4.1/100")
    assert "  tiers_adopted: true   # union 4.1/100" in cfg.read_text(encoding="utf-8")
