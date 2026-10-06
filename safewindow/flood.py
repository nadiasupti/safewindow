"""Flood maps on one shared grid (Step 2).

Every source (Sentinel-1, UNOSAT, MODIS, DEM estimate) is written as a uint8
GeoTIFF on the same grid with values DRY=0, FLOODED=1, UNKNOWN=255, and listed
in ``flood/manifest.csv``. ``merge_by_date`` then combines all sources for a
date into one map, filling unknown pixels from lower-priority sources.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .config import DRY, FLOODED, UNKNOWN


@dataclass(frozen=True)
class Grid:
    """A north-up raster grid in config.CRS."""
    xmin: float
    ymax: float
    width: int
    height: int
    res: float = config.GRID_RES_M
    crs: str = config.CRS

    @property
    def transform(self):
        from rasterio.transform import from_origin
        return from_origin(self.xmin, self.ymax, self.res, self.res)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.xmin, self.ymax - self.height * self.res,
                self.xmin + self.width * self.res, self.ymax)

    @classmethod
    def from_bounds(cls, xmin, ymin, xmax, ymax, res=config.GRID_RES_M, pad=500.0) -> "Grid":
        xmin, ymin = np.floor((xmin - pad) / res) * res, np.floor((ymin - pad) / res) * res
        xmax, ymax = np.ceil((xmax + pad) / res) * res, np.ceil((ymax + pad) / res) * res
        return cls(float(xmin), float(ymax), int(round((xmax - xmin) / res)),
                   int(round((ymax - ymin) / res)), float(res))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2))

    @classmethod
    def load(cls, path: Path) -> "Grid":
        return cls(**json.loads(path.read_text()))


def write_flood_map(arr: np.ndarray, grid: Grid, path: Path) -> None:
    import rasterio
    assert arr.shape == (grid.height, grid.width), "array does not match grid"
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=grid.width, height=grid.height,
                       count=1, dtype="uint8", crs=grid.crs, transform=grid.transform,
                       nodata=UNKNOWN, compress="deflate") as dst:
        dst.write(arr.astype("uint8"), 1)


def read_onto_grid(path: Path, grid: Grid) -> np.ndarray:
    """Read any single-band flood GeoTIFF and resample it onto ``grid``
    (nearest neighbour). Pixels the source does not cover become UNKNOWN."""
    import rasterio
    from rasterio.warp import Resampling, reproject

    out = np.full((grid.height, grid.width), UNKNOWN, dtype="uint8")
    with rasterio.open(path) as src:
        reproject(source=rasterio.band(src, 1), destination=out,
                  src_nodata=src.nodata if src.nodata is not None else UNKNOWN,
                  dst_transform=grid.transform, dst_crs=grid.crs, dst_nodata=UNKNOWN,
                  resampling=Resampling.nearest)
    return out


# --- manifest ------------------------------------------------------------------

MANIFEST_COLS = ["date", "source", "path", "note"]


def load_manifest(paths=None) -> pd.DataFrame:
    paths = paths or config.get_paths()
    if not paths.flood_manifest.exists():
        return pd.DataFrame(columns=MANIFEST_COLS)
    return pd.read_csv(paths.flood_manifest, dtype=str).fillna("")


def register_flood_map(day: str, source: str, arr: np.ndarray, grid: Grid,
                       note: str = "", paths=None) -> Path:
    """Write a flood map for one date/source and add it to the manifest
    (replacing any earlier entry for the same date and source)."""
    if source not in config.SOURCE_PRIORITY:
        raise ValueError(f"unknown source {source!r}; expected one of {config.SOURCE_PRIORITY}")
    paths = (paths or config.get_paths()).ensure()
    day = pd.Timestamp(day).strftime("%Y-%m-%d")
    out = paths.flood_dir / f"{source}_{day.replace('-', '')}.tif"
    write_flood_map(arr, grid, out)

    m = load_manifest(paths)
    m = m[~((m["date"] == day) & (m["source"] == source))]
    row = {"date": day, "source": source, "path": out.relative_to(paths.data).as_posix(), "note": note}
    m = pd.concat([m, pd.DataFrame([row])], ignore_index=True).sort_values(["date", "source"])
    m.to_csv(paths.flood_manifest, index=False)
    return out


def merge_by_date(paths=None, sources: list[str] | None = None) -> pd.DataFrame:
    """Combine all sources per date into data/processed/flood_merged/YYYYMMDD.tif.

    Returns a table with date, sources used, and the share of flooded / dry /
    unknown pixels, which doubles as the go/no-go coverage check."""
    paths = (paths or config.get_paths()).ensure()
    grid = Grid.load(paths.grid)
    m = load_manifest(paths)
    if sources:
        m = m[m["source"].isin(sources)]
    rank = {s: i for i, s in enumerate(config.SOURCE_PRIORITY)}
    rows = []
    for day, grp in m.groupby("date"):
        merged = np.full((grid.height, grid.width), UNKNOWN, dtype="uint8")
        used = []
        for _, r in sorted(grp.iterrows(), key=lambda kv: rank[kv[1]["source"]]):
            arr = read_onto_grid(paths.data / r["path"], grid)
            fill = (merged == UNKNOWN) & (arr != UNKNOWN)
            if fill.any():
                merged[fill] = arr[fill]
                used.append(r["source"])
        write_flood_map(merged, grid, paths.merged_flood_dir / f"{day.replace('-', '')}.tif")
        n = merged.size
        rows.append({"date": day, "sources": "+".join(used),
                     "flooded_pct": round(100 * (merged == FLOODED).sum() / n, 2),
                     "dry_pct": round(100 * (merged == DRY).sum() / n, 2),
                     "unknown_pct": round(100 * (merged == UNKNOWN).sum() / n, 2)})
    summary = pd.DataFrame(rows)
    summary.to_csv(paths.merged_flood_dir / "summary.csv", index=False)
    return summary


def merged_dates(paths=None) -> list[str]:
    paths = paths or config.get_paths()
    return sorted(pd.Timestamp(p.stem).strftime("%Y-%m-%d")
                  for p in paths.merged_flood_dir.glob("*.tif"))


def merged_path(day: str, paths=None) -> Path:
    paths = paths or config.get_paths()
    return paths.merged_flood_dir / f"{day.replace('-', '')}.tif"
