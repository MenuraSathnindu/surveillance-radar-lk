"""Daily weather per RDHS point from Open-Meteo's historical API, aggregated to the canonical week.

    python -m radar_lk.ingest.weather [--start 2021-01-01] [--end YYYY-MM-DD]

One request per point (26 in total), spaced by the configured delay, with an identifying
User-Agent. The raw JSON answers are kept in data/raw/weather/. Output: data/clean/weather.parquet,
one row per (RDHS, canonical week), attribution "Open-Meteo (CC BY 4.0)".

Canonical week = Monday-Sunday ISO week (harmonise.epiweek, Thursday rule). Only complete weeks
(7 non-missing days for every variable) are kept. WER tables before 2026 run Saturday-Friday, so a
WER week and its canonical weather week overlap on 5 of 7 days; the join is by (epi_year, epi_week).

About robots.txt: archive-api.open-meteo.com serves "Disallow: /" to crawlers, but it is a
documented public API (free for non-commercial use with attribution) and this is a client making
26 requests, not a crawler. That is why this module does not go through the robots-checking page
Fetcher.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from radar_lk import CLEAN_DIR, RAW_DIR, REPO_ROOT, load_config
from radar_lk.harmonise.epiweek import canonical_week

API = "https://archive-api.open-meteo.com/v1/archive"
POINTS = REPO_ROOT / "config" / "district_points.csv"
DAILY = ["precipitation_sum", "temperature_2m_mean", "relative_humidity_2m_mean"]
ATTRIBUTION = "Open-Meteo (CC BY 4.0)"
LAG_DAYS = 3  # the archive trails real time by a couple of days
MIN_DELAY = 6.0  # s; the limit is weighted by request size (6 years x 3 variables is heavy)
BACKOFF = 65.0  # s to wait after a 429 (the per-minute allowance resets), once per point
MAX_CONSECUTIVE_FAILURES = 3


def load_points() -> pd.DataFrame:
    pts = pd.read_csv(POINTS)
    cfg = load_config()
    missing = set(cfg["rdhs_units"]) - set(pts["rdhs"])
    if missing or len(pts) != 26:
        raise ValueError(
            f"district_points.csv must list the 26 RDHS units; missing {sorted(missing)}"
        )
    return pts


def weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Daily rows (date, precipitation_sum, temperature_2m_mean, relative_humidity_2m_mean) ->
    one row per canonical week; incomplete weeks are dropped."""
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"]).dt.date
    d["week_start"] = [x - timedelta(days=x.weekday()) for x in d["date"]]
    g = d.groupby("week_start")
    out = pd.DataFrame(
        {
            "precip_mm": g["precipitation_sum"].sum(min_count=7),
            "temp_c": g["temperature_2m_mean"].mean(),
            "rh_pct": g["relative_humidity_2m_mean"].mean(),
            "n_days": g[DAILY].apply(lambda x: int(x.notna().all(axis=1).sum())),
        }
    ).reset_index()
    out = out[out["n_days"] == 7].copy()
    out["week_end"] = [w + timedelta(days=6) for w in out["week_start"]]
    keys = [canonical_week(w) for w in out["week_start"]]
    out["epi_year"] = [k[0] for k in keys]
    out["epi_week"] = [k[1] for k in keys]
    return out


def fetch_point(session, lat: float, lon: float, start: str, end: str) -> dict:
    for attempt in (1, 2):
        r = _get(session, lat, lon, start, end)
        if r.status_code != 429 or attempt == 2:
            break
        wait = float(r.headers.get("Retry-After", BACKOFF))
        print(f"    429 Too Many Requests; waiting {wait:.0f} s before one retry")
        time.sleep(wait)
    r.raise_for_status()
    return r.json()


def _get(session, lat: float, lon: float, start: str, end: str):
    return session.get(
        API,
        params={
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "daily": ",".join(DAILY),
            "timezone": "Asia/Colombo",
        },
        timeout=90,
    )


def run(start: str = "2021-01-01", end: str | None = None) -> pd.DataFrame:
    cfg = load_config()
    delay = max(float(cfg["request_delay_seconds"]), MIN_DELAY)
    end = end or (date.today() - timedelta(days=LAG_DAYS)).isoformat()
    pts = load_points()
    out_dir = RAW_DIR / "weather"
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = cfg["user_agent"]
    frames, fails = [], 0
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    requested = 0
    stale: list[str] = []
    missing: set[str] = set()
    for _, p in pts.iterrows():
        cache = out_dir / f"{p['rdhs'].replace(' ', '_')}.json"
        j = None
        want = {"lat": float(p["lat"]), "lon": float(p["lon"]), "start": start, "end": end}
        if cache.exists():  # reuse an earlier answer only for the same point and date range
            old = json.loads(cache.read_text(encoding="utf-8"))
            got = old.get("_request")
            if (
                got is None and "town_lat" in p
            ):  # answers saved before 2 Nov were for the town point
                t = old.get("daily", {}).get("time", [])
                got = {
                    "lat": float(p["town_lat"]),
                    "lon": float(p["town_lon"]),
                    "start": t[0] if t else None,
                    "end": t[-1] if t else None,
                }
            if got == want:
                j = old
        if j is None:
            if requested:
                time.sleep(delay)
            requested += 1
            for attempt in (1, 2):  # one retry after a pause (timeouts happen under load)
                try:
                    j = fetch_point(session, p["lat"], p["lon"], start, end)
                    break
                except requests.RequestException as e:
                    j = e
                    if attempt == 1:
                        print(f"  {p['rdhs']}: {e}; retrying once in {BACKOFF:.0f} s")
                        time.sleep(BACKOFF)
        area_end = end
        if isinstance(j, requests.RequestException):
            e = j
            fails += 1
            print(f"  [fail {fails}/{MAX_CONSECUTIVE_FAILURES}] {p['rdhs']}: {e}")
            if fails >= MAX_CONSECUTIVE_FAILURES:
                raise SystemExit("[stop] consecutive failures; not hammering the API") from e
            if not cache.exists():
                missing.add(p["rdhs"])
                continue
            # keep the last good answer for this point (complete up to its own end date) rather
            # than dropping the district from the weather table
            j = json.loads(cache.read_text(encoding="utf-8"))
            area_end = (j.get("_request") or {}).get("end") or j["daily"]["time"][-1]
            stale.append(f"{p['rdhs']} (to {area_end})")
        else:
            fails = 0
            j["_request"] = want
            cache.write_text(json.dumps(j), encoding="utf-8")
        d = pd.DataFrame({"date": j["daily"]["time"], **{k: j["daily"][k] for k in DAILY}})
        w = weekly(d)
        w["area"] = p["rdhs"]
        w["area_level"] = "rdhs"
        w["lat"], w["lon"] = p["lat"], p["lon"]
        w["point_source"] = p.get("point_source", "")
        w["grid_lat"], w["grid_lon"] = j["latitude"], j["longitude"]
        w["elevation_m"] = j.get("elevation")
        w["as_of"] = area_end
        frames.append(w)
        print(f"  {p['rdhs']}: {len(w)} weeks")
    df = pd.concat(frames, ignore_index=True)
    df["source"] = ATTRIBUTION
    df["source_url"] = API
    df["fetched_at"] = fetched_at
    if missing:
        # never overwrite a complete weather table with one that lacks districts
        raise SystemExit(f"[stop] no weather at all for {sorted(missing)}; weather.parquet kept")
    if stale:
        print(f"  WARNING: fetch failed, last good data kept for: {', '.join(stale)}")
    cols = [
        "week_start",
        "week_end",
        "epi_year",
        "epi_week",
        "area_level",
        "area",
        "precip_mm",
        "temp_c",
        "rh_pct",
        "n_days",
        "lat",
        "lon",
        "point_source",
        "grid_lat",
        "grid_lon",
        "elevation_m",
        "source",
        "source_url",
        "fetched_at",
        "as_of",
    ]
    df = df[cols].sort_values(["area", "epi_year", "epi_week"]).reset_index(drop=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CLEAN_DIR / "weather.parquet", index=False)
    from radar_lk import store

    store.refresh_db()
    print(
        f"wrote {len(df)} rows ({df['area'].nunique()} RDHS), weeks {df['week_start'].min()} to "
        f"{df['week_end'].max()}, as of {end}"
    )
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--start", default="2021-01-01")
    ap.add_argument("--end", default=None)
    a = ap.parse_args()
    run(a.start, a.end)


if __name__ == "__main__":
    main()
