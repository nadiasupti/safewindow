# SafeWindow

**When does each village lose its last road to a flood shelter?**
A research prototype for the June 2022 Sunamganj (Bangladesh) haor flood, built for NASA Space Apps Challenge 2026.

SafeWindow combines satellite flood maps (Sentinel-1 radar, UNOSAT, NASA MODIS) with the OpenStreetMap road network. For every village it estimates:

- the **isolation date range**: when the last road path to any shelter went under water
- the **safe exit window**: the last date a road route out was still open, and that route
- the **aid deadline (Survival Clock)**: isolation date + household supply days
- an **urgency ranking** for responders

NASA GPM IMERG rainfall (local and upstream in Meghalaya) and the MODIS daily flood trend appear alongside the map.

> ⚠️ Research prototype, not an official warning system. Follow official alerts (BMD, FFWC, DDM).

---

## Quick start: run the synthetic demo (no accounts needed)

```powershell
python -m venv .venv
.\.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -r requirements-pipeline.txt
pip install -e .

$env:SAFEWINDOW_DATA_DIR="data_demo"     # macOS/Linux: export SAFEWINDOW_DATA_DIR=data_demo
python scripts/make_demo_data.py         # invented terrain, roads, flood
python scripts/run_engine.py             # steps 2e, 5, 6, 7, 9, 8
streamlit run app/streamlit_app.py
```

The demo data is **entirely made up**, and the app shows a banner saying so. Use it to develop the app and engine while the real data is being prepared.

With conda/Miniforge instead of pip: `conda env create -f environment.yml`.

Tests: `pytest`

---

## Running on real data

All outputs go to `data/` (default). Each script has `--help`.

| Step | Command | Needs |
|---|---|---|
| 1 Study area | `python pipeline/01_study_area.py --rank`, then set `UPAZILAS` in `safewindow/config.py`, then `python pipeline/01_study_area.py` (or `--hdx <adm3.shp>`) | internet |
| 2A Sentinel-1 | `python pipeline/02a_sentinel1_gee.py --list`, then run without `--list` | Earth Engine |
| 2B UNOSAT | `python pipeline/02b_unosat.py <flood.shp> --date YYYY-MM-DD` (once per map) | HDX download |
| 2C MODIS | `python pipeline/02c_modis.py [--register]` | Earthdata login |
| 2D DEM (optional) | `python pipeline/02d_dem_gapfill.py --download`, then run without `--download` | Earth Engine |
| 2E Merge + go/no-go | `python pipeline/02e_merge_flood.py` | |
| 3 Roads, villages, shelters | `python pipeline/03_osm_roads_places.py` | internet |
| 3 Shelters (by hand) | copy `data/processed/shelters_candidates.csv` to `shelters_verified.csv`, keep 15–30 checked shelters, set `verified=yes`, fill `source` | people |
| 3 Population | `python pipeline/03b_population.py --worldpop-gee [--buildings]` | Earth Engine |
| 4 Rainfall | `python pipeline/04_rainfall_gpm.py` | Earth Engine |
| 9 News sheet | `python pipeline/09_validate.py --template`, then fill `data/validation/news_reports.csv` | people |
| 5–9 + app data | `python scripts/run_engine.py` | |
| App | `streamlit run app/streamlit_app.py` | |

**Earth Engine setup (once):** run `earthengine authenticate`, then set `EE_PROJECT` to your Cloud project id.
**Earthdata:** `earthaccess` asks for your login on first use.

Check every intermediate layer in **QGIS** (`data/processed/*.gpkg`, `flood/*.tif`, `flood_merged/*.tif`, `results/exit_routes.gpkg`).

### Deploying

Run the engine locally, then commit `data/app/` (small, web-ready files) and deploy `app/streamlit_app.py` on [Streamlit Community Cloud](https://share.streamlit.io). Cloud installs only `requirements.txt`, the light app dependencies. The app never recomputes anything.

---

## Method in short

1. **Flood maps** on one 20 m grid in EPSG:32646. Each pixel is `0` dry, `1` flooded or `255` unknown.
   - **Sentinel-1:** VV below an Otsu threshold *and* ≥ 3 dB darker than the Feb–Mar dry season, with slopes > 5° masked. Histograms are saved as proof.
   - **Merging sources per date:** Sentinel-1 > UNOSAT > DEM estimate > MODIS. A lower source only fills pixels still unknown.
   - **Clouds** are never treated as dry.
2. **Road cut:** check-points every 20 m along each road.
   - **Cut:** more than 20% of points are flooded.
   - **Unknown:** most points are unknown.
   - **Sensitivity test:** also run at 10% and 40%.
3. **Isolation:** remove cut roads and check whether the village's road junction still connects to a shelter. Roads with unknown status are solved both ways:
   - **Connected:** a path exists over roads *seen* open.
   - **Isolated:** no path even if every unknown road is open.
   - **Uncertain:** anything in between.
   - **Boat-dependent:** villages more than 500 m from any road.
4. **Timeline:** isolation is reported as a **range**, from the day after the last connected image to the first isolated image.
   - **Safe exit route:** the shortest open-road path on the last connected date.
   - **Aid deadline:** the earliest possible isolation day + supply days.
   - **Ranking:** earliest deadline first, then larger population.

## Code layout

```
safewindow/        engine library
  config.py        study area, thresholds, paths (SAFEWINDOW_DATA_DIR)
  flood.py         common grid, flood-map manifest, merging
  roads.py         network files, check-points, cut rule
  isolation.py     snapping, connected/isolated/uncertain, exit routes
  timeline.py      isolation range, safe exit, aid deadline, ranking
  places.py, gee.py
pipeline/          one script per guide step (01 ... 09)
scripts/           make_demo_data.py, run_engine.py
app/               Streamlit app (reads data/app only)
tests/             engine unit tests
```

## Data sources and licences

| Data | Source | Licence / terms |
|---|---|---|
| Sentinel-1 GRD | ESA Copernicus via Google Earth Engine | Copernicus open data licence |
| Flood maps FL20220525BGD | UNOSAT via HDX | see HDX dataset page |
| MODIS/VIIRS Global Flood Product (MCDWD) | NASA LANCE / LAADS DAAC | NASA open data |
| GPM IMERG V07 | NASA GES DISC via Earth Engine | NASA open data |
| NASADEM (slope mask) | NASA via Earth Engine | NASA open data |
| Copernicus DEM GLO-30 | ESA via Earth Engine | Copernicus DEM licence |
| Roads, villages, shelters | © OpenStreetMap contributors | ODbL |
| Population | WorldPop 2020 (100 m) | CC BY 4.0 |
| Buildings (optional) | Google Open Buildings v3 | CC BY 4.0 / ODbL |
| Admin boundaries | OCHA COD-AB via HDX | see HDX dataset page |

## Limitations (also on a slide)

- **Supply days is an assumption** (default 7, adjustable from 2 to 14 in the app), not a measurement. Replace the default with a sourced figure and cite it.
- **Flood maps have gaps:** Sentinel-1 revisited only every 12 days in 2022, clouds block MODIS, and radar misreads some surfaces. Days between images are ranges or labelled estimates.
- **The DEM gap-fill is a "bathtub" estimate.** It ignores embankments and connectivity.
- **OpenStreetMap roads and shelters are incomplete.** The demo shelter list is hand-checked.
- **Validation uses news reports**, which are incomplete and favour easy-to-reach places. There is no perfect ground truth.
- A road counts as cut by a fixed share of flooded check-points; a short flooded stretch on a long road can be missed. See the sensitivity table for how much this choice matters.
