# SafeWindow Submission Status

## Status

**Prototype ready; scientific submission not verified.**

The repository contains a working, reproducible research prototype. It does not yet contain the evidence required to claim that SafeWindow is ready for NASA Space Challenge submission.

## What is implemented

- Date-aware road-isolation analysis.
- Flood, rainfall, road, shelter, and population processing.
- English and Bengali Streamlit interface.
- Synthetic demo package.
- Source provenance and artifact hashes.
- Automated code and artifact tests.
- A live-data build pipeline.

## Required evidence

A submission release must contain all of the following:

1. A versioned, region-specific benchmark with independent ground-truth labels.
2. Fixed temporal and geographic evaluation splits.
3. Raw benchmark and evaluation tables.
4. Reproducible model training and evaluation commands.
5. Metrics, confusion matrix, uncertainty, and error distributions.
6. Independent scientific review and reviewer contact information.
7. A complete source manifest with collection identifiers, dates, licenses, and processing parameters.
8. A documented method that explains all assumptions and limitations.
9. A deployment package built from the verified evidence directory.

## Evidence gate

Run the following command after producing a verified release:

```powershell
.venv\Scripts\python.exe scripts\verify_submission.py data/live
```

The command exits with status 1 until every required evidence file exists and the submission status is explicitly `verified`.

## Current evidence status

| Requirement | Status |
|---|---|
| Working prototype | Complete |
| Synthetic demo | Complete, but not scientific evidence |
| Real-region benchmark | Missing |
| Independent evaluation | Missing |
| Fixed splits | Missing |
| Model metrics and confusion matrix | Missing |
| Source provenance | Incomplete |
| Independent review | Missing |
| Submission deployment package | Missing |

## Scientific claims that must not be made

Do not describe the synthetic demo as real-world validation. Do not claim model accuracy, flood performance, or operational readiness without the corresponding audited benchmark and metrics.
