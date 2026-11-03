"""Weather fetch: incremental per-point cache, Retry-After, and the coverage stop."""

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from radar_lk.ingest import weather as wx
from radar_lk.ingest.weather import load_points, weekly


def _answer(start: str, end: str, lat=7.0, lon=80.0, rain=1.0) -> dict:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]
    return {
        "latitude": lat,
        "longitude": lon,
        "elevation": 10.0,
        "daily": {
            "time": days,
            "precipitation_sum": [rain] * len(days),
            "temperature_2m_mean": [27.0] * len(days),
            "relative_humidity_2m_mean": [80.0] * len(days),
        },
    }


# ------------------------------------------------------------------ weekly aggregation


def _daily(start: date, n: int, rain=1.0, temp=27.0, rh=80.0):
    days = [start + timedelta(days=i) for i in range(n)]
    return pd.DataFrame(
        {
            "date": [d.isoformat() for d in days],
            "precipitation_sum": rain,
            "temperature_2m_mean": temp,
            "relative_humidity_2m_mean": rh,
        }
    )


def test_26_points_one_per_rdhs():
    pts = load_points()
    assert len(pts) == 26 and pts["rdhs"].is_unique
    assert pts["lat"].between(5.5, 10).all() and pts["lon"].between(79, 82.5).all()


def test_weekly_aggregates_monday_to_sunday_and_drops_partial_weeks():
    # Wed 3 Jun 2026 .. Sun 14 Jun 2026: first week partial, second week (8-14 Jun) complete
    w = weekly(_daily(date(2026, 6, 3), 12))
    assert len(w) == 1
    r = w.iloc[0]
    assert r["week_start"] == date(2026, 6, 8) and r["week_end"] == date(2026, 6, 14)
    assert (r["epi_year"], r["epi_week"]) == (2026, 24)
    assert (
        r["precip_mm"] == 7.0 and r["temp_c"] == 27.0 and r["rh_pct"] == 80.0 and r["n_days"] == 7
    )


def test_week_with_a_missing_day_is_dropped():
    d = _daily(date(2026, 6, 8), 7)
    d.loc[3, "precipitation_sum"] = None
    assert weekly(d).empty


def test_53_week_year_uses_the_thursday_rule():
    # Mon 28 Dec 2020 - Sun 3 Jan 2021 holds Thursday 31 Dec 2020: ISO 2020-W53
    w = weekly(_daily(date(2020, 12, 28), 7))
    assert (w.iloc[0]["epi_year"], w.iloc[0]["epi_week"]) == (2020, 53)
    w = weekly(_daily(date(2021, 1, 4), 7))
    assert (w.iloc[0]["epi_year"], w.iloc[0]["epi_week"]) == (2021, 1)


# ------------------------------------------------------------------ pieces


def test_retry_after_seconds_and_http_date_and_fallback():
    assert wx.retry_after_seconds("120") == 120
    assert wx.retry_after_seconds(None) == wx.BACKOFF
    assert wx.retry_after_seconds("not a date") == wx.BACKOFF
    assert wx.retry_after_seconds("99999") == wx.MAX_RETRY_AFTER  # capped
    now = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)
    assert wx.retry_after_seconds("Tue, 03 Nov 2026 12:00:30 GMT", now=now) == 30


def test_cache_plan_fetches_only_missing_days():
    cached = _answer("2021-01-01", "2026-10-20")
    cached["_request"] = {"lat": 7.0, "lon": 80.0, "start": "2021-01-01"}
    # same point, later end: only from (cached end - overlap) onward
    frm, to = wx.cache_plan(cached, 7.0, 80.0, "2021-01-01", "2026-10-31")
    assert to == "2026-10-31"
    assert frm == (date(2026, 10, 20) - timedelta(days=wx.OVERLAP_DAYS)).isoformat()
    assert wx.cache_plan(cached, 7.0, 80.0, "2021-01-01", "2026-10-20") is None  # covered
    assert wx.cache_plan(cached, 7.1, 80.0, "2021-01-01", "2026-10-31") == (
        "2021-01-01",
        "2026-10-31",
    )  # moved point: full refetch
    assert wx.cache_plan(None, 7.0, 80.0, "2021-01-01", "2026-10-31")[0] == "2021-01-01"


def test_merge_daily_newer_answer_wins_on_overlap():
    old = _answer("2026-10-01", "2026-10-10", rain=1.0)
    new = _answer("2026-10-08", "2026-10-15", rain=5.0)
    m = wx.merge_daily(old, new)
    t = m["daily"]["time"]
    assert t == sorted(set(t)) and t[0] == "2026-10-01" and t[-1] == "2026-10-15"
    rain = dict(zip(t, m["daily"]["precipitation_sum"], strict=True))
    assert rain["2026-10-07"] == 1.0 and rain["2026-10-08"] == 5.0


def test_coverage_problems_names_missing_district_and_weeks():
    df = pd.DataFrame(
        {"area": ["A", "A", "A", "B"], "epi_year": [2026] * 4, "epi_week": [1, 2, 3, 1]}
    )
    p = wx.coverage_problems(df, ["A", "B", "C"], (2026, 1), (2026, 3))
    assert p == {"B": ["2026-W02", "2026-W03"], "C": ["2026-W01", "2026-W02", "2026-W03"]}
    assert "B: 2026-W02..2026-W03 (2 weeks)" in wx.describe(p)


class _Resp:
    def __init__(self, status, payload=None, headers=None):
        self.status_code, self.headers, self._p = status, headers or {}, payload

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")


class _Session:
    """Fake requests.Session: answers per call from a list; records the requested ranges."""

    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((params["latitude"], params["start_date"], params["end_date"]))
        a = self.answers.pop(0)
        if callable(a):
            return a(params)
        return a


def test_fetch_point_honours_retry_after(monkeypatch):
    waits = []
    monkeypatch.setattr(wx.time, "sleep", waits.append)
    s = _Session([_Resp(429, headers={"Retry-After": "7"}), _Resp(200, {"ok": 1})])
    assert wx.fetch_point(s, 7.0, 80.0, "2026-01-01", "2026-01-31") == {"ok": 1}
    assert waits == [7.0]


# ------------------------------------------------------------------ run()


@pytest.fixture
def two_points(tmp_path, monkeypatch):
    pts = pd.DataFrame(
        {"rdhs": ["A", "B"], "lat": [7.0, 8.0], "lon": [80.0, 81.0], "point_source": ["t", "t"]}
    )
    monkeypatch.setattr(wx, "load_points", lambda: pts)
    monkeypatch.setattr(wx, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(wx, "CLEAN_DIR", tmp_path / "clean")
    monkeypatch.setattr(wx, "latest_wer_week", lambda: None)
    monkeypatch.setattr(wx.time, "sleep", lambda s: None)
    import radar_lk.store as store

    monkeypatch.setattr(store, "refresh_db", lambda: None)
    return tmp_path


def _ok(params):
    return _Resp(200, _answer(params["start_date"], params["end_date"], params["latitude"]))


def test_run_second_time_fetches_only_new_days(two_points):
    s1 = _Session([_ok, _ok])
    df = wx.run("2026-01-05", "2026-02-01", session=s1, required=["A", "B"])
    assert df["area"].nunique() == 2 and (two_points / "clean" / "weather.parquet").exists()
    s2 = _Session([_ok, _ok])
    wx.run("2026-01-05", "2026-02-15", session=s2, required=["A", "B"])
    starts = {c[1] for c in s2.calls}
    assert starts == {(date(2026, 2, 1) - timedelta(days=wx.OVERLAP_DAYS)).isoformat()}
    s3 = _Session([])  # everything cached: no request at all
    wx.run("2026-01-05", "2026-02-15", session=s3, required=["A", "B"])
    assert s3.calls == []


def test_run_stops_and_keeps_old_file_when_a_district_lacks_weather(two_points):
    wx.run("2026-01-05", "2026-02-01", session=_Session([_ok, _ok]), required=["A", "B"])
    out = two_points / "clean" / "weather.parquet"
    before = out.read_bytes()
    import requests

    def boom(params):
        raise requests.ConnectionError("down")

    # A extends fine; B fails twice (one retry) and has only the older cache -> weeks missing
    s = _Session([_ok, boom, boom])
    with pytest.raises(SystemExit) as e:
        wx.run("2026-01-05", "2026-03-01", session=s, required=["A", "B"])
    assert e.value.code != 0
    assert "B:" in str(e.value) and "NOT written" in str(e.value)
    assert out.read_bytes() == before  # previous complete file kept
    # a district never fetched at all is reported too
    with pytest.raises(SystemExit) as e2:
        wx.run("2026-01-05", "2026-02-01", session=_Session([]), required=["A", "B", "C"])
    assert "C:" in str(e2.value)
