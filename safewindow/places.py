"""Villages, shelters and the study area (Step 3)."""
from __future__ import annotations

import warnings

import geopandas as gpd
import pandas as pd

from . import config

SHELTER_COLS = ["shelter_id", "name", "type", "lat", "lon", "source", "verified", "notes"]


def load_study_area(paths=None) -> gpd.GeoDataFrame:
    paths = paths or config.get_paths()
    return gpd.read_file(paths.study_area).to_crs(config.CRS)


def load_villages(paths=None) -> gpd.GeoDataFrame:
    paths = paths or config.get_paths()
    v = gpd.read_file(paths.villages).to_crs(config.CRS)
    v["village_id"] = v["village_id"].astype(str)
    if "population" not in v:
        v["population"] = pd.NA
    return v


def shelters_from_csv(path) -> gpd.GeoDataFrame:
    df = pd.read_csv(path, dtype={"shelter_id": str})
    missing = set(["shelter_id", "name", "lat", "lon"]) - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing columns {sorted(missing)}")
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=config.CRS_WGS84)
    return gdf.to_crs(config.CRS)


def load_shelters(paths=None) -> gpd.GeoDataFrame:
    """The hand-checked list if it exists (only rows with verified == yes),
    otherwise the raw OpenStreetMap candidates with a warning."""
    paths = paths or config.get_paths()
    if paths.shelters_verified.exists():
        s = shelters_from_csv(paths.shelters_verified)
        if "verified" in s:
            s = s[s["verified"].astype(str).str.lower().isin(["yes", "y", "true", "1"])]
        if s.empty:
            raise ValueError(f"No rows marked verified=yes in {paths.shelters_verified}")
        return s
    warnings.warn(f"{paths.shelters_verified.name} not found - using unverified OSM candidates. "
                  "Hand-check 15-30 shelters before the demo (guide Step 3).")
    return shelters_from_csv(paths.shelter_candidates)
