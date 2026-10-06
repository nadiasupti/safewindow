"""Step 3 (population) - add a population estimate to every village.

    python pipeline/03b_population.py --worldpop-gee            # WorldPop 100 m via Earth Engine
    python pipeline/03b_population.py --worldpop data/raw/bgd_ppp_2020.tif   # or a local download
    python pipeline/03b_population.py --worldpop-gee --buildings   # villages from Google Open Buildings

Each village gets the area that is closer to it than to any other village
(Voronoi cell, clipped to the study area). Its population is the WorldPop sum
inside that cell, so no person is counted twice.

--buildings: if OSM has too few villages, replace them with clusters of
Google Open Buildings (DBSCAN, 60 m). Each cluster is a settlement, named after
the nearest OSM village within 1 km when there is one.
"""
import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.features import rasterize

from safewindow import config
from safewindow.flood import Grid
from safewindow.places import load_study_area, load_villages

WORLDPOP_RES = 100


def worldpop_from_gee(paths, sa):
    from safewindow import gee
    ee = gee.init()
    grid = Grid.from_bounds(*sa.total_bounds, res=WORLDPOP_RES)
    img = (ee.ImageCollection("WorldPop/GP/100m/pop").filter(ee.Filter.eq("country", "BGD"))
           .filter(ee.Filter.eq("year", 2020)).first().select("population").unmask(0).toFloat())
    return gee.download_to_grid(img, grid, paths.raw / "worldpop_2020.tif", "worldpop")


def buildings_from_gee(paths, sa) -> pd.DataFrame:
    from safewindow import gee
    ee = gee.init()
    aoi = gee.study_area_geometry(paths)
    fc = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
          .filterBounds(aoi).filter(ee.Filter.gte("confidence", 0.75))
          .map(lambda f: ee.Feature(None, {"lon": f.geometry().centroid(1).coordinates().get(0),
                                           "lat": f.geometry().centroid(1).coordinates().get(1)})))
    url = fc.getDownloadURL(filetype="csv", selectors=["lon", "lat"])
    df = pd.read_csv(url)
    df.to_csv(paths.raw / "open_buildings_centroids.csv", index=False)
    print(f"  {len(df)} buildings")
    return df


def cluster_buildings(df: pd.DataFrame, osm_villages: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    from sklearn.cluster import DBSCAN
    pts = gpd.GeoSeries(gpd.points_from_xy(df["lon"], df["lat"]), crs=config.CRS_WGS84).to_crs(config.CRS)
    xy = np.column_stack([pts.x, pts.y])
    labels = DBSCAN(eps=60, min_samples=10).fit_predict(xy)
    keep = labels >= 0
    c = (pd.DataFrame({"x": xy[keep, 0], "y": xy[keep, 1], "lab": labels[keep]})
         .groupby("lab").agg(x=("x", "mean"), y=("y", "mean"), n_buildings=("x", "size")).reset_index())
    out = gpd.GeoDataFrame(c, geometry=gpd.points_from_xy(c["x"], c["y"]), crs=config.CRS)
    near = gpd.sjoin_nearest(out, osm_villages[["name", "name_bn", "geometry"]], how="left",
                             max_distance=1000, distance_col="d")
    near = near[~near.index.duplicated()]
    out["name"] = near["name"].fillna(pd.Series([f"Settlement {i + 1}" for i in range(len(out))], index=out.index))
    out["name_bn"] = near["name_bn"]
    out["village_id"] = [f"ob{i + 1:05d}" for i in range(len(out))]
    out["place"], out["source"] = "building_cluster", "Google Open Buildings v3"
    print(f"  {len(out)} settlements from {keep.sum()} clustered buildings ({(~keep).sum()} scattered)")
    return out[["village_id", "name", "name_bn", "place", "source", "n_buildings", "geometry"]]


def voronoi_cells(villages: gpd.GeoDataFrame, area) -> gpd.GeoSeries:
    pts = shapely.MultiPoint(villages.geometry.to_list())
    cells = shapely.voronoi_polygons(pts, extend_to=area.envelope.buffer(5000))
    cells = gpd.GeoDataFrame(geometry=list(cells.geoms), crs=config.CRS)
    # Voronoi output order is not guaranteed; match each cell back to its point
    j = gpd.sjoin(gpd.GeoDataFrame(geometry=villages.geometry.reset_index(drop=True), crs=config.CRS),
                  cells, predicate="within", how="left")
    j = j[~j.index.duplicated()]
    return cells.geometry.iloc[j["index_right"].to_numpy()].intersection(area).reset_index(drop=True)


def population(villages: gpd.GeoDataFrame, area, raster_path) -> np.ndarray:
    cells = voronoi_cells(villages, area)
    with rasterio.open(raster_path) as src:
        pop = src.read(1).astype("float64")
        pop[(pop < 0) | ~np.isfinite(pop)] = 0
        cells = cells.to_crs(src.crs)
        ids = rasterize([(g, i + 1) for i, g in enumerate(cells) if not g.is_empty],
                        out_shape=pop.shape, transform=src.transform, fill=0, dtype="int32")
    sums = np.bincount(ids.ravel(), weights=pop.ravel(), minlength=len(villages) + 1)
    return np.round(sums[1:]).astype(int)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worldpop", help="local WorldPop GeoTIFF")
    ap.add_argument("--worldpop-gee", action="store_true")
    ap.add_argument("--buildings", action="store_true")
    args = ap.parse_args()
    paths = config.get_paths().ensure()
    sa = load_study_area(paths)
    area = sa.union_all()
    villages = load_villages(paths)

    if args.buildings:
        villages = cluster_buildings(buildings_from_gee(paths, sa), villages)

    raster = args.worldpop or (worldpop_from_gee(paths, sa) if args.worldpop_gee else None)
    if raster is None:
        raise SystemExit("Pass --worldpop PATH or --worldpop-gee")
    villages["population"] = population(villages, area, raster)
    villages.to_file(paths.villages, driver="GPKG")
    print(f"total population in villages' areas: {villages['population'].sum():,}")
    print(villages.sort_values("population", ascending=False)[["name", "population"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
