"""District centroids from OCHA HDX COD-AB (Sri Lanka admin-2) -> config/district_points.csv.

    python scripts/district_centroids.py

Source: "Sri Lanka - Subnational Administrative Boundaries" (Survey Department of Sri Lanka via
OCHA HDX, CC BY-IGO), file data/raw/boundaries/lka_admin_boundaries.geojson.zip, layer admin2.
Centroids are computed in the Sri Lanka grid (EPSG:5235) and converted back to WGS84. Each district
keeps its capital-town point for reference; `lat`/`lon` (what weather.py fetches) become the
centroid. Kalmunai RDHS is not an administrative district (it is part of Ampara), so it keeps the
Kalmunai town point. Prints every town point more than 25 km from its district centroid.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from radar_lk import load_config  # noqa: E402
from radar_lk.ingest.parse_wer import norm  # noqa: E402

ZIP = REPO / "data" / "raw" / "boundaries" / "lka_admin_boundaries.geojson.zip"
POINTS = REPO / "config" / "district_points.csv"
NAME_FIX = {"moneragala": "Monaragala"}  # admin-2 spelling -> RDHS name in config
FAR_KM = 25.0


def km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def main() -> None:
    g = gpd.read_file(f"zip://{ZIP.as_posix()}!lka_admin2.geojson")
    units = {norm(u): u for u in load_config()["rdhs_units"]}
    g["rdhs"] = [NAME_FIX.get(norm(n)) or units.get(norm(n)) for n in g["adm2_name"]]
    if g["rdhs"].isna().any():
        raise SystemExit(
            f"unmatched admin-2 names: {g.loc[g['rdhs'].isna(), 'adm2_name'].tolist()}"
        )
    c = g.to_crs(5235).centroid.to_crs(4326)
    g["centroid_lat"], g["centroid_lon"] = c.y.round(4), c.x.round(4)
    g["inside"] = [geom.contains(pt) for geom, pt in zip(g.geometry, c, strict=True)]
    old = pd.read_csv(POINTS)
    if "town_lat" not in old.columns:  # first run: the existing lat/lon are the town points
        old = old.rename(columns={"lat": "town_lat", "lon": "town_lon"})
    m = old[["rdhs", "town", "town_lat", "town_lon"]].merge(
        g[["rdhs", "adm2_pcode", "centroid_lat", "centroid_lon", "inside"]], on="rdhs", how="left"
    )
    m["km_town_to_centroid"] = [
        round(km(a, b, x, y), 1) if pd.notna(x) else float("nan")
        for a, b, x, y in zip(
            m["town_lat"], m["town_lon"], m["centroid_lat"], m["centroid_lon"], strict=True
        )
    ]
    is_dist = m["centroid_lat"].notna()
    m["lat"] = m["centroid_lat"].where(is_dist, m["town_lat"])
    m["lon"] = m["centroid_lon"].where(is_dist, m["town_lon"])
    m["point_source"] = [
        "admin-2 centroid (HDX COD-AB, EPSG:5235)" if d else "town point (not an admin district)"
        for d in is_dist
    ]
    m["note"] = [
        "" if d else "Kalmunai RDHS is part of Ampara district; Kalmunai town used" for d in is_dist
    ]
    if not m.loc[is_dist, "inside"].all():
        print(
            "warning: centroid outside its district:",
            m.loc[is_dist & ~m["inside"], "rdhs"].tolist(),
        )
    cols = [
        "rdhs",
        "lat",
        "lon",
        "point_source",
        "adm2_pcode",
        "town",
        "town_lat",
        "town_lon",
        "centroid_lat",
        "centroid_lon",
        "km_town_to_centroid",
        "note",
    ]
    m[cols].to_csv(POINTS, index=False)
    far = m[m["km_town_to_centroid"] > FAR_KM].sort_values("km_town_to_centroid", ascending=False)
    print(f"wrote {POINTS} ({len(m)} RDHS, {int(is_dist.sum())} centroids)")
    print(f"town points more than {FAR_KM:.0f} km from their district centroid: {len(far)}")
    print(far[["rdhs", "town", "km_town_to_centroid"]].to_string(index=False))
    print("median distance:", m["km_town_to_centroid"].median(), "km")


if __name__ == "__main__":
    main()
