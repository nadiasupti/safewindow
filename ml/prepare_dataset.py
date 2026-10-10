"""Build a temporal flood-prediction dataset from SafeWindow GeoTIFF files.

Input files are expected in SAFEWINDOW_DATA_DIR/processed/flood_merged/*.tif.
The output is a compact NPZ dataset suitable for PyTorch.

For real data, add DEM and rainfall rasters to the same data directory using the
names below. The demo data is synthetic and must not be used for real-world
predictions.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from sklearn.model_selection import train_test_split

from safewindow import config

CLASS_NAMES = {0: "dry", 1: "flooded", 255: "unknown"}
INPUT_CHANNELS = 5
PATCH_SIZE = 256
HISTORY_DAYS = 3


@dataclass(frozen=True)
class DatasetSpec:
    x: np.ndarray
    y: np.ndarray
    dates: np.ndarray
    sample_ids: np.ndarray
    metadata: dict


def load_raster(path: Path, dtype: np.dtype = np.float32) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1).astype(dtype)


def build_spatial_features(floods: dict[str, np.ndarray], rainfall: dict[str, np.ndarray],
                          dem: dict[str, np.ndarray], patch_size: int) -> tuple[np.ndarray, np.ndarray]:
    """Create input patches and targets from temporal flood rasters."""
    dates = sorted(floods)
    if len(dates) < 2:
        raise ValueError("At least two flood dates are required")

    # A frame is [3 previous flood maps, rainfall, DEM].  The target is the
    # next flood map.  Unknown pixels are represented by zero in the model input
    # and masked in the loss; the target keeps the original class values.
    height, width = floods[dates[0]].shape
    if any(a.shape != (height, width) for a in floods.values()):
        raise ValueError("All flood rasters must have the same shape")
    if any(a.shape != (height, width) for a in rainfall.values()):
        raise ValueError("All rainfall rasters must have the same shape")
    if any(a.shape != (height, width) for a in dem.values()):
        raise ValueError("All DEM rasters must have the same shape")

    samples: list[np.ndarray] = []
    targets: list[np.ndarray] = []
    sample_dates: list[str] = []
    sample_ids: list[str] = []

    for target_index in range(1, len(dates)):
        target_date = dates[target_index]
        for history_start in range(max(0, target_index - HISTORY_DAYS), target_index):
            history = [floods[dates[i]] for i in range(history_start, target_index)]
            if len(history) < HISTORY_DAYS:
                continue
            # Build a five-channel input: three recent flood states,
            # rainfall, and DEM.  The temporal sequence is represented by the
            # first three channels; rainfall and DEM are the final two channels.
            input_patch = np.stack([
                history[0], history[1], history[2], rainfall[target_date]
            ], axis=0)
            input_patch = np.concatenate([input_patch, dem[target_date][None]], axis=0)
            if input_patch.shape[0] != INPUT_CHANNELS:
                raise RuntimeError("Unexpected input channel count")

            x = np.repeat(input_patch[None], 1, axis=0)
            y = floods[target_date][None, ...]
            samples.append(x)
            targets.append(y)
            sample_dates.append(target_date)
            sample_ids.append(f"{history_start:02d}_{target_index:02d}")

    # Spatially crop into patches with overlap. This creates more samples from
    # the small demo raster and avoids excessive memory use.
    x_blocks: list[np.ndarray] = []
    y_blocks: list[np.ndarray] = []
    block_dates: list[str] = []
    block_ids: list[str] = []
    for x, y, date, sample_id in zip(samples, targets, sample_dates, sample_ids):
        row_starts = list(range(0, height, patch_size // 2))
        col_starts = list(range(0, width, patch_size // 2))
        for row in row_starts:
            for col in col_starts:
                r0 = row
                r1 = min(r0 + patch_size, height)
                if r1 - r0 < patch_size:
                    r0 = height - patch_size
                    r1 = height
                c0 = col
                c1 = min(c0 + patch_size, width)
                if c1 - c0 < patch_size:
                    c0 = width - patch_size
                    c1 = width
                x_blocks.append(x[:, :, r0:r1, c0:c1])
                y_blocks.append(y[:, r0:r1, c0:c1])
                block_dates.append(date)
                block_ids.append(f"{sample_id}_{row}_{col}")

    x_array = np.concatenate(x_blocks, axis=0).astype(np.float32)
    y_array = np.concatenate(y_blocks, axis=0).astype(np.int64)
    return x_array, y_array, np.asarray(block_dates), np.asarray(block_ids)


def collect_rasters(data_dir: Path, flood_dir: Path) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]]:
    flood_paths = sorted(flood_dir.glob("*.tif"))
    if not flood_paths:
        raise FileNotFoundError(f"No flood rasters found in {flood_dir}")
    floods = {pd.Timestamp(p.stem).strftime("%Y-%m-%d"): load_raster(p) for p in flood_paths}

    rainfall = {}
    rainfall_path = data_dir / "processed" / "rainfall_daily.csv"
    if rainfall_path.exists():
        rainfall_df = pd.read_csv(rainfall_path)
        rainfall_df["date"] = pd.to_datetime(rainfall_df["date"])
        for date in floods:
            row = rainfall_df[rainfall_df["date"] == date]
            if not row.empty:
                rainfall[date] = np.full(floods[date].shape, float(row.iloc[0]["sunamganj_mm"]), np.float32)

    dem = {}
    dem_paths = sorted((data_dir / "processed" / "dem").glob("*.tif")) if (data_dir / "processed" / "dem").exists() else []
    for path in dem_paths:
        key = pd.Timestamp(path.stem).strftime("%Y-%m-%d")
        if key in floods:
            dem[key] = load_raster(path)

    missing_dem = sorted(set(floods) - set(dem))
    if missing_dem:
        raise FileNotFoundError(
            "Real DEM raster(s) are required for training; missing dates: "
            + ", ".join(missing_dem)
        )

    return floods, rainfall, dem


def split_dataset(x: np.ndarray, y: np.ndarray, dates: np.ndarray, sample_ids: np.ndarray,
                  validation_fraction: float, seed: int) -> tuple[DatasetSpec, DatasetSpec]:
    unique_dates = np.unique(dates)
    train_dates, validation_dates = train_test_split(unique_dates, test_size=validation_fraction,
                                                    random_state=seed)
    train_mask = np.isin(dates, train_dates)
    validation_mask = np.isin(dates, validation_dates)
    return (DatasetSpec(x[train_mask], y[train_mask], dates[train_mask], sample_ids[train_mask], {}),
            DatasetSpec(x[validation_mask], y[validation_mask], dates[validation_mask], sample_ids[validation_mask], {}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path(config.get_paths().data))
    parser.add_argument("--output", type=Path, default=Path("ml/dataset.npz"))
    parser.add_argument("--patch-size", type=int, default=PATCH_SIZE)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    flood_dir = data_dir / "processed" / "flood_merged"
    floods, rainfall, dem = collect_rasters(data_dir, flood_dir)
    x, y, dates, sample_ids = build_spatial_features(floods, rainfall, dem, args.patch_size)
    train, validation = split_dataset(x, y, dates, sample_ids, args.validation_fraction, args.seed)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        x=train.x,
        y=train.y,
        dates=train.dates,
        sample_ids=train.sample_ids,
        x_val=validation.x,
        y_val=validation.y,
        dates_val=validation.dates,
        sample_ids_val=validation.sample_ids,
        input_channels=INPUT_CHANNELS,
        patch_size=args.patch_size,
        history_days=HISTORY_DAYS,
        metadata=json.dumps({
            "data_dir": str(data_dir),
            "source": "synthetic_demo" if (data_dir / "DATA_LABEL").exists() and "SYNTHETIC" in
                (data_dir / "DATA_LABEL").read_text(errors="ignore") else "real",
            "classes": CLASS_NAMES,
            "train_samples": int(len(train.x)),
            "validation_samples": int(len(validation.x)),
        }),
    )
    print(f"Saved {len(train.x)} training and {len(validation.x)} validation samples to {args.output}")


if __name__ == "__main__":
    main()
