"""Inspect a SafeWindow data directory without modifying it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from safewindow import config
from safewindow.validation import validate_app_dataset


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", nargs="?", default=None)
    args = parser.parse_args()
    data = Path(args.data) if args.data else config.get_paths().data
    app = data / "app"
    print(f"Data directory: {data}")
    if not app.is_dir():
        print("App package: missing")
        return
    validation = validate_app_dataset(app)
    print("App package:", "VALID" if validation["valid"] else "INVALID")
    print("Files:", validation["files"])
    if validation["warnings"]:
        print("Warnings:")
        for warning in validation["warnings"]:
            print(" -", warning)
    if validation["errors"]:
        print("Errors:")
        for error in validation["errors"]:
            print(" -", error)
    meta = app / "meta.json"
    if meta.exists():
        payload = json.loads(meta.read_text(encoding="utf-8"))
        print("Dates:", len(payload.get("dates", [])))
        print("Data label:", payload.get("data_label", ""))


if __name__ == "__main__":
    main()
