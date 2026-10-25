# Build plan — 25 Oct → 1 Nov 2026 (compressed)

The proposal scheduled the scraper for 20–24 Oct. Build starts 25 Oct, so 7 days remain.
This plan applies the proposal's own contingencies up front (section 10) to fit.

## Scope cuts applied now
| Proposal | Now | Restore if time allows |
|---|---|---|
| WER 2016–2026 | **WER 2022–2026 first** (≈250 issues) | Extend back to 2016 |
| CHIRPS + ERA5 per MOH | **Open-Meteo daily, district centroids** | CHIRPS per MOH polygon |
| Farrington via R + EARS + NB-GLM | **EARS C1/C2/C3 + NB-GLM (pure Python)** | Farrington Flexible via rpy2 |
| Brief by email | **Downloadable brief (PDF/Markdown)** | Email |
| LLM phrasing | **Template only** | Optional LLM phrasing |

## Day by day
| Day | Goal | Done when |
|---|---|---|
| **Sun 25** | Repo up; downloader; pull WER 2022–2026 + NDCU weekly 2024–2026; inspect 3 WER layouts (2022, 2024, 2026) and 2 NDCU issues | PDFs on disk + manifest; layout notes in `docs/LAYOUTS.md` |
| **Mon 26** | WER Table 1 parser + validation (sum, cumulative); completeness/timeliness columns | 2024–2026 in clean Parquet, ≥95% of issues pass checks |
| **Tue 27** | WER 2022–2023; NDCU Table 1 + Table 2 parser, **timeboxed to end of day** | **Decision:** MOH flags reliable → dengue outlook; else leptospirosis fallback |
| **Wed 28** | Radar: EARS + NB-GLM baselines, percentile + expected range, completeness gating; backtest 2023–2026 vs "2× same week last year" | Backtest table: detection lead time, false alerts / 100 district-weeks |
| **Thu 29** | Outlook: persistence, logistic, LightGBM; MAPIE conformal; rolling-origin backtest | Brier, precision, recall vs persistence; coverage of ranges |
| **Fri 30** | Streamlit: This week, Map, Outlook, Track record; weekly brief template | App runs end-to-end on latest validated week |
| **Sat 31** | Technical report, two-page summary, 3-min demo video | Drafts complete |
| **Sun 1 Nov** | Buffer, hand-check 50 tables, polish, **submit** | Submitted |

## Stop rules (from proposal section 9)
- Hand checks find errors the automatic checks missed → fix the parser before any modelling.
- Outlook doesn't beat persistence → show persistence, say so in the report.
- Radar flags >10% of district-weeks → tighten thresholds or restrict diseases.

## Status
- [ ] Sun 25 — repo, downloader, PDFs
- [ ] Mon 26 — WER parser + validation
- [ ] Tue 27 — NDCU parser + outlook decision
- [ ] Wed 28 — radar + backtest
- [ ] Thu 29 — outlook + backtest
- [ ] Fri 30 — dashboard + brief
- [ ] Sat 31 — report, summary, video
- [ ] Sun 1 — submit
