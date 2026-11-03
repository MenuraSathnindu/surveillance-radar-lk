# Build plan — 2 Nov → 5 Nov 2026 (compressed)

**Deadline: Thu 5 Nov 2026, 23:59.** (Moved from Sun 1 Nov; see Data availability.)
The proposal scheduled the scraper for 20–24 Oct. Build effectively restarts on 2 Nov, so 4 days
remain. This plan applies the proposal's own contingencies up front (section 10) to fit.

## Data availability
epid.gov.lk was unavailable from 25 Oct to early Nov 2026: first a bandwidth limit, then HTTP 403/500
for scripted requests. Day-1 work (download, layout inspection) slipped to Mon 2 Nov and the
deadline moved to Thu 5 Nov. The downloader now identifies itself as a bot, sends ordinary
Accept headers, keeps a 2 s delay, downloads each file once and stops after 5 consecutive failures.
If the site goes down again: drop PDFs into `data/raw/wer/` and run
`python -m radar_lk.ingest.register --source wer`.

## Scope cuts applied now
| Proposal | Now | Restore if time allows |
|---|---|---|
| WER 2016–2026 | **WER 2022–2026 first** (≈240 issues) | Extend back to 2016 |
| CHIRPS + ERA5 per MOH | **Open-Meteo daily at 26 district-capital points** (`data/clean/weather.parquet`, done) | CHIRPS per MOH polygon |
| Dengue MOH high-risk outlook | **NO-GO (2 Nov): NDCU archive has only 2026 W1-43.** One disease-agnostic **district-level outlook** (leptospirosis primary, dengue secondary) from WER + weather that fills the publication gap: from the latest reported week t it forecasts t+1 .. t+L+2 (L = 8-week publication lag) | Dengue MOH outlook if older NDCU lists are found (see `docs/NDCU_FEASIBILITY.md`) |
| Farrington via R + EARS + NB-GLM | **EARS C1/C2/C3 + NB-GLM (pure Python)** | Farrington Flexible via rpy2 |
| Brief by email | **Downloadable brief (PDF/Markdown)** | Email |
| LLM phrasing | **Template only** | Optional LLM phrasing |

## Day by day
| Day | Goal | Done when |
|---|---|---|
| **Mon 2 Nov** | Download WER 2022–2026; inspect 3 layouts (2022, 2024, 2026) → `docs/LAYOUTS.md`; start the Table 1 parser | PDFs on disk + manifest; layout notes written; parser started |
| **Tue 3** | Hand-check the 40 cells + the 5 issues with odd cells; start radar baselines on `data/clean/wer.parquet` (use `completeness_low`, first-printed weekly counts) | Hand-check sheet filled; baselines run. **Decision taken early (Mon): leptospirosis fallback** |
| **Wed 4** | Radar: EARS + NB-GLM, percentile + expected range, completeness gating, backtest 2023–2026 vs "2× same week last year". Outlook (district-level leptospirosis, WER + weather lags): persistence, logistic, LightGBM, MAPIE conformal, rolling-origin backtest | Backtest tables: lead time, false alerts / 100 district-weeks; Brier, precision, recall vs persistence, interval coverage |
| **Thu 5** | Streamlit (This week, Map, Outlook, Track record), weekly brief template, technical report, two-page summary, 3-min demo video, hand-check tables, **submit by 23:59** | Submitted |

## Stop rules (from proposal section 9)
- Hand checks find errors the automatic checks missed → fix the parser before any modelling.
- Outlook doesn't beat persistence → show persistence, say so in the report.
- Radar flags >10% of district-weeks → tighten thresholds or restrict diseases.

## Status
- [x] Mon 2 Nov — downloader fixed, 244 WER PDFs downloaded, layouts documented. WER parser +
  two-tier validation (`python -m radar_lk.ingest.parse_wer`): 96.2% extraction_valid, 5.4% revised;
  6 week-typo overrides; extraction report and hand-check pack written
- [x] Mon 2 Nov — NDCU: 43 weekly PDFs (2026 W1-43) downloaded and parsed (`parse_ndcu`); **NO-GO**,
  history is 43 weeks, not 100 (`docs/NDCU_FEASIBILITY.md`) → leptospirosis outlook
- [x] Mon 2 Nov — weather: 26 points x 303 weeks, 2021-01 to 2026-10 (`python -m radar_lk.ingest.weather`)
- [x] Mon 2 Nov (late) — data integrity: row-alignment check (0 failures), PyMuPDF cross-extraction
  (100% of 177,876 cells agree), national cumulative source errors accepted, pre-2022 weeks dropped,
  extraction_valid 99.0%; district centroids from HDX COD-AB, weather re-fetched; hand-check pack v2
  (`data/handcheck/v2/`, to fill)
- [x] Mon 2 Nov (late) — radar: status quo, EARS C2/C3, NB-GLM with gating; signals, track record,
  backtest (`docs/RADAR_BACKTEST.md`)
- [x] Tue 3 — hand-check v2 scored (40/40); v3 pack (10 more cells) generated; publication lag
  measured (median 8 weeks); evaluation against proposal section 9: null false-alert rate, matched
  comparison, known-event replay (2024 leptospirosis, 2026 dengue, Cyclone Ditwah), gating
  evaluation, persistence and burden fields, 2026 reported separately, deviations documented
- [x] Tue 3 — hand-check v3 filled and scored with v2: **50/50** (95% CI 92.9-100%)
- [x] Tue 3 — radar follow-ups: two-tier radar (NB-GLM alert + EARS C2 early warning) evaluated and
  **adopted** (union 3.8 false alerts / 100, median replay gain 0); event replay with every
  qualifying district (67 district-events); held-back alerts shown greyed out with the shared
  label from config; wer.parquet rewrite checked (only `extracted_at` changed);
  `docs/HEADLINES.md` created as the single source for quoted numbers
- [x] Tue 3/Wed 4 — outlook: disease-agnostic engine (`src/radar_lk/outlook/`), leptospirosis +
  dengue, horizons 1..L+2, persistence / climatology / NB GLM-logistic / LightGBM, rolling-origin
  backtest from 2024-W01 (refit every 4 weeks), split-conformal intervals, Venn-Abers
  probabilities, SHAP, rainfall-lag figure, dengue vs NDCU check (`docs/OUTLOOK_BACKTEST.md`,
  `data/clean/outlook_forecasts.parquet`, `outlook_track_record.parquet`)
- [x] Tue 3 — outlook fixes: model selection on 2024 origins only (test = 2025-26 origins),
  adaptive conformal (ACI; used for dengue only, width cost reported), Venn-Abers range shown only
  as a tooltip; HEADLINES section 7 rewritten
- [x] Tue 3 — one-command pipeline (`python -m radar_lk.pipeline --all`, idempotent, logs) and
  Windows Task Scheduler instructions (README) in place of the GitHub Actions job
- [x] Tue 3 — dashboard (This week, Map, Outlook, Track record, Data & methods) with as-of replay,
  stale-data banner, footer; weekly brief (Markdown + PDF, zip of 26) and
  `docs/sample_brief_Galle.pdf`; non-clinical guard, number-provenance and AppTest tests; slim
  requirements.txt; screenshots in docs/figures/app_*.png
- [ ] Wed 4 — send the sample brief to a public-health reviewer; deploy to Streamlit Community Cloud
- [ ] Thu 5 — report, two-page summary, video (numbers from `docs/HEADLINES.md`), submit by 23:59
