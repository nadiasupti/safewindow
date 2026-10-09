"""Project-wide settings and file locations.

Every pipeline step and the app read paths from here, so the folder layout
lives in one place. Set the environment variable SAFEWINDOW_DATA_DIR to point
the whole project at another data folder (the synthetic demo uses
``data_demo``).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = "data/live"

# --- Study area (Step 1) -----------------------------------------------------
# Upazilas to analyse. Change after checking OSM road coverage
# (pipeline/01_study_area.py --rank).
UPAZILAS = ["Sunamganj Sadar", "Chhatak", "Dowarabazar"]
DISTRICT = "Sunamganj"
COUNTRY = "Bangladesh"

# One projection for everything: UTM zone 46N, units in metres.
CRS = "EPSG:32646"
CRS_WGS84 = "EPSG:4326"

# Common flood-map grid. Every flood source is written onto this grid so that
# sources can be merged pixel by pixel.
GRID_RES_M = 20

# --- Time window --------------------------------------------------------------
DRY_REF_START, DRY_REF_END = "2022-02-01", "2022-03-31"   # haor is dry
FLOOD_START, FLOOD_END = date(2022, 5, 15), date(2022, 7, 15)
APP_START, APP_END = date(2022, 5, 20), date(2022, 6, 30)

# --- Flood raster encoding ---------------------------------------------------
DRY, FLOODED, UNKNOWN = 0, 1, 255

# When several sources exist for one date, pixels are filled in this order:
# a lower-ranked source only fills pixels still unknown after the ones above.
SOURCE_PRIORITY = ["sentinel1", "unosat", "dem_estimate", "modis"]

# --- Road cutting (Step 5) ------------------------------------------------------
SAMPLE_SPACING_M = 20
CUT_THRESHOLD = 0.20                     # main result
SENSITIVITY_THRESHOLDS = [0.10, 0.20, 0.40]
UNKNOWN_MAJORITY = 0.50                  # > this share unknown -> road "unknown"

# --- Isolation (Step 6) ----------------------------------------------------------
BOAT_DEPENDENT_M = 500                   # village farther than this from a road
SHELTER_SNAP_MAX_M = 1000                # shelter farther than this is not road-reachable

# --- Survival Clock (Step 7) --------------------------------------------------------
# ASSUMPTION, not a measurement: days of food/water a household has on hand.
# Replace with a sourced figure (e.g. a household survey from the haor region)
# and cite it in the README and pitch.
DEFAULT_SUPPLY_DAYS = 7
SUPPLY_DAYS_RANGE = (2, 14)

# --- Rainfall boxes (Step 4), lon/lat: (west, south, east, north) ---------------
RAIN_BOXES = {
    "sunamganj": (90.95, 24.85, 91.75, 25.25),
    # Southern Meghalaya slopes around Cherrapunji (Sohra), upstream of Sunamganj.
    "meghalaya_upstream": (91.30, 25.15, 92.10, 25.45),
}


@dataclass(frozen=True)
class Paths:
    data: Path

    @property
    def raw(self) -> Path: return self.data / "raw"
    @property
    def processed(self) -> Path: return self.data / "processed"
    @property
    def results(self) -> Path: return self.data / "results"
    @property
    def app(self) -> Path: return self.data / "app"

    # processed inputs
    @property
    def study_area(self) -> Path: return self.processed / "study_area.gpkg"
    @property
    def grid(self) -> Path: return self.processed / "grid.json"
    @property
    def flood_dir(self) -> Path: return self.processed / "flood"
    @property
    def flood_manifest(self) -> Path: return self.flood_dir / "manifest.csv"
    @property
    def merged_flood_dir(self) -> Path: return self.processed / "flood_merged"
    @property
    def roads_graph(self) -> Path: return self.processed / "roads.graphml"   # raw osmnx graph
    @property
    def road_nodes(self) -> Path: return self.processed / "road_nodes.gpkg"
    @property
    def road_edges(self) -> Path: return self.processed / "road_edges.gpkg"
    @property
    def villages(self) -> Path: return self.processed / "villages.gpkg"
    @property
    def shelter_candidates(self) -> Path: return self.processed / "shelters_candidates.csv"
    @property
    def shelters_verified(self) -> Path: return self.processed / "shelters_verified.csv"
    @property
    def rainfall(self) -> Path: return self.processed / "rainfall_daily.csv"
    @property
    def modis_timeline(self) -> Path: return self.processed / "modis_flood_area.csv"

    # results
    @property
    def road_status(self) -> Path: return self.results / "road_status.csv"
    @property
    def village_status(self) -> Path: return self.results / "village_status.csv"
    @property
    def village_summary(self) -> Path: return self.results / "village_summary.csv"
    @property
    def exit_routes(self) -> Path: return self.results / "exit_routes.gpkg"
    @property
    def sensitivity(self) -> Path: return self.results / "sensitivity.csv"
    @property
    def validation_reports(self) -> Path: return self.data / "validation" / "news_reports.csv"
    @property
    def validation_results(self) -> Path: return self.results / "validation.csv"

    def ensure(self) -> "Paths":
        for p in (self.raw, self.processed, self.results, self.app,
                  self.flood_dir, self.merged_flood_dir):
            p.mkdir(parents=True, exist_ok=True)
        return self


def get_paths() -> Paths:
    data = Path(os.environ.get("SAFEWINDOW_DATA_DIR", ROOT / DEFAULT_DATA_DIR))
    if not data.is_absolute():
        data = ROOT / data
    return Paths(data)
