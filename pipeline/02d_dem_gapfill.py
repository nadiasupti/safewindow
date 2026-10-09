"""Step 2 / Source D (optional) - fill days between satellite images with an
elevation-based ESTIMATE.

  1. On each date with a Sentinel-1 or UNOSAT map, find the flood edge
     (flooded pixels next to dry ones) and take the median ground height there
     as that day's water level.
  2. For days in between, draw a straight line between the known levels.
  3. A pixel is flooded if its ground height is below that day's level.

    python pipeline/02d_dem_gapfill.py --download   # Copernicus DEM 30 m via Earth Engine (once)
    python pipeline/02d_dem_gapfill.py              # estimate missing days

This is a "bathtub" estimate: it ignores embankments and whether low ground is
actually connected to the river, and a 30 m DEM has metre-level errors on flat
floodplain. Say clearly in the app and pitch that these days are estimates.
"""
import argparse
from datetime import timedelta

import numpy as np
import pandas as pd
import rasterio

from safewindow import config
from safewindow.flood import Grid, load_manifest, read_onto_grid, register_flood_map

OBSERVED_SOURCES = ["sentinel1", "unosat"]


def edge_pixels(flood: np.ndarray) -> np.ndarray:
    """Flooded pixels with at least one dry 4-neighbour."""
    f, d = flood == config.FLOODED, flood == config.DRY
    nb_dry = np.zeros_like(d)
    nb_dry[1:, :] |= d[:-1, :]
    nb_dry[:-1, :] |= d[1:, :]
    nb_dry[:, 1:] |= d[:, :-1]
    nb_dry[:, :-1] |= d[:, 1:]
    return f & nb_dry


def download(paths, grid):
    from safewindow import gee
    ee = gee.init()
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic().toFloat()
    gee.download_to_grid(dem, grid, paths.processed / "dem.tif", "dem",
                         region=gee.study_area_geometry(paths), dtype="float32", nodata=-9999)
    print(f"saved {paths.processed / 'dem.tif'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()
    paths = config.get_paths().ensure()
    grid = Grid.load(paths.grid)
    if args.download:
        return download(paths, grid)

    with rasterio.open(paths.processed / "dem.tif") as src:
        dem = src.read(1).astype("float32")

    m = load_manifest(paths)
    obs = m[m["source"].isin(OBSERVED_SOURCES)]
    levels = []
    for day, grp in obs.groupby("date"):
        merged = np.full(dem.shape, config.UNKNOWN, dtype="uint8")
        for p in grp["path"]:
            a = read_onto_grid(paths.data / p, grid)
            merged[merged == config.UNKNOWN] = a[merged == config.UNKNOWN]
        edges = edge_pixels(merged)
        if edges.sum() < 100:
            print(f"{day}: too few flood-edge pixels, skipped")
            continue
        levels.append({"date": pd.Timestamp(day), "water_level_m": float(np.median(dem[edges])),
                       "edge_px": int(edges.sum())})
    if len(levels) < 2:
        raise SystemExit("Need at least two observed dates to interpolate.")
    lv = pd.DataFrame(levels).set_index("date")
    print(lv)

    daily = lv["water_level_m"].resample("D").asfreq().interpolate("linear")
    daily.to_csv(paths.processed / "water_levels_daily.csv")
    observed_days = set(lv.index)
    for day, level in daily.items():
        if day in observed_days:
            continue
        arr = np.where(dem <= level, config.FLOODED, config.DRY).astype("uint8")
        arr[~np.isfinite(dem)] = config.UNKNOWN
        register_flood_map(day.strftime("%Y-%m-%d"), "dem_estimate", arr, grid,
                           note=f"bathtub estimate, level {level:.2f} m", paths=paths)
    print(f"estimated {len(daily) - len(observed_days)} days between "
          f"{daily.index.min():%d %b} and {daily.index.max():%d %b}")


if __name__ == "__main__":
    main()
