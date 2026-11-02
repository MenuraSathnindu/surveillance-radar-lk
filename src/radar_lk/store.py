"""Tidy schema and Parquet/DuckDB IO. Everything downstream reads from here."""

from __future__ import annotations

import pandas as pd

from radar_lk import CLEAN_DIR, REVIEW_DIR

TIDY_COLUMNS = [
    "week_start",
    "week_end",
    "epi_year",
    "epi_week",
    "area_level",
    "area",
    "disease",
    "cases",
    "cum_cases",
    "completeness_pct",
    "timeliness_pct",
    "source_file",
    "source_issue",
    "extracted_at",
    "validated",
]

DB_PATH = CLEAN_DIR / "radar.duckdb"


def conform(df: pd.DataFrame) -> pd.DataFrame:
    missing = set(TIDY_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"missing tidy columns: {sorted(missing)}")
    return df[TIDY_COLUMNS + [c for c in df.columns if c not in TIDY_COLUMNS]]


def write_clean(df: pd.DataFrame, name: str) -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    conform(df).to_parquet(CLEAN_DIR / f"{name}.parquet", index=False)


def write_review(df: pd.DataFrame, name: str) -> None:
    if df.empty:
        return
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(REVIEW_DIR / f"{name}.parquet", index=False)


def refresh_db() -> None:
    """Rebuild DuckDB views over every clean Parquet file."""
    import duckdb

    con = duckdb.connect(str(DB_PATH))
    for p in sorted(CLEAN_DIR.glob("*.parquet")):
        sql = f"CREATE OR REPLACE VIEW {p.stem} AS SELECT * FROM read_parquet('{p.as_posix()}')"
        con.execute(sql)
    con.close()
