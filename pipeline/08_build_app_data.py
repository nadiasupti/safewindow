"""Step 8 (prep) - Package results into small web-ready files for the app.

    python pipeline/08_build_app_data.py

Writes data/app/ (commit this folder; keep it well under 100 MB):
  meta.json                dates, sources per date, data label, defaults
  villages.geojson         village points + summary fields
  village_status.csv       status per observed date (main threshold)
  shelters.geojson, exit_routes.geojson, cut_roads.geojson
  flood/YYYYMMDD.png       flood overlay per date (blue flooded, grey unknown)
  rainfall_daily.csv, modis_flood_area.csv, sensitivity_summary.csv, validation.csv
"""
import json
import shutil

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject

from safewindow import config
from safewindow.flood import merged_dates, merged_path
from safewindow.places import load_shelters, load_villages
from safewindow.provenance import write_manifest
from safewindow.roads import load_network
from safewindow.validation import validate_app_dataset

MAX_PX = 2000
FLOOD_RGBA = (30, 110, 230, 170)
UNKNOWN_RGBA = (140, 140, 140, 90)


def flood_png(src_path, out_png) -> list:
    """Reproject a flood map to WGS84, colour it and return folium bounds."""
    import matplotlib.image as mpimg
    with rasterio.open(src_path) as src:
        scale = max(1, max(src.width, src.height) / MAX_PX)
        w, h = int(src.width / scale), int(src.height / scale)
        t, w, h = calculate_default_transform(src.crs, config.CRS_WGS84, src.width, src.height,
                                              *src.bounds, dst_width=w, dst_height=h)
        dst = np.full((h, w), config.UNKNOWN, dtype="uint8")
        # nodata=None: UNKNOWN (255) is a real class here, and must be resampled too
        reproject(rasterio.band(src, 1), dst, src_nodata=None, dst_transform=t,
                  dst_crs=config.CRS_WGS84, resampling=Resampling.mode)
    rgba = np.zeros((h, w, 4), dtype="uint8")
    rgba[dst == config.FLOODED] = FLOOD_RGBA
    rgba[dst == config.UNKNOWN] = UNKNOWN_RGBA
    out_png.parent.mkdir(parents=True, exist_ok=True)
    mpimg.imsave(out_png, rgba)
    west, north = t.c, t.f
    east, south = west + t.a * w, north + t.e * h
    return [[south, west], [north, east]]


def write_geojson(gdf: gpd.GeoDataFrame, path, simplify_m: float = 0):
    g = gdf.copy()
    if simplify_m:
        g["geometry"] = g.geometry.simplify(simplify_m)
    for c in g.columns:
        if pd.api.types.is_datetime64_any_dtype(g[c]):
            g[c] = g[c].dt.strftime("%Y-%m-%d")
    g.to_crs(config.CRS_WGS84).to_file(path, driver="GeoJSON", COORDINATE_PRECISION=5)


def main():
    paths = config.get_paths().ensure()
    app = paths.app
    if app.exists():
        shutil.rmtree(app)
    (app / "flood").mkdir(parents=True)

    dates = merged_dates(paths)
    bounds = {d: flood_png(merged_path(d, paths), app / "flood" / f"{d.replace('-', '')}.png") for d in dates}
    merged_summary = pd.read_csv(paths.merged_flood_dir / "summary.csv")

    summary = pd.read_csv(paths.village_summary, dtype={"village_id": str})
    snapped = pd.read_csv(paths.results / "villages_snapped.csv", dtype={"village_id": str})
    villages = load_villages(paths)
    villages = villages[["village_id", "geometry"] + (["name_bn"] if "name_bn" in villages else [])]
    v = villages.merge(summary, on="village_id").merge(
        snapped[["village_id", "snap_dist_m", "boat_dependent"]], on="village_id")
    write_geojson(v, app / "villages.geojson")

    vs = pd.read_csv(paths.village_status, dtype={"village_id": str})
    vs[vs["threshold"] == config.CUT_THRESHOLD].drop(columns="threshold").to_csv(app / "village_status.csv", index=False)

    write_geojson(load_shelters(paths)[["shelter_id", "name", "type", "source", "geometry"]], app / "shelters.geojson")
    write_geojson(gpd.read_file(paths.exit_routes), app / "exit_routes.geojson", simplify_m=5)

    _, edges = load_network(paths)
    rs = pd.read_csv(paths.road_status, dtype={"edge_id": str})
    col = f"status_{round(config.CUT_THRESHOLD * 100)}"
    cut = rs[rs[col] == "cut"][["date", "edge_id"]].merge(edges[["edge_id", "highway", "geometry"]], on="edge_id")
    write_geojson(gpd.GeoDataFrame(cut, geometry="geometry", crs=config.CRS), app / "cut_roads.geojson", simplify_m=10)

    for src, name in [(paths.rainfall, "rainfall_daily.csv"), (paths.modis_timeline, "modis_flood_area.csv"),
                      (paths.results / "sensitivity_summary.csv", "sensitivity_summary.csv"),
                      (paths.validation_results, "validation.csv")]:
        if src.exists():
            shutil.copy(src, app / name)

    meta = {
        "data_label": (paths.data / "DATA_LABEL").read_text().strip() if (paths.data / "DATA_LABEL").exists() else "",
        "dates": dates,
        "flood_bounds": bounds,
        "sources": dict(zip(merged_summary["date"], merged_summary["sources"])),
        "unknown_pct": dict(zip(merged_summary["date"], merged_summary["unknown_pct"])),
        "cut_threshold": config.CUT_THRESHOLD,
        "default_supply_days": config.DEFAULT_SUPPLY_DAYS,
        "supply_days_range": list(config.SUPPLY_DAYS_RANGE),
        "app_start": str(config.APP_START), "app_end": str(config.APP_END),
    }
    (app / "meta.json").write_text(json.dumps(meta, indent=2))

    size = sum(f.stat().st_size for f in app.rglob("*") if f.is_file()) / 1e6
    print(f"app data written to {app} ({size:.1f} MB)")
    if size > 90:
        print("WARNING: close to GitHub's 100 MB limit - raise simplify_m or drop cut_roads.geojson")

    write_manifest(paths.data)
    validation = validate_app_dataset(app)
    if not validation["valid"]:
        raise RuntimeError("Generated app data failed validation: " + "; ".join(validation["errors"]))
    print(f"validated app package: {validation['files']} files")


if __name__ == "__main__":
    main()
