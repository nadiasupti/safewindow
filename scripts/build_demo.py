"""Build and validate a complete SafeWindow demo package in a temporary directory."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=Path, help="keep the generated package at this path")
    parser.add_argument("--launch", action="store_true", help="launch Streamlit after validation")
    args = parser.parse_args()

    temporary = tempfile.mkdtemp(prefix="safewindow-demo-")
    data_dir = Path(temporary) / "data_demo"
    env = os.environ.copy()
    env["SAFEWINDOW_DATA_DIR"] = str(data_dir)

    try:
        print(f"Building demo data in {data_dir}")
        run([sys.executable, str(ROOT / "scripts" / "make_demo_data.py")], env=env)
        run([sys.executable, str(ROOT / "scripts" / "run_engine.py")], env=env)

        from safewindow.validation import validate_app_dataset

        validation = validate_app_dataset(data_dir / "app")
        if not validation["valid"]:
            raise RuntimeError("Generated app data failed validation: " + "; ".join(validation["errors"]))

        print(f"Validated complete demo package: {validation['files']} files")
        if args.keep:
            destination = args.keep.resolve()
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(data_dir, destination)
            print(f"Kept package at {destination}")
        if args.launch:
            subprocess.run(
                [sys.executable, "-m", "streamlit", "run", "app/streamlit_app.py", "--server.headless", "true"],
                cwd=ROOT,
                env={**env, "SAFEWINDOW_DATA_DIR": str(data_dir)},
                check=True,
            )
    finally:
        if args.keep is None:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    main()
