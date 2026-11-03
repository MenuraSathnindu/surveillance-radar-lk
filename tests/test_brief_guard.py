"""Non-clinical guard and number provenance for the weekly brief and the dashboard text."""

import ast
import re
from pathlib import Path

import numpy as np
import pytest

from radar_lk import guard
from radar_lk import views as v
from radar_lk.brief import build as brief

ROOT = Path(__file__).resolve().parents[1]
WEEKS = ["2026-W33", "2024-W05", "2024-W51"]
CITE = re.compile(r"\(WER Vol \d+ No \d+, \d{4}-W\d{2}\)")
WEEK = re.compile(r"\d{4}-W\d{2}")
NUM = re.compile(r"\d+(?:\.\d+)?")


@pytest.fixture(scope="module")
def data():
    return brief.load_all()


# ------------------------------------------------------------------ guard


def test_guard_catches_clinical_words_but_allows_the_disclaimer():
    assert guard.hits("Start doxycycline for exposed farmers") == ["doxycycline"]
    assert guard.hits("Treatment of cases") == ["Treatment"]
    assert (
        guard.hits("Population-level signals. No diagnosis, treatment or prophylaxis advice.") == []
    )
    assert guard.hits("a threat to the estate sector") == []  # whole words only
    with pytest.raises(guard.NonClinicalError):
        guard.assert_nonclinical("consider prophylaxis", "x")


def _ui_strings() -> str:
    """Every string literal in the dashboard code, plus the shared labels and HEADLINES.md."""
    out = []
    for f in list((ROOT / "app").glob("*.py")) + list((ROOT / "app" / "views").glob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
    from radar_lk.radar import labels

    out += list(labels.labels().values())
    out.append((ROOT / "docs" / "HEADLINES.md").read_text(encoding="utf-8"))
    return "\n".join(out)


def test_dashboard_text_is_nonclinical():
    guard.assert_nonclinical(_ui_strings(), "dashboard text")


def test_every_brief_passes_the_guard(data):
    sw, fc, wer = data
    for week in WEEKS:
        for area in sorted(wer["area"].unique()):
            b = brief.build(area, week, sw, fc, wer)  # raises on any clinical word
            assert len(b.lines) == 6
            if week == WEEKS[0]:
                assert brief.pdf_bytes(b)[:5] == b"%PDF-"  # raises if it needs a second page


def test_brief_build_fails_on_clinical_text(data, monkeypatch):
    sw, fc, wer = data
    monkeypatch.setattr(brief, "FOOTER", brief.FOOTER + " Give doxycycline.")
    with pytest.raises(guard.NonClinicalError):
        brief.build("Galle", "2026-W33", sw, fc, wer)


# ------------------------------------------------------------------ provenance


def _fmt(vals, pct=False, one=False):
    out = set()
    for x in vals:
        if x is None or (isinstance(x, float) and np.isnan(x)):
            continue
        x = float(x)
        if pct:
            out.add(f"{100 * min(x, 0.999):.1f}" if one else f"{100 * x:.0f}")
        else:
            out.add(f"{x:.0f}")
    return out


def allowed_numbers(area, week, sw, fc, wer) -> set[str]:
    """Every number the brief may print for (area, week), formatted as printed, read straight
    from the source parquet rows of that district and week."""
    s = sw[(sw["area"] == area) & (sw["week"] == week)]
    w = wer[(wer["area"] == area) & (wer["week"] == week)]
    f = fc[(fc["area"] == area) & (fc["origin_week"] == week)]
    ok = set()
    for c in ("observed", "expected", "upper", "weeks_persisted", "completeness_pct"):
        ok |= _fmt(s[c])
    ok |= _fmt(s["percentile"], pct=True, one=True)
    ok |= _fmt(w["completeness_pct"]) | _fmt(w["completeness_p10"]) | _fmt(w["revision_delta"])
    ok.add(str(int(w["revised"].fillna(False).astype(bool).sum())))
    for c in ("pred_count", "lo80", "hi80", "lo90", "hi90", "lo80_aci", "hi80_aci",
              "lo90_aci", "hi90_aci", "elevated_threshold"):
        ok |= _fmt(f[c])
    ok |= _fmt(f["p_elevated"], pct=True) | _fmt(f["p_display"], pct=True)
    ok |= {str(int(np.ceil(x))) for x in f["elevated_threshold"].dropna()}  # "N or more"
    ok.add("90")  # the interval's stated level ("90% range"), a label, not a data value
    return ok


def test_every_number_in_a_brief_is_in_the_source_parquet(data):
    sw, fc, wer = data
    checked = 0
    for week in WEEKS:
        for area in sorted(wer["area"].unique()):
            b = brief.build(area, week, sw, fc, wer)
            body = WEEK.sub(" ", CITE.sub(" ", b.body())).replace("C**", "")
            nums = NUM.findall(body)
            ok = allowed_numbers(area, week, sw, fc, wer)
            bad = [n for n in nums if n not in ok]
            assert not bad, (area, week, bad, body)
            checked += len(nums)
    assert checked > 200


def test_every_number_in_a_brief_is_cited(data):
    sw, fc, wer = data
    b = brief.build("Galle", "2026-W33", sw, fc, wer)
    for _, text in b.lines:
        for part in text.split("; "):
            if NUM.search(WEEK.sub("", CITE.sub("", part))):
                assert CITE.search(text), text


def test_sample_brief_exists_and_is_one_page():
    pdfs = list((ROOT / "docs").glob("sample_brief_*.pdf"))
    assert pdfs
    head = pdfs[0].read_bytes()[:5]
    assert head == b"%PDF-"
    assert v.TIER_TEXT  # views importable without the pipeline stack
