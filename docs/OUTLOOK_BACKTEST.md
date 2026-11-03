# Outlook backtest

Generated 2026-11-03 by `python -m radar_lk.outlook.backtest`. Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (WER Table 1, `extraction_valid` RDHS rows, weekly counts as first printed); rainfall, temperature and humidity: Open-Meteo (CC BY 4.0); external check: National Dengue Control Unit (NDCU) Weekly Dengue Update. This is the proposal's fallback after the NDCU MOH outlook was judged NO-GO: a district-level outlook, leptospirosis primary, dengue secondary, from one disease-agnostic engine. Outputs are population-level signals for planning, not predictions about any person.

## Design: filling the publication gap

- The WER reports a week about **L = 8 weeks** after it ends (`publication_lag_weeks`, measured from the PDFs). Rainfall is observed in near real time. From the latest reported week t (the origin) the outlook forecasts t+1 .. t+10: at the time of use (about t+8) h = 9 is **this week** and h = 10 **next week**; h = 1, 2 are the proposal's horizons (weeks already over but not yet reported).
- Targets: (i) the weekly count; (ii) **elevated** = count >= that district's 80th percentile of its counts in the 104 weeks before t (past-only), floored at 1 case.
- Features: counts y_t..y_t-3, 4- and 8-week means, same week last year, mean count of neighbouring districts at t (HDX polygons; Kalmunai adjacent to Ampara and Batticaloa by rule, `config/district_adjacency.csv`), reporting completeness at t, district, h, Fourier terms of the target's week of year, and weather relative to the TARGET week: rain at lags 2..8, the 4-week rain sum ending at lag 2, mean temperature and humidity at lags 2-4. Lag >= 2 is enforced in code (`features.weather_at`) and tested; for targets up to now + 2 all of it is observed at the time of use.
- Models (fixed settings, nothing tuned on test data): persistence; seasonal climatology (district mean / elevated frequency for the target's week of year +-1 in earlier years); NB GLM (counts) / L2 logistic regression (class); LightGBM (Poisson / binary).
- Rolling origin, expanding window: test origins 2024-W01 to the latest week, refit every 4 weeks on rows whose target week is <= the refit origin. 2023 origins are forecast too but only to fill the calibration pools.
- Uncertainty: counts, rolling split-conformal on past-only residuals normalised by sqrt(pred + 1), pool = the last 52 origins with observed targets, same model and horizon (80% and 90%). Probabilities (GLM and LightGBM): inductive **Venn-Abers** (`venn-abers` package) on the same pool; `p_elevated` is the calibrated probability and [`p_lo`, `p_hi`] its Venn-Abers range. Baselines keep their own probability.
- Skill: MASE = MAE / persistence MAE on the same rows; BSS = 1 - Brier / reference Brier; recall and precision at p >= 0.5. Every model is scored on the same district-weeks.

## Leptospirosis

Backtest origins 2024-W01 to 2026-W32 (136 origins x 26 districts x up to 10 horizons). **Models are selected on 2024 origins only; every number below is on the untouched 2025-26 origins** unless the heading says otherwise.

### Headline (test origins 2025-26): Brier skill vs persistence (BSS), MASE vs persistence, 90% interval coverage (static split-conformal)

| model | h=1 BSS | h=1 MASE | h=1 cov90 % | h=2 BSS | h=2 MASE | h=2 cov90 % | h=9 (this week) BSS | h=9 (this week) MASE | h=9 (this week) cov90 % | h=10 (next week) BSS | h=10 (next week) MASE | h=10 (next week) cov90 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Persistence | 0.00 | 1.00 | 91.07 | 0.00 | 1.00 | 91.39 | 0.00 | 1.00 | 92.62 | 0.00 | 1.00 | 93.05 |
| Seasonal climatology | 0.33 | 0.89 | 94.35 | 0.36 | 0.86 | 94.57 | 0.51 | 0.68 | 95.53 | 0.50 | 0.67 | 95.68 |
| NB GLM / logistic | 0.40 | 0.91 | 92.07 | 0.42 | 0.89 | 92.93 | 0.52 | 0.71 | 94.80 | 0.50 | 0.70 | 95.10 |
| LightGBM | 0.37 | 0.93 | 92.40 | 0.39 | 0.91 | 92.45 | 0.50 | 0.76 | 93.87 | 0.49 | 0.75 | 94.63 |

![skill](figures/outlook_leptospirosis_skill.png)

### Model selection (2024 origins) -> what the dashboard shows

Candidates: persistence, seasonal climatology, NB GLM / logistic, LightGBM. Counts are selected by MASE, P(elevated) by Brier, on 2024 origins only; any model within 0.01 of the best is a tie and the simplest of the tied models is kept (persistence < climatology < GLM < LightGBM). This replaces the earlier rule (LightGBM unless persistence beats it), which looked at all years and ignored the GLM.

| h | selected count model | count selection reason | selected probability model | probability selection reason |
|---|---|---|---|---|
| 1 | NB GLM / logistic | MASE best on 2024 origins (0.904) | NB GLM / logistic | Brier best on 2024 origins (0.211) |
| 2 | NB GLM / logistic | MASE best on 2024 origins (0.890) | NB GLM / logistic | Brier best on 2024 origins (0.218) |
| 3 | NB GLM / logistic | MASE best on 2024 origins (0.854) | NB GLM / logistic | Brier best on 2024 origins (0.227) |
| 4 | NB GLM / logistic | MASE best on 2024 origins (0.821) | NB GLM / logistic | Brier best on 2024 origins (0.232) |
| 5 | NB GLM / logistic | MASE best on 2024 origins (0.790) | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.236, glm 0.237); the simpler model is kept |
| 6 | NB GLM / logistic | MASE within 0.01 of the best on 2024 origins (lightgbm 0.759, glm 0.767); the simpler model is kept | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.238, glm 0.239); the simpler model is kept |
| 7 | LightGBM | MASE best on 2024 origins (0.747) | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.240, glm 0.244); the simpler model is kept |
| 8 | LightGBM | MASE best on 2024 origins (0.752) | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.243, glm 0.246); the simpler model is kept |
| 9 | LightGBM | MASE best on 2024 origins (0.736) | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.244, glm 0.248); the simpler model is kept |
| 10 | LightGBM | MASE best on 2024 origins (0.705) | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.247, glm 0.250); the simpler model is kept |

How the selected models do on the untouched test (2025-26 origins):

| h | selected count model | its MASE (test) | LightGBM MASE (test) | selected probability model | its BSS vs persistence (test) | its BSS vs climatology (test) | LightGBM BSS vs persistence (test) |
|---|---|---|---|---|---|---|---|
| 1 | NB GLM / logistic | 0.915 | 0.931 | NB GLM / logistic | 0.397 | 0.100 | 0.367 |
| 2 | NB GLM / logistic | 0.890 | 0.909 | NB GLM / logistic | 0.418 | 0.085 | 0.391 |
| 3 | NB GLM / logistic | 0.852 | 0.865 | NB GLM / logistic | 0.411 | 0.078 | 0.382 |
| 4 | NB GLM / logistic | 0.808 | 0.830 | NB GLM / logistic | 0.452 | 0.058 | 0.423 |
| 5 | NB GLM / logistic | 0.785 | 0.811 | NB GLM / logistic | 0.467 | 0.048 | 0.439 |
| 6 | NB GLM / logistic | 0.752 | 0.798 | NB GLM / logistic | 0.472 | 0.059 | 0.442 |
| 7 | LightGBM | 0.764 | 0.764 | NB GLM / logistic | 0.497 | 0.047 | 0.467 |
| 8 | LightGBM | 0.760 | 0.760 | NB GLM / logistic | 0.510 | 0.029 | 0.484 |
| 9 | LightGBM | 0.761 | 0.761 | NB GLM / logistic | 0.524 | 0.019 | 0.501 |
| 10 | LightGBM | 0.753 | 0.753 | NB GLM / logistic | 0.502 | 0.008 | 0.485 |

The selected models beat persistence on both targets at every horizon on the test.

### Counts, every horizon (test)

| model | h | n | MAE | RMSE | MASE vs persistence | coverage80 % | width80 | coverage90 % | width90 | coverage80 ACI % | coverage90 ACI % | width90 ACI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 2106 | 3.943 | 5.990 | 0.931 | 81.814 | 10.838 | 92.403 | 15.029 | 80.912 | 90.503 | 14.476 |
| NB GLM / logistic | 1 | 2106 | 3.874 | 6.157 | 0.915 | 81.719 | 10.629 | 92.070 | 14.331 | 81.292 | 90.741 | 14.161 |
| Persistence | 1 | 2106 | 4.234 | 6.626 | 1.000 | 81.529 | 11.603 | 91.073 | 15.997 | 81.244 | 90.741 | 16.023 |
| Seasonal climatology | 1 | 2106 | 3.788 | 5.901 | 0.895 | 85.850 | 11.790 | 94.349 | 16.726 | 81.387 | 90.836 | 14.637 |
| LightGBM | 2 | 2080 | 3.998 | 6.069 | 0.909 | 82.019 | 11.002 | 92.452 | 15.248 | 80.913 | 90.481 | 14.561 |
| NB GLM / logistic | 2 | 2080 | 3.914 | 6.234 | 0.890 | 82.067 | 10.843 | 92.933 | 14.832 | 81.298 | 90.817 | 14.303 |
| Persistence | 2 | 2080 | 4.398 | 6.992 | 1.000 | 81.779 | 11.897 | 91.394 | 16.184 | 81.587 | 90.817 | 18.530 |
| Seasonal climatology | 2 | 2080 | 3.770 | 5.876 | 0.857 | 85.865 | 11.801 | 94.567 | 16.762 | 81.538 | 90.865 | 14.435 |
| LightGBM | 3 | 2054 | 4.026 | 6.066 | 0.865 | 82.571 | 11.202 | 93.135 | 15.482 | 80.818 | 90.555 | 14.669 |
| NB GLM / logistic | 3 | 2054 | 3.964 | 6.161 | 0.852 | 83.155 | 11.142 | 93.087 | 15.292 | 81.548 | 90.798 | 14.416 |
| Persistence | 3 | 2054 | 4.654 | 7.336 | 1.000 | 81.451 | 12.517 | 91.383 | 17.063 | 81.548 | 90.944 | 22.083 |
| Seasonal climatology | 3 | 2054 | 3.766 | 5.878 | 0.809 | 86.076 | 11.826 | 94.596 | 16.821 | 81.451 | 90.847 | 14.593 |
| LightGBM | 4 | 2028 | 4.056 | 6.154 | 0.830 | 82.643 | 11.303 | 92.998 | 15.795 | 80.819 | 90.533 | 15.389 |
| NB GLM / logistic | 4 | 2028 | 3.945 | 6.041 | 0.808 | 83.481 | 11.218 | 93.343 | 15.557 | 81.410 | 90.730 | 14.757 |
| Persistence | 4 | 2028 | 4.885 | 7.596 | 1.000 | 82.051 | 13.236 | 91.272 | 17.751 | 81.410 | 90.828 | 25.690 |
| Seasonal climatology | 4 | 2028 | 3.738 | 5.825 | 0.765 | 86.391 | 11.853 | 94.921 | 16.885 | 81.460 | 90.828 | 14.591 |
| LightGBM | 5 | 2002 | 4.078 | 6.146 | 0.811 | 82.767 | 11.436 | 93.057 | 15.978 | 80.669 | 90.659 | 19.290 |
| NB GLM / logistic | 5 | 2002 | 3.950 | 5.945 | 0.785 | 84.416 | 11.556 | 93.906 | 15.840 | 81.518 | 90.709 | 19.712 |
| Persistence | 5 | 2002 | 5.030 | 7.755 | 1.000 | 82.867 | 14.048 | 91.708 | 18.786 | 82.168 | 90.509 | 22.340 |
| Seasonal climatology | 5 | 2002 | 3.730 | 5.817 | 0.742 | 86.763 | 11.885 | 95.155 | 16.953 | 81.419 | 90.759 | 14.856 |
| LightGBM | 6 | 1976 | 4.077 | 6.146 | 0.798 | 82.996 | 11.563 | 93.370 | 16.044 | 80.769 | 90.638 | 25.025 |
| NB GLM / logistic | 6 | 1976 | 3.842 | 5.739 | 0.752 | 84.514 | 11.512 | 94.028 | 15.660 | 81.427 | 90.891 | 26.202 |
| Persistence | 6 | 1976 | 5.107 | 7.916 | 1.000 | 82.794 | 14.106 | 91.447 | 19.025 | 81.022 | 91.447 | 45.889 |
| Seasonal climatology | 6 | 1976 | 3.728 | 5.829 | 0.730 | 87.095 | 11.929 | 95.091 | 17.040 | 81.123 | 90.739 | 17.857 |
| LightGBM | 7 | 1976 | 4.124 | 6.197 | 0.764 | 82.794 | 11.659 | 93.522 | 16.377 | 81.073 | 91.144 | 48.784 |
| NB GLM / logistic | 7 | 1976 | 3.846 | 5.692 | 0.712 | 84.413 | 11.560 | 94.231 | 15.985 | 81.326 | 91.397 | 51.220 |
| Persistence | 7 | 1976 | 5.400 | 8.339 | 1.000 | 82.591 | 14.898 | 91.852 | 19.949 | 81.984 | 91.903 | 52.039 |
| Seasonal climatology | 7 | 1976 | 3.728 | 5.829 | 0.690 | 87.247 | 12.002 | 95.142 | 17.162 | 81.123 | 91.346 | 30.426 |
| LightGBM | 8 | 1950 | 4.158 | 6.248 | 0.760 | 83.026 | 11.779 | 94.256 | 16.609 | 81.385 | 91.282 | 56.526 |
| NB GLM / logistic | 8 | 1950 | 3.850 | 5.660 | 0.703 | 84.718 | 11.615 | 95.026 | 16.271 | 81.846 | 92.051 | 71.273 |
| Persistence | 8 | 1950 | 5.472 | 8.373 | 1.000 | 82.462 | 15.033 | 92.359 | 19.965 | 82.462 | 92.769 | 101.762 |
| Seasonal climatology | 8 | 1950 | 3.689 | 5.772 | 0.674 | 87.538 | 12.071 | 95.385 | 17.272 | 80.872 | 91.744 | 40.340 |
| LightGBM | 9 | 1924 | 4.164 | 6.256 | 0.761 | 83.108 | 11.871 | 93.867 | 16.657 | 81.289 | 91.580 | 71.578 |
| NB GLM / logistic | 9 | 1924 | 3.863 | 5.679 | 0.706 | 85.031 | 11.692 | 94.802 | 16.362 | 81.757 | 92.827 | 82.534 |
| Persistence | 9 | 1924 | 5.474 | 8.300 | 1.000 | 82.380 | 15.016 | 92.620 | 20.268 | 83.212 | 93.295 | 126.954 |
| Seasonal climatology | 9 | 1924 | 3.700 | 5.790 | 0.676 | 87.682 | 12.143 | 95.530 | 17.392 | 81.341 | 91.944 | 44.972 |
| LightGBM | 10 | 1898 | 4.154 | 6.261 | 0.753 | 83.930 | 11.972 | 94.626 | 16.891 | 81.770 | 91.886 | 75.961 |
| NB GLM / logistic | 10 | 1898 | 3.843 | 5.668 | 0.697 | 84.563 | 11.724 | 95.100 | 16.754 | 83.456 | 93.625 | 98.787 |
| Persistence | 10 | 1898 | 5.514 | 8.537 | 1.000 | 83.720 | 15.490 | 93.045 | 21.106 | 85.142 | 91.465 | 79.413 |
| Seasonal climatology | 10 | 1898 | 3.686 | 5.775 | 0.669 | 87.987 | 12.209 | 95.680 | 17.502 | 82.403 | 91.728 | 41.657 |

### Elevated, every horizon (test)

| model | h | n_class | base rate % | Brier | BSS vs persistence | BSS vs climatology | recall | precision | AUROC | PR-AUC | mean p range |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 2106 | 20.085 | 0.144 | 0.367 | 0.054 | 0.144 | 0.409 | 0.737 | 0.396 | 0.015 |
| NB GLM / logistic | 1 | 2106 | 20.085 | 0.137 | 0.397 | 0.100 | 0.225 | 0.597 | 0.758 | 0.473 | 0.017 |
| Persistence | 1 | 2106 | 20.085 | 0.228 | 0.000 | -0.493 | 0.452 | 0.435 | 0.652 | 0.307 |  |
| Seasonal climatology | 1 | 2106 | 20.085 | 0.153 | 0.330 | 0.000 | 0.132 | 0.519 | 0.682 | 0.358 |  |
| LightGBM | 2 | 2080 | 19.760 | 0.145 | 0.391 | 0.042 | 0.105 | 0.489 | 0.728 | 0.375 | 0.017 |
| NB GLM / logistic | 2 | 2080 | 19.760 | 0.138 | 0.418 | 0.085 | 0.217 | 0.574 | 0.752 | 0.443 | 0.016 |
| Persistence | 2 | 2080 | 19.760 | 0.238 | 0.000 | -0.573 | 0.423 | 0.403 | 0.634 | 0.284 |  |
| Seasonal climatology | 2 | 2080 | 19.760 | 0.151 | 0.364 | 0.000 | 0.141 | 0.537 | 0.676 | 0.354 |  |
| LightGBM | 3 | 2054 | 19.718 | 0.146 | 0.382 | 0.033 | 0.111 | 0.474 | 0.724 | 0.371 | 0.016 |
| NB GLM / logistic | 3 | 2054 | 19.718 | 0.139 | 0.411 | 0.078 | 0.190 | 0.597 | 0.749 | 0.452 | 0.016 |
| Persistence | 3 | 2054 | 19.718 | 0.236 | 0.000 | -0.565 | 0.437 | 0.408 | 0.641 | 0.289 |  |
| Seasonal climatology | 3 | 2054 | 19.718 | 0.151 | 0.361 | 0.000 | 0.146 | 0.551 | 0.676 | 0.354 |  |
| LightGBM | 4 | 2028 | 19.477 | 0.147 | 0.423 | 0.008 | 0.114 | 0.405 | 0.720 | 0.352 | 0.015 |
| NB GLM / logistic | 4 | 2028 | 19.477 | 0.140 | 0.452 | 0.058 | 0.159 | 0.600 | 0.747 | 0.432 | 0.015 |
| Persistence | 4 | 2028 | 19.477 | 0.255 | 0.000 | -0.719 | 0.397 | 0.359 | 0.613 | 0.260 |  |
| Seasonal climatology | 4 | 2028 | 19.477 | 0.149 | 0.418 | 0.000 | 0.149 | 0.562 | 0.681 | 0.355 |  |
| LightGBM | 5 | 2002 | 19.331 | 0.148 | 0.439 | -0.001 | 0.085 | 0.434 | 0.708 | 0.345 | 0.014 |
| NB GLM / logistic | 5 | 2002 | 19.331 | 0.141 | 0.467 | 0.048 | 0.186 | 0.621 | 0.743 | 0.424 | 0.014 |
| Persistence | 5 | 2002 | 19.331 | 0.264 | 0.000 | -0.786 | 0.375 | 0.336 | 0.599 | 0.247 |  |
| Seasonal climatology | 5 | 2002 | 19.331 | 0.148 | 0.440 | 0.000 | 0.155 | 0.566 | 0.679 | 0.356 |  |
| LightGBM | 6 | 1976 | 19.585 | 0.148 | 0.442 | 0.005 | 0.103 | 0.408 | 0.722 | 0.340 | 0.013 |
| NB GLM / logistic | 6 | 1976 | 19.585 | 0.140 | 0.472 | 0.059 | 0.165 | 0.674 | 0.745 | 0.456 | 0.015 |
| Persistence | 6 | 1976 | 19.585 | 0.265 | 0.000 | -0.782 | 0.377 | 0.340 | 0.600 | 0.250 |  |
| Seasonal climatology | 6 | 1976 | 19.585 | 0.149 | 0.439 | 0.000 | 0.152 | 0.567 | 0.681 | 0.361 |  |
| LightGBM | 7 | 1976 | 19.838 | 0.152 | 0.467 | -0.010 | 0.079 | 0.341 | 0.712 | 0.337 | 0.015 |
| NB GLM / logistic | 7 | 1976 | 19.838 | 0.144 | 0.497 | 0.047 | 0.217 | 0.659 | 0.737 | 0.446 | 0.016 |
| Persistence | 7 | 1976 | 19.838 | 0.285 | 0.000 | -0.892 | 0.344 | 0.305 | 0.575 | 0.235 |  |
| Seasonal climatology | 7 | 1976 | 19.838 | 0.151 | 0.472 | 0.000 | 0.145 | 0.553 | 0.680 | 0.358 |  |
| LightGBM | 8 | 1950 | 19.641 | 0.153 | 0.484 | -0.024 | 0.073 | 0.289 | 0.705 | 0.317 | 0.015 |
| NB GLM / logistic | 8 | 1950 | 19.641 | 0.145 | 0.510 | 0.029 | 0.193 | 0.661 | 0.730 | 0.421 | 0.016 |
| Persistence | 8 | 1950 | 19.641 | 0.297 | 0.000 | -0.983 | 0.321 | 0.278 | 0.559 | 0.223 |  |
| Seasonal climatology | 8 | 1950 | 19.641 | 0.150 | 0.496 | 0.000 | 0.144 | 0.550 | 0.679 | 0.357 |  |
| LightGBM | 9 | 1924 | 19.699 | 0.154 | 0.501 | -0.028 | 0.058 | 0.310 | 0.700 | 0.314 | 0.014 |
| NB GLM / logistic | 9 | 1924 | 19.699 | 0.147 | 0.524 | 0.019 | 0.140 | 0.688 | 0.723 | 0.418 | 0.014 |
| Persistence | 9 | 1924 | 19.699 | 0.309 | 0.000 | -1.060 | 0.288 | 0.252 | 0.539 | 0.213 |  |
| Seasonal climatology | 9 | 1924 | 19.699 | 0.150 | 0.515 | 0.000 | 0.145 | 0.550 | 0.680 | 0.358 |  |
| LightGBM | 10 | 1898 | 19.652 | 0.153 | 0.485 | -0.026 | 0.070 | 0.377 | 0.705 | 0.328 | 0.015 |
| NB GLM / logistic | 10 | 1898 | 19.652 | 0.148 | 0.502 | 0.008 | 0.153 | 0.640 | 0.726 | 0.420 | 0.016 |
| Persistence | 10 | 1898 | 19.652 | 0.297 | 0.000 | -0.992 | 0.311 | 0.275 | 0.555 | 0.221 |  |
| Seasonal climatology | 10 | 1898 | 19.652 | 0.149 | 0.498 | 0.000 | 0.145 | 0.529 | 0.687 | 0.358 |  |

![reliability](figures/outlook_leptospirosis_reliability.png)

`mean p range` is the width of the Venn-Abers calibration range. It is narrow because the calibration pool is large and it describes calibration uncertainty only; outbreak uncertainty is carried by the count interval. The dashboard shows the range only in a tooltip, labelled 'calibration range'.

### Count intervals: static split-conformal vs adaptive conformal (ACI)

ACI (Gibbs & Candes 2021) keeps the same rolling pool of past-only scores but adapts the working miscoverage online: when a forecast's target is reported, the miscoverage moves by gamma = 0.005 x (nominal - miss), per forecast, with gamma fixed a priori. The dashboard uses ACI only if it brings 2026 coverage closer to nominal without moving 2024-25 coverage more than 2.5 points from nominal.

| scope (selected count models, all horizons) | n | 80% static | 80% ACI | 90% static | 90% ACI | 90% width static | 90% width ACI |
|---|---|---|---|---|---|---|---|
| 2024-25 targets | 25090 | 83.2 | 80.8 | 92.6 | 90.6 | 17.8 | 39.6 |
| 2026 targets | 8060 | 82.7 | 82.8 | 93.3 | 91.5 | 13.7 | 14.0 |
| test (2025-26 origins) | 19994 | 83.2 | 81.4 | 93.5 | 91.0 | 15.8 | 35.0 |

**ACI not used: 2026 coverage 80/90 static 82.7/93.3% -> ACI 82.8/91.5% (not closer to nominal); 2024-25 ACI 80.8/90.6% (within +-2.5 pp of nominal).**

### 2026 separately (targets in 2026)

| model | h | n | MASE vs persistence | BSS vs persistence | BSS vs climatology | AUROC | coverage90 % | coverage90 ACI % |
|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 806 | 0.904 | 0.441 | 0.107 | 0.778 | 93.052 | 91.687 |
| NB GLM / logistic | 1 | 806 | 0.885 | 0.443 | 0.111 | 0.771 | 92.680 | 91.563 |
| Persistence | 1 | 806 | 1.000 | 0.000 | -0.597 | 0.636 | 91.687 | 90.819 |
| Seasonal climatology | 1 | 806 | 0.865 | 0.374 | 0.000 | 0.669 | 93.176 | 91.191 |
| LightGBM | 2 | 806 | 0.928 | 0.469 | 0.120 | 0.782 | 93.176 | 92.184 |
| NB GLM / logistic | 2 | 806 | 0.933 | 0.464 | 0.112 | 0.778 | 93.424 | 91.935 |
| Persistence | 2 | 806 | 1.000 | 0.000 | -0.657 | 0.652 | 94.045 | 93.424 |
| Seasonal climatology | 2 | 806 | 0.872 | 0.396 | 0.000 | 0.665 | 93.300 | 91.935 |
| LightGBM | 9 | 806 | 0.671 | 0.592 | 0.039 | 0.733 | 93.052 | 90.074 |
| NB GLM / logistic | 9 | 806 | 0.667 | 0.607 | 0.075 | 0.731 | 93.424 | 91.067 |
| Persistence | 9 | 806 | 1.000 | 0.000 | -1.354 | 0.551 | 92.928 | 96.650 |
| Seasonal climatology | 9 | 806 | 0.594 | 0.575 | 0.000 | 0.673 | 94.789 | 92.432 |
| LightGBM | 10 | 806 | 0.682 | 0.590 | 0.044 | 0.748 | 94.169 | 90.943 |
| NB GLM / logistic | 10 | 806 | 0.681 | 0.605 | 0.079 | 0.752 | 93.797 | 92.060 |
| Persistence | 10 | 806 | 1.000 | 0.000 | -1.332 | 0.543 | 93.424 | 97.270 |
| Seasonal climatology | 10 | 806 | 0.607 | 0.571 | 0.000 | 0.676 | 94.913 | 92.556 |

### What drives LightGBM (live models, on their training rows)

Mean |SHAP| is LightGBM's own TreeSHAP (`pred_contrib`), on the log scale of the model (log count / log-odds). Gain = share of split gain.

Elevated (binary), top 12:

| feature | gain % | mean |SHAP| |
|---|---|---|
| thr | 16.734 | 0.692 |
| rh | 8.242 | 0.240 |
| area | 18.616 | 0.233 |
| temp | 4.718 | 0.133 |
| cos1 | 7.660 | 0.129 |
| rain_l6 | 3.479 | 0.113 |
| sin2 | 3.714 | 0.112 |
| rain_l5 | 3.677 | 0.111 |
| rain_l4 | 4.228 | 0.088 |
| y0 | 1.574 | 0.087 |
| rain4 | 4.126 | 0.070 |
| sin1 | 2.677 | 0.066 |

Count (Poisson), top 8:

| feature | gain % | mean |SHAP| |
|---|---|---|
| area | 51.267 | 0.416 |
| thr | 15.483 | 0.208 |
| m4 | 6.328 | 0.127 |
| rh | 4.819 | 0.111 |
| rain4 | 3.859 | 0.070 |
| m8 | 3.413 | 0.057 |
| cos1 | 3.101 | 0.053 |
| temp | 1.443 | 0.040 |

### Rainfall lag

| rain lag (weeks before target) | model: mean SHAP if heavy rain (log-odds) | model: mean SHAP otherwise | data: share elevated after heavy rain % | data: share elevated otherwise % | data: ratio | heavy-rain district-weeks |
|---|---|---|---|---|---|---|
| 2 | 0.02 | -0.01 | 45.54 | 31.07 | 1.47 | 527 |
| 3 | 0.08 | -0.02 | 49.63 | 30.59 | 1.62 | 534 |
| 4 | 0.09 | -0.02 | 54.24 | 30.21 | 1.80 | 507 |
| 5 | 0.12 | -0.01 | 50.77 | 30.52 | 1.66 | 520 |
| 6 | 0.15 | -0.01 | 49.80 | 30.66 | 1.62 | 512 |
| 7 | 0.08 | -0.01 | 50.09 | 30.53 | 1.64 | 535 |
| 8 | 0.02 | -0.00 | 48.33 | 30.72 | 1.57 | 538 |

![rain lag](figures/outlook_leptospirosis_rain_lag.png)

**Finding: leptospirosis risk rises about 6 weeks after a very wet week in the model (largest push on P(elevated)); in the raw data the excess is largest 4 weeks after.** Association, not proof of cause: wet weeks also cluster in the monsoon seasons the Fourier terms describe.

### Live outlook (origin 2026-W33, as of 2026-08-16): highest P(elevated) for this week and next week

| area | target_week | h | model | p_elevated | p_lo | p_hi | pred_count | lo90 | hi90 | elevated_threshold |
|---|---|---|---|---|---|---|---|---|---|---|
| Kalutara | 2026-W43 | 10 | glm | 0.27 | 0.26 | 0.27 | 14.60 | 4.89 | 24.31 | 17.20 |
| Nuwara Eliya | 2026-W43 | 10 | glm | 0.27 | 0.26 | 0.27 | 5.86 | 0.00 | 12.30 | 7.00 |
| Kalutara | 2026-W42 | 9 | glm | 0.20 | 0.19 | 0.20 | 14.78 | 5.06 | 24.50 | 17.20 |
| Kandy | 2026-W43 | 10 | glm | 0.20 | 0.18 | 0.20 | 7.40 | 0.28 | 14.53 | 9.00 |
| Matara | 2026-W43 | 10 | glm | 0.20 | 0.18 | 0.20 | 12.51 | 3.47 | 21.54 | 15.00 |
| Matara | 2026-W42 | 9 | glm | 0.19 | 0.19 | 0.19 | 11.90 | 3.12 | 20.69 | 15.00 |
| Nuwara Eliya | 2026-W42 | 9 | glm | 0.19 | 0.19 | 0.19 | 5.36 | 0.00 | 11.52 | 7.00 |
| Hambantota | 2026-W43 | 10 | glm | 0.18 | 0.17 | 0.18 | 7.90 | 0.57 | 15.24 | 10.00 |
| Kegalle | 2026-W43 | 10 | glm | 0.17 | 0.17 | 0.18 | 18.97 | 7.99 | 29.96 | 25.20 |
| Badulla | 2026-W43 | 10 | glm | 0.17 | 0.17 | 0.18 | 7.23 | 0.18 | 14.28 | 9.00 |

## Dengue

Backtest origins 2024-W01 to 2026-W32 (136 origins x 26 districts x up to 10 horizons). **Models are selected on 2024 origins only; every number below is on the untouched 2025-26 origins** unless the heading says otherwise.

### Headline (test origins 2025-26): Brier skill vs persistence (BSS), MASE vs persistence, 90% interval coverage (static split-conformal)

| model | h=1 BSS | h=1 MASE | h=1 cov90 % | h=2 BSS | h=2 MASE | h=2 cov90 % | h=9 (this week) BSS | h=9 (this week) MASE | h=9 (this week) cov90 % | h=10 (next week) BSS | h=10 (next week) MASE | h=10 (next week) cov90 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Persistence | 0.00 | 1.00 | 87.26 | 0.00 | 1.00 | 86.22 | 0.00 | 1.00 | 82.09 | 0.00 | 1.00 | 82.37 |
| Seasonal climatology | -0.31 | 2.45 | 83.41 | -0.31 | 2.04 | 83.06 | 0.25 | 1.06 | 80.93 | 0.28 | 1.01 | 80.72 |
| NB GLM / logistic | 0.28 | 1.35 | 86.73 | 0.26 | 1.24 | 85.98 | 0.37 | 0.99 | 81.98 | 0.38 | 0.96 | 81.94 |
| LightGBM | 0.16 | 1.70 | 86.11 | 0.11 | 1.47 | 86.03 | 0.30 | 0.93 | 82.14 | 0.30 | 0.90 | 81.57 |

![skill](figures/outlook_dengue_skill.png)

### Model selection (2024 origins) -> what the dashboard shows

Candidates: persistence, seasonal climatology, NB GLM / logistic, LightGBM. Counts are selected by MASE, P(elevated) by Brier, on 2024 origins only; any model within 0.01 of the best is a tie and the simplest of the tied models is kept (persistence < climatology < GLM < LightGBM). This replaces the earlier rule (LightGBM unless persistence beats it), which looked at all years and ignored the GLM.

| h | selected count model | count selection reason | selected probability model | probability selection reason |
|---|---|---|---|---|
| 1 | Persistence | MASE best on 2024 origins (1.000) | Persistence | Brier within 0.01 of the best on 2024 origins (glm 0.103, persistence 0.103); the simpler model is kept |
| 2 | Persistence | MASE best on 2024 origins (1.000) | Persistence | Brier within 0.01 of the best on 2024 origins (glm 0.113, persistence 0.114); the simpler model is kept |
| 3 | Persistence | MASE best on 2024 origins (1.000) | NB GLM / logistic | Brier best on 2024 origins (0.121) |
| 4 | Persistence | MASE best on 2024 origins (1.000) | Persistence | Brier within 0.01 of the best on 2024 origins (glm 0.132, persistence 0.141); the simpler model is kept |
| 5 | Persistence | MASE within 0.01 of the best on 2024 origins (glm 0.994, persistence 1.000); the simpler model is kept | Seasonal climatology | Brier within 0.01 of the best on 2024 origins (glm 0.146, climatology 0.148); the simpler model is kept |
| 6 | NB GLM / logistic | MASE best on 2024 origins (0.943) | Seasonal climatology | Brier best on 2024 origins (0.140) |
| 7 | NB GLM / logistic | MASE best on 2024 origins (0.913) | Seasonal climatology | Brier best on 2024 origins (0.140) |
| 8 | NB GLM / logistic | MASE best on 2024 origins (0.911) | Seasonal climatology | Brier best on 2024 origins (0.135) |
| 9 | NB GLM / logistic | MASE best on 2024 origins (0.911) | Seasonal climatology | Brier best on 2024 origins (0.133) |
| 10 | Seasonal climatology | MASE best on 2024 origins (0.891) | Seasonal climatology | Brier best on 2024 origins (0.131) |

How the selected models do on the untouched test (2025-26 origins):

| h | selected count model | its MASE (test) | LightGBM MASE (test) | selected probability model | its BSS vs persistence (test) | its BSS vs climatology (test) | LightGBM BSS vs persistence (test) |
|---|---|---|---|---|---|---|---|
| 1 | Persistence | 1.000 | 1.704 | Persistence | 0.000 | 0.237 | 0.162 |
| 2 | Persistence | 1.000 | 1.473 | Persistence | 0.000 | 0.234 | 0.112 |
| 3 | Persistence | 1.000 | 1.192 | NB GLM / logistic | 0.328 | 0.393 | 0.195 |
| 4 | Persistence | 1.000 | 1.087 | Persistence | 0.000 | 0.081 | 0.176 |
| 5 | Persistence | 1.000 | 1.013 | Seasonal climatology | 0.032 | 0.000 | 0.221 |
| 6 | NB GLM / logistic | 0.965 | 0.962 | Seasonal climatology | 0.072 | 0.000 | 0.217 |
| 7 | NB GLM / logistic | 0.969 | 0.941 | Seasonal climatology | 0.190 | 0.000 | 0.289 |
| 8 | NB GLM / logistic | 0.975 | 0.930 | Seasonal climatology | 0.197 | 0.000 | 0.272 |
| 9 | NB GLM / logistic | 0.987 | 0.933 | Seasonal climatology | 0.252 | 0.000 | 0.298 |
| 10 | Seasonal climatology | 1.011 | 0.905 | Seasonal climatology | 0.283 | 0.000 | 0.302 |

**At some horizons a selected model does not beat persistence on the test (MASE >= 1 or BSS <= 0); see the table.**

### Counts, every horizon (test)

| model | h | n | MAE | RMSE | MASE vs persistence | coverage80 % | width80 | coverage90 % | width90 | coverage80 ACI % | coverage90 ACI % | width90 ACI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 2080 | 25.493 | 89.372 | 1.704 | 76.971 | 34.952 | 86.106 | 48.825 | 78.894 | 89.087 | 71.737 |
| NB GLM / logistic | 1 | 2080 | 20.265 | 55.435 | 1.354 | 76.394 | 36.000 | 86.731 | 50.032 | 78.798 | 89.087 | 81.446 |
| Persistence | 1 | 2080 | 14.962 | 39.876 | 1.000 | 76.154 | 30.436 | 87.260 | 41.652 | 78.462 | 89.087 | 71.242 |
| Seasonal climatology | 1 | 2080 | 36.679 | 111.080 | 2.452 | 73.990 | 43.548 | 83.413 | 62.609 | 78.077 | 88.894 | 103.588 |
| LightGBM | 2 | 2054 | 26.608 | 91.740 | 1.473 | 77.410 | 35.859 | 86.027 | 50.213 | 78.092 | 89.094 | 87.885 |
| NB GLM / logistic | 2 | 2054 | 22.315 | 64.276 | 1.236 | 76.826 | 36.889 | 85.979 | 50.336 | 78.286 | 88.900 | 89.445 |
| Persistence | 2 | 2054 | 18.058 | 49.487 | 1.000 | 75.268 | 33.542 | 86.222 | 46.195 | 77.945 | 88.802 | 74.750 |
| Seasonal climatology | 2 | 2054 | 36.790 | 111.614 | 2.037 | 74.099 | 43.035 | 83.057 | 61.614 | 77.848 | 89.192 | 104.917 |
| LightGBM | 3 | 2028 | 27.861 | 94.664 | 1.192 | 76.578 | 36.263 | 85.404 | 50.468 | 77.022 | 88.264 | 97.743 |
| NB GLM / logistic | 3 | 2028 | 24.946 | 74.854 | 1.067 | 75.542 | 37.124 | 84.961 | 51.022 | 77.170 | 88.116 | 94.060 |
| Persistence | 3 | 2028 | 23.381 | 69.378 | 1.000 | 74.507 | 36.930 | 85.158 | 52.255 | 79.043 | 88.659 | 106.690 |
| Seasonal climatology | 3 | 2028 | 36.895 | 112.138 | 1.578 | 73.718 | 42.555 | 82.742 | 60.598 | 76.824 | 88.215 | 112.554 |
| LightGBM | 4 | 2002 | 28.799 | 96.764 | 1.087 | 76.823 | 36.991 | 84.815 | 51.312 | 75.874 | 87.163 | 99.373 |
| NB GLM / logistic | 4 | 2002 | 27.215 | 83.719 | 1.028 | 75.774 | 37.834 | 84.765 | 51.234 | 76.274 | 87.313 | 98.353 |
| Persistence | 4 | 2002 | 26.483 | 80.042 | 1.000 | 74.925 | 40.340 | 84.615 | 57.214 | 78.521 | 87.962 | 110.446 |
| Seasonal climatology | 4 | 2002 | 37.011 | 112.733 | 1.398 | 73.427 | 42.153 | 82.418 | 59.740 | 76.024 | 87.313 | 114.254 |
| LightGBM | 5 | 1976 | 30.017 | 99.699 | 1.013 | 76.265 | 37.643 | 84.211 | 51.092 | 75.354 | 85.931 | 91.057 |
| NB GLM / logistic | 5 | 1976 | 29.318 | 91.709 | 0.990 | 75.152 | 38.498 | 84.109 | 51.325 | 75.304 | 85.779 | 107.736 |
| Persistence | 5 | 1976 | 29.628 | 89.922 | 1.000 | 75.000 | 42.345 | 84.261 | 62.528 | 77.277 | 86.842 | 143.371 |
| Seasonal climatology | 5 | 1976 | 37.199 | 113.368 | 1.256 | 73.431 | 41.829 | 81.984 | 59.035 | 75.152 | 86.589 | 119.248 |
| LightGBM | 6 | 1950 | 31.068 | 101.799 | 0.962 | 76.000 | 38.337 | 83.846 | 52.327 | 74.667 | 84.667 | 90.830 |
| NB GLM / logistic | 6 | 1950 | 31.162 | 98.127 | 0.965 | 74.974 | 38.832 | 83.692 | 51.701 | 74.000 | 84.718 | 118.721 |
| Persistence | 6 | 1950 | 32.292 | 96.129 | 1.000 | 73.641 | 44.350 | 83.436 | 63.557 | 76.103 | 85.744 | 164.892 |
| Seasonal climatology | 6 | 1950 | 37.414 | 114.046 | 1.159 | 73.333 | 41.588 | 81.538 | 58.473 | 74.410 | 85.436 | 108.951 |
| LightGBM | 7 | 1950 | 31.736 | 102.797 | 0.941 | 76.667 | 39.553 | 83.128 | 52.800 | 74.410 | 84.051 | 86.853 |
| NB GLM / logistic | 7 | 1950 | 32.703 | 102.466 | 0.969 | 74.462 | 39.621 | 83.744 | 52.259 | 73.795 | 84.205 | 104.322 |
| Persistence | 7 | 1950 | 33.737 | 98.938 | 1.000 | 73.179 | 45.858 | 83.436 | 66.551 | 75.487 | 85.128 | 215.848 |
| Seasonal climatology | 7 | 1950 | 37.414 | 114.046 | 1.109 | 73.333 | 41.645 | 81.538 | 58.317 | 73.590 | 86.615 | 114.832 |
| LightGBM | 8 | 1924 | 32.652 | 104.371 | 0.930 | 76.403 | 39.639 | 82.744 | 53.455 | 73.649 | 83.836 | 83.175 |
| NB GLM / logistic | 8 | 1924 | 34.235 | 106.572 | 0.975 | 74.896 | 40.046 | 82.848 | 52.986 | 74.064 | 85.447 | 100.675 |
| Persistence | 8 | 1924 | 35.116 | 102.785 | 1.000 | 73.337 | 48.932 | 83.004 | 66.479 | 74.792 | 85.291 | 196.766 |
| Seasonal climatology | 8 | 1924 | 37.711 | 114.781 | 1.074 | 73.077 | 41.576 | 81.341 | 58.076 | 73.753 | 86.383 | 110.366 |
| LightGBM | 9 | 1898 | 33.575 | 105.966 | 0.933 | 75.342 | 40.106 | 82.139 | 54.123 | 73.762 | 85.458 | 92.172 |
| NB GLM / logistic | 9 | 1898 | 35.506 | 109.876 | 0.987 | 74.816 | 40.918 | 81.981 | 53.930 | 74.974 | 85.195 | 100.559 |
| Persistence | 9 | 1898 | 35.981 | 105.159 | 1.000 | 72.761 | 48.428 | 82.086 | 68.136 | 74.605 | 83.614 | 136.374 |
| Seasonal climatology | 9 | 1898 | 38.054 | 115.543 | 1.058 | 72.866 | 41.530 | 80.927 | 57.836 | 74.816 | 86.143 | 105.827 |
| LightGBM | 10 | 1872 | 34.306 | 107.335 | 0.905 | 74.840 | 40.465 | 81.571 | 54.205 | 76.068 | 86.378 | 95.672 |
| NB GLM / logistic | 10 | 1872 | 36.399 | 112.234 | 0.960 | 75.427 | 41.941 | 81.944 | 54.776 | 75.908 | 85.791 | 96.893 |
| Persistence | 10 | 1872 | 37.920 | 109.282 | 1.000 | 72.810 | 50.634 | 82.372 | 71.149 | 75.160 | 82.746 | 122.583 |
| Seasonal climatology | 10 | 1872 | 38.350 | 116.299 | 1.011 | 72.810 | 41.540 | 80.716 | 57.742 | 76.335 | 86.218 | 106.460 |

### Elevated, every horizon (test)

| model | h | n_class | base rate % | Brier | BSS vs persistence | BSS vs climatology | recall | precision | AUROC | PR-AUC | mean p range |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 2080 | 31.394 | 0.145 | 0.162 | 0.361 | 0.331 | 0.960 | 0.869 | 0.795 | 0.017 |
| NB GLM / logistic | 1 | 2080 | 31.394 | 0.125 | 0.279 | 0.450 | 0.492 | 0.887 | 0.887 | 0.824 | 0.020 |
| Persistence | 1 | 2080 | 31.394 | 0.173 | 0.000 | 0.237 | 0.714 | 0.729 | 0.796 | 0.610 |  |
| Seasonal climatology | 1 | 2080 | 31.394 | 0.227 | -0.311 | 0.000 | 0.240 | 0.473 | 0.627 | 0.410 |  |
| LightGBM | 2 | 2054 | 31.402 | 0.152 | 0.112 | 0.319 | 0.298 | 0.975 | 0.860 | 0.785 | 0.016 |
| NB GLM / logistic | 2 | 2054 | 31.402 | 0.126 | 0.262 | 0.435 | 0.476 | 0.925 | 0.887 | 0.825 | 0.020 |
| Persistence | 2 | 2054 | 31.402 | 0.171 | 0.000 | 0.234 | 0.719 | 0.732 | 0.799 | 0.615 |  |
| Seasonal climatology | 2 | 2054 | 31.402 | 0.223 | -0.305 | 0.000 | 0.239 | 0.487 | 0.638 | 0.423 |  |
| LightGBM | 3 | 2028 | 31.509 | 0.160 | 0.195 | 0.273 | 0.274 | 0.972 | 0.850 | 0.770 | 0.014 |
| NB GLM / logistic | 3 | 2028 | 31.509 | 0.134 | 0.328 | 0.393 | 0.476 | 0.876 | 0.880 | 0.811 | 0.019 |
| Persistence | 3 | 2028 | 31.509 | 0.199 | 0.000 | 0.097 | 0.651 | 0.698 | 0.761 | 0.564 |  |
| Seasonal climatology | 3 | 2028 | 31.509 | 0.220 | -0.107 | 0.000 | 0.230 | 0.492 | 0.649 | 0.434 |  |
| LightGBM | 4 | 2002 | 31.369 | 0.165 | 0.176 | 0.243 | 0.239 | 0.968 | 0.846 | 0.764 | 0.015 |
| NB GLM / logistic | 4 | 2002 | 31.369 | 0.136 | 0.319 | 0.374 | 0.446 | 0.900 | 0.876 | 0.806 | 0.020 |
| Persistence | 4 | 2002 | 31.369 | 0.200 | 0.000 | 0.081 | 0.654 | 0.691 | 0.760 | 0.560 |  |
| Seasonal climatology | 4 | 2002 | 31.369 | 0.218 | -0.088 | 0.000 | 0.228 | 0.495 | 0.652 | 0.439 |  |
| LightGBM | 5 | 1976 | 31.781 | 0.175 | 0.221 | 0.195 | 0.196 | 0.984 | 0.835 | 0.748 | 0.015 |
| NB GLM / logistic | 5 | 1976 | 31.781 | 0.144 | 0.357 | 0.336 | 0.420 | 0.901 | 0.868 | 0.793 | 0.018 |
| Persistence | 5 | 1976 | 31.781 | 0.224 | 0.000 | -0.033 | 0.596 | 0.664 | 0.728 | 0.524 |  |
| Seasonal climatology | 5 | 1976 | 31.781 | 0.217 | 0.032 | 0.000 | 0.225 | 0.507 | 0.660 | 0.454 |  |
| LightGBM | 6 | 1950 | 32.154 | 0.182 | 0.217 | 0.157 | 0.156 | 0.980 | 0.827 | 0.742 | 0.015 |
| NB GLM / logistic | 6 | 1950 | 32.154 | 0.153 | 0.343 | 0.292 | 0.400 | 0.878 | 0.861 | 0.775 | 0.017 |
| Persistence | 6 | 1950 | 32.154 | 0.232 | 0.000 | -0.077 | 0.573 | 0.660 | 0.716 | 0.515 |  |
| Seasonal climatology | 6 | 1950 | 32.154 | 0.216 | 0.072 | 0.000 | 0.231 | 0.525 | 0.669 | 0.468 |  |
| LightGBM | 7 | 1950 | 31.897 | 0.188 | 0.289 | 0.122 | 0.137 | 0.988 | 0.814 | 0.724 | 0.014 |
| NB GLM / logistic | 7 | 1950 | 31.897 | 0.163 | 0.384 | 0.239 | 0.330 | 0.869 | 0.849 | 0.745 | 0.017 |
| Persistence | 7 | 1950 | 31.897 | 0.265 | 0.000 | -0.235 | 0.505 | 0.602 | 0.674 | 0.462 |  |
| Seasonal climatology | 7 | 1950 | 31.897 | 0.214 | 0.190 | 0.000 | 0.228 | 0.522 | 0.671 | 0.467 |  |
| LightGBM | 8 | 1924 | 32.069 | 0.193 | 0.272 | 0.094 | 0.131 | 0.988 | 0.811 | 0.722 | 0.013 |
| NB GLM / logistic | 8 | 1924 | 32.069 | 0.170 | 0.361 | 0.204 | 0.311 | 0.831 | 0.832 | 0.728 | 0.016 |
| Persistence | 8 | 1924 | 32.069 | 0.266 | 0.000 | -0.245 | 0.501 | 0.604 | 0.673 | 0.462 |  |
| Seasonal climatology | 8 | 1924 | 32.069 | 0.213 | 0.197 | 0.000 | 0.235 | 0.533 | 0.677 | 0.471 |  |
| LightGBM | 9 | 1898 | 32.350 | 0.200 | 0.298 | 0.061 | 0.140 | 0.956 | 0.801 | 0.706 | 0.014 |
| NB GLM / logistic | 9 | 1898 | 32.350 | 0.179 | 0.372 | 0.161 | 0.296 | 0.835 | 0.814 | 0.698 | 0.016 |
| Persistence | 9 | 1898 | 32.350 | 0.285 | 0.000 | -0.337 | 0.445 | 0.578 | 0.645 | 0.437 |  |
| Seasonal climatology | 9 | 1898 | 32.350 | 0.213 | 0.252 | 0.000 | 0.241 | 0.546 | 0.683 | 0.478 |  |
| LightGBM | 10 | 1872 | 32.692 | 0.206 | 0.302 | 0.026 | 0.100 | 0.968 | 0.796 | 0.702 | 0.014 |
| NB GLM / logistic | 10 | 1872 | 32.692 | 0.182 | 0.383 | 0.139 | 0.279 | 0.842 | 0.809 | 0.711 | 0.019 |
| Persistence | 10 | 1872 | 32.692 | 0.295 | 0.000 | -0.395 | 0.422 | 0.566 | 0.632 | 0.428 |  |
| Seasonal climatology | 10 | 1872 | 32.692 | 0.211 | 0.283 | 0.000 | 0.242 | 0.556 | 0.692 | 0.491 |  |

![reliability](figures/outlook_dengue_reliability.png)

`mean p range` is the width of the Venn-Abers calibration range. It is narrow because the calibration pool is large and it describes calibration uncertainty only; outbreak uncertainty is carried by the count interval. The dashboard shows the range only in a tooltip, labelled 'calibration range'.

### Count intervals: static split-conformal vs adaptive conformal (ACI)

ACI (Gibbs & Candes 2021) keeps the same rolling pool of past-only scores but adapts the working miscoverage online: when a forecast's target is reported, the miscoverage moves by gamma = 0.005 x (nominal - miss), per forecast, with gamma fixed a priori. The dashboard uses ACI only if it brings 2026 coverage closer to nominal without moving 2024-25 coverage more than 2.5 points from nominal.

| scope (selected count models, all horizons) | n | 80% static | 80% ACI | 90% static | 90% ACI | 90% width static | 90% width ACI |
|---|---|---|---|---|---|---|---|
| 2024-25 targets | 25090 | 87.2 | 81.1 | 94.7 | 90.9 | 67.0 | 161.6 |
| 2026 targets | 7800 | 62.7 | 72.7 | 72.6 | 83.5 | 64.6 | 196.9 |
| test (2025-26 origins) | 19734 | 74.8 | 76.5 | 84.1 | 86.8 | 52.7 | 103.4 |

**ACI used: 2026 coverage 80/90 static 62.7/72.6% -> ACI 72.7/83.5% (closer to nominal); 2024-25 ACI 81.1/90.9% (within +-2.5 pp of nominal).**

### 2026 separately (targets in 2026)

| model | h | n | MASE vs persistence | BSS vs persistence | BSS vs climatology | AUROC | coverage90 % | coverage90 ACI % |
|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 780 | 1.931 | 0.117 | 0.422 | 0.816 | 73.974 | 87.821 |
| NB GLM / logistic | 1 | 780 | 1.383 | 0.287 | 0.533 | 0.850 | 76.026 | 87.564 |
| Persistence | 1 | 780 | 1.000 | 0.000 | 0.345 | 0.746 | 81.026 | 88.333 |
| Seasonal climatology | 1 | 780 | 2.782 | -0.527 | 0.000 | 0.533 | 67.308 | 88.974 |
| LightGBM | 2 | 780 | 1.604 | 0.003 | 0.382 | 0.807 | 72.821 | 88.333 |
| NB GLM / logistic | 2 | 780 | 1.251 | 0.235 | 0.526 | 0.853 | 74.103 | 87.821 |
| Persistence | 2 | 780 | 1.000 | 0.000 | 0.380 | 0.760 | 80.641 | 88.846 |
| Seasonal climatology | 2 | 780 | 2.234 | -0.612 | 0.000 | 0.539 | 66.667 | 89.615 |
| LightGBM | 9 | 780 | 1.031 | 0.156 | 0.038 | 0.716 | 64.744 | 81.795 |
| NB GLM / logistic | 9 | 780 | 1.073 | 0.274 | 0.173 | 0.711 | 65.897 | 80.897 |
| Persistence | 9 | 780 | 1.000 | 0.000 | -0.140 | 0.628 | 74.359 | 77.564 |
| Seasonal climatology | 9 | 780 | 1.178 | 0.122 | 0.000 | 0.572 | 62.564 | 82.949 |
| LightGBM | 10 | 780 | 1.003 | 0.154 | -0.007 | 0.720 | 64.615 | 84.231 |
| NB GLM / logistic | 10 | 780 | 1.048 | 0.281 | 0.144 | 0.718 | 66.667 | 80.897 |
| Persistence | 10 | 780 | 1.000 | 0.000 | -0.190 | 0.620 | 73.846 | 76.667 |
| Seasonal climatology | 10 | 780 | 1.132 | 0.160 | 0.000 | 0.584 | 62.179 | 82.308 |

### What drives LightGBM (live models, on their training rows)

Mean |SHAP| is LightGBM's own TreeSHAP (`pred_contrib`), on the log scale of the model (log count / log-odds). Gain = share of split gain.

Elevated (binary), top 12:

| feature | gain % | mean |SHAP| |
|---|---|---|
| thr | 18.032 | 0.827 |
| cos2 | 7.737 | 0.391 |
| sin1 | 9.322 | 0.368 |
| y0 | 12.726 | 0.329 |
| area | 13.542 | 0.270 |
| neigh | 5.196 | 0.175 |
| m4 | 4.266 | 0.165 |
| temp | 3.259 | 0.131 |
| m8 | 1.465 | 0.108 |
| rain_l5 | 2.548 | 0.101 |
| ly | 3.809 | 0.083 |
| y1 | 1.639 | 0.069 |

Count (Poisson), top 8:

| feature | gain % | mean |SHAP| |
|---|---|---|
| m4 | 19.224 | 0.298 |
| y0 | 47.842 | 0.236 |
| area | 9.509 | 0.235 |
| thr | 3.363 | 0.159 |
| cos2 | 4.888 | 0.126 |
| m8 | 2.530 | 0.119 |
| ly | 2.028 | 0.063 |
| temp | 1.314 | 0.044 |

### Rainfall lag

| rain lag (weeks before target) | model: mean SHAP if heavy rain (log-odds) | model: mean SHAP otherwise | data: share elevated after heavy rain % | data: share elevated otherwise % | data: ratio | heavy-rain district-weeks |
|---|---|---|---|---|---|---|
| 2 | -0.08 | 0.00 | 26.94 | 27.72 | 0.97 | 527 |
| 3 | 0.09 | -0.01 | 29.40 | 27.44 | 1.07 | 534 |
| 4 | 0.06 | -0.00 | 31.90 | 27.19 | 1.17 | 511 |
| 5 | 0.07 | -0.01 | 33.01 | 27.05 | 1.22 | 521 |
| 6 | 0.06 | -0.01 | 36.15 | 26.74 | 1.35 | 509 |
| 7 | 0.05 | -0.00 | 36.60 | 26.64 | 1.37 | 530 |
| 8 | 0.11 | -0.01 | 39.41 | 26.30 | 1.50 | 543 |

![rain lag](figures/outlook_dengue_rain_lag.png)

**Finding: dengue risk rises about 8 weeks after a very wet week in the model (largest push on P(elevated)); in the raw data the excess is largest 8 weeks after.** Association, not proof of cause: wet weeks also cluster in the monsoon seasons the Fourier terms describe.

### Live outlook (origin 2026-W33, as of 2026-08-16): highest P(elevated) for this week and next week

| area | target_week | h | model | p_elevated | p_lo | p_hi | pred_count | lo90 | hi90 | elevated_threshold |
|---|---|---|---|---|---|---|---|---|---|---|
| Puttalam | 2026-W43 | 10 | climatology | 0.50 |  |  | 29.10 | 0.00 | 114.62 | 26.80 |
| Monaragala | 2026-W42 | 9 | climatology | 0.44 |  |  | 21.22 | 0.00 | 94.71 | 27.00 |
| Puttalam | 2026-W42 | 9 | climatology | 0.44 |  |  | 22.00 | 0.00 | 96.76 | 26.80 |
| Monaragala | 2026-W43 | 10 | climatology | 0.40 |  |  | 23.50 | 0.00 | 100.66 | 27.00 |
| Matale | 2026-W42 | 9 | climatology | 0.33 |  |  | 25.89 | 0.00 | 106.72 | 38.00 |
| Kalmunai | 2026-W42 | 9 | climatology | 0.33 |  |  | 14.22 | 0.00 | 75.04 | 26.40 |
| Jaffna | 2026-W43 | 10 | climatology | 0.30 |  |  | 33.90 | 0.00 | 125.99 | 46.40 |
| Kalmunai | 2026-W43 | 10 | climatology | 0.30 |  |  | 17.50 | 0.00 | 84.55 | 26.40 |
| Matale | 2026-W43 | 10 | climatology | 0.30 |  |  | 30.00 | 0.00 | 116.79 | 38.00 |
| Badulla | 2026-W42 | 9 | climatology | 0.22 |  |  | 11.89 | 0.00 | 67.85 | 25.00 |

## Dengue: 2026 forecasts vs NDCU district flags

Forecast elevated (dashboard class model at that horizon, P >= 0.5) vs NDCU: a district is NDCU-positive when >= 1 (or >= 3) of its MOH areas is on that week's high-risk list. The row 'observed (truth)' compares the observed elevated flag itself, so it shows how far the two definitions can agree at best: NDCU flags absolute MOH burden, 'elevated' is relative to the district's own past.

| h | model | NDCU-positive | district-weeks | both | agreement % | kappa | share of NDCU flags forecast % | share of forecasts flagged % | NDCU onsets | onsets forecast within +-4 wk |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | persistence | >= 1 MOH | 780 | 295 | 68.6 | 0.38 | 80.6 | 62.9 | 66 | 58 |
| 1 | observed (truth) | >= 1 MOH | 780 | 303 | 70.1 | 0.41 | 82.8 | 64.1 | 66 | 58 |
| 1 | persistence | >= 3 MOH | 780 | 182 | 61.0 | 0.29 | 91.5 | 38.8 | 35 | 34 |
| 1 | observed (truth) | >= 3 MOH | 780 | 184 | 61.0 | 0.29 | 92.5 | 38.9 | 35 | 34 |
| 2 | persistence | >= 1 MOH | 780 | 294 | 67.3 | 0.36 | 80.3 | 61.6 | 66 | 56 |
| 2 | observed (truth) | >= 1 MOH | 780 | 304 | 70.4 | 0.42 | 83.1 | 64.3 | 66 | 58 |
| 2 | persistence | >= 3 MOH | 780 | 181 | 59.7 | 0.27 | 91.0 | 37.9 | 35 | 34 |
| 2 | observed (truth) | >= 3 MOH | 780 | 185 | 61.3 | 0.30 | 93.0 | 39.1 | 35 | 34 |
| 9 | climatology | >= 1 MOH | 780 | 109 | 57.1 | 0.11 | 29.8 | 58.3 | 66 | 39 |
| 9 | observed (truth) | >= 1 MOH | 780 | 309 | 71.7 | 0.44 | 84.4 | 65.3 | 66 | 57 |
| 9 | climatology | >= 3 MOH | 780 | 48 | 62.8 | 0.00 | 24.1 | 25.7 | 35 | 19 |
| 9 | observed (truth) | >= 3 MOH | 780 | 190 | 62.6 | 0.32 | 95.5 | 40.2 | 35 | 34 |
| 10 | climatology | >= 1 MOH | 780 | 110 | 57.6 | 0.12 | 30.1 | 59.5 | 66 | 38 |
| 10 | observed (truth) | >= 1 MOH | 780 | 310 | 71.7 | 0.44 | 84.7 | 65.3 | 66 | 57 |
| 10 | climatology | >= 3 MOH | 780 | 47 | 62.8 | -0.00 | 23.6 | 25.4 | 35 | 19 |
| 10 | observed (truth) | >= 3 MOH | 780 | 191 | 62.6 | 0.32 | 96.0 | 40.2 | 35 | 34 |

## Limitations

- 2.6 seasons of training history at the first test origin (2022-2023), 4.6 at the last; the seasonal terms and the climatology baseline rest on few years.
- Weather is one Open-Meteo point per district (centroid), not an areal average; Kalmunai uses its town point.
- The first-printed weekly counts are under-notified and late reports raise them later; the target is what a Regional Epidemiologist would have seen, not true incidence.
- Venn-Abers and conformal pools pool all districts: coverage holds on average, not for every district.
- Rows where any model has no forecast are left out of the comparison; all models are scored on the same district-weeks.
