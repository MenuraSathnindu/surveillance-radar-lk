"""Publication lag of the WER: how long after a reporting week does its table become available?

    python -m radar_lk.ingest.publication_lag     # writes data/clean/publication_lag.parquet and
                                                  # publication_lag_weeks in config/sources.yaml

No network. Two clocks per PDF:
* `created`: the PDF's CreationDate metadata (when the issue was exported from Publisher);
  ModDate is read too (it equals CreationDate in these files).
* `uploaded`: inferred from the website file name `en_<13 hex digits>_...`, which has the shape of
  PHP `uniqid()` (first 8 hex digits = Unix seconds). This is an inference from the naming scheme,
  not documented by the site; older files (`vol_49_no_..`) have no such stamp.
Lag = date - last day of the reporting week printed in Table 1. A lag below 0 or above 365 days is
implausible (e.g. a re-export long after publication) and excluded from the summary.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
import pdfplumber

from radar_lk import CLEAN_DIR, CONFIG_PATH, RAW_DIR, REVIEW_DIR

OUT = CLEAN_DIR / "publication_lag.parquet"
DEFAULT_WEEKS = 8
MIN_FILES = 30
PDF_DATE = re.compile(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?")
UNIQID = re.compile(r"^en_([0-9a-f]{13})_", re.I)


def pdf_date(s: str | None):
    m = PDF_DATE.match(s or "")
    if not m:
        return None
    y, mo, d = (int(m.group(i)) for i in (1, 2, 3))
    try:
        return datetime(y, mo, d).date()
    except ValueError:
        return None


def upload_date(name: str):
    m = UNIQID.match(name)
    if not m:
        return None
    return datetime.fromtimestamp(int(m.group(1)[:8], 16), tz=timezone.utc).date()


def issue_weeks() -> pd.DataFrame:
    frames = []
    for p in (CLEAN_DIR / "wer.parquet", REVIEW_DIR / "wer.parquet"):
        if p.exists():
            frames.append(
                pd.read_parquet(
                    p, columns=["source_file", "source_issue", "epi_year", "epi_week", "week_end"]
                )
            )
    return pd.concat(frames).drop_duplicates("source_file")


def measure() -> pd.DataFrame:
    weeks = issue_weeks().set_index("source_file")
    rows = []
    for f in sorted((RAW_DIR / "wer").glob("*.pdf")):
        key = f"wer/{f.name}"
        if key not in weeks.index:
            continue  # no Table 1 week (no_table / failed / dropped)
        with pdfplumber.open(f) as pdf:
            meta = pdf.metadata or {}
        w = weeks.loc[key]
        end = pd.Timestamp(w["week_end"]).date()
        created = pdf_date(meta.get("CreationDate"))
        modified = pdf_date(meta.get("ModDate"))
        uploaded = upload_date(f.name)
        rows.append(
            {
                "source_file": key,
                "source_issue": w["source_issue"],
                "epi_year": int(w["epi_year"]),
                "epi_week": int(w["epi_week"]),
                "week_end": end,
                "created": created,
                "modified": modified,
                "uploaded": uploaded,
                "producer": meta.get("Producer"),
                "lag_created_days": (created - end).days if created else None,
                "lag_uploaded_days": (uploaded - end).days if uploaded else None,
            }
        )
    df = pd.DataFrame(rows)
    for c in ("lag_created_days", "lag_uploaded_days"):
        df[c] = pd.to_numeric(df[c])
        df[c.replace("lag_", "plausible_")] = df[c].between(0, 365)
    return df


def summary(df: pd.DataFrame, col: str) -> dict:
    ok = df.loc[df[col.replace("lag_", "plausible_")], col]
    return {
        "files": int(df[col].notna().sum()),
        "plausible": int(len(ok)),
        "median_days": float(ok.median()) if len(ok) else float("nan"),
        "p25_days": float(ok.quantile(0.25)) if len(ok) else float("nan"),
        "p75_days": float(ok.quantile(0.75)) if len(ok) else float("nan"),
    }


def write_config(weeks: int, how: str) -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    line = f"publication_lag_weeks: {weeks}   # {how}"
    if re.search(r"^publication_lag_weeks:.*$", text, re.M):
        text = re.sub(r"^publication_lag_weeks:.*$", line, text, flags=re.M)
    else:
        text = text.replace(
            "\nthresholds:",
            f"\n# WER publication lag "
            f"(src/radar_lk/ingest/publication_lag.py)\n{line}\n\nthresholds:",
            1,
        )
    CONFIG_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    df = measure()
    df.to_parquet(OUT, index=False)
    s = summary(df, "lag_created_days")
    if s["plausible"] >= MIN_FILES:
        weeks = int(round(s["median_days"] / 7))
        how = (
            f"median days from end of reporting week to PDF CreationDate = {s['median_days']:.0f} "
            f"over {s['plausible']} issues"
        )
    else:
        weeks, how = DEFAULT_WEEKS, "default: CreationDate not measurable"
    write_config(weeks, how)
    print(f"created: {s}")
    print(f"uploaded: {summary(df, 'lag_uploaded_days')}")
    print(f"publication_lag_weeks = {weeks} ({how})")


if __name__ == "__main__":
    main()
