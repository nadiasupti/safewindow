"""Build a reproducibility manifest for SafeWindow model and data artifacts."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safewindow import config


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(data_dir: Path, model_path: Path | None = None) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "project": "SafeWindow",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "data_dir": str(data_dir),
        "data_label": "",
        "data_files": [],
        "model": None,
        "configuration": {
            "grid_res_m": config.GRID_RES_M,
            "cut_threshold": config.CUT_THRESHOLD,
            "boat_dependent_m": config.BOAT_DEPENDENT_M,
            "default_supply_days": config.DEFAULT_SUPPLY_DAYS,
        },
    }
    if (data_dir / "DATA_LABEL").exists():
        manifest["data_label"] = (data_dir / "DATA_LABEL").read_text(encoding="utf-8").strip()
    for path in sorted(data_dir.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            manifest["data_files"].append({
                "path": str(path.relative_to(data_dir)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            })
    if model_path and model_path.is_file():
        manifest["model"] = {
            "path": str(model_path),
            "sha256": sha256(model_path),
            "bytes": model_path.stat().st_size,
        }
    return manifest


def write_manifest(data_dir: Path, model_path: Path | None = None) -> Path:
    manifest_path = data_dir / "manifest.json"
    manifest_path.write_text(json.dumps(build_manifest(data_dir, model_path), indent=2), encoding="utf-8")
    return manifest_path
