"""Write docs/NDCU_FEASIBILITY.md: can the dengue MOH outlook be built from NDCU's weekly lists?"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import pandas as pd

from radar_lk import REPO_ROOT
from radar_lk.ingest.parse_wer import norm
from radar_lk.ingest.report_wer import md

REPORT = REPO_ROOT / "docs" / "NDCU_FEASIBILITY.md"
CROSSWALK = REPO_ROOT / "config" / "moh_crosswalk.csv"
N_MOH = 364  # "all 364 Medical Officer of Health (MOH) divisions", WER Vol 53 No 1 p1
NEED_RUN, NEED_MAPPED, NEED_AREAS = 100, 90.0, 30


def longest_run(starts: list) -> tuple[int, object, object]:
    """Longest run of weekly starts exactly 7 days apart: (length, first start, last start)."""
    best = (0, None, None)
    run_start, prev, n = None, None, 0
    for s in sorted(set(starts)):
        if prev is not None and s - prev == timedelta(days=7):
            n += 1
        else:
            run_start, n = s, 1
        prev = s
        if n > best[0]:
            best = (n, run_start, s)
    return best


def write_feasibility(results, flags: pd.DataFrame, dist: pd.DataFrame) -> None:
    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status != "ok"]
    parseable = [r for r in ok if r.meta["list_parseable"]]
    bad_list = [r for r in ok if not r.meta["list_parseable"]]
    starts_ok = [r.meta["start"] for r in parseable]
    run_n, run_a, run_b = longest_run(starts_ok)

    # --- names
    f = flags.copy()
    f["parseable"] = f["source_file"].isin({f"ndcu_weekly/{r.file}" for r in parseable})
    f = f[f["parseable"]]
    cw_rows = []
    if CROSSWALK.exists():
        with open(CROSSWALK, newline="", encoding="utf-8") as fh:
            cw_rows = list(csv.DictReader(fh))
    seeded = {(r["district"], r["moh_name_raw"]) for r in cw_rows if r.get("source") == "ndcu_seed"}
    f["mapped"] = f["moh_name"].notna()
    f["by_seed"] = [(d, r) in seeded for d, r in zip(f["district"], f["moh_raw"], strict=True)]
    names = f.drop_duplicates(["district", "moh_raw"])
    mapped_pct = 100 * f["mapped"].mean() if len(f) else 0.0
    mapped_names_pct = 100 * names["mapped"].mean() if len(names) else 0.0
    manual_pct = 100 * (f["mapped"] & ~f["by_seed"]).mean() if len(f) else 0.0
    unmapped = sorted(
        set(
            zip(
                names.loc[~names["mapped"], "district"],
                names.loc[~names["mapped"], "moh_raw"],
                strict=True,
            )
        )
    )
    # a name printed under more than one district is a conflict: left unmapped, never resolved
    f["key"] = [norm(x) for x in f["moh_raw"]]
    by_key = f.groupby("key")["district"].agg(lambda s: sorted(set(s)))
    conflicts = by_key[by_key.map(len) > 1]
    conflict_detail = []
    for k, ds in conflicts.items():
        parts = [
            f"{d} ({f[(f.key == k) & (f.district == d)]['epi_week'].nunique()} wk)" for d in ds
        ]
        conflict_detail.append(f"{f[f.key == k]['moh_raw'].iloc[0]}: " + ", ".join(parts))
    flagged = f[f["mapped"]].drop_duplicates(["district", "moh_name"])
    n_areas = len(flagged)
    similar = []
    for d, g in flagged.groupby("district"):
        nm = sorted(set(g["moh_name"]))
        for i, x in enumerate(nm):
            for y in nm[i + 1 :]:
                if SequenceMatcher(None, x.lower(), y.lower()).ratio() >= 0.88:
                    similar.append(f"{d}: {x} / {y}")

    # --- base rates
    per_week = f.groupby("epi_week").size()
    weeks_parse = len(parseable)
    base_rate = per_week.sum() / (N_MOH * weeks_parse) if weeks_parse else float("nan")
    fm = f[f["mapped"]].assign(key=lambda d: d["district"] + "|" + d["moh_name"])
    by_week = {int(w): set(g["key"]) for w, g in fm.groupby("epi_week")}
    stay = leave = enter = nonflag = 0
    for w, cur in by_week.items():
        nxt = by_week.get(w + 1)
        if nxt is None:
            continue
        stay += len(cur & nxt)
        leave += len(cur - nxt)
        enter += len(nxt - cur)
        nonflag += N_MOH - len(cur)
    persist = stay / (stay + leave) if stay + leave else float("nan")
    entry = enter / nonflag if nonflag else float("nan")

    # --- weeks per year
    rows = []
    for y in sorted({r.meta["epi_year"] for r in ok}):
        wk = sorted(r.meta["epi_week"] for r in ok if r.meta["epi_year"] == y)
        pw = sorted(r.meta["epi_week"] for r in parseable if r.meta["epi_year"] == y)
        miss = [w for w in range(1, max(wk) + 1) if w not in wk]
        rows.append(
            {
                "year": y,
                "issues parsed": len(wk),
                "weeks": f"{min(wk)}..{max(wk)}",
                "missing weeks": ", ".join(map(str, miss)) or "none",
                "parseable high-risk list": len(pw),
            }
        )
    yr = pd.DataFrame(rows)
    # year counts of anything older that the site should have had
    crit = [
        (
            "consecutive weeks with a parseable high-risk list",
            f">= {NEED_RUN}",
            f"{run_n}",
            run_n >= NEED_RUN,
        ),
        (
            "MOH names mapped through the crosswalk",
            f">= {NEED_MAPPED:.0f}%",
            f"{mapped_pct:.1f}% (see caveat)",
            mapped_pct >= NEED_MAPPED,
        ),
        (
            "distinct MOH areas ever flagged",
            f">= {NEED_AREAS}",
            f"{n_areas}",
            n_areas >= NEED_AREAS,
        ),
    ]
    go = all(c[3] for c in crit)
    out = [
        "# NDCU feasibility: dengue MOH high-risk outlook",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by "
        "`python -m radar_lk.ingest.parse_ndcu`. Primary data: National Dengue Control Unit, "
        "Ministry of "
        "Health, Sri Lanka (Weekly Dengue Update, `www.dengue.health.gov.lk/weekly-report/`).",
        "",
        f"## Verdict: **{'GO' if go else 'NO-GO'}**",
        "",
        md(
            pd.DataFrame(
                [
                    {
                        "criterion": c[0],
                        "required": c[1],
                        "measured": c[2],
                        "met": "yes" if c[3] else "**no**",
                    }
                    for c in crit
                ]
            )
        ),
        "",
    ]
    if not go:
        out += [
            "**The binding failure is history length.** The NDCU site publishes weekly updates "
            "for 2026 "
            f"Weeks 1-{max(r.meta['epi_week'] for r in ok)} only; there is nothing from 2023-2025 "
            f"on the "
            "weekly archive (3 pages, 20 per page), the publications page, or the daily-report "
            "page. "
            f"{run_n} consecutive weeks cannot become {NEED_RUN}. Without history there is no way "
            f"to train "
            "or backtest a rolling-origin model of the flag, so the outlook falls back to the "
            "**district-level leptospirosis outlook from WER** (already parsed, 2022-2026) as "
            "planned. "
            "Older NDCU PDFs may exist elsewhere (e.g. a ReliefWeb mirror); that was **not** "
            "fetched "
            "because it needs your approval.",
            "",
        ]
    out += [
        "## 1. Source and coverage",
        "",
        f"- Archive: `https://www.dengue.health.gov.lk/weekly-report/` and `/page/2/`, `/page/3/` "
        f"(robots.txt allows them; fetched with the polite downloader, 2 s delay). "
        f"{len(results)} PDFs downloaded, all dated 2026.",
        f"- Parsed: **{len(ok)}** of {len(results)}; failed: **{len(failed)}**"
        + (": " + "; ".join(f"{r.file} ({r.reason[:60]})" for r in failed) if failed else "")
        + ".",
        f"- Parsed issues whose high-risk list did not match the count the issue states about "
        f"itself: "
        f"**{len(bad_list)}**"
        + (
            ": "
            + ", ".join(
                f"Wk{r.meta['epi_week']} ({r.meta['parsed_high_risk']} vs "
                f"{r.meta['stated_high_risk']})"
                for r in bad_list
            )
            if bad_list
            else ""
        )
        + ".",
        "",
        md(yr),
        "",
        f"Longest consecutive run of weeks with a parseable list: **{run_n}** "
        f"({run_a} to {run_b + timedelta(days=6) if run_b else None}).",
        "",
        "A list is *parseable* when the number of MOH areas read from Table 2 equals the number "
        "the issue "
        "states in its own text, every area sits under a district heading, and the week passes "
        "the weekday "
        "and printed-week checks.",
        "",
        "## 2. MOH names",
        "",
        f"- {len(names)} distinct (district, printed name) pairs over {len(f)} flag rows.",
        f"- Mapped through `config/moh_crosswalk.csv`: **{mapped_pct:.1f}%** of flag rows "
        f"({mapped_names_pct:.1f}% of distinct names). Of the flag rows, **{manual_pct:.1f}%** "
        f"map through a "
        "hand-curated crosswalk row; the rest map through rows seeded from NDCU's own spellings "
        "(`source=ndcu_seed`).",
        "- **Caveat on that number.** The repository has no independent list of the 364 MOH "
        "areas, so the "
        "crosswalk was seeded from the names NDCU prints (spelling tidied: one space, space "
        "before a "
        "bracket) under the district heading they appear in. That makes names consistent across "
        "weeks "
        "and catches a name appearing under two districts, but it does not prove the names match "
        "the "
        "official MOH list used by anyone else. A 100% here is internal consistency, not external "
        "validation.",
        f"- Unmapped: {len(unmapped)}"
        + (": " + ", ".join(f"{d}/{n}" for d, n in unmapped[:30]) if unmapped else "")
        + ".",
        f"- Names printed under more than one district (left unmapped, not resolved): "
        f"**{len(conflict_detail)}**"
        + (": " + "; ".join(conflict_detail) if conflict_detail else "")
        + ". These are source inconsistencies in the district heading above the name, or a wrong "
        "heading assignment in my reading of a column break; either way they cannot be mapped "
        "without an authoritative list.",
        f"- Likely spelling variants of the same area that were **not** merged (different "
        f"spellings, "
        f"same district): {len(similar)}"
        + (": " + "; ".join(similar) if similar else "")
        + ". Only "
        "spellings that normalise identically (case, spaces, hyphens) are merged, so the "
        "distinct-area "
        "counts below can be slightly too high.",
        "",
        "## 3. Flag statistics (parseable weeks only)",
        "",
        f"- Distinct MOH areas ever flagged: **{n_areas}** of {N_MOH} MOH areas "
        '(WER Vol 53 No 1: "all 364 Medical Officer of Health (MOH) divisions").',
        f"- Areas flagged per week: min {per_week.min()}, median {per_week.median():.0f}, "
        f"max {per_week.max()} ({100 * per_week.median() / N_MOH:.1f}% of {N_MOH} in a median "
        f"week).",
        f"- **Flag base rate** = flagged MOH-weeks / ({N_MOH} MOH x {weeks_parse} parseable "
        f"weeks) = "
        f"**{100 * base_rate:.1f}%**.",
        f"- Persistence (what a 1-week-ahead baseline would score): P(flagged next week | flagged "
        f"now) = "
        f"**{100 * persist:.0f}%**; P(newly flagged next week | not flagged now) = "
        f"**{100 * entry:.1f}%**.",
        "",
        "## 4. District weekly counts (Table 1)",
        "",
        f"- {len(dist)} district-week rows from {len(ok)} issues; the 26 districts add to the "
        f"printed Total "
        f"in {sum(r.meta['district_sum_ok'] for r in ok)} of {len(ok)} issues.",
        "- Columns kept: this week and last week for 2026 (an asterisk marks a revised figure), "
        "the same "
        "weeks of 2025, and the two year-to-date totals. They are in "
        "`data/clean/ndcu_districts.parquet`; "
        "the flags are in `data/clean/ndcu_flags.parquet`.",
        "",
        "## 5. What would make this a GO",
        "",
        f"At least {NEED_RUN} consecutive weekly lists, i.e. issues back to about Nov 2024 or "
        f"earlier, "
        "from NDCU or a faithful mirror. The parser already handles the 2026 layout; older "
        "layouts would "
        "need the same self-checks (stated count vs parsed count) before being trusted. Until "
        "then the "
        "dengue MOH outlook is not buildable with a defensible backtest, and `docs/PLAN.md` "
        "switches to "
        "the leptospirosis fallback.",
        "",
    ]
    REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {REPORT}")
