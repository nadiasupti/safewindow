# SafeWindow Live Evidence Status

Generated: 2026-10-08

## Status

**Prototype data build incomplete; submission evidence not verified.**

The live pipeline produced the study area, OSM road and village data, rainfall data, and MODIS trend data. Sentinel-1 export and downstream flood processing could not complete because Earth Engine rejected the requested export with HTTP 400 after repeated attempts. The repository now rejects unsafe real-data training without DEM and uses a valid integer OSM timeout.

## Verified outputs

- `processed/study_area.gpkg`: Sunamganj Sadar, Chhatak, and Dowarabazar study area, 1,265 km².
- `processed/grid.json`: 2,473 x 2,081 pixels at 20 m resolution.
- `processed/roads.graphml`: 21,542 junctions and 24,947 road segments.
- `processed/villages.gpkg`: 16 OSM villages, hamlets, or towns.
- `processed/shelters_candidates.csv`: 50 OSM shelter candidates; these are not verified shelters.
- `processed/rainfall_daily.csv`: 42 daily observations for the configured upstream and study-area boxes.
- `processed/modis_flood_area.csv`: empty; no MODIS raster observations were downloaded.

## Evidence gap

The following required submission files are absent:

- `submission_evidence.json`
- `benchmark.csv`
- `benchmark_manifest.json`
- `model_evaluation.csv`
- `model_evaluation.json`
- `source_manifest.json`
- `science_methods.md`

No real-world benchmark, fixed split, independent evaluation, model metrics, or scientific review is currently available. The existing FloodNet benchmark evaluates a separate classifier and must not be treated as SafeWindow evidence.

## Blocked dependency

The live Sentinel-1 pipeline reached Earth Engine image computation but failed while downloading the completed image. The same image and transform succeeded in an isolated export request, while the pipeline request repeatedly returned HTTP 400. This indicates an external project/service rejection that cannot be resolved from repository code alone.

## Required next steps

1. Resolve the Earth Engine project export failure or use a project-specific export method.
2. Complete the Sentinel-1 raster and flood-merge stages.
3. Supply a region-specific benchmark with independent ground truth.
4. Run fixed temporal and geographic splits.
5. Record metrics, confusion matrix, uncertainty, and error distributions.
6. Obtain independent scientific review.
7. Complete the source manifest and methods document.
8. Build and verify the submission package with `scripts/verify_submission.py data/live`.
