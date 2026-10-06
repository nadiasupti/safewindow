# SafeWindow 🌊

**When will a flood-hit village be cut off, and when must aid arrive?**

SafeWindow gives each flood-affected village in Bangladesh's haor region three things: the date it loses its last road to safety, the last safe exit route, and a deadline for aid. It combines satellite radar flood maps with road-network analysis.

> Built for the **NASA Space Apps Challenge 2026**.
> Status: **early prototype**. The pipeline and app run end to end on synthetic demo data; real 2022 data is being prepared.
> This is a research project, not an official warning system. Always follow official alerts (BMD, FFWC, DDM).

---

## The Problem

In Sunamganj and other haor areas of Bangladesh, floods often hurt people by cutting villages off from shelters, hospitals, and aid. In 2022, floods in Sylhet and Sunamganj left millions of people stranded.

Most flood tools show **where** the water is. Very few say **when** a village loses access, or **how long** it can survive. Aid planners need that deadline.

## Our Solution

For each village, SafeWindow calculates three things:

| Output | Meaning |
|---|---|
| **Isolation date** | The first day no road path to a shelter remains, reported as a date range because satellite images have gaps |
| **Safe exit window** | The last day, and the route, a village can still use to reach a shelter |
| **Aid deadline** | Isolation date + days of food and water supply (adjustable) |

Villages are then **ranked by urgency**, so responders know who needs help first.

## How It Works

```
Satellite radar (SAR)  ──►  Flood map for each date
                                   │
OpenStreetMap roads    ──►  Road network graph
                                   │
                    Remove flooded roads for each date
                                   │
         Which villages can no longer reach any shelter?
                                   │
     Isolation date ─► Exit route ─► Aid deadline ─► Urgency ranking
```

1. **Flood maps.** Radar sees water through monsoon clouds. Every source is put on one 20 m grid (EPSG:32646), where each pixel is dry, flooded or unknown.
   - **Sentinel-1:** a pixel is flooded if VV is below an Otsu threshold *and* at least 3 dB darker than the Feb–Mar dry season. Histograms are saved as proof.
   - **Other dates:** UNOSAT maps, NASA MODIS and an optional elevation estimate fill gaps, in that order of trust.
   - **Clouds** are never treated as dry.
2. **Road graph.** Roads, villages and shelters come from OpenStreetMap, with a hand-checked shelter list for the demo area.
3. **Cut flooded roads.** Check-points sit every 20 m along each road.
   - **Cut:** more than 20% of the check-points are flooded.
   - **Sensitivity test:** the same rule is run at 10% and 40%.
4. **Isolation check.** A village is isolated when no connected path to any shelter remains. Roads hidden by cloud are solved both ways:
   - **Connected:** the village reaches a shelter using roads seen to be open.
   - **Isolated:** no path exists even if every unknown road is open.
   - **Uncertain:** anything in between.
   - **Boat-dependent:** villages more than 500 m from any road.
5. **Survival Clock.** An adjustable supply assumption (days of food and water) gives the aid deadline.
   - The deadline counts from the earliest possible isolation day.
   - Ranking puts the earliest deadline first, then the larger population.

## What the User Sees

- A map with a **date slider** that replays the flood, with villages turning red as they are cut off
- A **village panel** with isolation date, exit route, and aid deadline
- A **responder view** ranking villages by urgency
- **Bangla and English** text, plus a short SMS-style alert
- NASA **GPM rainfall** (local and upstream Meghalaya) and the **MODIS** daily flood trend

---

## Run it

### Easiest (Windows)

Double-click **`run_demo.bat`**. The first time, it creates the Python environment and builds the demo data. Then it opens the app at http://localhost:8501.

### From the terminal

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
.\.venv\Scripts\python.exe -m pip install -e .

$env:SAFEWINDOW_DATA_DIR="data_demo"     # macOS/Linux: export SAFEWINDOW_DATA_DIR=data_demo
.\.venv\Scripts\python.exe scripts\make_demo_data.py    # invented terrain, roads, flood
.\.venv\Scripts\python.exe scripts\run_engine.py        # steps 2e, 5, 6, 7, 9, 8
.\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
```

The demo data is **entirely made up**, and the app shows a banner saying so. With conda/Miniforge use `conda env create -f environment.yml`.

Run the tests with `pytest`.

### Running on real data

Outputs go to `data/` (the default when `SAFEWINDOW_DATA_DIR` is not set). Each script has `--help`.

| Step | Command | Needs |
|---|---|---|
| 1 Study area | `python pipeline/01_study_area.py --rank`, set `UPAZILAS` in `safewindow/config.py`, then `python pipeline/01_study_area.py` (or `--hdx <adm3.shp>`) | internet |
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

## Project Structure

```
safewindow/            engine library
  config.py            study area, thresholds, paths (SAFEWINDOW_DATA_DIR)
  flood.py             common grid, flood-map manifest, merging sources
  roads.py             network files, check-points, cut rule
  isolation.py         snapping, connected / isolated / uncertain, exit routes
  timeline.py          isolation range, safe exit, aid deadline, ranking
  places.py, gee.py
pipeline/              one script per build step (01 ... 09)
scripts/               make_demo_data.py, run_engine.py
app/streamlit_app.py   Streamlit web app (reads data/app only)
tests/                 engine unit tests
safewindow_build_guide.md   full build plan
run_demo.bat           one-click demo for Windows
```

## Roadmap

- [x] Project idea, method, and build plan
- [x] Pipeline code for every step, engine and app working on synthetic demo data
- [ ] Confirm flood maps for 4–5 dates and a usable road graph (go/no-go)
- [ ] Compute isolation dates on real data and sanity-check in QGIS
- [ ] Hand-checked shelter list and population numbers
- [ ] Validate against news and public reports of isolated areas
- [ ] Deploy the app online
- [ ] Optional: test whether rainfall predicts flood extent a few days ahead

## Validation Plan

We will compare predicted isolation dates with news and public reports of isolated areas, and report the error openly (`pipeline/09_validate.py`). There is no perfect ground truth, and we will say so.

## Data Sources

**NASA**
- NASA-ISRO NISAR (synthetic aperture radar), subject to data availability
- GPM IMERG (rainfall)
- MODIS Global Flood Product (MCDWD)
- NASADEM (slope mask)
- NASA Worldview (visual context)

**Partner and open data**
- ESA Sentinel-1 (radar)
- UNOSAT flood extent maps
- OpenStreetMap (roads, villages, shelters)
- WorldPop (population)
- Copernicus DEM (elevation)

| Data | Source | Licence / terms |
|---|---|---|
| Sentinel-1 GRD | ESA Copernicus via Google Earth Engine | Copernicus open data licence |
| Flood maps FL20220525BGD | UNOSAT via HDX | see HDX dataset page |
| MODIS/VIIRS Global Flood Product (MCDWD) | NASA LANCE / LAADS DAAC | NASA open data |
| GPM IMERG V07 | NASA GES DISC via Earth Engine | NASA open data |
| NASADEM | NASA via Earth Engine | NASA open data |
| Copernicus DEM GLO-30 | ESA via Earth Engine | Copernicus DEM licence |
| Roads, villages, shelters | © OpenStreetMap contributors | ODbL |
| Population | WorldPop 2020 (100 m) | CC BY 4.0 |
| Buildings (optional) | Google Open Buildings v3 | CC BY 4.0 / ODbL |
| Admin boundaries | OCHA COD-AB via HDX | see HDX dataset page |

## Tech Stack

Python · Google Earth Engine · osmnx · networkx · geopandas · rasterio · Streamlit · folium · QGIS

## Limitations

- **Supply duration is an assumption** (default 7 days, adjustable from 2 to 14), not measured data.
- **Flood maps have gaps** from clouds and radar errors. Days between satellite images are ranges or labelled estimates.
- **The elevation gap-fill is a "bathtub" estimate.** It ignores embankments.
- **OpenStreetMap roads and shelters may be incomplete**, so we use a hand-checked shelter list for the demo area.
- **A road counts as cut** by a fixed share of flooded check-points. The sensitivity table shows how much this choice matters.
- This is a research prototype, not an official warning system.

## What Makes It Different

The output is a **deadline**, not a risk map. To our knowledge, no existing tool combines satellite flood data, road-network analysis, and supply timing for Bangladesh in this way. We have not searched exhaustively.

## Team DeltaSentinels

**Team members:**
- Farhan Labib
- Nadia Yeasmin

## License

MIT License. See [LICENSE](LICENSE).
