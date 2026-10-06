"""Build a SYNTHETIC demo dataset so the engine and the app can run before the
real data (Earth Engine, Earthdata, OSM) is downloaded.

    python scripts/make_demo_data.py          # writes data_demo/
    set SAFEWINDOW_DATA_DIR=data_demo         (PowerShell: $env:SAFEWINDOW_DATA_DIR="data_demo")
    python scripts/run_engine.py              # steps 2e, 5, 6, 7, 8 (and 9)
    streamlit run app/streamlit_app.py

Everything here is invented: a made-up road grid, a made-up terrain and a
flood that rises to a peak on 19 June and then falls. Village and shelter names
are placeholders. Nothing in data_demo/ is an observation; the app shows a
banner saying so.
"""
import json
import os
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SAFEWINDOW_DATA_DIR", "data_demo")

from safewindow import config  # noqa: E402
from safewindow.flood import Grid, register_flood_map  # noqa: E402

RNG = np.random.default_rng(2022)
# Lower-left corner of the made-up area, roughly east of Sunamganj town (UTM 46N)
X0, Y0, W, H = 340_000, 2_768_000, 14_000, 11_000

# observation dates and which (pretend) source they stand in for
OBS = [("2022-05-26", "sentinel1"), ("2022-06-07", "sentinel1"), ("2022-06-14", "modis"),
       ("2022-06-17", "sentinel1"), ("2022-06-19", "unosat"), ("2022-06-21", "unosat"),
       ("2022-06-24", "unosat"), ("2022-06-29", "sentinel1"), ("2022-07-05", "sentinel1")]
LEVEL = {"2022-05-26": 4.2, "2022-06-07": 5.0, "2022-06-14": 5.9, "2022-06-17": 6.9, "2022-06-19": 7.6,
         "2022-06-21": 7.4, "2022-06-24": 6.8, "2022-06-29": 6.0, "2022-07-05": 5.3}


def terrain(xx, yy):
    """Ground height (m): higher in the north-west, a haor bowl in the south-east,
    a river channel across the middle, plus smooth noise."""
    u, v = (xx - X0) / W, (yy - Y0) / H
    z = 8.5 - 3.0 * u + 2.0 * v
    z -= 4.0 * np.exp(-(((u - 0.72) / 0.22) ** 2 + ((v - 0.30) / 0.25) ** 2))      # haor bowl
    z -= 2.5 * np.exp(-((v - 0.55 - 0.08 * np.sin(6 * u)) / 0.03) ** 2)               # river
    z += 0.6 * np.sin(9 * u + 1.3) * np.cos(7 * v) + 0.3 * np.sin(23 * u) * np.sin(19 * v)
    return z


def make_roads():
    nx_, ny_ = 15, 12
    xs, ys = np.linspace(X0 + 500, X0 + W - 500, nx_), np.linspace(Y0 + 500, Y0 + H - 500, ny_)
    nodes = {}
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            px, py = x + RNG.normal(0, 150), y + RNG.normal(0, 150)
            u, v = (px - X0) / W, (py - Y0) / H
            # nobody builds roads in the middle of the haor
            if ((u - 0.72) / 0.17) ** 2 + ((v - 0.30) / 0.17) ** 2 < 1:
                continue
            nodes[(i, j)] = (px, py)
    edges = []
    for (i, j), p in nodes.items():
        for di, dj in [(1, 0), (0, 1), (1, 1)]:
            q = nodes.get((i + di, j + dj))
            if q is None or (di and dj and RNG.random() > 0.25) or RNG.random() < 0.12:
                continue
            mid = ((p[0] + q[0]) / 2 + RNG.normal(0, 60), (p[1] + q[1]) / 2 + RNG.normal(0, 60))
            edges.append(((i, j), (i + di, j + dj), LineString([p, mid, q])))
    nid = {k: f"n{n}" for n, k in enumerate(nodes)}
    ng = gpd.GeoDataFrame({"node_id": list(nid.values())},
                          geometry=[Point(nodes[k]) for k in nid], crs=config.CRS)
    eg = gpd.GeoDataFrame({
        "edge_id": [f"e{n}" for n in range(len(edges))],
        "u": [nid[a] for a, _, _ in edges], "v": [nid[b] for _, b, _ in edges],
        "length_m": [round(g.length, 1) for *_, g in edges],
        "highway": ["unclassified" if (a[1] == 5) else "track" for a, _, _ in edges],
        "name": None,
    }, geometry=[g for *_, g in edges], crs=config.CRS)
    return ng, eg


def raised_road_mask(edges, grid, xx, yy):
    """The east-west road on row 5 sits on an embankment (+2 m)."""
    from rasterio.features import rasterize
    main = edges[edges["highway"] == "unclassified"].buffer(15)
    return rasterize([(g, 1) for g in main], out_shape=(grid.height, grid.width),
                     transform=grid.transform, fill=0, dtype="uint8").astype(bool)


def main():
    paths = config.get_paths()
    if paths.data.exists():
        import shutil
        shutil.rmtree(paths.data)
    paths.ensure()
    (paths.data / "DATA_LABEL").write_text("SYNTHETIC DEMO DATA - invented terrain, roads and flood; not observations")

    sa = gpd.GeoDataFrame({"upazila": ["Demo area"]}, geometry=[box(X0, Y0, X0 + W, Y0 + H)], crs=config.CRS)
    sa.to_file(paths.study_area, driver="GPKG")
    grid = Grid.from_bounds(*sa.total_bounds, pad=0)
    grid.save(paths.grid)

    nodes, edges = make_roads()
    nodes.to_file(paths.road_nodes, driver="GPKG")
    edges.to_file(paths.road_edges, driver="GPKG")

    cx = grid.xmin + (np.arange(grid.width) + 0.5) * grid.res
    cy = grid.ymax - (np.arange(grid.height) + 0.5) * grid.res
    xx, yy = np.meshgrid(cx, cy)
    dem = terrain(xx, yy)
    dem[raised_road_mask(edges, grid, xx, yy)] += 2.0

    for day, source in OBS:
        arr = np.where(dem < LEVEL[day], config.FLOODED, config.DRY).astype("uint8")
        if day == "2022-06-14":   # a cloudy day: a band of unknown pixels
            u = (xx - X0) / W
            arr[(u > 0.15) & (u < 0.45)] = config.UNKNOWN
        register_flood_map(day, source, arr, grid, note="SYNTHETIC", paths=paths)

    # villages: random points, a few deep in the haor (boat-dependent)
    pts, names = [], []
    while len(pts) < 70:
        p = Point(X0 + RNG.uniform(300, W - 300), Y0 + RNG.uniform(300, H - 300))
        if all(p.distance(q) > 600 for q in pts):
            pts.append(p)
    v = gpd.GeoDataFrame({
        "village_id": [f"v{i:03d}" for i in range(len(pts))],
        "name": [f"Demo Village {i + 1}" for i in range(len(pts))],
        "name_bn": [f"ডেমো গ্রাম {str(i + 1).translate(str.maketrans('0123456789', '০১২৩৪৫৬৭৮৯'))}"
                    for i in range(len(pts))],
        "place": "village", "source": "SYNTHETIC",
        "population": RNG.integers(300, 6000, len(pts)),
    }, geometry=pts, crs=config.CRS)
    v.to_file(paths.villages, driver="GPKG")

    # shelters on the highest road junctions (like schools on raised ground)
    nz = terrain(nodes.geometry.x.to_numpy(), nodes.geometry.y.to_numpy())
    pick = nodes.iloc[np.argsort(-nz)[::9][:10]].to_crs(config.CRS_WGS84)
    sh = pd.DataFrame({
        "shelter_id": [f"s{i:02d}" for i in range(len(pick))],
        "name": [f"Demo Shelter {i + 1} (school)" for i in range(len(pick))],
        "type": "school", "lat": pick.geometry.y.round(6), "lon": pick.geometry.x.round(6),
        "source": "SYNTHETIC", "verified": "yes", "notes": "",
    })
    sh.to_csv(paths.shelters_verified, index=False)

    # rainfall (mm/day): upstream Meghalaya much wetter, peaking mid-June
    days = pd.date_range("2022-05-15", "2022-07-05")
    t = np.arange(len(days))
    pulse = lambda c, w, a: a * np.exp(-((t - c) / w) ** 2)  # noqa: E731
    up = 20 + pulse(32, 3, 520) + pulse(14, 2, 180) + RNG.gamma(1.5, 15, len(t))
    local = 8 + pulse(32, 3, 160) + pulse(14, 2, 60) + RNG.gamma(1.2, 8, len(t))
    pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "sunamganj_mm": local.round(1),
                  "meghalaya_upstream_mm": up.round(1)}).to_csv(paths.rainfall, index=False)

    # MODIS-style daily flooded area (km2) for the regional trend
    lv = pd.Series(LEVEL, dtype=float)
    lv.index = pd.to_datetime(lv.index)
    daily = lv.resample("D").asfreq().interpolate()
    area = [(dem < L).mean() * W * H / 1e6 for L in daily]
    pd.DataFrame({"date": daily.index.strftime("%Y-%m-%d"), "flooded_km2": np.round(area, 1),
                  "unknown_pct": np.round(RNG.uniform(5, 60, len(daily)), 1)}).to_csv(paths.modis_timeline, index=False)

    # a few invented "reports" so step 9 can be exercised
    (paths.data / "validation").mkdir(exist_ok=True)
    pd.DataFrame({
        "place_name": ["Demo Village 12", "demo village 30", "Demo Vilage 41", "Demo Village 7"],
        "place_name_bn": "", "upazila": "Demo area",
        "date_reported": ["2022-06-18", "2022-06-20", "2022-06-17", "2022-06-19"],
        "reported_isolated": "yes", "source_name": "SYNTHETIC", "source_url": "", "village_id": "", "notes": "",
    }).to_csv(paths.validation_reports, index=False)

    print(f"synthetic demo data written to {paths.data}")
    print(json.dumps({"roads": len(edges), "junctions": len(nodes), "villages": len(v),
                      "shelters": len(sh), "flood_dates": len(OBS)}))
    print("\nNEXT: python scripts/run_engine.py   (with SAFEWINDOW_DATA_DIR=data_demo), "
          "then streamlit run app/streamlit_app.py")


if __name__ == "__main__":
    main()
