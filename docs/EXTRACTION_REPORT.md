# WER Table 1 extraction report

Generated 2026-11-02 11:50 UTC by `python -m radar_lk.ingest.parse_wer`.
Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (Weekly Epidemiological Report, Table 1). Source files: `data/raw/wer/*.pdf`, listed with hashes in `data/raw/manifest.csv`. Every row in `data/clean/wer.parquet` carries `source_file`, `source_issue` and `extracted_at`.

## 1. Summary

- PDFs: **244**: parsed **241**, no Table 1 **2**, failed **1**; week overrides applied: **6**
- District-disease-weeks `extraction_valid` (tier 1): **97.06%** (76,440 of 78,754); target 95% met
- Of those, `revised` (tier 2: cross-week identity fails, kept with `revision_delta`): **5.3%** of 75,634 checkable rows
- National source errors (districts kept, national row queued): weekly **155**, cumulative **80**
- Duplicate weeks resolved: **0**
- Rows in review queue: **2,638** (district 2,314)

## 2. Issues processed, per year

| year | files | ok | no_table | failed |
|---|---|---|---|---|
| 2011 | 1 | 0 | 1 | 0 |
| 2021 | 2 | 2 | 0 | 0 |
| 2022 | 51 | 51 | 0 | 0 |
| 2023 | 52 | 52 | 0 | 0 |
| 2024 | 52 | 51 | 0 | 1 |
| 2025 | 52 | 52 | 0 | 0 |
| 2026 | 33 | 33 | 0 | 0 |
| unknown | 1 | 0 | 1 | 0 |
| **total** | 244 | 241 | 2 | 1 |

`year` is the year of the week printed in Table 1 for parsed issues, and the volume year (vol + 1973) for issues that did not parse. 2021 and 2011 are out-of-range files that the site lists under 2022 dates.

**Dropped as before 2022-W01** (parsed, but outside the post-COVID baseline): Vol 48 No 37 (2021-W35), Vol 49 No 1 (2021-W52).

**no_table** (no Table 1 title found on any page; logged and skipped):

- `wer/en_63ec87e11b430_WER.pdf`
- `wer/Vol_38_NO_29_English.pdf`

**failed** (1; nothing from these issues reaches the clean table):

| issue | file | reason |
|---|---|---|
| Vol 51 No 36 | en_66ff7279f1888_Vol_51_no_36-english.pdf | week_number_mismatch: printed week 35 != canonical 2024-W34 (+0) for 2024-08-17..2024-08-23 |

### Week overrides applied (source typos in the printed week)

Each entry exists only where the printed day numbers/weekday, the printed `(Nth Week)`, the front-page range (table week = front page - 7 days), the previous and next issues' weeks and the cumulative values agree on one answer. `parse_wer` still checks weekday and week number against the override. The evidence for each is in `config/sources.yaml`.

| issue | file | week used | status | reason |
|---|---|---|---|---|
| Vol 50 No 2 | en_64100cf21b53d_Vol_50_no_02-english_1.pdf | 2022-12-31 to 2023-01-06 | ok | printed "31st- 06th Jan 2022" but the year is 2023: front page 7-13 Jan 2023, previous issue 24-30 Dec 2022 (W52), next 7-13 Jan 2023 (W02), printed "(1st Week)", Sat start, cum == weekly in 100% of district cells (year-start week) and cum chains to next week in 100%. |
| Vol 50 No 41 | en_658bfc0e47143_Vol_50_no_41-english.pdf | 2023-09-30 to 2023-10-06 | ok | printed "30th- 06th Sep 2023" but 30 Sep-6 Oct: front page 7-13 Oct 2023, previous 23-29 Sep (W39), next 7-13 Oct (W41), printed "(40th Week)", Sat start, cum chains 98%/97%, monotone 99.7%. |
| Vol 51 No 24 | en_6684d253a04fc_Vol_51_no_24-english.pdf | 2024-06-01 to 2024-06-07 | ok | printed "01st - 07th May 2024" (a Wednesday start) but 1-7 June: front page 8-14 June 2024, previous 25-31 May (W22), next 8-14 June (W24), printed "(23rd Week)", cum chains 99%/97%, monotone 100%. |
| Vol 53 No 2 | en_69db13e10917e_Vol_53_no_02-english.pdf | 2025-12-29 to 2026-01-04 | ok | printed "29th - 04th Jan 2025" but the year is 2026: front page 5-11 Jan 2026, previous issue 20-26 Dec 2025 (Sat-Fri), first Monday-Sunday week after the announced switch, printed "(01st Week)", cum == weekly in 93% of cells (same as other year-start weeks), chains to next 93%. |
| Vol 53 No 3 | en_69db15872f0bb_Vol_53_no_03-english.pdf | 2026-01-05 to 2026-01-11 | ok | printed "05th - 11th Jan 2025" but the year is 2026: front page 12-18 Jan 2026, previous 29 Dec-4 Jan, next 12-18 Jan 2026 (W03), Monday start, printed "(02nd Week)", cum chains 93%/100%, monotone 97%. |
| Vol 53 No 32 | en_6abdf20d4de58_Vol_53_no_32-english.pdf | 2026-07-27 to 2026-08-02 | ok | printed "26th - 02nd Aug 2026" but the Monday-Sunday week is 27 Jul-2 Aug: front page 3-9 Aug 2026, previous 20-26 Jul (W30), next 3-9 Aug (W32), printed "(31st Week)", cum chains 100%/100%, monotone 100%. |

**Not settled (no override, still failed):** Vol 51 No 36 (`en_66ff7279f1888_Vol_51_no_36-english.pdf`). Vol 51 No 36 prints the dates of Vol 51 No 35 (17-23 Aug 2024) with its own week number (35). The number, the neighbours and the front page say 24-30 Aug, but its cumulatives chain to the previous week in only 73% of district cells (normal median 98%) and are monotone in 90%, so the evidence does not all agree and the week stays out.

## 3. Validation (two tiers)

**Tier 1, `extraction_valid` (= column `validated`).** The row passes the checks that need only its own issue: for its (week, disease) the 26 districts' cumulative counts add to the printed national cumulative; no count cell is blank or unreadable; completeness and timeliness are percentages (a value outside 0..100 is set to NaN and counted, the counts stay). Only `extraction_valid` rows are in `data/clean/wer.parquet` and may reach the dashboard. If the cumulatives add up but the districts' weekly counts do not add to the printed national weekly, the national weekly is a source error (`note=national_weekly_source_error`); if the weekly counts add up but the cumulatives do not, the national cumulative is (`note=national_cumulative_source_error`). In both cases the district rows are kept and only the national row is queued; if neither adds up the whole group is queued. Each label must also sit on the same text line as its numbers (checked in the parser). Only weeks from 2022-W01 are kept: a deliberate post-COVID baseline.

**Tier 2, `revised`.** The cross-week identity `cum_t = cum_(t-1) + weekly_t` (in a year's first week `cum = weekly`). A failure does **not** remove the row: it sets `revised=True` and `revision_delta = cum_t - (cum_(t-1) + weekly_t)`; `revised` is empty where the previous week is missing. **Weekly counts are kept exactly as printed in that issue** (first-printed). A later issue may raise the cumulative of an earlier week without re-printing the weekly figure, so the radar's weekly series is what a Regional Epidemiologist saw in real time, and `revision_delta` says how much was added afterwards.

District-disease-weeks extracted from parsed issues: **78,754**; extraction_valid: **76,440 = 97.06%**.

### Per year

| year | extraction_valid | review | total | % extraction_valid | tier 2 checkable | revised | % revised |
|---|---|---|---|---|---|---|---|
| 2022 | 15496 | 416 | 15912 | 97.4 | 15106 | 1202 | 8.0 |
| 2023 | 15574 | 650 | 16224 | 96.0 | 15548 | 1460 | 9.4 |
| 2024 | 16926 | 78 | 17004 | 99.5 | 16588 | 700 | 4.2 |
| 2025 | 17264 | 338 | 17602 | 98.1 | 17238 | 516 | 3.0 |
| 2026 | 11180 | 832 | 12012 | 93.1 | 11154 | 100 | 0.9 |

### Per disease

| disease | extraction_valid | review | total | % extraction_valid | % revised | median revision_delta | median abs delta |
|---|---|---|---|---|---|---|---|
| chickenpox | 5980 | 234 | 6214 | 96.2 | 8.3 | 2.0 | 3.0 |
| dengue | 6006 | 208 | 6214 | 96.7 | 15.0 | 13.0 | 21.0 |
| dysentery | 6032 | 182 | 6214 | 97.1 | 4.5 | 1.0 | 2.0 |
| encephalitis | 6006 | 208 | 6214 | 96.7 | 2.4 | 1.0 | 2.0 |
| enteric_fever | 6084 | 130 | 6214 | 97.9 | 1.6 | 1.0 | 1.5 |
| food_poisoning | 6032 | 182 | 6214 | 97.1 | 3.0 | 1.0 | 3.0 |
| human_rabies | 6084 | 130 | 6214 | 97.9 | 1.1 | 1.0 | 1.0 |
| leishmaniasis | 6032 | 182 | 6214 | 97.1 | 5.7 | 2.0 | 5.0 |
| leprosy | 832 | 52 | 884 | 94.1 | 0.0 |  |  |
| leptospirosis | 6006 | 208 | 6214 | 96.7 | 10.3 | 3.0 | 4.0 |
| meningitis | 6006 | 208 | 6214 | 96.7 | 5.4 | 1.0 | 2.0 |
| tuberculosis | 3198 | 104 | 3302 | 96.9 | 3.8 | 1.0 | 8.0 |
| typhus | 6084 | 130 | 6214 | 97.9 | 4.4 | 1.0 | 2.0 |
| viral_hepatitis | 6058 | 156 | 6214 | 97.5 | 3.1 | 1.0 | 3.0 |

`revision_delta` over all 3,978 revised district rows: median 2, median absolute 4, 90th percentile absolute 112; positive in 79% (the cumulative was raised after the weekly figure was printed).

| group | district rows |
|---|---|
| extraction_valid, tier 2 checked, not revised | 71656 |
| extraction_valid, revised (kept, delta recorded) | 3978 |
| extraction_valid, tier 2 unknown (previous week missing) | 806 |
| of all these: note = national_weekly_source_error | 4030 |
| of all these: note = national_cumulative_source_error | 2080 |

## 4. What is in the review queue

| fail_reason | national | rdhs | total |
|---|---|---|---|
| scrambled_weekly_column | 29 | 780 | 809 |
| stale_weekly_copy | 24 | 728 | 752 |
| cum_sum_mismatch | 26 | 676 | 702 |
| national_weekly_source_error | 155 | 0 | 155 |
| group_has_missing_cell | 3 | 127 | 130 |
| national_cumulative_source_error | 80 | 0 | 80 |
| missing_cell | 2 | 3 | 5 |
| stale_weekly_copy;national_cumulative_source_error | 2 | 0 | 2 |
| stale_weekly_copy;national_weekly_source_error | 2 | 0 | 2 |
| scrambled_weekly_column;national_cumulative_source_error | 1 | 0 | 1 |

`cum_sum_mismatch`: for that (week, disease) neither the districts' weekly counts nor their cumulative counts add to the printed national row, so the whole group is unreliable. `national_weekly_source_error` / `national_cumulative_source_error`: only the national row of a group whose districts are consistent (section 5). `missing_cell` / `group_has_missing_cell`: a count cell is blank or unreadable in the PDF; the group cannot be verified and nothing is inferred. Issues that failed to parse (section 2) and issues before 2022-W01 contribute no rows.

## 5. National source errors (districts kept, national row queued)

Two symmetric rules, per (week, disease):

- `national_weekly_source_error`: the districts' cumulative counts add to the printed national cumulative, but their weekly counts do not add to the printed national weekly.
- `national_cumulative_source_error`: the districts' weekly counts add to the printed national weekly, but their cumulative counts do not add to the printed national cumulative.

In both cases the district rows are kept with that `note` and only the national row goes to review. The second rule can also fire when a single district's cumulative carries a fixed offset (see the constant gaps below); its weekly figures, which the radar uses, still add up.

### `national_weekly_source_error`: 155 groups

By year: {2022: 78, 2023: 64, 2024: 1, 2025: 10, 2026: 2}; by disease: {'dengue': 80, 'leptospirosis': 57, 'chickenpox': 13, 'leishmaniasis': 3, 'food_poisoning': 1, 'meningitis': 1}.

The printed national weekly is below the district sum in 100% (median printed/sum = 0.10).

First 25 (all are in `data/review_queue/wer.parquet` under that `fail_reason`):

| week | disease | printed_national_cases | district_sum_cases | printed_national_cum | district_sum_cum | file |
|---|---|---|---|---|---|---|
| 2022-W01 | dengue | 21 | 686 | 2132 | 2132 | vol_49_no_02-english_2.pdf |
| 2022-W01 | leptospirosis | 22 | 221 | 221 | 221 | vol_49_no_02-english_2.pdf |
| 2022-W02 | dengue | 14 | 803 | 3604 | 3604 | vol_49_no_03-english_2.pdf |
| 2022-W02 | leptospirosis | 10 | 101 | 322 | 322 | vol_49_no_03-english_2.pdf |
| 2022-W03 | dengue | 16 | 785 | 5232 | 5232 | vol_49_no_04-english_1.pdf |
| 2022-W03 | leptospirosis | 11 | 114 | 436 | 436 | vol_49_no_04-english_1.pdf |
| 2022-W04 | dengue | 12 | 726 | 6497 | 6497 | vol_49_no_05-english_1.pdf |
| 2022-W05 | dengue | 86 | 742 | 7361 | 7361 | vol_49_no_06-english.pdf |
| 2022-W06 | dengue | 51 | 403 | 7874 | 7874 | vol_49_no_07-english.pdf |
| 2022-W07 | dengue | 71 | 508 | 8589 | 8589 | vol_49_no_08-english_2.pdf |
| 2022-W08 | dengue | 67 | 565 | 9260 | 9260 | vol_49_no_09-english.pdf |
| 2022-W09 | dengue | 54 | 542 | 9802 | 9802 | vol_49_no_10-english.pdf |
| 2022-W10 | dengue | 59 | 594 | 10396 | 10396 | vol_49_no_11-english.pdf |
| 2022-W11 | dengue | 56 | 563 | 10959 | 10959 | vol_49_no_12-english.pdf |
| 2022-W12 | dengue | 62 | 532 | 11584 | 11584 | vol_49_no_13-english.pdf |
| 2022-W13 | dengue | 57 | 481 | 12158 | 12158 | vol_49_no_14-english.pdf |
| 2022-W14 | dengue | 72 | 626 | 12883 | 12883 | vol_49_no_15-english_1.pdf |
| 2022-W15 | dengue | 36 | 367 | 13250 | 13250 | vol_49_no_16-english_1.pdf |
| 2022-W16 | dengue | 96 | 845 | 14214 | 14214 | vol_49_no_17-english_3.pdf |
| 2022-W17 | dengue | 98 | 630 | 15195 | 15195 | vol_49_no_18-english_2.pdf |
| 2022-W17 | leptospirosis | 10 | 100 | 1377 | 1377 | vol_49_no_18-english_2.pdf |
| 2022-W18 | dengue | 90 | 797 | 16124 | 16124 | vol_49_no_19-english_2.pdf |
| 2022-W19 | dengue | 84 | 741 | 16964 | 16964 | vol_49_no_20-english_1.pdf |
| 2022-W20 | dengue | 12 | 594 | 18205 | 18205 | vol_49_no_21-english_3.pdf |
| 2022-W20 | leptospirosis | 16 | 162 | 1714 | 1714 | vol_49_no_21-english_3.pdf |

### `national_cumulative_source_error`: 80 groups

By year: {2022: 23, 2023: 20, 2024: 24, 2025: 8, 2026: 5}; by disease: {'viral_hepatitis': 34, 'tuberculosis': 24, 'typhus': 11, 'chickenpox': 3, 'human_rabies': 3, 'enteric_fever': 2, 'leprosy': 2, 'dengue': 1}.

Constant gaps: tuberculosis 2024: district cumulatives exceed the national by exactly 66 in all 21 weeks; viral_hepatitis 2025: district cumulatives exceed the national by exactly -10 in all 6 weeks. Median printed/sum of the cumulative: 0.95.

First 25 (all are in `data/review_queue/wer.parquet` under that `fail_reason`):

| week | disease | printed_national_cases | district_sum_cases | printed_national_cum | district_sum_cum | file |
|---|---|---|---|---|---|---|
| 2022-W16 | viral_hepatitis | 12 | 12 | 10 | 100 | vol_49_no_17-english_3.pdf |
| 2022-W17 | viral_hepatitis | 8 | 8 | 10 | 108 | vol_49_no_18-english_2.pdf |
| 2022-W18 | viral_hepatitis | 3 | 3 | 11 | 111 | vol_49_no_19-english_2.pdf |
| 2022-W19 | viral_hepatitis | 8 | 8 | 11 | 119 | vol_49_no_20-english_1.pdf |
| 2022-W20 | viral_hepatitis | 9 | 9 | 12 | 128 | vol_49_no_21-english_3.pdf |
| 2022-W21 | viral_hepatitis | 5 | 5 | 14 | 140 | vol_49_no_22-english_1.pdf |
| 2022-W23 | viral_hepatitis | 7 | 7 | 14 | 147 | vol_49_no_24-english_1.pdf |
| 2022-W24 | viral_hepatitis | 6 | 6 | 15 | 155 | vol_49_no_25-english_2.pdf |
| 2022-W25 | viral_hepatitis | 9 | 9 | 16 | 164 | vol_49_no_26-english_2.pdf |
| 2022-W26 | viral_hepatitis | 1 | 1 | 16 | 165 | vol_49_no_27-english.pdf |
| 2022-W27 | viral_hepatitis | 5 | 5 | 17 | 170 | vol_49_no_28-english_2.pdf |
| 2022-W28 | viral_hepatitis | 10 | 10 | 18 | 180 | vol_49_no_29-english_3.pdf |
| 2022-W29 | viral_hepatitis | 12 | 12 | 19 | 195 | vol_49_no_30-english.pdf |
| 2022-W30 | viral_hepatitis | 6 | 6 | 20 | 203 | vol_49_no_31-english_1.pdf |
| 2022-W31 | viral_hepatitis | 13 | 13 | 21 | 216 | vol_49_no_32-english_1.pdf |
| 2022-W32 | viral_hepatitis | 6 | 6 | 22 | 222 | vol_49_no_33-english_2.pdf |
| 2022-W33 | viral_hepatitis | 11 | 11 | 23 | 234 | vol_49_no_34-english_2.pdf |
| 2022-W48 | typhus | 28 | 28 | 101 | 1013 | en_6459f77cb2316_vol_49_no_49-english_2.pdf |
| 2022-W49 | typhus | 38 | 38 | 105 | 1056 | en_6459f7dbd4561_vol_49_no_50-english_1.pdf |
| 2022-W50 | typhus | 38 | 38 | 109 | 1095 | en_6459f8449d423_vol_49_no_51-english_1.pdf |
| 2022-W51 | typhus | 71 | 71 | 116 | 1169 | en_6459f889a4a8c_vol_49_no_52-english_1.pdf |
| 2022-W52 | typhus | 74 | 74 | 124 | 1246 | en_640feff0076ea_Vol_50_no_01-english.pdf |
| 2022-W52 | viral_hepatitis | 4 | 4 | 39 | 390 | en_640feff0076ea_Vol_50_no_01-english.pdf |
| 2023-W15 | viral_hepatitis | 6 | 6 | 10 | 105 | en_6450a83ec365f_Vol_50_no_16-english.pdf |
| 2023-W16 | viral_hepatitis | 7 | 7 | 11 | 113 | en_647d696889d75_Vol_50_no_17-english_2.pdf |

## 5b. Weekly columns copied or scrambled (source errors)

Some issues print a weekly (A) column that repeats the previous week's exactly, while the cumulative column is advanced by the copied figures, so every sum and cumulative check passes. Confirmed on the rendered pages for Vol 53 No 26 vs No 27 (dengue: Colombo 1138, Gampaha 1294, Kandy 472 ... in both). Rule: a (week, disease) group is queued (`stale_weekly_copy`) when at least 8 districts report a non-zero count and at least 80% of them equal the previous week, or when at least 70% of all non-zero district cells of the whole issue repeat (the highest other week scores 42%). The true counts of those weeks are unknown, so nothing is corrected.

| week | disease | scope | repeated / non-zero districts | issue share % |
|---|---|---|---|---|
| 2022-W22 | chickenpox | whole issue | 12 / 14 | 84.0 |
| 2022-W22 | dengue | whole issue | 18 / 25 | 84.0 |
| 2022-W22 | dysentery | whole issue | 7 / 7 | 84.0 |
| 2022-W22 | encephalitis | whole issue | 0 / 0 | 84.0 |
| 2022-W22 | enteric_fever | whole issue | 1 / 1 | 84.0 |
| 2022-W22 | food_poisoning | whole issue | 2 / 2 | 84.0 |
| 2022-W22 | human_rabies | whole issue | 0 / 1 | 84.0 |
| 2022-W22 | leishmaniasis | whole issue | 10 / 11 | 84.0 |
| 2022-W22 | leptospirosis | whole issue | 17 / 20 | 84.0 |
| 2022-W22 | meningitis | whole issue | 4 / 5 | 84.0 |
| 2022-W22 | typhus | whole issue | 6 / 6 | 84.0 |
| 2022-W22 | viral_hepatitis | whole issue | 2 / 2 | 84.0 |
| 2024-W11 | chickenpox | disease column | 20 / 20 | 25.8 |
| 2024-W39 | tuberculosis | disease column | 20 / 20 | 22.0 |
| 2025-W07 | chickenpox | whole issue | 22 / 22 | 87.3 |
| 2025-W07 | dengue | whole issue | 26 / 26 | 87.3 |
| 2025-W07 | dysentery | whole issue | 11 / 11 | 87.3 |
| 2025-W07 | encephalitis | whole issue | 5 / 5 | 87.3 |
| 2025-W07 | enteric_fever | whole issue | 0 / 0 | 87.3 |
| 2025-W07 | food_poisoning | whole issue | 7 / 7 | 87.3 |
| 2025-W07 | human_rabies | whole issue | 0 / 0 | 87.3 |
| 2025-W07 | leishmaniasis | whole issue | 10 / 10 | 87.3 |
| 2025-W07 | leptospirosis | whole issue | 24 / 24 | 87.3 |
| 2025-W07 | meningitis | whole issue | 13 / 13 | 87.3 |
| 2025-W07 | tuberculosis | whole issue | 0 / 20 | 87.3 |
| 2025-W07 | typhus | whole issue | 13 / 13 | 87.3 |
| 2025-W07 | viral_hepatitis | whole issue | 7 / 7 | 87.3 |
| 2026-W26 | dengue | disease column | 26 / 26 | 29.8 |

Second rule, `scrambled_weekly_column`: the weekly column is printed against the wrong rows (confirmed on the rendered page of Vol 53 No 15, 2026-W14: dengue Colombo 9, Matale 256, Nuwara Eliya 113, Kilinochchi 117, where the weeks around read about 300, 20, 6 and 1; the national total and the cumulatives are consistent with the scrambled column). Past-only test: with >= 20 non-zero districts, the rank correlation (Spearman) of this week's district counts with last week's is below 0.3 while last week and the week before agreed (>= 0.7; for dengue the typical week-to-week value is 0.93). Two or more diseases tripping in one week flag the whole issue.

| week | scope | diseases | min_rho |
|---|---|---|---|
| 2026-W03 | disease column | chickenpox | 0.2 |
| 2026-W07 | disease column | chickenpox | 0.1 |
| 2026-W14 | whole issue | chickenpox, dengue, dysentery, encephalitis, enteric_fever, food_poisoning, human_rabies, leishmaniasis, leprosy, leptospirosis, meningitis, tuberculosis, typhus, viral_hepatitis | -0.0 |
| 2026-W24 | whole issue | chickenpox, dengue, dysentery, encephalitis, enteric_fever, food_poisoning, human_rabies, leishmaniasis, leprosy, leptospirosis, meningitis, tuberculosis, typhus, viral_hepatitis | -0.2 |

## 6. Week sequence: gaps and duplicates

| year | weeks present | expected | missing weeks |
|---|---|---|---|
| 2022 | 51 | 1..52 | 43 |
| 2023 | 52 | 1..52 | none |
| 2024 | 51 | 1..52 | 35 |
| 2025 | 52 | 1..52 | none |
| 2026 | 33 | 1..33 | none |

Missing weeks are almost entirely issues that failed to parse (section 2: printed-week typos) or that the website does not list.

### Duplicate weeks (two issues, same week)

None. A misprinted week (wrong month or year) used to look like a duplicate of the real week; the weekday and printed-week checks in section 8 now reject such issues instead.

## 7. Completeness (C**) and timeliness (T*)

**C\*\* is not defined in any of the 244 issues (section 9), so it is used only relatively:** `completeness_low` is true when an RDHS's C\*\* for the week is below that RDHS's own 10th percentile of C\*\* over its past weeks (expanding window, the current week excluded, at least 26 past weeks, so 2022 H1 is empty). No absolute threshold is used. **T\* is for display only**: it steps from 42% to 93% at 2023-W52 (national), so it cannot be compared across years.

Values outside 0..100 were set to NaN (the counts of those rows are kept): C\*\*: 9 area-weeks (9 RDHS), values [194.0, 195.0, 200.0, 1000.0]; T\*: 7 area-weeks, values [152.0, 153.0, 320.0, 330.0, 350.0].

### Per RDHS (C** min / p10 / median over all weeks; completeness_low rate)

| area | weeks | C min | C p10 | C median | weeks with a threshold | completeness_low weeks | % low |
|---|---|---|---|---|---|---|---|
| Ampara | 239 | 14.0 | 93.0 | 100.0 | 210 | 36 | 17.1 |
| Anuradhapura | 239 | 42.0 | 87.8 | 100.0 | 210 | 19 | 9.0 |
| Badulla | 239 | 10.0 | 100.0 | 100.0 | 210 | 14 | 6.7 |
| Batticaloa | 239 | 10.0 | 99.0 | 100.0 | 210 | 15 | 7.1 |
| Colombo | 239 | 10.0 | 93.8 | 100.0 | 210 | 21 | 10.0 |
| Galle | 239 | 10.0 | 99.0 | 100.0 | 210 | 13 | 6.2 |
| Gampaha | 239 | 7.0 | 72.0 | 100.0 | 210 | 4 | 1.9 |
| Hambantota | 239 | 10.0 | 99.0 | 100.0 | 210 | 10 | 4.8 |
| Jaffna | 239 | 80.0 | 88.0 | 93.0 | 210 | 7 | 3.3 |
| Kalmunai | 239 | 10.0 | 99.0 | 100.0 | 210 | 21 | 10.0 |
| Kalutara | 230 | 1.0 | 59.5 | 100.0 | 201 | 10 | 5.0 |
| Kandy | 239 | 10.0 | 97.0 | 100.0 | 210 | 2 | 1.0 |
| Kegalle | 239 | 10.0 | 99.0 | 100.0 | 210 | 20 | 9.5 |
| Kilinochchi | 239 | 10.0 | 99.0 | 100.0 | 210 | 16 | 7.6 |
| Kurunegala | 239 | 10.0 | 97.0 | 100.0 | 210 | 17 | 8.1 |
| Mannar | 239 | 10.0 | 80.0 | 100.0 | 210 | 10 | 4.8 |
| Matale | 239 | 10.0 | 99.0 | 100.0 | 210 | 19 | 9.0 |
| Matara | 239 | 10.0 | 100.0 | 100.0 | 210 | 17 | 8.1 |
| Monaragala | 239 | 10.0 | 99.0 | 100.0 | 210 | 19 | 9.0 |
| Mullaitivu | 239 | 10.0 | 94.0 | 100.0 | 210 | 23 | 11.0 |
| Nuwara Eliya | 239 | 10.0 | 94.0 | 100.0 | 210 | 28 | 13.3 |
| Polonnaruwa | 239 | 72.0 | 88.0 | 99.0 | 210 | 8 | 3.8 |
| Puttalam | 239 | 10.0 | 90.0 | 100.0 | 210 | 20 | 9.5 |
| Ratnapura | 239 | 10.0 | 95.0 | 100.0 | 210 | 8 | 3.8 |
| Trincomalee | 239 | 10.0 | 91.0 | 100.0 | 210 | 8 | 3.8 |
| Vavuniya | 239 | 10.0 | 84.6 | 100.0 | 210 | 5 | 2.4 |

### National row, by year (T* shown only to document the 2023-W52 step)

| epi_year | weeks | C_median | T_median | T_min |
|---|---|---|---|---|
| 2022 | 51 | 95.0 | 17.0 | 5.0 |
| 2023 | 52 | 98.0 | 35.5 | 25.0 |
| 2024 | 51 | 99.0 | 93.0 | 40.0 |
| 2025 | 52 | 99.0 | 94.0 | 65.0 |
| 2026 | 33 | 99.0 | 91.0 | 58.0 |

## 8. What the parser saw

Disease columns per issue: {12: 114, 13: 93, 14: 34} (12 -> 13 with Tuberculosis from Vol 51 No 11 -> 14 with Leprosy from Vol 53 No 1; see docs/LAYOUTS.md).

Printed header spellings mapped to each disease (all explicit aliases in `config/sources.yaml`; an unknown spelling is a hard failure):

- dengue: `Dengue Fever` x240, `Dengue` x1
- dysentery: `Dysentery` x241
- encephalitis: `Encephalitis` x126, `Encephaliti` x80, `Encephalit` x23, `Encephali` x12
- enteric_fever: `En. Fever` x127, `Enteric Fever` x100, `Enteric` x11, `Enteric F.` x3
- food_poisoning: `Food Poi-` x103, `F. Poisoning` x97, `F. Poison-` x30, `Food Poison-` x11
- leptospirosis: `Leptospirosis` x241
- typhus: `Typhus` x143, `Typhus F.` x93, `Typhus Fev.` x4, `Typhus Fe-` x1
- viral_hepatitis: `Viral Hep.` x127, `Viral Hep-` x59, `Viral` x23, `Viral Hepa-` x18, `V. Hep.` x14
- human_rabies: `Human` x100, `H. Rabiies` x93, `H. Rabies` x34, `H. Rabi.` x14
- chickenpox: `Chickenpox` x241
- meningitis: `Meningitis` x241
- leishmaniasis: `Leishmania-` x205, `Leishman.` x34, `Leishmani-` x1, `Leishmaniasis` x1
- tuberculosis: `Tuberculosis` x127
- leprosy: `Leprosy` x34

Cell-level oddities across all parsed issues: {'blank': 4, 'unreadable': 2, 'pct_format': 32}. T*/C** printed as `8%` or `5.5` in `pct_format` cells are read as numbers. Blank/unreadable count cells put their whole (week, disease) group in review. Issues with such cells: Vol 50 No 52 (0 blank, 1 unreadable); Vol 53 No 8 (1 blank, 0 unreadable); Vol 49 No 7 (0 blank, 1 unreadable); Vol 49 No 17 (1 blank, 0 unreadable); Vol 49 No 38 (2 blank, 0 unreadable).

Checks applied to every parsed issue: Table 1 title found by content; RDHS/WRCD header and A/B/T*/C** sub-header found; every disease header mapped to a config id in config order; 26 RDHS rows in canonical order then SRI LANKA; week text internally consistent (start = end - 6 days), correct start weekday (Sat before the Dec 2025 switch, Mon after), and the printed `(Nth Week)` equal to the canonical week (WER numbered 2021 one ahead).

## 9. What do T* and C** mean? (investigation)

**C\*\* is undefined in all 244 issues; we use relative gating only** (`completeness_low`, section 7). T\* is used for display only.

Footnote text under Table 1 in the parsed issues (digits and dates masked), most common first:

- x58 (e.g. Vol 50 No 1): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: N C**-Completeness *`
- x42 (e.g. Vol 50 No 46): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: 358C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the yea`
- x31 (e.g. Vol 50 No 22): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: N C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the year`
- x22 (e.g. Vol 52 No 31): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: N. C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the yea`
- x19 (e.g. Vol 53 No 15): `Source: WRCD module of the EPINET. T*=Timeliness refers to returns received on or before <date>. Total number of reporting units N C**-Completeness; A = Cases reported during the current week; B = Cumulative cases for the year. C**-Completeness;`
- x10 (e.g. Vol 52 No 20): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: 360C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the yea`
- x7 (e.g. Vol 53 No 2): `Source: WRCD module of the EPINET. T*=Timeliness refers to returns received on or before <date>. Total number of reporting units N. Data provided for the current week: N. C**-Completeness; A = Cases reported during the current week; B = Cumulative cases for the year.`
- x5 (e.g. Vol 51 No 1): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: 356C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the yea`

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

## 10. Independent checks

**Second extractor (PyMuPDF, `scripts/cross_extract.py`, details in `docs/CROSS_EXTRACT.md`):**

- Cells compared: **177,876** from 241 issues
- Agreement: **100.000%**; disagreements: **0** (all listed in `data/review_queue/cross_extract.csv`)
- Of the agreeing cells, 6 are blank or unreadable in both extractors (e.g. a stray `v` where a digit should be); they stay in review.
- Both libraries read the PDF's embedded text layer, so this rules out parser bugs (row, column and token handling) but not a text layer that differs from the printed page; the hand-check pack covers that.
- Issues not compared: 3

<!-- handcheck:start -->
## Hand-check (manual verification against the rendered page)

Scored 2026-11-02 from `data/handcheck/v2/handcheck_verified.csv`. Cells checked: **40** of 40; correct: **40**; accuracy **100.0%** (95% Wilson interval 91.2-100.0%).

Pack v3 (10 more cells from issues not used in v2, `data/handcheck/v3/`) is generated but not yet checked; together they make the 50 cells promised in the proposal. Score both with `python scripts/handcheck_score.py data/handcheck/v2/handcheck_verified.csv data/handcheck/v3/handcheck.csv`.
<!-- handcheck:end -->

## 11. Publication lag

Measured without network from the PDFs themselves: lag = PDF `CreationDate` minus the last day of the reporting week printed in Table 1 (`ModDate` equals `CreationDate` in these Microsoft Publisher exports). A second clock, the upload time, is inferred from the website file name `en_<13 hex>_...`, which has the shape of PHP `uniqid()` (first 8 hex digits = Unix seconds); that is an inference from the naming scheme, not documented by the site. Lags outside 0-365 days would be treated as implausible: 0 found; metadata missing in 0 files.

**Creation date (used):**

| epi_year | issues | median days | p25 | p75 | median weeks |
|---|---|---|---|---|---|
| 2022 | 51.0 | 63.0 | 32.5 | 120.5 | 9.0 |
| 2023 | 52.0 | 24.5 | 18.0 | 50.2 | 3.5 |
| 2024 | 51.0 | 39.0 | 26.5 | 52.0 | 5.6 |
| 2025 | 52.0 | 70.5 | 60.8 | 81.0 | 10.1 |
| 2026 | 33.0 | 55.0 | 36.0 | 78.0 | 7.9 |
| all | 239.0 | 53.0 | 30.0 | 75.5 | 7.6 |

**Upload date (corroboration; files named `en_<uniqid>_` only):**

| epi_year | issues | median days | p25 | p75 | median weeks |
|---|---|---|---|---|---|
| 2022 | 9.0 | 158.0 | 144.0 | 172.0 | 22.6 |
| 2023 | 52.0 | 31.0 | 23.2 | 60.2 | 4.4 |
| 2024 | 51.0 | 39.0 | 27.5 | 53.5 | 5.6 |
| 2025 | 52.0 | 70.5 | 61.0 | 81.2 | 10.1 |
| 2026 | 33.0 | 57.0 | 40.0 | 78.0 | 8.1 |
| all | 197.0 | 54.0 | 32.0 | 75.0 | 7.7 |

The 2022 upload lag is long because 2022 issues were re-uploaded in a batch in 2023 (their file names carry 2023 stamps); their creation dates are the better measure. `publication_lag_weeks` in `config/sources.yaml` is the overall median creation lag in weeks (7.6, rounded). Practical meaning: a rise in week t is visible in the WER about two months later, so the radar is a retrospective early-warning check for the Regional Epidemiologist, not a real-time alarm, unless the same table is available to them earlier through EPINET.

## 12. Reproduce

```
python -m radar_lk.ingest.download --source wer --years 2022-2026
python -m radar_lk.ingest.parse_wer
python scripts/cross_extract.py        # second extractor (PyMuPDF), cell-by-cell
python scripts/handcheck.py --version v3 --n 10 --exclude v2   # new pack, never overwrites
python scripts/handcheck_score.py      # after filling the CSV
pytest -q
```
