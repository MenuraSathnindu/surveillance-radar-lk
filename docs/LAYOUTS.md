# WER Table 1 layouts (2022, 2024, 2026)

Inspected 2 Nov 2026 with pdfplumber 0.11 on three issues, all **week 25 of their year**, plus a
scan of all 244 downloaded PDFs (`data/raw/wer/`, listing scraped 2 Nov 2026).
Nothing here is parser code; this is what the parser has to cope with.

| | 2022 | 2024 | 2026 |
|---|---|---|---|
| File | `vol_49_no_26-english_2.pdf` | `en_6696544245aa2_Vol_51_no_26-english.pdf` | `en_6a6399f5cc4a7_Vol_53_no_26-english.pdf` |
| Front-page issue line | `Vol. 49 No. 26 25th– 01st July 2022` | `Vol. 51 No. 26 22nd – 28th June 2024` | `Vol. 53 No. 26 22nd – 28th June 2026` |
| PDF pages | 4 | 4 | 4 |
| **Table 1 on page** | **3** (printed "Page 3") | **3** | **3** |
| Table 1 title (exact) | `Table 1: Selected notifiable diseases reported by Medical Officers of Health 18th– 24th Jun 2022 (25th Week)` | `Table 1: Selected notifiable diseases reported by Medical Officers of Health 15th – 21st June 2024 (25th Week)` | `Table 1: Distribution of Notified Diseases reported by Medical Officers of Health 15th – 21st June 2026 (25th Week)` |
| Disease column pairs | 12 | 13 (+ Tuberculosis) | 14 (+ Tuberculosis, + Leprosy) |
| Numeric columns per row | 26 = 12×2 + T + C | 28 = 13×2 + T + C | 30 = 14×2 + T + C |
| Week definition (table) | 18–24 Jun 2022 = Sat–Fri | 15–21 Jun 2024 = Sat–Fri | 15–21 Jun 2026 = **Mon–Sun** |

## What is the same in all three

- **The page is rotated 90°.** Table characters have text matrix `(0, 1, -1, 0)` (text reads
  bottom-to-top); only the title line, `Page 3` and footer are upright. `page.extract_text()` returns
  digit-by-digit garbage (`"D\n**C 7 9 6 7 0 0 1 …"`), so do **not** use it for Table 1.
  Rebuild rows from character geometry: reading position = `page.height - char.bottom`, each text
  line is a cluster of equal `x0` (lines are ~17 pt apart, rows go left→right on the unrotated page
  = top→bottom when read). I did this with ~25 lines of pdfplumber; every row came out whole.
- **Row order** is fixed: 26 RDHS rows, then `SRI LANKA`. Order: Colombo, Gampaha, Kalutara, Kandy,
  Matale, Nuwara Eliya, Galle, Hambantota, Matara, Jaffna, Kilinochchi, Mannar, Vavuniya,
  Mullaitivu, Batticaloa, Ampara, Trincomalee, Kurunegala, Puttalam, Anuradhapura, Polonnaruwa,
  Badulla, Monaragala, Ratnapura, Kegalle, Kalmunai. This is the same list and order as
  `rdhs_units` in `config/sources.yaml`.
- **National total row label:** `SRI LANKA`, but the text layer yields `SRILANKA` (no space, bold).
- **Header = two lines** (in rotated reading order):
  1. disease names (and `RDHS` first, `WRCD` last);
  2. under each disease two sub-columns `A` `B`, under `WRCD` the two sub-columns `T*` `C**`.
- **Weekly / cumulative pairs: yes.** Every disease is a pair, `A` = cases reported during the current
  week, `B` = cumulative cases for the year (footnote: `A = Cases reported during the current week.
  B = Cumulative cases for the year.`). Order inside the pair is always A then B.
- **Completeness / timeliness: the last two columns of every row**, under the group header `WRCD`
  (Weekly Return of Communicable Diseases): `T*` = Timeliness %, then `C**` = Completeness %.
  They are single percentages with no `%` sign, **per RDHS and also on the SRI LANKA row**.
  So with `n` disease pairs: columns `2n+1` = T, `2n+2` = C (1-based, after the row label).
  Footnote text: `T*=Timeliness refers to returns received on or before <date>` /
  `C**-Completeness…` (the completeness definition is cut off in the text layer in all three).
- **Reporting-week text** is only reliable in the Table 1 title (upright text), format
  `<start day>(th|st|nd|rd) – <end day>(th|st|nd|rd) <Mon|Month> <year> (<N>th Week)`,
  e.g. `18th– 24th Jun 2022 (25th Week)`. Month abbreviation varies (`Jun`, `June`, `Sep`, `July`).
  Spacing around the dash varies (`18th– 24th`, `15th – 21st`).
- **Same page 3 in 242 of 244 files**, all 4-page PDFs, all rotated (see survey at the end).
- **Footnote** (after the SRI LANKA row, rotated): source line, `T*` definition, `Total number of
  reporting units N`, in 2022 and 2024 also `Number of reporting units data provided for the current
  week: N`, then `A = …  B = …`.

## Per-year details

### 2022 (Vol 49 No 26)

- Page 3, title says **25th Week, 18th–24th Jun 2022**; the issue is "No. 26, 25th–01st July 2022".
  The table is the week *before* the issue's own date range. The website listing calls this file
  "Week 27, 2022.06.25 – 2022.07.01". Three different week numbers for one file (25 / 26 / 27);
  key on the title.
- Header line 1 (reading order): `RDHS | Dengue Fever | Dysentery | Encephaliti | Enteric Fever |
  Food Poi- | Leptospirosis | Typhus | Viral Hep- | Human | Chickenpox | Meningitis | Leishmania- | WRCD`.
  Several names are **truncated in the PDF itself** (`Encephaliti`, `Food Poi-`, `Viral Hep-`,
  `Human` for Human Rabies, `Leishmania-`); there is no continuation line.
- Column order: RDHS, Dengue Fever, Dysentery, Encephalitis, Enteric Fever, Food Poisoning,
  Leptospirosis, Typhus, Viral Hepatitis, Human Rabies, Chickenpox, Meningitis, Leishmaniasis
  (each A,B), then T*, C**. No Tuberculosis, no Leprosy.
- Footnote: `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness
  refers to returns received on or before 24rth June , 2022 Total number of reporting units 361
  Number of reporting units data provided for the current week: 308 C**-`
- **Quirks**
  - *Row labels truncated / merged:* text layer gives `NuwaraEliya`, `Anuradhapur` and `Kalmune` (the
    latter two end one letter short; I did not check whether the glyphs are missing in the PDF or
    only in the text layer). 2024 and 2026 are clean. Match on row position or normalised prefix.
  - ***SRI LANKA row fails the district-sum check in 3 cells*** (all 3-digit values, the printed
    value looks like a digit was lost; confirmed on the rendered page, not an extraction error):
    Dengue A prints `20` (26 districts sum to 809), Leptospirosis A prints `16` (sum 163), Viral
    Hepatitis B prints `16` (sum 164). The other 21 of the 24 additive columns match exactly. Our sum check
    will correctly send this issue to `data/review_queue/`.
  - Page 4 header says `Vol. 48 No. 26` (typo; the issue is Vol 49). Never trust headers outside Table 1.
  - Page 4 (Table 2, vaccine-preventable diseases, province-level) has a `Tuberculosis` row in this
    issue; it is not Table 1 and has no RDHS rows.
  - `C**` for SRI LANKA is 94 although 308/361 reporting units = 85 %, so C is not simply that ratio
    (see Uncertain).

Raw extracted rows (reading order, `|` marks a visible gap):
```
y=49 | RDHS | Dengue Fever  Dysentery | Encephaliti | Enteric Fever  Food Poi- | Leptospirosis | Typhus | Viral  Hep- | Human | Chickenpox | Meningitis | Leishmania- | WRCD
y=66 |      | A | B | A | B | A | B | A | B | A | B | A | B | A | B | A | B | A | B | A | B | A | B | A | B | T* | C**
y=82 | Colombo  | 58 | 5291 | 0 | 2 | 0 | 3 | 0 | 0 | 0 | 5 | 4 | 84 | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 16 | 0 | 4 | 0 | 2 | 14 | 97
y=511| Kalmune  | 31 | 570 | 1 | 23 | 0 | 0 | 1 | 1 | 0 | 5 | 1 | 14 | 0 | 1 | 1 | 1 | 0 | 0 | 1 | 31 | 4 | 21 | 0 | 0 | 30 | 100
y=528| SRILANKA | 20 | 26602 | 7 | 282 | 1 | 30 | 3 | 72 | 0 | 161 | 16 | 2513 | 8 | 601 | 9 | 16 | 0 | 11 | 26 | 634 | 11 | 300 | 37 | 1567 | 17 | 94
```
(the three bad SRI LANKA cells are Dengue A `20`, Leptospirosis A `16`, Viral Hepatitis B `16`.)

### 2024 (Vol 51 No 26)

- Page 3, title says **25th Week, 15th–21st June 2024**; issue date `22nd – 28th June 2024`; the
  listing calls it "Week 26, 2024.06.22 – 2024.06.28". Table week = issue week − 1 again.
- Header line 1: `RDHS | Dengue Fever | Dysentery | Encephalitis | En. Fever | F. Poisoning |
  Leptospirosis | Typhus F. | Viral Hep. | H . R abiies | Chickenpox | Meningitis | Leishmania- |
  Tuberculosis | WRCD`. Abbreviated names appear (`En. Fever`, `F. Poisoning`, `Typhus F.`, `Viral
  Hep.`) and `H . R abiies` is a **garbled Human Rabies**.
- Column order: RDHS, Dengue, Dysentery, Encephalitis, Enteric Fever, Food Poisoning,
  Leptospirosis, Typhus, Viral Hepatitis, Human Rabies, Chickenpox, Meningitis, Leishmaniasis,
  **Tuberculosis** (each A,B), then T*, C**.
- Footnote: `Source: Weekly Returns of Communicable Diseases (esurvillance.epid.gov.lk). T=Timeliness
  refers to returns received on or before 21st June, 2024 Total number of reporting units 358 Number
  of reporting units data provided for the current week: 358C**-Completeness` (the `C**` line
  wraps onto separate lines in the text layer).
- **Quirks:** district sums match SRI LANKA in all 26 additive columns. Whitespace between cells is
  unreliable: on a few rows adjacent cells touch and print with a single space
  (`… | 46 | 323  100 | 100` on Kandy = TB A 46, TB B 323, T 100, C 100) and on the SRI LANKA row
  (bold, tight) several pairs collapse (`30037  23`). **Assign cells to columns by x-position, or
  split on all whitespace and require exactly `2n+2` numbers per row.**

```
y=48 | RDHS | Dengue Fever | Dysentery | Encephalitis | En. Fever | F. Poisoning | Leptospirosis | Typhus F. | Viral Hep.  H . R abiies | Chickenpox | Meningitis | Leishmania- | Tuberculosis | WRCD
y=64 |      | A | B | A | B | … (13 × A,B) … | T* | C**
y=81 | Colombo  | 218 | 5592 | 2 | 13 | 1 | 6 | 2 | 42 | 4 | 10 | 10 | 225 | 0 | 8 | 0 | 7 | 0 | 0 | 15 | 255 | 1 | 16 | 0 | 0 | 26 | 1036 | 95 | 100
y=131| Kandy    | 85 | 2332 | 0 | 19 | 0 | 2 | 0 | 6 | 3 | 40 | 3 | 139 | 0 | 21 | 0 | 8 | 0 | 1 | 1 | 261 | 2 | 13 | 1 | 24 | 46 | 323  100 | 100
y=527| SRILANKA | 683 | 30037  23 | 533 | 4 | 93 | 2  147 | 33  1029 | 224  5833 | 8 | 706 | 6  143 | 1 | 13  123  3956 | 25 | 782 | 64  1917 | 166 | 4341 | 90 | 99
```

### 2026 (Vol 53 No 26)

- Page 3, title **`Table 1: Distribution of Notified Diseases reported by Medical Officers of
  Health 15th – 21st June 2026 (25th Week)`**. The title wording changed from "Selected notifiable
  diseases" (208 issues) to "Distribution of Notified Diseases" (all 34 issues of Vol 53).
- **Decoy:** page 2 of the same PDF has `Table 1 : Water Quality Surveillance …` (district / MOH
  areas / samples). Locate Table 1 by "Table 1" **and** "Medical Officers of Health", on a page with
  rotated text, not by "Table 1" alone.
- Week definition is Monday–Sunday (15–21 June 2026). Front page says `22nd – 28th June 2026`, but the
  website listing says "Week 26, 2026.06.20 – 2026.06.26" (Sat–Fri), so listing dates are wrong or
  inconsistent for 2026. Do not use them.
- Header line 1: `RDHS | Dengue Fever | Dysentery | Encephalitis | En. Fever | F. Poison- |
  Leptospirosis | Typhus | Viral Hep. | H . Rabies | Chickenpox | Meningitis | Leishman. |
  Tuberculosis | Leprosy | WRCD`.
- Column order: as 2024 plus **Leprosy** after Tuberculosis; then T*, C**.
- Footnote: `Source: WRCD module of the EPINET. T*=Timeliness refers to returns received on or before
  21st June, 2026. Total number of reporting units 360 … C**-Completeness; A = Cases reported during
  the current week; B = Cumulative cases for the year.` (source line changed; there is no
  "reporting units data provided" figure in the text layer.)
- **Quirks:** district sums match SRI LANKA in all 28 additive columns. Same touching-cells issue
  (Kalmunai `… | 0 | 23  100 | 100` = Leprosy A 0, B 23, T 100, C 100; SRI LANKA row merges several
  pairs).

```
y=48 | RDHS | Dengue Fever | Dysentery | Encephalitis | En. Fever | F. Poison- | Leptospirosis | Typhus | Viral Hep.  H . Rabies | Chickenpox | Meningitis | Leishman. | Tuberculosis | Leprosy | WRCD
y=64 |      | A | B | … (14 × A,B) … | T* | C**
y=81 | Colombo  | 1138 | 9357 | 0 | 16 | 0 | 2 | 0 | 4 | 1 | 16 | 6 | 178 | 0 | 2 | 0 | 9 | 0 | 0 | 8 | 317 | 6 | 44 | 0 | 3 | 29 | 880 | 3 | 83 | 89 | 100
y=511| Kalmunai | 37 | 640 | 3 | 29 | 0 | 1 | 0 | 1 | 3 | 18 | 3 | 51 | 0 | 1 | 0 | 1 | 0 | 0 | 11 | 335 | 1 | 23 | 0 | 0 | 1 | 62 | 0 | 23  100 | 100
y=527| SRILANKA | 5828 | 45879 | 25 | 589 | 5 | 149 | 1 | 82 | 21 | 636 | 171 | 4327 | 17 | 532 | 10 | 337 | 0 | 6  213 | 6820  139  1793 | 73  2050  144  3944 | 23 | 584 | 90 | 99
```

## How the disease set changed (all 242 issues with a Table 1)

Counted from the number of `A` sub-columns on page 3:

| Pairs | Diseases | Issues | First → last |
|---|---|---|---|
| 12 | Dengue, Dysentery, Encephalitis, Enteric Fever, Food Poisoning, Leptospirosis, Typhus, Viral Hepatitis, Human Rabies, Chickenpox, Meningitis, Leishmaniasis | 114 | Vol 48 No 37 → Vol 51 No 10 |
| 13 | + Tuberculosis | 94 | Vol 51 No 11 → Vol 52 No 52 |
| 14 | + Leprosy | 34 | Vol 53 No 1 → Vol 53 No 34 |

So "14 diseases" holds only for 2026. A parser must read the header (or count A/B pairs) per issue
and emit only the diseases present; a missing disease is *not available*, not zero. Tuberculosis
and Leprosy have **no history before Mar 2024 / Jan 2026**, which limits the radar for them.

## Survey of all downloaded PDFs

- 244 files: 243 have 4 pages, 1 has 1 page.
- **242 have Table 1 on page 3, rotated**. The title is "Selected notifiable diseases reported by
  Medical Officers of Health" in 208 and "Distribution of Notified Diseases reported by Medical
  Officers of Health" in 34.
- The 2 without Table 1: `en_63ec87e11b430_WER.pdf` (the one-page generic "Read More" description,
  not an issue) and `Vol_38_NO_29_English.pdf` (a **2011** issue, Vol 38 No 29 16–22 Jul 2011,
  listed on the site under 2022 dates; its page 3 has no rotated table).
- `vol_48_no_37-english.pdf` is a genuine **2021** issue (Table 1: `28th– 03rd Sep 2021 (36th Week)`)
  that the site lists under 2022.08.27–09.02. So **filter on the table's printed week, not on the
  download list**: two out-of-range files are among the 244.
- Note the start month is omitted when the range crosses a month: `28th– 03rd Sep 2021`.
  The start date has to be inferred (end date minus 6 days).

## Uncertain / to verify when writing the parser

1. `C**` (completeness) definition is cut off in every footnote. For 2022 SRI LANKA: 308 of 361
   reporting units supplied data (85 %) but C = 94, T = 17. I do not know what C is a percentage of.
   Needs a hand check against the Epidemiology Unit's definition before gating alerts on it.
2. Whether `Anuradhapur` / `Kalmune` (2022) are missing glyphs or only text-layer truncation.
3. Whether the 2022 SRI LANKA digit loss recurs in other 2022/2023 issues (it is one issue of the
   ones sampled; the validator will tell us).
4. Weeks that straddle New Year / 53-week years were not sampled (only week 25 per year).
5. Layout drift inside a year was checked only by page position and disease count, not by
   column-level comparison on every issue.
