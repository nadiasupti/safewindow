# SafeWindow ML training

This directory contains a compact temporal U-Net for predicting the next flood map from recent flood observations, rainfall, and DEM data.

## Important limitation

The repository's synthetic demo is invented. It is useful for testing the training pipeline, but it must not be used to make real-world flood predictions. Use real, quality-controlled Sentinel-1, rainfall, DEM, and road data for operational models.

## Local GPU

The code uses CUDA when available and falls back to CPU. It is designed for a 12 GB GPU. Use `--batch-size 4` or `8` on the first run if memory is constrained.

## Install

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
```

## Build the dataset

The demo data must first be generated using the existing pipeline:

```powershell
$env:SAFEWINDOW_DATA_DIR = "data_demo"
.\.venv\Scripts\python.exe scripts\make_demo_data.py
.\.venv\Scripts\python.exe scripts\run_engine.py
```

Then create the training dataset:

```powershell
.\.venv\Scripts\python.exe ml\prepare_dataset.py --data-dir data_demo --output ml\dataset.npz --patch-size 256
```

For real data, provide the data directory containing `processed/flood_merged/*.tif`. Rainfall should be in `processed/rainfall_daily.csv`. DEM rasters should be in `processed/dem/*.tif`. The training input uses three previous flood maps, the target date rainfall, and the target date DEM.

## Train

```powershell
.\.venv\Scripts\python.exe ml\train.py --dataset ml\dataset.npz --epochs 80 --batch-size 8
```

The best checkpoint is written to `ml/model.pt`. The current code uses the prior 3 days, so the model predicts the next available flood map.

## Data layout

- `x`: `[N, 5, H, W]` — three flood states, rainfall, DEM.
- `y`: `[N, H, W]` — next-day flood target with values `0=dry`, `1=flooded`, `255=unknown`.
- Unknown pixels are excluded from the loss.

## Real-data recommendations

1. Keep the original Sentinel-1 classification and raw VV/ VH rasters for traceability.
2. Use at least 30-60 temporal samples per area; the demo has only nine dates.
3. Split by time and geographic area, never by random pixels.
4. Include cloud masks, road masks, and date offsets.
5. Evaluate with recall for flooded pixels and IoU, not only accuracy.
6. Add a separate model for each source or use source probabilities as a label.

## Validate with the model

The training script reports validation loss and pixel accuracy. For a real model, replace the accuracy metric with flood IoU, recall, precision, and confusion matrix.

## FloodNet image classification prototype

The completed prototype classifies an entire aerial scene as flooded or non-flooded. It does not produce a pixel-level flood mask.

Run the Streamlit interface with:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app\floodnet_app.py
```

The application uses the trained checkpoint at `ml/floodnet_model.pt`. The model was evaluated on 181 held-out FloodNet images with 96.69% accuracy and 91.89% flood F1. The checkpoint is a local prototype artifact and must not be treated as an operational flood warning system.

The classifier uses real FloodNet images and labels. The original temporal U-Net remains a separate SafeWindow pipeline for future Sentinel-1 and environmental-data work.
