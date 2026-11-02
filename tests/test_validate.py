import pandas as pd

from radar_lk.ingest.validate import NATIONAL, cumulative_check, sum_check, validate


def make(rows):
    cols = ["epi_year", "epi_week", "area", "disease", "cases", "cum_cases"]
    return pd.DataFrame(rows, columns=cols)


GOOD = make(
    [
        (2026, 1, "Colombo", "dengue", 10, 10),
        (2026, 1, "Gampaha", "dengue", 5, 5),
        (2026, 1, NATIONAL, "dengue", 15, 15),
        (2026, 2, "Colombo", "dengue", 7, 17),
        (2026, 2, "Gampaha", "dengue", 3, 8),
        (2026, 2, NATIONAL, "dengue", 10, 25),
    ]
)


def test_sum_check_passes():
    assert sum_check(GOOD)["sum_ok"].all()


def test_sum_check_catches_mismatch():
    bad = GOOD.copy()
    bad.loc[bad["area"] == "Gampaha", "cases"] += 1
    assert not sum_check(bad)["sum_ok"].any()


def test_cumulative_check_catches_jump():
    bad = GOOD.copy()
    bad.loc[(bad["area"] == "Colombo") & (bad["epi_week"] == 2), "cum_cases"] = 99
    d = cumulative_check(bad)
    row = d[(d["area"] == "Colombo") & (d["epi_week"] == 2)]
    assert not bool(row["cum_ok"].iloc[0])


def test_validate_splits_rows():
    bad = GOOD.copy()
    bad.loc[(bad["area"] == "Colombo") & (bad["epi_week"] == 2), "cum_cases"] = 99
    passed, failed = validate(bad)
    assert len(failed) == 1 and "cumulative_mismatch" in failed["fail_reason"].iloc[0]
    assert len(passed) == len(GOOD) - 1


def test_gap_week_is_unknown_not_failed():
    gap = GOOD[GOOD["epi_week"] == 2]
    d = cumulative_check(gap)
    assert d["cum_ok"].isna().all()
