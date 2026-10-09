"""Google Earth Engine helpers shared by the Sentinel-1, DEM, population and
rainfall steps.

First-time setup (once per computer):
    earthengine authenticate
and set your Cloud project id (created when you registered for noncommercial
Earth Engine use):
    set EE_PROJECT=my-project-id        (Windows)
    export EE_PROJECT=my-project-id     (macOS / Linux)
"""
from __future__ import annotations

import io
import os
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from . import config
from .flood import Grid


def retry_ee_download(url: str, attempts: int = 4, delay_seconds: float = 2.0) -> bytes:
    """Retry transient Earth Engine HTTP failures with exponential backoff."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            retryable = exc.code in {400, 408, 429, 500, 502, 503, 504}
            last_error = exc
            if not retryable or attempt == attempts:
                raise
            time.sleep(delay_seconds * (2 ** (attempt - 1)))
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == attempts:
                raise
            time.sleep(delay_seconds * (2 ** (attempt - 1)))
    raise last_error


def init():
    import ee
    project = os.environ.get("EE_PROJECT")
    try:
        ee.Initialize(project=project)
    except Exception as exc:  # noqa: BLE001 - give a clear next step
        raise SystemExit(
            "Could not start Earth Engine. Run `earthengine authenticate` and set the "
            f"EE_PROJECT environment variable to your Cloud project id.\n  ({exc})")
    return ee


def study_area_geometry(paths=None):
    """The study area as an ee.Geometry in WGS84."""
    import ee
    from .places import load_study_area
    sa = load_study_area(paths).to_crs(config.CRS_WGS84)
    return ee.Geometry(sa.union_all().__geo_interface__)


def chunk_bounds(grid: Grid, tile_width: int = 800, tile_height: int = 800):
    """Return contiguous raster chunks, each no larger than the requested pixels."""
    if tile_width < 1 or tile_height < 1:
        raise ValueError("tile dimensions must be positive")
    for y in range(0, grid.height, tile_height):
        for x in range(0, grid.width, tile_width):
            yield (x, y, min(x + tile_width, grid.width), min(y + tile_height, grid.height))


def raster_window(bounds):
    """Convert absolute tile bounds to Rasterio's width/height window."""
    import rasterio

    x0, y0, x1, y1 = bounds
    return rasterio.windows.Window(x0, y0, x1 - x0, y1 - y0)


def download_to_grid(
    image, grid: Grid, out: Path, name: str = "img", region=None,
    dtype: str = "uint8", nodata: int | float = 255,
) -> Path:
    """Download an ee.Image onto the project grid as a GeoTIFF.

    Earth Engine limits each export to roughly 48 MB. Split the grid into
    800 x 800 pixel tiles, download each tile independently, and stitch
    them into one GeoTIFF in the destination grid's native projection.

    The image is normalized to one named band, cast to the requested dtype,
    and explicitly clipped to the requested region before each tile is
    exported."""
    if region is None:
        raise ValueError("region is required for a valid Earth Engine export")
    import ee
    import rasterio

    cast = {"uint8": "toByte", "float32": "toFloat"}.get(dtype)
    if cast is None:
        raise ValueError(f"unsupported Earth Engine export dtype: {dtype}")
    export_image = getattr(image.rename("value").clip(region), cast)()
    out.parent.mkdir(parents=True, exist_ok=True)
    t = grid.transform

    with rasterio.open(out, "w", driver="GTiff", width=grid.width, height=grid.height,
                       count=1, dtype=dtype, crs=grid.crs, transform=t,
                       nodata=nodata, compress="deflate") as dst:
        for x0, y0, x1, y1 in chunk_bounds(grid):
            tile_transform = rasterio.transform.from_origin(
                t.c + x0 * t.a, t.f + y0 * t.e, t.a, t.e)
            url = export_image.getDownloadURL({
                "name": f"{name}_{x0}_{y0}",
                "crs": grid.crs,
                "crsTransform": [tile_transform.a, tile_transform.b,
                                 tile_transform.c, tile_transform.d,
                                 tile_transform.e, tile_transform.f],
                "dimensions": f"{x1 - x0}x{y1 - y0}",
                "format": "GEO_TIFF",
            })
            try:
                data = retry_ee_download(url)
            except Exception as exc:
                raise RuntimeError(f"Earth Engine tile export failed for chunk {(x0, y0, x1, y1)}: {url}") from exc
            if data[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    tile_name = next(n for n in z.namelist() if n.endswith(".tif"))
                    data = z.read(tile_name)
            with rasterio.open(io.BytesIO(data)) as src:
                dst.write(src.read(1), 1, window=raster_window((x0, y0, x1, y1)))
    return out
