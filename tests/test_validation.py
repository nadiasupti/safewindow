import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point

from safewindow import config
from safewindow.validation import validate_app_dataset


def make_app_dataset(tmp_path: Path) -> Path:
    app = tmp_path / "app"
    (app / "flood").mkdir(parents=True)

    meta = {
        "data_label": "SYNTHETIC DEMO DATA",
        "dates": ["2022-06-07"],
        "flood_bounds": {"2022-06-07": [[0, 0], [1, 1]]},
        "sources": {"2022-06-07": "demo"},
        "unknown_pct": {"2022-06-07": 0},
        "cut_threshold": config.CUT_THRESHOLD,
        "default_supply_days": config.DEFAULT_SUPPLY_DAYS,
        "supply_days_range": list(config.SUPPLY_DAYS_RANGE),
        "app_start": "2022-06-01",
        "app_end": "2022-06-30",
    }
    (app / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    pd.DataFrame({
        "village_id": ["v1"], "name": ["Village"], "name_bn": ["গ্রাম"],
        "population": [100], "isolated_from_earliest": ["2022-06-08"],
        "first_isolated": ["2022-06-08"], "last_connected": ["2022-06-07"],
        "safe_exit_date": ["2022-06-07"], "reconnected": [None],
        "outcome": ["isolated"], "urgency_rank": [1], "status_now": ["isolated"],
        "date": ["2022-06-07"], "status": ["isolated"], "dist_to_shelter_m": [1000],
        "nearest_shelter_id": ["s1"],
    }).to_csv(app / "village_status.csv", index=False)

    villages = gpd.GeoDataFrame({
        "village_id": ["v1"], "name": ["Village"], "name_bn": ["গ্রাম"],
        "population": [100], "isolated_from_earliest": ["2022-06-08"],
        "first_isolated": ["2022-06-08"], "last_connected": ["2022-06-07"],
        "safe_exit_date": ["2022-06-07"], "reconnected": [None],
        "outcome": ["isolated"], "urgency_rank": [1], "geometry": [Point(0, 0)],
    }, crs=config.CRS_WGS84)
    villages.to_file(app / "villages.geojson", driver="GeoJSON")

    shelters = gpd.GeoDataFrame({
        "shelter_id": ["s1"], "name": ["Shelter"], "type": ["school"],
        "source": ["demo"], "geometry": [Point(1, 1)],
    }, crs=config.CRS_WGS84)
    shelters.to_file(app / "shelters.geojson", driver="GeoJSON")

    routes = gpd.GeoDataFrame({
        "village_id": ["v1"], "shelter_id": ["s1"], "shelter_name": ["Shelter"],
        "length_m": [1000], "date": ["2022-06-07"],
        "geometry": [Point(0.5, 0.5)],
    }, crs=config.CRS_WGS84)
    routes.to_file(app / "exit_routes.geojson", driver="GeoJSON")

    cut = gpd.GeoDataFrame({"edge_id": [], "date": [], "geometry": []}, geometry="geometry", crs=config.CRS_WGS84)
    cut.to_file(app / "cut_roads.geojson", driver="GeoJSON")

    with rasterio.open(
        app / "flood" / "20220607.png",
        "w",
        driver="PNG",
        width=2,
        height=2,
        count=1,
        dtype="uint8",
        crs=config.CRS_WGS84,
        transform=from_origin(0, 2, 1, 1),
    ) as image:
        image.write(np.array([[0, 1], [0, 1]], dtype="uint8"), 1)

    pd.DataFrame({"date": ["2022-06-07"], "sunamganj_mm": [1.0], "meghalaya_upstream_mm": [2.0]}).to_csv(
        app / "rainfall_daily.csv", index=False)
    pd.DataFrame({"date": ["2022-06-07"], "flooded_km2": [1.0], "unknown_pct": [0.0]}).to_csv(
        app / "modis_flood_area.csv", index=False)
    pd.DataFrame({"row": [1], "road_cutoff": [0.2], "flooded_area_km2": [1.0], "unknown_area_km2": [0.0]}).to_csv(
        app / "sensitivity_summary.csv", index=False)
    pd.DataFrame({"village_id": ["v1"], "report_date": ["2022-06-07"], "reported_isolated": ["yes"]}).to_csv(
        app / "validation.csv", index=False)
    return app


def test_valid_app_dataset_is_accepted(tmp_path: Path) -> None:
    app = make_app_dataset(tmp_path)
    result = validate_app_dataset(app)
    assert result["valid"] is True
    assert result["files"] == 12


def test_invalid_date_range_is_rejected(tmp_path: Path) -> None:
    app = make_app_dataset(tmp_path)
    meta = json.loads((app / "meta.json").read_text())
    meta["dates"] = ["2022-06-07", "2022-06-06"]
    (app / "meta.json").write_text(json.dumps(meta))

    result = validate_app_dataset(app)
    assert result["valid"] is False
    assert any("chronological" in error.lower() for error in result["errors"])
