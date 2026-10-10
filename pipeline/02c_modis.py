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
import os
from datetime import timedelta

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject

from safewindow import config, gee
from safewindow.flood import Grid, load_manifest, read_onto_grid, register_flood_map
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


def process_earth_engine_modis(ee, paths, grid, start: str, end: str,
                               baseline_start: str, baseline_end: str) -> None:
    """Register MOD09GA NDWI increase as an optical inundation proxy.

    MOD09GA is surface reflectance, not a flood-class product. This method
    compares cloud-masked NDWI against a dry-season baseline and records the
    result as a low-priority proxy, not ground truth.
    """
    aoi = gee.study_area_geometry(paths)
    collection = (ee.ImageCollection("MODIS/061/MOD09GA")
                  .filterBounds(aoi))

    def clear_reflectance(date_start: str, date_end: str):
        images = collection.filterDate(date_start, date_end)

        def mask_clouds(image):
            qa = image.select("state_1km")
            clear = qa.bitwiseAnd(3).eq(0).And(qa.bitwiseAnd(1 << 2).eq(0))
            return image.select(["sur_refl_b04", "sur_refl_b02"]).updateMask(clear)

        return images.map(mask_clouds).median().clip(aoi)

    baseline = clear_reflectance(baseline_start, baseline_end)
    baseline_ndwi = (baseline.select("sur_refl_b04").subtract(baseline.select("sur_refl_b02"))
                     .divide(baseline.select("sur_refl_b04").add(baseline.select("sur_refl_b02"))))
    manifest = load_manifest(paths)
    observed = manifest[(manifest["source"] == "sentinel1") &
                        (manifest["date"] >= start) & (manifest["date"] <= end)]
    days = ([pd.Timestamp(value) for value in sorted(observed["date"].unique())]
            if not observed.empty else list(pd.date_range(start, end, freq="D")))
    sa = load_study_area(paths)
    modis_grid = Grid.from_bounds(*sa.to_crs(config.CRS).total_bounds, res=500, pad=0)
    inside = rasterize([(geom, 1) for geom in sa.geometry],
                       out_shape=(grid.height, grid.width), transform=grid.transform,
                       fill=0, dtype="uint8").astype(bool)
    rows = []
    for day in days:
        day_text = day.strftime("%Y-%m-%d")
        daily = clear_reflectance(day_text, (day + timedelta(days=1)).strftime("%Y-%m-%d"))
        green, nir = daily.select("sur_refl_b04"), daily.select("sur_refl_b02")
        ndwi = green.subtract(nir).divide(green.add(nir))
        valid = ndwi.mask().And(baseline_ndwi.mask())
        newly_inundated = ndwi.gt(0.15).And(baseline_ndwi.lte(0.15))
        classified = (ee.Image.constant(config.UNKNOWN)
                      .where(newly_inundated, config.FLOODED)
                      .where(valid.And(newly_inundated.Not()), config.DRY)
                      .updateMask(valid).unmask(config.UNKNOWN).rename("flood").toByte().clip(aoi))
        output = paths.raw / "modis" / f"modis_{day_text}_500m.tif"
        gee.download_to_grid(classified, modis_grid, output, f"modis_{day_text}",
                             region=aoi, dtype="uint8", nodata=config.UNKNOWN)
        arr = read_onto_grid(output, grid)
        register_flood_map(day_text, "modis", arr, grid,
                           note=(f"MOD09GA NDWI > 0.15 increase vs {baseline_start}..{baseline_end}; "
                                 "optical inundation proxy, not ground truth"), paths=paths)
        values = arr[inside]
        rows.append({"date": day_text,
                     "flooded_km2": round((values == config.FLOODED).sum() * grid.res ** 2 / 1e6, 1),
                     "unknown_pct": round(100 * (values == config.UNKNOWN).mean(), 1),
                     "metric": "MOD09GA NDWI increase proxy; resampled to 20 m grid"})
        print(f"{day_text}: registered MOD09GA proxy; unknown={rows[-1]['unknown_pct']:.1f}%")
    pd.DataFrame(rows).to_csv(paths.modis_timeline, index=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--short-name", default="MCDWD_L3", help="Earthdata collection short name")
    ap.add_argument("--layer", default="Flood 3-Day 250m")
    ap.add_argument("--register", action="store_true", help="add each day as a flood map")
    ap.add_argument("--find", action="store_true")
    ap.add_argument("--ee-check", action="store_true", help="check MODIS in Earth Engine without Earthdata login")
    ap.add_argument("--ee-process", action="store_true", help="register cloud-masked MOD09GA water-change proxy")
    ap.add_argument("--baseline-start", default=config.DRY_REF_START)
    ap.add_argument("--baseline-end", default=config.DRY_REF_END)
    ap.add_argument("--start", default=config.FLOOD_START.isoformat(), help="first date to download")
    ap.add_argument("--end", default=config.FLOOD_END.isoformat(), help="last date to download")
    args = ap.parse_args()

    paths = config.get_paths().ensure()
    if args.ee_check or args.ee_process:
        ee = gee.init()
        aoi = gee.study_area_geometry(paths)
        end_exclusive = (pd.Timestamp(args.end) + timedelta(days=1)).strftime("%Y-%m-%d")
        collection = (ee.ImageCollection("MODIS/061/MOD09GA")
                      .filterBounds(aoi)
                      .filterDate(args.start, end_exclusive))
        print(f"MODIS_EE_COUNT={collection.size().getInfo()}")
        print(f"MODIS_EE_COLLECTION=MODIS/061/MOD09GA")
        print(f"MODIS_EE_DATE_RANGE={args.start}..{args.end}")
        if args.ee_process:
            grid = Grid.load(paths.grid)
            process_earth_engine_modis(ee, paths, grid, args.start, args.end,
                                       args.baseline_start, args.baseline_end)
        return

    import earthaccess
    username = os.environ.get("EARTHDATA_USERNAME")
    password = os.environ.get("EARTHDATA_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "Earthdata credentials are required. Set EARTHDATA_USERNAME and "
            "EARTHDATA_PASSWORD, or use a valid ~/.netrc entry."
        )
    earthaccess.login(strategy="environment")
    if args.find:
        for c in earthaccess.search_datasets(keyword="MCDWD"):
            summary = c.summary
            print(summary["short-name"], "-", summary.get("EntryTitle", ""))
        return


    grid = Grid.load(paths.grid)
    sa = load_study_area(paths)
    bbox = tuple(sa.to_crs(config.CRS_WGS84).total_bounds)
    from rasterio.features import rasterize
    inside = rasterize([(g, 1) for g in sa.geometry], out_shape=(grid.height, grid.width),
                       transform=grid.transform, fill=0, dtype="uint8").astype(bool)
    px_km2 = grid.res ** 2 / 1e6

    rows, day = [], pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    while day <= end:
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
