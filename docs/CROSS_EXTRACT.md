# Cross-extraction check (pdfplumber vs PyMuPDF)

Generated 2026-11-02 10:01 UTC by `python scripts/cross_extract.py`.

Every Table 1 cell of every parsed WER issue (26 RDHS + SRI LANKA, every A/B column, T\* and C\*\*) was extracted a second time with PyMuPDF, using its own word boxes, row clustering and cell order, and compared with the pdfplumber parser.

- Cells compared: **177,876** from 241 issues
- Agreement: **100.000%**; disagreements: **0** (all listed in `data/review_queue/cross_extract.csv`)
- Of the agreeing cells, 6 are blank or unreadable in both extractors (e.g. a stray `v` where a digit should be); they stay in review.
- Both libraries read the PDF's embedded text layer, so this rules out parser bugs (row, column and token handling) but not a text layer that differs from the printed page; the hand-check pack covers that.
- Issues not compared: 3
  - `Vol_38_NO_29_English.pdf`: pdfplumber no_table
  - `en_63ec87e11b430_WER.pdf`: pdfplumber no_table
  - `en_66ff7279f1888_Vol_51_no_36-english.pdf`: pdfplumber failed

| year | cells | % agree |
|---|---|---|
| 2021 | 1,404 | 100.000 |
| 2022 | 35,802 | 100.000 |
| 2023 | 36,504 | 100.000 |
| 2024 | 38,070 | 100.000 |
| 2025 | 39,366 | 100.000 |
| 2026 | 26,730 | 100.000 |

## Disagreements

None.
