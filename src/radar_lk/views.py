"""As-of views over data/clean for the dashboard and the weekly brief (no pipeline imports).

Everything here takes an "as of" week W (the latest REPORTED week at that time) and returns
only what was available then: radar signals of week W (computed past-only), a series' track
record from signals before W, and outlook forecasts made at origin W. Replaying an earlier W
therefore shows the system as it would have looked that week. Model selection (outlook) and the
tier decision (radar) are fixed, documented choices made on the backtest; they are not replayed.

Reads only parquet files in data/clean (and data/geo for the map).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"
GEO = ROOT / "data" / "geo"

TIER_ORDER = {"alert": 0, "early_warning": 1, "held_back": 2}
TIER_TEXT = {"alert": "Alert", "early_warning": "Early warning", "held_back": "Held back"}
DISEASE_TEXT = {
    "chickenpox": "Chickenpox",
    "dengue": "Dengue",
    "dysentery": "Dysentery",
    "encephalitis": "Encephalitis",
    "enteric_fever": "Enteric fever",
    "food_poisoning": "Food poisoning",
    "human_rabies": "Human rabies",
    "leishmaniasis": "Leishmaniasis",
    "leprosy": "Leprosy",
    "leptospirosis": "Leptospirosis",
    "meningitis": "Meningitis",
    "tuberculosis": "Tuberculosis",
    "typhus": "Typhus",
    "viral_hepatitis": "Viral hepatitis",
}


def week_key(label: str) -> int:
    y, w = label.split("-W")
    return int(y) * 100 + int(w)


def week_label(y: int, w: int) -> str:
    return f"{int(y)}-W{int(w):02d}"


# ------------------------------------------------------------------ loading


def load_signals() -> pd.DataFrame:
    s = pd.read_parquet(CLEAN / "radar_signals.parquet")
    s["week"] = [week_label(y, w) for y, w in zip(s["epi_year"], s["epi_week"], strict=True)]
    return s


def load_forecasts() -> pd.DataFrame:
    return pd.read_parquet(CLEAN / "outlook_forecasts.parquet")


def load_outlook_track() -> pd.DataFrame:
    return pd.read_parquet(CLEAN / "outlook_track_record.parquet")


def load_wer() -> pd.DataFrame:
    c = pd.read_parquet(CLEAN / "wer.parquet")
    c = c[c["area_level"] == "rdhs"]
    c["week"] = [week_label(y, w) for y, w in zip(c["epi_year"], c["epi_week"], strict=True)]
    return c


def load_weather() -> pd.DataFrame:
    w = pd.read_parquet(CLEAN / "weather.parquet")
    w["week"] = [week_label(y, k) for y, k in zip(w["epi_year"], w["epi_week"], strict=True)]
    return w


def load_geo() -> tuple[dict, dict]:
    gj = json.loads((GEO / "rdhs.geojson").read_text())
    pt = json.loads((GEO / "kalmunai_point.json").read_text())
    return gj, pt


def weeks_available(sig: pd.DataFrame) -> list[str]:
    w = sig[["epi_year", "epi_week"]].drop_duplicates().sort_values(["epi_year", "epi_week"])
    return [week_label(y, k) for y, k in w.to_numpy()]


# ------------------------------------------------------------------ radar


def series_weeks(sig: pd.DataFrame) -> pd.DataFrame:
    """One row per (area, disease, t) with the tier (same on every method's row) and the
    method row that explains it: NB-GLM for alerts, EARS C2 for early warnings."""
    nb = sig[sig["method"] == "nb_glm"]
    c2 = sig[sig["method"] == "ears_c2"]
    key = ["area", "disease", "t"]
    base = sig.drop_duplicates(key)[
        key + ["week", "epi_year", "epi_week", "tier", "held_back", "tier_label"]
    ]
    nbc = [
        "observed", "expected", "upper", "percentile", "weeks_persisted", "sustained",
        "burden_pctl", "burden_label", "revised", "revision_delta", "completeness_pct",
        "completeness_p10", "completeness_low", "source_issue", "source_file", "suppress_reason",
    ]  # fmt: skip
    out = base.merge(nb[key + nbc], on=key, how="left")
    c2x = c2[key + nbc].rename(columns={c: f"c2_{c}" for c in nbc})
    out = out.merge(c2x, on=key, how="left")
    use_c2 = out["tier"].eq("early_warning") | out["expected"].isna()
    nb_pct = out["percentile"].copy()  # EARS has no percentile: keep NB-GLM's where it exists
    for c in nbc:
        out[c] = np.where(use_c2 & out[f"c2_{c}"].notna(), out[f"c2_{c}"], out[c])
    out["percentile"] = np.where(nb_pct.notna(), nb_pct, np.nan)
    out["explained_by"] = np.where(use_c2, "EARS C2", "NB-GLM")
    return out.drop(columns=[f"c2_{c}" for c in nbc])


def add_track_record(sw: pd.DataFrame) -> pd.DataFrame:
    """Per series, as of each week W: past signals (shown, weeks before W) and how many of them
    were followed by a second high week (known by W)."""
    sw = sw.sort_values(["area", "disease", "t"]).copy()
    sig = (sw["tier"] != "") & ~sw["held_back"].astype(bool)
    g = sw.assign(sig=sig).groupby(["area", "disease"], sort=False)
    nxt_t = g["t"].shift(-1)
    nxt_sig = g["sig"].shift(-1).fillna(False).astype(bool)
    high_next = (nxt_t == sw["t"] + 1) & (
        nxt_sig | (g["observed"].shift(-1) > g["upper"].shift(-1)).fillna(False)
    )
    sw["followed"] = sig & high_next
    g = sw.assign(sig=sig.astype(int), fol=sw["followed"].astype(int)).groupby(
        ["area", "disease"], sort=False
    )
    sw["past_signals"] = g["sig"].cumsum() - sig.astype(int)
    sw["past_followed"] = g["fol"].cumsum() - sw["followed"].astype(int)
    return sw


def signals_at(sw: pd.DataFrame, week: str) -> pd.DataFrame:
    """Shown signals (alert / early warning) and held-back ones for week `week`, sorted."""
    x = sw[(sw["week"] == week) & (sw["tier"] != "")].copy()
    x["status"] = np.where(x["held_back"].astype(bool), "held_back", x["tier"])
    x["order"] = x["status"].map(TIER_ORDER)
    return x.sort_values(["order", "percentile"], ascending=[True, False])


def kpis(x: pd.DataFrame) -> dict:
    shown = x[x["status"] != "held_back"]
    return {
        "alerts": int((x["status"] == "alert").sum()),
        "early_warnings": int((x["status"] == "early_warning").sum()),
        "held_back": int((x["status"] == "held_back").sum()),
        "districts": int(shown["area"].nunique()),
    }


# ------------------------------------------------------------------ outlook


def outlook_at(fc: pd.DataFrame, disease: str, week: str, L: int) -> pd.DataFrame:
    """Per district at origin `week`: P(elevated) and count forecast from the selected models at
    h = 1, 2, L+1, L+2; elevated now; emerging / persistent label."""
    f = fc[(fc["disease"] == disease) & (fc["origin_week"] == week)]
    if f.empty:
        return pd.DataFrame()
    aci = f["interval_method"].iloc[0] == "aci"
    lo, hi = ("lo90_aci", "hi90_aci") if aci else ("lo90", "hi90")
    pc = f[f["dashboard_class"]][
        ["area", "h", "model", "p_elevated", "p_lo", "p_hi", "target_week", "elevated_threshold"]
    ]
    cc = f[f["dashboard_count"]][["area", "h", "model", "pred_count", lo, hi, "observed"]]
    cc = cc.rename(columns={"model": "count_model", lo: "lo90", hi: "hi90"})
    o = pc.merge(cc, on=["area", "h"])
    now = f[(f["model"] == "persistence") & (f["h"] == 1)][["area", "p_elevated", "source_issue"]]
    now = now.rename(columns={"p_elevated": "elevated_now"})
    o = o.merge(now, on="area", how="left")
    o["interval"] = "ACI 90%" if aci else "90%"
    return o[o["h"].isin([1, 2, L + 1, L + 2])]


def outlook_wide(o: pd.DataFrame, L: int) -> pd.DataFrame:
    """One row per district: this week / next week / h=1 / h=2, emerging-persistent label,
    ranked by P(elevated) next week (proposal 7.3)."""
    if o.empty:
        return o
    rows = []
    for a, g in o.groupby("area"):
        g = g.set_index("h")
        r = {"area": a, "elevated_now": bool(g["elevated_now"].iloc[0] >= 0.5)}
        for h, name in ((L + 1, "this"), (L + 2, "next"), (1, "h1"), (2, "h2")):
            if h in g.index:
                r[f"p_{name}"] = float(g.at[h, "p_elevated"])
                r[f"plo_{name}"] = float(g.at[h, "p_lo"])
                r[f"phi_{name}"] = float(g.at[h, "p_hi"])
                r[f"count_{name}"] = float(g.at[h, "pred_count"])
                r[f"lo_{name}"] = float(g.at[h, "lo90"])
                r[f"hi_{name}"] = float(g.at[h, "hi90"])
                r[f"week_{name}"] = g.at[h, "target_week"]
                r[f"model_{name}"] = g.at[h, "model"]
                r[f"cmodel_{name}"] = g.at[h, "count_model"]
        r["threshold"] = float(g["elevated_threshold"].iloc[0])
        r["source_issue"] = g["source_issue"].iloc[0]
        rows.append(r)
    w = pd.DataFrame(rows)
    fut = (w.get("p_this", 0) >= 0.5) | (w.get("p_next", 0) >= 0.5)
    w["pattern"] = np.select(
        [w["elevated_now"] & fut, ~w["elevated_now"] & fut, w["elevated_now"] & ~fut],
        ["persistent", "emerging", "easing"],
        "",
    )
    return w.sort_values("p_next", ascending=False).reset_index(drop=True)


def rain_panel(weather: pd.DataFrame, area: str, end_week: str, n: int = 12) -> pd.DataFrame:
    """Last `n` weeks of rain to `end_week` for `area`, with the normal (mean of the same weeks
    of year in earlier years of the record)."""
    w = weather[weather["area"] == area].sort_values(["epi_year", "epi_week"]).reset_index()
    k = week_key(end_week)
    w["key"] = w["epi_year"] * 100 + w["epi_week"]
    last = w[w["key"] <= k].tail(n).copy()
    if last.empty:
        return last
    y0 = int(last["epi_year"].min())
    past = w[w["epi_year"] < y0]
    norm = past.groupby("epi_week")["precip_mm"].mean()
    last["normal_mm"] = last["epi_week"].map(norm)
    return last[["week", "epi_year", "epi_week", "precip_mm", "normal_mm", "as_of"]]


def add_weeks(label: str, n: int) -> str:
    from datetime import date, timedelta

    y, w = label.split("-W")
    d = date.fromisocalendar(int(y), int(w), 1) + timedelta(weeks=n)
    iy, iw = d.isocalendar()[:2]
    return week_label(iy, iw)
