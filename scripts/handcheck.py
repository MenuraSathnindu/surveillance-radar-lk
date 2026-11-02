"""Hand-check pack: sample validated cells and render the source page with each cell boxed.

    python scripts/handcheck.py [--n 40] [--seed 20261102]

Writes data/handcheck/<issue>.png (the Table 1 page, rotated upright, sampled cells boxed and
numbered) and data/handcheck/handcheck.csv. Fill the `verified` column (y / n, and the printed
value if different) while looking at the image; the numbers in `no` match the boxes.

Sampling is stratified: the same number of cells per year, and within a year the diseases are
cycled so no disease dominates. Only validated RDHS rows are sampled (the national row is
excluded), and each cell is either the weekly (A) or the cumulative (B) column.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from radar_lk import CLEAN_DIR, RAW_DIR, load_config  # noqa: E402
from radar_lk.ingest.parse_wer import (  # noqa: E402
    find_table_page,
    norm,
    read_header,
    read_lines,
    tokens,
)

OUT = REPO / "data" / "handcheck"
RES = 110  # dpi of the rendered page


def sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    years = sorted(df["epi_year"].unique())
    years = [y for y in years if (df["epi_year"] == y).sum() > 2000]  # skip stray out-of-range years
    per_year = [n // len(years) + (1 if i < n % len(years) else 0) for i in range(len(years))]
    picks = []
    for y, k in zip(years, per_year, strict=True):
        d = df[df["epi_year"] == y]
        diseases = sorted(d["disease"].unique())
        rng.shuffle(diseases)
        for i in range(k):
            dis = diseases[i % len(diseases)]
            cand = d[d["disease"] == dis]
            row = cand.iloc[rng.randrange(len(cand))]
            picks.append((row, "A" if rng.random() < 0.5 else "B"))
    rng.shuffle(picks)
    out = []
    for row, col in picks:
        out.append({
            "issue": row["source_issue"], "page": int(row["page"]), "district": row["area"],
            "disease": row["disease"], "column": col,
            "extracted_value": int(row["cases"] if col == "A" else row["cum_cases"]),
            "verified": "", "epi_week": f"{row['epi_year']}-W{int(row['epi_week']):02d}",
            "source_file": row["source_file"],
        })
    return pd.DataFrame(out)


def locate(path: Path, cfg: dict, wanted: list[dict]):
    """Page object, page index and, for each wanted cell, its box in page coordinates (or None)."""
    alias = {norm(a): d["id"] for d in cfg["diseases"] for a in d["aliases"]}
    order = [d["id"] for d in cfg["diseases"]]
    units = {norm(u): u for u in cfg["rdhs_units"]}
    for v, t in cfg.get("rdhs_label_variants", {}).items():
        units[norm(v)] = t
    pdf = pdfplumber.open(path)
    idx, _, _ = find_table_page(pdf)
    page = pdf.pages[idx]
    H = float(page.height)
    lines = read_lines(page)
    layout, sub = read_header(lines, alias, order)
    ncol = len(layout.label_c)
    label_end = layout.label_c[0] - 10.0
    boxes: dict[tuple, tuple | None] = {}
    for ln in lines[sub + 1:]:
        toks = tokens(ln)
        label = norm("".join(t.text for t in toks if t.c < label_end))
        area = units.get(label)
        nums = [t for t in toks if t.c >= label_end]
        if area is None or len(nums) != ncol:
            continue
        x0, x1 = min(c["x0"] for c in ln), max(c["x1"] for c in ln)
        for w in wanted:
            if w["district"] != area:
                continue
            k = layout.diseases.index(w["disease"]) if w["disease"] in layout.diseases else None
            if k is None:
                continue
            t = nums[2 * k + (0 if w["column"] == "A" else 1)]
            boxes[(w["district"], w["disease"], w["column"])] = (
                x0 - 1, H - t.e - 1.5, x1 + 1, H - t.s + 1.5)
    return pdf, page, boxes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261102)
    a = ap.parse_args()

    clean = pd.read_parquet(CLEAN_DIR / "wer.parquet")
    df = clean[(clean["area_level"] == "rdhs") & clean["validated"]]
    cells = sample(df, a.n, a.seed)
    cells.insert(0, "no", range(1, len(cells) + 1))
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    images = {}
    for src, grp in cells.groupby("source_file"):
        path = RAW_DIR / src
        pdf, page, boxes = locate(path, cfg, grp.to_dict("records"))
        img = page.to_image(resolution=RES)
        for _, c in grp.iterrows():
            b = boxes.get((c["district"], c["disease"], c["column"]))
            if b:
                img.draw_rect(b, stroke="red", stroke_width=2, fill=None)
        up = img.annotated.rotate(-90, expand=True)  # the table is rotated 90 degrees CCW
        name = f"{grp['issue'].iloc[0].replace(' ', '_')}.png"
        up.save(OUT / name)
        pdf.close()
        for no in grp["no"]:
            images[no] = name
    cells["image"] = cells["no"].map(images)
    cols = ["no", "issue", "page", "district", "disease", "column", "extracted_value", "verified",
            "epi_week", "image"]
    cells[cols].to_csv(OUT / "handcheck.csv", index=False)
    print(f"wrote {len(cells)} cells, {len(set(images.values()))} images to {OUT}")
    print(cells.groupby(cells["epi_week"].str[:4]).size().to_string())


if __name__ == "__main__":
    main()
