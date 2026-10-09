"""Write a data and model reproducibility manifest."""
from __future__ import annotations

import argparse
from pathlib import Path

from safewindow.provenance import write_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("data", nargs="?", default=None)
    parser.add_argument("--model", type=Path, default=None)
    args = parser.parse_args()
    data = Path(args.data) if args.data else Path(__file__).resolve().parents[1] / "data" / "live"
    destination = write_manifest(data, args.model)
    print(destination)


if __name__ == "__main__":
    main()
