"""Step 4 - Daily rainfall from NASA GPM IMERG (Final Run, V07) via Earth Engine.

    python pipeline/04_rainfall_gpm.py

Two boxes (config.RAIN_BOXES):
  sunamganj           rain falling on the study area
  meghalaya_upstream  the Cherrapunji hills - most Sunamganj flood water comes
                      from here, so this series matters more
Days are Bangladesh local days (UTC+6). Values are box-average mm/day.
Writes data/processed/rainfall_daily.csv (date, <box>_mm ...).
"""
import argparse

import pandas as pd

from safewindow import config, gee

COLLECTION = "NASA/GPM_L3/IMERG_V07"
UTC_OFFSET_H = 6


def daily_series(ee, box, start: str, n_days: int) -> list[float]:
    region = ee.Geometry.Rectangle(list(box))
    col = ee.ImageCollection(COLLECTION).select("precipitation")   # mm/hr, every 30 min
    t0 = ee.Date(start).advance(-UTC_OFFSET_H, "hour")

    def one_day(i):
        d = t0.advance(i, "day")
        img = col.filterDate(d, d.advance(1, "day")).sum().multiply(0.5)   # mm/hr * 0.5 h
        return img.reduceRegion(ee.Reducer.mean(), region, scale=10000).get("precipitation")

    return ee.List.sequence(0, n_days - 1).map(one_day).getInfo()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2022-05-15")
    ap.add_argument("--end", default="2022-07-05")
    args = ap.parse_args()

    ee = gee.init()
    days = pd.date_range(args.start, args.end, freq="D")
    df = pd.DataFrame({"date": days.strftime("%Y-%m-%d")})
    for name, box in config.RAIN_BOXES.items():
        print(f"{name} {box} ...")
        df[f"{name}_mm"] = [round(v, 1) if v is not None else None
                            for v in daily_series(ee, box, args.start, len(days))]
    paths = config.get_paths().ensure()
    df.to_csv(paths.rainfall, index=False)
    print(df.describe().round(1))
    print(f"saved {paths.rainfall}")


if __name__ == "__main__":
    main()
