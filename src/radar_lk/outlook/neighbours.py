"""District adjacency for the outlook's neighbour feature -> config/district_adjacency.csv.

    python -m radar_lk.outlook.neighbours

Source: OCHA HDX COD-AB Sri Lanka admin-2 polygons (Survey Department of Sri Lanka, CC BY-IGO),
data/raw/boundaries/lka_admin_boundaries.geojson.zip. Two districts are neighbours when their
polygons touch or come within `TOL_M` metres of each other in the Sri Lanka grid (EPSG:5235); the
tolerance absorbs digitising slivers along shared borders and lagoon mouths.

Kalmunai RDHS is not an administrative district (it is carved out of Ampara district), so it has
no polygon. By rule it is adjacent to Ampara and Batticaloa, and only to them (its coastal strip
lies between the two).
"""

from __future__ import annotations

import pandas as pd

from radar_lk import RAW_DIR, REPO_ROOT, load_config

ZIP = RAW_DIR / "boundaries" / "lka_admin_boundaries.geojson.zip"
OUT = REPO_ROOT / "config" / "district_adjacency.csv"
TOL_M = 200.0
NAME_FIX = {"moneragala": "Monaragala"}  # admin-2 spelling -> RDHS name
KALMUNAI = ("Kalmunai", ["Ampara", "Batticaloa"])


def build() -> pd.DataFrame:
    import geopandas as gpd

    from radar_lk.ingest.parse_wer import norm

    g = gpd.read_file(f"zip://{ZIP.as_posix()}!lka_admin2.geojson").to_crs(5235)
    units = {norm(u): u for u in load_config()["rdhs_units"]}
    g["rdhs"] = [NAME_FIX.get(norm(n)) or units.get(norm(n)) for n in g["adm2_name"]]
    if g["rdhs"].isna().any():
        raise SystemExit(f"unmatched admin-2 names: {g.loc[g['rdhs'].isna(), 'adm2_name']}")
    rows = []
    geoms = dict(zip(g["rdhs"], g.geometry, strict=True))
    names = sorted(geoms)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            if geoms[a].distance(geoms[b]) <= TOL_M:
                rows += [(a, b, "polygon"), (b, a, "polygon")]
    k, nbrs = KALMUNAI
    for b in nbrs:
        rows += [(k, b, "rule: Kalmunai RDHS"), (b, k, "rule: Kalmunai RDHS")]
    return pd.DataFrame(rows, columns=["area", "neighbour", "basis"]).sort_values(
        ["area", "neighbour"]
    )


def load() -> dict[str, list[str]]:
    """{area: [neighbours]} from the committed CSV."""
    d = pd.read_csv(OUT)
    return {a: sorted(g["neighbour"]) for a, g in d.groupby("area")}


def main() -> None:
    d = build()
    d.to_csv(OUT, index=False)
    n = d.groupby("area").size()
    print(f"wrote {OUT}: {len(d) // 2} pairs; neighbours per district {n.min()}-{n.max()}")
    print(n.to_string())


if __name__ == "__main__":
    main()
