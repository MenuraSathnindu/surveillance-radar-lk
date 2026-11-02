# Radar backtest

Generated 2026-11-02 by `python -m radar_lk.radar.run` then `python -m radar_lk.radar.backtest`. Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (WER Table 1); external validation: National Dengue Control Unit (NDCU) Weekly Dengue Update.

## Data and design

- **Post-COVID baseline.** Only `extraction_valid` RDHS rows from **2022-W01** to 2026-W33 (Vol 53 No 34). 2020-2021 reporting was distorted by COVID-19, so the baselines deliberately start in 2022; the cost is that seasonal models have at most ~3.5 years of history.
- **Weekly counts as first printed** in each issue (what a Regional Epidemiologist saw that week), never later back-filled values.
- **Series:** 338 RDHS x disease series with >= 104 observed weeks. Not modelled (insufficient history): 26 series (leprosy x26).
- **No lookahead.** Every method uses only weeks before t; `tests/test_radar.py::test_no_lookahead` changes future weeks and checks no earlier signal moves.

| method | rule |
|---|---|
| Status quo | alert if count >= 2 x the same week last year and >= 3 |
| EARS C2 | baseline = 7 weeks ending 2 weeks before t (t-9..t-3); alert if (y - mean) / sd > 3 (sd floored at 1) |
| EARS C3 | sum over t, t-1, t-2 of max(0, C2 - 1) > 2 |
| NB-GLM | log mu = intercept + linear trend + Fourier (period 52.18, K=2); fitted on past weeks only, refitted every 4 weeks after 52 observed weeks; past weeks with Anscombe residual > 2.58 down-weighted (r^-2); alert if observed > the 98th-percentile NB bound |

Every method also needs observed >= 3. **Gating:** an alert in a week whose completeness is below the RDHS's own past 10th percentile is kept but `suppressed` with the reason; a `revised` week keeps its alert and carries the marker. Parameter uncertainty of the NB fit is not added to the bound (it slightly narrows the band).

## a) Injected-outbreak evaluation

2600 simulated outbreaks (200 per disease, seed 20261104) added to the real series: start week uniform over 2024-W01 onwards (where the NB-GLM already has a fit), duration 1-4 weeks, total size ~ negative binomial (dispersion 2) with mean k x the series' SD, k uniform on 2..10, spread evenly over the weeks. **Sensitivity** = share of outbreaks with an alert in an outbreak week; **delay** = weeks from outbreak start to the first such alert (0 = first week). **Specificity / false alerts** come from the real 2024-2026 data, counting every real alert as false: a conservative bound, since some real alerts are real rises.

| method | sensitivity % | sensitivity after gating % | specificity % | false alerts / 100 district-weeks | median delay (weeks) |
|---|---|---|---|---|---|
| Status quo (2x last year) | 73.3 | 71.8 | 89.2 | 10.8 | 0.0 |
| EARS C2 | 56.4 | 55.2 | 97.1 | 2.9 | 0.0 |
| EARS C3 | 62.4 | 61.2 | 94.0 | 6.0 | 0.0 |
| NB-GLM (Farrington-style) | 53.4 | 52.1 | 98.4 | 1.6 | 0.0 |

Sensitivity by outbreak size:

| outbreak size (x series SD) | Status quo (2x last year) | EARS C2 | EARS C3 | NB-GLM (Farrington-style) |
|---|---|---|---|---|
| 2-3 SD | 53.2 | 30.2 | 35.8 | 25.8 |
| 4-6 SD | 72.5 | 54.4 | 60.7 | 52.8 |
| 7-10 SD | 84.1 | 71.3 | 77.2 | 68.0 |

Per disease (sensitivity % on injected outbreaks; FA/100 = real alerts per 100 district-weeks):

| disease | outbreaks | status_quo sens % | status_quo FA/100 | ears_c2 sens % | ears_c2 FA/100 | ears_c3 sens % | ears_c3 FA/100 | nb_glm sens % | nb_glm FA/100 |
|---|---|---|---|---|---|---|---|---|---|
| chickenpox | 200 | 84.0 | 29.5 | 59.5 | 4.8 | 67.0 | 11.7 | 46.5 | 1.5 |
| dengue | 200 | 84.5 | 25.7 | 84.5 | 10.6 | 89.0 | 23.6 | 59.5 | 5.7 |
| dysentery | 200 | 72.0 | 7.1 | 52.0 | 1.7 | 59.0 | 2.7 | 50.5 | 1.4 |
| encephalitis | 200 | 63.0 | 0.8 | 47.0 | 0.1 | 53.5 | 0.2 | 58.0 | 0.4 |
| enteric_fever | 200 | 59.5 | 0.6 | 48.5 | 0.2 | 49.5 | 0.3 | 55.0 | 0.4 |
| food_poisoning | 200 | 83.5 | 8.6 | 65.5 | 4.1 | 69.0 | 5.2 | 46.0 | 2.3 |
| human_rabies | 200 | 61.5 | 0.0 | 46.0 | 0.0 | 50.5 | 0.0 | 59.0 | 0.0 |
| leishmaniasis | 200 | 70.0 | 11.0 | 51.5 | 1.9 | 59.5 | 4.5 | 47.0 | 1.1 |
| leptospirosis | 200 | 83.5 | 22.7 | 64.0 | 6.5 | 74.0 | 14.5 | 50.5 | 2.2 |
| meningitis | 200 | 80.5 | 14.3 | 59.0 | 2.8 | 65.5 | 5.0 | 53.5 | 2.0 |
| tuberculosis | 200 | 80.0 | 19.3 | 57.5 | 3.6 | 65.0 | 7.8 | 52.5 | 2.4 |
| typhus | 200 | 67.5 | 4.0 | 52.0 | 0.8 | 57.5 | 1.9 | 58.5 | 0.7 |
| viral_hepatitis | 200 | 63.0 | 2.2 | 46.5 | 0.5 | 52.0 | 0.8 | 58.0 | 1.3 |

## b) Real-data alert rates (2024 onwards)

| method | weeks | alerts | shown | alerts per 100 district-weeks | shown per 100 (after gating) |
|---|---|---|---|---|---|
| EARS C2 | 44356 | 1279 | 1236 | 2.9 | 2.8 |
| EARS C3 | 44356 | 2656 | 2576 | 6.0 | 5.8 |
| NB-GLM (Farrington-style) | 43186 | 705 | 677 | 1.6 | 1.6 |
| Status quo (2x last year) | 41912 | 4539 | 4381 | 10.8 | 10.5 |

**Stop rule** (NB-GLM must not flag more than 10% of district-weeks): NB-GLM shows alerts in 1.57 per 100 district-weeks at the 98th percentile, so the configured quantile was kept.

Per disease, alerts per 100 district-weeks (shown after gating):

| disease | Status quo (2x last year) | EARS C2 | EARS C3 | NB-GLM (Farrington-style) |
|---|---|---|---|---|
| chickenpox | 28.4 | 4.7 | 11.4 | 1.5 |
| dengue | 25.1 | 10.3 | 23.2 | 5.4 |
| dysentery | 6.9 | 1.7 | 2.7 | 1.4 |
| encephalitis | 0.8 | 0.1 | 0.2 | 0.4 |
| enteric_fever | 0.6 | 0.2 | 0.3 | 0.4 |
| food_poisoning | 8.2 | 3.9 | 4.9 | 2.2 |
| human_rabies | 0.0 | 0.0 | 0.0 | 0.0 |
| leishmaniasis | 10.3 | 1.9 | 4.4 | 1.1 |
| leptospirosis | 22.4 | 6.4 | 13.9 | 2.2 |
| meningitis | 13.5 | 2.5 | 4.7 | 1.9 |
| tuberculosis | 18.4 | 3.4 | 7.6 | 2.3 |
| typhus | 3.8 | 0.8 | 1.8 | 0.7 |
| viral_hepatitis | 2.1 | 0.5 | 0.8 | 1.3 |

## c) External validation: dengue radar vs NDCU 2026 high-risk MOH lists

District x week pairs in 2026 where both exist (weeks 1-33). NDCU flags an MOH area as high-risk from its own case counts; a district is 'NDCU-positive' when at least 1 (or at least 3) of its MOH areas is on the list. The two signals answer different questions (NDCU: absolute burden; radar: unusual for this district and season), so high concordance is not expected; the lead/lag is the more useful number.

### NDCU-positive = >= 1 MOH area(s) flagged

| method | district-weeks | both | radar only | NDCU only | neither | agreement % | kappa | radar sensitivity vs NDCU % | share of radar alerts with NDCU flag % | NDCU onsets | onsets with a radar alert within +-4 wk | median lag (radar - NDCU, wk) | radar earlier | same week | radar later |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Status quo (2x last year) | 754 | 219 | 118 | 138 | 279 | 66.0 | 0.32 | 61.3 | 65.0 | 65 | 48 | 0.0 | 7 | 31 | 10 |
| EARS C2 | 780 | 103 | 25 | 263 | 389 | 63.1 | 0.23 | 28.1 | 80.5 | 66 | 42 | 0.0 | 6 | 20 | 16 |
| EARS C3 | 780 | 191 | 81 | 175 | 333 | 67.2 | 0.33 | 52.2 | 70.2 | 66 | 47 | 0.0 | 5 | 30 | 12 |
| NB-GLM (Farrington-style) | 780 | 120 | 14 | 246 | 400 | 66.7 | 0.31 | 32.8 | 89.6 | 66 | 28 | 0.0 | 4 | 13 | 11 |

NB-GLM pooled correlation of the two weekly 0/1 series at lag L (radar shifted by L weeks; L < 0 means the radar leads): L=-4: 0.07, L=-3: 0.14, L=-2: 0.22, L=-1: 0.31, L=0: 0.30, L=1: 0.31, L=2: 0.29, L=3: 0.23, L=4: 0.16. Peak at L = 1.

### NDCU-positive = >= 3 MOH area(s) flagged

| method | district-weeks | both | radar only | NDCU only | neither | agreement % | kappa | radar sensitivity vs NDCU % | share of radar alerts with NDCU flag % | NDCU onsets | onsets with a radar alert within +-4 wk | median lag (radar - NDCU, wk) | radar earlier | same week | radar later |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Status quo (2x last year) | 754 | 131 | 206 | 65 | 352 | 64.1 | 0.24 | 66.8 | 38.9 | 34 | 31 | 0.0 | 3 | 22 | 6 |
| EARS C2 | 780 | 65 | 63 | 134 | 518 | 74.7 | 0.25 | 32.7 | 50.8 | 35 | 28 | 0.0 | 4 | 17 | 7 |
| EARS C3 | 780 | 123 | 149 | 76 | 432 | 71.2 | 0.32 | 61.8 | 45.2 | 35 | 34 | 0.0 | 5 | 24 | 5 |
| NB-GLM (Farrington-style) | 780 | 88 | 46 | 111 | 535 | 79.9 | 0.41 | 44.2 | 65.7 | 35 | 22 | 0.0 | 2 | 14 | 6 |

NB-GLM pooled correlation of the two weekly 0/1 series at lag L (radar shifted by L weeks; L < 0 means the radar leads): L=-4: 0.06, L=-3: 0.17, L=-2: 0.22, L=-1: 0.34, L=0: 0.34, L=1: 0.33, L=2: 0.30, L=3: 0.25, L=4: 0.17. Peak at L = -1.

### Disagreements (NB-GLM)

- NDCU >= 3 MOH flagged but no radar alert: 111 district-weeks; largest: Colombo W32 (24 MOH), Colombo W33 (24 MOH), Colombo W1 (23 MOH), Colombo W31 (23 MOH), Colombo W5 (22 MOH), Colombo W4 (22 MOH), Colombo W3 (22 MOH), Colombo W23 (22 MOH), Colombo W2 (21 MOH), Colombo W7 (20 MOH), Colombo W22 (20 MOH), Colombo W6 (20 MOH).
- Radar alert but no MOH flagged: 14 district-weeks: Ampara W25, Ampara W30, Anuradhapura W28, Anuradhapura W30, Badulla W11, Hambantota W17, Kalmunai W25, Kilinochchi W28, Mannar W29, Matale W30, Polonnaruwa W17, Trincomalee W30, Trincomalee W31, Vavuniya W30.

What the data say about the disagreements: of the 111 NDCU-only district-weeks, 58% are Colombo, Gampaha, Galle. In 61% the observed count was above the radar's expected value but within its upper bound, and in 35% at or below the expected value: high in absolute terms (NDCU's view) but within what the radar expects for that district and season. The 14 radar-only district-weeks have a median observed count of 30 (rises from a low base); the busiest weeks are W30 (5), W25 (2), W28 (2). 2026-W14 and W24 are no longer among them because those issues are now queued as `scrambled_weekly_column` (see docs/EXTRACTION_REPORT.md section 5b).

## d) Case studies

![Colombo dengue](figures/radar_case1_dengue_Colombo.png)

![Jaffna leptospirosis](figures/radar_case2_leptospirosis_Jaffna.png)

![Kandy tuberculosis](figures/radar_case3_tuberculosis_Kandy.png)

## e) Track record (for the dashboard)

`data/clean/radar_track_record.parquet`: per series and method, shown alerts, alerts per 100 weeks, and the share of alerts followed by a second high week (the next week also alerting or above its bound).

NB-GLM: 1085 shown alerts over 58,032 series-weeks; 25% followed by a second high week.

## Limitations

- Injected outbreaks are synthetic; detection of real events of other shapes may differ.
- Real alerts are all counted as false for specificity, which understates specificity.
- NB bounds ignore parameter uncertainty; with 1-3 seasons of post-COVID history the seasonal terms are estimated from few cycles.
- TB starts in 2024, so its NB-GLM only predicts from 2025.
