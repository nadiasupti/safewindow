"""Step 1 - Choose the study area and build the common flood-map grid.

    # rank all Sunamganj upazilas by mapped road density (OSM), to choose 2-3
    python pipeline/01_study_area.py --rank

    # build the study area from the upazilas in config.UPAZILAS
    python pipeline/01_study_area.py                     # boundaries from OpenStreetMap
    python pipeline/01_study_area.py --hdx data/raw/bgd_admbnda_adm3.shp   # boundaries from HDX COD-AB

Writes data/processed/study_area.gpkg (EPSG:32646) and grid.json.
"""
import argparse
import difflib

import geopandas as gpd
import pandas as pd

from safewindow import config
from safewindow.flood import Grid

SUNAMGANJ_UPAZILAS = [
    "Bishwambharpur", "Chhatak", "Dakshin Sunamganj", "Derai", "Dharamapasha",
    "Dowarabazar", "Jagannathpur", "Jamalganj", "Madhyanagar", "Sullah",
    "Sunamganj Sadar", "Tahirpur",
]


def from_osm(name: str) -> gpd.GeoDataFrame:
    import osmnx as ox
    queries = [f"{name} Upazila, {config.DISTRICT} District, {config.COUNTRY}",
               f"{name} Upazila, {config.COUNTRY}", f"{name}, {config.DISTRICT}, {config.COUNTRY}"]
    for q in queries:
        try:
            gdf = ox.geocode_to_gdf(q)
            if gdf.geom_type.iloc[0] in ("Polygon", "MultiPolygon"):
                return gdf.assign(upazila=name)[["upazila", "geometry"]]
        except Exception:  # noqa: BLE001 - try the next spelling
            pass
    raise SystemExit(f"Could not find a boundary for {name!r} in OSM. Try --hdx instead.")


def from_hdx(path: str, names: list[str]) -> gpd.GeoDataFrame:
    adm = gpd.read_file(path)
    col = next((c for c in adm.columns if c.upper().startswith("ADM3_EN")), None)
    if col is None:
        raise SystemExit(f"No ADM3_EN column in {path}; is this the upazila (admin 3) layer?")
    dcol = next((c for c in adm.columns if c.upper().startswith("ADM2_EN")), None)
    if dcol:
        adm = adm[adm[dcol].str.lower() == config.DISTRICT.lower()]
    out = []
    for n in names:
        match = difflib.get_close_matches(n, adm[col].tolist(), n=1, cutoff=0.6)
        if not match:
            raise SystemExit(f"{n!r} not found. Available: {sorted(adm[col])}")
        print(f"  {n!r} -> {match[0]!r}")
        out.append(adm[adm[col] == match[0]].assign(upazila=n)[["upazila", "geometry"]])
    return pd.concat(out)


def rank():
    import osmnx as ox
    rows = []
    for name in SUNAMGANJ_UPAZILAS:
        try:
            poly = from_osm(name).to_crs(config.CRS)
            area_km2 = poly.area.sum() / 1e6
            g = ox.graph_from_polygon(poly.to_crs(config.CRS_WGS84).union_all(), network_type="all",
                                      retain_all=True)
            km = sum(d["length"] for *_, d in ox.convert.to_undirected(g).edges(data=True)) / 1000
            rows.append({"upazila": name, "area_km2": round(area_km2), "road_km": round(km),
                         "road_km_per_km2": round(km / area_km2, 2)})
            print(rows[-1])
        except SystemExit as e:
            print(e)
    df = pd.DataFrame(rows).sort_values("road_km_per_km2", ascending=False)
    print(df.to_string(index=False))
    out = config.get_paths().ensure().processed / "upazila_road_density.csv"
    df.to_csv(out, index=False)
    print(f"saved {out}. Pick 2-3 well-mapped upazilas and set config.UPAZILAS.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hdx", help="path to HDX COD-AB admin-3 (upazila) boundaries")
    ap.add_argument("--rank", action="store_true", help="rank upazilas by OSM road density")
    args = ap.parse_args()
    if args.rank:
        return rank()

    paths = config.get_paths().ensure()
    print(f"Study area upazilas: {config.UPAZILAS}")
    if args.hdx:
        sa = from_hdx(args.hdx, config.UPAZILAS)
    else:
        sa = pd.concat([from_osm(n) for n in config.UPAZILAS])
    sa = gpd.GeoDataFrame(sa, crs=sa.crs).to_crs(config.CRS)
    sa.to_file(paths.study_area, driver="GPKG")

    grid = Grid.from_bounds(*sa.total_bounds)
    grid.save(paths.grid)
    print(f"saved {paths.study_area} ({sa.area.sum() / 1e6:.0f} km2)")
    print(f"grid: {grid.width} x {grid.height} px at {grid.res} m -> {paths.grid}")


if __name__ == "__main__":
    main()
