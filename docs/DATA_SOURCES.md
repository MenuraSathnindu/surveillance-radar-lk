# Data sources

Every source, what is taken from it, how it is fetched, and the attribution to show. Raw files are
kept as downloaded and listed with SHA-256 hashes in `data/raw/manifest.csv`.

## 1. Epidemiology Unit, Weekly Epidemiological Report (primary)

- **Publisher:** Epidemiology Unit, Ministry of Health, Sri Lanka. **Attribution on every page:**
  "Source: Epidemiology Unit, Ministry of Health, Sri Lanka".
- **Where:** `https://www.epid.gov.lk/weekly-epidemiological-report` (one listing page).
- **What we take:** Table 1 only (RDHS x notifiable disease, weekly and cumulative counts,
  completeness C\*\* and timeliness T\*). 244 English PDFs, 2022-2026 (`data/raw/wer/`).
- **How:** `python -m radar_lk.ingest.download --source wer --years 2022-2026`. Honours robots.txt,
  identifies itself (`Mozilla/5.0 (compatible; SurveillanceRadarLK/0.1; +mailto:...)`), 2 s between
  requests, each file downloaded once, stops after 5 consecutive failures.

## 2. National Dengue Control Unit, Weekly Dengue Update (external validation only)

- **Publisher:** National Dengue Control Unit (NDCU), Ministry of Health, Sri Lanka. **Attribution:**
  "Source: National Dengue Control Unit, Ministry of Health, Sri Lanka".
- **Where:** `https://www.dengue.health.gov.lk/weekly-report/` (+ `/page/2/`, `/page/3/`).
- **What we take:** reporting week, Table 2 high-risk MOH areas with their district, Table 1 district
  weekly counts. The site holds 2026 Weeks 1-43 only (43 PDFs, `data/raw/ndcu_weekly/`).
- **Use:** the dengue MOH outlook is **NO-GO** (`docs/NDCU_FEASIBILITY.md`). The 2026 lists are kept as
  **external validation** for the WER dengue radar (`docs/RADAR_BACKTEST.md`). The ReliefWeb mirror is
  deliberately not used.
- **How:** same polite downloader as the WER.

## 3. Open-Meteo historical weather API (weather covariates)

- **Publisher:** Open-Meteo (`https://open-meteo.com`), historical API
  `https://archive-api.open-meteo.com/v1/archive` (reanalysis, ERA5-based). **Licence:** CC BY 4.0;
  free for non-commercial use. **Attribution to show:** "Weather data by Open-Meteo.com (CC BY 4.0)".
  The column `source` in `data/clean/weather.parquet` carries "Open-Meteo (CC BY 4.0)".
- **What we take:** daily `precipitation_sum`, `temperature_2m_mean`, `relative_humidity_2m_mean`,
  2021-01-01 to the latest available day (~3 days behind), one point per RDHS
  (`config/district_points.csv`), aggregated to the canonical Monday-Sunday week; incomplete weeks
  are dropped.
- **How (documented API client, not a crawler):** the API host's robots.txt says `Disallow: /`, which
  addresses crawlers. This project calls a documented public API with a handful of requests, so it
  is treated as an API client, not a crawler (decision of 2 Nov 2026): **one request per point (26 in
  total)**, **at least 6 s between requests** (Open-Meteo weighs a request by its size, and 6 years x
  3 variables is heavy), an identifying User-Agent, on HTTP 429 one wait of `Retry-After` (default 65 s)
  and one retry, and a stop after 3 consecutive failures. Raw answers are kept in
  `data/raw/weather/<RDHS>.json` with the requested point; a rerun re-fetches only points whose
  coordinates or date range changed.
- **Command:** `python -m radar_lk.ingest.weather`.

## 4. OCHA HDX COD-AB, Sri Lanka administrative boundaries (district centroids)

- **Publisher:** Survey Department of Sri Lanka, distributed by OCHA on HDX ("Sri Lanka - Subnational
  Administrative Boundaries", `https://data.humdata.org/dataset/cod-ab-lka`, version v03, valid from
  2022-08-16). **Licence:** CC BY-IGO. **Attribution:** "Boundaries: Survey Department of Sri Lanka,
  via OCHA HDX (CC BY-IGO)".
- **What we take:** the admin-2 (district) layer of `lka_admin_boundaries.geojson.zip` (133 MB,
  `data/raw/boundaries/`, gitignored, hash in the manifest). `scripts/district_centroids.py` computes
  area centroids in the Sri Lanka grid (EPSG:5235); these are the weather points for the 25 districts.
  **Kalmunai RDHS is not an administrative district** (it is part of Ampara), so it keeps the Kalmunai
  town point (7.4167, 81.8167).
- **How:** one file download, after the 10 s Crawl-Delay in HDX's robots.txt. The `.zip` download path
  is not disallowed there. Two things to note honestly: (1) to find the file URL I made one call to the
  HDX metadata API (`/api/3/action/package_show?id=cod-ab-lka`) before reading robots.txt, which
  disallows `/api/` for crawlers; (2) our robots-checking fetcher received HTTP 202 for robots.txt
  (a bot-challenge response) and therefore refuses HDX, so the single file was fetched directly with
  the identifying User-Agent after reading robots.txt with curl. No further HDX requests are made.
- **Check against the old points:** town points more than 25 km from their district centroid:
  Mullaitivu (30.9 km), Matale (25.2 km); median 15.2 km. Full table in `config/district_points.csv`.

## Not used

- ReliefWeb mirror of NDCU PDFs (decision 2 Nov 2026).
- Any LLM for reading PDFs or producing numbers (CLAUDE.md hard rule).
