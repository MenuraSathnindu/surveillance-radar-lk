"""Daily weather per RDHS point from Open-Meteo's historical API, aggregated to the canonical week.

    python -m radar_lk.ingest.weather [--start 2021-01-01] [--end YYYY-MM-DD]

One request per point (26 in total), spaced by the configured delay, with an identifying
User-Agent. The raw JSON answers are kept in data/raw/weather/ as a per-point cache: a later run
fetches only the days after the cached end (re-fetching the last OVERLAP_DAYS, which the archive
may still revise), so a refresh is 26 small requests instead of 26 six-year ones. A 429 answer is
retried after the server's Retry-After (seconds or HTTP date, capped).

Output: data/clean/weather.parquet, one row per (RDHS, canonical week), attribution
"Open-Meteo (CC BY 4.0)". It is written only if EVERY RDHS covers every week from the first week
to the latest complete week returned (and at least to the latest reported WER week, which the
outlook needs); otherwise the run exits non-zero naming the districts and weeks, the previous
weather.parquet is kept, and the points that did succeed stay cached for the next run.

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
BACKOFF = 65.0  # s to wait after a 429 without Retry-After (the per-minute allowance resets)
MAX_RETRY_AFTER = 600.0  # s; never wait longer than this on one Retry-After
MAX_429_RETRIES = 3
OVERLAP_DAYS = 14  # re-fetch the last two cached weeks (recent archive days can be revised)
MAX_CONSECUTIVE_FAILURES = 3


class WeatherCoverageError(SystemExit):
    """Some RDHS lacks weather for weeks the outlook needs (exit code 1, message printed)."""


def retry_after_seconds(value: str | None, now: datetime | None = None) -> float:
    """Seconds to wait from a Retry-After header: delay-seconds or an HTTP date; BACKOFF when
    absent or unreadable; capped at MAX_RETRY_AFTER."""
    if not value:
        return BACKOFF
    try:
        wait = float(value)
    except ValueError:
        from email.utils import parsedate_to_datetime

        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return BACKOFF
        now = now or datetime.now(timezone.utc)
        wait = (when - now).total_seconds()
    return float(min(max(wait, 1.0), MAX_RETRY_AFTER))


def cache_plan(cached: dict | None, lat: float, lon: float, start: str, end: str):
    """(fetch_start, fetch_end) still needed for a point given its cached answer, or None if the
    cache already covers start..end. A cache for another point or a later start is refetched."""
    if not cached:
        return start, end
    req = cached.get("_request") or {}
    days = cached.get("daily", {}).get("time", [])
    same_point = req.get("lat") == float(lat) and req.get("lon") == float(lon)
    if not same_point or not days or days[0] > start:
        return start, end
    have = days[-1]
    if have >= end:
        return None
    frm = max(start, (date.fromisoformat(have) - timedelta(days=OVERLAP_DAYS)).isoformat())
    return frm, end


def merge_daily(old: dict, new: dict) -> dict:
    """Merge two Open-Meteo answers by date (the newer answer wins on overlapping days)."""
    rows = {}
    for src in (old, new):
        d = src.get("daily", {})
        for i, t in enumerate(d.get("time", [])):
            rows[t] = {k: d[k][i] for k in DAILY}
    times = sorted(rows)
    out = {k: v for k, v in new.items() if k != "daily"}
    out["daily"] = {"time": times, **{k: [rows[t][k] for t in times] for k in DAILY}}
    return out


def coverage_problems(df: pd.DataFrame, areas, first: tuple, last: tuple) -> dict[str, list]:
    """{area: missing canonical weeks 'YYYY-Www'} for weeks first..last (inclusive)."""
    d = date.fromisocalendar(first[0], first[1], 1)
    end = date.fromisocalendar(last[0], last[1], 1)
    need = []
    while d <= end:
        y, w = d.isocalendar()[:2]
        need.append((y, w))
        d += timedelta(weeks=1)
    have = {a: set(zip(g["epi_year"], g["epi_week"], strict=True)) for a, g in df.groupby("area")}
    out = {}
    for a in areas:
        miss = [f"{y}-W{w:02d}" for y, w in need if (y, w) not in have.get(a, set())]
        if miss:
            out[a] = miss
    return out


def describe(problems: dict[str, list]) -> str:
    parts = []
    for a, m in sorted(problems.items()):
        span = m[0] if len(m) == 1 else f"{m[0]}..{m[-1]} ({len(m)} weeks)"
        parts.append(f"{a}: {span}")
    return "; ".join(parts)


def latest_wer_week() -> tuple | None:
    p = CLEAN_DIR / "wer.parquet"
    if not p.exists():
        return None
    w = pd.read_parquet(p, columns=["epi_year", "epi_week"])
    return tuple(int(x) for x in w.sort_values(["epi_year", "epi_week"]).iloc[-1])


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
    for attempt in range(MAX_429_RETRIES + 1):
        r = _get(session, lat, lon, start, end)
        if r.status_code != 429 or attempt == MAX_429_RETRIES:
            break
        wait = retry_after_seconds(r.headers.get("Retry-After"))
        print(f"    429 Too Many Requests; waiting {wait:.0f} s (Retry-After) before retrying")
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


def run(
    start: str = "2021-01-01", end: str | None = None, session=None, required=None
) -> pd.DataFrame:
    cfg = load_config()
    delay = max(float(cfg["request_delay_seconds"]), MIN_DELAY)
    end = end or (date.today() - timedelta(days=LAG_DAYS)).isoformat()
    pts = load_points()
    required = list(required) if required is not None else list(cfg["rdhs_units"])
    out_dir = RAW_DIR / "weather"
    out_dir.mkdir(parents=True, exist_ok=True)
    if session is None:
        session = requests.Session()
        session.headers["User-Agent"] = cfg["user_agent"]
    frames, fails = [], 0
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    requested = 0
    for _, p in pts.iterrows():
        cache = out_dir / f"{p['rdhs'].replace(' ', '_')}.json"
        old = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
        plan = cache_plan(old, p["lat"], p["lon"], start, end)
        j = old
        if plan is not None:
            if requested:
                time.sleep(delay)
            requested += 1
            res = None
            for attempt in (1, 2):  # one retry after a pause (timeouts happen under load)
                try:
                    res = fetch_point(session, p["lat"], p["lon"], *plan)
                    break
                except (requests.RequestException, ValueError) as e:
                    res = e
                    if attempt == 1:
                        print(f"  {p['rdhs']}: {e}; retrying once in {BACKOFF:.0f} s")
                        time.sleep(BACKOFF)
            if isinstance(res, Exception):
                fails += 1
                print(f"  [fail {fails}/{MAX_CONSECUTIVE_FAILURES}] {p['rdhs']}: {res}")
                if fails >= MAX_CONSECUTIVE_FAILURES:
                    raise SystemExit(
                        "[stop] consecutive failures; not hammering the API. Points fetched so "
                        "far are cached; rerun later to fetch only what is missing."
                    ) from res
                if old is None or cache_plan(old, p["lat"], p["lon"], start, start) is not None:
                    continue  # nothing usable for this point; the coverage check reports it
                # keep the cached days for this point; the coverage check decides if enough
            else:
                fails = 0
                fresh = plan[0] == start or old is None
                j = res if fresh else merge_daily(old, res)
                j["_request"] = {"lat": float(p["lat"]), "lon": float(p["lon"]), "start": start}
                cache.write_text(json.dumps(j), encoding="utf-8")
                print(f"  {p['rdhs']}: fetched {plan[0]} to {plan[1]}")
        d = pd.DataFrame({"date": j["daily"]["time"], **{k: j["daily"][k] for k in DAILY}})
        w = weekly(d)
        w["area"] = p["rdhs"]
        w["area_level"] = "rdhs"
        w["lat"], w["lon"] = p["lat"], p["lon"]
        w["point_source"] = p.get("point_source", "")
        w["grid_lat"], w["grid_lon"] = j["latitude"], j["longitude"]
        w["elevation_m"] = j.get("elevation")
        w["as_of"] = j["daily"]["time"][-1]
        frames.append(w)
    df = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=["area", "epi_year", "epi_week"])
    )
    # coverage: every required RDHS, every week from the first complete week to the latest
    # complete week any point returned, and at least to the latest reported WER week
    first = canonical_week(
        date.fromisoformat(start) + timedelta(days=(7 - date.fromisoformat(start).weekday()) % 7)
    )
    if len(df):
        last_row = df.sort_values(["epi_year", "epi_week"]).iloc[-1]
        last = (int(last_row["epi_year"]), int(last_row["epi_week"]))
    else:
        last = first
    wer_last = latest_wer_week()
    if wer_last and wer_last > last:
        last = wer_last
    problems = coverage_problems(df, required, first, last)
    if problems:
        raise WeatherCoverageError(
            f"[stop] weather incomplete for {len(problems)} RDHS (needed {first[0]}-W"
            f"{first[1]:02d} to {last[0]}-W{last[1]:02d}): {describe(problems)}. "
            "weather.parquet NOT written (previous file kept); fetched points are cached, so "
            "rerun to fetch only what is missing."
        )
    df["source"] = ATTRIBUTION
    df["source_url"] = API
    df["fetched_at"] = fetched_at
    cols = [
        "week_start", "week_end", "epi_year", "epi_week", "area_level", "area", "precip_mm",
        "temp_c", "rh_pct", "n_days", "lat", "lon", "point_source", "grid_lat", "grid_lon",
        "elevation_m", "source", "source_url", "fetched_at", "as_of",
    ]  # fmt: skip
    df = df[cols].sort_values(["area", "epi_year", "epi_week"]).reset_index(drop=True)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CLEAN_DIR / "weather.parquet", index=False)
    from radar_lk import store

    store.refresh_db()
    print(
        f"wrote {len(df)} rows ({df['area'].nunique()} RDHS), weeks {df['week_start'].min()} to "
        f"{df['week_end'].max()} (complete weeks), {requested} request(s), archive to {end}"
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
