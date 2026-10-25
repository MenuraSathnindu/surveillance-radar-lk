# Surveillance Radar LK

Weekly outbreak-signal radar for Sri Lanka's Regional Epidemiologists.
ModelX 2.0 · Team SoloMind · Domain 03 (Health & wellbeing, non-clinical).

**What it does**
- **Radar:** flags district × disease weeks that are abnormal for that place and season
  (14 notifiable diseases, 26 RDHS units), held back when reporting completeness is too low.
- **Dengue outlook:** probability each MOH area joins the NDCU high-risk list in 1–2 weeks,
  with conformal uncertainty ranges and a published backtest.

Population-level signals for planning and investigation only. No diagnosis, no treatment or
prophylaxis advice, nothing about individuals.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
python -m radar_lk.ingest.download --source wer --years 2022-2026
streamlit run app/streamlit_app.py
```

## Pipeline
```
ingest → parse → validate → harmonise → store (Parquet + DuckDB) → radar / outlook → dashboard + brief
```
Nothing reaches the dashboard without passing the sum and cumulative checks.

## Data sources
- **Epidemiology Unit, Ministry of Health, Sri Lanka** — Weekly Epidemiological Report (primary source).
- **National Dengue Control Unit, Ministry of Health, Sri Lanka** — weekly and daily dengue updates.
- Open-Meteo (CC BY 4.0), CHIRPS (public domain), OCHA HDX COD-AB boundaries.

All data are public, aggregated weekly counts by area. No personal data.

## Status
See [`docs/PLAN.md`](docs/PLAN.md).
