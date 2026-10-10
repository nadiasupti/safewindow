# SafeWindow

SafeWindow is a research prototype for estimating when villages lose all road access to a flood shelter. The project combines flood observations, road connectivity, shelter locations, rainfall, and a user-adjustable household supply assumption into a date-based isolation timeline.

> **Important:** SafeWindow is not an official warning system, evacuation planner, or emergency decision tool. Its outputs are provisional and must be checked against official alerts and local information.

## Project guide

See [PROJECT_GUIDE.md](PROJECT_GUIDE.md) for the scientific scope, data status, live-data prerequisites, validation commands, and NASA Space Challenge submission assessment.

## Quick start

### Windows demo

Run `run_demo.bat`. The launcher creates or updates the isolated Python environment, builds a deterministic synthetic package, validates it, and opens the application.

### Manual commands

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-pipeline.txt
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe scripts\build_demo.py --keep data_demo
.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py
```

## Live data

The live-data pipeline requires Earth Engine and Earthdata authentication:

```powershell
earthengine authenticate
$env:EE_PROJECT="your-project-id"
.venv\Scripts\python.exe pipeline\10_build_live_data.py
.venv\Scripts\python.exe scripts\inspect_data.py data/live
```

The project defaults to `data/live`. The synthetic package remains available in `data_demo` and is explicitly labelled as invented.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

The suite covers the road-cutting and isolation engine, date-aware routes, FloodNet dataset/checkpoint behavior, and generated app artifact validation.

## Architecture

```text
Public sources
  -> pipeline/01-10
  -> processed results
  -> pipeline/08_build_app_data.py
  -> data/live/app or data_demo/app
  -> Streamlit application
```

The separate FloodNet classifier is retained for classifier research. It is not the same model as the temporal flood segmentation pipeline.

## Scientific limitations

- Flood observations contain cloud and radar gaps.
- Dates between observations are ranges, not exact flood events.
- OSM roads and shelters are incomplete and must be verified before operational use.
- Household supply days are an assumption, not a measured field value.
- News-report validation is a sanity check, not ground truth.
- Results must not be used to make emergency decisions without official sources.

## Submission readiness

The codebase provides a complete reproducible research prototype, but it is **not yet NASA Space Challenge submission-ready**. A submission requires an audited real-world benchmark, fixed evaluation splits, independent review, source provenance, and recorded scientific metrics.

See [SUBMISSION_STATUS.md](SUBMISSION_STATUS.md) for the evidence gate and [scripts/verify_submission.py](scripts/verify_submission.py) for the submission verification command.
