from radar_lk.ingest.download import find_pdf_links, parse_years, year_filter

HTML = """
<a href="/storage/post/pdfs/vol_53_no_34-english.pdf">WER 34</a>
<a href="/storage/post/pdfs/vol_53_no_34-sinhala.pdf">si</a>
<a href="/storage/post/pdfs/vol_48_no_01-english.pdf">old</a>
<a href="/about">about</a>
"""


def test_find_pdf_links():
    links = find_pdf_links(HTML, "https://www.epid.gov.lk/wer", r"(?i)/storage/post/pdfs/.*\.pdf$")
    assert len(links) == 3
    assert links[0] == "https://www.epid.gov.lk/storage/post/pdfs/vol_53_no_34-english.pdf"


def test_year_filter_from_volume():
    yrs = parse_years("2022-2026")
    assert year_filter("vol_53_no_34-english.pdf", yrs)       # 2026
    assert not year_filter("vol_48_no_01-english.pdf", yrs)   # 2021
    assert year_filter("en_abc123_report.pdf", yrs)           # unknown year: keep
