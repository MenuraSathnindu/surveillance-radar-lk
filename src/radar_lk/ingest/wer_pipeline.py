"""WER pipeline: parse every PDF, drop duplicate weeks, validate, write clean + review outputs.

    python -m radar_lk.ingest.parse_wer

Two-tier validation (see CLAUDE.md):
  tier 1  extraction_valid  within-issue checks; only these rows reach data/clean and the dashboard
  tier 2  revised           cross-week identity cum_t = cum_(t-1) + weekly_t; a failure keeps the
                            row and records revised=True and revision_delta
Weekly counts are kept AS PRINTED in the issue (first-printed), which is what a Regional
Epidemiologist saw in real time; later revisions only show up in the cumulative column.

Outputs: data/clean/wer.parquet (+ DuckDB views), data/review_queue/wer.parquet,
data/review_queue/wer_issues.csv (issues that failed / had no table), docs/EXTRACTION_REPORT.md.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from radar_lk import REVIEW_DIR, store
from radar_lk.ingest.parse_wer import IssueResult, parse_all
from radar_lk.ingest.validate import (
    cross_week_gap,
    scrambled_weekly_groups,
    stale_weekly_groups,
    sum_check,
    within_issue_split,
)

WEEK = ["epi_year", "epi_week"]
LOW_QUANTILE = 0.10  # completeness_low: below this RDHS's own past 10th percentile
LOW_MIN_WEEKS = 26  # ... once at least this many past weeks exist
FIRST_YEAR = 2022  # deliberate post-COVID baseline: weeks before 2022-W01 are dropped


def assemble(results: list[IssueResult]) -> pd.DataFrame:
    rows = [r for res in results if res.status == "ok" for r in res.rows]
    return pd.DataFrame(rows)


def choose_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Two issues for the same canonical week: keep the one whose districts add to its national
    row in the most (week, disease) checks. Ties go to the later source_file name; every choice
    is logged so it can be reviewed."""
    log: list[dict] = []
    drop: list[tuple] = []
    files_per_week = df.groupby(WEEK)["source_file"].nunique()
    for y, w in files_per_week[files_per_week > 1].index:
        cand = df[(df["epi_year"] == y) & (df["epi_week"] == w)]
        scores = {}
        for f, g in cand.groupby("source_file"):
            scores[f] = float(sum_check(g)["sum_ok"].mean())
        ranked = sorted(scores, key=lambda f: (scores[f], f), reverse=True)
        keep = ranked[0]
        tie = len(set(scores.values())) == 1
        log.append(
            {
                "epi_year": y,
                "epi_week": w,
                "kept": keep,
                "dropped": ranked[1:],
                "scores": {f: round(s, 4) for f, s in scores.items()},
                "reason": "tie on sum check; kept later file name"
                if tie
                else "kept best sum-check score",
            }
        )
        drop += [(f, y, w) for f in ranked[1:]]
    for f, y, w in drop:
        df = df[~((df["source_file"] == f) & (df["epi_year"] == y) & (df["epi_week"] == w))]
    return df.reset_index(drop=True), log


def drop_pre_baseline(df: pd.DataFrame) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    """Post-COVID baseline: drop every row whose reporting week is before 2022-W01 (e.g. the
    2021 issues the website lists under 2022 dates). Returns (kept, [(issue, week) dropped])."""
    early = df[df["epi_year"] < FIRST_YEAR]
    dropped = sorted(
        {(i, f"{y}-W{w:02d}") for i, y, w in early[["source_issue", "epi_year", "epi_week"]].values}
    )
    return df[df["epi_year"] >= FIRST_YEAR].reset_index(drop=True), dropped


def split_missing_cells(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A blank/unreadable count cell cannot be verified, and it breaks the sum check for the
    whole (week, disease), so that whole group goes to review. The missing value is not inferred
    from the national total."""
    keys = ["epi_year", "epi_week", "disease"]
    missing = df["cases"].isna() | df["cum_cases"].isna()
    bad_groups = df[missing][keys].drop_duplicates()
    flag = bad_groups.assign(_g=True)
    in_group = df.merge(flag, on=keys, how="left")["_g"].fillna(False).to_numpy(bool)
    review = df[in_group].copy()
    review["fail_reason"] = [
        "missing_cell" if m else "group_has_missing_cell" for m in missing[in_group]
    ]
    review["validated"] = False
    return df[~in_group].reset_index(drop=True), review.reset_index(drop=True)


def clean_percentages(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Completeness/timeliness are percentages; a printed value outside 0..100 (e.g. Kalutara
    C** = 200) is not a percentage, so it becomes NaN. The count cells of that row are unaffected.

    Returns (df, counts) with the number of (area, week) values blanked per column."""
    df = df.copy()
    counts = {}
    unit = df.drop_duplicates(["epi_year", "epi_week", "area"])
    for col in ("completeness_pct", "timeliness_pct"):
        bad = (df[col] < 0) | (df[col] > 100)
        ub = (unit[col] < 0) | (unit[col] > 100)
        counts[col] = {
            "area_weeks": int(ub.sum()),
            "rdhs_area_weeks": int((ub & (unit["area_level"] == "rdhs")).sum()),
            "values": sorted(unit.loc[ub, col].astype(float).unique().tolist()),
        }
        df.loc[bad, col] = np.nan
    return df, counts


def add_completeness_low(df: pd.DataFrame) -> pd.DataFrame:
    """completeness_low = this week's C** is below the RDHS's own 10th percentile of C** over its
    *past* weeks only (expanding window, shifted by one week so a week never sees itself). Needs
    LOW_MIN_WEEKS past values; earlier weeks and the national row get <NA>. T* is never used.
    """
    df = df.copy()
    unit = (
        df[df["area_level"] == "rdhs"]
        .drop_duplicates(["epi_year", "epi_week", "area"])
        .sort_values(["area", "epi_year", "epi_week"])
    )
    unit["completeness_p10"] = unit.groupby("area")["completeness_pct"].transform(
        lambda s: s.expanding(min_periods=LOW_MIN_WEEKS).quantile(LOW_QUANTILE).shift(1)
    )
    unit["completeness_low"] = (unit["completeness_pct"] < unit["completeness_p10"]).astype(
        "boolean"
    )
    unit.loc[
        unit["completeness_p10"].isna() | unit["completeness_pct"].isna(), "completeness_low"
    ] = pd.NA
    df = df.merge(
        unit[["area", "epi_year", "epi_week", "completeness_p10", "completeness_low"]],
        on=["area", "epi_year", "epi_week"],
        how="left",
    )
    df["completeness_low"] = df["completeness_low"].astype("boolean")
    return df


def validate_wer(df: pd.DataFrame):
    """Two-tier validation. Returns (clean, review, errors, pct_counts, stale).

    clean   extraction_valid rows (validated=True), each with revised / revision_delta
    review  everything else, with fail_reason
    errors  one row per (week, disease) whose printed national row is a source error
    stale   (week, disease) groups whose weekly column repeats the previous week or is scrambled
            across the rows (column `kind`; all queued)
    """
    df, missing_review = split_missing_cells(df)
    df = df.astype({"cases": "int64", "cum_cases": "int64"})
    df, pct_counts = clean_percentages(df)
    df = add_completeness_low(df)
    # tier 2 information first (needs every neighbouring week, whatever its tier-1 outcome)
    gap = cross_week_gap(df)
    df["revision_delta"] = gap
    df["revised"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
    df.loc[gap.notna(), "revised"] = gap[gap.notna()] != 0
    # tier 1
    kept, rejected, errors = within_issue_split(df)
    # a weekly column copied from the previous issue, or printed against the wrong rows, passes
    # every sum and cumulative check
    stale = stale_weekly_groups(df).assign(kind="stale_weekly_copy")
    scr = scrambled_weekly_groups(df).assign(kind="scrambled_weekly_column")
    keys = ["epi_year", "epi_week", "disease"]
    stale = pd.concat([stale, scr], ignore_index=True)
    for kind in ("stale_weekly_copy", "scrambled_weekly_column"):
        part = stale[stale["kind"] == kind]
        if part.empty:
            continue
        flag = part[keys].drop_duplicates().assign(_stale=True)
        hit = kept.merge(flag, on=keys, how="left")["_stale"].fillna(False).to_numpy(bool)
        moved = kept[hit].copy()
        moved["validated"] = False
        moved["fail_reason"] = kind
        kept = kept[~hit].reset_index(drop=True)
        rh = rejected.merge(flag, on=keys, how="left")["_stale"].fillna(False).to_numpy(bool)
        rejected.loc[rh, "fail_reason"] = f"{kind};" + rejected.loc[rh, "fail_reason"]
        rejected = pd.concat([rejected, moved], ignore_index=True)
        errors = errors.merge(flag, on=keys, how="left")
        errors = errors[errors["_stale"].isna()].drop(columns="_stale").reset_index(drop=True)
    rejected = pd.concat([rejected, missing_review], ignore_index=True)
    for part in (kept, rejected):
        part["revised"] = part["revised"].astype("boolean")
    return kept, rejected, errors, pct_counts, stale


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values([*WEEK, "disease", "area"]).reset_index(drop=True)


def run(raw_dir: Path, workers: int = 4, write_report: bool = True) -> int:
    paths = sorted(raw_dir.glob("*.pdf"))
    print(f"parsing {len(paths)} PDFs from {raw_dir} ...")
    results = parse_all(paths, workers)
    ok = sum(r.status == "ok" for r in results)
    print(
        f"  ok {ok}, no_table {sum(r.status == 'no_table' for r in results)}, "
        f"failed {sum(r.status == 'failed' for r in results)}"
    )
    for r in results:
        if r.status == "failed":
            print(f"  [failed] {r.file}: {r.reason}")

    raw = assemble(results)
    deduped, dup_log = choose_duplicates(raw)
    deduped, dropped_early = drop_pre_baseline(deduped)
    clean, review, errors, pct_counts, stale = validate_wer(deduped)
    clean, review = _finish(clean), _finish(review)

    store.write_clean(clean, "wer")
    store.write_review(review, "wer")
    store.refresh_db()
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"file": r.file, "status": r.status, "reason": r.reason, "source_issue": r.source_issue}
            for r in results
            if r.status != "ok"
        ]
    ).to_csv(REVIEW_DIR / "wer_issues.csv", index=False)

    d = clean[clean["area_level"] == "rdhs"]
    r_ = review[review["area_level"] == "rdhs"]
    total = len(d) + len(r_)
    print(
        f"district-disease-weeks extraction_valid: {len(d)}/{total} = "
        f"{100 * len(d) / max(total, 1):.2f}%"
    )
    rv = d["revised"].dropna()
    print(
        f"revised (cross-week identity fails): {100 * rv.mean():.2f}% of {len(rv)} checkable rows"
    )
    print(
        f"national source errors: {errors['kind'].value_counts().to_dict()}; duplicate weeks: "
        f"{len(dup_log)}"
    )
    print(f"dropped before 2022-W01: {dropped_early}")
    if not review.empty:
        print("review reasons (rows):")
        print(review["fail_reason"].value_counts().head(8).to_string())

    if write_report:
        from radar_lk.ingest.report_wer import write_report as _write

        _write(
            results, raw, deduped, clean, review, errors, dup_log, pct_counts, dropped_early, stale
        )
    return 0
