"""Parse WER Table 1 (RDHS x notifiable disease) from the rotated page into tidy rows.

The table sits on a page whose text is rotated 90 degrees, so ``extract_text`` is useless. We read
pdfplumber characters, transform them into reading order (reading position = page height - char
bottom, text lines are clusters of equal x0), and take the layout from the printed header.

Rules (see docs/LAYOUTS.md and CLAUDE.md):
- Table 1 is found by its content (title + RDHS/WRCD header), not by page number. The 2026 page-2
  "Table 1 : Water Quality Surveillance" is rejected explicitly.
- The reporting week comes from the week text printed in the table title, never from the listing.
- Unknown header text, an unmapped district, a wrong token count or an inconsistent week text is a
  hard failure for that issue. Nothing is guessed.
- No PDF page contributes numbers unless the whole issue parsed.

Usage:
    python -m radar_lk.ingest.parse_wer   # data/raw/wer/*.pdf -> data/clean, data/review_queue
"""

from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pdfplumber

from radar_lk import RAW_DIR, load_config
from radar_lk.harmonise.epiweek import block_from_range
from radar_lk.ingest.validate import NATIONAL

GAP = 1.5  # pt; larger gap between consecutive characters of a line starts a new token
RUN_GAP = 5.0  # pt; header characters further apart than this belong to different words/cells
LINE_TOL = 3.0  # pt; characters whose x0 differ by less than this are on the same text line
LABEL_MARGIN = 10.0  # pt; tokens centred left of (first column label - this) are the row label
ROW_ALIGN_TOL = 4.0  # pt; max label-to-numbers offset across the line (observed max 2.0)
ROW_MIN_GAP = 8.0  # pt; min distance between consecutive rows (observed min 12.5)
PCT = re.compile(r"\d+(?:\.\d+)?%?")  # T*/C** cells: "97", "8%", "5.5"
MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}

TITLE = re.compile(
    r"Table\s*1\s*:\s*(?P<name>[^()]{0,90}?)\s*reported\s+by\s+Medical\s+Officers\s+of\s+Health"
    r"\s*(?P<week>[^()]*?)\(\s*(?P<wk>\d+)\s*(?:st|nd|rd|th)\s*Week\s*\)",
    re.I,
)
DECOY = re.compile(r"Table\s*1\s*:?\s*Water\s*Quality", re.I)
RANGE = re.compile(
    r"(?P<d1>\d{1,2})\s*(?:st|nd|rd|th)?\s*(?P<m1>[A-Za-z]{3,9})?\s*(?P<y1>\d{4})?\s*[–—-]\s*"
    r"(?P<d2>\d{1,2})\s*(?:st|nd|rd|th)?\s*(?P<m2>[A-Za-z]{3,9})\s*(?P<y2>\d{4})"
)
VOLNO = re.compile(r"Vol\.?\s*(\d+)\s*No\s*\.?\s*(\d+)", re.I)


class ParseError(Exception):
    """Hard failure for one issue; ``code`` is a short machine-readable reason."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


@dataclass
class IssueResult:
    file: str
    status: str  # ok | no_table | failed
    reason: str = ""
    source_issue: str = ""
    page: int | None = None
    rows: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# ---------------------------------------------------------------- page reading


def _rot(c) -> bool:
    m = c["matrix"]
    return abs(m[0]) < 0.1 and m[1] > 0.9


def _upright(c) -> bool:
    m = c["matrix"]
    return m[0] > 0.9 and abs(m[1]) < 0.1


def upright_text(page) -> str:
    return re.sub(r"\s+", " ", "".join(c["text"] for c in page.chars if _upright(c)))


@dataclass
class Tok:
    text: str
    s: float  # reading start
    e: float  # reading end

    @property
    def c(self) -> float:
        return (self.s + self.e) / 2


def read_lines(page) -> list[list[dict]]:
    """Rotated characters, grouped into text lines (sorted by x0), each in reading order."""
    H = float(page.height)
    chars = sorted((c for c in page.chars if _rot(c)), key=lambda c: c["x0"])
    if len(chars) < 500:
        clockwise = sum(1 for c in page.chars if c["matrix"][1] < -0.9)
        raise ParseError(
            "orientation", f"{len(chars)} rotated chars; {clockwise} rotated the other way"
        )
    lines: list[list[dict]] = []
    anchor = None
    for c in chars:
        if anchor is None or c["x0"] - anchor > LINE_TOL:
            lines.append([])
            anchor = c["x0"]
        lines[-1].append(c)
    for ln in lines:
        ln.sort(key=lambda c: H - c["bottom"])
        for c in ln:
            c["_s"], c["_e"] = H - c["bottom"], H - c["top"]
    return lines


def tokens(line: list[dict]) -> list[Tok]:
    out: list[Tok] = []
    cur: list[dict] = []

    def flush():
        if cur:
            out.append(Tok("".join(c["text"] for c in cur), cur[0]["_s"], cur[-1]["_e"]))
            cur.clear()

    last_e = None
    for c in line:
        if not c["text"].strip():
            flush()
            last_e = None
            continue
        if last_e is not None and c["_s"] - last_e > GAP:
            flush()
        cur.append(c)
        last_e = c["_e"]
    flush()
    return out


def line_text(line: list[dict]) -> str:
    out, last_e = "", None
    for c in line:
        if last_e is not None and c["_s"] - last_e > GAP and not out.endswith(" "):
            out += " "
        out += c["text"]
        last_e = c["_e"]
    return re.sub(r"\s+", " ", out).strip()


# ---------------------------------------------------------------- locating Table 1


def find_table_page(pdf) -> tuple[int, re.Match, str] | None:
    """(page index, title match, upright text) of the page holding Table 1, by content.

    Page order is only a speed hint; any page may match. Needs the Table 1 title naming the
    Medical Officers of Health and, on the same page, rotated text (checked later via the header).
    """
    order = [2, 1, 0] + list(range(3, len(pdf.pages)))
    for i in [i for i in order if i < len(pdf.pages)]:
        text = upright_text(pdf.pages[i])
        if DECOY.search(text) and not TITLE.search(text):
            continue  # e.g. 2026 page 2 "Table 1 : Water Quality Surveillance"
        m = TITLE.search(text)
        if m and "water" not in m.group("name").lower():
            return i, m, text
    return None


def parse_week(week_text: str) -> tuple[date, date]:
    m = RANGE.search(week_text)
    if not m:
        raise ParseError("week_text", repr(week_text))
    mon = lambda s: MONTHS.get(s[:3].lower())  # noqa: E731
    m2, y2 = mon(m["m2"]), int(m["y2"])
    if m2 is None:
        raise ParseError("week_text_month", repr(week_text))
    try:
        end = date(y2, m2, int(m["d2"]))
    except ValueError as e:
        raise ParseError("week_text_date", f"{week_text!r}: {e}") from e
    start = end - timedelta(days=6)
    # the printed start must agree with end - 6 days; a start month/year is optional in print
    if start.day != int(m["d1"]):
        raise ParseError("week_text_inconsistent", f"{week_text!r}: start day {m['d1']} != {start}")
    if m["m1"] and mon(m["m1"]) != start.month:
        raise ParseError("week_text_inconsistent", f"{week_text!r}: start month != {start}")
    if m["y1"] and int(m["y1"]) != start.year:
        raise ParseError("week_text_inconsistent", f"{week_text!r}: start year != {start}")
    return start, end


def check_week(start: date, end: date, printed: int, cal: dict) -> None:
    """Sanity-check the week read from the table title; a source typo must fail, not mis-file.

    1. The block must start on the weekday the WER used at that time (Sat, then Mon).
    2. The printed "(Nth Week)" must equal the canonical week (plus WER's 2021 offset).
    A wrong month or year in the printed range still forms a valid 7-day block, so only these
    cross-checks can catch it. Both checks also apply to user-approved overrides.
    """
    monday_from = cal.get("monday_weeks_from")
    expected = 0 if monday_from and start >= monday_from else 5
    if start.weekday() != expected:
        raise ParseError(
            "week_weekday",
            f"{start:%a %Y-%m-%d} to {end:%Y-%m-%d} starts on {start:%A}, WER weeks then started "
            f"on "
            f"{'Monday' if expected == 0 else 'Saturday'}",
        )
    epi_year, epi_week = block_from_range(start, end)
    offset = (cal.get("printed_week_offset") or {}).get(epi_year, 0)
    if printed != epi_week + offset:
        raise ParseError(
            "week_number_mismatch",
            f"printed week {printed} != canonical {epi_year}-W{epi_week:02d} (+{offset}) for "
            f"{start}..{end}",
        )


# ---------------------------------------------------------------- header + rows


@dataclass
class Layout:
    diseases: list[str]  # config ids in column order
    header_names: list[str]  # header text as printed, per disease
    label_c: list[float]  # reading-centre of each numeric column label (A,B,...,T*,C**)


def _centre(c) -> float:
    return (c["_s"] + c["_e"]) / 2


def read_header(
    lines: list[list[dict]], alias_to_id: dict[str, str], order: list[str]
) -> tuple[Layout, int]:
    """Locate the RDHS/WRCD header and its A/B/T*/C** sub-header; return layout + sub-line index."""

    def is_header(ln) -> bool:
        toks = tokens(ln)
        return (
            bool(toks)
            and norm(toks[0].text) == "rdhs"
            and any(norm(t.text) == "wrcd" for t in toks)
        )

    i = next((k for k, ln in enumerate(lines) if is_header(ln)), None)
    if i is None:
        raise ParseError("header_missing", "no line starting RDHS and containing WRCD")
    head, sub = lines[i], lines[i + 1] if i + 1 < len(lines) else []
    sub_chars = [c for c in sub if c["text"].strip()]
    s = "".join(c["text"] for c in sub_chars)
    if not re.fullmatch(r"(?:AB)+T\*C\*\*", s):
        raise ParseError("subheader", f"unexpected sub-header {s!r}")
    n = (len(sub_chars) - 5) // 2
    cen = [_centre(c) for c in sub_chars]
    label_c = cen[: 2 * n] + [sum(cen[2 * n : 2 * n + 2]) / 2, sum(cen[2 * n + 2 :]) / 3]
    # cell boundaries between neighbouring disease pairs; WRCD starts after the last B
    bounds = [(cen[2 * k + 1] + cen[2 * k + 2]) / 2 for k in range(n - 1)]
    wrcd_from = (cen[2 * n - 1] + cen[2 * n]) / 2
    toks = tokens(head)
    rdhs_end = toks[0].e
    # Names are left-aligned in some years and centred in others, and can be wider than their
    # cell, so classify whole word-runs (split at gaps > RUN_GAP) by the run's centre, not chars.
    runs: list[list[dict]] = []
    last_e = None
    for c in head:
        if not c["text"].strip() or c["_e"] <= rdhs_end + 0.1:
            continue
        if last_e is None or c["_s"] - last_e > RUN_GAP:
            runs.append([])
        runs[-1].append(c)
        last_e = c["_e"]
    names: list[list[list[dict]]] = [[] for _ in range(n)]
    wrcd: list[dict] = []
    for run in runs:
        x = (run[0]["_s"] + run[-1]["_e"]) / 2
        if x >= wrcd_from:
            wrcd.extend(run)
        else:
            names[sum(1 for b in bounds if x > b)].append(run)
    if norm("".join(c["text"] for c in wrcd)) != "wrcd":
        raise ParseError("header_wrcd", "".join(c["text"] for c in wrcd))
    printed = [" ".join(line_text(r) for r in g) for g in names]
    ids = []
    for p in printed:
        if norm(p) not in alias_to_id:
            raise ParseError("header_unknown", f"unmapped disease header {p!r} in {printed}")
        ids.append(alias_to_id[norm(p)])
    idx = [order.index(d) for d in ids]
    if idx != sorted(set(idx)):
        raise ParseError("header_order", f"{ids}")
    return Layout(ids, printed, label_c), i + 1


def read_rows(lines: list[list[dict]], sub_idx: int, layout: Layout, units: dict[str, str]):
    """Rows after the sub-header, up to and including SRI LANKA.

    Each value token is assigned to the column whose header label centre is nearest. A column
    with no token is a blank cell, a token that is not a number is unreadable; both give None
    (the cell is not guessed). Two tokens in one column is ambiguous and fails the whole issue.
    Disease cells are plain integers; T*/C** may print as ``8%`` or ``5.5`` and become floats.

    Returns [(canonical area, [value or None per column], {"blank": n, "unreadable": n,
    "pct_format": n})].
    """
    ncol = len(layout.label_c)
    label_end = layout.label_c[0] - LABEL_MARGIN
    out = []
    last_x = 0.0
    for ln in lines[sub_idx + 1 :]:
        toks = tokens(ln)
        if not toks:
            continue
        label_toks = [t for t in toks if t.c < label_end]
        nums = [t for t in toks if t.c >= label_end]
        label = "".join(t.text for t in label_toks)
        if not label and not nums:
            continue
        if not label:
            raise ParseError("row_label", f"row without label: {[t.text for t in toks][:6]}")
        if not nums:
            raise ParseError("row_misaligned", f"label {label!r} has no numbers on its text line")
        # the label must sit on the same text line as its numbers (measured: <= 2.0 pt apart in
        # all 244 issues, rows >= 12.5 pt apart), so a label paired with a neighbouring row fails
        lab_x = [c["x0"] for c in ln if c["text"].strip() and (c["_s"] + c["_e"]) / 2 < label_end]
        num_x = [c["x0"] for c in ln if c["text"].strip() and (c["_s"] + c["_e"]) / 2 >= label_end]
        offset = sum(lab_x) / len(lab_x) - sum(num_x) / len(num_x)
        if abs(offset) > ROW_ALIGN_TOL:
            raise ParseError("row_misaligned", f"{label!r} sits {offset:+.1f} pt off its numbers")
        row_x = sum(num_x) / len(num_x)
        if out and row_x - last_x < ROW_MIN_GAP:
            raise ParseError(
                "row_misaligned", f"{label!r} is {row_x - last_x:.1f} pt below the row above"
            )
        last_x = row_x
        nl = norm(label)
        if nl == "srilanka":
            area = NATIONAL
        elif nl in units:
            area = units[nl]
        else:
            raise ParseError("district_unmapped", repr(label))
        cells: list[str | None] = [None] * ncol
        if len(nums) == ncol:
            # one token per column: take them in order (cells are left/right/centre aligned, so
            # token position is not a reliable column key when nothing is missing)
            cells = [t.text for t in nums]
        else:
            # a cell is blank or two cells ran together: fall back to the nearest column label
            for t in nums:
                j = min(range(ncol), key=lambda q: abs(t.c - layout.label_c[q]))
                if cells[j] is not None:
                    raise ParseError(
                        "row_ambiguous",
                        f"{label}: {len(nums)} tokens for {ncol} columns, "
                        f"two in column {j}: {cells[j]!r}, {t.text!r}",
                    )
                cells[j] = t.text
        vals: list[int | float | None] = []
        stats = {"blank": 0, "unreadable": 0, "pct_format": 0}
        for j, txt in enumerate(cells):
            if txt is None:
                stats["blank"] += 1
                vals.append(None)
            elif j >= ncol - 2 and PCT.fullmatch(txt):  # T* and C**
                if not txt.isdigit():
                    stats["pct_format"] += 1
                vals.append(float(txt.rstrip("%")))
            elif j < ncol - 2 and txt.isdigit():
                vals.append(int(txt))
            else:
                stats["unreadable"] += 1
                vals.append(None)
        out.append((area, vals, stats))
        if area == NATIONAL:
            break
    if not out or out[-1][0] != NATIONAL:
        raise ParseError("row_national", "no SRI LANKA row")
    return out


def footnote(lines: list[list[dict]]) -> str:
    """Rotated text after the SRI LANKA row (source line, T*/C** notes)."""
    seen_nat = False
    parts = []
    for ln in lines:
        t = line_text(ln)
        if seen_nat and t:
            parts.append(t)
        if norm(t).startswith("srilanka"):
            seen_nat = True
    return " ".join(parts)


# ---------------------------------------------------------------- one issue


def _issue_label(text: str, p1_text: str, name: str) -> str:
    for t in (text, p1_text):
        m = VOLNO.search(t)
        if m:
            return f"Vol {int(m[1])} No {int(m[2])}"
    m = re.search(r"[Vv]ol[_ ](\d+)[_ ]+[Nn][Oo][_ ]+(\d+)", name)
    return f"Vol {int(m[1])} No {int(m[2])}" if m else ""


def parse_issue(path: str | Path, cfg: dict | None = None) -> IssueResult:
    path = Path(path)
    cfg = cfg or load_config()
    try:
        rel = path.resolve().relative_to(RAW_DIR.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    res = IssueResult(file=rel, status="failed")
    alias_to_id = {norm(a): d["id"] for d in cfg["diseases"] for a in d["aliases"]}
    order = [d["id"] for d in cfg["diseases"]]
    canon = {norm(u): u for u in cfg["rdhs_units"]}
    units = dict(canon)
    for variant, target in cfg.get("rdhs_label_variants", {}).items():
        units[norm(variant)] = target
    # `units` maps any accepted label -> canonical name; row_order compares to canonical list
    units_expected = list(cfg["rdhs_units"])

    try:
        with pdfplumber.open(path) as pdf:
            found = find_table_page(pdf)
            if not found:
                res.status, res.reason = (
                    "no_table",
                    "no page with a Table 1 'Medical Officers of Health' title",
                )
                return res
            pi, title, text = found
            res.page = pi + 1
            p1 = upright_text(pdf.pages[0]) if pi != 0 else text
            res.source_issue = _issue_label(text, p1, path.name)
            cal = cfg.get("wer_calendar", {})
            override = (cal.get("week_overrides") or {}).get(res.file)
            if override:
                start = end = override["start"]  # the printed text is what the override replaces
            else:
                start, end = parse_week(title["week"])
            if override:
                start = override["start"]
                end = start + timedelta(days=6)
                res.meta["week_override"] = f"{override['start']}: {override.get('reason', '')}"
            check_week(start, end, int(title["wk"]), cal)
            epi_year, epi_week = block_from_range(start, end)
            lines = read_lines(pdf.pages[pi])
            layout, sub_idx = read_header(lines, alias_to_id, order)
            rows = read_rows(lines, sub_idx, layout, units)
            # canonical-order check uses canonical names
            names = [a for a, _, _ in rows[:-1]]  # (area, values, stats)
            if names != units_expected:
                raise ParseError("row_order", f"{names}")
            foot = footnote(lines)
    except ParseError as e:
        res.status, res.reason = "failed", f"{e.code}: {e.detail}" if e.detail else e.code
        res.meta["error_code"] = e.code
        return res
    except Exception as e:  # corrupt PDF etc.; reported, never silent
        res.status, res.reason = "failed", f"exception: {type(e).__name__}: {e}"
        res.meta["error_code"] = "exception"
        return res

    n = len(layout.diseases)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cell_stats = {"blank": 0, "unreadable": 0, "pct_format": 0}
    cell_problems: list[str] = []
    for area, vals, stats in rows:
        for k_, v_ in stats.items():
            cell_stats[k_] += v_
        t_pct, c_pct = vals[2 * n], vals[2 * n + 1]
        if t_pct is None or c_pct is None or any(v is None for v in vals[: 2 * n]):
            cell_problems.append(area)
        for k, dis in enumerate(layout.diseases):
            res.rows.append(
                {
                    "week_start": start,
                    "week_end": end,
                    "epi_year": epi_year,
                    "epi_week": epi_week,
                    "area_level": "national" if area == NATIONAL else "rdhs",
                    "area": area,
                    "disease": dis,
                    "cases": vals[2 * k],
                    "cum_cases": vals[2 * k + 1],
                    "completeness_pct": c_pct,
                    "timeliness_pct": t_pct,
                    "source_file": res.file,
                    "source_issue": res.source_issue,
                    "extracted_at": now,
                    "validated": False,
                    "printed_week": int(title["wk"]),
                    "page": res.page,
                }
            )
    res.status = "ok"
    res.meta.update(
        title=title["name"].strip(),
        week_text=re.sub(r"\s+", " ", title["week"]).strip(),
        n_diseases=n,
        diseases=layout.diseases,
        header_names=layout.header_names,
        cell_stats=cell_stats,
        rows_with_cell_problems=cell_problems,
        footnote=foot,
        epi_year=epi_year,
        epi_week=epi_week,
        start=start,
        end=end,
    )
    return res


def _parse_one(path: str) -> IssueResult:  # top-level for multiprocessing
    return parse_issue(path)


def parse_all(paths: list[Path], workers: int = 4) -> list[IssueResult]:
    if workers <= 1:
        return [parse_issue(p) for p in paths]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_parse_one, [str(p) for p in paths], chunksize=4))


def main() -> None:
    from radar_lk.ingest.wer_pipeline import run

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dir", default=str(RAW_DIR / "wer"))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    sys.exit(run(Path(a.dir), a.workers))


if __name__ == "__main__":
    main()
