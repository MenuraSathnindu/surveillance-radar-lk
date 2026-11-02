"""Build the weekly series the radar runs on.

Only `extraction_valid` RDHS rows (`validated`), weekly counts as first printed (`cases`), from
2022-W01 (the deliberate post-COVID baseline). Each (RDHS, disease) series is laid out on one
continuous canonical-week index starting at 2022-W01; weeks with no valid row are NaN.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from radar_lk import CLEAN_DIR


def week_index(first_year: int, last_year: int, last_week: int) -> pd.DataFrame:
    """Continuous canonical weeks from (first_year, 1) to (last_year, last_week)."""
    start = date.fromisocalendar(first_year, 1, 1)
    end = date.fromisocalendar(last_year, last_week, 1)
    rows = []
    d = start
    while d <= end:
        iso = d.isocalendar()
        rows.append({"t": len(rows), "week_start": d, "epi_year": iso.year, "epi_week": iso.week})
        d += timedelta(days=7)
    return pd.DataFrame(rows)


def load_panel(first_year: int = 2022, min_history: int = 104) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(panel, skipped). panel: one row per (area, disease, t) for every modelled series; skipped:
    series with fewer than `min_history` observed weeks (e.g. leprosy, 2026 only)."""
    c = pd.read_parquet(CLEAN_DIR / "wer.parquet")
    c = c[(c["area_level"] == "rdhs") & c["validated"] & (c["epi_year"] >= first_year)]
    last = (
        c[["epi_year", "epi_week"]].drop_duplicates().sort_values(["epi_year", "epi_week"]).iloc[-1]
    )
    idx = week_index(first_year, int(last["epi_year"]), int(last["epi_week"]))
    keep = [
        "area",
        "disease",
        "epi_year",
        "epi_week",
        "cases",
        "completeness_pct",
        "completeness_p10",
        "completeness_low",
        "revised",
        "revision_delta",
        "note",
        "source_file",
        "source_issue",
        "week_end",
    ]
    c = c[keep].rename(columns={"cases": "observed"})
    n_obs = c.groupby(["area", "disease"]).size().rename("observed_weeks").reset_index()
    ok = n_obs[n_obs["observed_weeks"] >= min_history]
    skipped = n_obs[n_obs["observed_weeks"] < min_history].assign(
        reason=lambda d: "insufficient history (< " + str(min_history) + " observed weeks)"
    )
    grid = ok[["area", "disease"]].merge(idx, how="cross")
    panel = grid.merge(c, on=["area", "disease", "epi_year", "epi_week"], how="left")
    panel["observed"] = panel["observed"].astype(float)
    return panel.sort_values(["area", "disease", "t"]).reset_index(drop=True), skipped
