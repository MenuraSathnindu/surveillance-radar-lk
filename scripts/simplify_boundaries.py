"""Simplified RDHS boundaries for the dashboard map -> data/geo/rdhs.geojson (committed).

    python scripts/simplify_boundaries.py

Source: OCHA HDX COD-AB Sri Lanka admin-2 (Survey Department of Sri Lanka, CC BY-IGO),
data/raw/boundaries/lka_admin_boundaries.geojson.zip (not committed: 128 MB). Polygons are
simplified in the Sri Lanka grid (EPSG:5235, tolerance TOL_M metres, topology kept per polygon),
converted to WGS84 and rounded to 4 decimals (~10 m). 25 administrative districts = 25 RDHS;
Exterior rings are made clockwise (plotly geo / d3-geo convention). Kalmunai RDHS has no
polygon (it is part of Ampara district), so data/geo/kalmunai_point.json
holds its town point and the map draws it as a marker inside Ampara.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from radar_lk import load_config  # noqa: E402
from radar_lk.ingest.parse_wer import norm  # noqa: E402

ZIP = REPO / "data" / "raw" / "boundaries" / "lka_admin_boundaries.geojson.zip"
OUT = REPO / "data" / "geo"
TOL_M = 400.0
NAME_FIX = {"moneragala": "Monaragala"}


def _clockwise(geom):
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.geometry.polygon import orient

    if isinstance(geom, Polygon):
        return orient(geom, sign=-1.0)
    if isinstance(geom, MultiPolygon):
        return MultiPolygon([orient(p, sign=-1.0) for p in geom.geoms])
    return geom


def _round(o, nd=4):
    if isinstance(o, float):
        return round(o, nd)
    if isinstance(o, list):
        return [_round(v, nd) for v in o]
    if isinstance(o, dict):
        return {k: _round(v, nd) for k, v in o.items()}
    return o


def main() -> None:
    import geopandas as gpd

    g = gpd.read_file(f"zip://{ZIP.as_posix()}!lka_admin2.geojson")
    units = {norm(u): u for u in load_config()["rdhs_units"]}
    g["rdhs"] = [NAME_FIX.get(norm(n)) or units.get(norm(n)) for n in g["adm2_name"]]
    g = g[["rdhs", "geometry"]].to_crs(5235)
    g["geometry"] = g.geometry.simplify(TOL_M, preserve_topology=True)
    g = g.to_crs(4326)
    # plotly's spherical geo (d3-geo) wants exterior rings clockwise; otherwise each polygon is
    # drawn as "everything except the district" and the map fills as one block
    g["geometry"] = g.geometry.apply(_clockwise)
    OUT.mkdir(parents=True, exist_ok=True)
    gj = json.loads(g.to_json(drop_id=True))
    for f in gj["features"]:
        f["id"] = f["properties"]["rdhs"]
    (OUT / "rdhs.geojson").write_text(json.dumps(_round(gj), separators=(",", ":")))
    pts = pd.read_csv(REPO / "config" / "district_points.csv").set_index("rdhs")
    k = pts.loc["Kalmunai"]
    lat = float(k["town_lat"] if "town_lat" in pts.columns else k["lat"])
    lon = float(k["town_lon"] if "town_lon" in pts.columns else k["lon"])
    (OUT / "kalmunai_point.json").write_text(
        json.dumps({"rdhs": "Kalmunai", "lat": lat, "lon": lon, "within": "Ampara"})
    )
    size = (OUT / "rdhs.geojson").stat().st_size
    print(
        f"wrote {OUT / 'rdhs.geojson'} ({len(g)} polygons, {size / 1024:.0f} KB) + Kalmunai point"
    )


if __name__ == "__main__":
    main()
