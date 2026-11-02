"""Validation checks. Rows that fail never reach the dashboard.

Input: a tidy DataFrame with at least
    epi_year, epi_week, area, disease, cases, cum_cases, source_file
where the national total row uses area == NATIONAL.
"""

from __future__ import annotations

import pandas as pd

NATIONAL = "Sri Lanka"


def sum_check(df: pd.DataFrame, col: str = "cases") -> pd.DataFrame:
    """Per (week, disease): do the unit rows add up to the printed national total?

    Returns one row per (epi_year, epi_week, disease) with columns
    units_sum, national, sum_ok.
    """
    keys = ["epi_year", "epi_week", "disease"]
    units = df[df["area"] != NATIONAL].groupby(keys)[col].sum().rename("units_sum")
    nat = df[df["area"] == NATIONAL].set_index(keys)[col].rename("national")
    out = pd.concat([units, nat], axis=1).reset_index()
    out["sum_ok"] = out["units_sum"].eq(out["national"])
    return out


def cumulative_check(df: pd.DataFrame) -> pd.DataFrame:
    """Per (area, disease, year): cum_t == cum_{t-1} + cases_t.

    The first week present in a year is checked against cases (cum == cases) only if it is week 1;
    otherwise it is marked unknown (NaN) because the previous week is missing.
    """
    d = df.sort_values(["area", "disease", "epi_year", "epi_week"]).copy()
    g = d.groupby(["area", "disease", "epi_year"])
    prev_cum = g["cum_cases"].shift(1)
    prev_week = g["epi_week"].shift(1)
    consecutive = prev_week.eq(d["epi_week"] - 1)
    expected = prev_cum + d["cases"]
    d["cum_ok"] = pd.NA
    d.loc[consecutive, "cum_ok"] = d.loc[consecutive, "cum_cases"].eq(expected[consecutive])
    first_week = d["epi_week"].eq(1) & prev_week.isna()
    d.loc[first_week, "cum_ok"] = d.loc[first_week, "cum_cases"].eq(d.loc[first_week, "cases"])
    return d


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (passed, failed). A row fails if its week/disease fails the sum check
    or the row itself fails the cumulative check. Unknown cumulative status passes
    but is kept visible via the cum_ok column.
    """
    keys = ["epi_year", "epi_week", "disease"]
    sums = sum_check(df)
    d = cumulative_check(df).merge(sums[keys + ["sum_ok"]], on=keys, how="left")
    bad = d["sum_ok"].eq(False) | d["cum_ok"].eq(False)
    reason = pd.Series("", index=d.index)
    reason[d["sum_ok"].eq(False)] += "sum_mismatch;"
    reason[d["cum_ok"].eq(False)] += "cumulative_mismatch;"
    d["fail_reason"] = reason
    d["validated"] = ~bad
    return d[~bad].reset_index(drop=True), d[bad].reset_index(drop=True)


def reclassify_source_total_errors(
    passed: pd.DataFrame, failed: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Separate a wrong *printed national total* from errors in the district rows.

    For a (week, disease) that fails the sum check, if every district row passes its own
    cumulative check (explicitly True, not unknown) and the national row fails its cumulative
    check, the districts are internally consistent and only the printed national figure is off.
    Then:
      - the district rows are kept: validated=True, note="national_total_source_error"
      - only the national row stays in the failed set, fail_reason "source_total_error;..."
    Anything else is left as validate() classified it.

    Returns (passed, failed, errors); ``errors`` has one row per reclassified (week, disease)
    with the printed national value and the district sum, for the extraction report.
    """
    keys = ["epi_year", "epi_week", "disease"]
    passed, failed = passed.copy(), failed.copy()
    for d in (passed, failed):
        if "note" not in d:
            d["note"] = ""
    promote: list[int] = []
    national_idx: list[int] = []
    errors = []
    sum_bad = failed[failed["sum_ok"].eq(False)]
    for key, g in sum_bad.groupby(keys):
        nat = g[g["area"] == NATIONAL]
        dist = g[g["area"] != NATIONAL]
        if len(nat) != 1 or dist.empty:
            continue
        ok = g["cum_ok"].astype("boolean")
        if not ok[nat.index].eq(False).all():
            continue
        if not ok[dist.index].fillna(False).all():
            continue
        promote += list(dist.index)
        national_idx += list(nat.index)
        e = dict(zip(keys, key, strict=True))
        e.update(
            printed_national_cases=int(nat["cases"].iloc[0]),
            district_sum_cases=int(dist["cases"].sum()),
            printed_national_cum=int(nat["cum_cases"].iloc[0]),
            district_sum_cum=int(dist["cum_cases"].sum()),
            source_file=nat["source_file"].iloc[0],
        )
        errors.append(e)
    moved = failed.loc[promote].copy()
    moved["validated"] = True
    moved["fail_reason"] = ""
    moved["note"] = "national_total_source_error"
    failed.loc[national_idx, "fail_reason"] = "source_total_error;" + failed.loc[national_idx, "fail_reason"]
    failed = failed.drop(index=promote).reset_index(drop=True)
    passed = pd.concat([passed, moved], ignore_index=True)
    return passed, failed, pd.DataFrame(errors)
