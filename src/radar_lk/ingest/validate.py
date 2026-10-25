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
    sums = sum_check(df)
    d = cumulative_check(df).merge(
        sums[["epi_year", "epi_week", "disease", "sum_ok"]],
        on=["epi_year", "epi_week", "disease"],
        how="left",
    )
    bad = d["sum_ok"].eq(False) | d["cum_ok"].eq(False)
    reason = pd.Series("", index=d.index)
    reason[d["sum_ok"].eq(False)] += "sum_mismatch;"
    reason[d["cum_ok"].eq(False)] += "cumulative_mismatch;"
    d["fail_reason"] = reason
    d["validated"] = ~bad
    return d[~bad].reset_index(drop=True), d[bad].reset_index(drop=True)
