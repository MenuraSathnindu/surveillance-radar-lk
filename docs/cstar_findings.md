### Findings (hand-written 2 Nov 2026, from all 244 PDFs)

**The WER never defines C\*\*.** Searched every page of all 244 files (printed text and the rotated Table 1 text) for *complete*, *timel*, *WRCD*, *reporting unit*, *weekly return*. I also looked at the rendered page, because I first suspected the text layer was cutting the footnote: it is not. The footnote really ends at the bare label.

- 2022-2025 footnote, e.g. `vol_49_no_26-english_2.pdf` p3 (same wording in most 2022-2025 issues):
  > Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before 24th June, 2022 Total number of reporting units 361 Number of reporting units data provided for the current week: 308 C\*\*-Completeness

- 2026 footnote, e.g. `en_6a6399f5cc4a7_Vol_53_no_26-english.pdf` p3:
  > Source: WRCD module of the EPINET. T\*=Timeliness refers to returns received on or before 21st June, 2026. Total number of reporting units 360 C\*\*-Completeness; A = Cases reported during the current week; B = Cumulative cases for the year. C\*\*-Completeness;

  So **T\*** is defined (returns received on or before the stated date, which is the last day of the table week) but only as a phrase; **C\*\*** is only named "Completeness". Neither says what is counted (units? returns? diseases?) or what the denominator is.

- A 2011 predecessor table, `Vol_38_NO_29_English.pdf` p4 (Table 4, 28th week of 2011), had the columns *Returns Received* and *Timely\*\** and the footnote: "\*\*Timely refers to returns received on or before 15th July, 2011 Total number of reporting units =327. Number of reporting units data provided for the current week: 287". Its national row ends in `88`, and 287 / 327 = 87.8 %. That suggests the older "returns received" percentage was units-that-reported over total units. One issue, an old layout: a hint only.

- Feature articles mention the words but never define the Table 1 columns:
  - `en_69afa77f13c32_Vol_53_no_01-english.pdf` p1: "In 2025, the national e-Surveillance system achieved near 100% timeliness and completeness across all 364 Medical Officer of Health (MOH) divisions."
  - `en_67c181e537afa_Vol_52_no_01-english.pdf` p1: "The completeness and the timeliness of the system is near 100%." (the 2024 review, in `en_65b8d3689b762_Vol_51_no_01-english.pdf`, says only "completeness ... near 100%")
  - `en_68aca1e16f16d_Vol_52_no_23-english.pdf` (EPINET data-quality article): "Completeness - All required fields and datasets should be filled in fully." / "Timeliness - Data should be submitted according to the reporting schedule." and "Completeness and timeliness reports - Summarise reporting rates by facility or district". These are general data-quality principles, not the Table 1 definition.

**What the numbers show** (computed over the parsed issues; 204 print a "data provided" count):

- National C\*\* is **not** `units that provided data / total units`: mean absolute difference 4.3 points (e.g. Vol 49 No 26: 308/361 = 85 %, printed C\*\* = 94 %). It is close to, but not equal to, the unweighted mean of the 26 district C\*\* values (mean absolute difference 1.3).
- National T\* equals, to about one point, the mean of the 26 district T\* values (mean absolute difference 1.1; correlation 0.998). So the national row is an aggregate of the district rows.
- **T\* is not comparable across years.** National median T\*: 2022 17 %, 2023 35.5 %, 2024 93 %, 2025 94 %, 2026 91.5 %. Within 2023 it creeps up week after week (28 % in W02 to 44 % in W45), then steps from 42 % to 93 % at 2023-W52 and stays at about 90-95 %. The footnote wording did not change. A slow drift followed by one step looks like a change in how the value is computed rather than a change in behaviour, but the PDFs do not say. National C\*\* is stable (median 95 % in 2022 to 99 % in 2024-25).
- C\*\* above 100 is printed (Kalutara 200, 195, 194 in Vol 52 Nos 23, 38, 39); those rows go to review as `pct_out_of_range`.

**Conclusion: still unclear.** The most defensible reading is that C\*\* is the share of expected weekly returns received for that RDHS and week, and T\* the share received by the Friday cut-off, but the PDFs do not confirm the numerator, denominator or whether late returns count towards C\*\*. Do not describe C\*\* more precisely than "reporting completeness as printed by the Epidemiology Unit" until the Unit confirms. For gating alerts, C\*\* is the usable signal; T\* should not be used without a per-year baseline.
