"""Build a current SafeWindow dataset from live public sources.

Run after configuring Earth Engine and Earthdata credentials:

    earthengine authenticate
    $env:EE_PROJECT="your-project-id"
    python pipeline/10_build_live_data.py

The generated files are written to data/live. The app uses this directory by
default; data_demo remains available with SAFEWINDOW_DATA_DIR=data_demo.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from safewindow import config

ROOT = Path(__file__).resolve().parent.parent
STEPS = [
    ("01_study_area.py", []),
    ("03_osm_roads_places.py", []),
    ("04_rainfall_gpm.py", []),
    ("02c_modis.py", ["--register"]),
    ("02a_sentinel1_gee.py", []),
    ("02e_merge_flood.py", []),
    ("05_cut_roads.py", []),
    ("06_isolation.py", []),
    ("07_timeline.py", []),
    ("09_validate.py", []),
    ("08_build_app_data.py", []),
]


def run(command: list[str]) -> None:
    print(f"\n== {command[0]} ==", flush=True)
    result = subprocess.run(command, cwd=ROOT, env=os.environ)
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=14, help="number of days ending yesterday")
    ap.add_argument("--start", help="optional first date in YYYY-MM-DD format")
    ap.add_argument("--end", help="optional last date in YYYY-MM-DD format")
    args = ap.parse_args()

    paths = config.get_paths().ensure()
    end = date.today() - timedelta(days=1)
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=args.days - 1)
    if args.end:
        end = date.fromisoformat(args.end)
    if start > end:
        raise SystemExit("--start must be on or before --end")

    if not os.environ.get("EE_PROJECT"):
        raise SystemExit("Set EE_PROJECT and run earthengine authenticate before building live data.")

    paths.data.joinpath("DATA_LABEL").write_text(
        "LIVE DATA - current public observations; OSM shelter candidates are not verified shelters. "
        "Follow official flood alerts.", encoding="utf-8")

    run([sys.executable, str(ROOT / "pipeline" / "01_study_area.py")])
    run([sys.executable, str(ROOT / "pipeline" / "03_osm_roads_places.py")])
    run([sys.executable, str(ROOT / "pipeline" / "04_rainfall_gpm.py"), "--start", start.isoformat(), "--end", end.isoformat()])
        dry_start = (start - timedelta(days=90)).isoformat()
        dry_end = (start - timedelta(days=1)).isoformat()
        run([sys.executable, str(ROOT / "pipeline" / "02a_sentinel1_gee.py"), "--start", start.isoformat(), "--end", end.isoformat(),
            "--dry-start", dry_start, "--dry-end", dry_end])
        run([sys.executable, str(ROOT / "pipeline" / "02c_modis.py"), "--ee-process",
            "--start", start.isoformat(), "--end", end.isoformat(),
            "--baseline-start", dry_start, "--baseline-end", dry_end])
    run([sys.executable, str(ROOT / "pipeline" / "02e_merge_flood.py")])
    run([sys.executable, str(ROOT / "pipeline" / "05_cut_roads.py")])
    run([sys.executable, str(ROOT / "pipeline" / "06_isolation.py")])
    run([sys.executable, str(ROOT / "pipeline" / "07_timeline.py")])
    if paths.validation_reports.exists():
        run([sys.executable, str(ROOT / "pipeline" / "09_validate.py")])
    else:
        print("\nSkipping news-report validation: no validation template has been supplied.")
    run([sys.executable, str(ROOT / "pipeline" / "08_build_app_data.py")])
    print(f"\nLive SafeWindow data built in {paths.data}")
    print("\nScientific evidence is not complete until the benchmark, independent evaluation, and source manifest are supplied.")


if __name__ == "__main__":
    main()
