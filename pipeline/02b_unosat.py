"""Step 2 / Source B - UNOSAT ready-made flood maps (event FL20220525BGD).

Download the flood-extent shapefiles from HDX (search "UNOSAT Bangladesh
flood 2022"), then register each one with the date of the satellite image it
was made from (stated in the UNOSAT map / metadata, NOT the publish date):

    python pipeline/02b_unosat.py data/raw/unosat/FL20220525BGD_SHP_0619.shp --date 2022-06-19
    python pipeline/02b_unosat.py <flood.shp> --date 2022-06-21 --aoi <analysis_extent.shp>

Pixels inside a flood polygon become FLOODED. Pixels inside the analysed
area but outside the polygons become DRY. Everything else is UNKNOWN.
UNOSAT shapefiles often contain only the water polygons, so pass --aoi with the
image footprint if you have it; otherwise the whole study area is assumed to
have been analysed (check this against the map PDF).

Also prints agreement with the Sentinel-1 map of the same date, if there is one.
"""
import argparse

import geopandas as gpd
import numpy as np
from rasterio.features import rasterize

from safewindow import config
from safewindow.flood import Grid, load_manifest, read_onto_grid, register_flood_map
from safewindow.places import load_study_area


def burn(gdf: gpd.GeoDataFrame, grid: Grid) -> np.ndarray:
    gdf = gdf.to_crs(grid.crs)
    shapes = [(g, 1) for g in gdf.geometry if g is not None and not g.is_empty]
    return rasterize(shapes, out_shape=(grid.height, grid.width), transform=grid.transform,
                     fill=0, dtype="uint8") if shapes else np.zeros((grid.height, grid.width), "uint8")


def agreement(a: np.ndarray, b: np.ndarray) -> dict:
    both = (a != config.UNKNOWN) & (b != config.UNKNOWN)
    fa, fb = a[both] == config.FLOODED, b[both] == config.FLOODED
    inter, union = (fa & fb).sum(), (fa | fb).sum()
    return {"overlap_px": int(both.sum()), "same_class_pct": round(100 * (fa == fb).mean(), 1) if both.any() else None,
            "flood_IoU": round(inter / union, 3) if union else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shapefile")
    ap.add_argument("--date", required=True, help="satellite acquisition date YYYY-MM-DD")
    ap.add_argument("--aoi", help="polygon of the area UNOSAT analysed (optional)")
    args = ap.parse_args()

    paths = config.get_paths().ensure()
    grid = Grid.load(paths.grid)
    water = burn(gpd.read_file(args.shapefile), grid)
    analysed = burn(gpd.read_file(args.aoi) if args.aoi else load_study_area(paths), grid)

    arr = np.full(water.shape, config.UNKNOWN, dtype="uint8")
    arr[analysed == 1] = config.DRY
    arr[water == 1] = config.FLOODED
    register_flood_map(args.date, "unosat", arr, grid, note=f"from {args.shapefile}", paths=paths)
    print(f"{args.date}: flooded {(arr == config.FLOODED).mean() * 100:.1f}% of grid")

    m = load_manifest(paths)
    s1 = m[(m["date"] == args.date) & (m["source"] == "sentinel1")]
    if len(s1):
        print("agreement with Sentinel-1 on the same date:",
              agreement(arr, read_onto_grid(paths.data / s1.iloc[0]["path"], grid)))


if __name__ == "__main__":
    main()
