"""Step 2 / Source A - Sentinel-1 radar flood maps in Google Earth Engine.

Method (after the UN-SPIDER Recommended Practice for Sentinel-1 flood mapping):
  1. Sentinel-1 GRD, IW mode, VV polarisation, over the study area.
  2. Dry-season reference: median of Feb-Mar 2022 from the same relative orbit.
  3. Light speckle filter (30 m focal median).
  4. Flooded = VV below an Otsu threshold (very dark) AND at least 3 dB darker
     than the dry reference (new water, so permanent rivers under bridges are
     not counted as cutting roads).
  5. Steep slopes (> 5 deg, radar shadow) are set to dry. Areas without
     coverage on that date stay UNKNOWN.

    python pipeline/02a_sentinel1_gee.py --list          # list available dates first
    python pipeline/02a_sentinel1_gee.py                 # map every date
    python pipeline/02a_sentinel1_gee.py --dates 2022-06-17 2022-06-29

Needs: `earthengine authenticate` and EE_PROJECT (see safewindow/gee.py).
Saves an Otsu histogram PNG per date in data/processed/flood/otsu/ as proof.
"""
import argparse

import numpy as np
import pandas as pd

from safewindow import config, gee
from safewindow.flood import Grid, read_onto_grid, register_flood_map

DIFF_DB = -3.0          # must be this much darker than the dry season
SLOPE_MAX_DEG = 5
FALLBACK_THRESHOLD = -18.0


def otsu(counts: np.ndarray, centers: np.ndarray) -> float:
    """Threshold that maximises between-class variance of a histogram."""
    total = counts.sum()
    w0 = np.cumsum(counts)
    w1 = total - w0
    m0 = np.cumsum(counts * centers)
    mean0 = np.divide(m0, w0, out=np.zeros_like(m0), where=w0 > 0)
    mean1 = np.divide(m0[-1] - m0, w1, out=np.zeros_like(m0), where=w1 > 0)
    between = w0 * w1 * (mean0 - mean1) ** 2
    return float(centers[np.argmax(between)])


def save_histogram(counts, centers, threshold, day, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(centers, counts, width=centers[1] - centers[0], color="#4a7db3")
    ax.axvline(threshold, color="#c0392b", lw=2, label=f"Otsu threshold {threshold:.1f} dB")
    ax.set(xlabel="Sentinel-1 VV backscatter (dB)", ylabel="pixels", title=f"Sentinel-1 VV histogram, {day}")
    ax.legend()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)


def collection(ee, aoi):
    return (ee.ImageCollection("COPERNICUS/S1_GRD")
            .filterBounds(aoi)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .select("VV"))


def list_dates(ee, aoi) -> pd.DataFrame:
    col = collection(ee, aoi).filterDate(str(config.FLOOD_START), str(config.FLOOD_END))
    info = col.reduceColumns(ee.Reducer.toList(3), ["system:time_start", "relativeOrbitNumber_start",
                                                     "orbitProperties_pass"]).get("list").getInfo()
    df = pd.DataFrame(info, columns=["t", "relative_orbit", "pass"])
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.strftime("%Y-%m-%d")
    return (df.groupby("date").agg(relative_orbit=("relative_orbit", "first"), passes=("pass", "first"),
                                   scenes=("t", "size")).reset_index())


def flood_map(ee, aoi, day: str, rel_orbit: int, hist_out):
    s1 = collection(ee, aoi)
    start = ee.Date(day)
    flood_img = s1.filterDate(start, start.advance(1, "day")).mosaic().focal_median(30, "circle", "meters")

    dry_col = s1.filterDate(config.DRY_REF_START, config.DRY_REF_END)
    same_orbit = dry_col.filter(ee.Filter.eq("relativeOrbitNumber_start", int(rel_orbit)))
    dry = ee.Image(ee.Algorithms.If(same_orbit.size().gt(0), same_orbit.median(), dry_col.median()))
    dry = dry.focal_median(30, "circle", "meters")

    hist = flood_img.reduceRegion(ee.Reducer.histogram(maxBuckets=200, minBucketWidth=0.25),
                                  aoi, scale=60, bestEffort=True).get("VV").getInfo()
    if hist and sum(hist["histogram"]) > 1000:
        counts = np.array(hist["histogram"], float)
        centers = np.array(hist["bucketMeans"], float)
        t = otsu(counts, centers)
        if not -26 <= t <= -12:   # unimodal histogram -> Otsu is meaningless
            print(f"  Otsu gave {t:.1f} dB (implausible), using {FALLBACK_THRESHOLD} dB")
            t = FALLBACK_THRESHOLD
        save_histogram(counts, centers, t, day, hist_out)
    else:
        t = FALLBACK_THRESHOLD
        print(f"  too few pixels for a histogram, using {t} dB")

    slope = ee.Terrain.slope(ee.Image("NASA/NASADEM_HGT/001").select("elevation"))
    flooded = flood_img.lt(t).And(flood_img.subtract(dry).lt(DIFF_DB)).And(slope.lte(SLOPE_MAX_DEG))
    # keep the radar's own mask so areas outside the swath stay UNKNOWN
    cls = flooded.updateMask(flood_img.mask()).toByte()
    return cls.unmask(config.UNKNOWN).toByte(), t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="only list available image dates")
    ap.add_argument("--dates", nargs="*", help="only these dates (YYYY-MM-DD)")
    args = ap.parse_args()

    ee = gee.init()
    paths = config.get_paths().ensure()
    grid = Grid.load(paths.grid)
    aoi = gee.study_area_geometry(paths)

    dates = list_dates(ee, aoi)
    print(dates.to_string(index=False))
    if args.list:
        return
    if args.dates:
        dates = dates[dates["date"].isin(args.dates)]

    log = []
    for day, orbit in dates[["date", "relative_orbit"]].itertuples(index=False):
        print(f"{day}: orbit {orbit}")
        img, t = flood_map(ee, aoi, day, orbit, paths.flood_dir / "otsu" / f"otsu_{day}.png")
        tmp = gee.download_to_grid(img, grid, paths.raw / "sentinel1" / f"s1_{day}.tif", f"s1_{day}")
        arr = read_onto_grid(tmp, grid)
        register_flood_map(day, "sentinel1", arr, grid, note=f"otsu={t:.2f}dB orbit={orbit}", paths=paths)
        share = (arr == config.FLOODED).mean() * 100
        print(f"  threshold {t:.1f} dB, flooded {share:.1f}% of grid")
        log.append({"date": day, "relative_orbit": orbit, "otsu_db": round(t, 2), "flooded_pct": round(share, 2)})
    pd.DataFrame(log).to_csv(paths.flood_dir / "sentinel1_log.csv", index=False)


if __name__ == "__main__":
    main()
