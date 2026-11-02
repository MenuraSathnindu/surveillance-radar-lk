"""WER Table 1 parser: golden cells, week edge cases, validation rules.

Golden values were read off the rendered PDF pages (150 dpi, rotated upright), not off the
parser's own output. Fixtures live in tests/fixtures (real WER issues, original PDFs).
"""

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pdfplumber
import pytest

from radar_lk import load_config
from radar_lk.harmonise.epiweek import block_from_range
from radar_lk.ingest import wer_pipeline
from radar_lk.ingest.parse_wer import (
    DECOY,
    TITLE,
    ParseError,
    check_week,
    find_table_page,
    parse_issue,
    parse_week,
    upright_text,
)
from radar_lk.ingest.validate import NATIONAL, cross_week_gap, within_issue_split

FIX = Path(__file__).parent / "fixtures"
CAL = load_config()["wer_calendar"]

# (area, disease, field, value). field: cases = weekly A, cum = cumulative B,
# C = completeness C**, T = timeliness T*
GOLDEN = {
    "wer_2022_vol49_no26.pdf": dict(
        issue="Vol 49 No 26",
        week=(2022, 25),
        start=date(2022, 6, 18),
        n_diseases=12,
        cells=[
            ("Colombo", "dengue", "cases", 58),
            ("Colombo", "dengue", "cum", 5291),
            ("Jaffna", "typhus", "cases", 3),
            ("Jaffna", "typhus", "cum", 399),
            ("Kalmunai", "chickenpox", "cases", 1),
            ("Kalmunai", "chickenpox", "cum", 31),
            ("Colombo", "dengue", "T", 14),
            ("Colombo", "dengue", "C", 97),
            # the printed national weekly dengue is 20 although the districts add to 809
            (NATIONAL, "dengue", "cases", 20),
            (NATIONAL, "dengue", "cum", 26602),
            (NATIONAL, "leptospirosis", "cum", 2513),
            (NATIONAL, "dengue", "T", 17),
            (NATIONAL, "dengue", "C", 94),
        ],
    ),
    "wer_2024_vol51_no26.pdf": dict(
        issue="Vol 51 No 26",
        week=(2024, 25),
        start=date(2024, 6, 15),
        n_diseases=13,
        cells=[
            ("Colombo", "dengue", "cases", 218),
            ("Colombo", "dengue", "cum", 5592),
            ("Colombo", "tuberculosis", "cases", 26),
            ("Colombo", "tuberculosis", "cum", 1036),
            ("Kandy", "tuberculosis", "cum", 323),  # cells touch the T*/C** cells in this row
            ("Kalmunai", "dengue", "cases", 5),
            ("Kalmunai", "dysentery", "cum", 15),
            ("Colombo", "dengue", "T", 95),
            ("Colombo", "dengue", "C", 100),
            ("Galle", "dengue", "T", 0),
            (NATIONAL, "dengue", "cases", 683),
            (NATIONAL, "dengue", "cum", 30037),
            (NATIONAL, "leptospirosis", "cum", 5833),
            (NATIONAL, "tuberculosis", "cases", 166),
            (NATIONAL, "dengue", "T", 90),
            (NATIONAL, "dengue", "C", 99),
        ],
    ),
    "wer_2026_vol53_no26.pdf": dict(
        issue="Vol 53 No 26",
        week=(2026, 25),
        start=date(2026, 6, 15),
        n_diseases=14,
        cells=[
            ("Colombo", "dengue", "cases", 1138),
            ("Colombo", "dengue", "cum", 9357),
            ("Colombo", "leprosy", "cases", 3),
            ("Colombo", "leprosy", "cum", 83),
            ("Kalmunai", "leprosy", "cum", 23),
            ("Kalmunai", "dengue", "cum", 640),
            ("Gampaha", "dengue", "C", 86),
            ("Gampaha", "dengue", "T", 73),
            (NATIONAL, "dengue", "cases", 5828),
            (NATIONAL, "dengue", "cum", 45879),
            (NATIONAL, "leptospirosis", "cases", 171),
            (NATIONAL, "tuberculosis", "cum", 3944),
            (NATIONAL, "leprosy", "cum", 584),
            (NATIONAL, "dengue", "T", 90),
            (NATIONAL, "dengue", "C", 99),
        ],
    ),
}
FIELD = {"cases": "cases", "cum": "cum_cases", "C": "completeness_pct", "T": "timeliness_pct"}


def _cell(res, area, disease, field):
    rows = [r for r in res.rows if r["area"] == area and r["disease"] == disease]
    assert len(rows) == 1, (area, disease)
    return rows[0][FIELD[field]]


@pytest.mark.parametrize("name", list(GOLDEN))
def test_golden_cells(name):
    g = GOLDEN[name]
    res = parse_issue(FIX / name)
    assert res.status == "ok", res.reason
    assert res.source_issue == g["issue"]
    assert (res.meta["epi_year"], res.meta["epi_week"]) == g["week"]
    assert res.meta["start"] == g["start"]
    assert res.meta["n_diseases"] == g["n_diseases"]
    assert len(res.rows) == 27 * g["n_diseases"]  # 26 RDHS + national
    for area, disease, field, value in g["cells"]:
        assert _cell(res, area, disease, field) == value, (area, disease, field)


def test_2022_national_total_is_a_source_error():
    res = parse_issue(FIX / "wer_2022_vol49_no26.pdf")
    dengue = [r for r in res.rows if r["disease"] == "dengue" and r["area"] != NATIONAL]
    assert sum(r["cases"] for r in dengue) == 809  # printed national says 20


# ------------------------------------------------------------------ finding Table 1


def test_finds_table_by_content_and_rejects_water_quality_decoy():
    with pdfplumber.open(FIX / "wer_2026_vol53_no26.pdf") as pdf:
        page2 = upright_text(pdf.pages[1])
        assert DECOY.search(page2) and not TITLE.search(page2)  # "Table 1 : Water Quality ..."
        idx, title, _ = find_table_page(pdf)
    assert idx == 2 and "Distribution of Notified Diseases" in title.group("name")


def test_issue_without_table_is_no_table():
    res = parse_issue(FIX / "wer_no_table_readmore.pdf")
    assert res.status == "no_table" and not res.rows


def test_unknown_header_text_is_a_hard_failure():
    cfg = load_config()
    cfg["diseases"][0]["aliases"] = ["Something Else"]  # dengue header no longer known
    res = parse_issue(FIX / "wer_2026_vol53_no26.pdf", cfg)
    assert res.status == "failed" and res.meta["error_code"] == "header_unknown" and not res.rows


def test_unmapped_district_is_a_hard_failure():
    cfg = load_config()
    cfg["rdhs_units"] = [u for u in cfg["rdhs_units"] if u != "Kandy"]
    res = parse_issue(FIX / "wer_2026_vol53_no26.pdf", cfg)
    assert res.status == "failed" and res.meta["error_code"] == "district_unmapped"


# ------------------------------------------------------------------ weeks


def test_new_year_crossing_week_real_pdf():
    # Table 1 of Vol 52 No 2: "28th Dec - 03rd Jan 2025 (1st Week)"
    # = Sat 28 Dec 2024 - Fri 3 Jan 2025
    res = parse_issue(FIX / "wer_vol52_no02_newyear_2024_25.pdf")
    assert res.status == "ok", res.reason
    assert res.meta["start"] == date(2024, 12, 28) and res.meta["end"] == date(2025, 1, 3)
    assert (res.meta["epi_year"], res.meta["epi_week"]) == (2025, 1)  # Thursday 2 Jan 2025
    assert res.rows[0]["printed_week"] == 1  # the WER agrees


def test_last_saturday_friday_week_then_first_monday_sunday_week():
    last = parse_issue(FIX / "wer_vol53_no01_last_saturday_week.pdf")
    assert last.status == "ok", last.reason
    assert last.meta["start"] == date(2025, 12, 20) and last.meta["start"].weekday() == 5
    assert (last.meta["epi_year"], last.meta["epi_week"]) == (2025, 52)


def test_first_monday_sunday_week_has_a_misprinted_year_and_needs_an_override():
    path = FIX / "wer_vol53_no02_first_monday_week.pdf"
    # printed "29th - 04th Jan 2025": a 2025 end date makes a Sunday-start block, so it must fail
    res = parse_issue(path)
    assert res.status == "failed" and res.meta["error_code"] == "week_weekday"
    # with an explicit, user-approved override the real week is Mon 29 Dec 2025 - Sun 4 Jan 2026
    cfg = load_config()
    cfg["wer_calendar"]["week_overrides"] = {path.as_posix(): {"start": date(2025, 12, 29)}}
    fixed = parse_issue(path, cfg)
    assert fixed.status == "ok", fixed.reason
    assert fixed.meta["start"].weekday() == 0 and fixed.meta["end"] == date(2026, 1, 4)
    assert (fixed.meta["epi_year"], fixed.meta["epi_week"]) == (2026, 1)  # Thursday 1 Jan 2026
    assert fixed.rows[0]["printed_week"] == 1  # corroborates the override


def test_53_week_year_real_pdf():
    # 2020 has 53 ISO weeks. Table 1 of Vol 48 No 2 covers Sat 26 Dec 2020 - Fri 1 Jan 2021 and the
    # WER prints it as "(1st Week)" of 2021, whereas the Thursday rule (31 Dec 2020) gives 2020-W53.
    path = FIX / "wer_vol48_no02_2020_w53.pdf"
    with pdfplumber.open(path) as pdf:
        _, title, _ = find_table_page(pdf)
    start, end = parse_week(title["week"])
    assert (start, end) == (date(2020, 12, 26), date(2021, 1, 1))
    assert block_from_range(start, end) == (2020, 53)
    assert int(title["wk"]) == 1
    # the disagreement is detected, not silently filed: the issue fails instead of mis-resetting
    # cumulative counts
    res = parse_issue(path)
    assert res.status == "failed" and res.meta["error_code"] == "week_number_mismatch"


def test_2026_has_53_iso_weeks():
    assert block_from_range(date(2026, 12, 28), date(2027, 1, 3)) == (2026, 53)


@pytest.mark.parametrize(
    "text, start, end",
    [
        ("18th– 24th Jun 2022 ", date(2022, 6, 18), date(2022, 6, 24)),
        ("28th– 03rd Sep 2021 ", date(2021, 8, 28), date(2021, 9, 3)),  # start month omitted
        ("28th Dec – 03rd Jan 2025 ", date(2024, 12, 28), date(2025, 1, 3)),
        ("27th July– 02nd Aug 2026 ", date(2026, 7, 27), date(2026, 8, 2)),
    ],
)
def test_parse_week(text, start, end):
    assert parse_week(text) == (start, end)


@pytest.mark.parametrize("text", ["26th – 02nd Aug 2026 ", "30th– 06th Sep 2023 ", "garbage"])
def test_inconsistent_week_text_fails(text):
    with pytest.raises(ParseError):
        parse_week(text)


def test_check_week_rules():
    check_week(date(2024, 6, 15), date(2024, 6, 21), 25, CAL)  # Sat start, number agrees
    check_week(date(2026, 6, 15), date(2026, 6, 21), 25, CAL)  # Mon start after the switch
    check_week(date(2021, 8, 28), date(2021, 9, 3), 36, CAL)  # WER's 2021 numbering is ISO + 1
    with pytest.raises(ParseError, match="week_weekday"):  # "01st - 07th May" for 1-7 June 2024
        check_week(date(2024, 5, 1), date(2024, 5, 7), 23, CAL)
    with pytest.raises(ParseError, match="week_weekday"):  # a Monday block before the switch
        check_week(date(2024, 6, 17), date(2024, 6, 23), 25, CAL)
    with pytest.raises(ParseError, match="week_number_mismatch"):  # stale dates, new number
        check_week(date(2024, 8, 17), date(2024, 8, 23), 35, CAL)


# ------------------------------------------------------------------ validation

# Real 2022-W25 dengue (Vol 49 No 26): the 26 RDHS rows in table order, read off the rendered page.
W25_WEEKLY = [
    58,
    17,
    14,
    21,
    61,
    10,
    15,
    53,
    82,
    67,
    4,
    4,
    0,
    4,
    29,
    8,
    20,
    86,
    34,
    13,
    9,
    51,
    23,
    84,
    11,
    31,
]
W25_CUM = [
    5291,
    3312,
    1859,
    1660,
    422,
    104,
    1832,
    566,
    717,
    2080,
    83,
    163,
    53,
    39,
    857,
    96,
    927,
    1442,
    1126,
    205,
    67,
    575,
    218,
    1277,
    1061,
    570,
]


def _frame(rows):
    cols = ["epi_year", "epi_week", "area", "disease", "cases", "cum_cases"]
    df = pd.DataFrame(rows, columns=cols)
    df["area_level"] = np.where(df["area"] == NATIONAL, "national", "rdhs")
    df["completeness_pct"], df["timeliness_pct"] = 100.0, 50.0
    df["source_file"], df["validated"] = "f.pdf", False
    return df


def _group(year, week, weekly, cum, nat_weekly=None, nat_cum=None, disease="dengue"):
    rows = [
        (year, week, f"D{i:02d}", disease, w, c)
        for i, (w, c) in enumerate(zip(weekly, cum, strict=True))
    ]
    rows.append(
        (
            year,
            week,
            NATIONAL,
            disease,
            sum(weekly) if nat_weekly is None else nat_weekly,
            sum(cum) if nat_cum is None else nat_cum,
        )
    )
    return rows


def test_real_2022_w25_dengue_numbers():
    assert sum(W25_WEEKLY) == 809 and sum(W25_CUM) == 26602  # as read off the page
    # the real fixture agrees with the hand-copied numbers
    res = parse_issue(FIX / "wer_2022_vol49_no26.pdf")
    dengue = [r for r in res.rows if r["disease"] == "dengue" and r["area"] != NATIONAL]
    assert [r["cases"] for r in dengue] == W25_WEEKLY
    assert [r["cum_cases"] for r in dengue] == W25_CUM
    # districts' cumulatives add to the national cumulative; the printed weekly (20) does not
    df = _frame(_group(2022, 25, W25_WEEKLY, W25_CUM, nat_weekly=20, nat_cum=26602))
    kept, review, errors = within_issue_split(df)
    assert len(errors) == 1
    e = errors.iloc[0]
    assert (e["printed_national_cases"], e["district_sum_cases"]) == (20, 809)
    assert len(kept) == 26 and kept["validated"].all()
    assert set(kept["note"]) == {"national_weekly_source_error"}
    assert list(review["area"]) == [NATIONAL]
    assert list(review["fail_reason"]) == ["national_weekly_source_error"]


def test_neither_column_adding_up_sends_the_whole_group_to_review():
    df = _frame(_group(2022, 25, W25_WEEKLY, W25_CUM, nat_weekly=20, nat_cum=26602 + 1))
    kept, review, errors = within_issue_split(df)
    assert kept.empty and errors.empty and len(review) == 27
    assert set(review["fail_reason"]) == {"cum_sum_mismatch"}


def test_national_cumulative_source_error_keeps_districts():
    # weekly counts add up (809 = 809) but the printed national cumulative is off: e.g. TB 2024,
    # where the districts exceed the national cumulative by exactly 66 every week
    df = _frame(_group(2024, 30, W25_WEEKLY, W25_CUM, nat_cum=26602 - 66))
    kept, review, errors = within_issue_split(df)
    assert len(kept) == 26 and kept["validated"].all()
    assert set(kept["note"]) == {"national_cumulative_source_error"}
    assert list(review["area"]) == [NATIONAL]
    assert list(review["fail_reason"]) == ["national_cumulative_source_error"]
    assert list(errors["kind"]) == ["national_cumulative_source_error"]
    assert (errors["district_sum_cum"] - errors["printed_national_cum"]).tolist() == [66]


def test_weeks_before_2022_are_dropped():
    df = _frame(_group(2021, 52, [1, 2], [10, 20]) + _group(2022, 1, [1, 2], [1, 2]))
    df["source_issue"] = np.where(df["epi_year"] == 2021, "Vol 49 No 1", "Vol 49 No 2")
    kept, dropped = wer_pipeline.drop_pre_baseline(df)
    assert set(kept["epi_year"]) == {2022}
    assert dropped == [("Vol 49 No 1", "2021-W52")]


def _row_chars(label, nums, label_x0, nums_x0):
    """Synthetic rotated line: label chars then number tokens, at given cross-line positions."""
    chars, pos = [], 40.0
    for ch in label:
        chars.append({"text": ch, "x0": label_x0, "_s": pos, "_e": pos + 4})
        pos += 4
    for k, n in enumerate(nums):
        pos = 100.0 + 20 * k
        for ch in str(n):
            chars.append({"text": ch, "x0": nums_x0, "_s": pos, "_e": pos + 4})
            pos += 4
    return chars


def _layout(n_cols):
    from radar_lk.ingest.parse_wer import Layout

    return Layout(["dengue"], ["Dengue"], [102.0 + 20 * k for k in range(n_cols)])


def test_label_on_a_different_text_line_than_its_numbers_fails():
    from radar_lk.ingest.parse_wer import read_rows

    units = {"colombo": "Colombo", "gampaha": "Gampaha"}
    good = [_row_chars("Colombo", [5, 50, 90, 99], 100.0, 100.4)]
    bad = good + [_row_chars("Gampaha", [6, 60, 91, 98], 117.0, 134.0)]  # label one row off
    nat = _row_chars("SRILANKA", [11, 110, 90, 99], 151.0, 151.0)
    assert read_rows([[]] + good + [nat], 0, _layout(4), units)[0][0] == "Colombo"
    with pytest.raises(ParseError, match="row_misaligned"):
        read_rows([[]] + bad + [nat], 0, _layout(4), units)


def test_label_without_numbers_fails():
    from radar_lk.ingest.parse_wer import read_rows

    units = {"colombo": "Colombo"}
    lonely = [[c for c in _row_chars("Colombo", [], 100.0, 100.0)]]
    with pytest.raises(ParseError, match="row_misaligned"):
        read_rows([[]] + lonely, 0, _layout(4), units)


def test_consistent_group_is_kept_untouched():
    kept, review, errors = within_issue_split(_frame(_group(2022, 25, W25_WEEKLY, W25_CUM)))
    assert len(kept) == 27 and review.empty and errors.empty
    assert set(kept["note"]) == {""}


def test_cross_week_gap_and_revised_flag_keep_the_row():
    wk1 = _group(2024, 10, [5, 3], [100, 50])
    wk2 = _group(2024, 11, [4, 2], [110, 52])  # D00: 100 + 4 = 104 but printed 110: revised by +6
    df = _frame(wk1 + wk2)
    gap = cross_week_gap(df)
    d00 = df[(df["area"] == "D00") & (df["epi_week"] == 11)].index[0]
    d01 = df[(df["area"] == "D01") & (df["epi_week"] == 11)].index[0]
    assert gap[d00] == 6 and gap[d01] == 0
    assert gap[df[df["epi_week"] == 10].index].isna().all()  # no previous week: unknown, not failed
    clean, review, errors, _, _ = wer_pipeline.validate_wer(df)
    assert review.empty and len(clean) == len(df)  # a revised row is NOT dropped
    row = clean[(clean["area"] == "D00") & (clean["epi_week"] == 11)].iloc[0]
    assert bool(row["revised"]) is True and row["revision_delta"] == 6
    assert row["cases"] == 4  # the weekly count stays as printed in that issue
    ok = clean[(clean["area"] == "D01") & (clean["epi_week"] == 11)].iloc[0]
    assert bool(ok["revised"]) is False and ok["revision_delta"] == 0
    assert clean[clean["epi_week"] == 10]["revised"].isna().all()


def test_first_week_of_year_expects_cum_equal_weekly():
    df = _frame(_group(2025, 1, [7, 1], [7, 3]))
    gap = cross_week_gap(df)
    assert gap[df[df["area"] == "D00"].index[0]] == 0
    assert gap[df[df["area"] == "D01"].index[0]] == 2


def test_missing_cell_group_goes_to_review_and_is_not_inferred():
    df = _frame(_group(2022, 25, [5, 3], [50, 30]))
    df.loc[df["area"] == "D01", "cases"] = None
    ok, review = wer_pipeline.split_missing_cells(df)
    assert ok.empty and len(review) == 3
    assert list(review.loc[review["area"] == "D01", "fail_reason"]) == ["missing_cell"]
    assert set(review.loc[review["area"] != "D01", "fail_reason"]) == {"group_has_missing_cell"}


def test_percentages_outside_0_100_become_nan_and_are_counted_not_rejected():
    df = _frame(_group(2022, 25, [5, 3], [50, 30]))
    df.loc[df["area"] == "D01", "completeness_pct"] = 200.0  # cf. Kalutara C** = 200, Vol 52 No 23
    df.loc[df["area"] == "D00", "timeliness_pct"] = -1.0
    clean, review, _, counts, _ = wer_pipeline.validate_wer(df)
    assert review.empty and len(clean) == 3  # the counts are fine, so the rows stay
    assert clean.loc[clean["area"] == "D01", "completeness_pct"].isna().all()
    assert clean.loc[clean["area"] == "D00", "timeliness_pct"].isna().all()
    assert counts["completeness_pct"]["rdhs_area_weeks"] == 1
    assert counts["completeness_pct"]["values"] == [200.0]
    assert counts["timeliness_pct"]["area_weeks"] == 1


def _completeness_series(values, area="D00"):
    rows = [(2022 + i // 52, i % 52 + 1, area, "dengue", 1, 1) for i in range(len(values))]
    df = _frame(rows)
    df["completeness_pct"] = values
    return df


def test_completeness_low_uses_only_past_weeks_and_own_percentile():
    values = [100.0] * 30 + [80.0, 100.0, 100.0]
    df = wer_pipeline.add_completeness_low(_completeness_series(values))
    df = df.sort_values(["epi_year", "epi_week"])
    low = df["completeness_low"].tolist()
    assert all(pd.isna(v) for v in low[:26])  # fewer than 26 past weeks: no threshold yet
    assert low[26:30] == [False] * 4  # 100 is not below its own past p10 (100)
    assert low[30] == True  # noqa: E712  (80 < 100; the 80 is not in its own history)
    assert low[31] == False  # noqa: E712
    assert df["completeness_p10"].iloc[30] == 100.0


def test_completeness_low_is_relative_to_each_rdhs():
    a = _completeness_series([90.0] * 31, "A")
    b = _completeness_series([100.0] * 30 + [90.0], "B")
    df = wer_pipeline.add_completeness_low(pd.concat([a, b], ignore_index=True))
    last = df[(df["epi_year"] == 2022) & (df["epi_week"] == 31)]
    assert last.set_index("area")["completeness_low"].to_dict() == {"A": False, "B": True}


def test_duplicate_week_keeps_the_issue_that_adds_up():
    good = _frame(_group(2022, 25, [5, 3], [50, 30], nat_weekly=8))
    bad = good.copy()
    bad.loc[bad["area"] == NATIONAL, "cases"] = 2
    good["source_file"], bad["source_file"] = "a_good.pdf", "b_bad.pdf"
    kept, log = wer_pipeline.choose_duplicates(pd.concat([good, bad], ignore_index=True))
    assert set(kept["source_file"]) == {"a_good.pdf"}
    assert log[0]["kept"] == "a_good.pdf" and log[0]["dropped"] == ["b_bad.pdf"]


def test_week_overrides_in_config_are_settled_and_still_checked():
    cal = load_config()["wer_calendar"]
    ov = cal["week_overrides"]
    assert len(ov) == 6 and all(len(o["reason"]) > 80 for o in ov.values())
    assert not any("Vol_51_no_36" in f for f in ov)  # the unsettled one stays out
    for o in ov.values():  # every override must itself pass the weekday check
        expected = 0 if o["start"] >= cal["monday_weeks_from"] else 5
        assert o["start"].weekday() == expected


def test_weekly_column_copied_from_previous_week_is_flagged():
    from radar_lk.ingest.validate import stale_weekly_groups

    wk1 = list(range(5, 31))  # 26 non-zero districts
    cum1 = [10 * w for w in wk1]
    df = _frame(
        _group(2026, 25, wk1, cum1)
        + _group(2026, 26, wk1, [c + w for c, w in zip(cum1, wk1, strict=True)])
    )
    s = stale_weekly_groups(df)
    assert list(zip(s["epi_week"], s["disease"], s["scope"], strict=True)) == [
        (26, "dengue", "whole issue")
    ]
    clean, review, _, _, stale = wer_pipeline.validate_wer(df)
    assert set(review.loc[review["epi_week"] == 26, "fail_reason"]) == {"stale_weekly_copy"}
    assert (clean["epi_week"] == 25).all() and len(stale) == 1


def test_ordinary_week_to_week_change_is_not_flagged():
    from radar_lk.ingest.validate import stale_weekly_groups

    wk1 = list(range(5, 31))
    wk2 = [w + (i % 3) - 1 for i, w in enumerate(wk1)]  # about a third repeat, as in real data
    cum1 = [10 * w for w in wk1]
    df = _frame(
        _group(2026, 25, wk1, cum1)
        + _group(2026, 26, wk2, [c + w for c, w in zip(cum1, wk2, strict=True)])
    )
    assert stale_weekly_groups(df).empty


def _weeks_of(vectors, start_week=10):
    rows = []
    cum = [0] * len(vectors[0])
    for k, v in enumerate(vectors):
        cum = [c + x for c, x in zip(cum, v, strict=True)]
        rows += _group(2026, start_week + k, v, cum)
    return _frame(rows)


def test_weekly_column_printed_against_the_wrong_rows_is_flagged():
    from radar_lk.ingest.validate import scrambled_weekly_groups

    base = [
        300,
        180,
        110,
        50,
        17,
        6,
        89,
        35,
        112,
        22,
        3,
        2,
        4,
        5,
        51,
        9,
        20,
        31,
        15,
        13,
        8,
        13,
        10,
        91,
        44,
        20,
    ]
    noisy = [b + (i % 3) for i, b in enumerate(base)]
    scrambled = base[13:] + base[:13]  # same values, wrong rows: sums still add up
    df = _weeks_of([base, noisy, scrambled])
    s = scrambled_weekly_groups(df)
    assert list(zip(s["epi_week"], s["disease"], strict=True)) == [(12, "dengue")]
    assert s["rho"].iloc[0] < 0.3
    clean, review, _, _, flagged = wer_pipeline.validate_wer(df)
    assert set(review.loc[review["epi_week"] == 12, "fail_reason"]) == {"scrambled_weekly_column"}
    assert set(clean["epi_week"]) == {10, 11}


def test_ordinary_rise_does_not_look_scrambled():
    from radar_lk.ingest.validate import scrambled_weekly_groups

    base = [
        300,
        180,
        110,
        50,
        17,
        6,
        89,
        35,
        112,
        22,
        3,
        2,
        4,
        5,
        51,
        9,
        20,
        31,
        15,
        13,
        8,
        13,
        10,
        91,
        44,
        20,
    ]
    noisy = [b + (i % 3) for i, b in enumerate(base)]
    outbreak = [b * 3 if i in (4, 5, 6) else b for i, b in enumerate(base)]  # a real local rise
    assert scrambled_weekly_groups(_weeks_of([base, noisy, outbreak])).empty
