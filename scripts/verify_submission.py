"""Verify that a SafeWindow release has auditable scientific evidence.

This command intentionally fails for demo-only or unvalidated releases. It is
not a general code-quality checker; it checks the evidence required for a
NASA Space Challenge submission package.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_FILES = (
    "submission_evidence.json",
    "benchmark.csv",
    "benchmark_manifest.json",
    "model_evaluation.csv",
    "model_evaluation.json",
    "source_manifest.json",
    "science_methods.md",
)


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def verify(data_dir: Path) -> list[str]:
    errors: list[str] = []
    data_dir = data_dir.resolve()
    missing = [name for name in REQUIRED_FILES if not (data_dir / name).is_file()]
    if missing:
        errors.append("missing submission evidence: " + ", ".join(missing))
        return errors

    evidence = _load_json(data_dir / "submission_evidence.json")
    benchmark = _load_json(data_dir / "benchmark_manifest.json")
    evaluation = _load_json(data_dir / "model_evaluation.json")
    sources = _load_json(data_dir / "source_manifest.json")

    required_evidence = {
        "region", "study_period_start", "study_period_end", "ground_truth_source",
        "ground_truth_version", "independent_review", "submission_status",
    }
    for key in required_evidence:
        if not evidence.get(key):
            errors.append(f"submission_evidence.json is missing {key}")

    if evidence.get("submission_status") != "verified":
        errors.append("submission_status must be 'verified'")
    if not benchmark.get("independent_evaluation"):
        errors.append("benchmark_manifest.json lacks independent_evaluation")
    if benchmark.get("split_strategy") in (None, ""):
        errors.append("benchmark_manifest.json lacks split_strategy")
    if not evaluation.get("metrics"):
        errors.append("model_evaluation.json lacks metrics")
    if not sources.get("sources"):
        errors.append("source_manifest.json lacks sources")

    for filename in ("benchmark.csv", "model_evaluation.csv"):
        path = data_dir / filename
        if path.stat().st_size == 0:
            errors.append(f"{filename} is empty")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", nargs="?", default="data/live", type=Path)
    args = parser.parse_args()
    errors = verify(args.data_dir)
    if errors:
        print("SUBMISSION EVIDENCE CHECK FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print("\nThe synthetic demo is not submission evidence. Add the required files and run this command again.", file=sys.stderr)
        return 1
    print("SUBMISSION EVIDENCE CHECK PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
