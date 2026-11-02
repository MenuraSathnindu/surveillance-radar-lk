"""WER pipeline: parse every PDF, drop duplicate weeks, validate, write clean + review outputs.

    python -m radar_lk.ingest.parse_wer

Outputs: data/clean/wer.parquet (+ DuckDB views), data/review_queue/wer.parquet,
data/review_queue/wer_issues.csv (issues that failed / had no table), docs/EXTRACTION_REPORT.md.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from radar_lk import REVIEW_DIR, store
from radar_lk.ingest.parse_wer import IssueResult, parse_all
from radar_lk.ingest.validate import reclassify_source_total_errors, sum_check, validate

WEEK = ["epi_year", "epi_week"]


def assemble(results: list[IssueResult]) -> pd.DataFrame:
    rows = [r for res in results if res.status == "ok" for r in res.rows]
    return pd.DataFrame(rows)


def choose_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Two issues for the same canonical week: keep the one whose districts add to its national
    row in the most (week, disease) checks. Ties go to the later source_file name; every choice
    is logged so it can be reviewed."""
    log: list[dict] = []
    drop: list[str] = []
    files_per_week = df.groupby(WEEK)["source_file"].nunique()
    for y, w in files_per_week[files_per_week > 1].index:
        cand = df[(df["epi_year"] == y) & (df["epi_week"] == w)]
        scores = {}
        for f, g in cand.groupby("source_file"):
            scores[f] = float(sum_check(g)["sum_ok"].mean())
        ranked = sorted(scores, key=lambda f: (scores[f], f), reverse=True)
        keep = ranked[0]
        tie = len({scores[f] for f in scores}) == 1
        log.append({
            "epi_year": y, "epi_week": w, "kept": keep, "dropped": ranked[1:],
            "scores": {f: round(s, 4) for f, s in scores.items()},
            "reason": "tie on sum check; kept later file name" if tie else "kept best sum-check score",
        })
        drop += [(f, y, w) for f in ranked[1:]]
    for f, y, w in drop:
        df = df[~((df["source_file"] == f) & (df["epi_year"] == y) & (df["epi_week"] == w))]
    return df.reset_index(drop=True), log


def split_missing_cells(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A blank/unreadable count cell cannot be verified, and it breaks the sum check for the
    whole (week, disease), so that whole group goes to review. The missing value is not inferred
    from the national total."""
    keys = ["epi_year", "epi_week", "disease"]
    missing = df["cases"].isna() | df["cum_cases"].isna()
    bad_groups = df[missing][keys].drop_duplicates()
    in_group = df.merge(bad_groups.assign(_g=True), on=keys, how="left")["_g"].fillna(False).to_numpy(bool)
    review = df[in_group].copy()
    review["fail_reason"] = [
        "missing_cell;" if m else "group_has_missing_cell;" for m in missing[in_group]
    ]
    review["validated"] = False
    return df[~in_group].reset_index(drop=True), review.reset_index(drop=True)


def flag_pct_range(passed: pd.DataFrame, failed: pd.DataFrame):
    """Completeness/timeliness are percentages; a printed value outside 0..100 is a source
    error (e.g. Kalutara C** = 200). Counts may be fine, but gating on it would be wrong, so the
    row goes to review."""
    pct = passed[["completeness_pct", "timeliness_pct"]]
    bad = ((pct < 0) | (pct > 100)).any(axis=1)
    moved = passed[bad].copy()
    moved["validated"] = False
    moved["fail_reason"] = "pct_out_of_range;"
    return passed[~bad].reset_index(drop=True), pd.concat([failed, moved], ignore_index=True)


def validate_wer(df: pd.DataFrame):
    """Missing-cell split, validate(), the printed-national-total rule, then the pct range check.

    Returns (clean, review, errors)."""
    df, missing_review = split_missing_cells(df)
    df = df.astype({"cases": "int64", "cum_cases": "int64"})
    passed, failed = validate(df)
    passed, failed, errors = reclassify_source_total_errors(passed, failed)
    passed, failed = flag_pct_range(passed, failed)
    failed = pd.concat([failed, missing_review], ignore_index=True)
    return passed, failed, errors


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "cum_ok" in df:
        df["cum_ok"] = df["cum_ok"].astype("boolean")
    if "sum_ok" in df:
        df["sum_ok"] = df["sum_ok"].astype("boolean")
    return df.sort_values(WEEK + ["disease", "area"]).reset_index(drop=True)


def run(raw_dir: Path, workers: int = 4, write_report: bool = True) -> int:
    paths = sorted(raw_dir.glob("*.pdf"))
    print(f"parsing {len(paths)} PDFs from {raw_dir} ...")
    results = parse_all(paths, workers)
    ok = sum(r.status == "ok" for r in results)
    print(f"  ok {ok}, no_table {sum(r.status == 'no_table' for r in results)}, "
          f"failed {sum(r.status == 'failed' for r in results)}")
    for r in results:
        if r.status == "failed":
            print(f"  [failed] {r.file}: {r.reason}")

    raw = assemble(results)
    deduped, dup_log = choose_duplicates(raw)
    passed, failed, errors = validate_wer(deduped)
    clean, review = _finish(passed), _finish(failed)

    store.write_clean(clean, "wer")
    store.write_review(review, "wer")
    store.refresh_db()
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"file": r.file, "status": r.status, "reason": r.reason, "source_issue": r.source_issue}
         for r in results if r.status != "ok"]
    ).to_csv(REVIEW_DIR / "wer_issues.csv", index=False)

    d = clean[clean["area_level"] == "rdhs"]
    r_ = review[review["area_level"] == "rdhs"]
    total = len(d) + len(r_)
    print(f"district-disease-weeks: {len(d)}/{total} validated = {100 * len(d) / max(total, 1):.2f}%")
    print(f"duplicate weeks resolved: {len(dup_log)}; source_total_error cases: {len(errors)}")
    if not review.empty:
        print("top fail reasons (rows):")
        print(review["fail_reason"].value_counts().head(8).to_string())

    if write_report:
        from radar_lk.ingest.report_wer import write_report as _write

        _write(results, raw, deduped, clean, review, errors, dup_log)
    return 0
