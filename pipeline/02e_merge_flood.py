"""Step 2 (end) - merge all flood sources per date and run the go/no-go check.

    python pipeline/02e_merge_flood.py
    python pipeline/02e_merge_flood.py --sources sentinel1 unosat   # leave out estimates

For each date, pixels come from the best available source (config.SOURCE_PRIORITY);
lower sources only fill pixels still unknown. Writes data/processed/flood_merged/.

Go/No-Go (end of Week 1): at least 4 dates covering the rise, the peak and the
fall of the flood.
"""
import argparse

import pandas as pd

from safewindow import config
from safewindow.flood import merge_by_date


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sources", nargs="*", help="only use these sources")
    args = ap.parse_args()

    s = merge_by_date(sources=args.sources)
    if s.empty:
        raise SystemExit("No flood maps registered yet - run the 02a-02d steps first.")
    print(s.to_string(index=False))

    good = s[s["unknown_pct"] < 50].copy()
    good["date"] = pd.to_datetime(good["date"])
    peak = good.loc[good["flooded_pct"].idxmax(), "date"] if len(good) else None
    rise = (good["date"] < peak).any() if peak is not None else False
    fall = (good["date"] > peak).any() if peak is not None else False
    ok = len(good) >= 4 and rise and fall
    print(f"\nusable dates (<50% unknown): {len(good)}; peak {peak:%d %b} ; "
          f"before peak: {rise}; after peak: {fall}" if peak is not None else "\nno usable dates")
    print("GO/NO-GO:", "GO" if ok else
          "NO-GO - add MODIS (--register) and DEM estimates for daily coverage, and say so openly.")


if __name__ == "__main__":
    main()
