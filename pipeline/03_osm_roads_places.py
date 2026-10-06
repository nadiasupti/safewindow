"""Step 3 - Roads, villages and shelter candidates from OpenStreetMap.

    python pipeline/03_osm_roads_places.py

Writes to data/processed/:
  roads.graphml             full osmnx graph (projected), for QGIS / debugging
  road_nodes.gpkg, road_edges.gpkg   undirected network used by the engine
  villages.gpkg             OSM village / hamlet points (population added in 03b)
  shelters_candidates.csv   schools, health facilities, union parishad offices...

NEXT (by hand): copy shelters_candidates.csv to shelters_verified.csv, keep
15-30 real flood shelters for the demo area, set verified=yes and fill
`source` (upazila website, news report, healthsites.io...). Missing shelters
can be added as new rows with lat/lon.
"""
import argparse

import geopandas as gpd
import osmnx as ox
import pandas as pd

from safewindow import config
from safewindow.places import SHELTER_COLS, load_study_area

PLACE_TAGS = {"place": ["village", "hamlet", "isolated_dwelling", "neighbourhood", "quarter", "suburb", "town"]}
SHELTER_TAGS = {
    "amenity": ["school", "college", "university", "hospital", "clinic", "doctors",
                "townhall", "shelter", "community_centre"],
    "healthcare": True,
    "building": ["school", "hospital"],
    "emergency": ["assembly_point"],
    "social_facility": ["shelter"],
    "office": ["government"],
}


def first(v):
    return v[0] if isinstance(v, list) else v


def roads(poly_wgs84):
    print("downloading roads (network_type='all' so village paths are included)...")
    g = ox.graph_from_polygon(poly_wgs84, network_type="all", retain_all=True, truncate_by_edge=True)
    g = ox.project_graph(g, to_crs=config.CRS)
    paths = config.get_paths()
    ox.save_graphml(g, paths.roads_graph)

    nodes, edges = ox.convert.graph_to_gdfs(ox.convert.to_undirected(g))
    nodes = nodes.reset_index()[["osmid", "geometry"]].rename(columns={"osmid": "node_id"})
    edges = edges.reset_index()
    edges = gpd.GeoDataFrame({
        "edge_id": edges["u"].astype(str) + "-" + edges["v"].astype(str) + "-" + edges["key"].astype(str),
        "u": edges["u"].astype(str), "v": edges["v"].astype(str),
        "length_m": edges["length"].round(1),
        "highway": edges["highway"].map(first).astype(str),
        "name": edges.get("name", pd.Series(index=edges.index)).map(first),
    }, geometry=edges.geometry, crs=config.CRS)
    nodes["node_id"] = nodes["node_id"].astype(str)
    nodes.to_file(paths.road_nodes, driver="GPKG")
    edges.to_file(paths.road_edges, driver="GPKG")
    print(f"  {len(nodes)} junctions, {len(edges)} road segments, {edges['length_m'].sum() / 1000:.0f} km")
    print("  road types:", edges["highway"].value_counts().head(10).to_dict())


def to_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.to_crs(config.CRS)
    gdf["geometry"] = gdf.geometry.representative_point()
    return gdf


def villages(poly_wgs84):
    v = to_points(ox.features_from_polygon(poly_wgs84, PLACE_TAGS)).reset_index()
    out = gpd.GeoDataFrame({
        "village_id": "osm" + v["id"].astype(str),
        "name": v.get("name", pd.Series(index=v.index)).fillna(v.get("name:en")).fillna("(unnamed)"),
        "name_bn": v.get("name:bn", pd.Series(index=v.index)),
        "place": v["place"],
        "source": "OpenStreetMap",
    }, geometry=v.geometry, crs=config.CRS)
    out.to_file(config.get_paths().villages, driver="GPKG")
    print(f"  {len(out)} villages/hamlets: {out['place'].value_counts().to_dict()}")
    if len(out) < 50:
        print("  Few OSM villages - consider 03b_population.py --buildings (Google Open Buildings).")


def shelters(poly_wgs84):
    s = to_points(ox.features_from_polygon(poly_wgs84, SHELTER_TAGS)).reset_index().to_crs(config.CRS_WGS84)
    kind = pd.Series("", index=s.index)
    for col in ["amenity", "healthcare", "building", "emergency", "social_facility", "office"]:
        if col in s:
            kind = kind.where(kind != "", s[col].fillna("").astype(str).replace("yes", col))
    out = pd.DataFrame({
        "shelter_id": "osm" + s["id"].astype(str),
        "name": s.get("name", pd.Series(index=s.index)).fillna("(unnamed)"),
        "type": kind, "lat": s.geometry.y.round(6), "lon": s.geometry.x.round(6),
        "source": "OpenStreetMap", "verified": "", "notes": "",
    })[SHELTER_COLS]
    out.to_csv(config.get_paths().shelter_candidates, index=False)
    print(f"  {len(out)} shelter candidates: {out['type'].value_counts().head(8).to_dict()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--buffer-m", type=float, default=1000,
                    help="extend the area so roads to shelters just outside are kept")
    args = ap.parse_args()
    paths = config.get_paths().ensure()
    sa = load_study_area(paths)
    poly = sa.buffer(args.buffer_m).to_crs(config.CRS_WGS84).union_all()
    roads(poly)
    print("downloading villages...")
    villages(sa.to_crs(config.CRS_WGS84).union_all())
    print("downloading shelter candidates...")
    shelters(poly)
    print("Now hand-check shelters -> data/processed/shelters_verified.csv (see docstring).")


if __name__ == "__main__":
    main()
