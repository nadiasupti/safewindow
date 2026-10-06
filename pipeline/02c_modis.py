"""Step 2 / Source C - NASA MODIS Global Flood Product (daily, 250 m).

Downloads the MODIS flood product (MCDWD) for every day of the flood window
via earthaccess (NASA Earthdata login), clips it to the study area and writes
  data/processed/modis_flood_area.csv   daily flooded km2 + % unknown (the regional trend)
and, with --register, also adds each day as a low-priority flood map that
only fills pixels no better source covers.

    python pipeline/02c_modis.py                       # trend table only
    python pipeline/02c_modis.py --register            # also use as gap-filler
    python pipeline/02c_modis.py --find                # list MCDWD collections if the default name fails

Layer: the 3-day composite by default (fewer cloud gaps, see guide). Pixel
codes: 0 no water, 1 normal surface water, 2 recurring flood, 3 flood,
255 insufficient data (cloud). Codes 2 and 3 count as FLOODED, 0 and 1 as DRY,
and 255 stays UNKNOWN - cloud is never treated as dry.

Login: earthaccess asks for your Earthdata username/password the first time
(or set EARTHDATA_USERNAME / EARTHDATA_PASSWORD, or a ~/.netrc entry).

NOTE: the reader handles GeoTIFF and HDF files whose sub-dataset names contain
the layer name. Check the first downloaded file in QGIS; if the product layout
differs, adjust `open_layer` below.
"""
import argparse
from datetime import timedelta

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, reproject

from safewindow import config
from safewindow.flood import Grid, register_flood_map
from safewindow.places import load_study_area

FLOOD_CODES, DRY_CODES, NODATA_CODE = (2, 3), (0, 1), 255


def open_layer(path: str, layer: str):
    """Return an open rasterio dataset for the requested layer."""
    ds = rasterio.open(path)
    if not ds.subdatasets:
        return ds
    match = [s for s in ds.subdatasets if layer.lower() in s.lower()]
    ds.close()
    if not match:
        raise RuntimeError(f"layer {layer!r} not in {path}. Sub-datasets: {ds.subdatasets}")
    return rasterio.open(match[0])


def to_classes(path: str, grid: Grid, layer: str) -> np.ndarray:
    raw = np.full((grid.height, grid.width), NODATA_CODE, dtype="uint8")
    with open_layer(path, layer) as src:
        reproject(rasterio.band(src, 1), raw, dst_transform=grid.transform, dst_crs=grid.crs,
                  dst_nodata=NODATA_CODE, resampling=Resampling.nearest)
    out = np.full(raw.shape, config.UNKNOWN, dtype="uint8")
    out[np.isin(raw, DRY_CODES)] = config.DRY
    out[np.isin(raw, FLOOD_CODES)] = config.FLOODED
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--short-name", default="MCDWD_L3", help="Earthdata collection short name")
    ap.add_argument("--layer", default="Flood 3-Day 250m")
    ap.add_argument("--register", action="store_true", help="add each day as a flood map")
    ap.add_argument("--find", action="store_true")
    args = ap.parse_args()

    import earthaccess
    earthaccess.login()
    if args.find:
        for c in earthaccess.search_datasets(keyword="MCDWD"):
            print(c.summary()["short-name"], "-", c["umm"].get("EntryTitle", ""))
        return

    paths = config.get_paths().ensure()
    grid = Grid.load(paths.grid)
    sa = load_study_area(paths)
    bbox = tuple(sa.to_crs(config.CRS_WGS84).total_bounds)
    from rasterio.features import rasterize
    inside = rasterize([(g, 1) for g in sa.geometry], out_shape=(grid.height, grid.width),
                       transform=grid.transform, fill=0, dtype="uint8").astype(bool)
    px_km2 = grid.res ** 2 / 1e6

    rows, day = [], config.FLOOD_START
    while day <= config.FLOOD_END:
        d = day.isoformat()
        granules = earthaccess.search_data(short_name=args.short_name, temporal=(d, d), bounding_box=bbox)
        if not granules:
            print(f"{d}: no granule (try --find for the right collection name)")
        else:
            files = earthaccess.download(granules, str(paths.raw / "modis" / d))
            arr = np.full((grid.height, grid.width), config.UNKNOWN, dtype="uint8")
            for f in files:   # several tiles may touch the study area
                part = to_classes(str(f), grid, args.layer)
                arr[part != config.UNKNOWN] = part[part != config.UNKNOWN]
            a = arr[inside]
            rows.append({"date": d, "flooded_km2": round((a == config.FLOODED).sum() * px_km2, 1),
                         "unknown_pct": round(100 * (a == config.UNKNOWN).mean(), 1)})
            print(rows[-1])
            if args.register:
                register_flood_map(d, "modis", arr, grid, note=args.layer, paths=paths)
        day += timedelta(days=1)

    pd.DataFrame(rows).to_csv(paths.modis_timeline, index=False)
    print(f"saved {paths.modis_timeline}")


if __name__ == "__main__":
    main()
