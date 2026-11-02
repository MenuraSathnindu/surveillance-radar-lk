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
| CHIRPS + ERA5 per MOH | **Open-Meteo daily, district centroids** | CHIRPS per MOH polygon |
| Farrington via R + EARS + NB-GLM | **EARS C1/C2/C3 + NB-GLM (pure Python)** | Farrington Flexible via rpy2 |
| Brief by email | **Downloadable brief (PDF/Markdown)** | Email |
| LLM phrasing | **Template only** | Optional LLM phrasing |

## Day by day
| Day | Goal | Done when |
|---|---|---|
| **Mon 2 Nov** | Download WER 2022–2026; inspect 3 layouts (2022, 2024, 2026) → `docs/LAYOUTS.md`; start the Table 1 parser | PDFs on disk + manifest; layout notes written; parser started |
| **Tue 3** | WER Table 1 parser + validation (sum, cumulative), completeness/timeliness columns; NDCU check (Table 1 + 2, **timeboxed**) | 2022–2026 in clean Parquet, ≥95% of issues pass checks. **Decision:** MOH flags reliable → dengue outlook; else leptospirosis fallback |
| **Wed 4** | Radar: EARS + NB-GLM, percentile + expected range, completeness gating, backtest 2023–2026 vs "2× same week last year". Outlook: persistence, logistic, LightGBM, MAPIE conformal, rolling-origin backtest | Backtest tables: lead time, false alerts / 100 district-weeks; Brier, precision, recall vs persistence, interval coverage |
| **Thu 5** | Streamlit (This week, Map, Outlook, Track record), weekly brief template, technical report, two-page summary, 3-min demo video, hand-check tables, **submit by 23:59** | Submitted |

## Stop rules (from proposal section 9)
- Hand checks find errors the automatic checks missed → fix the parser before any modelling.
- Outlook doesn't beat persistence → show persistence, say so in the report.
- Radar flags >10% of district-weeks → tighten thresholds or restrict diseases.

## Status
- [x] Mon 2 Nov — downloader fixed, 244 PDFs downloaded, layouts documented, WER parser + validation
  written (`python -m radar_lk.ingest.parse_wer`), extraction report and hand-check pack generated
- [ ] Tue 3 — **decision needed first:** validated rate is 90.6% vs the 95% target (see
  `docs/EXTRACTION_REPORT.md` section 4 and "What-if"); then hand-check, NDCU check, outlook decision
- [ ] Wed 4 — radar + outlook + backtests
- [ ] Thu 5 — dashboard, brief, report, video, submit by 23:59
