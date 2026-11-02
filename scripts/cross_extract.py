"""Independent second extractor: re-read every WER Table 1 with PyMuPDF and compare cell by cell
with the pdfplumber parser (src/radar_lk/ingest/parse_wer.py).

    python scripts/cross_extract.py

PyMuPDF only supplies words and their boxes; this script finds the page, the rows and the cell
order on its own (rows = words clustered across the rotated text line, read bottom-to-top). The
only shared pieces are the district-name normalisation and the canonical district list, which are
mappings, not extraction. Writes data/review_queue/cross_extract.csv (every disagreement) and
docs/CROSS_EXTRACT.md, and prints the agreement.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pymupdf

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from radar_lk import RAW_DIR, REVIEW_DIR, load_config  # noqa: E402
from radar_lk.ingest.parse_wer import norm, parse_issue  # noqa: E402
from radar_lk.ingest.validate import NATIONAL  # noqa: E402

OUT_MD = REPO / "docs" / "CROSS_EXTRACT.md"
ROW_TOL = 4.0  # pt; words whose centres across the rotated line differ by less are one row
NUMERIC = re.compile(r"^\d+(?:\.\d+)?%?$")


def _value(txt: str):
    if not NUMERIC.match(txt):
        return txt  # unreadable stays text, so it can only agree with an unreadable cell
    v = float(txt.rstrip("%"))
    return int(v) if v.is_integer() else v


def fitz_rows(path: Path, units: dict[str, str]) -> dict[str, list] | None:
    """{area: [cell values in column order]} read by PyMuPDF, or None if no Table 1 page."""
    doc = pymupdf.open(path)
    try:
        page = None
        for p in doc:
            t = re.sub(r"\s+", " ", p.get_text())
            if re.search(
                r"Table\s*1\s*:[^:()]{0,90}?reported\s+by\s+Medical\s+Officers\s+of\s+Health", t
            ):
                page = p
                break
        if page is None:
            return None
        # rotated words: those on text lines whose writing direction points up the page
        vertical = set()
        for b in page.get_text("dict")["blocks"]:
            for li, ln in enumerate(b.get("lines", [])):
                dx, dy = ln["dir"]
                if abs(dx) < 0.1 and dy < -0.9:
                    vertical.add((b["number"], li))
        words = [w for w in page.get_text("words") if (w[5], w[6]) in vertical]
        words.sort(key=lambda w: (w[0] + w[2]) / 2)
        rows: list[list] = []
        for w in words:
            xc = (w[0] + w[2]) / 2
            if rows and xc - rows[-1][0] <= ROW_TOL:
                rows[-1][1].append(w)
            else:
                rows.append([xc, [w]])
        out: dict[str, list] = {}
        for _, ws in rows:
            ws.sort(key=lambda w: -w[3])  # rotated text reads from the bottom of the page upwards
            toks = [w[4] for w in ws]
            k = 0
            while k < len(toks) and not NUMERIC.match(toks[k]):
                k += 1
            label = norm("".join(toks[:k]))
            area = NATIONAL if label == "srilanka" else units.get(label)
            if area and k < len(toks):
                out[area] = [_value(t) for t in toks[k:]]
        return out
    finally:
        doc.close()


def compare(path_str: str):
    path = Path(path_str)
    cfg = load_config()
    units = {norm(u): u for u in cfg["rdhs_units"]}
    for v, t in (cfg.get("rdhs_label_variants") or {}).items():
        units[norm(v)] = t
    res = parse_issue(path, cfg)
    if res.status != "ok":
        return {"file": path.name, "status": f"pdfplumber {res.status}", "cells": []}
    # pdfplumber cells in column order per area: (A, B) per disease, then T*, C**
    plumb: dict[str, list] = defaultdict(list)
    tc: dict[str, tuple] = {}
    for r in res.rows:
        plumb[r["area"]] += [r["cases"], r["cum_cases"]]
        tc[r["area"]] = (r["timeliness_pct"], r["completeness_pct"])
    cols = []
    for d in res.meta["diseases"]:
        cols += [f"{d}:A", f"{d}:B"]
    cols += ["T*", "C**"]
    try:
        fz = fitz_rows(path, units)
    except Exception as e:  # noqa: BLE001 - reported, not fatal
        return {"file": path.name, "status": f"pymupdf error {e}", "cells": []}
    if fz is None:
        return {"file": path.name, "status": "pymupdf found no Table 1", "cells": []}
    cells = []
    for area, vals in plumb.items():
        pv = vals + list(tc[area])
        fv = fz.get(area)
        blanks = [j for j, v in enumerate(pv) if v is None or v != v]
        aligned = None
        if fv is not None and len(fv) == len(cols):
            aligned = fv
        elif fv is not None and len(fv) == len(cols) - len(blanks):
            # pdfplumber found blank cells; PyMuPDF simply has fewer words. Align the rest in order.
            it = iter(fv)
            aligned = [None if j in blanks else next(it) for j in range(len(cols))]
        for j, col in enumerate(cols):
            f = aligned[j] if aligned is not None else None
            p = pv[j]
            p = None if p is not None and p != p else p
            p = int(p) if isinstance(p, float) and p.is_integer() else p
            note = ""
            if aligned is None:
                note = (
                    "row missing in pymupdf"
                    if fv is None
                    else (f"pymupdf row has {len(fv)} cells, expected {len(cols)}")
                )
            both_unreadable = (
                p is None and (f is None or isinstance(f, str)) and aligned is not None
            )
            if both_unreadable:
                note = (
                    "blank/unreadable in both"
                    if f is None
                    else f"unreadable in both (pymupdf: {f!r})"
                )
            cells.append(
                {
                    "file": path.name,
                    "issue": res.source_issue,
                    "epi_year": res.meta["epi_year"],
                    "epi_week": res.meta["epi_week"],
                    "area": area,
                    "column": col,
                    "pdfplumber": p,
                    "pymupdf": f,
                    "agree": both_unreadable or (p == f and f is not None),
                    "note": note,
                }
            )
    return {"file": path.name, "status": "compared", "cells": cells}


def main() -> None:
    paths = sorted(str(p) for p in (RAW_DIR / "wer").glob("*.pdf"))
    with ProcessPoolExecutor(4) as ex:
        results = list(ex.map(compare, paths, chunksize=4))
    df = pd.DataFrame([c for r in results for c in r["cells"]])
    skipped = [(r["file"], r["status"]) for r in results if r["status"] != "compared"]
    dis = df[~df["agree"]]
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    dis.to_csv(REVIEW_DIR / "cross_extract.csv", index=False)
    overall = 100 * df["agree"].mean()
    by_year = df.groupby("epi_year")["agree"].agg(["size", "mean"])
    by_year["% agree"] = 100 * by_year.pop("mean")
    by_year = by_year.rename(columns={"size": "cells"})
    print(f"cells compared: {len(df):,}; agreement {overall:.3f}%; disagreements {len(dis)}")
    print(by_year.round(3).to_string())
    for f, s in skipped:
        print(f"  not compared: {f} ({s})")
    lines = [
        "# Cross-extraction check (pdfplumber vs PyMuPDF)",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python "
        f"scripts/cross_extract.py`.",
        "",
        "Every Table 1 cell of every parsed WER issue (26 RDHS + SRI LANKA, every A/B column, "
        "T\\* and "
        "C\\*\\*) was extracted a second time with PyMuPDF, using its own word boxes, row "
        "clustering and "
        "cell order, and compared with the pdfplumber parser.",
        "",
        f"- Cells compared: **{len(df):,}** from {df['file'].nunique()} issues",
        f"- Agreement: **{overall:.3f}%**; disagreements: **{len(dis)}** (all listed in "
        "`data/review_queue/cross_extract.csv`)",
        f"- Of the agreeing cells, {int(df['note'].str.contains('in both').sum())} are blank or "
        "unreadable in both extractors (e.g. a stray `v` where a digit should be); they stay in "
        "review.",
        "- Both libraries read the PDF's embedded text layer, so this rules out parser bugs (row, "
        "column "
        "and token handling) but not a text layer that differs from the printed page; the "
        "hand-check "
        "pack covers that.",
        f"- Issues not compared: {len(skipped)}"
        + ("".join(f"\n  - `{f}`: {s}" for f, s in skipped) if skipped else ""),
        "",
        "| year | cells | % agree |",
        "|---|---|---|",
    ]
    lines += [f"| {y} | {int(r['cells']):,} | {r['% agree']:.3f} |" for y, r in by_year.iterrows()]
    lines += ["", "## Disagreements", ""]
    if dis.empty:
        lines.append("None.")
    else:
        lines += [
            "| issue | week | area | column | pdfplumber | pymupdf | note |",
            "|---|---|---|---|---|---|---|",
        ]
        for _, r in dis.head(200).iterrows():
            lines.append(
                f"| {r['issue']} | {r['epi_year']}-W{r['epi_week']:02d} | {r['area']} | "
                f"{r['column']} | "
                f"{r['pdfplumber']} | {r['pymupdf']} | {r['note']} |"
            )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
