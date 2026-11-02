from datetime import date, timedelta

import pandas as pd

from radar_lk.ingest.weather import load_points, weekly


def _daily(start: date, n: int, rain=1.0, temp=27.0, rh=80.0):
    days = [start + timedelta(days=i) for i in range(n)]
    return pd.DataFrame(
        {
            "date": [d.isoformat() for d in days],
            "precipitation_sum": rain,
            "temperature_2m_mean": temp,
            "relative_humidity_2m_mean": rh,
        }
    )


def test_26_points_one_per_rdhs():
    pts = load_points()
    assert len(pts) == 26 and pts["rdhs"].is_unique
    assert pts["lat"].between(5.5, 10).all() and pts["lon"].between(79, 82.5).all()


def test_weekly_aggregates_monday_to_sunday_and_drops_partial_weeks():
    # Wed 3 Jun 2026 .. Sun 14 Jun 2026: first week partial, second week (8-14 Jun) complete
    w = weekly(_daily(date(2026, 6, 3), 12))
    assert len(w) == 1
    r = w.iloc[0]
    assert r["week_start"] == date(2026, 6, 8) and r["week_end"] == date(2026, 6, 14)
    assert (r["epi_year"], r["epi_week"]) == (2026, 24)
    assert (
        r["precip_mm"] == 7.0 and r["temp_c"] == 27.0 and r["rh_pct"] == 80.0 and r["n_days"] == 7
    )


def test_week_with_a_missing_day_is_dropped():
    d = _daily(date(2026, 6, 8), 7)
    d.loc[3, "precipitation_sum"] = None
    assert weekly(d).empty


def test_53_week_year_uses_the_thursday_rule():
    # Mon 28 Dec 2020 - Sun 3 Jan 2021 holds Thursday 31 Dec 2020: ISO 2020-W53
    w = weekly(_daily(date(2020, 12, 28), 7))
    assert (w.iloc[0]["epi_year"], w.iloc[0]["epi_week"]) == (2020, 53)
    w = weekly(_daily(date(2021, 1, 4), 7))
    assert (w.iloc[0]["epi_year"], w.iloc[0]["epi_week"]) == (2021, 1)
