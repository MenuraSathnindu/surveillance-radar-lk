"""Hand-check pack v2: 40 validated cells, one image each, for manual verification.

    python scripts/handcheck.py            # writes data/handcheck/v2/ (refuses if it exists)
    python scripts/handcheck_score.py      # after filling the CSV: accuracy -> EXTRACTION_REPORT

Sampling (fixed seed, so the pack is reproducible): 8 cells per year 2022-2026, diseases cycled
within a year, never two cells from the same issue, only validated RDHS rows (not the national
row), each cell either the weekly (A) or the cumulative (B) column.

Each image NN.png is the Table 1 page rendered upright and cropped to two strips: the column
header (disease name and A/B) and the cell's row with one row of context above and below. The
cell is boxed in red, its column header in blue, and a caption names the cell and the extracted
value. Fill `verified` (Y/N) and, if N, `actual_value` with what the page shows.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pandas as pd
import pdfplumber
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from radar_lk import CLEAN_DIR, RAW_DIR, load_config  # noqa: E402
from radar_lk.ingest.parse_wer import (  # noqa: E402
    LABEL_MARGIN,
    find_table_page,
    norm,
    read_header,
    read_lines,
    tokens,
)

OUT = REPO / "data" / "handcheck" / "v2"
SEED = 20261103
N = 40
YEARS = [2022, 2023, 2024, 2025, 2026]
RES = 150  # dpi
SC = RES / 72.0


def sample(df: pd.DataFrame, rng: random.Random) -> pd.DataFrame:
    per_year = {y: N // len(YEARS) + (1 if i < N % len(YEARS) else 0) for i, y in enumerate(YEARS)}
    used_issues: set[str] = set()
    picks = []
    for y in YEARS:
        d = df[df["epi_year"] == y]
        diseases = sorted(d["disease"].unique())
        rng.shuffle(diseases)
        k = 0
        while sum(p["epi_year"] == y for p in picks) < per_year[y]:
            dis = diseases[k % len(diseases)]
            k += 1
            cand = d[(d["disease"] == dis) & ~d["source_file"].isin(used_issues)]
            if cand.empty:
                continue
            row = cand.iloc[rng.randrange(len(cand))]
            used_issues.add(row["source_file"])
            col = "A" if rng.random() < 0.5 else "B"
            picks.append(
                {
                    "epi_year": y,
                    "issue": row["source_issue"],
                    "source_file": row["source_file"],
                    "district": row["area"],
                    "disease": dis,
                    "column": col,
                    "extracted_value": int(row["cases"] if col == "A" else row["cum_cases"]),
                }
            )
    rng.shuffle(picks)
    out = pd.DataFrame(picks)
    out.insert(0, "no", range(1, len(out) + 1))
    return out


def locate(page, cfg, district, disease, column):
    """Boxes (pdf coords: x0, top, x1, bottom) of the cell, its header labels, and the strips."""
    alias = {norm(a): d["id"] for d in cfg["diseases"] for a in d["aliases"]}
    order = [d["id"] for d in cfg["diseases"]]
    units = {norm(u): u for u in cfg["rdhs_units"]}
    for v, t in (cfg.get("rdhs_label_variants") or {}).items():
        units[norm(v)] = t
    H = float(page.height)
    lines = read_lines(page)
    layout, sub = read_header(lines, alias, order)
    ncol = len(layout.label_c)
    label_end = layout.label_c[0] - LABEL_MARGIN
    k = layout.diseases.index(disease) * 2 + (0 if column == "A" else 1)
    rows = [ln for ln in lines[sub + 1 :] if ln]
    for i, ln in enumerate(rows):
        toks = tokens(ln)
        label = norm("".join(t.text for t in toks if t.c < label_end))
        nums = [t for t in toks if t.c >= label_end]
        if units.get(label) != district:
            continue
        if len(nums) != ncol:
            return None  # a blank cell in this row: positions are not one-to-one, skip
        t = nums[k]
        x0, x1 = min(c["x0"] for c in ln), max(c["x1"] for c in ln)
        cell = (x0 - 1, H - t.e - 2, x1 + 1, H - t.s + 2)
        sub_chars = [c for c in lines[sub] if c["text"].strip()]
        hdr = sub_chars[k]
        head_box = (hdr["x0"] - 1, hdr["top"] - 2, hdr["x1"] + 1, hdr["bottom"] + 2)
        head_lines = lines[sub - 1] + lines[sub]
        prev_ln = rows[i - 1] if i > 0 else ln
        next_ln = rows[i + 1] if i + 1 < len(rows) else ln
        return {
            "cell": cell,
            "head": head_box,
            "head_strip": (
                min(c["x0"] for c in head_lines) - 4,
                max(c["x1"] for c in head_lines) + 4,
            ),
            "row_strip": (min(c["x0"] for c in prev_ln) - 3, max(c["x1"] for c in next_ln) + 3),
            "reading_end": t.e,
        }
    return None


def render(page, boxes, caption: str) -> Image.Image:
    img = page.to_image(resolution=RES)
    img.draw_rect(boxes["cell"], stroke="red", stroke_width=3, fill=None)
    img.draw_rect(boxes["head"], stroke="blue", stroke_width=2, fill=None)
    up = img.annotated.convert("RGB").rotate(-90, expand=True)  # rotated table -> upright
    # upright coords: x = (page height - top) * SC (reading direction), y = page x * SC (rows)
    x_right = min(up.width, int((boxes["reading_end"] + 70) * SC))
    hs = up.crop((0, int(boxes["head_strip"][0] * SC), x_right, int(boxes["head_strip"][1] * SC)))
    rs = up.crop((0, int(boxes["row_strip"][0] * SC), x_right, int(boxes["row_strip"][1] * SC)))
    cap_h, gap = 34, 8
    out = Image.new("RGB", (x_right, cap_h + hs.height + gap + rs.height), "white")
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    draw.text((8, 7), caption, fill="black", font=font)
    out.paste(hs, (0, cap_h))
    draw.line((0, cap_h + hs.height + gap // 2, x_right, cap_h + hs.height + gap // 2), fill="grey")
    out.paste(rs, (0, cap_h + hs.height + gap))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.parse_args()
    if OUT.exists():
        raise SystemExit(f"{OUT} already exists; the pack is never overwritten. Use a new folder.")
    clean = pd.read_parquet(CLEAN_DIR / "wer.parquet")
    df = clean[(clean["area_level"] == "rdhs") & clean["validated"]]
    cfg = load_config()
    rng = random.Random(SEED)
    # draw until every sampled cell can be located one-to-one (rows with a blank cell are skipped)
    cells = None
    for _ in range(20):
        cand = sample(df, rng)
        ok = True
        located = {}
        for _, c in cand.iterrows():
            with pdfplumber.open(RAW_DIR / c["source_file"]) as pdf:
                page = pdf.pages[find_table_page(pdf)[0]]
                b = locate(page, cfg, c["district"], c["disease"], c["column"])
            if b is None:
                ok = False
                break
            located[c["no"]] = b
        if ok:
            cells = cand
            break
    if cells is None:
        raise SystemExit("could not draw 40 locatable cells")
    OUT.mkdir(parents=True)
    rows = []
    for _, c in cells.iterrows():
        kind = "A (weekly)" if c["column"] == "A" else "B (cumulative)"
        caption = (
            f"#{c['no']:02d} | {c['issue']} | {c['district']} | {c['disease']} | {kind} | "
            f"extracted = {c['extracted_value']}"
        )
        with pdfplumber.open(RAW_DIR / c["source_file"]) as pdf:
            page = pdf.pages[find_table_page(pdf)[0]]
            render(page, located[c["no"]], caption).save(OUT / f"{c['no']:02d}.png")
        rows.append(
            {
                "no": c["no"],
                "issue": c["issue"],
                "district": c["district"],
                "disease": c["disease"],
                "column": c["column"],
                "extracted_value": c["extracted_value"],
                "image": f"{c['no']:02d}.png",
                "verified": "",
                "actual_value": "",
                "notes": "",
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "handcheck.csv", index=False)
    print(f"wrote {len(rows)} cells to {OUT}")
    print(cells.groupby("epi_year").size().to_string())
    print(
        "distinct issues:",
        cells["source_file"].nunique(),
        "| diseases:",
        cells["disease"].nunique(),
    )


if __name__ == "__main__":
    main()
