# Headline numbers

This is the single source for every number quoted in the report, the two-page summary and the
video. Each line gives the value, what it means, and the file and section it comes from. If you
regenerate a source, update this page from it; never quote a number that is not here.

Last updated 2026-11-03. Data: WER Table 1, 2022-W01 to 2026-W33 (Vol 53 No 34; as of 2026-08-16).
Primary sources: Epidemiology Unit and National Dengue Control Unit (NDCU), Ministry of Health,
Sri Lanka.

Reproduce: `python -m radar_lk.ingest.parse_wer`, `python -m radar_lk.radar.run --reuse-fits`,
`python -m radar_lk.radar.backtest --reuse`.

## 1. Extraction quality

| number | value | meaning | source |
|---|---|---|---|
| Hand-check accuracy | **50 / 50 = 100%** (95% Wilson CI **92.9–100%**) | 50 randomly drawn cells across 2022–2026, read by a person on the rendered PDF page, all matched the extracted value. | `docs/EXTRACTION_REPORT.md` "Hand-check"; `docs/handcheck_result.md`; `data/handcheck/v2`, `v3` |
| Cross-extractor agreement | **100.000%** of **177,876** cells (241 issues), **0** disagreements | A second, independent PDF library (PyMuPDF) gives the same number in every cell. This rules out parser bugs, but not a text layer that differs from the print; the hand-check covers that. | `docs/EXTRACTION_REPORT.md` §10; `docs/CROSS_EXTRACT.md` |
| `extraction_valid`, all years | **97.06%** (76,440 of 78,754 district-disease-weeks) | Share of rows that pass every single-issue check and may reach the dashboard. Target was 95%. | `docs/EXTRACTION_REPORT.md` §1, §3 |
| `extraction_valid` by year | 2022 **97.4%**, 2023 **96.0%**, 2024 **99.5%**, 2025 **98.1%**, 2026 **93.1%** | 2026 is lowest because it has the most source-table errors, including two wholly scrambled issues. | `docs/EXTRACTION_REPORT.md` §3 "Per year" |
| Source-table scrambling | **2** whole issues printed against the wrong rows (2026-W14, W24) plus **2** single columns (chickenpox 2026-W03, W07); **2** whole issues copied from the previous week (2022-W22, 2025-W07) plus **3** single columns (chickenpox 2024-W11, TB 2024-W39, dengue 2026-W26) | The PDFs themselves sometimes print a weekly column against the wrong districts or repeat last week's. Totals and cumulatives agree with the wrong numbers, so sum checks and a second extractor cannot catch it. Before this was caught, the radar alerted on them (e.g. Matale dengue 256 when nearby weeks read ~20). Now detected with past-only rules and quarantined. | `docs/EXTRACTION_REPORT.md` §5b; `docs/RADAR_BACKTEST.md` "Highlighted finding" |
| Publication lag | median **53 days** (IQR **30–75.5**) over **239** issues, which is about **8 weeks** | Time from the end of a reporting week to the PDF's creation date. Radar signals are therefore retrospective on the published record, not real-time. | `docs/EXTRACTION_REPORT.md` §11; `config/sources.yaml` `publication_lag_weeks` |

## 2. Radar: false alerts and sensitivity

False-alert rates come from 200 simulated outbreak-free years per series. Sensitivity is measured on
2,600 injected outbreaks (200 per modelled disease) (k × SD, k = 1..10, 1–4 weeks, 2024 onwards). "Per 100" means per 100
district-weeks.

| number | value | meaning | source |
|---|---|---|---|
| Status-quo rule false alerts | **13.7** per 100 (null); real-data alert rate **10.8** per 100 | The rule used by eye today (≥ 2× the same week last year) breaks the proposal's 10% usability bar even when there is no outbreak at all. It cannot get below about 3.5 per 100 at any factor. | `docs/RADAR_BACKTEST.md` §a, §b |
| NB-GLM at default (98%) | sensitivity **49.0%**, false alerts **2.0** per 100 | The confirmed-signal method at its a-priori threshold. | `docs/RADAR_BACKTEST.md` §a |
| Matched comparison at 1 false alert / 100 | NB-GLM **41.6%**, EARS C2 **32.3%**, EARS C3 **26.9%**, status quo n/a | At the same false-alert rate, NB-GLM finds the most injected outbreaks. | `docs/RADAR_BACKTEST.md` §b |
| Matched comparison at 2 false alerts / 100 | NB-GLM **49.0%**, EARS C2 **45.4%**, EARS C3 **37.0%**, status quo n/a | Same comparison at a looser rate. | `docs/RADAR_BACKTEST.md` §b |
| By outbreak size at 1 / 100 (NB-GLM) | 1 SD **8%**, 2 SD **21%**, 3 SD **26%**, 4 SD **39%** | Small rises are hard for every method; NB-GLM leads at every size. | `docs/RADAR_BACKTEST.md` §b |

## 3. Known-event replay

Events are located in our own data by written rules, and every qualifying district is included:
leptospirosis 2024 (three waves), dengue 2026 W23–W33, and leptospirosis after Cyclone Ditwah
(rain week 2025-W48). That gives **67 district-events**. "Gain" means weeks earlier than the
status-quo rule. Censored first alerts are excluded from the comparison.

| number | value | meaning | source |
|---|---|---|---|
| NB-GLM vs status quo | 24 comparable: earlier **1**, same **7**, later **16**; median **−2 weeks** | On real slow build-ups, NB-GLM alone alerts later than today's rule. | `docs/RADAR_BACKTEST.md` §d |
| EARS C2 vs status quo | 30 comparable: earlier **13**, same **6**, later **11**; median **0 weeks** | C2 is as early as today's rule with about a fifth of its false alerts (3.0 vs 13.7 per 100). | `docs/RADAR_BACKTEST.md` §d |
| Two-tier vs status quo | 31 comparable: earlier **14**, same **7**, later **10**; median **0 weeks** | The adopted two-tier radar signals as early as today's rule. | `docs/RADAR_BACKTEST.md` §d, §d2 |

## 4. Two-tier radar (adopted)

| number | value | meaning | source |
|---|---|---|---|
| Decision | **Adopted.** The rule (fixed before running) was union null false alerts ≤ 5 per 100 AND median replay gain ≥ 0. | `alert` = NB-GLM above its 98% bound; `early_warning` = EARS C2 > 3 while NB-GLM is silent. Thresholds were not re-tuned. | `docs/RADAR_BACKTEST.md` §d2; `config/sources.yaml` `radar_display.tiers_adopted` |
| Null false alerts | alert **2.0**, early warning **1.8**, union **3.8** per 100 | What a user sees with no outbreak: under 4 per 100 district-weeks, against 13.7 for today's rule. Dengue (9.3) and leptospirosis (7.3) are higher than the pooled figure. | `docs/RADAR_BACKTEST.md` §d2 |
| Sensitivity (default thresholds) | alert **49.0%**, union **61.0%** | The early-warning tier adds 12 points of sensitivity. | `docs/RADAR_BACKTEST.md` §d2 |
| Union sensitivity by size | 1 SD **22.5%**, 2 SD **38.9%**, 3 SD **45.5%**, 4 SD **55.7%** | Not matched: the union runs at a higher false-alert rate than §2's 1 / 100 figures. | `docs/RADAR_BACKTEST.md` §d2 |
| Replay first signal | **31** early warning, **27** alert (58 district-events signalled out of 67) | In real events the early-warning tier usually speaks first. | `docs/RADAR_BACKTEST.md` §d2 |

## 5. Completeness gating

| number | value | meaning | source |
|---|---|---|---|
| Revision after a held-back vs kept alert | next week revised **21% vs 9%**; cumulative raised **19% vs 6%** | Low-completeness weeks really are incomplete: late reports arrive. | `docs/RADAR_BACKTEST.md` §e |
| Persistence | next 2 weeks above expected **52% vs 48%** (618 held-back vs 13,042 kept alerts) | Held-back alerts are as real as kept ones. Gating does not remove false alerts; the proposal's target is not met. Held-back alerts are therefore shown greyed out with their completeness, never hidden. | `docs/RADAR_BACKTEST.md` §e |

## 6. External concordance: radar vs NDCU dengue high-risk lists (2026, weeks 1–33)

NDCU flags absolute burden in MOH areas; the radar flags what is unusual for a district and
season. These are different questions, so moderate agreement is expected. Below, "NDCU-positive"
means ≥ 3 of the district's MOH areas are on the list; NB-GLM; 780 district-weeks.

| number | value | meaning | source |
|---|---|---|---|
| Agreement / kappa | **79.9%**, κ **0.41** | Moderate agreement beyond chance. | `docs/RADAR_BACKTEST.md` §f |
| Radar alerts NDCU also flagged | **65.7%** | Two thirds of radar dengue alerts fall in districts NDCU also lists that week. | `docs/RADAR_BACKTEST.md` §f |
| NDCU onsets caught within ±4 weeks | **22 of 35**; median lag **0 weeks** | When the radar catches an NDCU onset, it does so in the same week. | `docs/RADAR_BACKTEST.md` §f |
| NDCU-only weeks explained | **64%** of the 111 are labelled "High burden, within expected range" | The dashboard reconciles the two: high for the district, but normal for the season. | `docs/RADAR_BACKTEST.md` §f |

## 7. Outlook

_To be filled next session (leptospirosis / dengue outlook backtest)._
