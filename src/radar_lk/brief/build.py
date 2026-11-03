"""Weekly brief per RDHS: template only (no LLM), Markdown + one-page PDF.

    python -m radar_lk.brief.build                      # latest week, all 26 RDHS
    python -m radar_lk.brief.build --week 2026-W33 --area Puttalam
    python -m radar_lk.brief.build --sample             # docs/sample_brief_<district>.pdf

Six plain lines per RDHS and week, from data/clean only:
  1 anomalies (alerts) with the expected range and percentile
  2 early warnings
  3 held-back signals with the reason (shared label, radar.labels)
  4 persistent signals (2 or more weeks in a row)
  5 the outlook for this week and next week (selected models; leptospirosis, dengue)
  6 one data note (reporting completeness, revisions)
Every number is followed by its source, "(WER Vol/No, week)". Every brief passes the
non-clinical guard (radar_lk.guard) or the build fails.
"""

from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass, field

import pandas as pd

from radar_lk import REPO_ROOT, load_config
from radar_lk import views as v
from radar_lk.guard import assert_nonclinical
from radar_lk.radar import labels as lb

OUT = REPO_ROOT / "data" / "briefs"
OUTLOOK_DISEASES = ("leptospirosis", "dengue")
FOOTER = (
    "Population-level signals for planning and investigation only. No diagnosis, treatment or "
    "prophylaxis advice. Every signal is a prompt for investigation, relative to this "
    "district's own history; counts are under-notified. Sources: Epidemiology Unit, Ministry of "
    "Health, Sri Lanka (Weekly Epidemiological Report); National Dengue Control Unit; "
    "Open-Meteo (CC BY); OCHA HDX boundaries."
)


def week_end(week: str) -> str:
    from datetime import date, timedelta

    y, w = week.split("-W")
    return f"{date.fromisocalendar(int(y), int(w), 1) + timedelta(days=6):%d %b %Y}"


def cite(issue: str, week: str) -> str:
    return f"(WER {issue}, {week})" if issue else f"({week})"


def n0(x) -> str:
    return f"{float(x):.0f}"


def pct(p) -> str:
    """A 0..1 percentile as e.g. '99.9th'; at or above 99.95 'above the 99.9th' (not '100.0th')."""
    p = float(p)
    return "above the 99.9th" if p >= 0.9995 else f"{100 * p:.1f}th"


def cases(x) -> str:
    return f"{n0(x)} case" if n0(x) == "1" else f"{n0(x)} cases"


MODEL_TEXT = {
    "persistence": "the latest reported week (persistence)",
    "climatology": "the usual pattern for this time of year (seasonal climatology)",
    "glm": "a regression model with recent counts, season and rainfall",
    "lightgbm": "a tree model with recent counts, season and rainfall",
}


def dname(d: str) -> str:
    return v.DISEASE_TEXT.get(d, d)


@dataclass
class Brief:
    area: str
    week: str
    issue: str
    lines: list[tuple[str, str]] = field(default_factory=list)  # (heading, text)

    def markdown(self) -> str:
        out = [
            f"# Weekly signal brief: {self.area} RDHS",
            "",
            f"As of reporting week {self.week} (ending {week_end(self.week)}) "
            f"{cite(self.issue, self.week)}. The WER is "
            "published with a lag of about two months, so this describes weeks already past.",
            "",
        ]
        out += [f"- **{h}:** {t}" for h, t in self.lines]
        out += ["", "---", "", FOOTER, ""]
        return "\n".join(out)

    def body(self) -> str:
        return "\n".join(t for _, t in self.lines)


def _alert_text(r) -> str:
    return (
        f"{dname(r.disease)} {cases(r.observed)}, expected about {n0(r.expected)} "
        f"(range up to {n0(r.upper)}), {pct(r.percentile)} percentile "
        f"{cite(r.source_issue, r.week)}"
    )


def _ew_text(r) -> str:
    return (
        f"{dname(r.disease)} {cases(r.observed)}, above its recent level of about "
        f"{n0(r.expected)} (range up to {n0(r.upper)}) but not yet beyond the seasonal range "
        f"{cite(r.source_issue, r.week)}"
    )


def build(area: str, week: str, sw: pd.DataFrame, fc: pd.DataFrame, wer: pd.DataFrame) -> Brief:
    L = int(load_config()["publication_lag_weeks"])
    x = v.signals_at(sw, week)
    x = x[x["area"] == area]
    w = wer[(wer["area"] == area) & (wer["week"] == week)]
    issue = str(w["source_issue"].iloc[0]) if len(w) else ""
    b = Brief(area, week, issue)
    al = x[x["status"] == "alert"]
    b.lines.append(
        (
            "Unusual this week",
            "; ".join(_alert_text(r) for r in al.itertuples())
            if len(al)
            else "no disease is above its expected range for this district and season.",
        )
    )
    ew = x[x["status"] == "early_warning"]
    b.lines.append(
        (
            "Early warnings",
            "; ".join(_ew_text(r) for r in ew.itertuples())
            if len(ew)
            else "none (no disease is rising sharply against its recent weeks).",
        )
    )
    hb = x[x["status"] == "held_back"]
    b.lines.append(
        (
            "Held back",
            "; ".join(
                f"{dname(r.disease)}: {lb.held_back(r.completeness_pct)} "
                f"{cite(r.source_issue, r.week)}"
                for r in hb.itertuples()
            )
            if len(hb)
            else "none (reporting completeness is within this district's usual range).",
        )
    )
    ps = x[(x["status"] != "held_back") & (x["weeks_persisted"].fillna(0) >= 2)]
    b.lines.append(
        (
            "Persistent",
            "; ".join(
                f"{dname(r.disease)} above its expected range for {n0(r.weeks_persisted)} weeks "
                f"in a row {cite(r.source_issue, r.week)}"
                for r in ps.itertuples()
            )
            if len(ps)
            else "no signal has lasted two weeks or more.",
        )
    )
    parts = []
    for d in OUTLOOK_DISEASES:
        o = v.outlook_wide(v.outlook_at(fc, d, week, L), L)
        o = o[o["area"] == area] if len(o) else o
        if o is None or o.empty:
            continue
        r = o.iloc[0]
        wide = r.hi_this > 5 * max(r.count_this, 1) and r.hi_this - r.lo_this > 30
        parts.append(
            f"{dname(d)}: chance of an elevated week {n0(100 * r.p_this)}% this week "
            f"({r.week_this}) and {n0(100 * r.p_next)}% next week ({r.week_next}; elevated "
            f"here means {cases(math.ceil(r.threshold))} or more), from "
            f"{MODEL_TEXT[r.model_this]}; expected about {cases(r.count_this)} this week "
            f"(90% range {n0(r.lo_this)} to {n0(r.hi_this)}"
            + ("; very wide because recent forecasts missed often" if wide else "")
            + f") {cite(r.source_issue, week)}"
        )
    b.lines.append(
        (
            "Outlook",
            "; ".join(parts)
            if parts
            else "no outlook for this week (the outlook backtest starts at 2024-W01).",
        )
    )
    note = "no WER row for this district this week."
    if len(w):
        c = w["completeness_pct"].iloc[0]
        p10 = w["completeness_p10"].iloc[0]
        rv = w[w["revised"].fillna(False).astype(bool)]
        note = (
            f"reporting completeness (C**) {n0(c)}% {cite(issue, week)}"
            + (f", this district's usual low is {n0(p10)}%" if pd.notna(p10) else "")
            + ". "
        )
        if len(rv):
            top = rv.sort_values("revision_delta", ascending=False).iloc[0]
            note += (
                f"Earlier weeks were revised for {len(rv)} diseases; the largest late addition "
                f"was {n0(top.revision_delta)} cases ({dname(top.disease)}) {cite(issue, week)}."
            )
        else:
            note += "No earlier week was revised in this issue."
    b.lines.append(("Data note", note))
    assert_nonclinical(b.markdown(), f"brief {area} {week}")
    return b


# ------------------------------------------------------------------ PDF


def _latin1(s: str) -> str:
    return s.encode("latin-1", "replace").decode("latin-1")


def pdf_bytes(b: Brief) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_margins(16, 14, 16)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(11, 11, 11)
    pdf.cell(0, 9, _latin1(f"Weekly signal brief: {b.area} RDHS"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(82, 81, 78)
    pdf.multi_cell(
        0,
        5,
        _latin1(
            f"As of reporting week {b.week} (ending {week_end(b.week)}) "
            f"{cite(b.issue, b.week)}. The WER is published with "
            "a lag of about two months, so this describes weeks already past."
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)
    for h, t in b.lines:
        pdf.set_text_color(11, 11, 11)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.cell(0, 6, _latin1(h), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5.2, _latin1(t), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
    pdf.ln(2)
    pdf.set_draw_color(195, 194, 183)
    pdf.line(16, pdf.get_y(), 194, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(82, 81, 78)
    pdf.multi_cell(0, 4, _latin1(FOOTER), new_x="LMARGIN", new_y="NEXT")
    if pdf.page_no() > 1:
        raise ValueError(f"brief {b.area} {b.week} does not fit on one page")
    return bytes(pdf.output())


def zip_all(week: str, sw, fc, wer) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for a in sorted(wer["area"].unique()):
            b = build(a, week, sw, fc, wer)
            stem = f"brief_{week}_{a.replace(' ', '_')}"
            z.writestr(f"{stem}.md", b.markdown())
            z.writestr(f"{stem}.pdf", pdf_bytes(b))
    return buf.getvalue()


def load_all():
    sw = v.add_track_record(v.series_weeks(v.load_signals()))
    return sw, v.load_forecasts(), v.load_wer()


def most_interesting(sw: pd.DataFrame, week: str) -> str:
    x = v.signals_at(sw, week)
    score = (
        x.assign(
            s=x["status"].map({"alert": 3, "early_warning": 2, "held_back": 1})
            + (x["weeks_persisted"].fillna(0) >= 2).astype(int)
        )
        .groupby("area")["s"]
        .sum()
    )
    return str(score.idxmax())


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--week", default=None, help="reporting week, e.g. 2026-W33 (default latest)")
    ap.add_argument("--area", default=None)
    ap.add_argument("--sample", action="store_true", help="write docs/sample_brief_<area>.pdf")
    a = ap.parse_args()
    sw, fc, wer = load_all()
    week = a.week or v.weeks_available(sw)[-1]
    if a.sample:
        while v.signals_at(sw, week).empty:
            week = v.add_weeks(week, -1)
        area = a.area or most_interesting(sw, week)
        b = build(area, week, sw, fc, wer)
        p = REPO_ROOT / "docs" / f"sample_brief_{area.replace(' ', '_')}.pdf"
        p.write_bytes(pdf_bytes(b))
        p.with_suffix(".md").write_text(b.markdown(), encoding="utf-8")
        print(f"wrote {p} ({week})")
        return
    out = OUT / week
    out.mkdir(parents=True, exist_ok=True)
    areas = [a.area] if a.area else sorted(wer["area"].unique())
    for ar in areas:
        b = build(ar, week, sw, fc, wer)
        stem = out / f"brief_{week}_{ar.replace(' ', '_')}"
        stem.with_suffix(".md").write_text(b.markdown(), encoding="utf-8")
        stem.with_suffix(".pdf").write_bytes(pdf_bytes(b))
    print(f"wrote {len(areas)} brief(s) to {out}")


if __name__ == "__main__":
    main()
