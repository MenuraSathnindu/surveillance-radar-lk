# Surveillance Radar LK

Weekly outbreak-signal radar for Sri Lanka's Regional Epidemiologists.
ModelX 2.0 · Team SoloMind · Domain 03 (Health & wellbeing, non-clinical).

**What it does**
- **Radar:** flags district × disease weeks that are abnormal for that place and season
  (14 notifiable diseases, 26 RDHS units), in two tiers (alert / early warning). Signals in
  weeks with low reporting completeness are held back: shown greyed out, never hidden.
- **Outlook:** for each district, the chance of an elevated leptospirosis (primary) or dengue
  week for "this week" and "next week", filling the WER's two-month publication gap with
  near-real-time rainfall; count forecasts with conformal intervals; published backtest.
- **Weekly brief:** six plain lines per RDHS, every number with its WER issue and week.

Population-level signals for planning and investigation only. No diagnosis, no treatment or
prophylaxis advice, nothing about individuals.

## Run the dashboard
```bash
pip install -r requirements.txt          # slim runtime: streamlit, pandas, plotly, fpdf2 ...
streamlit run app/streamlit_app.py
```
It reads only the committed `data/clean/` and `data/geo/` (no PDFs, no model fitting). The sidebar
"As of week" replays the system as it looked in any past week; `?week=2024-W51` in the URL
opens a replay week directly. Deploys as is to Streamlit Community Cloud (main file
`app/streamlit_app.py`, requirements `requirements.txt`).

## Run the pipeline
```bash
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m radar_lk.pipeline --all                   # download -> parse/validate -> radar ->
                                                    # outlook -> briefs
pytest -q
```
The pipeline is idempotent: a step whose inputs have not changed since its last successful run is
skipped (`data/logs/pipeline_state.json`; `--force` reruns everything). Each run logs to
`data/logs/pipeline_<timestamp>.log`. If the source site is down the download step fails, the run
continues on the data already on disk, and the exit code stays 0 for that case only.

### Weekly schedule on Windows (Task Scheduler)
epid.gov.lk blocks requests from cloud runners, so the daily GitHub Actions job in the proposal is
replaced by a scheduled task on a machine in Sri Lanka:

1. Open **Task Scheduler** → **Create Task…**
2. *General*: name `Surveillance Radar LK pipeline`; select **Run whether user is logged on or
   not**.
3. *Triggers*: **New…** → **Daily** at 06:00 (new WER issues appear irregularly; a daily check is
   cheap because unchanged steps are skipped).
4. *Actions*: **New…** → **Start a program**
   - Program/script: `F:\surveillance-radar-lk\.venv\Scripts\python.exe`
   - Add arguments: `-m radar_lk.pipeline --all`
   - Start in: `F:\surveillance-radar-lk`
5. *Settings*: tick **Stop the task if it runs longer than 2 hours**.

Or from a terminal (PowerShell):
```powershell
schtasks /Create /TN "Surveillance Radar LK pipeline" /SC DAILY /ST 06:00 `
  /TR "F:\surveillance-radar-lk\.venv\Scripts\python.exe -m radar_lk.pipeline --all" `
  /RL LIMITED /F
```
(`schtasks /TR` has no "start in" option; the pipeline resolves all paths from the package, so the
working directory does not matter.) To publish the new outputs, commit `data/clean/` and
`data/geo/` and push; Streamlit Community Cloud redeploys from the repository.

**Failure signal:** the dashboard's **stale-data banner**. It shows the latest WER issue, its
reporting week, today's date and the normal publication lag (about 8 weeks), and turns into a
warning when the latest week is more than lag + 2 weeks old. If the banner says "Data may be
stale", check the newest `data/logs/pipeline_*.log` for a failed step.

## Pipeline stages
```
ingest → parse → validate → harmonise → store (Parquet + DuckDB) → radar / outlook → dashboard + brief
```
Nothing reaches the dashboard without passing the sum and cumulative checks. Results:
`docs/EXTRACTION_REPORT.md`, `docs/RADAR_BACKTEST.md`, `docs/OUTLOOK_BACKTEST.md`; every number
quoted elsewhere comes from `docs/HEADLINES.md`.

## Data sources
- **Epidemiology Unit, Ministry of Health, Sri Lanka** — Weekly Epidemiological Report (primary source).
- **National Dengue Control Unit, Ministry of Health, Sri Lanka** — weekly dengue updates (external check).
- Open-Meteo (CC BY 4.0) weather; OCHA HDX COD-AB boundaries (CC BY-IGO).

All data are public, aggregated weekly counts by area. No personal data.

## Status
See [`docs/PLAN.md`](docs/PLAN.md).
