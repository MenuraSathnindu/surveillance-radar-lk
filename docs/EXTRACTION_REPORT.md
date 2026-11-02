# WER Table 1 extraction report

Generated 2026-11-02 05:44 UTC by `python -m radar_lk.ingest.parse_wer`.
Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (Weekly Epidemiological Report, Table 1). Source files: `data/raw/wer/*.pdf`, listed with hashes in `data/raw/manifest.csv`. Every row in `data/clean/wer.parquet` carries `source_file`, `source_issue` and `extracted_at`.

## 1. Summary

- PDFs: **244**: parsed **235**, no Table 1 **2**, failed **7**
- District-disease-weeks validated: **90.57%** (70,033 of 77,324); target 95% **not met**
- `source_total_error` cases (printed national total wrong, districts kept): **33**
- Duplicate weeks resolved: **0**
- Rows in review queue: **8,000** (district 7,291)

## 2. Issues processed, per year

| year | files | ok | no_table | failed |
|---|---|---|---|---|
| 2011 | 1 | 0 | 1 | 0 |
| 2021 | 2 | 2 | 0 | 0 |
| 2022 | 51 | 51 | 0 | 0 |
| 2023 | 52 | 50 | 0 | 2 |
| 2024 | 52 | 50 | 0 | 2 |
| 2025 | 52 | 52 | 0 | 0 |
| 2026 | 33 | 30 | 0 | 3 |
| unknown | 1 | 0 | 1 | 0 |
| **total** | 244 | 235 | 2 | 7 |

`year` is the year of the week printed in Table 1 for parsed issues, and the volume year (vol + 1973) for issues that did not parse. 2021 and 2011 are out-of-range files that the site lists under 2022 dates.

**no_table** (no Table 1 title found on any page; logged and skipped):

- `wer/en_63ec87e11b430_WER.pdf`
- `wer/Vol_38_NO_29_English.pdf`

**failed** (7; nothing from these issues reaches the clean table):

| issue | file | reason |
|---|---|---|
| Vol 50 No 2 | en_64100cf21b53d_Vol_50_no_02-english_1.pdf | week_weekday: Fri 2021-12-31 to 2022-01-06 starts on Friday, WER weeks then started on Saturday |
| Vol 50 No 41 | en_658bfc0e47143_Vol_50_no_41-english.pdf | week_text_inconsistent: '30th– 06th Sep 2023 ': start day 30 != 2023-08-31 |
| Vol 51 No 24 | en_6684d253a04fc_Vol_51_no_24-english.pdf | week_weekday: Wed 2024-05-01 to 2024-05-07 starts on Wednesday, WER weeks then started on Saturday |
| Vol 51 No 36 | en_66ff7279f1888_Vol_51_no_36-english.pdf | week_number_mismatch: printed week 35 != canonical 2024-W34 (+0) for 2024-08-17..2024-08-23 |
| Vol 53 No 2 | en_69db13e10917e_Vol_53_no_02-english.pdf | week_weekday: Sun 2024-12-29 to 2025-01-04 starts on Sunday, WER weeks then started on Saturday |
| Vol 53 No 3 | en_69db15872f0bb_Vol_53_no_03-english.pdf | week_weekday: Sun 2025-01-05 to 2025-01-11 starts on Sunday, WER weeks then started on Saturday |
| Vol 53 No 32 | en_6abdf20d4de58_Vol_53_no_32-english.pdf | week_text_inconsistent: '26th – 02nd Aug 2026 ': start day 26 != 2026-07-27 |

### Source typos in the printed week (not corrected)

These issues print a week that is impossible or contradicts the issue's own numbering. They are not guessed; to accept a correction add it to `wer_calendar.week_overrides` in `config/sources.yaml`. The front-page line (separate from the table) is shown as corroboration only: in every parsed issue the table week is the 7 days before the front-page range.

| issue | printed in Table 1 | front page |
|---|---|---|
| Vol 50 No 2 |  Fri 2021-12-31 to 2022-01-06 starts on Friday, WER weeks then started on Saturday | Vol. 50 No. 02 07th– 13th Jan 2023 Ocean Pollution |
| Vol 50 No 41 |  '30th– 06th Sep 2023 ': start day 30 != 2023-08-31 | Vol. 50 No. 41 07th– 13th Oct 2023 Ethical considerations in |
| Vol 51 No 24 |  Wed 2024-05-01 to 2024-05-07 starts on Wednesday, WER weeks then started on Saturday | Vol. 51 No. 24 08th – 14th June 2024 Human Rabies – Part III |
| Vol 51 No 36 |  printed week 35 != canonical 2024-W34 (+0) for 2024-08-17..2024-08-23 | Vol. 51 No. 36 31st – 06th Sep 2024 Brucellosis - Part II Ph |
| Vol 53 No 2 |  Sun 2024-12-29 to 2025-01-04 starts on Sunday, WER weeks then started on Saturday | Vol. 53 No. 02 05th – 11th Jan 2026 Flashback 2025: Digital |
| Vol 53 No 3 |  Sun 2025-01-05 to 2025-01-11 starts on Sunday, WER weeks then started on Saturday | Vol. 53 No. 03 12th – 18th Jan 2026 Nipah Virus in South Asi |
| Vol 53 No 32 |  '26th – 02nd Aug 2026 ': start day 26 != 2026-07-27 | Vol. 53 No. 32 03rd – 09th Aug 2026 The EPI Coverage Assessm |

## 3. Validation

District-disease-weeks extracted from parsed issues: **77,324**; validated: **70,033 = 90.57%** (target 95%: **NOT MET**).

A district-disease-week is one RDHS x disease x week. Validated means it passed the sum check (districts add to the printed national total) and, where the previous week is present, the cumulative check; it is in `data/clean/wer.parquet`. Everything else is in `data/review_queue/wer.parquet` with `fail_reason`. Issues that failed to parse contribute no rows to either count (see section 2).

### Validated, per year

| year | validated | not validated | total | % validated |
|---|---|---|---|---|
| 2021 | 546 | 78 | 624 | 87.5 |
| 2022 | 13503 | 2409 | 15912 | 84.9 |
| 2023 | 12468 | 3132 | 15600 | 79.9 |
| 2024 | 15888 | 778 | 16666 | 95.3 |
| 2025 | 16814 | 788 | 17602 | 95.5 |
| 2026 | 10814 | 106 | 10920 | 99.0 |

### Validated, per disease

| disease | validated | not validated | total | % validated |
|---|---|---|---|---|
| chickenpox | 5281 | 829 | 6110 | 86.4 |
| dengue | 3924 | 2186 | 6110 | 64.2 |
| dysentery | 5733 | 377 | 6110 | 93.8 |
| encephalitis | 5844 | 266 | 6110 | 95.6 |
| enteric_fever | 5975 | 135 | 6110 | 97.8 |
| food_poisoning | 5809 | 301 | 6110 | 95.1 |
| human_rabies | 6006 | 104 | 6110 | 98.3 |
| leishmaniasis | 5662 | 448 | 6110 | 92.7 |
| leprosy | 804 | 2 | 806 | 99.8 |
| leptospirosis | 4602 | 1508 | 6110 | 75.3 |
| meningitis | 5655 | 455 | 6110 | 92.6 |
| tuberculosis | 3102 | 96 | 3198 | 97.0 |
| typhus | 5787 | 323 | 6110 | 94.7 |
| viral_hepatitis | 5849 | 261 | 6110 | 95.7 |

### How the validated rows were validated

| check | district rows |
|---|---|
| sum ok and cumulative ok | 66471 |
| sum ok, cumulative unknown (previous week missing / first week) | 2704 |
| kept via source_total_error rule (note=national_total_source_error) | 858 |

## 4. Why rows failed (top reasons first)

| fail_reason | national | rdhs | total | share of all review rows |
|---|---|---|---|---|
| cumulative_mismatch; | 520 | 3078 | 3598 | 45.0 |
| sum_mismatch; | 27 | 2753 | 2780 | 34.8 |
| sum_mismatch;cumulative_mismatch; | 124 | 1173 | 1297 | 16.2 |
| pct_out_of_range; | 0 | 157 | 157 | 2.0 |
| group_has_missing_cell; | 3 | 127 | 130 | 1.6 |
| source_total_error;sum_mismatch;cumulative_mismatch; | 33 | 0 | 33 | 0.4 |
| missing_cell; | 2 | 3 | 5 | 0.1 |

`cumulative_mismatch`: cum_t != cum_(t-1) + weekly_t for that row. `sum_mismatch`: the 26 districts do not add to the printed SRI LANKA row for that (week, disease), which fails every row of that group. `source_total_error`: the rule in section 5. `missing_cell` / `group_has_missing_cell`: a count cell is blank or unreadable in the PDF, so the group cannot be verified and nothing is inferred. `pct_out_of_range`: completeness or timeliness outside 0..100 in the PDF.

### Cumulative-check failures: what they look like

4,284 of 74,302 checkable district rows (5.8%) fail `cum_t = cum_(t-1) + weekly_t`. `gap` = cum_t - (cum_(t-1) + weekly_t):

- median |gap| = 4; 75th percentile = 19; 90th = 110
- gap > 0 in 74% of failures, gap < 0 in 26%

| epi_year | checkable rows | failing | % failing |
|---|---|---|---|
| 2022 | 15598 | 1314 | 8.4 |
| 2023 | 14974 | 1536 | 10.3 |
| 2024 | 15964 | 728 | 4.6 |
| 2025 | 17576 | 654 | 3.7 |
| 2026 | 10190 | 52 | 0.5 |

| disease | checkable rows | failing | % failing |
|---|---|---|---|
| dengue | 5876 | 954 | 16.2 |
| leptospirosis | 5874 | 668 | 11.4 |
| chickenpox | 5876 | 553 | 9.4 |
| leishmaniasis | 5876 | 366 | 6.2 |
| meningitis | 5876 | 349 | 5.9 |
| dysentery | 5876 | 296 | 5.0 |
| typhus | 5876 | 293 | 5.0 |
| viral_hepatitis | 5874 | 202 | 3.4 |
| food_poisoning | 5876 | 194 | 3.3 |
| tuberculosis | 3068 | 91 | 3.0 |
| encephalitis | 5874 | 156 | 2.7 |
| enteric_fever | 5876 | 96 | 1.6 |
| human_rabies | 5876 | 66 | 1.1 |
| leprosy | 728 | 0 | 0.0 |

Weeks where more than 30% of checkable district rows fail (an issue-level problem rather than scattered cells): 2022-W21 (36%), 2022-W22 (31%), 2022-W38 (41%), 2022-W52 (31%), 2023-W42 (37%), 2023-W46 (52%), 2023-W51 (30%), 2025-W06 (45%), 2025-W07 (41%).

Reading: failures are mostly small (median gap a handful of cases), mostly positive, highest for the highest-volume diseases (dengue, leptospirosis, chickenpox) and lower in 2024-26 than in 2022-23. That pattern is *consistent with* cumulative columns being revised for late-notified cases after the weekly figure was printed, but the PDFs do not say so, so this is a hypothesis, not a finding. It means the strict identity may reject correct rows.

### Sum-check failures: what they look like

187 of 2974 (week, disease) groups (6.3%) fail the sum check. districts-sum minus printed-national: median 196, 94% positive (the printed national is *smaller* than the districts).

| epi_year | failing groups | groups | % failing |
|---|---|---|---|
| 2021 | 3 | 24 | 12.5 |
| 2022 | 83 | 612 | 13.6 |
| 2023 | 87 | 600 | 14.5 |
| 2024 | 2 | 641 | 0.3 |
| 2025 | 10 | 677 | 1.5 |
| 2026 | 2 | 420 | 0.5 |

| disease | failing groups |
|---|---|
| dengue | 85 |
| leptospirosis | 62 |
| chickenpox | 15 |
| leishmaniasis | 6 |
| meningitis | 5 |
| food_poisoning | 4 |
| encephalitis | 3 |
| dysentery | 3 |

### Failing sum groups, split by what the cumulative columns say

| class | groups | what it means |
|---|---|---|
| A | 33 | national cumulative = district cumulative sum, all 26 districts pass their own cumulative check, national fails its own (rule in section 5 fires) |
| B | 7 | national cumulative = district cumulative sum, no district fails, but some district's previous week is missing so its cumulative check is unknown |
| C | 118 | national cumulative = district cumulative sum, but at least one district fails its own cross-week cumulative check |
| D | 27 | national cumulative != district cumulative sum |

In classes A-C the *cumulative* columns of the districts add up to the national cumulative, so only the printed national *weekly* figure disagrees; in the rule-A cases the printed weekly is far below the district sum (e.g. 16 printed against 163 for 2022-W25 leptospirosis). Class D (and e.g. every disease of 2023-W41) points at a wrong national row or week and stays in review.

### What-if (NOT applied): which rule keeps the rate below target

- current rules (weekly sum check + cross-week cumulative check + pct range): 90.57%
- only checks that live inside one issue (districts' cumulative sum = national cumulative, pct range), with the cross-week cumulative identity reported but not enforced: 96.00%

The gap between the two is the cross-week identity `cum_t = cum_(t-1) + weekly_t`, which is the largest single failure class. Whether a row that fails only that identity may reach the dashboard (flagged) or must stay in review is a policy decision, not a parser fix.

## 5. `source_total_error` cases

Rule: for a (week, disease) that fails the sum check, if every district row passes its own cumulative check *and* the national row fails its own cumulative check, the districts are internally consistent and only the printed national figure is wrong. The district rows are kept (`validated=True`, `note=national_total_source_error`); only the national row goes to the review queue. If any district's cumulative status is unknown or failing, the rule does not fire and the whole group stays in review.

Count: **33**.

| week | disease | printed_national_cases | district_sum_cases | printed_national_cum | district_sum_cum | file |
|---|---|---|---|---|---|---|
| 2022-W01 | leptospirosis | 22 | 221 | 221 | 221 | vol_49_no_02-english_2.pdf |
| 2022-W02 | leptospirosis | 10 | 101 | 322 | 322 | vol_49_no_03-english_2.pdf |
| 2022-W03 | leptospirosis | 11 | 114 | 436 | 436 | vol_49_no_04-english_1.pdf |
| 2022-W09 | dengue | 54 | 542 | 9802 | 9802 | vol_49_no_10-english.pdf |
| 2022-W10 | dengue | 59 | 594 | 10396 | 10396 | vol_49_no_11-english.pdf |
| 2022-W11 | dengue | 56 | 563 | 10959 | 10959 | vol_49_no_12-english.pdf |
| 2022-W15 | dengue | 36 | 367 | 13250 | 13250 | vol_49_no_16-english_1.pdf |
| 2022-W17 | leptospirosis | 10 | 100 | 1377 | 1377 | vol_49_no_18-english_2.pdf |
| 2022-W20 | leptospirosis | 16 | 162 | 1714 | 1714 | vol_49_no_21-english_3.pdf |
| 2022-W23 | leptospirosis | 13 | 135 | 2166 | 2166 | vol_49_no_24-english_1.pdf |
| 2022-W25 | leptospirosis | 16 | 163 | 2513 | 2513 | vol_49_no_26-english_2.pdf |
| 2022-W28 | leptospirosis | 11 | 110 | 2792 | 2792 | vol_49_no_29-english_3.pdf |
| 2022-W31 | leptospirosis | 10 | 102 | 3234 | 3234 | vol_49_no_32-english_1.pdf |
| 2022-W35 | dengue | 46 | 461 | 44185 | 44185 | vol_49_no_36-english_1.pdf |
| 2022-W45 | dengue | 56 | 567 | 54748 | 54748 | en_6459f68898aa0_vol_49_no_46-english_1.pdf |
| 2022-W45 | leptospirosis | 16 | 165 | 5174 | 5174 | en_6459f68898aa0_vol_49_no_46-english_1.pdf |
| 2023-W25 | leptospirosis | 17 | 175 | 4798 | 4798 | en_64b4cbff23f46_Vol_50_no_26-english_2.pdf |
| 2023-W25 | meningitis | 3 | 30 | 638 | 638 | en_64b4cbff23f46_Vol_50_no_26-english_2.pdf |
| 2023-W26 | leptospirosis | 14 | 147 | 4945 | 4945 | en_64c772c1952be_Vol_50_no_27-english_1.pdf |
| 2023-W28 | leptospirosis | 15 | 153 | 5326 | 5326 | en_64c78901a4223_Vol_50_no_29-english_1.pdf |
| 2023-W32 | chickenpox | 12 | 124 | 3315 | 3315 | en_6592f77ef271b_Vol_50_no_33-english.pdf |
| 2023-W32 | leishmaniasis | 11 | 111 | 2270 | 2270 | en_6592f77ef271b_Vol_50_no_33-english.pdf |
| 2023-W33 | chickenpox | 14 | 140 | 3455 | 3455 | en_6592f6eec67ef_Vol_50_no_34-english.pdf |
| 2023-W33 | leptospirosis | 16 | 165 | 6216 | 6216 | en_6592f6eec67ef_Vol_50_no_34-english.pdf |
| 2023-W34 | leptospirosis | 14 | 142 | 6358 | 6358 | en_6507d4a364766_Vol_50_no_35-english_1.pdf |
| 2025-W01 | dengue | 111 | 1118 | 1118 | 1118 | en_67c96592b4988_Vol_52_no_02-english.pdf |
| 2025-W04 | dengue | 111 | 1116 | 4486 | 4486 | en_67d929c3161cb_Vol_52_no_05-english.pdf |
| 2025-W05 | dengue | 102 | 1025 | 5511 | 5511 | en_67de6da079b22_Vol_52_no_06-english.pdf |
| 2025-W18 | dengue | 129 | 1290 | 18067 | 18067 | en_6872ab13dcf76_Vol_52_no_19-english.pdf |
| 2025-W20 | dengue | 137 | 1379 | 20784 | 20784 | en_68a41de1ba48e_Vol_52_no_21-english.pdf |
| 2025-W52 | dengue | 144 | 1443 | 50501 | 50501 | en_69afa77f13c32_Vol_53_no_01-english.pdf |
| 2026-W23 | leishmaniasis | 11 | 115 | 1902 | 1902 | en_6a4f3700e64f1_Vol_53_no_24-english.pdf |
| 2026-W33 | leishmaniasis | 12 | 127 | 2736 | 2736 | en_6ac4966950695_Vol_53_no_34-english.pdf |

By year: {2022: 16, 2023: 9, 2025: 6, 2026: 2}.

## 6. Week sequence: gaps and duplicates

| year | weeks present | expected | missing weeks |
|---|---|---|---|
| 2021 | 2 | n/a (out of range) |  |
| 2022 | 51 | 1..52 | 43 |
| 2023 | 50 | 1..52 | 1, 40 |
| 2024 | 50 | 1..52 | 23, 35 |
| 2025 | 52 | 1..52 | none |
| 2026 | 30 | 1..33 | 1, 2, 31 |

Missing weeks are almost entirely issues that failed to parse (section 2: printed-week typos) or that the website does not list.

### Duplicate weeks (two issues, same week)

None. A misprinted week (wrong month or year) used to look like a duplicate of the real week; the weekday and printed-week checks in section 8 now reject such issues instead.

## 7. Completeness (C**) and timeliness (T*) per RDHS

From the parsed issues (one value per RDHS per week, values outside 0..100 excluded). min / p10 / median over all weeks. **T\* is not comparable across years** (see national table below).

| area | weeks | C min | C p10 | C median | T min | T p10 | T median |
|---|---|---|---|---|---|---|---|
| Ampara | 235 | 14.0 | 93.0 | 100.0 | 5.0 | 9.0 | 71.0 |
| Anuradhapura | 235 | 42.0 | 88.0 | 100.0 | 0.0 | 8.4 | 73.0 |
| Badulla | 235 | 10.0 | 100.0 | 100.0 | 0.0 | 13.4 | 81.0 |
| Batticaloa | 235 | 10.0 | 99.0 | 100.0 | 0.0 | 28.4 | 79.0 |
| Colombo | 235 | 10.0 | 94.0 | 100.0 | 0.0 | 13.0 | 88.0 |
| Galle | 235 | 10.0 | 99.0 | 100.0 | 0.0 | 10.0 | 70.0 |
| Gampaha | 235 | 7.0 | 72.0 | 100.0 | 0.0 | 1.0 | 67.0 |
| Hambantota | 235 | 10.0 | 99.0 | 100.0 | 0.0 | 13.0 | 85.0 |
| Jaffna | 235 | 80.0 | 88.0 | 93.0 | 20.0 | 57.4 | 86.0 |
| Kalmunai | 235 | 10.0 | 99.0 | 100.0 | 0.0 | 26.4 | 77.0 |
| Kalutara | 223 | 1.0 | 62.0 | 100.0 | 0.0 | 2.0 | 73.0 |
| Kandy | 234 | 10.0 | 97.3 | 100.0 | 1.0 | 11.0 | 89.0 |
| Kegalle | 235 | 10.0 | 99.0 | 100.0 | 0.0 | 8.0 | 73.0 |
| Kilinochchi | 234 | 10.0 | 99.0 | 100.0 | 8.0 | 19.0 | 100.0 |
| Kurunegala | 235 | 10.0 | 97.0 | 100.0 | 0.0 | 8.0 | 53.0 |
| Mannar | 235 | 10.0 | 80.0 | 100.0 | 11.0 | 18.0 | 100.0 |
| Matale | 234 | 10.0 | 99.0 | 100.0 | 0.0 | 17.0 | 82.0 |
| Matara | 235 | 10.0 | 100.0 | 100.0 | 0.0 | 18.4 | 76.0 |
| Monaragala | 235 | 10.0 | 99.0 | 100.0 | 0.0 | 8.4 | 73.0 |
| Mullaitivu | 235 | 10.0 | 94.0 | 100.0 | 8.0 | 20.0 | 83.0 |
| Nuwara Eliya | 235 | 10.0 | 94.0 | 100.0 | 0.0 | 18.8 | 85.0 |
| Polonnaruwa | 235 | 72.0 | 88.0 | 99.0 | 0.0 | 15.0 | 88.0 |
| Puttalam | 235 | 10.0 | 90.0 | 100.0 | 8.0 | 13.0 | 54.0 |
| Ratnapura | 235 | 10.0 | 95.0 | 100.0 | 0.0 | 12.0 | 82.0 |
| Trincomalee | 235 | 10.0 | 91.0 | 100.0 | 0.0 | 17.0 | 83.0 |
| Vavuniya | 235 | 10.0 | 85.0 | 100.0 | 0.0 | 0.0 | 75.0 |

### National row, by year

| epi_year | weeks | C_median | T_median | T_min |
|---|---|---|---|---|
| 2021 | 2 | 97.0 | 39.0 | 38.0 |
| 2022 | 51 | 95.0 | 17.0 | 5.0 |
| 2023 | 50 | 98.0 | 35.5 | 25.0 |
| 2024 | 50 | 99.0 | 93.0 | 40.0 |
| 2025 | 52 | 99.0 | 94.0 | 65.0 |
| 2026 | 30 | 98.5 | 91.5 | 58.0 |

## 8. What the parser saw

Disease columns per issue: {12: 112, 13: 92, 14: 31} (12 -> 13 with Tuberculosis from Vol 51 No 11 -> 14 with Leprosy from Vol 53 No 1; see docs/LAYOUTS.md).

Printed header spellings mapped to each disease (all explicit aliases in `config/sources.yaml`; an unknown spelling is a hard failure):

- dengue: `Dengue Fever` x234, `Dengue` x1
- dysentery: `Dysentery` x235
- encephalitis: `Encephalitis` x122, `Encephaliti` x79, `Encephalit` x22, `Encephali` x12
- enteric_fever: `En. Fever` x123, `Enteric Fever` x98, `Enteric` x11, `Enteric F.` x3
- food_poisoning: `Food Poi-` x101, `F. Poisoning` x94, `F. Poison-` x29, `Food Poison-` x11
- leptospirosis: `Leptospirosis` x235
- typhus: `Typhus` x140, `Typhus F.` x92, `Typhus Fev.` x2, `Typhus Fe-` x1
- viral_hepatitis: `Viral Hep.` x123, `Viral Hep-` x58, `Viral` x22, `Viral Hepa-` x18, `V. Hep.` x14
- human_rabies: `Human` x98, `H. Rabiies` x92, `H. Rabies` x31, `H. Rabi.` x14
- chickenpox: `Chickenpox` x235
- meningitis: `Meningitis` x235
- leishmaniasis: `Leishmania-` x202, `Leishman.` x31, `Leishmani-` x1, `Leishmaniasis` x1
- tuberculosis: `Tuberculosis` x123
- leprosy: `Leprosy` x31

Cell-level oddities across all parsed issues: {'blank': 4, 'unreadable': 2, 'pct_format': 32}. T*/C** printed as `8%` or `5.5` in `pct_format` cells are read as numbers. Blank/unreadable count cells put their whole (week, disease) group in review. Issues with such cells: Vol 50 No 52 (0 blank, 1 unreadable); Vol 53 No 8 (1 blank, 0 unreadable); Vol 49 No 7 (0 blank, 1 unreadable); Vol 49 No 17 (1 blank, 0 unreadable); Vol 49 No 38 (2 blank, 0 unreadable).

Checks applied to every parsed issue: Table 1 title found by content; RDHS/WRCD header and A/B/T*/C** sub-header found; every disease header mapped to a config id in config order; 26 RDHS rows in canonical order then SRI LANKA; week text internally consistent (start = end - 6 days), correct start weekday (Sat before the Dec 2025 switch, Mon after), and the printed `(Nth Week)` equal to the canonical week (WER numbered 2021 one ahead).

## 9. What do T* and C** mean? (investigation)

Footnote text under Table 1 in the parsed issues (digits and dates masked), most common first:

- x56 (e.g. Vol 50 No 1): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: N C**-Completeness *`
- x42 (e.g. Vol 50 No 46): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: 358C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the yea`
- x31 (e.g. Vol 50 No 22): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: N C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the year`
- x22 (e.g. Vol 52 No 31): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: N. C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the yea`
- x18 (e.g. Vol 53 No 15): `Source: WRCD module of the EPINET. T*=Timeliness refers to returns received on or before <date>. Total number of reporting units N C**-Completeness; A = Cases reported during the current week; B = Cumulative cases for the year. C**-Completeness;`
- x10 (e.g. Vol 52 No 20): `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness refers to returns received on or before <date> Total number of reporting units N Number of reporting units data provided for the current week: 360C**-Completeness * A = Cases reported during the current week. B = Cumulative cases for the yea`
- x6 (e.g. Vol 53 No 4): `Source: WRCD module of the EPINET. T*=Timeliness refers to returns received on or before <date>. Total number of reporting units N. Data provided for the current week: N. C**-Completeness; A = Cases reported during the current week; B = Cumulative cases for the year.`
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

## 10. Reproduce

```
python -m radar_lk.ingest.download --source wer --years 2022-2026
python -m radar_lk.ingest.parse_wer
python scripts/handcheck.py
pytest -q
```
