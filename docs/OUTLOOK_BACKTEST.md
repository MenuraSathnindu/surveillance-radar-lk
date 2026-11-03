# Outlook backtest

Generated 2026-11-03 by `python -m radar_lk.outlook.backtest`. Primary data: Epidemiology Unit, Ministry of Health, Sri Lanka (WER Table 1, `extraction_valid` RDHS rows, weekly counts as first printed); rainfall, temperature and humidity: Open-Meteo (CC BY 4.0); external check: National Dengue Control Unit (NDCU) Weekly Dengue Update. This is the proposal's fallback after the NDCU MOH outlook was judged NO-GO: a district-level outlook, leptospirosis primary, dengue secondary, from one disease-agnostic engine. Outputs are population-level signals for planning, not predictions about any person.

## Design: filling the publication gap

- The WER reports a week about **L = 8 weeks** after it ends (`publication_lag_weeks`, measured from the PDFs). Rainfall is observed in near real time. From the latest reported week t (the origin) the outlook forecasts t+1 .. t+10: at the time of use (about t+8) h = 9 is **this week** and h = 10 **next week**; h = 1, 2 are the proposal's horizons (weeks already over but not yet reported).
- Targets: (i) the weekly count; (ii) **elevated** = count >= that district's 80th percentile of its counts in the 104 weeks before t (past-only), floored at 1 case.
- Features: counts y_t..y_t-3, 4- and 8-week means, same week last year, mean count of neighbouring districts at t (HDX polygons; Kalmunai adjacent to Ampara and Batticaloa by rule, `config/district_adjacency.csv`), reporting completeness at t, district, h, Fourier terms of the target's week of year, and weather relative to the TARGET week: rain at lags 2..8, the 4-week rain sum ending at lag 2, mean temperature and humidity at lags 2-4. Lag >= 2 is enforced in code (`features.weather_at`) and tested; for targets up to now + 2 all of it is observed at the time of use.
- Models (fixed settings, nothing tuned on test data): persistence; seasonal climatology (district mean / elevated frequency for the target's week of year +-1 in earlier years); NB GLM (counts) / L2 logistic regression (class); LightGBM (Poisson / binary).
- Rolling origin, expanding window: test origins 2024-W01 to the latest week, refit every 4 weeks on rows whose target week is <= the refit origin. 2023 origins are forecast too but only to fill the calibration pools.
- Uncertainty: counts, rolling split-conformal on past-only residuals normalised by sqrt(pred + 1), pool = the last 52 origins with observed targets, same model and horizon (80% and 90%). Probabilities (GLM and LightGBM): inductive **Venn-Abers** (`venn-abers` package) on the same pool; `p_elevated` is the calibrated probability and [`p_lo`, `p_hi`] its Venn-Abers range. Baselines keep their own probability for evaluation; the dashboard shows them calibrated (see 'Baseline probabilities as displayed').
- Skill: MASE = MAE / persistence MAE on the same rows; BSS = 1 - Brier / reference Brier; recall and precision at p >= 0.5. Every model is scored on the same district-weeks.

## Leptospirosis

Backtest origins 2024-W01 to 2026-W35 (139 origins x 26 districts x up to 10 horizons). **Models are selected on 2024 origins only; every number below is on the untouched 2025-26 origins** unless the heading says otherwise.

### Headline (test origins 2025-26): Brier skill vs persistence (BSS), MASE vs persistence, 90% interval coverage (static split-conformal)

| model | h=1 BSS | h=1 MASE | h=1 cov90 % | h=2 BSS | h=2 MASE | h=2 cov90 % | h=9 (this week) BSS | h=9 (this week) MASE | h=9 (this week) cov90 % | h=10 (next week) BSS | h=10 (next week) MASE | h=10 (next week) cov90 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Persistence | 0.00 | 1.00 | 91.30 | 0.00 | 1.00 | 91.43 | 0.00 | 1.00 | 92.91 | 0.00 | 1.00 | 93.22 |
| Seasonal climatology | 0.33 | 0.91 | 94.32 | 0.36 | 0.87 | 94.53 | 0.52 | 0.68 | 95.45 | 0.51 | 0.66 | 95.60 |
| NB GLM / logistic | 0.39 | 0.90 | 92.40 | 0.41 | 0.89 | 92.96 | 0.52 | 0.78 | 94.36 | 0.51 | 0.76 | 94.79 |
| LightGBM | 0.37 | 0.91 | 93.32 | 0.39 | 0.89 | 93.47 | 0.51 | 0.75 | 94.16 | 0.50 | 0.73 | 94.38 |

![skill](figures/outlook_leptospirosis_skill.png)

### Model selection (2024 origins) -> what the dashboard shows

Candidates: persistence, seasonal climatology, NB GLM / logistic, LightGBM. Counts are selected by MASE, P(elevated) by Brier, on 2024 origins only; any model within 0.01 of the best is a tie and the simplest of the tied models is kept (persistence < climatology < GLM < LightGBM). This replaces the earlier rule (LightGBM unless persistence beats it), which looked at all years and ignored the GLM.

| h | selected count model | count selection reason | selected probability model | probability selection reason |
|---|---|---|---|---|
| 1 | NB GLM / logistic | MASE best on 2024 origins (0.913) | NB GLM / logistic | Brier best on 2024 origins (0.212) |
| 2 | NB GLM / logistic | MASE best on 2024 origins (0.896) | NB GLM / logistic | Brier best on 2024 origins (0.218) |
| 3 | NB GLM / logistic | MASE best on 2024 origins (0.851) | NB GLM / logistic | Brier best on 2024 origins (0.227) |
| 4 | NB GLM / logistic | MASE best on 2024 origins (0.819) | NB GLM / logistic | Brier best on 2024 origins (0.232) |
| 5 | NB GLM / logistic | MASE best on 2024 origins (0.786) | NB GLM / logistic | Brier best on 2024 origins (0.235) |
| 6 | NB GLM / logistic | MASE best on 2024 origins (0.758) | NB GLM / logistic | Brier best on 2024 origins (0.239) |
| 7 | NB GLM / logistic | MASE within 0.01 of the best on 2024 origins (lightgbm 0.751, glm 0.757); the simpler model is kept | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.241, glm 0.242); the simpler model is kept |
| 8 | NB GLM / logistic | MASE within 0.01 of the best on 2024 origins (lightgbm 0.756, glm 0.766); the simpler model is kept | NB GLM / logistic | Brier best on 2024 origins (0.245) |
| 9 | LightGBM | MASE best on 2024 origins (0.742) | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.246, glm 0.246); the simpler model is kept |
| 10 | LightGBM | MASE best on 2024 origins (0.715) | NB GLM / logistic | Brier within 0.01 of the best on 2024 origins (lightgbm 0.248, glm 0.249); the simpler model is kept |

How the selected models do on the untouched test (2025-26 origins):

| h | selected count model | its MASE (test) | LightGBM MASE (test) | selected probability model | its BSS vs persistence (test) | its BSS vs climatology (test) | LightGBM BSS vs persistence (test) |
|---|---|---|---|---|---|---|---|
| 1 | NB GLM / logistic | 0.905 | 0.911 | NB GLM / logistic | 0.391 | 0.094 | 0.367 |
| 2 | NB GLM / logistic | 0.890 | 0.888 | NB GLM / logistic | 0.410 | 0.076 | 0.392 |
| 3 | NB GLM / logistic | 0.861 | 0.851 | NB GLM / logistic | 0.401 | 0.064 | 0.383 |
| 4 | NB GLM / logistic | 0.833 | 0.819 | NB GLM / logistic | 0.448 | 0.051 | 0.429 |
| 5 | NB GLM / logistic | 0.820 | 0.799 | NB GLM / logistic | 0.461 | 0.035 | 0.445 |
| 6 | NB GLM / logistic | 0.809 | 0.792 | NB GLM / logistic | 0.461 | 0.036 | 0.446 |
| 7 | NB GLM / logistic | 0.779 | 0.755 | NB GLM / logistic | 0.482 | 0.017 | 0.474 |
| 8 | NB GLM / logistic | 0.775 | 0.751 | NB GLM / logistic | 0.499 | 0.004 | 0.494 |
| 9 | LightGBM | 0.747 | 0.747 | NB GLM / logistic | 0.519 | -0.005 | 0.514 |
| 10 | LightGBM | 0.732 | 0.732 | NB GLM / logistic | 0.507 | -0.009 | 0.504 |

The selected models beat persistence on both targets at every horizon on the test.

### Counts, every horizon (test)

| model | h | n | MAE | RMSE | MASE vs persistence | coverage80 % | width80 | coverage90 % | width90 | coverage80 ACI % | coverage90 ACI % | width90 ACI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 2184 | 3.776 | 5.634 | 0.911 | 82.005 | 10.614 | 93.315 | 14.765 | 81.136 | 90.705 | 13.896 |
| NB GLM / logistic | 1 | 2184 | 3.752 | 5.874 | 0.905 | 82.234 | 10.496 | 92.399 | 14.158 | 81.319 | 90.980 | 13.716 |
| Persistence | 1 | 2184 | 4.147 | 6.527 | 1.000 | 81.914 | 11.406 | 91.300 | 15.721 | 81.548 | 90.934 | 15.713 |
| Seasonal climatology | 1 | 2184 | 3.763 | 5.857 | 0.907 | 85.714 | 11.659 | 94.322 | 16.517 | 81.273 | 90.797 | 14.465 |
| LightGBM | 2 | 2158 | 3.837 | 5.741 | 0.888 | 82.669 | 10.853 | 93.466 | 14.988 | 81.047 | 90.500 | 14.116 |
| NB GLM / logistic | 2 | 2158 | 3.845 | 5.992 | 0.890 | 82.576 | 10.823 | 92.956 | 14.495 | 81.372 | 90.918 | 14.303 |
| Persistence | 2 | 2158 | 4.322 | 6.895 | 1.000 | 82.113 | 11.714 | 91.427 | 15.929 | 81.742 | 90.871 | 18.156 |
| Seasonal climatology | 2 | 2158 | 3.745 | 5.832 | 0.867 | 85.728 | 11.668 | 94.532 | 16.550 | 81.279 | 90.778 | 14.259 |
| LightGBM | 3 | 2132 | 3.894 | 5.807 | 0.851 | 83.068 | 11.030 | 93.621 | 15.276 | 80.863 | 90.478 | 14.525 |
| NB GLM / logistic | 3 | 2132 | 3.940 | 5.986 | 0.861 | 83.161 | 11.153 | 93.386 | 14.932 | 81.473 | 90.807 | 14.293 |
| Persistence | 3 | 2132 | 4.575 | 7.235 | 1.000 | 81.942 | 12.366 | 91.651 | 16.847 | 81.707 | 91.182 | 21.640 |
| Seasonal climatology | 3 | 2132 | 3.741 | 5.834 | 0.818 | 85.929 | 11.691 | 94.559 | 16.605 | 81.332 | 90.854 | 14.416 |
| LightGBM | 4 | 2106 | 3.938 | 5.902 | 0.819 | 82.716 | 11.209 | 93.400 | 15.463 | 80.769 | 90.646 | 14.932 |
| NB GLM / logistic | 4 | 2106 | 4.004 | 5.984 | 0.833 | 83.428 | 11.425 | 93.257 | 15.264 | 81.387 | 90.883 | 14.763 |
| Persistence | 4 | 2106 | 4.808 | 7.495 | 1.000 | 82.384 | 13.088 | 91.595 | 17.546 | 81.909 | 91.168 | 25.189 |
| Seasonal climatology | 4 | 2106 | 3.714 | 5.782 | 0.773 | 86.230 | 11.716 | 94.872 | 16.664 | 81.434 | 90.931 | 14.435 |
| LightGBM | 5 | 2080 | 3.967 | 5.917 | 0.799 | 83.365 | 11.506 | 93.462 | 15.597 | 81.010 | 91.106 | 22.549 |
| NB GLM / logistic | 5 | 2080 | 4.070 | 6.054 | 0.820 | 84.135 | 11.754 | 93.846 | 15.719 | 81.394 | 91.010 | 15.801 |
| Persistence | 5 | 2080 | 4.963 | 7.663 | 1.000 | 83.221 | 13.907 | 91.971 | 18.587 | 82.548 | 90.817 | 22.097 |
| Seasonal climatology | 5 | 2080 | 3.706 | 5.774 | 0.747 | 86.587 | 11.747 | 95.096 | 16.728 | 81.538 | 90.962 | 14.725 |
| LightGBM | 6 | 2054 | 3.994 | 5.982 | 0.792 | 83.788 | 11.557 | 93.525 | 15.848 | 81.256 | 91.237 | 30.554 |
| NB GLM / logistic | 6 | 2054 | 4.081 | 6.024 | 0.809 | 83.496 | 11.767 | 94.255 | 15.869 | 81.159 | 91.188 | 26.814 |
| Persistence | 6 | 2054 | 5.042 | 7.818 | 1.000 | 83.301 | 13.998 | 91.772 | 18.876 | 81.646 | 91.772 | 44.746 |
| Seasonal climatology | 6 | 2054 | 3.703 | 5.785 | 0.734 | 86.952 | 11.789 | 95.034 | 16.811 | 81.500 | 90.993 | 17.646 |
| LightGBM | 7 | 2054 | 4.028 | 6.003 | 0.755 | 83.544 | 11.724 | 93.768 | 16.028 | 81.548 | 91.626 | 46.420 |
| NB GLM / logistic | 7 | 2054 | 4.153 | 6.069 | 0.779 | 84.567 | 12.162 | 93.866 | 16.198 | 82.181 | 91.821 | 52.885 |
| Persistence | 7 | 2054 | 5.333 | 8.237 | 1.000 | 83.057 | 14.781 | 92.162 | 19.770 | 82.327 | 92.210 | 50.633 |
| Seasonal climatology | 7 | 2054 | 3.703 | 5.785 | 0.695 | 87.147 | 11.862 | 95.083 | 16.929 | 81.402 | 91.529 | 29.710 |
| LightGBM | 8 | 2028 | 4.055 | 6.061 | 0.751 | 83.580 | 11.764 | 93.688 | 16.209 | 81.706 | 91.765 | 57.375 |
| NB GLM / logistic | 8 | 2028 | 4.187 | 6.092 | 0.775 | 84.714 | 12.317 | 93.787 | 16.329 | 81.953 | 92.012 | 68.110 |
| Persistence | 8 | 2028 | 5.403 | 8.271 | 1.000 | 82.939 | 14.931 | 92.653 | 19.798 | 82.495 | 93.047 | 98.414 |
| Seasonal climatology | 8 | 2028 | 3.666 | 5.729 | 0.679 | 87.426 | 11.927 | 95.316 | 17.033 | 81.016 | 91.815 | 39.211 |
| LightGBM | 9 | 2002 | 4.048 | 6.064 | 0.747 | 83.267 | 11.828 | 94.156 | 16.406 | 81.219 | 92.258 | 69.561 |
| NB GLM / logistic | 9 | 2002 | 4.213 | 6.094 | 0.778 | 84.715 | 12.416 | 94.356 | 16.694 | 81.968 | 92.308 | 76.195 |
| Persistence | 9 | 2002 | 5.415 | 8.213 | 1.000 | 82.767 | 14.926 | 92.907 | 20.121 | 83.117 | 93.556 | 122.634 |
| Seasonal climatology | 9 | 2002 | 3.676 | 5.746 | 0.679 | 87.512 | 11.995 | 95.455 | 17.145 | 81.369 | 92.008 | 43.633 |
| LightGBM | 10 | 1976 | 4.051 | 6.060 | 0.732 | 83.401 | 11.919 | 94.383 | 16.544 | 81.326 | 92.156 | 72.049 |
| NB GLM / logistic | 10 | 1976 | 4.211 | 6.080 | 0.761 | 84.818 | 12.592 | 94.787 | 17.059 | 81.832 | 92.915 | 92.696 |
| Persistence | 10 | 1976 | 5.536 | 8.538 | 1.000 | 83.654 | 15.449 | 93.219 | 21.018 | 84.615 | 91.802 | 77.671 |
| Seasonal climatology | 10 | 1976 | 3.663 | 5.731 | 0.662 | 87.804 | 12.054 | 95.597 | 17.246 | 82.085 | 91.650 | 40.409 |

### Elevated, every horizon (test)

| model | h | n_class | base rate % | Brier | BSS vs persistence | BSS vs climatology | recall | precision | AUROC | PR-AUC | mean p range |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 2184 | 19.368 | 0.139 | 0.367 | 0.059 | 0.158 | 0.479 | 0.750 | 0.393 | 0.016 |
| NB GLM / logistic | 1 | 2184 | 19.368 | 0.134 | 0.391 | 0.094 | 0.243 | 0.526 | 0.767 | 0.459 | 0.017 |
| Persistence | 1 | 2184 | 19.368 | 0.220 | 0.000 | -0.487 | 0.452 | 0.435 | 0.655 | 0.303 |  |
| Seasonal climatology | 1 | 2184 | 19.368 | 0.148 | 0.328 | 0.000 | 0.132 | 0.519 | 0.686 | 0.355 |  |
| LightGBM | 2 | 2158 | 19.045 | 0.139 | 0.392 | 0.047 | 0.088 | 0.529 | 0.742 | 0.376 | 0.014 |
| NB GLM / logistic | 2 | 2158 | 19.045 | 0.135 | 0.410 | 0.076 | 0.248 | 0.520 | 0.755 | 0.432 | 0.016 |
| Persistence | 2 | 2158 | 19.045 | 0.229 | 0.000 | -0.567 | 0.423 | 0.403 | 0.638 | 0.280 |  |
| Seasonal climatology | 2 | 2158 | 19.045 | 0.146 | 0.362 | 0.000 | 0.141 | 0.537 | 0.681 | 0.350 |  |
| LightGBM | 3 | 2132 | 18.996 | 0.141 | 0.383 | 0.036 | 0.091 | 0.544 | 0.738 | 0.378 | 0.015 |
| NB GLM / logistic | 3 | 2132 | 18.996 | 0.137 | 0.401 | 0.064 | 0.200 | 0.544 | 0.746 | 0.426 | 0.016 |
| Persistence | 3 | 2132 | 18.996 | 0.228 | 0.000 | -0.562 | 0.437 | 0.407 | 0.644 | 0.285 |  |
| Seasonal climatology | 3 | 2132 | 18.996 | 0.146 | 0.360 | 0.000 | 0.146 | 0.551 | 0.681 | 0.350 |  |
| LightGBM | 4 | 2106 | 18.756 | 0.141 | 0.429 | 0.018 | 0.111 | 0.564 | 0.735 | 0.377 | 0.015 |
| NB GLM / logistic | 4 | 2106 | 18.756 | 0.136 | 0.448 | 0.051 | 0.149 | 0.567 | 0.748 | 0.419 | 0.016 |
| Persistence | 4 | 2106 | 18.756 | 0.247 | 0.000 | -0.719 | 0.397 | 0.358 | 0.616 | 0.255 |  |
| Seasonal climatology | 4 | 2106 | 18.756 | 0.144 | 0.418 | 0.000 | 0.149 | 0.562 | 0.685 | 0.351 |  |
| LightGBM | 5 | 2080 | 18.606 | 0.142 | 0.445 | 0.006 | 0.093 | 0.610 | 0.727 | 0.363 | 0.014 |
| NB GLM / logistic | 5 | 2080 | 18.606 | 0.138 | 0.461 | 0.035 | 0.160 | 0.585 | 0.740 | 0.409 | 0.015 |
| Persistence | 5 | 2080 | 18.606 | 0.256 | 0.000 | -0.792 | 0.375 | 0.333 | 0.602 | 0.241 |  |
| Seasonal climatology | 5 | 2080 | 18.606 | 0.143 | 0.442 | 0.000 | 0.155 | 0.566 | 0.683 | 0.352 |  |
| LightGBM | 6 | 2054 | 18.841 | 0.142 | 0.446 | 0.010 | 0.065 | 0.694 | 0.730 | 0.362 | 0.013 |
| NB GLM / logistic | 6 | 2054 | 18.841 | 0.139 | 0.461 | 0.036 | 0.163 | 0.685 | 0.737 | 0.422 | 0.015 |
| Persistence | 6 | 2054 | 18.841 | 0.257 | 0.000 | -0.788 | 0.377 | 0.337 | 0.603 | 0.245 |  |
| Seasonal climatology | 6 | 2054 | 18.841 | 0.144 | 0.441 | 0.000 | 0.152 | 0.567 | 0.685 | 0.357 |  |
| LightGBM | 7 | 2054 | 19.085 | 0.145 | 0.474 | 0.002 | 0.094 | 0.521 | 0.724 | 0.366 | 0.015 |
| NB GLM / logistic | 7 | 2054 | 19.085 | 0.143 | 0.482 | 0.017 | 0.148 | 0.637 | 0.725 | 0.407 | 0.017 |
| Persistence | 7 | 2054 | 19.085 | 0.277 | 0.000 | -0.898 | 0.344 | 0.303 | 0.579 | 0.229 |  |
| Seasonal climatology | 7 | 2054 | 19.085 | 0.146 | 0.473 | 0.000 | 0.145 | 0.553 | 0.684 | 0.354 |  |
| LightGBM | 8 | 2028 | 18.886 | 0.146 | 0.494 | -0.007 | 0.060 | 0.500 | 0.722 | 0.344 | 0.015 |
| NB GLM / logistic | 8 | 2028 | 18.886 | 0.144 | 0.499 | 0.004 | 0.131 | 0.641 | 0.722 | 0.385 | 0.016 |
| Persistence | 8 | 2028 | 18.886 | 0.287 | 0.000 | -0.989 | 0.321 | 0.276 | 0.562 | 0.217 |  |
| Seasonal climatology | 8 | 2028 | 18.886 | 0.145 | 0.497 | 0.000 | 0.144 | 0.550 | 0.683 | 0.353 |  |
| LightGBM | 9 | 2002 | 18.931 | 0.147 | 0.514 | -0.016 | 0.040 | 0.319 | 0.723 | 0.327 | 0.015 |
| NB GLM / logistic | 9 | 2002 | 18.931 | 0.145 | 0.519 | -0.005 | 0.113 | 0.614 | 0.718 | 0.382 | 0.015 |
| Persistence | 9 | 2002 | 18.931 | 0.302 | 0.000 | -1.090 | 0.288 | 0.245 | 0.541 | 0.205 |  |
| Seasonal climatology | 9 | 2002 | 18.931 | 0.145 | 0.521 | 0.000 | 0.145 | 0.550 | 0.685 | 0.354 |  |
| LightGBM | 10 | 1976 | 18.877 | 0.146 | 0.504 | -0.015 | 0.072 | 0.500 | 0.726 | 0.339 | 0.015 |
| NB GLM / logistic | 10 | 1976 | 18.877 | 0.145 | 0.507 | -0.009 | 0.153 | 0.564 | 0.720 | 0.381 | 0.014 |
| Persistence | 10 | 1976 | 18.877 | 0.294 | 0.000 | -1.047 | 0.311 | 0.264 | 0.554 | 0.212 |  |
| Seasonal climatology | 10 | 1976 | 18.877 | 0.144 | 0.512 | 0.000 | 0.145 | 0.529 | 0.691 | 0.354 |  |

![reliability](figures/outlook_leptospirosis_reliability.png)

`mean p range` is the width of the Venn-Abers calibration range. It is narrow because the calibration pool is large and it describes calibration uncertainty only; outbreak uncertainty is carried by the count interval. The dashboard shows the range only in a tooltip, labelled 'calibration range'.

### Baseline probabilities as displayed (post-hoc display change, disclosed)

Persistence gives a 0/1 probability and climatology a frequency over one to four past years, so where they are the selected model the dashboard would print 0% or 100%. **After model selection and evaluation**, the displayed probability of these two baselines was changed to an empirical frequency estimated past-only (expanding window, per disease and horizon, from earlier forecasts whose target was already reported): persistence shows P(elevated at t+h | elevated status at t), Laplace-smoothed; climatology shows the district's own past frequency at that time of year, smoothed with two pseudo-weeks at the 20% base rate. The selected model at each horizon is unchanged, and every other number in this report (selection, BSS, reliability) still uses the probabilities as evaluated. Brier on the test origins (2025-26), lower is better:

| h | persistence Brier (0/1, as evaluated) | persistence Brier (calibrated display) | climatology Brier (as evaluated) | climatology Brier (calibrated display) |
|---|---|---|---|---|
| 1 | 0.220 | 0.154 | 0.148 | 0.145 |
| 2 | 0.229 | 0.158 | 0.146 | 0.143 |
| 3 | 0.228 | 0.160 | 0.146 | 0.143 |
| 4 | 0.247 | 0.166 | 0.144 | 0.141 |
| 5 | 0.256 | 0.170 | 0.143 | 0.140 |
| 6 | 0.257 | 0.173 | 0.144 | 0.141 |
| 7 | 0.277 | 0.181 | 0.146 | 0.143 |
| 8 | 0.287 | 0.185 | 0.145 | 0.142 |
| 9 | 0.302 | 0.189 | 0.145 | 0.142 |
| 10 | 0.294 | 0.193 | 0.144 | 0.141 |

### Count intervals: static split-conformal vs adaptive conformal (ACI)

ACI (Gibbs & Candes 2021) keeps the same rolling pool of past-only scores but adapts the working miscoverage online: when a forecast's target is reported, the miscoverage moves by gamma = 0.005 x (nominal - miss), per forecast, with gamma fixed a priori. The dashboard uses ACI only if it brings 2026 coverage closer to nominal without moving 2024-25 coverage more than 2.5 points from nominal.

| scope (selected count models, all horizons) | n | 80% static | 80% ACI | 90% static | 90% ACI | 90% width static | 90% width ACI |
|---|---|---|---|---|---|---|---|
| 2024-25 targets | 25090 | 83.6 | 80.8 | 92.7 | 90.6 | 17.8 | 40.3 |
| 2026 targets | 8840 | 82.4 | 82.6 | 93.1 | 92.3 | 13.3 | 13.8 |
| test (2025-26 origins) | 20774 | 83.5 | 81.5 | 93.6 | 91.4 | 15.6 | 35.6 |

**ACI not used: 2026 coverage 80/90 static 82.4/93.1% -> ACI 82.6/92.3% (not closer to nominal); 2024-25 ACI 80.8/90.6% (within +-2.5 pp of nominal).**

### 2026 separately (targets in 2026)

| model | h | n | MASE vs persistence | BSS vs persistence | BSS vs climatology | AUROC | coverage90 % | coverage90 ACI % |
|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 884 | 0.925 | 0.440 | 0.117 | 0.801 | 93.100 | 91.629 |
| NB GLM / logistic | 1 | 884 | 0.883 | 0.433 | 0.106 | 0.791 | 92.760 | 92.195 |
| Persistence | 1 | 884 | 1.000 | 0.000 | -0.577 | 0.642 | 92.195 | 91.290 |
| Seasonal climatology | 1 | 884 | 0.902 | 0.366 | 0.000 | 0.679 | 93.213 | 91.063 |
| LightGBM | 2 | 884 | 0.943 | 0.467 | 0.127 | 0.805 | 93.439 | 91.855 |
| NB GLM / logistic | 2 | 884 | 0.916 | 0.453 | 0.106 | 0.792 | 93.552 | 93.100 |
| Persistence | 2 | 884 | 1.000 | 0.000 | -0.636 | 0.659 | 93.891 | 93.326 |
| Seasonal climatology | 2 | 884 | 0.898 | 0.389 | 0.000 | 0.675 | 93.326 | 91.629 |
| LightGBM | 9 | 884 | 0.682 | 0.617 | 0.068 | 0.787 | 93.552 | 92.195 |
| NB GLM / logistic | 9 | 884 | 0.703 | 0.616 | 0.065 | 0.757 | 92.647 | 90.950 |
| Persistence | 9 | 884 | 1.000 | 0.000 | -1.435 | 0.556 | 93.552 | 96.946 |
| Seasonal climatology | 9 | 884 | 0.606 | 0.589 | 0.000 | 0.683 | 94.683 | 92.534 |
| LightGBM | 10 | 884 | 0.675 | 0.622 | 0.061 | 0.783 | 93.552 | 91.968 |
| NB GLM / logistic | 10 | 884 | 0.696 | 0.626 | 0.071 | 0.772 | 92.647 | 91.516 |
| Persistence | 10 | 884 | 1.000 | 0.000 | -1.483 | 0.542 | 93.778 | 97.511 |
| Seasonal climatology | 10 | 884 | 0.597 | 0.597 | 0.000 | 0.685 | 94.796 | 92.308 |

### What drives LightGBM (live models, on their training rows)

Mean |SHAP| is LightGBM's own TreeSHAP (`pred_contrib`), on the log scale of the model (log count / log-odds). Gain = share of split gain.

Elevated (binary), top 12:

| feature | gain % | mean |SHAP| |
|---|---|---|
| thr | 16.529 | 0.695 |
| area | 17.715 | 0.239 |
| rh | 6.801 | 0.192 |
| cos1 | 10.127 | 0.183 |
| sin2 | 3.758 | 0.148 |
| rain_l6 | 3.611 | 0.108 |
| temp | 4.625 | 0.101 |
| y0 | 1.916 | 0.096 |
| rain_l4 | 4.420 | 0.084 |
| rain_l5 | 2.761 | 0.075 |
| rain_l7 | 3.266 | 0.067 |
| m4 | 2.334 | 0.067 |

Count (Poisson), top 8:

| feature | gain % | mean |SHAP| |
|---|---|---|
| area | 50.856 | 0.434 |
| thr | 13.199 | 0.185 |
| m4 | 7.583 | 0.142 |
| rh | 5.250 | 0.080 |
| cos1 | 3.408 | 0.076 |
| sin2 | 2.635 | 0.061 |
| rain4 | 3.744 | 0.059 |
| m8 | 3.160 | 0.051 |

### Rainfall lag

| rain lag (weeks before target) | model: mean SHAP if heavy rain (log-odds) | model: mean SHAP otherwise | data: share elevated after heavy rain % | data: share elevated otherwise % | data: ratio | heavy-rain district-weeks |
|---|---|---|---|---|---|---|
| 2 | -0.03 | 0.00 | 46.87 | 30.84 | 1.52 | 399 |
| 3 | -0.06 | -0.01 | 50.12 | 30.58 | 1.64 | 401 |
| 4 | 0.17 | -0.02 | 58.22 | 30.03 | 1.94 | 383 |
| 5 | 0.12 | -0.00 | 54.78 | 30.27 | 1.81 | 387 |
| 6 | 0.12 | -0.01 | 52.47 | 30.46 | 1.72 | 385 |
| 7 | 0.12 | -0.01 | 53.73 | 30.28 | 1.77 | 402 |
| 8 | 0.03 | 0.00 | 50.74 | 30.50 | 1.66 | 408 |

![rain lag](figures/outlook_leptospirosis_rain_lag.png)

**Finding: leptospirosis risk rises about 4 weeks after a very wet week in the model (largest push on P(elevated)); in the raw data the excess is largest 4 weeks after.** Association, not proof of cause: wet weeks also cluster in the monsoon seasons the Fourier terms describe.

### Live outlook (origin 2026-W36, as of 2026-09-06): highest P(elevated) for this week and next week

| area | target_week | h | model | p_elevated | p_lo | p_hi | pred_count | lo90 | hi90 | elevated_threshold |
|---|---|---|---|---|---|---|---|---|---|---|
| Mannar | 2026-W45 | 9 | glm | 0.36 | 0.35 | 0.36 | 1.28 | 0.00 | 4.99 | 2.00 |
| Hambantota | 2026-W45 | 9 | glm | 0.36 | 0.35 | 0.36 | 11.76 | 2.98 | 20.55 | 10.00 |
| Badulla | 2026-W45 | 9 | glm | 0.30 | 0.28 | 0.31 | 9.64 | 1.62 | 17.66 | 9.00 |
| Kalutara | 2026-W46 | 10 | glm | 0.30 | 0.29 | 0.30 | 15.22 | 5.07 | 25.38 | 17.00 |
| Kalutara | 2026-W45 | 9 | glm | 0.22 | 0.21 | 0.22 | 14.75 | 4.99 | 24.51 | 17.00 |
| Mullaitivu | 2026-W45 | 9 | glm | 0.22 | 0.21 | 0.22 | 1.41 | 0.00 | 5.23 | 2.00 |
| Colombo | 2026-W45 | 9 | glm | 0.21 | 0.20 | 0.22 | 10.93 | 2.44 | 19.43 | 14.00 |
| Kandy | 2026-W45 | 9 | glm | 0.20 | 0.18 | 0.21 | 6.78 | 0.00 | 13.64 | 9.00 |
| Trincomalee | 2026-W45 | 9 | glm | 0.19 | 0.18 | 0.20 | 3.05 | 0.00 | 8.00 | 4.00 |
| Kegalle | 2026-W45 | 9 | glm | 0.19 | 0.18 | 0.20 | 20.57 | 9.15 | 31.99 | 25.00 |

## Dengue

Backtest origins 2024-W01 to 2026-W35 (139 origins x 26 districts x up to 10 horizons). **Models are selected on 2024 origins only; every number below is on the untouched 2025-26 origins** unless the heading says otherwise.

### Headline (test origins 2025-26): Brier skill vs persistence (BSS), MASE vs persistence, 90% interval coverage (static split-conformal)

| model | h=1 BSS | h=1 MASE | h=1 cov90 % | h=2 BSS | h=2 MASE | h=2 cov90 % | h=9 (this week) BSS | h=9 (this week) MASE | h=9 (this week) cov90 % | h=10 (next week) BSS | h=10 (next week) MASE | h=10 (next week) cov90 % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Persistence | 0.00 | 1.00 | 86.84 | 0.00 | 1.00 | 85.23 | 0.00 | 1.00 | 80.87 | 0.00 | 1.00 | 81.64 |
| Seasonal climatology | -0.28 | 2.32 | 83.97 | -0.22 | 1.82 | 83.63 | 0.30 | 0.87 | 81.33 | 0.32 | 0.88 | 80.97 |
| NB GLM / logistic | 0.28 | 1.26 | 86.14 | 0.29 | 1.14 | 85.46 | 0.40 | 0.81 | 82.03 | 0.41 | 0.83 | 82.26 |
| LightGBM | 0.19 | 1.63 | 86.33 | 0.17 | 1.34 | 86.02 | 0.35 | 0.78 | 82.54 | 0.35 | 0.80 | 81.69 |

![skill](figures/outlook_dengue_skill.png)

### Model selection (2024 origins) -> what the dashboard shows

Candidates: persistence, seasonal climatology, NB GLM / logistic, LightGBM. Counts are selected by MASE, P(elevated) by Brier, on 2024 origins only; any model within 0.01 of the best is a tie and the simplest of the tied models is kept (persistence < climatology < GLM < LightGBM). This replaces the earlier rule (LightGBM unless persistence beats it), which looked at all years and ignored the GLM.

| h | selected count model | count selection reason | selected probability model | probability selection reason |
|---|---|---|---|---|
| 1 | Persistence | MASE best on 2024 origins (1.000) | Persistence | Brier within 0.01 of the best on 2024 origins (glm 0.096, persistence 0.103); the simpler model is kept |
| 2 | Persistence | MASE best on 2024 origins (1.000) | Persistence | Brier within 0.01 of the best on 2024 origins (glm 0.106, persistence 0.114); the simpler model is kept |
| 3 | Persistence | MASE best on 2024 origins (1.000) | NB GLM / logistic | Brier best on 2024 origins (0.113) |
| 4 | NB GLM / logistic | MASE best on 2024 origins (0.977) | NB GLM / logistic | Brier best on 2024 origins (0.126) |
| 5 | NB GLM / logistic | MASE best on 2024 origins (0.914) | Seasonal climatology | Brier within 0.01 of the best on 2024 origins (glm 0.138, climatology 0.148); the simpler model is kept |
| 6 | NB GLM / logistic | MASE best on 2024 origins (0.869) | Seasonal climatology | Brier best on 2024 origins (0.140) |
| 7 | NB GLM / logistic | MASE best on 2024 origins (0.846) | Seasonal climatology | Brier best on 2024 origins (0.140) |
| 8 | NB GLM / logistic | MASE best on 2024 origins (0.841) | Seasonal climatology | Brier best on 2024 origins (0.135) |
| 9 | NB GLM / logistic | MASE best on 2024 origins (0.846) | Seasonal climatology | Brier best on 2024 origins (0.133) |
| 10 | NB GLM / logistic | MASE best on 2024 origins (0.859) | Seasonal climatology | Brier best on 2024 origins (0.131) |

How the selected models do on the untouched test (2025-26 origins):

| h | selected count model | its MASE (test) | LightGBM MASE (test) | selected probability model | its BSS vs persistence (test) | its BSS vs climatology (test) | LightGBM BSS vs persistence (test) |
|---|---|---|---|---|---|---|---|
| 1 | Persistence | 1.000 | 1.630 | Persistence | 0.000 | 0.216 | 0.190 |
| 2 | Persistence | 1.000 | 1.335 | Persistence | 0.000 | 0.180 | 0.171 |
| 3 | Persistence | 1.000 | 1.051 | NB GLM / logistic | 0.352 | 0.365 | 0.256 |
| 4 | NB GLM / logistic | 0.910 | 0.927 | NB GLM / logistic | 0.346 | 0.343 | 0.247 |
| 5 | NB GLM / logistic | 0.852 | 0.845 | Seasonal climatology | 0.108 | 0.000 | 0.278 |
| 6 | NB GLM / logistic | 0.801 | 0.786 | Seasonal climatology | 0.150 | 0.000 | 0.285 |
| 7 | NB GLM / logistic | 0.784 | 0.764 | Seasonal climatology | 0.251 | 0.000 | 0.344 |
| 8 | NB GLM / logistic | 0.788 | 0.768 | Seasonal climatology | 0.252 | 0.000 | 0.326 |
| 9 | NB GLM / logistic | 0.807 | 0.785 | Seasonal climatology | 0.296 | 0.000 | 0.345 |
| 10 | NB GLM / logistic | 0.826 | 0.803 | Seasonal climatology | 0.324 | 0.000 | 0.352 |

**At some horizons a selected model does not beat persistence on the test (MASE >= 1 or BSS <= 0); see the table.**

### Counts, every horizon (test)

| model | h | n | MAE | RMSE | MASE vs persistence | coverage80 % | width80 | coverage90 % | width90 | coverage80 ACI % | coverage90 ACI % | width90 ACI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 2158 | 25.289 | 85.906 | 1.630 | 77.525 | 35.646 | 86.330 | 50.734 | 79.564 | 89.574 | 79.185 |
| NB GLM / logistic | 1 | 2158 | 19.597 | 53.327 | 1.263 | 75.672 | 35.477 | 86.145 | 48.298 | 79.194 | 89.527 | 79.639 |
| Persistence | 1 | 2158 | 15.518 | 41.936 | 1.000 | 75.811 | 30.622 | 86.840 | 41.940 | 78.499 | 89.064 | 71.816 |
| Seasonal climatology | 1 | 2158 | 36.073 | 109.420 | 2.325 | 74.513 | 44.114 | 83.967 | 63.921 | 78.823 | 89.296 | 105.536 |
| LightGBM | 2 | 2132 | 26.549 | 88.708 | 1.335 | 77.861 | 36.802 | 86.023 | 52.195 | 79.221 | 89.493 | 83.910 |
| NB GLM / logistic | 2 | 2132 | 22.610 | 63.217 | 1.137 | 75.188 | 36.615 | 85.460 | 50.301 | 78.940 | 89.353 | 87.833 |
| Persistence | 2 | 2132 | 19.886 | 55.166 | 1.000 | 74.156 | 34.304 | 85.225 | 47.345 | 78.049 | 88.790 | 79.272 |
| Seasonal climatology | 2 | 2132 | 36.173 | 109.922 | 1.819 | 74.578 | 43.560 | 83.630 | 62.965 | 78.659 | 89.587 | 106.775 |
| LightGBM | 3 | 2106 | 27.985 | 92.310 | 1.051 | 77.113 | 37.319 | 85.755 | 53.400 | 78.443 | 88.794 | 117.628 |
| NB GLM / logistic | 3 | 2106 | 25.979 | 75.025 | 0.976 | 73.932 | 37.496 | 84.615 | 51.654 | 77.873 | 88.604 | 109.816 |
| Persistence | 3 | 2106 | 26.625 | 78.084 | 1.000 | 72.982 | 38.345 | 84.046 | 54.894 | 78.585 | 89.079 | 123.114 |
| Seasonal climatology | 3 | 2106 | 36.266 | 110.413 | 1.362 | 74.169 | 42.995 | 83.333 | 61.921 | 77.683 | 88.651 | 127.813 |
| LightGBM | 4 | 2080 | 29.071 | 94.801 | 0.927 | 76.587 | 38.121 | 84.856 | 53.850 | 77.548 | 87.644 | 114.978 |
| NB GLM / logistic | 4 | 2080 | 28.542 | 84.487 | 0.910 | 73.413 | 38.160 | 83.558 | 53.480 | 76.731 | 87.837 | 123.199 |
| Persistence | 4 | 2080 | 31.350 | 95.596 | 1.000 | 73.365 | 42.460 | 83.317 | 60.870 | 79.327 | 88.413 | 134.167 |
| Seasonal climatology | 4 | 2080 | 36.369 | 110.973 | 1.160 | 73.846 | 42.486 | 83.029 | 60.934 | 76.923 | 87.788 | 129.641 |
| LightGBM | 5 | 2054 | 30.462 | 98.491 | 0.845 | 75.657 | 38.679 | 84.275 | 53.803 | 76.680 | 86.563 | 117.077 |
| NB GLM / logistic | 5 | 2054 | 30.727 | 92.453 | 0.852 | 73.028 | 38.473 | 82.911 | 54.384 | 75.949 | 86.417 | 134.088 |
| Persistence | 5 | 2054 | 36.047 | 111.875 | 1.000 | 73.418 | 45.341 | 83.009 | 68.022 | 78.140 | 87.342 | 181.426 |
| Seasonal climatology | 5 | 2054 | 36.542 | 111.571 | 1.014 | 73.759 | 42.058 | 82.619 | 60.014 | 76.095 | 87.098 | 134.639 |
| LightGBM | 6 | 2028 | 31.466 | 100.648 | 0.786 | 75.690 | 39.600 | 83.777 | 54.770 | 75.690 | 85.454 | 113.413 |
| NB GLM / logistic | 6 | 2028 | 32.075 | 97.491 | 0.801 | 72.781 | 39.270 | 82.840 | 53.981 | 74.852 | 85.750 | 136.750 |
| Persistence | 6 | 2028 | 40.045 | 122.712 | 1.000 | 71.844 | 47.928 | 82.150 | 70.182 | 77.022 | 86.292 | 208.723 |
| Seasonal climatology | 6 | 2028 | 36.741 | 112.210 | 0.917 | 73.521 | 41.731 | 82.199 | 59.229 | 75.394 | 85.996 | 124.507 |
| LightGBM | 7 | 2028 | 32.056 | 101.641 | 0.764 | 75.888 | 39.926 | 83.629 | 54.903 | 75.148 | 85.059 | 109.360 |
| NB GLM / logistic | 7 | 2028 | 32.887 | 100.654 | 0.784 | 73.028 | 39.709 | 82.939 | 54.028 | 74.408 | 86.489 | 147.877 |
| Persistence | 7 | 2028 | 41.957 | 127.236 | 1.000 | 71.400 | 49.713 | 82.199 | 73.930 | 75.986 | 85.700 | 262.604 |
| Seasonal climatology | 7 | 2028 | 36.741 | 112.210 | 0.876 | 73.521 | 41.672 | 82.101 | 58.825 | 74.556 | 87.130 | 129.754 |
| LightGBM | 8 | 2002 | 32.812 | 103.168 | 0.768 | 75.774 | 40.214 | 83.167 | 55.254 | 74.525 | 85.365 | 97.590 |
| NB GLM / logistic | 8 | 2002 | 33.643 | 103.428 | 0.788 | 73.377 | 40.231 | 82.817 | 54.142 | 74.525 | 86.414 | 129.414 |
| Persistence | 8 | 2002 | 42.717 | 127.713 | 1.000 | 71.628 | 52.583 | 81.618 | 72.408 | 74.476 | 85.015 | 217.792 |
| Seasonal climatology | 8 | 2002 | 37.017 | 112.905 | 0.867 | 73.277 | 41.508 | 81.818 | 58.365 | 74.625 | 86.913 | 124.222 |
| LightGBM | 9 | 1976 | 33.654 | 104.683 | 0.785 | 75.051 | 40.399 | 82.540 | 56.148 | 74.696 | 87.298 | 101.995 |
| NB GLM / logistic | 9 | 1976 | 34.599 | 106.201 | 0.807 | 73.735 | 40.865 | 82.034 | 54.422 | 74.798 | 85.678 | 117.906 |
| Persistence | 9 | 1976 | 42.883 | 126.748 | 1.000 | 71.255 | 51.926 | 80.870 | 73.859 | 73.532 | 83.755 | 161.743 |
| Seasonal climatology | 9 | 1976 | 37.338 | 113.624 | 0.871 | 73.077 | 41.387 | 81.326 | 57.979 | 75.152 | 86.690 | 119.027 |
| LightGBM | 10 | 1950 | 34.178 | 105.831 | 0.803 | 74.923 | 40.725 | 81.692 | 55.846 | 75.538 | 86.308 | 106.120 |
| NB GLM / logistic | 10 | 1950 | 35.138 | 108.192 | 0.826 | 74.205 | 41.878 | 82.256 | 55.264 | 75.795 | 86.308 | 117.362 |
| Persistence | 10 | 1950 | 42.546 | 122.133 | 1.000 | 71.795 | 53.435 | 81.641 | 75.723 | 74.051 | 82.000 | 126.065 |
| Seasonal climatology | 10 | 1950 | 37.613 | 114.337 | 0.884 | 72.923 | 41.342 | 80.974 | 57.736 | 76.615 | 86.718 | 115.071 |

### Elevated, every horizon (test)

| model | h | n_class | base rate % | Brier | BSS vs persistence | BSS vs climatology | recall | precision | AUROC | PR-AUC | mean p range |
|---|---|---|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 2158 | 30.816 | 0.143 | 0.190 | 0.365 | 0.382 | 0.888 | 0.864 | 0.783 | 0.017 |
| NB GLM / logistic | 1 | 2158 | 30.816 | 0.126 | 0.284 | 0.438 | 0.522 | 0.842 | 0.881 | 0.803 | 0.021 |
| Persistence | 1 | 2158 | 30.816 | 0.176 | 0.000 | 0.216 | 0.714 | 0.714 | 0.794 | 0.598 |  |
| Seasonal climatology | 1 | 2158 | 30.816 | 0.225 | -0.275 | 0.000 | 0.236 | 0.473 | 0.628 | 0.405 |  |
| LightGBM | 2 | 2132 | 30.816 | 0.150 | 0.171 | 0.320 | 0.320 | 0.913 | 0.851 | 0.764 | 0.017 |
| NB GLM / logistic | 2 | 2132 | 30.816 | 0.129 | 0.290 | 0.417 | 0.514 | 0.851 | 0.879 | 0.791 | 0.021 |
| Persistence | 2 | 2132 | 30.816 | 0.181 | 0.000 | 0.180 | 0.723 | 0.700 | 0.792 | 0.591 |  |
| Seasonal climatology | 2 | 2132 | 30.816 | 0.221 | -0.219 | 0.000 | 0.234 | 0.486 | 0.639 | 0.419 |  |
| LightGBM | 3 | 2106 | 30.959 | 0.159 | 0.256 | 0.271 | 0.281 | 0.906 | 0.839 | 0.737 | 0.016 |
| NB GLM / logistic | 3 | 2106 | 30.959 | 0.138 | 0.352 | 0.365 | 0.511 | 0.814 | 0.865 | 0.754 | 0.022 |
| Persistence | 3 | 2106 | 30.959 | 0.214 | 0.000 | 0.020 | 0.658 | 0.654 | 0.751 | 0.536 |  |
| Seasonal climatology | 3 | 2106 | 30.959 | 0.218 | -0.021 | 0.000 | 0.225 | 0.490 | 0.649 | 0.429 |  |
| LightGBM | 4 | 2080 | 30.865 | 0.164 | 0.247 | 0.245 | 0.271 | 0.879 | 0.831 | 0.723 | 0.015 |
| NB GLM / logistic | 4 | 2080 | 30.865 | 0.142 | 0.346 | 0.343 | 0.469 | 0.818 | 0.864 | 0.731 | 0.021 |
| Persistence | 4 | 2080 | 30.865 | 0.217 | 0.000 | -0.004 | 0.662 | 0.644 | 0.749 | 0.531 |  |
| Seasonal climatology | 4 | 2080 | 30.865 | 0.217 | 0.003 | 0.000 | 0.223 | 0.493 | 0.650 | 0.434 |  |
| LightGBM | 5 | 2054 | 31.256 | 0.175 | 0.278 | 0.190 | 0.202 | 0.890 | 0.817 | 0.694 | 0.015 |
| NB GLM / logistic | 5 | 2054 | 31.256 | 0.151 | 0.377 | 0.301 | 0.428 | 0.811 | 0.854 | 0.697 | 0.020 |
| Persistence | 5 | 2054 | 31.256 | 0.242 | 0.000 | -0.122 | 0.604 | 0.615 | 0.716 | 0.495 |  |
| Seasonal climatology | 5 | 2054 | 31.256 | 0.216 | 0.108 | 0.000 | 0.220 | 0.505 | 0.658 | 0.448 |  |
| LightGBM | 6 | 2028 | 31.607 | 0.181 | 0.285 | 0.158 | 0.172 | 0.873 | 0.817 | 0.695 | 0.015 |
| NB GLM / logistic | 6 | 2028 | 31.607 | 0.160 | 0.368 | 0.256 | 0.354 | 0.775 | 0.843 | 0.664 | 0.017 |
| Persistence | 6 | 2028 | 31.607 | 0.252 | 0.000 | -0.177 | 0.582 | 0.605 | 0.703 | 0.484 |  |
| Seasonal climatology | 6 | 2028 | 31.607 | 0.214 | 0.150 | 0.000 | 0.226 | 0.523 | 0.667 | 0.462 |  |
| LightGBM | 7 | 2028 | 31.361 | 0.187 | 0.344 | 0.124 | 0.151 | 0.889 | 0.799 | 0.671 | 0.014 |
| NB GLM / logistic | 7 | 2028 | 31.361 | 0.168 | 0.408 | 0.210 | 0.341 | 0.761 | 0.826 | 0.638 | 0.020 |
| Persistence | 7 | 2028 | 31.361 | 0.285 | 0.000 | -0.335 | 0.514 | 0.550 | 0.661 | 0.435 |  |
| Seasonal climatology | 7 | 2028 | 31.361 | 0.213 | 0.251 | 0.000 | 0.223 | 0.520 | 0.668 | 0.460 |  |
| LightGBM | 8 | 2002 | 31.568 | 0.192 | 0.326 | 0.099 | 0.139 | 0.917 | 0.794 | 0.672 | 0.014 |
| NB GLM / logistic | 8 | 2002 | 31.568 | 0.174 | 0.389 | 0.184 | 0.340 | 0.782 | 0.816 | 0.645 | 0.017 |
| Persistence | 8 | 2002 | 31.568 | 0.284 | 0.000 | -0.336 | 0.513 | 0.554 | 0.661 | 0.438 |  |
| Seasonal climatology | 8 | 2002 | 31.568 | 0.213 | 0.252 | 0.000 | 0.229 | 0.531 | 0.673 | 0.464 |  |
| LightGBM | 9 | 1976 | 31.832 | 0.198 | 0.345 | 0.069 | 0.132 | 0.902 | 0.778 | 0.659 | 0.014 |
| NB GLM / logistic | 9 | 1976 | 31.832 | 0.180 | 0.402 | 0.150 | 0.267 | 0.753 | 0.808 | 0.634 | 0.018 |
| Persistence | 9 | 1976 | 31.832 | 0.302 | 0.000 | -0.421 | 0.458 | 0.530 | 0.634 | 0.415 |  |
| Seasonal climatology | 9 | 1976 | 31.832 | 0.212 | 0.296 | 0.000 | 0.235 | 0.544 | 0.679 | 0.471 |  |
| LightGBM | 10 | 1950 | 32.154 | 0.202 | 0.352 | 0.041 | 0.174 | 0.872 | 0.773 | 0.657 | 0.014 |
| NB GLM / logistic | 10 | 1950 | 32.154 | 0.184 | 0.410 | 0.128 | 0.230 | 0.758 | 0.795 | 0.653 | 0.017 |
| Persistence | 10 | 1950 | 32.154 | 0.312 | 0.000 | -0.479 | 0.435 | 0.518 | 0.622 | 0.407 |  |
| Seasonal climatology | 10 | 1950 | 32.154 | 0.211 | 0.324 | 0.000 | 0.236 | 0.554 | 0.688 | 0.484 |  |

![reliability](figures/outlook_dengue_reliability.png)

`mean p range` is the width of the Venn-Abers calibration range. It is narrow because the calibration pool is large and it describes calibration uncertainty only; outbreak uncertainty is carried by the count interval. The dashboard shows the range only in a tooltip, labelled 'calibration range'.

### Baseline probabilities as displayed (post-hoc display change, disclosed)

Persistence gives a 0/1 probability and climatology a frequency over one to four past years, so where they are the selected model the dashboard would print 0% or 100%. **After model selection and evaluation**, the displayed probability of these two baselines was changed to an empirical frequency estimated past-only (expanding window, per disease and horizon, from earlier forecasts whose target was already reported): persistence shows P(elevated at t+h | elevated status at t), Laplace-smoothed; climatology shows the district's own past frequency at that time of year, smoothed with two pseudo-weeks at the 20% base rate. The selected model at each horizon is unchanged, and every other number in this report (selection, BSS, reliability) still uses the probabilities as evaluated. Brier on the test origins (2025-26), lower is better:

| h | persistence Brier (0/1, as evaluated) | persistence Brier (calibrated display) | climatology Brier (as evaluated) | climatology Brier (calibrated display) |
|---|---|---|---|---|
| 1 | 0.176 | 0.140 | 0.225 | 0.217 |
| 2 | 0.181 | 0.142 | 0.221 | 0.214 |
| 3 | 0.214 | 0.162 | 0.218 | 0.213 |
| 4 | 0.217 | 0.163 | 0.217 | 0.211 |
| 5 | 0.242 | 0.177 | 0.216 | 0.211 |
| 6 | 0.252 | 0.184 | 0.214 | 0.210 |
| 7 | 0.285 | 0.197 | 0.213 | 0.209 |
| 8 | 0.284 | 0.199 | 0.213 | 0.209 |
| 9 | 0.302 | 0.207 | 0.212 | 0.209 |
| 10 | 0.312 | 0.212 | 0.211 | 0.208 |

### Count intervals: static split-conformal vs adaptive conformal (ACI)

ACI (Gibbs & Candes 2021) keeps the same rolling pool of past-only scores but adapts the working miscoverage online: when a forecast's target is reported, the miscoverage moves by gamma = 0.005 x (nominal - miss), per forecast, with gamma fixed a priori. The dashboard uses ACI only if it brings 2026 coverage closer to nominal without moving 2024-25 coverage more than 2.5 points from nominal.

| scope (selected count models, all horizons) | n | 80% static | 80% ACI | 90% static | 90% ACI | 90% width static | 90% width ACI |
|---|---|---|---|---|---|---|---|
| 2024-25 targets | 25090 | 87.4 | 81.2 | 94.9 | 90.9 | 68.1 | 130.6 |
| 2026 targets | 8580 | 61.6 | 72.8 | 72.3 | 85.5 | 63.9 | 224.9 |
| test (2025-26 origins) | 20514 | 73.7 | 76.3 | 83.6 | 87.2 | 52.3 | 117.6 |

**ACI used: 2026 coverage 80/90 static 61.6/72.3% -> ACI 72.8/85.5% (closer to nominal); 2024-25 ACI 81.2/90.9% (within +-2.5 pp of nominal).**

### 2026 separately (targets in 2026)

| model | h | n | MASE vs persistence | BSS vs persistence | BSS vs climatology | AUROC | coverage90 % | coverage90 ACI % |
|---|---|---|---|---|---|---|---|---|
| LightGBM | 1 | 858 | 1.763 | 0.165 | 0.421 | 0.825 | 75.641 | 88.695 |
| NB GLM / logistic | 1 | 858 | 1.250 | 0.304 | 0.517 | 0.852 | 77.739 | 89.277 |
| Persistence | 1 | 858 | 1.000 | 0.000 | 0.306 | 0.749 | 80.536 | 88.345 |
| Seasonal climatology | 1 | 858 | 2.553 | -0.441 | 0.000 | 0.572 | 70.163 | 89.977 |
| LightGBM | 2 | 858 | 1.363 | 0.127 | 0.379 | 0.807 | 75.175 | 89.044 |
| NB GLM / logistic | 2 | 858 | 1.106 | 0.296 | 0.499 | 0.843 | 76.340 | 89.394 |
| Persistence | 2 | 858 | 1.000 | 0.000 | 0.289 | 0.742 | 78.671 | 88.811 |
| Seasonal climatology | 2 | 858 | 1.888 | -0.406 | 0.000 | 0.577 | 69.580 | 90.559 |
| LightGBM | 9 | 858 | 0.798 | 0.254 | 0.049 | 0.684 | 67.949 | 85.082 |
| NB GLM / logistic | 9 | 858 | 0.825 | 0.338 | 0.155 | 0.685 | 67.366 | 82.984 |
| Persistence | 9 | 858 | 1.000 | 0.000 | -0.275 | 0.583 | 72.261 | 78.438 |
| Seasonal climatology | 9 | 858 | 0.894 | 0.216 | 0.000 | 0.597 | 65.152 | 84.499 |
| LightGBM | 10 | 858 | 0.838 | 0.255 | 0.013 | 0.683 | 67.366 | 83.916 |
| NB GLM / logistic | 10 | 858 | 0.864 | 0.343 | 0.130 | 0.692 | 67.832 | 84.382 |
| Persistence | 10 | 858 | 1.000 | 0.000 | -0.325 | 0.574 | 72.960 | 75.524 |
| Seasonal climatology | 10 | 858 | 0.933 | 0.245 | 0.000 | 0.608 | 64.452 | 83.800 |

### What drives LightGBM (live models, on their training rows)

Mean |SHAP| is LightGBM's own TreeSHAP (`pred_contrib`), on the log scale of the model (log count / log-odds). Gain = share of split gain.

Elevated (binary), top 12:

| feature | gain % | mean |SHAP| |
|---|---|---|
| thr | 18.604 | 0.853 |
| cos2 | 8.146 | 0.420 |
| sin1 | 9.186 | 0.361 |
| y0 | 12.894 | 0.324 |
| area | 13.073 | 0.282 |
| m4 | 4.959 | 0.198 |
| neigh | 5.024 | 0.164 |
| ly | 3.673 | 0.090 |
| m8 | 1.405 | 0.090 |
| temp | 2.843 | 0.078 |
| rain_l5 | 2.326 | 0.075 |
| y1 | 1.546 | 0.073 |

Count (Poisson), top 8:

| feature | gain % | mean |SHAP| |
|---|---|---|
| m4 | 18.488 | 0.296 |
| area | 11.339 | 0.265 |
| y0 | 45.344 | 0.223 |
| thr | 3.258 | 0.151 |
| cos2 | 5.865 | 0.130 |
| m8 | 2.366 | 0.112 |
| ly | 2.685 | 0.062 |
| sin1 | 1.508 | 0.051 |

### Rainfall lag

| rain lag (weeks before target) | model: mean SHAP if heavy rain (log-odds) | model: mean SHAP otherwise | data: share elevated after heavy rain % | data: share elevated otherwise % | data: ratio | heavy-rain district-weeks |
|---|---|---|---|---|---|---|
| 2 | -0.09 | -0.00 | 26.82 | 27.51 | 0.97 | 399 |
| 3 | 0.08 | -0.01 | 30.92 | 27.18 | 1.14 | 401 |
| 4 | 0.13 | -0.02 | 35.32 | 26.86 | 1.32 | 385 |
| 5 | 0.12 | -0.01 | 36.18 | 26.79 | 1.35 | 387 |
| 6 | 0.20 | -0.02 | 39.63 | 26.53 | 1.49 | 381 |
| 7 | 0.07 | 0.00 | 38.64 | 26.57 | 1.45 | 396 |
| 8 | 0.12 | -0.01 | 41.32 | 26.32 | 1.57 | 409 |

![rain lag](figures/outlook_dengue_rain_lag.png)

**Finding: dengue risk rises about 6 weeks after a very wet week in the model (largest push on P(elevated)); in the raw data the excess is largest 8 weeks after.** Association, not proof of cause: wet weeks also cluster in the monsoon seasons the Fourier terms describe.

### Live outlook (origin 2026-W36, as of 2026-09-06): highest P(elevated) for this week and next week

| area | target_week | h | model | p_elevated | p_lo | p_hi | pred_count | lo90 | hi90 | elevated_threshold |
|---|---|---|---|---|---|---|---|---|---|---|
| Jaffna | 2026-W46 | 10 | climatology | 0.75 |  |  | 64.42 | 0.00 | 191.19 | 46.20 |
| Mannar | 2026-W45 | 9 | climatology | 0.67 |  |  | 6.58 | 0.00 | 49.75 | 5.00 |
| Mannar | 2026-W46 | 10 | climatology | 0.67 |  |  | 6.42 | 0.00 | 49.10 | 5.00 |
| Jaffna | 2026-W45 | 9 | climatology | 0.67 |  |  | 53.67 | 0.00 | 169.56 | 46.20 |
| Puttalam | 2026-W46 | 10 | climatology | 0.58 |  |  | 32.17 | 0.00 | 122.44 | 28.00 |
| Puttalam | 2026-W45 | 9 | climatology | 0.50 |  |  | 30.67 | 0.00 | 118.87 | 28.00 |
| Badulla | 2026-W46 | 10 | climatology | 0.42 |  |  | 27.00 | 0.00 | 109.94 | 25.20 |
| Matale | 2026-W46 | 10 | climatology | 0.33 |  |  | 27.25 | 0.00 | 110.56 | 38.00 |
| Badulla | 2026-W45 | 9 | climatology | 0.33 |  |  | 23.17 | 0.00 | 100.22 | 25.20 |
| Kilinochchi | 2026-W46 | 10 | climatology | 0.33 |  |  | 2.92 | 0.00 | 33.94 | 4.20 |

## Dengue: 2026 forecasts vs NDCU district flags

Forecast elevated (dashboard class model at that horizon, P >= 0.5) vs NDCU: a district is NDCU-positive when >= 1 (or >= 3) of its MOH areas is on that week's high-risk list. The row 'observed (truth)' compares the observed elevated flag itself, so it shows how far the two definitions can agree at best: NDCU flags absolute MOH burden, 'elevated' is relative to the district's own past.

| h | model | NDCU-positive | district-weeks | both | agreement % | kappa | share of NDCU flags forecast % | share of forecasts flagged % | NDCU onsets | onsets forecast within +-4 wk |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | persistence | >= 1 MOH | 858 | 307 | 67.9 | 0.37 | 77.9 | 62.0 | 70 | 62 |
| 1 | observed (truth) | >= 1 MOH | 858 | 307 | 69.1 | 0.39 | 77.9 | 63.3 | 70 | 62 |
| 1 | persistence | >= 3 MOH | 858 | 188 | 61.5 | 0.29 | 89.1 | 38.0 | 35 | 34 |
| 1 | observed (truth) | >= 3 MOH | 858 | 187 | 62.5 | 0.30 | 88.6 | 38.6 | 35 | 34 |
| 2 | persistence | >= 1 MOH | 858 | 314 | 66.4 | 0.34 | 79.7 | 60.2 | 70 | 60 |
| 2 | observed (truth) | >= 1 MOH | 858 | 308 | 69.3 | 0.39 | 78.2 | 63.5 | 70 | 62 |
| 2 | persistence | >= 3 MOH | 858 | 191 | 59.1 | 0.26 | 90.5 | 36.6 | 35 | 34 |
| 2 | observed (truth) | >= 3 MOH | 858 | 188 | 62.7 | 0.30 | 89.1 | 38.8 | 35 | 34 |
| 9 | climatology | >= 1 MOH | 858 | 110 | 57.8 | 0.12 | 27.9 | 58.5 | 70 | 39 |
| 9 | observed (truth) | >= 1 MOH | 858 | 314 | 70.4 | 0.41 | 79.7 | 64.3 | 70 | 61 |
| 9 | climatology | >= 3 MOH | 858 | 48 | 64.7 | 0.01 | 22.7 | 25.5 | 35 | 19 |
| 9 | observed (truth) | >= 3 MOH | 858 | 193 | 63.5 | 0.32 | 91.5 | 39.5 | 35 | 34 |
| 10 | climatology | >= 1 MOH | 858 | 111 | 58.3 | 0.13 | 28.2 | 59.7 | 70 | 38 |
| 10 | observed (truth) | >= 1 MOH | 858 | 315 | 70.4 | 0.41 | 79.9 | 64.3 | 70 | 61 |
| 10 | climatology | >= 3 MOH | 858 | 47 | 64.7 | 0.01 | 22.3 | 25.3 | 35 | 19 |
| 10 | observed (truth) | >= 3 MOH | 858 | 194 | 63.5 | 0.32 | 91.9 | 39.6 | 35 | 34 |

## Limitations

- 2.6 seasons of training history at the first test origin (2022-2023), 4.6 at the last; the seasonal terms and the climatology baseline rest on few years.
- Weather is one Open-Meteo point per district (centroid), not an areal average; Kalmunai uses its town point.
- The first-printed weekly counts are under-notified and late reports raise them later; the target is what a Regional Epidemiologist would have seen, not true incidence.
- Venn-Abers and conformal pools pool all districts: coverage holds on average, not for every district.
- Rows where any model has no forecast are left out of the comparison; all models are scored on the same district-weeks.
