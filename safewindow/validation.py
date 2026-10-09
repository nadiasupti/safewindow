"""Validation contracts for generated SafeWindow application datasets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from pandas.api.types import is_numeric_dtype

from safewindow import config

REQUIRED_FILES = (
    "meta.json",
    "villages.geojson",
    "village_status.csv",
    "shelters.geojson",
    "exit_routes.geojson",
    "cut_roads.geojson",
)
REQUIRED_STATUS_COLUMNS = {
    "village_id", "date", "status", "dist_to_shelter_m", "nearest_shelter_id",
}
OPTIONAL_FILES = (
    "rainfall_daily.csv",
    "modis_flood_area.csv",
    "sensitivity_summary.csv",
    "validation.csv",
)


def _parse_dates(values: Any) -> list[pd.Timestamp]:
    try:
        return pd.to_datetime(values, errors="raise").tolist()
    except (TypeError, ValueError):
        raise ValueError("dates must be valid ISO date strings") from None


def _read_geojson(path: Path) -> gpd.GeoDataFrame:
    frame = gpd.read_file(path)
    if frame.geometry.isna().any():
        raise ValueError(f"{path.name} contains missing geometries")
    if frame.crs is None:
        raise ValueError(f"{path.name} has no CRS")
    return frame


def validate_app_dataset(app_dir: Path | str) -> dict[str, Any]:
    """Validate a generated app package and return a machine-readable report."""
    app = Path(app_dir)
    errors: list[str] = []
    warnings: list[str] = []

    missing = [name for name in REQUIRED_FILES if not (app / name).is_file()]
    if missing:
        errors.append("missing required files: " + ", ".join(missing))

    flood_dir = app / "flood"
    if not flood_dir.is_dir():
        errors.append("missing flood image directory")
    else:
        flood_images = sorted(flood_dir.glob("*.png"))
        if not flood_images:
            errors.append("no flood images were generated")

    if errors:
        return {"valid": False, "files": 0, "errors": errors, "warnings": warnings}

    try:
        meta = json.loads((app / "meta.json").read_text(encoding="utf-8"))
        dates = _parse_dates(meta.get("dates"))
        if not dates:
            raise ValueError("dates is empty")
        if dates != sorted(dates):
            raise ValueError("dates must be in chronological order")
        if not meta.get("data_label"):
            raise ValueError("data_label is missing")
        if not isinstance(meta.get("sources"), dict) or not meta.get("unknown_pct"):
            raise ValueError("sources and unknown_pct must be objects")
        if meta.get("app_start") is None or meta.get("app_end") is None:
            raise ValueError("app_start and app_end are required")
        for date_value in dates:
            if date_value.strftime("%Y-%m-%d") not in meta.get("flood_bounds", {}):
                raise ValueError(f"missing flood bounds for {date_value.date()}")
            if date_value.strftime("%Y-%m-%d") not in meta.get("sources", {}):
                raise ValueError(f"missing source metadata for {date_value.date()}")
        if not 0 <= float(meta.get("unknown_pct", {}).get(dates[0].strftime("%Y-%m-%d"), 0)) <= 100:
            raise ValueError("unknown_pct must be between 0 and 100")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        errors.append(f"meta.json: {exc}")

    try:
        villages = _read_geojson(app / "villages.geojson")
        if villages.empty:
            raise ValueError("villages.geojson contains no villages")
        if villages["village_id"].duplicated().any():
            raise ValueError("villages.geojson contains duplicate village_id values")
        required_village_columns = {"village_id", "name", "population", "geometry"}
        missing_columns = required_village_columns - set(villages.columns)
        if missing_columns:
            raise ValueError("missing village columns: " + ", ".join(sorted(missing_columns)))
        if not villages.geometry.geom_type.eq("Point").all():
            raise ValueError("all village geometries must be points")
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f"villages.geojson: {exc}")

    try:
        status = pd.read_csv(app / "village_status.csv", dtype={"village_id": str})
        missing_columns = REQUIRED_STATUS_COLUMNS - set(status.columns)
        if missing_columns:
            raise ValueError("missing status columns: " + ", ".join(sorted(missing_columns)))
        if status.empty:
            raise ValueError("village_status.csv is empty")
        if status[["village_id", "date"]].duplicated().any():
            raise ValueError("village_status.csv contains duplicate village/date rows")
        status["date"] = pd.to_datetime(status["date"], errors="raise")
        if status["date"].isna().any():
            raise ValueError("village_status.csv contains invalid dates")
        valid_statuses = {"connected", "isolated", "uncertain", "boat_dependent"}
        invalid_statuses = set(status["status"].dropna()) - valid_statuses
        if invalid_statuses:
            raise ValueError("invalid statuses: " + ", ".join(sorted(invalid_statuses)))
        if not is_numeric_dtype(status["dist_to_shelter_m"]):
            raise ValueError("dist_to_shelter_m must be numeric")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"village_status.csv: {exc}")

    for filename in ("shelters.geojson", "exit_routes.geojson", "cut_roads.geojson"):
        try:
            frame = _read_geojson(app / filename)
            if frame.crs is None or not frame.crs.is_projected:
                warnings.append(f"{filename} uses a non-projected CRS")
            if filename == "cut_roads.geojson" and not frame.empty and "edge_id" not in frame.columns:
                raise ValueError("cut_roads.geojson must contain edge_id")
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f"{filename}: {exc}")

    for image in sorted(flood_dir.glob("*.png")):
        try:
            with rasterio.open(image) as raster:
                if raster.count not in (1, 4) or raster.dtypes[0] != "uint8":
                    raise ValueError("flood image must be a one-band class raster or four-band RGBA overlay")
                if raster.count == 1:
                    values = raster.read(1)
                    if not set(np.unique(values)).issubset({config.DRY, config.FLOODED, config.UNKNOWN}):
                        raise ValueError("flood image contains values outside the valid classes")
                if raster.width == 0 or raster.height == 0:
                    raise ValueError("flood image has no pixels")
        except (OSError, ValueError) as exc:
            errors.append(f"{image.name}: {exc}")

    for filename in OPTIONAL_FILES:
        path = app / filename
        if not path.exists():
            warnings.append(f"optional file missing: {filename}")
            continue
        try:
            if filename.endswith(".csv"):
                pd.read_csv(path)
        except (OSError, pd.errors.ParserError, ValueError) as exc:
            errors.append(f"{filename}: {exc}")

    files = sum(1 for path in app.rglob("*") if path.is_file())
    return {"valid": not errors, "files": files, "errors": errors, "warnings": warnings}
