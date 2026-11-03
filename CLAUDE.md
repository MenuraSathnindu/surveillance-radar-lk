# CLAUDE.md — Surveillance Radar LK

Context for Claude Code working in this repo. Read this first, every session.

## What this is
ModelX 2.0 (IEEE CIS Student Chapter, IIT) entry, team **SoloMind** (solo: Menura Gunasiri).
Domain 03 — Health & wellbeing, **non-clinical only**. Implementation due **Sun 1 Nov 2026**.
The submitted Phase 1 proposal is the spec; `docs/PLAN.md` is the day-by-day build plan.

**Problem:** Sri Lanka's Regional Epidemiologists (26 RDHS offices) get weekly disease counts
only as static PDFs, so abnormal local rises are noticed late.

**Product, two parts:**
1. **Radar** — for each of 26 RDHS units × 14 notifiable diseases (Epidemiology Unit WER Table 1),
   flag weeks that are abnormal for that place and season. Suppress alerts when that unit's
   reporting completeness is too low, and say why.
2. **Outlook (district level; the proposal's fallback)** — the NDCU MOH-level dengue outlook is
   NO-GO (only 43 weeks of NDCU lists, see `docs/NDCU_FEASIBILITY.md`). Instead, one
   disease-agnostic engine (`src/radar_lk/outlook/`) forecasts, for each of the 26 RDHS units,
   the weekly count and P(elevated) (count ≥ the district's own past-only 80th percentile).
   **Leptospirosis is primary, dengue secondary.** It fills the publication gap: the WER reports a
   week about L = `publication_lag_weeks` (8) weeks late, but rainfall is near real time, so from
   the latest reported week t it forecasts t+1 … t+L+2 (h = L+1 is "this week" and L+2 "next week"
   at the time of use; h = 1, 2 are the proposal's horizons). Weather features sit at lag ≥ 2 weeks
   before the target week (enforced in code). Models: persistence, seasonal climatology, NB GLM /
   logistic, LightGBM. Uncertainty: split-conformal count intervals and Venn-Abers probability
   ranges. Stop rule: at any horizon where LightGBM doesn't beat persistence, the dashboard shows
   the best baseline there. Results are in `docs/OUTLOOK_BACKTEST.md`.

Delivered as a Streamlit dashboard + a one-page weekly brief per RDHS.

## Hard rules
- **No clinical content.** No diagnosis, treatment or prophylaxis advice, nothing about individuals.
  Every alert is "a signal for investigation" and shows its track record.
- **Nothing unvalidated reaches the UI. Validation has two tiers:**
  1. `extraction_valid` (column `validated`) = passes the checks that need only the one issue: per
     (week, disease) the 26 districts add up to the printed national row in the weekly column, the
     cumulative column, or both; the row's label sits on the same text line as its numbers and the
     rows come in the expected order; the weekly column is neither a copy of the previous week's
     (`stale_weekly_copy`) nor printed against the wrong rows (`scrambled_weekly_column`, a
     past-only rank-correlation test); no blank or unreadable count cell; completeness/timeliness in
     [0,100] (outside -> NaN, counted); reporting week 2022-W01 or later. Only `extraction_valid` rows
     are written to `data/clean/` and may reach the dashboard; everything else goes to
     `data/review_queue/`. When exactly one national column disagrees with the districts, that
     national figure is the source error: keep the district rows
     (`note=national_weekly_source_error` or `note=national_cumulative_source_error`) and queue only
     the national row. When both disagree, the whole group is queued (`cum_sum_mismatch`).
  2. `revised` = the cross-week identity cum_t = cum_{t-1} + weekly_t fails. This does **not** remove a
     row: it sets `revised=True` and `revision_delta = cum_t - (cum_{t-1} + weekly_t)` (empty if the
     previous week is missing). Weekly counts are kept **as first printed** in that issue (what a
     Regional Epidemiologist saw in real time); the radar uses those, never back-filled values.
- **Completeness is relative.** C** is undefined in the WER, so never apply an absolute threshold:
  `completeness_low` = below that RDHS's own 10th percentile of past C** (expanding, past only).
- **Held-back alerts are shown, greyed out, never hidden.** An alert in a `completeness_low` week is
  held back, not dropped. Its label is "Possible rise, held back: reporting completeness low (X%).
  Late reports usually add cases, so the true rise may be larger." (X = that week's C**). The text
  lives in `config/sources.yaml` `radar_display.labels` (read via `radar_lk.radar.labels`), so
  the dashboard and the brief share it; never hard-code it. The backtest found that held-back
  alerts persist as often as kept ones, so hiding them would lose real rises.
  T* is display-only (it steps from ~40% to ~93% at 2023-W52).
- **Every displayed number carries its source file and as-of date.**
- **No LLM reads PDFs or produces numbers.** An LLM may only phrase the brief from computed values;
  the template path must always work without it.
- Attribute the Epidemiology Unit and NDCU as primary data sources on every page.
- Scraper honours robots.txt, identifies itself, rate-limits, and keeps original PDFs.
- Counts are under-notified: present signals relative to each area's own history, never as true incidence.

## Architecture (one-way batch pipeline)
```
ingest (download PDFs) -> parse (tables) -> validate -> harmonise (epi week, names)
  -> store (Parquet + DuckDB) -> models (radar, outlook) -> deliver (Streamlit, brief)
```
Deliver reads only model outputs, never raw PDFs.

## Layout
```
config/sources.yaml          source URLs, disease list, RDHS list, thresholds
src/radar_lk/ingest/         download.py, parse_wer.py, parse_ndcu.py, validate.py
src/radar_lk/harmonise/      epiweek.py (canonical week), names.py (district/MOH crosswalk)
src/radar_lk/store.py        tidy schema, Parquet/DuckDB IO
src/radar_lk/radar/          baselines (EARS, NB-GLM, Farrington via R), gating, backtest
src/radar_lk/outlook/        features (lag>=2 weather), models (persistence, climatology, GLM, LightGBM),
                             conformal (+Venn-Abers), neighbours (HDX adjacency), backtest, report
src/radar_lk/brief/          weekly brief generation (template first)
app/streamlit_app.py         dashboard
data/raw/                    original PDFs (gitignored), data/raw/manifest.csv (committed)
data/clean/                  validated Parquet + radar.duckdb
data/review_queue/           rows that failed validation
tests/fixtures/              a few sample PDFs used in CI extraction tests
```

## Tidy table (the one schema everything shares)
`week_start, week_end, epi_year, epi_week, area_level (rdhs|moh), area, disease, cases,
cum_cases, completeness_pct, timeliness_pct, source_file, source_issue, extracted_at, validated`

## Known data traps (handle explicitly)
- WER issue number, its listed date range and the week its table reports can all disagree
  (e.g. Vol 53 No 34). Always key on the reporting week printed in the table.
- Week definition changed in 2026: Saturday–Friday before, Monday–Sunday from 2026.
  `harmonise/epiweek.py` maps both to one canonical week via the Thursday rule.
- Layout drift across years; occasional 53-week years; garbled headers in extracted text.
- MOH spelling variants ("Pugoda (Dompe)"); build the crosswalk incrementally in `config/moh_crosswalk.csv`.
- NDCU lists only flagged MOH areas → counts missing for non-flagged areas. Model the **flag**, not counts.
- 2020–2021 (COVID) reporting is distorted; flag these years in baselines, consider excluding.

## Commands
```
pip install -e ".[dev]"            # install
pytest -q                          # tests (run before every commit)
python -m radar_lk.ingest.download --source wer --years 2022-2026
python -m radar_lk.ingest.download --source ndcu_weekly
python -m radar_lk.radar.run --reuse-fits && python -m radar_lk.radar.backtest --reuse
python -m radar_lk.outlook.backtest            # ~12 min; --reuse rebuilds the report only
streamlit run app/streamlit_app.py
```

## Working style
- Data first, baselines before models, backtest as soon as something runs.
- Small commits with clear messages; keep `docs/PLAN.md` status current.
- When a parser decision is uncertain, open the actual PDF page and check, don't guess.
- Prefer simple, interpretable methods; no deep learning (≈550 points per series).
