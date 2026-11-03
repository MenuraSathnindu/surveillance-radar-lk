# Headline numbers

This is the single source for every number quoted in the report, the two-page summary and the
video. Each line gives the value, what it means, and the file and section it comes from. If you
regenerate a source, update this page from it; never quote a number that is not here.

**Data freeze: 2026-W36, 3 Nov 2026.** Every number below uses the WER Table 1 data from 2022-W01
to 2026-W36 (Vol 53 No 37; week ending 2026-09-06), downloaded and frozen on 3 Nov 2026.
Simulation-based radar numbers (§2, §4: false alerts, sensitivity, matched comparison) come from
simulations fitted on the series up to 2026-W33 and were not re-simulated for the freeze.
Primary sources: Epidemiology Unit and National Dengue Control Unit (NDCU), Ministry of Health,
Sri Lanka.

Reproduce: `python -m radar_lk.ingest.parse_wer`, `python -m radar_lk.radar.run --reuse-fits`,
`python -m radar_lk.radar.backtest --reuse`.

## 1. Extraction quality

| number | value | meaning | source |
|---|---|---|---|
| Hand-check accuracy | **50 / 50 = 100%** (95% Wilson CI **92.9–100%**) | 50 randomly drawn cells across 2022–2026, read by a person on the rendered PDF page, all matched the extracted value. | `docs/EXTRACTION_REPORT.md` "Hand-check"; `docs/handcheck_result.md`; `data/handcheck/v2`, `v3` |
| Cross-extractor agreement | **100.000%** of **180,306** cells (244 issues), **0** disagreements | A second, independent PDF library (PyMuPDF) gives the same number in every cell. This rules out parser bugs, but not a text layer that differs from the print; the hand-check covers that. | `docs/EXTRACTION_REPORT.md` §10; `docs/CROSS_EXTRACT.md` |
| `extraction_valid`, all years | **97.10%** (77,532 of 79,846 district-disease-weeks) | Share of rows that pass every single-issue check and may reach the dashboard. Target was 95%. | `docs/EXTRACTION_REPORT.md` §1, §3 |
| `extraction_valid` by year | 2022 **97.4%**, 2023 **96.0%**, 2024 **99.5%**, 2025 **98.1%**, 2026 **93.7%** | 2026 is lowest because it has the most source-table errors, including two wholly scrambled issues. | `docs/EXTRACTION_REPORT.md` §3 "Per year" |
| Source-table scrambling | **2** whole issues printed against the wrong rows (2026-W14, W24) plus **2** single columns (chickenpox 2026-W03, W07); **2** whole issues copied from the previous week (2022-W22, 2025-W07) plus **3** single columns (chickenpox 2024-W11, TB 2024-W39, dengue 2026-W26) | The PDFs themselves sometimes print a weekly column against the wrong districts or repeat last week's. Totals and cumulatives agree with the wrong numbers, so sum checks and a second extractor cannot catch it. Before this was caught, the radar alerted on them (e.g. Matale dengue 256 when nearby weeks read ~20). Now detected with past-only rules and quarantined. | `docs/EXTRACTION_REPORT.md` §5b; `docs/RADAR_BACKTEST.md` "Highlighted finding" |
| Publication lag | median **53 days** (IQR **31–74.8**) over **242** issues, which is about **8 weeks** | Time from the end of a reporting week to the PDF's creation date. Radar signals are therefore retrospective on the published record, not real-time. | `docs/EXTRACTION_REPORT.md` §11; `config/sources.yaml` `publication_lag_weeks` |

## 2. Radar: false alerts and sensitivity

False-alert rates come from 200 simulated outbreak-free years per series. Sensitivity is measured on
2,600 injected outbreaks (200 per modelled disease) (k × SD, k = 1..10, 1–4 weeks, 2024 onwards). "Per 100" means per 100
district-weeks.

| number | value | meaning | source |
|---|---|---|---|
| Status-quo rule false alerts | **13.7** per 100 (null); real-data alert rate **10.7** per 100 | The rule used by eye today (≥ 2× the same week last year) breaks the proposal's 10% usability bar even when there is no outbreak at all. It cannot get below about 3.5 per 100 at any factor. | `docs/RADAR_BACKTEST.md` §a, §b |
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
| Two-tier decision | **Adopted.** The rule (fixed before running) was union null false alerts ≤ 5 per 100 AND median replay gain ≥ 0. | `alert` = NB-GLM above its 98% bound; `early_warning` = EARS C2 > 3 while NB-GLM is silent. Thresholds were not re-tuned. | `docs/RADAR_BACKTEST.md` §d2; `config/sources.yaml` `radar_display.tiers_adopted` |
| Two-tier null false alerts | alert **2.0**, early warning **1.8**, union **3.8** per 100 | What a user sees with no outbreak: under 4 per 100 district-weeks, against 13.7 for today's rule. Dengue (9.3) and leptospirosis (7.3) are higher than the pooled figure. | `docs/RADAR_BACKTEST.md` §d2 |
| Two-tier sensitivity | alert **49.0%**, union **61.0%** | The early-warning tier adds 12 points of sensitivity. | `docs/RADAR_BACKTEST.md` §d2 |
| Two-tier sensitivity by outbreak size | 1 SD **22.5%**, 2 SD **38.9%**, 3 SD **45.5%**, 4 SD **55.7%** | Not matched: the union runs at a higher false-alert rate than §2's 1 / 100 figures. | `docs/RADAR_BACKTEST.md` §d2 |
| Two-tier first signal in the replay | **31** early warning, **27** alert (58 district-events signalled out of 67) | In real events the early-warning tier usually speaks first. | `docs/RADAR_BACKTEST.md` §d2 |

## 5. Completeness gating

| number | value | meaning | source |
|---|---|---|---|
| Revision after a held-back vs kept alert | next week revised **20% vs 9%**; cumulative raised **18% vs 6%** | Low-completeness weeks really are incomplete: late reports arrive. | `docs/RADAR_BACKTEST.md` §e |
| Held-back alerts that persisted | next 2 weeks above expected **51% vs 48%** (650 held-back vs 13,111 kept alerts) | Held-back alerts are as real as kept ones. Gating does not remove false alerts; the proposal's target is not met. Held-back alerts are therefore shown greyed out with their completeness, never hidden. | `docs/RADAR_BACKTEST.md` §e |

## 6. External concordance: radar vs NDCU dengue high-risk lists (2026, weeks 1–36)

NDCU flags absolute burden in MOH areas; the radar flags what is unusual for a district and
season. These are different questions, so moderate agreement is expected. Below, "NDCU-positive"
means ≥ 3 of the district's MOH areas are on the list; NB-GLM; 858 district-weeks.

| number | value | meaning | source |
|---|---|---|---|
| Radar vs NDCU agreement / kappa | **80.3%**, κ **0.39** | Agreement beyond chance, at the top of "fair" (Landis–Koch 0.21–0.40). | `docs/RADAR_BACKTEST.md` §f |
| Radar alerts NDCU also flagged | **65.7%** | Two thirds of radar dengue alerts fall in districts NDCU also lists that week. | `docs/RADAR_BACKTEST.md` §f |
| NDCU onsets caught within ±4 weeks | **22 of 35**; median lag **0 weeks** | When the radar catches an NDCU onset, it does so in the same week. | `docs/RADAR_BACKTEST.md` §f |
| NDCU-only weeks explained | **59%** of the 123 are labelled "High burden, within expected range" | The dashboard reconciles the two: high for the district, but normal for the season. | `docs/RADAR_BACKTEST.md` §f |

## 7. Outlook (district level: leptospirosis primary, dengue secondary)

Rolling-origin backtest, refitted every 4 weeks, past-only, 26 districts. **Models are selected
on 2024 origins only** (counts by MASE, probabilities by Brier; within 0.01 the simpler model
wins). **Every number below is on the untouched test: origins 2025-W01 to 2026-W32**, unless it
says otherwise. The origin t is the latest reported week. With the publication lag L = 8 weeks,
h = 9 is "this week" and h = 10 is "next week" at the time of use; h = 1, 2 are the proposal's
horizons. "Elevated" means at or above the district's own 80th percentile of the 104 weeks before
t. BSS = Brier skill score; MASE = MAE divided by persistence's MAE.

At h=9–10 the skill over seasonal climatology is small, so the outlook is mainly a calibrated seasonal expectation.

| number | value | meaning | source |
|---|---|---|---|
| Leptospirosis: selected models | probability: **NB GLM / logistic** at all 10 horizons; counts: **GLM** at h=1–6, **LightGBM** at h=7–10 | Chosen on 2024 origins. The GLM tied or beat LightGBM on probability, and the simpler model was kept. | `docs/OUTLOOK_BACKTEST.md` Leptospirosis, "Model selection" |
| Leptospirosis, h=1 / 2 (test) | BSS **0.40 / 0.42**, MASE **0.92 / 0.89**, AUROC **0.76 / 0.75** | For the weeks already over but not yet reported, the probability is about 40% better than "same as the last report", and counts are 8–11% closer. | same, "How the selected models do on the untouched test" |
| Leptospirosis, this week / next week (h=9 / 10, test) | BSS **0.52 / 0.50**, MASE **0.76 / 0.75**; BSS over climatology only **0.02 / 0.01** | At the time of use the outlook halves persistence's probability error and cuts its count error by a quarter, but almost all of that is the seasonal pattern. | same |
| Leptospirosis, 90% interval coverage (test) | **93.5%** (80%: **83.2%**), static split-conformal | The intervals are slightly conservative. ACI was not adopted: in 2026 it brought 90% coverage from 93.3% to 91.5%, but 80% did not move closer to nominal (82.7% to 82.8%). | same, "Count intervals" |
| ACI interval width cost | leptospirosis mean 90% width: 2024–25 **17.8 → 39.6** cases, 2026 **13.7 → 14.0**; dengue: 2024–25 **67 → 162**, 2026 **65 → 197** | Adaptive intervals buy coverage with width: when misses pile up they widen sharply, up to the largest past error. That is why ACI is used only where static coverage failed (dengue). | same, "Count intervals" |
| Rainfall lag | leptospirosis risk rises **about 6 weeks** after a very wet week in the model; in the raw data the excess peaks at **4 weeks** (**1.8×** the share elevated) | Rain at lags 3–7 weeks pushes P(elevated) up. This is an association, not proof of cause. | same, "Rainfall lag"; `docs/figures/outlook_leptospirosis_rain_lag.png` |
| Top leptospirosis drivers (LightGBM, P(elevated)) | the district's own threshold, humidity (lags 2–4), district, temperature, season, rain at lags 4–6 | Weather relative to the target week matters, alongside place and season. | same, "What drives LightGBM" |
| Dengue: selected models | counts: **persistence** at h=1–5, **GLM** at h=6–9, **climatology** at h=10; probability: **persistence** at h=1, 2, 4, **GLM** at h=3, **climatology** at h=5–10 | On 2024 origins nothing beat the simple baselines for dengue by more than 0.01. | `docs/OUTLOOK_BACKTEST.md` Dengue, "Model selection" |
| Dengue, what selection cost on the test | at h=1 LightGBM would have scored BSS **0.16** against the selected persistence's 0; at h=9 **0.30** against climatology's **0.25** | Choosing on 2024 alone did not anticipate the 2026 epidemic. The selection rule is kept because it was fixed before seeing the test. | same, "How the selected models do on the untouched test" |
| Dengue 2026, count interval coverage | static 80/90%: **62.7 / 72.6%**; adaptive (ACI): **72.7 / 83.5%** | The epidemic year broke the past-only calibration. ACI brings coverage closer to nominal and is used on the dashboard for dengue, but its 90% intervals are about three times as wide (mean **197** vs **65** cases). | same, "Count intervals" |
| Dengue vs NDCU (h=1, ≥ 3 MOH areas, selected model) | agreement **61.0%**, κ **0.29**; **92%** of NDCU-flagged district-weeks were forecast elevated, but only **39%** of forecasts were NDCU-flagged | At h=1 the selected model is persistence, so it matches the observed elevated flag (κ 0.29). At h=9–10 (climatology) agreement drops to κ **0.00**. | same, "Dengue: 2026 forecasts vs NDCU" |
