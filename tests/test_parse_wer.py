"""WER Table 1 parser: golden cells, week edge cases, validation rules.

Golden values were read off the rendered PDF pages (150 dpi, rotated upright), not off the
parser's own output. Fixtures live in tests/fixtures (real WER issues, original PDFs).
"""

from datetime import date
from pathlib import Path

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
from radar_lk.ingest.validate import NATIONAL, reclassify_source_total_errors, validate

FIX = Path(__file__).parent / "fixtures"
CAL = load_config()["wer_calendar"]

# (area, disease, field, value). field: cases = weekly A, cum = cumulative B,
# C = completeness C**, T = timeliness T*
GOLDEN = {
    "wer_2022_vol49_no26.pdf": dict(
        issue="Vol 49 No 26", week=(2022, 25), start=date(2022, 6, 18), n_diseases=12,
        cells=[
            ("Colombo", "dengue", "cases", 58), ("Colombo", "dengue", "cum", 5291),
            ("Jaffna", "typhus", "cases", 3), ("Jaffna", "typhus", "cum", 399),
            ("Kalmunai", "chickenpox", "cases", 1), ("Kalmunai", "chickenpox", "cum", 31),
            ("Colombo", "dengue", "T", 14), ("Colombo", "dengue", "C", 97),
            # the printed national weekly dengue is 20 although the districts add to 809
            (NATIONAL, "dengue", "cases", 20), (NATIONAL, "dengue", "cum", 26602),
            (NATIONAL, "leptospirosis", "cum", 2513),
            (NATIONAL, "dengue", "T", 17), (NATIONAL, "dengue", "C", 94),
        ],
    ),
    "wer_2024_vol51_no26.pdf": dict(
        issue="Vol 51 No 26", week=(2024, 25), start=date(2024, 6, 15), n_diseases=13,
        cells=[
            ("Colombo", "dengue", "cases", 218), ("Colombo", "dengue", "cum", 5592),
            ("Colombo", "tuberculosis", "cases", 26), ("Colombo", "tuberculosis", "cum", 1036),
            ("Kandy", "tuberculosis", "cum", 323),  # cells touch the T*/C** cells in this row
            ("Kalmunai", "dengue", "cases", 5), ("Kalmunai", "dysentery", "cum", 15),
            ("Colombo", "dengue", "T", 95), ("Colombo", "dengue", "C", 100),
            ("Galle", "dengue", "T", 0),
            (NATIONAL, "dengue", "cases", 683), (NATIONAL, "dengue", "cum", 30037),
            (NATIONAL, "leptospirosis", "cum", 5833), (NATIONAL, "tuberculosis", "cases", 166),
            (NATIONAL, "dengue", "T", 90), (NATIONAL, "dengue", "C", 99),
        ],
    ),
    "wer_2026_vol53_no26.pdf": dict(
        issue="Vol 53 No 26", week=(2026, 25), start=date(2026, 6, 15), n_diseases=14,
        cells=[
            ("Colombo", "dengue", "cases", 1138), ("Colombo", "dengue", "cum", 9357),
            ("Colombo", "leprosy", "cases", 3), ("Colombo", "leprosy", "cum", 83),
            ("Kalmunai", "leprosy", "cum", 23), ("Kalmunai", "dengue", "cum", 640),
            ("Gampaha", "dengue", "C", 86), ("Gampaha", "dengue", "T", 73),
            (NATIONAL, "dengue", "cases", 5828), (NATIONAL, "dengue", "cum", 45879),
            (NATIONAL, "leptospirosis", "cases", 171), (NATIONAL, "tuberculosis", "cum", 3944),
            (NATIONAL, "leprosy", "cum", 584), (NATIONAL, "dengue", "T", 90),
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
    # Table 1 of Vol 52 No 2: "28th Dec - 03rd Jan 2025 (1st Week)", Sat 28 Dec 2024 - Fri 3 Jan 2025
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


# ------------------------------------------------------------------ validation rules

def _frame(rows):
    return pd.DataFrame(rows, columns=["epi_year", "epi_week", "area", "disease", "cases", "cum_cases"]
                        ).assign(source_file="f.pdf")


def _split(df):
    passed, failed = validate(df)
    return reclassify_source_total_errors(passed, failed)


def _dengue_2022_case(national_cases=20, national_cum=26602, with_prev_week=True):
    """Week 24 is fine; in week 25 the districts add to 809 but the national row prints 20."""
    rows = []
    d24 = {"Colombo": (500, 4000), "Gampaha": (200, 2500), "Kandy": (100, 1000)}
    d25 = {"Colombo": (400, 4400), "Gampaha": (250, 2750), "Kandy": (159, 1159)}  # sum 809
    if with_prev_week:
        rows += [(2022, 24, a, "dengue", c, m) for a, (c, m) in d24.items()]
        rows.append((2022, 24, NATIONAL, "dengue", 800, 7500))
    rows += [(2022, 25, a, "dengue", c, m) for a, (c, m) in d25.items()]
    rows.append((2022, 25, NATIONAL, "dengue", national_cases, national_cum))
    return _frame(rows)


def test_source_total_error_2022_dengue_case():
    # districts add to 809, the national row prints 20 and a cumulative that is not 7500 + 20
    passed, failed, errors = _split(_dengue_2022_case(national_cases=20, national_cum=26602))
    assert len(errors) == 1
    e = errors.iloc[0]
    assert (e["printed_national_cases"], e["district_sum_cases"]) == (20, 809)
    wk25 = passed[passed["epi_week"] == 25]
    assert set(wk25["area"]) == {"Colombo", "Gampaha", "Kandy"} and wk25["validated"].all()
    assert (wk25["note"] == "national_total_source_error").all()
    bad = failed[failed["epi_week"] == 25]
    assert list(bad["area"]) == [NATIONAL]  # only the national row goes to review
    assert bad["fail_reason"].iloc[0].startswith("source_total_error")


def test_rule_does_not_fire_when_a_district_fails_its_own_cumulative_check():
    df = _dengue_2022_case()
    df.loc[(df["epi_week"] == 25) & (df["area"] == "Kandy"), "cum_cases"] = 2000  # not 1000 + 159
    passed, failed, errors = _split(df)
    assert errors.empty
    assert len(failed[failed["epi_week"] == 25]) == 4  # nothing is reclassified: all four rows stay failed
    assert not (passed["note"] == "national_total_source_error").any()


def test_rule_does_not_fire_when_cumulative_status_is_unknown():
    # without the previous week the cumulative check cannot be evaluated, so nothing is assumed
    passed, failed, errors = _split(_dengue_2022_case(with_prev_week=False))
    assert errors.empty
    assert len(failed) == 4 and set(failed["fail_reason"]) == {"sum_mismatch;"}


def test_rule_does_not_fire_when_national_cumulative_is_consistent():
    # printed 20 weekly but cum = 7500 + 20: internally consistent, so the sum mismatch is not
    # attributable to a bad printed total
    passed, failed, errors = _split(_dengue_2022_case(national_cases=20, national_cum=7520))
    assert errors.empty
    assert len(failed[failed["epi_week"] == 25]) == 4


def test_missing_cell_group_goes_to_review_and_is_not_inferred():
    df = _dengue_2022_case(national_cases=809, national_cum=8309)
    df.loc[(df["epi_week"] == 25) & (df["area"] == "Kandy"), "cases"] = None
    ok, review = wer_pipeline.split_missing_cells(df)
    assert (ok["epi_week"] == 24).all()
    assert len(review) == 4
    assert list(review.loc[review["area"] == "Kandy", "fail_reason"]) == ["missing_cell;"]
    assert set(review.loc[review["area"] != "Kandy", "fail_reason"]) == {"group_has_missing_cell;"}


def test_percentages_outside_0_100_go_to_review():
    df = _dengue_2022_case(national_cases=809, national_cum=8309)
    df["completeness_pct"], df["timeliness_pct"] = 100.0, 50.0
    df.loc[df["area"] == "Kandy", "completeness_pct"] = 200.0  # e.g. Kalutara C** = 200 in Vol 52 No 23
    passed, failed = validate(df)
    passed, failed = wer_pipeline.flag_pct_range(passed, failed)
    assert set(failed["area"]) == {"Kandy"} and set(failed["fail_reason"]) == {"pct_out_of_range;"}
    assert "Kandy" not in set(passed["area"])


def test_duplicate_week_keeps_the_issue_that_adds_up():
    good = _dengue_2022_case(national_cases=809, national_cum=8309, with_prev_week=False)
    bad = good.copy()
    bad.loc[bad["area"] == NATIONAL, "cases"] = 20
    good["source_file"], bad["source_file"] = "a_good.pdf", "b_bad.pdf"
    kept, log = wer_pipeline.choose_duplicates(pd.concat([good, bad], ignore_index=True))
    assert set(kept["source_file"]) == {"a_good.pdf"}
    assert log[0]["kept"] == "a_good.pdf" and log[0]["dropped"] == ["b_bad.pdf"]
