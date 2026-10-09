"""Tests for real-data dataset safety."""

from pathlib import Path

import numpy as np
import pytest
import rasterio

from ml.prepare_dataset import collect_rasters


def test_collect_rasters_rejects_missing_real_dem(tmp_path: Path) -> None:
    flood_dir = tmp_path / "processed" / "flood_merged"
    flood_dir.mkdir(parents=True)
    flood_path = flood_dir / "2022-05-20.tif"
    with rasterio.open(
        flood_path,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="uint8",
        crs="EPSG:32646",
        transform=rasterio.transform.from_origin(0, 4, 1, 1),
    ) as image:
        image.write(np.zeros((4, 4), dtype=np.uint8), 1)

    with pytest.raises(FileNotFoundError, match="Real DEM"):
        collect_rasters(tmp_path, flood_dir)
