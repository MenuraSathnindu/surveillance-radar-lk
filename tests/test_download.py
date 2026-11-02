from radar_lk.ingest import download, register
from radar_lk.ingest.download import (
    find_pdf_items,
    find_pdf_links,
    link_years,
    parse_years,
    select_candidates,
    year_filter,
)

HTML = """
<a href="/storage/post/pdfs/vol_53_no_34-english.pdf">WER 34</a>
<a href="/storage/post/pdfs/vol_53_no_34-sinhala.pdf">si</a>
<a href="/storage/post/pdfs/vol_48_no_01-english.pdf">old</a>
<a href="/about">about</a>
"""

PDF_RE = r"(?i)/storage/post/pdfs/.*\.pdf$"


def _row(title, week, dates, name):
    return f"""<li class="product"><div class="product-name"><p title="{title}">{title[:12]}...</p></div>
<div class="product-name"><p>Week {week}</p></div><div class="product-name"><p>{dates}</p></div>
<a href="https://www.epid.gov.lk/storage/post/pdfs/{name}" class="btn">Download</a></li>"""


LISTING = "<ul>" + "".join(
    [
        _row("Topic A 2025", 34, "2026.08.15 - 2026.08.21", "en_6ac49_Vol_53_no_34-english.pdf"),
        _row("Topic B", 1, "2025.12.27 - 2026.01.02", "en_6aa11_Vol_52_no_52-english.pdf"),
        _row("Survey 2022", 46, "2020.11.07 - 2020.11.13", "vol_47_no_46-english_1.pdf"),
        _row("Mystery", 7, "", "en_63ec87e11b430_WER.pdf"),
        _row("Topic C", 5, "2023.02.04 - 2023.02.10", "en_7bb22_WER-sinhala.pdf"),
    ]
) + "</ul>"
SRC = {"pdf_link_regex": PDF_RE, "english_only_regex": r"(?i)(english|^en_|/en_)"}


def test_find_pdf_links():
    links = find_pdf_links(HTML, "https://www.epid.gov.lk/wer", PDF_RE)
    assert len(links) == 3
    assert links[0] == "https://www.epid.gov.lk/storage/post/pdfs/vol_53_no_34-english.pdf"


def test_year_filter_from_volume():
    yrs = parse_years("2022-2026")
    assert year_filter("vol_53_no_34-english.pdf", yrs)       # 2026
    assert not year_filter("vol_48_no_01-english.pdf", yrs)   # 2021
    assert year_filter("en_abc123_report.pdf", yrs)           # unknown year: keep


def test_anchor_text_context_is_the_row_only():
    items = find_pdf_items(LISTING, "https://www.epid.gov.lk/wer", PDF_RE)
    assert len(items) == 5
    assert "2026.08.15 - 2026.08.21" in items[0].text
    assert "2020.11.07" not in items[0].text  # neighbouring rows not included


def test_year_from_date_range_when_url_has_no_year():
    url = "https://www.epid.gov.lk/storage/post/pdfs/en_63ec87e11b430_WER.pdf"
    yrs = parse_years("2022-2026")
    assert link_years(url, "Week 34 2026.08.15 - 2026.08.21") == (2026, {2026})
    assert year_filter(url, yrs, "Week 34 2026.08.15 - 2026.08.21")
    assert not year_filter(url, yrs, "Week 46 2020.11.07 - 2020.11.13")


def test_title_year_is_not_evidence():
    # "2025" in the title must not outvote the dates; only dates and "Vol NN" count
    best, ev = link_years("en_x_WER.pdf", "Immunization survey 2025 Week 46 2020.11.07 - 2020.11.13")
    assert ev == {2020} and best == 2020


def test_new_year_week_keeps_both_years():
    best, ev = link_years("en_x_WER.pdf", "Week 1 2021.12.25 - 2022.01.01")
    assert ev == {2021, 2022}
    assert year_filter("en_x_WER.pdf", parse_years("2022-2026"), "2021.12.25 - 2022.01.01")


def test_select_candidates_filters_and_reports_unknown():
    items, unknown = select_candidates(
        LISTING, "https://www.epid.gov.lk/wer", SRC, parse_years("2022-2026")
    )
    names = [i.url.rsplit("/", 1)[1] for i in items]
    assert names == [
        "en_6ac49_Vol_53_no_34-english.pdf",
        "en_6aa11_Vol_52_no_52-english.pdf",
        "en_63ec87e11b430_WER.pdf",  # year unreadable: kept
    ]
    assert [i.url.rsplit("/", 1)[1] for i in unknown] == ["en_63ec87e11b430_WER.pdf"]


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(download, "MANIFEST", tmp_path / "manifest.csv")
    (tmp_path / "wer").mkdir()
    return tmp_path


def test_register_adds_manual_pdfs_once(monkeypatch, tmp_path):
    raw = _isolate(monkeypatch, tmp_path)
    (raw / "wer" / "a.pdf").write_bytes(b"%PDF-1.4 a")
    (raw / "wer" / "b.pdf").write_bytes(b"%PDF-1.4 b")
    (raw / "wer" / "bad.pdf").write_bytes(b"<html>forbidden</html>")
    assert register.register("wer", raw) == ["wer/a.pdf", "wer/b.pdf"]
    rows = download.load_manifest()
    assert {r["listing_url"] for r in rows.values()} == {"manual"}
    assert all(len(r["sha256"]) == 64 for r in rows.values())
    assert register.register("wer", raw) == []  # idempotent
    assert len(download.load_manifest()) == 2


def test_register_skips_duplicate_content_and_downloaded_files(monkeypatch, tmp_path):
    raw = _isolate(monkeypatch, tmp_path)
    (raw / "wer" / "a.pdf").write_bytes(b"%PDF-1.4 same")
    (raw / "wer" / "copy.pdf").write_bytes(b"%PDF-1.4 same")
    assert register.register("wer", raw) == ["wer/a.pdf"]
