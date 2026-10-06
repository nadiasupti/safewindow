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
import urllib.request
import zipfile
from pathlib import Path

from . import config
from .flood import Grid


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


def download_to_grid(image, grid: Grid, out: Path, name: str = "img") -> Path:
    """Download an ee.Image exactly onto the project grid as a GeoTIFF.

    Uses getDownloadURL, which is limited to roughly 48 MB per request. A 40 x
    40 km area at 20 m is ~4 M pixels, well within the limit. For much larger
    areas raise GRID_RES_M or export to Drive instead."""
    t = grid.transform
    url = image.getDownloadURL({
        "name": name,
        "crs": grid.crs,
        "crsTransform": [t.a, t.b, t.c, t.d, t.e, t.f],
        "dimensions": f"{grid.width}x{grid.height}",
        "format": "GEO_TIFF",
    })
    out.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as r:
        data = r.read()
    if data[:2] == b"PK":   # some EE versions still return a zip
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            data = z.read([n for n in z.namelist() if n.endswith(".tif")][0])
    out.write_bytes(data)
    return out
