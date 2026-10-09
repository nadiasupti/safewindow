# SafeWindow Project Guide

## Mission

SafeWindow is a research prototype for estimating when villages in Sunamganj, Bangladesh, lose all road access to a flood shelter. It combines flood observations, road accessibility, shelter locations, rainfall, and a household-supply assumption into a date-based isolation timeline.

The project does **not** provide an official warning, evacuation order, or emergency decision.

## What is complete

- Deterministic synthetic demo data for local development.
- Flood raster merge and road-cut analysis.
- Village isolation and shelter-route analysis.
- Survival Clock and date-aware route calculations.
- English and Bengali Streamlit interface.
- Current public-data pipeline for MODIS, Sentinel-1, GPM IMERG, and OSM.
- Source provenance, hashes, and output validation.
- Regression tests for engine behavior, route availability, classifier prediction, and app artifacts.

## Data status

- **Synthetic demo:** invented terrain, roads, flood, villages, and shelters. Clearly labelled as synthetic.
- **Live data:** currently requires Earth Engine and Earthdata authentication, a configured project ID, and a successful live source build.
- **No source should be treated as ground truth:** flood maps have cloud/radar gaps, OSM is incomplete, and the supply-day value is an assumption.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe scripts\build_demo.py --keep data_demo
.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

On Windows, run `run_demo.bat`.

## Live data

```powershell
earthengine authenticate
$env:EE_PROJECT="your-project-id"
.venv\Scripts\python.exe pipeline\10_build_live_data.py
.venv\Scripts\python.exe scripts\inspect_data.py data/live
```

The live pipeline writes to `data/live/app` and uses `data/live` by default. It should not be run until Earth Engine and Earthdata credentials have been configured.

## Validation

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\inspect_data.py data_demo
```

## Scientific limitations

- Flood status is inferred from incomplete observations and is not a direct ground truth.
- Dates between observations are ranges, not exact flood events.
- Shelter and road coverage depends on OSM and manual verification.
- The Supply Day value is user-adjustable and must not be interpreted as a measured household value.
- Evaluation results are nuanced by source, date, and location.
- The application is a research prototype, not an official emergency system.

## NASA Space Challenge submission status

The repository has a complete reproducible prototype and evidence of end-to-end operation. It is not submission-ready as a NASA Space Challenge project because the current project lacks a documented scientific benchmark, validated real-world dataset, independent evaluation, source provenance, and a complete live-data region-specific assessment.

A verified submission release must pass:

```powershell
.venv\Scripts\python.exe scripts\verify_submission.py data/live
.venv\Scripts\python.exe scripts\build_submission_package.py data/live
```

The verifier intentionally fails for demo-only or unverified data. See [SUBMISSION_STATUS.md](SUBMISSION_STATUS.md) for the full evidence requirements.
