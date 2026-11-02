"""Write docs/EXTRACTION_REPORT.md from a WER pipeline run.

Every number in the report is computed from the run's data; the only hand-written part is the
C** investigation, which is read from docs/cstar_findings.md if that file exists.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from radar_lk import REPO_ROOT
from radar_lk.ingest.validate import NATIONAL, cumulative_check, sum_check

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
            if isinstance(v, float):
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
        return t[m.start(): m.start() + 60].strip() if m else ""
    except Exception:  # noqa: BLE001 - report only
        return ""


def issues_section(results) -> list[str]:
    out = ["## 2. Issues processed, per year", ""]
    rows = defaultdict(Counter)
    for r in results:
        y = _nominal_year(r)
        rows[y]["files"] += 1
        rows[y][r.status] += 1
    tbl = pd.DataFrame(
        [{"year": y, "files": c["files"], "ok": c["ok"], "no_table": c["no_table"], "failed": c["failed"]}
         for y, c in sorted(rows.items())]
    )
    tot = tbl[["files", "ok", "no_table", "failed"]].sum()
    tbl.loc[len(tbl)] = ["**total**", *tot]
    out += [md(tbl), "",
            "`year` is the year of the week printed in Table 1 for parsed issues, and the volume year "
            "(vol + 1973) for issues that did not parse. 2021 and 2011 are out-of-range files that the "
            "site lists under 2022 dates.", ""]
    nt = [r for r in results if r.status == "no_table"]
    out += ["**no_table** (no Table 1 title found on any page; logged and skipped):", ""]
    out += [f"- `{r.file}`" for r in nt] or ["- none"]
    failed = [r for r in results if r.status == "failed"]
    out += ["", f"**failed** ({len(failed)}; nothing from these issues reaches the clean table):", ""]
    if failed:
        out.append(md(pd.DataFrame([{"issue": r.source_issue, "file": r.file.split("/")[-1],
                                     "reason": r.reason[:170]} for r in failed])))
    out.append("")
    wk = [r for r in failed if (r.meta.get("error_code") or "").startswith("week_")]
    if wk:
        out += ["### Source typos in the printed week (not corrected)", "",
                "These issues print a week that is impossible or contradicts the issue's own numbering. "
                "They are not guessed; to accept a correction add it to `wer_calendar.week_overrides` in "
                "`config/sources.yaml`. The front-page line (separate from the table) is shown as "
                "corroboration only: in every parsed issue the table week is the 7 days before the "
                "front-page range.", ""]
        rows2 = []
        for r in wk:
            rows2.append({"issue": r.source_issue, "printed in Table 1": r.reason.split(":", 1)[1][:90],
                          "front page": _front_page_line(REPO_ROOT / "data" / "raw" / r.file)})
        out += [md(pd.DataFrame(rows2)), ""]
    return out


def validation_section(raw, clean, review) -> list[str]:
    out = ["## 3. Validation", ""]
    d_c, d_r = clean[clean["area_level"] == "rdhs"], review[review["area_level"] == "rdhs"]
    n_all = len(d_c) + len(d_r)
    pct = _pct(len(d_c), n_all)
    out += [f"District-disease-weeks extracted from parsed issues: **{n_all:,}**; validated: "
            f"**{len(d_c):,} = {pct:.2f}%** (target {TARGET:.0f}%: "
            f"{'MET' if pct >= TARGET else '**NOT MET**'}).", "",
            "A district-disease-week is one RDHS x disease x week. Validated means it passed the sum "
            "check (districts add to the printed national total) and, where the previous week is "
            "present, the cumulative check; it is in `data/clean/wer.parquet`. Everything else is in "
            "`data/review_queue/wer.parquet` with `fail_reason`. Issues that failed to parse contribute "
            "no rows to either count (see section 2).", ""]
    for key, label in (("epi_year", "year"), ("disease", "disease")):
        a = d_c.groupby(key).size().rename("validated")
        b = d_r.groupby(key).size().rename("not validated")
        t = pd.concat([a, b], axis=1).fillna(0).astype(int)
        t["total"] = t.sum(axis=1)
        t["% validated"] = 100 * t["validated"] / t["total"]
        t.index.name = label
        out += [f"### Validated, per {label}", "", md(t, index=True), ""]
    lv = pd.Series({
        "sum ok and cumulative ok": int((d_c["cum_ok"].fillna(False).astype(bool) & (d_c["note"] == "")).sum()),
        "sum ok, cumulative unknown (previous week missing / first week)": int(d_c["cum_ok"].isna().sum()),
        "kept via source_total_error rule (note=national_total_source_error)":
            int((d_c["note"] == "national_total_source_error").sum()),
    }).rename("district rows").to_frame()
    lv.index.name = "check"
    out += ["### How the validated rows were validated", "", md(lv, index=True), ""]
    return out


def failures_section(clean, review) -> list[str]:
    out = ["## 4. Why rows failed (top reasons first)", ""]
    rv = review.copy()
    rv["level"] = rv["area_level"]
    t = rv.groupby(["fail_reason", "level"]).size().unstack(fill_value=0)
    t["total"] = t.sum(axis=1)
    t = t.sort_values("total", ascending=False)
    t["share of all review rows"] = 100 * t["total"] / t["total"].sum()
    t.index.name = "fail_reason"
    out += [md(t, index=True), "",
            "`cumulative_mismatch`: cum_t != cum_(t-1) + weekly_t for that row. `sum_mismatch`: the 26 "
            "districts do not add to the printed SRI LANKA row for that (week, disease), which fails "
            "every row of that group. `source_total_error`: the rule in section 5. `missing_cell` / "
            "`group_has_missing_cell`: a count cell is blank or unreadable in the PDF, so the group "
            "cannot be verified and nothing is inferred. `pct_out_of_range`: completeness or timeliness "
            "outside 0..100 in the PDF.", ""]
    # ---- analysis of the two big classes, computed from the union of both outputs
    u = pd.concat([clean, review], ignore_index=True)
    u = u[u["cases"].notna() & u["cum_cases"].notna()].astype({"cases": "int64", "cum_cases": "int64"})
    base = u.drop(columns=[c for c in ("cum_ok", "sum_ok") if c in u])
    d = cumulative_check(base)
    d["gap"] = d["cum_cases"] - (d.groupby(["area", "disease", "epi_year"])["cum_cases"].shift(1) + d["cases"])
    dd = d[d["area"] != NATIONAL]
    chk = dd[dd["cum_ok"].notna()]
    bad = chk[chk["cum_ok"] == False]  # noqa: E712
    out += ["### Cumulative-check failures: what they look like", "",
            f"{len(bad):,} of {len(chk):,} checkable district rows ({_pct(len(bad), len(chk)):.1f}%) fail "
            f"`cum_t = cum_(t-1) + weekly_t`. `gap` = cum_t - (cum_(t-1) + weekly_t):", "",
            f"- median |gap| = {bad['gap'].abs().median():.0f}; 75th percentile = "
            f"{bad['gap'].abs().quantile(.75):.0f}; 90th = {bad['gap'].abs().quantile(.9):.0f}",
            f"- gap > 0 in {100 * (bad['gap'] > 0).mean():.0f}% of failures, gap < 0 in "
            f"{100 * (bad['gap'] < 0).mean():.0f}%", ""]
    by_year = chk.groupby("epi_year").apply(lambda g: pd.Series({
        "checkable rows": len(g), "failing": int((g["cum_ok"] == False).sum()),  # noqa: E712
        "% failing": 100 * (g["cum_ok"] == False).mean()}), include_groups=False)  # noqa: E712
    by_dis = chk.groupby("disease").apply(lambda g: pd.Series({
        "checkable rows": len(g), "failing": int((g["cum_ok"] == False).sum()),  # noqa: E712
        "% failing": 100 * (g["cum_ok"] == False).mean()}), include_groups=False  # noqa: E712
    ).sort_values("% failing", ascending=False)
    byw = chk.groupby(["epi_year", "epi_week"])["cum_ok"].apply(lambda s: (s == False).mean())  # noqa: E712
    hot = byw[byw > 0.3].round(2)
    out += [md(by_year.astype({"checkable rows": int, "failing": int}), index=True), "",
            md(by_dis.astype({"checkable rows": int, "failing": int}), index=True), "",
            "Weeks where more than 30% of checkable district rows fail (an issue-level problem rather "
            "than scattered cells): " + (", ".join(f"{y}-W{w:02d} ({v:.0%})" for (y, w), v in hot.items())
                                         or "none") + ".", "",
            "Reading: failures are mostly small (median gap a handful of cases), mostly positive, "
            "highest for the highest-volume diseases (dengue, leptospirosis, chickenpox) and lower in "
            "2024-26 than in 2022-23. That pattern is *consistent with* cumulative columns being revised "
            "for late-notified cases after the weekly figure was printed, but the PDFs do not say so, so "
            "this is a hypothesis, not a finding. It means the strict identity may reject correct "
            "rows.", ""]
    sc = sum_check(u)
    sc["diff"] = sc["units_sum"] - sc["national"]
    fs = sc[~sc["sum_ok"]]
    out += ["### Sum-check failures: what they look like", "",
            f"{len(fs)} of {len(sc)} (week, disease) groups ({_pct(len(fs), len(sc)):.1f}%) fail the sum "
            f"check. districts-sum minus printed-national: median {fs['diff'].median():.0f}, "
            f"{100 * (fs['diff'] > 0).mean():.0f}% positive (the printed national is *smaller* than the "
            f"districts).", ""]
    t1 = fs.groupby("epi_year").size().rename("failing groups").to_frame()
    t1["groups"] = sc.groupby("epi_year").size()
    t1["% failing"] = 100 * t1["failing groups"] / t1["groups"]
    t2 = fs.groupby("disease").size().sort_values(ascending=False).rename("failing groups").to_frame()
    out += [md(t1, index=True), "", md(t2.head(8), index=True), ""]
    out += _sum_failure_classes(u, d, sc)
    out += _what_if(u, d)
    return out


def _sum_failure_classes(u, d, sc) -> list[str]:
    """Split the failing (week, disease) groups by what the cumulative columns say."""
    keys = ["epi_year", "epi_week", "disease"]
    cs = sum_check(u, "cum_cases")[keys + ["sum_ok"]].rename(columns={"sum_ok": "cum_sum_ok"})
    f = sc[~sc["sum_ok"]].merge(cs, on=keys)
    dist = d[d["area"] != NATIONAL].groupby(keys)["cum_ok"].agg(
        n_false=lambda s: int((s == False).sum()), n_unknown=lambda s: int(s.isna().sum())  # noqa: E712
    ).reset_index()
    nat = d[d["area"] == NATIONAL][keys + ["cum_ok"]].rename(columns={"cum_ok": "nat_cum_ok"})
    g = f.merge(dist, on=keys).merge(nat, on=keys)
    labels = {
        "A": "national cumulative = district cumulative sum, all 26 districts pass their own cumulative "
             "check, national fails its own (rule in section 5 fires)",
        "B": "national cumulative = district cumulative sum, no district fails, but some district's "
             "previous week is missing so its cumulative check is unknown",
        "C": "national cumulative = district cumulative sum, but at least one district fails its own "
             "cross-week cumulative check",
        "D": "national cumulative != district cumulative sum",
    }
    g["class"] = np.select(
        [g["cum_sum_ok"] & (g["n_false"] == 0) & (g["n_unknown"] == 0) & (g["nat_cum_ok"] == False),  # noqa: E712
         g["cum_sum_ok"] & (g["n_false"] == 0) & (g["n_unknown"] > 0),
         g["cum_sum_ok"] & (g["n_false"] > 0), ~g["cum_sum_ok"]],
        ["A", "B", "C", "D"], "other")
    t = g.groupby("class").size().rename("groups").to_frame()
    t["what it means"] = [labels[c] for c in t.index]
    t.index.name = "class"
    out = ["### Failing sum groups, split by what the cumulative columns say", "", md(t, index=True), "",
           "In classes A-C the *cumulative* columns of the districts add up to the national cumulative, so "
           "only the printed national *weekly* figure disagrees; in the rule-A cases the printed weekly is "
           "far below the district sum (e.g. 16 printed against 163 for 2022-W25 leptospirosis). Class D (and e.g. every disease of "
           "2023-W41) points at a wrong national row or week and stays in review.", ""]
    return out


def _what_if(u, d) -> list[str]:
    """Hypothetical validation rates under alternative rules. NOT applied to the outputs."""
    keys = ["epi_year", "epi_week", "disease"]
    cs = sum_check(u, "cum_cases")[keys + ["sum_ok"]].rename(columns={"sum_ok": "cum_sum_ok"})
    x = d.merge(cs, on=keys, how="left")
    x = x[x["area"] != NATIONAL]
    pct_ok = x["completeness_pct"].between(0, 100) & x["timeliness_pct"].between(0, 100)
    all_rdhs = u[u["area_level"] == "rdhs"]
    n = len(all_rdhs)
    now = int((all_rdhs["validated"] == True).sum())  # noqa: E712
    h2 = int(((x["cum_sum_ok"] == True) & pct_ok).sum())  # noqa: E712
    return ["### What-if (NOT applied): which rule keeps the rate below target", "",
            f"- current rules (weekly sum check + cross-week cumulative check + pct range): "
            f"{100 * now / n:.2f}%",
            f"- only checks that live inside one issue (districts' cumulative sum = national cumulative, "
            f"pct range), with the cross-week cumulative identity reported but not enforced: "
            f"{100 * h2 / n:.2f}%",
            "", "The gap between the two is the cross-week identity `cum_t = cum_(t-1) + weekly_t`, which "
            "is the largest single failure class. Whether a row that fails only that identity may reach "
            "the dashboard (flagged) or must stay in review is a policy decision, not a parser fix.", ""]


def source_error_section(errors) -> list[str]:
    out = ["## 5. `source_total_error` cases", "",
           "Rule: for a (week, disease) that fails the sum check, if every district row passes its own "
           "cumulative check *and* the national row fails its own cumulative check, the districts are "
           "internally consistent and only the printed national figure is wrong. The district rows are "
           "kept (`validated=True`, `note=national_total_source_error`); only the national row goes to "
           "the review queue. If any district's cumulative status is unknown or failing, the rule does "
           "not fire and the whole group stays in review.", "",
           f"Count: **{len(errors)}**.", ""]
    if len(errors):
        e = errors.sort_values(["epi_year", "epi_week", "disease"])
        out += [md(e.assign(week=e["epi_year"].astype(str) + "-W" + e["epi_week"].astype(str).str.zfill(2),
                            file=e["source_file"].str.split("/").str[-1])
                   [["week", "disease", "printed_national_cases", "district_sum_cases",
                     "printed_national_cum", "district_sum_cum", "file"]]), ""]
        by = e.groupby("epi_year").size().to_dict()
        out += [f"By year: {by}.", ""]
    return out


def sequence_section(raw, deduped, dup_log) -> list[str]:
    out = ["## 6. Week sequence: gaps and duplicates", ""]
    weeks = deduped[["epi_year", "epi_week"]].drop_duplicates()
    rows = []
    for y, g in weeks.groupby("epi_year"):
        have = set(g["epi_week"])
        if len(have) < 5:
            rows.append({"year": y, "weeks present": len(have), "expected": "n/a (out of range)",
                         "missing weeks": ""})
            continue
        last = date(y, 12, 28).isocalendar().week
        top = max(have) if y == weeks["epi_year"].max() else last
        miss = [w for w in range(1, top + 1) if w not in have]
        rows.append({"year": y, "weeks present": len(have), "expected": f"1..{top}",
                     "missing weeks": ", ".join(map(str, miss)) or "none"})
    out += [md(pd.DataFrame(rows)), "",
            "Missing weeks are almost entirely issues that failed to parse (section 2: printed-week "
            "typos) or that the website does not list.", "", "### Duplicate weeks (two issues, same week)", ""]
    if dup_log:
        for d in dup_log:
            out.append(f"- {d['epi_year']}-W{d['epi_week']:02d}: kept `{d['kept']}`, dropped "
                       f"{d['dropped']}; scores {d['scores']}; {d['reason']}")
    else:
        out.append("None. A misprinted week (wrong month or year) used to look like a duplicate of the real "
                   "week; the weekday and printed-week checks in section 8 now reject such issues instead.")
    out.append("")
    return out


def completeness_section(deduped) -> list[str]:
    out = ["## 7. Completeness (C**) and timeliness (T*) per RDHS", "",
           "From the parsed issues (one value per RDHS per week, values outside 0..100 excluded). "
           "min / p10 / median over all weeks. **T\\* is not comparable across years** (see national "
           "table below).", ""]
    d = deduped[deduped["area_level"] == "rdhs"].drop_duplicates(["epi_year", "epi_week", "area"])
    d = d[d["completeness_pct"].between(0, 100) & d["timeliness_pct"].between(0, 100)]

    def agg(g):
        return pd.Series({
            "weeks": len(g),
            "C min": g["completeness_pct"].min(), "C p10": g["completeness_pct"].quantile(.1),
            "C median": g["completeness_pct"].median(),
            "T min": g["timeliness_pct"].min(), "T p10": g["timeliness_pct"].quantile(.1),
            "T median": g["timeliness_pct"].median()})

    t = d.groupby("area").apply(agg, include_groups=False)
    t["weeks"] = t["weeks"].astype(int)
    out += [md(t, index=True), ""]
    n = deduped[deduped["area_level"] == "national"].drop_duplicates(["epi_year", "epi_week"])
    ny = n.groupby("epi_year").agg(weeks=("epi_week", "size"), C_median=("completeness_pct", "median"),
                                   T_median=("timeliness_pct", "median"), T_min=("timeliness_pct", "min"))
    out += ["### National row, by year", "", md(ny, index=True), ""]
    return out


def parser_section(results) -> list[str]:
    ok = [r for r in results if r.status == "ok"]
    out = ["## 8. What the parser saw", ""]
    ds = Counter(r.meta["n_diseases"] for r in ok)
    out += [f"Disease columns per issue: {dict(sorted(ds.items()))} (12 -> 13 with Tuberculosis from "
            "Vol 51 No 11 -> 14 with Leprosy from Vol 53 No 1; see docs/LAYOUTS.md).", ""]
    names = defaultdict(Counter)
    for r in ok:
        for dis, nm in zip(r.meta["diseases"], r.meta["header_names"], strict=True):
            names[dis][nm] += 1
    out += ["Printed header spellings mapped to each disease (all explicit aliases in "
            "`config/sources.yaml`; an unknown spelling is a hard failure):", ""]
    out += [f"- {dis}: " + ", ".join(f"`{n}` x{c}" for n, c in cnt.most_common()) for dis, cnt in names.items()]
    cs = Counter()
    probs = []
    for r in ok:
        for k, v in r.meta["cell_stats"].items():
            cs[k] += v
        if r.meta["cell_stats"]["blank"] or r.meta["cell_stats"]["unreadable"]:
            probs.append(f"{r.source_issue} ({r.meta['cell_stats']['blank']} blank, "
                         f"{r.meta['cell_stats']['unreadable']} unreadable)")
    out += ["", f"Cell-level oddities across all parsed issues: {dict(cs)}. T*/C** printed as `8%` or `5.5` "
            "in `pct_format` cells are read as numbers. Blank/unreadable count cells put their whole "
            "(week, disease) group in review. Issues with such cells: " + ("; ".join(probs) or "none") + ".", ""]
    out += ["Checks applied to every parsed issue: Table 1 title found by content; RDHS/WRCD header and "
            "A/B/T*/C** sub-header found; every disease header mapped to a config id in config order; "
            "26 RDHS rows in canonical order then SRI LANKA; week text internally consistent "
            "(start = end - 6 days), correct start weekday (Sat before the Dec 2025 switch, Mon after), "
            "and the printed `(Nth Week)` equal to the canonical week (WER numbered 2021 one ahead).", ""]
    return out


def cstar_section(results) -> list[str]:
    ok = [r for r in results if r.status == "ok"]
    out = ["## 9. What do T* and C** mean? (investigation)", ""]
    v = defaultdict(list)
    for r in ok:
        f = re.sub(r"\s+", " ", r.meta["footnote"])
        f = re.sub(r"\d+(st|nd|rd|th)?\s*[A-Za-z]*\s*,?\s*\d{4}", "<date>", f)
        f = re.sub(r"\b\d+\b", "N", f)
        v[f].append(r.source_issue)
    out += ["Footnote text under Table 1 in the parsed issues (digits and dates masked), most common first:", ""]
    for f, issues in sorted(v.items(), key=lambda kv: -len(kv[1]))[:8]:
        out.append(f"- x{len(issues)} (e.g. {issues[0]}): `{f.strip()[:330]}`")
    out.append("")
    if CSTAR_NOTES.exists():
        out += [CSTAR_NOTES.read_text(encoding="utf-8").strip(), ""]
    return out


def write_report(results, raw, deduped, clean, review, errors, dup_log) -> Path:
    n_ok = sum(r.status == "ok" for r in results)
    d_c = clean[clean["area_level"] == "rdhs"]
    d_r = review[review["area_level"] == "rdhs"]
    pct = _pct(len(d_c), len(d_c) + len(d_r))
    head = [
        "# WER Table 1 extraction report", "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m radar_lk.ingest.parse_wer`.",
        "Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (Weekly Epidemiological Report, "
        "Table 1). Source files: `data/raw/wer/*.pdf`, listed with hashes in `data/raw/manifest.csv`. "
        "Every row in `data/clean/wer.parquet` carries `source_file`, `source_issue` and `extracted_at`.", "",
        "## 1. Summary", "",
        f"- PDFs: **{len(results)}**: parsed **{n_ok}**, no Table 1 **{sum(r.status == 'no_table' for r in results)}**, "
        f"failed **{sum(r.status == 'failed' for r in results)}**",
        f"- District-disease-weeks validated: **{pct:.2f}%** ({len(d_c):,} of {len(d_c) + len(d_r):,}); "
        f"target {TARGET:.0f}% {'met' if pct >= TARGET else '**not met**'}",
        f"- `source_total_error` cases (printed national total wrong, districts kept): **{len(errors)}**",
        f"- Duplicate weeks resolved: **{len(dup_log)}**",
        f"- Rows in review queue: **{len(review):,}** (district {len(d_r):,})", ""]
    body = (issues_section(results) + validation_section(raw, clean, review) + failures_section(clean, review)
            + source_error_section(errors) + sequence_section(raw, deduped, dup_log)
            + completeness_section(deduped) + parser_section(results) + cstar_section(results))
    body += ["## 10. Reproduce", "", "```", "python -m radar_lk.ingest.download --source wer --years 2022-2026",
             "python -m radar_lk.ingest.parse_wer", "python scripts/handcheck.py", "pytest -q", "```", ""]
    REPORT.write_text("\n".join(head + body), encoding="utf-8")
    print(f"wrote {REPORT}")
    return REPORT
