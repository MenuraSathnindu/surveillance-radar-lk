"""Validation checks. Rows that fail never reach the dashboard.

Input: a tidy DataFrame with at least
    epi_year, epi_week, area, disease, cases, cum_cases, source_file
where the national total row uses area == NATIONAL.
"""

from __future__ import annotations

import numpy as np
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


def cross_week_gap(df: pd.DataFrame) -> pd.Series:
    """cum_t - (cum_(t-1) + weekly_t) per row, aligned to ``df``.

    NaN where the previous week is missing. In the first week of a year (epi_week 1, nothing
    before it in that year) the cumulative must equal the weekly count, so the gap is cum - weekly.
    A non-zero gap means the printed cumulative was revised after the previous issue.
    """
    d = df.sort_values(["area", "disease", "epi_year", "epi_week"])
    g = d.groupby(["area", "disease", "epi_year"])
    prev_cum = g["cum_cases"].shift(1)
    prev_week = g["epi_week"].shift(1)
    gap = d["cum_cases"] - (prev_cum + d["cases"])
    gap[~prev_week.eq(d["epi_week"] - 1)] = float("nan")
    first = d["epi_week"].eq(1) & prev_week.isna()
    gap[first] = d.loc[first, "cum_cases"] - d.loc[first, "cases"]
    return gap.reindex(df.index)


def within_issue_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Tier-1 (extraction) validation: checks that need only the one issue.

    Per (week, disease) the 26 districts' *cumulative* counts must add to the printed national
    cumulative. If they do not, the whole group is unreliable and goes to review
    (``cum_sum_mismatch``). If they do but the districts' *weekly* counts do not add to the printed
    national weekly, the national weekly figure is a source error: the district rows are kept
    (``note=national_weekly_source_error``) and only the national row goes to review.
    Symmetrically, if the districts' *weekly* counts add to the printed national weekly but the
    cumulatives do not add up, the national cumulative is treated as the source error
    (``note=national_cumulative_source_error``): districts kept, national row queued. Only when
    neither column adds up is the whole group unreliable (``cum_sum_mismatch``).

    Returns (kept, review, errors); ``errors`` lists both kinds of national source error (column
    ``kind``).
    """
    keys = ["epi_year", "epi_week", "disease"]
    wk = sum_check(df, "cases").rename(
        columns={
            "units_sum": "district_sum_cases",
            "national": "printed_national_cases",
            "sum_ok": "wk_ok",
        }
    )
    cm = sum_check(df, "cum_cases").rename(
        columns={
            "units_sum": "district_sum_cum",
            "national": "printed_national_cum",
            "sum_ok": "cum_ok_sum",
        }
    )
    g = wk.merge(cm, on=keys)
    g["state"] = "ok"
    g.loc[~g["wk_ok"] & g["cum_ok_sum"], "state"] = "national_weekly_source_error"
    g.loc[g["wk_ok"] & ~g["cum_ok_sum"], "state"] = "national_cumulative_source_error"
    g.loc[~g["wk_ok"] & ~g["cum_ok_sum"], "state"] = "cum_sum_mismatch"
    d = df.merge(g[keys + ["state"]], on=keys, how="left")
    d["note"] = ""
    is_nat = d["area"] == NATIONAL
    err = d["state"].isin(["national_weekly_source_error", "national_cumulative_source_error"])
    d.loc[err & ~is_nat, "note"] = d.loc[err & ~is_nat, "state"]
    bad = (d["state"] == "cum_sum_mismatch") | d["state"].isna() | (err & is_nat)
    d["fail_reason"] = ""
    d.loc[bad, "fail_reason"] = d.loc[bad, "state"].fillna("no_national_row")
    d["validated"] = ~bad
    errors = g[
        g["state"].isin(["national_weekly_source_error", "national_cumulative_source_error"])
    ]
    errors = errors.rename(columns={"state": "kind"}).drop(columns=["wk_ok", "cum_ok_sum"])
    src = df.drop_duplicates(keys)[keys + ["source_file"]]
    errors = errors.merge(src, on=keys, how="left")
    return (
        d[~bad].reset_index(drop=True),
        d[bad].reset_index(drop=True),
        errors.reset_index(drop=True),
    )


def stale_weekly_groups(
    df: pd.DataFrame, min_nonzero: int = 8, group_share: float = 0.8, issue_share: float = 0.7
) -> pd.DataFrame:
    """(week, disease) groups whose district weekly column repeats the previous week's.

    A source error seen in the WER: the weekly (A) column of an issue is a copy of the previous
    issue's (e.g. Vol 53 No 27 dengue: all 26 districts identical to Vol 53 No 26, while the
    cumulatives were advanced by the copied values). Every sum and cumulative check passes, so
    it needs its own test. Flagged when, in a group, >= `min_nonzero` districts report a non-zero
    count and >= `group_share` of them equal the previous canonical week exactly; or when
    >= `issue_share` of all non-zero district cells of the whole issue repeat (then every disease
    of that week is flagged). Returns one row per flagged group.
    """
    d = df[df["area"] != NATIONAL][["area", "disease", "epi_year", "epi_week", "cases"]].copy()
    d["monday"] = [
        pd.Timestamp.fromisocalendar(int(y), int(w), 1)
        for y, w in zip(d["epi_year"], d["epi_week"], strict=True)
    ]
    prev = d[["area", "disease", "monday", "cases"]].rename(columns={"cases": "prev_cases"})
    prev["monday"] = prev["monday"] + pd.Timedelta(days=7)
    m = d.merge(prev, on=["area", "disease", "monday"], how="inner")
    m["nz"] = m["cases"] > 0
    m["rep"] = m["nz"] & (m["cases"] == m["prev_cases"])
    keys = ["epi_year", "epi_week", "disease"]
    g = m.groupby(keys).agg(nonzero=("nz", "sum"), repeated=("rep", "sum")).reset_index()
    g["share"] = g["repeated"] / g["nonzero"].where(g["nonzero"] > 0)
    w = m.groupby(["epi_year", "epi_week"]).agg(nz=("nz", "sum"), rep=("rep", "sum")).reset_index()
    w["issue_share"] = w["rep"] / w["nz"].where(w["nz"] > 0)
    g = g.merge(w[["epi_year", "epi_week", "issue_share"]], on=["epi_year", "epi_week"])
    whole = g["issue_share"] >= issue_share
    one = (g["nonzero"] >= min_nonzero) & (g["share"] >= group_share)
    g["scope"] = np.where(whole, "whole issue", np.where(one, "disease column", ""))
    return g[whole | one].reset_index(drop=True)


def scrambled_weekly_groups(
    df: pd.DataFrame,
    min_nonzero: int = 20,
    rho_max: float = 0.3,
    rho_prev_min: float = 0.7,
    issue_min: int = 2,
) -> pd.DataFrame:
    """(week, disease) groups whose weekly column is scrambled across the district rows.

    A source error seen in the WER: the weekly (A) column of an issue is printed against the wrong
    rows (Vol 53 No 15, 2026-W14 dengue: Colombo 9 and Matale 256 where the weeks around read about
    300 and 20), with the cumulatives advanced to match and the national total unchanged, so every
    sum and cumulative check passes. Past-only test: with >= `min_nonzero` non-zero districts, the
    Spearman rank correlation of this week's district counts with last week's is below `rho_max`
    while last week and the week before agreed (rho >= `rho_prev_min`). If >= `issue_min` diseases
    of one week trip, every disease of that week is flagged (whole issue).
    """
    from scipy.stats import spearmanr

    d = df[df["area"] != NATIONAL][["area", "disease", "epi_year", "epi_week", "cases"]].copy()
    d["monday"] = [
        pd.Timestamp.fromisocalendar(int(y), int(w), 1)
        for y, w in zip(d["epi_year"], d["epi_week"], strict=True)
    ]
    week_of = d.drop_duplicates("monday").set_index("monday")[["epi_year", "epi_week"]]
    rows = []
    for dis, g in d.groupby("disease"):
        p = g.pivot_table(index="monday", columns="area", values="cases").sort_index()
        for t in p.index:
            t1, t2 = t - pd.Timedelta(days=7), t - pd.Timedelta(days=14)
            if t1 not in p.index or t2 not in p.index:
                continue
            a, b, c = p.loc[t], p.loc[t1], p.loc[t2]
            ok = a.notna() & b.notna() & c.notna()
            if (a[ok] > 0).sum() < min_nonzero:
                continue
            r = spearmanr(a[ok], b[ok]).correlation
            r0 = spearmanr(b[ok], c[ok]).correlation
            if r < rho_max and r0 >= rho_prev_min:
                rows.append(
                    {
                        "monday": t,
                        "disease": dis,
                        "rho": r,
                        "rho_prev": r0,
                        "nonzero": int((a[ok] > 0).sum()),
                    }
                )
    out = pd.DataFrame(rows, columns=["monday", "disease", "rho", "rho_prev", "nonzero"])
    if out.empty:
        return out.assign(epi_year=[], epi_week=[], scope=[]).drop(columns="monday")
    n_per_week = out.groupby("monday")["disease"].transform("size")
    out["scope"] = np.where(n_per_week >= issue_min, "whole issue", "disease column")
    whole = out.loc[out["scope"] == "whole issue", "monday"].unique()
    extra = [
        {
            "monday": m,
            "disease": dis,
            "rho": np.nan,
            "rho_prev": np.nan,
            "nonzero": np.nan,
            "scope": "whole issue",
        }
        for m in whole
        for dis in sorted(
            set(d.loc[d["monday"] == m, "disease"]) - set(out.loc[out["monday"] == m, "disease"])
        )
    ]
    out = pd.concat([out, pd.DataFrame(extra)], ignore_index=True)
    out = out.join(week_of, on="monday").drop(columns="monday")
    return out.sort_values(["epi_year", "epi_week", "disease"]).reset_index(drop=True)
