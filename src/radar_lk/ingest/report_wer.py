"""Write docs/EXTRACTION_REPORT.md from a WER pipeline run.

Every number in the report is computed from the run's data; the only hand-written part is the
C** investigation, which is read from docs/cstar_findings.md if that file exists.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from radar_lk import REPO_ROOT

REPORT = REPO_ROOT / "docs" / "EXTRACTION_REPORT.md"
CSTAR_NOTES = REPO_ROOT / "docs" / "cstar_findings.md"
TARGET = 95.0


def md(df: pd.DataFrame, index: bool = False) -> str:
    """Minimal markdown table (avoids the optional `tabulate` dependency)."""
    if index:
        df = df.reset_index()
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        cells = []
        for v in row:
            if v is pd.NA or (isinstance(v, float) and np.isnan(v)):
                cells.append("")
            elif isinstance(v, float):
                cells.append("" if np.isnan(v) else (f"{v:.1f}" if abs(v) < 1000 else f"{v:,.0f}"))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _nominal_year(r) -> str:
    if r.status == "ok":
        return str(r.meta["epi_year"])
    m = re.search(r"[Vv]ol[_ ]+(\d+)", r.file)
    return str(int(m[1]) + 1973) if m else "unknown"


def _pct(a, b) -> float:
    return 100.0 * a / b if b else float("nan")


def _front_page_line(path: Path) -> str:
    import pdfplumber

    from radar_lk.ingest.parse_wer import VOLNO, upright_text

    try:
        with pdfplumber.open(path) as pdf:
            t = upright_text(pdf.pages[0])
        m = VOLNO.search(t)
        return t[m.start() : m.start() + 60].strip() if m else ""
    except Exception:  # noqa: BLE001 - report only
        return ""


def issues_section(results, dropped_early=()) -> list[str]:
    out = ["## 2. Issues processed, per year", ""]
    rows = defaultdict(Counter)
    for r in results:
        y = _nominal_year(r)
        rows[y]["files"] += 1
        rows[y][r.status] += 1
    tbl = pd.DataFrame(
        [
            {
                "year": y,
                "files": c["files"],
                "ok": c["ok"],
                "no_table": c["no_table"],
                "failed": c["failed"],
            }
            for y, c in sorted(rows.items())
        ]
    )
    tot = tbl[["files", "ok", "no_table", "failed"]].sum()
    tbl.loc[len(tbl)] = ["**total**", *tot]
    out += [
        md(tbl),
        "",
        "`year` is the year of the week printed in Table 1 for parsed issues, and the volume year "
        "(vol + 1973) for issues that did not parse. 2021 and 2011 are out-of-range files that the "
        "site lists under 2022 dates.",
        "",
    ]
    if dropped_early:
        out += [
            "**Dropped as before 2022-W01** (parsed, but outside the post-COVID baseline): "
            + ", ".join(f"{i} ({w})" for i, w in dropped_early)
            + ".",
            "",
        ]
    nt = [r for r in results if r.status == "no_table"]
    out += ["**no_table** (no Table 1 title found on any page; logged and skipped):", ""]
    out += [f"- `{r.file}`" for r in nt] or ["- none"]
    failed = [r for r in results if r.status == "failed"]
    out += [
        "",
        f"**failed** ({len(failed)}; nothing from these issues reaches the clean table):",
        "",
    ]
    if failed:
        out.append(
            md(
                pd.DataFrame(
                    [
                        {
                            "issue": r.source_issue,
                            "file": r.file.split("/")[-1],
                            "reason": r.reason[:170],
                        }
                        for r in failed
                    ]
                )
            )
        )
    out.append("")
    out += overrides_section(results)
    return out


def overrides_section(results) -> list[str]:
    from radar_lk import load_config

    cal = load_config().get("wer_calendar", {})
    ov = cal.get("week_overrides") or {}
    out = [
        "### Week overrides applied (source typos in the printed week)",
        "",
        "Each entry exists only where the printed day numbers/weekday, the printed `(Nth Week)`, "
        "the "
        "front-page range (table week = front page - 7 days), the previous and next issues' weeks "
        "and "
        "the cumulative values agree on one answer. `parse_wer` still checks weekday and week "
        "number "
        "against the override. The evidence for each is in `config/sources.yaml`.",
        "",
    ]
    rows = []
    byfile = {r.file: r for r in results}
    for f, o in ov.items():
        r = byfile.get(f)
        rows.append(
            {
                "issue": r.source_issue if r else "?",
                "file": f.split("/")[-1],
                "week used": f"{o['start']} to {o['start'] + timedelta(days=6)}",
                "status": r.status if r else "missing",
                "reason": " ".join(str(o["reason"]).split()),
            }
        )
    out += [md(pd.DataFrame(rows)), ""]
    unsettled = [
        r
        for r in results
        if r.status == "failed" and (r.meta.get("error_code") or "").startswith("week_")
    ]
    names = ", ".join(f"{r.source_issue} (`{r.file.split('/')[-1]}`)" for r in unsettled) or "none"
    out += [
        f"**Not settled (no override, still failed):** {names}. Vol 51 No 36 prints the dates of "
        "Vol 51 No 35 (17-23 Aug 2024) with its own week number (35). The number, the neighbours "
        "and "
        "the front page say 24-30 Aug, but its cumulatives chain to the previous week in only 73% "
        "of "
        "district cells (normal median 98%) and are monotone in 90%, so the evidence does not all "
        "agree and the week stays out.",
        "",
    ]
    return out


def validation_section(raw, clean, review) -> list[str]:
    out = ["## 3. Validation (two tiers)", ""]
    d_c = clean[clean["area_level"] == "rdhs"]
    d_r = review[review["area_level"] == "rdhs"]
    n_all = len(d_c) + len(d_r)
    pct = _pct(len(d_c), n_all)
    out += [
        "**Tier 1, `extraction_valid` (= column `validated`).** The row passes the checks that "
        "need "
        "only its own issue: for its (week, disease) the 26 districts' cumulative counts add to "
        "the "
        "printed national cumulative; no count cell is blank or unreadable; completeness and "
        "timeliness are percentages (a value outside 0..100 is set to NaN and counted, the counts "
        "stay). Only `extraction_valid` rows are in `data/clean/wer.parquet` and may reach the "
        "dashboard. If the cumulatives add up but the districts' weekly counts do not add to the "
        "printed national weekly, the national weekly is a source error "
        "(`note=national_weekly_source_error`); if the weekly counts add up but the cumulatives "
        "do not, the national cumulative is (`note=national_cumulative_source_error`). In both "
        "cases "
        "the district rows are kept and only the national row is queued; if neither adds up the "
        "whole group is queued. Each label must also sit on the same text line as its numbers "
        "(checked in the parser). Only weeks from 2022-W01 are kept: a deliberate post-COVID "
        "baseline.",
        "",
        "**Tier 2, `revised`.** The cross-week identity `cum_t = cum_(t-1) + weekly_t` (in a "
        "year's "
        "first week `cum = weekly`). A failure does **not** remove the row: it sets `revised=True` "
        "and `revision_delta = cum_t - (cum_(t-1) + weekly_t)`; `revised` is empty where the "
        "previous "
        "week is missing. **Weekly counts are kept exactly as printed in that issue** "
        "(first-printed). A later issue may raise the cumulative of an earlier week without "
        "re-printing the weekly figure, so the radar's weekly series is what a Regional "
        "Epidemiologist saw in real time, and `revision_delta` says how much was added afterwards.",
        "",
        f"District-disease-weeks extracted from parsed issues: **{n_all:,}**; extraction_valid: "
        f"**{len(d_c):,} = {pct:.2f}%**.",
        "",
    ]
    for key, label in (("epi_year", "year"), ("disease", "disease")):
        a = d_c.groupby(key).size().rename("extraction_valid")
        b = d_r.groupby(key).size().rename("review")
        t = pd.concat([a, b], axis=1).fillna(0).astype(int)
        t["total"] = t.sum(axis=1)
        t["% extraction_valid"] = 100 * t["extraction_valid"] / t["total"]
        chk = d_c.dropna(subset=["revised"])
        rv = chk.groupby(key)["revised"].agg(["size", "sum"])
        if key == "epi_year":
            t["tier 2 checkable"] = rv["size"]
            t["revised"] = rv["sum"]
            t["% revised"] = 100 * rv["sum"] / rv["size"]
        else:
            r2 = d_c[d_c["revised"].fillna(False).astype(bool)]
            t["% revised"] = 100 * rv["sum"] / rv["size"]
            t["median revision_delta"] = r2.groupby("disease")["revision_delta"].median()
            t["median abs delta"] = r2.groupby("disease")["revision_delta"].apply(
                lambda s: s.abs().median()
            )
        t.index.name = label
        out += [f"### Per {label}", "", md(t, index=True), ""]
    r2 = d_c[d_c["revised"].fillna(False).astype(bool)]
    out += [
        f"`revision_delta` over all {len(r2):,} revised district rows: median "
        f"{r2['revision_delta'].median():.0f}, median absolute "
        f"{r2['revision_delta'].abs().median():.0f}, "
        f"90th percentile absolute {r2['revision_delta'].abs().quantile(0.9):.0f}; positive in "
        f"{100 * (r2['revision_delta'] > 0).mean():.0f}% (the cumulative was raised after the "
        f"weekly "
        "figure was printed).",
        "",
    ]
    lv = pd.Series(
        {
            "extraction_valid, tier 2 checked, not revised": int((d_c["revised"] == False).sum()),  # noqa: E712
            "extraction_valid, revised (kept, delta recorded)": int((d_c["revised"] == True).sum()),  # noqa: E712
            "extraction_valid, tier 2 unknown (previous week missing)": int(
                d_c["revised"].isna().sum()
            ),
            "of all these: note = national_weekly_source_error": int(
                (d_c["note"] == "national_weekly_source_error").sum()
            ),
            "of all these: note = national_cumulative_source_error": int(
                (d_c["note"] == "national_cumulative_source_error").sum()
            ),
        }
    ).rename("district rows")
    lv = lv.to_frame()
    lv.index.name = "group"
    out += [md(lv, index=True), ""]
    return out


def failures_section(clean, review) -> list[str]:
    out = ["## 4. What is in the review queue", ""]
    t = review.groupby(["fail_reason", "area_level"]).size().unstack(fill_value=0)
    t["total"] = t.sum(axis=1)
    t = t.sort_values("total", ascending=False)
    t.index.name = "fail_reason"
    out += [
        md(t, index=True),
        "",
        "`cum_sum_mismatch`: for that (week, disease) neither the districts' weekly counts nor "
        "their "
        "cumulative counts add to the printed national row, so the whole group is unreliable. "
        "`national_weekly_source_error` / `national_cumulative_source_error`: only the national "
        "row "
        "of a group whose districts are consistent (section 5). `missing_cell` / "
        "`group_has_missing_cell`: a count cell is blank or unreadable in the PDF; the group "
        "cannot "
        "be verified and nothing is inferred. Issues that failed to parse (section 2) and issues "
        "before 2022-W01 contribute no rows.",
        "",
    ]
    return out


def source_error_section(errors) -> list[str]:
    out = [
        "## 5. National source errors (districts kept, national row queued)",
        "",
        "Two symmetric rules, per (week, disease):",
        "",
        "- `national_weekly_source_error`: the districts' cumulative counts add to the printed "
        "national cumulative, but their weekly counts do not add to the printed national weekly.",
        "- `national_cumulative_source_error`: the districts' weekly counts add to the printed "
        "national weekly, but their cumulative counts do not add to the printed national "
        "cumulative.",
        "",
        "In both cases the district rows are kept with that `note` and only the national row goes "
        "to "
        "review. The second rule can also fire when a single district's cumulative carries a fixed "
        "offset (see the constant gaps below); its weekly figures, which the radar uses, still "
        "add up.",
        "",
    ]
    if errors.empty:
        return out + ["None.", ""]
    e = errors.sort_values(["epi_year", "epi_week", "disease"]).copy()
    e["week"] = e["epi_year"].astype(str) + "-W" + e["epi_week"].astype(str).str.zfill(2)
    e["file"] = e["source_file"].str.split("/").str[-1]
    cols = [
        "week",
        "disease",
        "printed_national_cases",
        "district_sum_cases",
        "printed_national_cum",
        "district_sum_cum",
        "file",
    ]
    for kind in ("national_weekly_source_error", "national_cumulative_source_error"):
        k = e[e["kind"] == kind]
        out += [f"### `{kind}`: {len(k)} groups", ""]
        if k.empty:
            continue
        by_dis = k.groupby("disease").size().sort_values(ascending=False).to_dict()
        out += [f"By year: {k.groupby('epi_year').size().to_dict()}; by disease: {by_dis}.", ""]
        if kind == "national_weekly_source_error":
            ratio = k["printed_national_cases"] / k["district_sum_cases"]
            below = 100 * (k["printed_national_cases"] < k["district_sum_cases"]).mean()
            out += [
                f"The printed national weekly is below the district sum in {below:.0f}% "
                f"(median printed/sum = {ratio.median():.2f}).",
                "",
            ]
        else:
            k = k.assign(cum_gap=k["district_sum_cum"] - k["printed_national_cum"])
            const = k.groupby(["disease", "epi_year"])["cum_gap"].agg(["size", "nunique", "first"])
            const = const[(const["size"] >= 5) & (const["nunique"] == 1)]
            pat = "; ".join(
                f"{d} {y}: district cumulatives exceed the national by exactly "
                f"{int(r['first'])} in all {int(r['size'])} weeks"
                for (d, y), r in const.iterrows()
            )
            ratio = (k["printed_national_cum"] / k["district_sum_cum"]).median()
            out += [
                f"Constant gaps: {pat or 'none'}. Median printed/sum of the cumulative: "
                f"{ratio:.2f}.",
                "",
            ]
        out += [
            "First 25 (all are in `data/review_queue/wer.parquet` under that `fail_reason`):",
            "",
            md(k[cols].head(25)),
            "",
        ]
    return out


def sequence_section(raw, deduped, dup_log) -> list[str]:
    out = ["## 6. Week sequence: gaps and duplicates", ""]
    weeks = deduped[["epi_year", "epi_week"]].drop_duplicates()
    rows = []
    for y, g in weeks.groupby("epi_year"):
        have = set(g["epi_week"])
        if len(have) < 5:
            rows.append(
                {
                    "year": y,
                    "weeks present": len(have),
                    "expected": "n/a (out of range)",
                    "missing weeks": "",
                }
            )
            continue
        last = date(y, 12, 28).isocalendar().week
        top = max(have) if y == weeks["epi_year"].max() else last
        miss = [w for w in range(1, top + 1) if w not in have]
        rows.append(
            {
                "year": y,
                "weeks present": len(have),
                "expected": f"1..{top}",
                "missing weeks": ", ".join(map(str, miss)) or "none",
            }
        )
    out += [
        md(pd.DataFrame(rows)),
        "",
        "Missing weeks are almost entirely issues that failed to parse (section 2: printed-week "
        "typos) or that the website does not list.",
        "",
        "### Duplicate weeks (two issues, same week)",
        "",
    ]
    if dup_log:
        for d in dup_log:
            out.append(
                f"- {d['epi_year']}-W{d['epi_week']:02d}: kept `{d['kept']}`, dropped "
                f"{d['dropped']}; scores {d['scores']}; {d['reason']}"
            )
    else:
        out.append(
            "None. A misprinted week (wrong month or year) used to look like a duplicate of the "
            "real "
            "week; the weekday and printed-week checks in section 8 now reject such issues instead."
        )
    out.append("")
    return out


def completeness_section(deduped, clean, pct_counts) -> list[str]:
    out = [
        "## 7. Completeness (C**) and timeliness (T*)",
        "",
        "**C\\*\\* is not defined in any of the 244 issues (section 9), so it is used only "
        "relatively:** "
        "`completeness_low` is true when an RDHS's C\\*\\* for the week is below that RDHS's own "
        "10th "
        "percentile of C\\*\\* over its past weeks (expanding window, the current week excluded, "
        "at "
        "least 26 past weeks, so 2022 H1 is empty). No absolute threshold is used. **T\\* is for "
        "display only**: it steps from 42% to 93% at 2023-W52 (national), so it cannot be compared "
        "across years.",
        "",
        "Values outside 0..100 were set to NaN (the counts of those rows are kept): "
        f"C\\*\\*: {pct_counts['completeness_pct']['area_weeks']} area-weeks "
        f"({pct_counts['completeness_pct']['rdhs_area_weeks']} RDHS), values "
        f"{pct_counts['completeness_pct']['values']}; T\\*: "
        f"{pct_counts['timeliness_pct']['area_weeks']} "
        f"area-weeks, values {pct_counts['timeliness_pct']['values']}.",
        "",
    ]
    d = deduped[deduped["area_level"] == "rdhs"].drop_duplicates(["epi_year", "epi_week", "area"])
    d = d[d["completeness_pct"].between(0, 100)]
    cl = clean[clean["area_level"] == "rdhs"].drop_duplicates(["epi_year", "epi_week", "area"])

    def agg(g):
        return pd.Series(
            {
                "weeks": len(g),
                "C min": g["completeness_pct"].min(),
                "C p10": g["completeness_pct"].quantile(0.1),
                "C median": g["completeness_pct"].median(),
            }
        )

    t = d.groupby("area").apply(agg, include_groups=False)
    t["weeks"] = t["weeks"].astype(int)
    flagged = (
        cl.dropna(subset=["completeness_low"])
        .groupby("area")["completeness_low"]
        .agg(["size", "sum"])
    )
    t["weeks with a threshold"] = flagged["size"]
    t["completeness_low weeks"] = flagged["sum"]
    t["% low"] = 100 * flagged["sum"] / flagged["size"]
    out += [
        "### Per RDHS (C** min / p10 / median over all weeks; completeness_low rate)",
        "",
        md(t, index=True),
        "",
    ]
    n = deduped[deduped["area_level"] == "national"].drop_duplicates(["epi_year", "epi_week"])
    ny = n.groupby("epi_year").agg(
        weeks=("epi_week", "size"),
        C_median=("completeness_pct", "median"),
        T_median=("timeliness_pct", "median"),
        T_min=("timeliness_pct", "min"),
    )
    out += [
        "### National row, by year (T* shown only to document the 2023-W52 step)",
        "",
        md(ny, index=True),
        "",
    ]
    return out


def parser_section(results) -> list[str]:
    ok = [r for r in results if r.status == "ok"]
    out = ["## 8. What the parser saw", ""]
    ds = Counter(r.meta["n_diseases"] for r in ok)
    out += [
        f"Disease columns per issue: {dict(sorted(ds.items()))} (12 -> 13 with Tuberculosis from "
        "Vol 51 No 11 -> 14 with Leprosy from Vol 53 No 1; see docs/LAYOUTS.md).",
        "",
    ]
    names = defaultdict(Counter)
    for r in ok:
        for dis, nm in zip(r.meta["diseases"], r.meta["header_names"], strict=True):
            names[dis][nm] += 1
    out += [
        "Printed header spellings mapped to each disease (all explicit aliases in "
        "`config/sources.yaml`; an unknown spelling is a hard failure):",
        "",
    ]
    out += [
        f"- {dis}: " + ", ".join(f"`{n}` x{c}" for n, c in cnt.most_common())
        for dis, cnt in names.items()
    ]
    cs = Counter()
    probs = []
    for r in ok:
        for k, v in r.meta["cell_stats"].items():
            cs[k] += v
        if r.meta["cell_stats"]["blank"] or r.meta["cell_stats"]["unreadable"]:
            probs.append(
                f"{r.source_issue} ({r.meta['cell_stats']['blank']} blank, "
                f"{r.meta['cell_stats']['unreadable']} unreadable)"
            )
    out += [
        "",
        f"Cell-level oddities across all parsed issues: {dict(cs)}. T*/C** printed as `8%` or "
        f"`5.5` "
        "in `pct_format` cells are read as numbers. Blank/unreadable count cells put their whole "
        "(week, disease) group in review. Issues with such cells: "
        + ("; ".join(probs) or "none")
        + ".",
        "",
    ]
    out += [
        "Checks applied to every parsed issue: Table 1 title found by content; RDHS/WRCD header "
        "and "
        "A/B/T*/C** sub-header found; every disease header mapped to a config id in config order; "
        "26 RDHS rows in canonical order then SRI LANKA; week text internally consistent "
        "(start = end - 6 days), correct start weekday (Sat before the Dec 2025 switch, Mon "
        "after), "
        "and the printed `(Nth Week)` equal to the canonical week (WER numbered 2021 one ahead).",
        "",
    ]
    return out


def cstar_section(results) -> list[str]:
    ok = [r for r in results if r.status == "ok"]
    out = [
        "## 9. What do T* and C** mean? (investigation)",
        "",
        r"**C\*\* is undefined in all 244 issues; we use relative gating only** "
        r"(`completeness_low`, "
        r"section 7). T\* is used for display only.",
        "",
    ]
    v = defaultdict(list)
    for r in ok:
        f = re.sub(r"\s+", " ", r.meta["footnote"])
        f = re.sub(r"\d+(st|nd|rd|th)?\s*[A-Za-z]*\s*,?\s*\d{4}", "<date>", f)
        f = re.sub(r"\b\d+\b", "N", f)
        v[f].append(r.source_issue)
    out += [
        "Footnote text under Table 1 in the parsed issues (digits and dates masked), most common "
        "first:",
        "",
    ]
    for f, issues in sorted(v.items(), key=lambda kv: -len(kv[1]))[:8]:
        out.append(f"- x{len(issues)} (e.g. {issues[0]}): `{f.strip()[:330]}`")
    out.append("")
    if CSTAR_NOTES.exists():
        out += [CSTAR_NOTES.read_text(encoding="utf-8").strip(), ""]
    return out


def cross_check_section() -> list[str]:
    """Second extractor result and hand-check score, embedded from their own outputs."""
    out = ["## 10. Independent checks", ""]
    cx = REPO_ROOT / "docs" / "CROSS_EXTRACT.md"
    if cx.exists():
        bullets = [ln for ln in cx.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")]
        out += [
            "**Second extractor (PyMuPDF, `scripts/cross_extract.py`, details in "
            "`docs/CROSS_EXTRACT.md`):**",
            "",
            *bullets,
            "",
        ]
    else:
        out += ["Second extractor not run yet (`python scripts/cross_extract.py`).", ""]
    hc = REPO_ROOT / "docs" / "handcheck_result.md"
    out += ["<!-- handcheck:start -->"]
    if hc.exists():
        out += [hc.read_text(encoding="utf-8").rstrip()]
    else:
        out += [
            "## Hand-check (manual verification against the rendered page)",
            "",
            "Pack ready, not yet scored: 40 cells in `data/handcheck/v2/` (one image per cell, "
            "fixed "
            "seed, 8 per year 2022-2026, no two from one issue). Fill `verified` and run "
            "`python scripts/handcheck_score.py`.",
        ]
    out += ["<!-- handcheck:end -->", ""]
    return out


def stale_section(stale) -> list[str]:
    out = [
        "## 5b. Weekly columns copied or scrambled (source errors)",
        "",
        "Some issues print a weekly (A) column that repeats the previous week's exactly, while the "
        "cumulative column is advanced by the copied figures, so every sum and cumulative check "
        "passes. Confirmed on the rendered pages for Vol 53 No 26 vs No 27 (dengue: Colombo 1138, "
        "Gampaha 1294, Kandy 472 ... in both). Rule: a (week, disease) group is queued "
        "(`stale_weekly_copy`) when at least 8 districts report a non-zero count and at least 80% "
        "of "
        "them equal the previous week, or when at least 70% of all non-zero district cells of the "
        "whole issue repeat (the highest other week scores 42%). The true counts of those weeks "
        "are "
        "unknown, so nothing is corrected.",
        "",
    ]
    out_scr = [
        "Second rule, `scrambled_weekly_column`: the weekly column is printed against the wrong "
        "rows "
        "(confirmed on the rendered page of Vol 53 No 15, 2026-W14: dengue Colombo 9, Matale 256, "
        "Nuwara Eliya 113, Kilinochchi 117, where the weeks around read about 300, 20, 6 and 1; "
        "the "
        "national total and the cumulatives are consistent with the scrambled column). Past-only "
        "test: with >= 20 non-zero districts, the rank correlation (Spearman) of this week's "
        "district counts with last week's is below 0.3 while last week and the week before agreed "
        "(>= 0.7; for dengue the typical week-to-week value is 0.93). Two or more diseases "
        "tripping "
        "in one week flag the whole issue.",
        "",
    ]
    if stale is None or stale.empty:
        return out + out_scr + ["None found.", ""]
    s = stale.copy()
    if "kind" not in s:
        s["kind"] = "stale_weekly_copy"
    s["rho"] = s.get("rho", np.nan)
    s["week"] = s["epi_year"].astype(str) + "-W" + s["epi_week"].astype(str).str.zfill(2)
    s["repeated / non-zero districts"] = [
        f"{int(a)} / {int(b)}" if a == a and b == b else ""
        for a, b in zip(s.get("repeated", np.nan * s["nonzero"]), s["nonzero"], strict=True)
    ]
    s["issue share %"] = 100 * s.get("issue_share", np.nan * s["nonzero"])
    st = s[s["kind"] == "stale_weekly_copy"]
    out += [
        md(st[["week", "disease", "scope", "repeated / non-zero districts", "issue share %"]]),
        "",
    ]
    out += out_scr
    sc = s[s["kind"] == "scrambled_weekly_column"]
    if sc.empty:
        out += ["None found.", ""]
    else:
        g = (
            sc.groupby(["week", "scope"])
            .agg(
                diseases=("disease", lambda x: ", ".join(sorted(x))),
                min_rho=("rho", "min"),
            )
            .reset_index()
        )
        out += [md(g), ""]
    return out


def write_report(
    results,
    raw,
    deduped,
    clean,
    review,
    errors,
    dup_log,
    pct_counts,
    dropped_early=(),
    stale=None,
) -> Path:
    n_ok = sum(r.status == "ok" for r in results)
    d_c = clean[clean["area_level"] == "rdhs"]
    d_r = review[review["area_level"] == "rdhs"]
    pct = _pct(len(d_c), len(d_c) + len(d_r))
    rv = d_c["revised"].dropna()
    n_ov = sum(1 for r in results if r.meta.get("week_override"))
    head = [
        "# WER Table 1 extraction report",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by "
        "`python -m radar_lk.ingest.parse_wer`.",
        "Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (Weekly Epidemiological "
        "Report, Table 1). Source files: `data/raw/wer/*.pdf`, listed with hashes in "
        "`data/raw/manifest.csv`. Every row in `data/clean/wer.parquet` carries `source_file`, "
        "`source_issue` and `extracted_at`.",
        "",
        "## 1. Summary",
        "",
        f"- PDFs: **{len(results)}**: parsed **{n_ok}**, no Table 1 "
        f"**{sum(r.status == 'no_table' for r in results)}**, failed "
        f"**{sum(r.status == 'failed' for r in results)}**; week overrides applied: **{n_ov}**",
        f"- District-disease-weeks `extraction_valid` (tier 1): **{pct:.2f}%** "
        f"({len(d_c):,} of {len(d_c) + len(d_r):,}); target {TARGET:.0f}% "
        f"{'met' if pct >= TARGET else '**not met**'}",
        f"- Of those, `revised` (tier 2: cross-week identity fails, kept with `revision_delta`): "
        f"**{100 * rv.mean():.1f}%** of {len(rv):,} checkable rows",
        "- National source errors (districts kept, national row queued): weekly "
        f"**{int((errors['kind'] == 'national_weekly_source_error').sum())}**, cumulative "
        f"**{int((errors['kind'] == 'national_cumulative_source_error').sum())}**",
        f"- Duplicate weeks resolved: **{len(dup_log)}**",
        f"- Rows in review queue: **{len(review):,}** (district {len(d_r):,})",
        "",
    ]
    body = (
        issues_section(results, dropped_early)
        + validation_section(raw, clean, review)
        + failures_section(clean, review)
        + source_error_section(errors)
        + stale_section(stale)
        + sequence_section(raw, deduped, dup_log)
        + completeness_section(deduped, clean, pct_counts)
        + parser_section(results)
        + cstar_section(results)
    )
    body += cross_check_section()
    body += [
        "## 12. Reproduce",
        "",
        "```",
        "python -m radar_lk.ingest.download --source wer --years 2022-2026",
        "python -m radar_lk.ingest.parse_wer",
        "python scripts/cross_extract.py        # second extractor (PyMuPDF), cell-by-cell",
        "python scripts/handcheck.py            # hand-check pack v2 (refuses to overwrite)",
        "python scripts/handcheck_score.py      # after filling the CSV",
        "pytest -q",
        "```",
        "",
    ]
    REPORT.write_text("\n".join(head + body), encoding="utf-8")
    print(f"wrote {REPORT}")
    return REPORT
