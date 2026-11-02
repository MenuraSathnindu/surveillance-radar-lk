"""Parse NDCU "Weekly Dengue Update" PDFs. Extracts only:

* the reporting week (title "Week 43 (19th - 25th October 2026)", checked like the WER weeks),
* the high-risk MOH areas of Table 2, each with the district heading it sits under, and
* the district weekly counts of Table 1 (checked against the printed Total row).

Nothing else is read. Self-checks per issue: the number of parsed high-risk areas must equal the
number the issue states in its own text ("44 Medical Officer of Health (MOH) areas were identified
as high-risk"), every area must sit under a district heading, and the district counts must add to
the printed total. An issue that fails a check is logged, not guessed.

    python -m radar_lk.ingest.parse_ndcu                   # parse, write clean tables + report
    python -m radar_lk.ingest.parse_ndcu --seed-crosswalk  # append names found to moh_crosswalk.csv
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pdfplumber

from radar_lk import CLEAN_DIR, REPO_ROOT, REVIEW_DIR, load_config
from radar_lk.harmonise.epiweek import block_from_range
from radar_lk.ingest.parse_wer import ParseError, check_week, norm, parse_week

RAW = REPO_ROOT / "data" / "raw" / "ndcu_weekly"
CROSSWALK = REPO_ROOT / "config" / "moh_crosswalk.csv"
CROSSWALK_FIELDS = ["moh_name_raw", "moh_name", "district", "ds_division", "source"]
TITLE = re.compile(r"Week\s*(\d+)\s*\(([^)]*\d{4}[^)]*)\)")
STATED = re.compile(
    r"(\d+)\s+Medical\s+Officer\s+of\s+Health\s+\(MOH\)\s+areas\s+were\s+identified\s+as\s+high-?risk",
    re.I,
)
NUM = re.compile(
    r"^\d+[*\]]?$"
)  # a figure, optionally starred (revised) or with a stray ] (Week 31)


def _int(text: str) -> int:
    return int(re.sub(r"\D", "", text))


LINE_TOL = 2.5


@dataclass
class NdcuIssue:
    file: str
    status: str  # ok | failed
    reason: str = ""
    meta: dict = field(default_factory=dict)
    flags: list[dict] = field(default_factory=list)
    districts: list[dict] = field(default_factory=list)


def _lines(words: list[dict]) -> list[list[dict]]:
    out: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if out and abs(out[-1][0]["top"] - w["top"]) <= LINE_TOL:
            out[-1].append(w)
        else:
            out.append([w])
    return [sorted(ln, key=lambda w: w["x0"]) for ln in out]


def _text(ln: list[dict]) -> str:
    return " ".join(w["text"] for w in ln).strip()


def district_of_heading(text: str, units: dict[str, str]) -> str | None:
    """'Colombo District' / 'Kalmunai RDHS' -> the canonical RDHS name, or None."""
    m = re.match(r"^(.*?)\s*\b(District|Distrcit|RDHS|Region)\b\s*$", text.strip())
    if not m:
        return None
    return units.get(norm(m.group(1)))


def _units(cfg: dict) -> dict[str, str]:
    units = {norm(u): u for u in cfg["rdhs_units"]}
    for v, t in (cfg.get("rdhs_label_variants") or {}).items():
        units[norm(v)] = t
    return units


# ------------------------------------------------------------------ Table 2: high-risk MOH areas


def _is_heading_line(t: str) -> bool:
    return bool(re.search(r"\b(District|Distrcit|RDHS|Region)\s*$", t.strip()))


def _band_entries(bw: list[dict], units, district, other: list[str]):
    """Entries of one sub-table, in reading order, plus the district heading in force at its end.

    Returns (entries, district) with entries = [(district, name, [numeric words])].
    """
    lines = []
    seen = False
    for ln in _lines(bw):
        toks = [w["text"] for w in ln]
        t = " ".join(toks)
        trailing = []
        for w in reversed(ln):
            if NUM.match(w["text"]):
                trailing.insert(0, w)
            else:
                break
        name = " ".join(w["text"] for w in ln[: len(ln) - len(trailing)]).strip()
        if not seen and (re.match(r"^(Table|Cases|reported|Week|MOH|Wee|k\b)", t) or not name):
            continue  # column-header rows above the first heading/entry
        seen = True
        if (
            lines
            and not lines[-1]["nums"]
            and re.fullmatch(r"(District|Distrcit|RDHS)", t)
            and not _is_heading_line(lines[-1]["text"])
        ):
            # heading wrapped onto two lines: 'Nuwara Eliya' / 'District'
            lines[-1]["text"] = f"{lines[-1]['text']} {t}"
            lines[-1]["name"] = lines[-1]["text"]
            continue
        lines.append({"name": name, "nums": trailing, "text": t})
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        name, nums, t = ln["name"], ln["nums"], ln["text"]
        if not nums:
            if _is_heading_line(t):
                d = district_of_heading(t, units)
                if d is None:
                    raise ParseError("district_heading_unmapped", repr(t))
                district = d
            elif t.upper() == t:  # province heading, or the wrapped second line of one
                pass
            elif i + 1 < len(lines) and not lines[i + 1]["name"] and lines[i + 1]["nums"]:
                # name on the line above its (vertically centred) numbers, maybe continued below
                nm = name
                nums = lines[i + 1]["nums"]
                i += 1
                if (
                    i + 1 < len(lines)
                    and lines[i + 1]["name"]
                    and not lines[i + 1]["nums"]
                    and not _is_heading_line(lines[i + 1]["text"])
                    and lines[i + 1]["text"].upper() != lines[i + 1]["text"]
                ):
                    nm = f"{nm} {lines[i + 1]['name']}"
                    i += 1
                if district is None:
                    raise ParseError(
                        "no_district_context", f"entry {nm!r} before any district heading"
                    )
                out.append((district, nm, nums))
            else:
                other.append(t)  # sub-heading such as 'CMC' or 'NIHS'
        elif name:
            if district is None:
                raise ParseError("no_district_context", f"entry {t!r} before any district heading")
            nm = name
            if (
                nm.endswith("-")
                and i + 1 < len(lines)
                and lines[i + 1]["name"]
                and not lines[i + 1]["nums"]
            ):
                nm = nm + lines[i + 1]["name"]  # 'Nuwaragam-' + 'Palatha'
                i += 1
            out.append((district, nm, nums))
        else:
            raise ParseError("orphan_numbers", f"numbers without a name: {t!r}")
        i += 1
    return out, district


def _table2(page, units) -> tuple[list[dict], dict]:
    words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
    lines = _lines(words)
    start = end = None
    for ln in lines:
        t = _text(ln)
        if start is None and re.match(r"^Table\s*2\b", t):
            start = (
                max(w["bottom"] for w in ln) + 1
            )  # below the title, which can overflow its column
        elif start is not None and re.match(r"^Table\s*3\b", t):
            end = ln[0]["top"]
            break
    if start is None:
        raise ParseError("table2_missing", "no 'Table 2' title on the page")
    end = end if end is not None else float(page.height)
    region = [w for w in words if start <= w["top"] < end - 1]
    heads = sorted(
        (
            w
            for w in region
            if w["text"] == "MOH"
            and any(
                a["text"] == "Area" and abs(a["top"] - w["top"]) < 2 and 0 < a["x0"] - w["x1"] < 8
                for a in region
            )
        ),
        key=lambda w: w["x0"],
    )
    if not heads:
        raise ParseError("table2_header", "no 'MOH Area' column headers")
    # each sub-table starts ~22 pt left of its 'MOH' header word
    bounds = [h["x0"] - 22 for h in heads[1:]]
    flags: list[dict] = []
    other: list[str] = []
    district = None
    for band in range(len(heads)):
        lo = bounds[band - 1] if band else -1.0
        hi = bounds[band] if band < len(bounds) else 1e9
        bw = [w for w in region if lo <= (w["x0"] + w["x1"]) / 2 < hi]
        entries, district = _band_entries(bw, units, district, other)
        two = [n for _, _, n in entries if len(n) >= 2]
        if two:
            c_prev = sorted((n[-2]["x0"] + n[-2]["x1"]) / 2 for n in two)[len(two) // 2]
            c_cur = sorted((n[-1]["x0"] + n[-1]["x1"]) / 2 for n in two)[len(two) // 2]
        for d, name, nums in entries:
            vals = [_int(w["text"]) for w in nums[-2:]]
            if len(nums) == 1:  # one cell is blank: decide which by position
                x = (nums[0]["x0"] + nums[0]["x1"]) / 2
                if not two:
                    raise ParseError("blank_cell", f"{name!r}: one number and no reference columns")
                vals = [vals[0], None] if abs(x - c_prev) < abs(x - c_cur) else [None, vals[0]]
            flags.append(
                {
                    "district": d,
                    "moh_raw": name.rstrip("*").strip(),
                    "cases_prev_week": vals[0],
                    "cases_week": vals[1],
                    "band": band,
                }
            )
    return flags, {"other_headings": sorted(set(other)), "n_bands": len(heads)}


# ------------------------------------------------------------------ Table 1: district counts


def _table1(page, units) -> tuple[list[dict], dict]:
    words = page.extract_words(x_tolerance=1.5, y_tolerance=2)
    hdr = [w for w in words if w["text"].startswith("District/")]
    tot = [w for w in words if w["text"].startswith("Total")]
    if not hdr or not tot:
        raise ParseError("table1_missing", "no 'District/' header or 'Total' row")
    x0 = hdr[0]["x0"] - 4
    y0 = hdr[0]["top"] - 12
    y1 = max(t["bottom"] for t in tot if t["x0"] >= x0) + 3
    reg = [w for w in words if w["x0"] >= x0 and y0 <= w["top"] <= y1]
    rows, total = [], None
    for ln in _lines(reg):
        toks = [w["text"] for w in ln]
        if toks and toks[0].startswith("Total"):
            # the total row's cells sit a few pt off the line (e.g. a wrapped figure): take every
            # numeric word within 7 pt of the label, left to right
            top = ln[0]["top"]
            near = sorted(
                (w for w in reg if abs(w["top"] - top) <= 7 and w["x0"] > ln[0]["x1"] - 1),
                key=lambda w: w["x0"],
            )
            vals = [w["text"] for w in near if NUM.match(w["text"]) or w["text"].lower() == "nil"]
            if len(vals) != 6:
                raise ParseError("table1_total", f"total row has {len(vals)} figures: {vals}")
            total = [0 if v.lower() == "nil" else _int(v) for v in vals]
            continue
        vals = []
        for t in reversed(toks):
            if NUM.match(t) or t.lower() == "nil":
                vals.append(t)
            else:
                break
        if len(vals) < 6:
            continue
        vals = list(reversed(vals))[-6:]
        name = " ".join(toks[: len(toks) - 6]).strip()
        nums = [0 if v.lower() == "nil" else _int(v) for v in vals]
        revised = [v.endswith("*") for v in vals]
        d = units.get(norm(name))
        if d is None:
            raise ParseError("district_unmapped", repr(name))
        rows.append(
            {
                "district": d,
                "cases_2025_prev_week": nums[0],
                "cases_2025_week": nums[1],
                "cases_prev_week": nums[2],
                "cases_week": nums[3],
                "cum_2025": nums[4],
                "cum_2026": nums[5],
                "prev_week_revised": revised[2],
                "week_revised": revised[3],
            }
        )
    if total is None:
        raise ParseError("table1_total", "no Total row")
    return rows, {"total": total}


# ------------------------------------------------------------------ one issue


def parse_issue(path: str | Path, cfg: dict | None = None) -> NdcuIssue:
    path = Path(path)
    cfg = cfg or load_config()
    units = _units(cfg)
    res = NdcuIssue(file=path.name, status="failed")
    try:
        with pdfplumber.open(path) as pdf:
            p1 = pdf.pages[0]
            m = TITLE.search(p1.extract_text() or "")
            if not m:
                raise ParseError("title", "no 'Week N (dates)' title on page 1")
            printed = int(m.group(1))
            start, end = parse_week(m.group(2))
            check_week(start, end, printed, cfg["wer_calendar"])
            epi_year, epi_week = block_from_range(start, end)
            left = [w for w in p1.extract_words(x_tolerance=1.5) if w["x1"] < 318]
            narrative = " ".join(_text(ln) for ln in _lines(left))
            sm = STATED.search(narrative)
            stated = int(sm.group(1)) if sm else None
            d_rows, d_meta = _table1(p1, units)
            p2 = next(
                (
                    p
                    for p in pdf.pages
                    if re.search(r"Table\s*2\s*:\s*High", p.extract_text() or "", re.I)
                ),
                None,
            )
            if p2 is None:
                raise ParseError("table2_missing", "no page with 'Table 2: High risk MOH areas'")
            f_rows, f_meta = _table2(p2, units)
    except ParseError as e:
        res.reason = f"{e.code}: {e.detail}" if e.detail else e.code
        res.meta["error_code"] = e.code
        return res
    except Exception as e:  # noqa: BLE001 - reported, never silent
        res.reason = f"exception: {type(e).__name__}: {e}"
        res.meta["error_code"] = "exception"
        return res

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = {
        "week_start": start,
        "week_end": end,
        "epi_year": epi_year,
        "epi_week": epi_week,
        "source_file": f"ndcu_weekly/{path.name}",
        "extracted_at": now,
    }
    res.flags = [{**base, **r} for r in f_rows]
    res.districts = [{**base, **r} for r in d_rows]
    sums_ok = sum(r["cases_week"] for r in d_rows) == d_meta["total"][3]
    res.status = "ok"
    res.meta.update(
        epi_year=epi_year,
        epi_week=epi_week,
        start=start,
        end=end,
        printed_week=printed,
        stated_high_risk=stated,
        parsed_high_risk=len(f_rows),
        list_parseable=stated is not None and stated == len(f_rows),
        n_districts=len(d_rows),
        district_sum_ok=sums_ok,
        **f_meta,
    )
    return res


def parse_all(paths: list[Path]) -> list[NdcuIssue]:
    return [parse_issue(p) for p in paths]


# ------------------------------------------------------------------ crosswalk


def load_crosswalk() -> dict[tuple[str, str], str]:
    out = {}
    if CROSSWALK.exists():
        with open(CROSSWALK, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[(r["district"], norm(r["moh_name_raw"]))] = r["moh_name"]
    return out


def tidy_name(raw: str) -> str:
    """Spelling normalisation only: single spaces, a space before '(' ."""
    return re.sub(r"\s+", " ", re.sub(r"(?<=\S)\(", " (", raw)).strip()


def map_flags(flags: pd.DataFrame) -> pd.DataFrame:
    cw = load_crosswalk()
    flags = flags.copy()
    flags["moh_name"] = [
        cw.get((d, norm(r))) for d, r in zip(flags["district"], flags["moh_raw"], strict=True)
    ]
    return flags


def seed_crosswalk(flags: pd.DataFrame) -> int:
    """Append every (district, raw name) not yet in the crosswalk, spelled as printed (tidied).

    This is seeding from NDCU's own spellings: it makes names consistent across weeks but is NOT an
    independent check against an official MOH list (see docs/NDCU_FEASIBILITY.md)."""
    have = load_crosswalk()
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for d, r in zip(flags["district"], flags["moh_raw"], strict=True):
        counts.setdefault((d, norm(r)), {}).setdefault(r, 0)
        counts[(d, norm(r))][r] += 1
    # a name that appears under more than one district is a conflict: not mapped, not guessed
    districts_of: dict[str, set[str]] = {}
    for d, k in counts:
        districts_of.setdefault(k, set()).add(d)
    new = {}
    for (d, k), spellings in counts.items():
        if (d, k) in have or len(districts_of[k]) > 1:
            continue
        commonest = max(spellings, key=lambda s: (spellings[s], s))
        new[(d, k)] = (commonest, tidy_name(commonest), d)
    new_file = not CROSSWALK.exists() or CROSSWALK.stat().st_size == 0
    existing = CROSSWALK.read_text(encoding="utf-8") if not new_file else ""
    rows = list(csv.DictReader(existing.splitlines())) if existing else []
    with open(CROSSWALK, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CROSSWALK_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(
                {**{k: "" for k in CROSSWALK_FIELDS}, **r, "source": r.get("source") or "manual"}
            )
        for raw, name, d in sorted(new.values(), key=lambda t: (t[2], t[1])):
            w.writerow(
                {
                    "moh_name_raw": raw,
                    "moh_name": name,
                    "district": d,
                    "ds_division": "",
                    "source": "ndcu_seed",
                }
            )
    return len(new)


# ------------------------------------------------------------------ run


def run(seed: bool = False) -> list[NdcuIssue]:
    paths = sorted(RAW.glob("*.pdf"))
    results = parse_all(paths)
    ok = [r for r in results if r.status == "ok"]
    print(f"{len(paths)} PDFs: ok {len(ok)}, failed {len(results) - len(ok)}")
    for r in results:
        if r.status != "ok":
            print(f"  [failed] {r.file}: {r.reason}")
    flags = pd.DataFrame([f for r in ok for f in r.flags])
    dist = pd.DataFrame([d for r in ok for d in r.districts])
    if seed and not flags.empty:
        print(f"crosswalk: {seed_crosswalk(flags)} names appended")
    if not flags.empty:
        flags = map_flags(flags)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    if not flags.empty:
        flags.to_parquet(CLEAN_DIR / "ndcu_flags.parquet", index=False)
    if not dist.empty:
        dist.to_parquet(CLEAN_DIR / "ndcu_districts.parquet", index=False)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"file": r.file, "status": r.status, "reason": r.reason}
            for r in results
            if r.status != "ok"
        ]
    ).to_csv(REVIEW_DIR / "ndcu_issues.csv", index=False)
    from radar_lk.ingest.report_ndcu import write_feasibility

    write_feasibility(results, flags, dist)
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--seed-crosswalk", action="store_true")
    a = ap.parse_args()
    run(a.seed_crosswalk)


if __name__ == "__main__":
    main()
