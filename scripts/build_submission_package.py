"""Build a submission package from verified evidence and a production app artifact.

The package is intentionally strict: it refuses to copy a synthetic demo or an
unverified live directory into the submission output.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path, help="verified data directory")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "safewindow-submission")
    args = parser.parse_args()

    evidence_dir = args.data_dir.resolve()
    output = args.output.resolve()
    required = (
        "submission_evidence.json", "benchmark.csv", "benchmark_manifest.json",
        "model_evaluation.csv", "model_evaluation.json", "source_manifest.json",
        "science_methods.md",
    )
    missing = [name for name in required if not (evidence_dir / name).is_file()]
    if missing:
        print("Submission package build failed: missing evidence files: " + ", ".join(missing), file=sys.stderr)
        return 1

    evidence = json.loads((evidence_dir / "submission_evidence.json").read_text(encoding="utf-8"))
    if evidence.get("submission_status") != "verified":
        print("Submission package build failed: evidence status is not verified", file=sys.stderr)
        return 1
    if not evidence.get("independent_review"):
        print("Submission package build failed: independent review is not recorded", file=sys.stderr)
        return 1
    if not (evidence_dir / "app" / "meta.json").is_file():
        print("Submission package build failed: production app artifact is missing", file=sys.stderr)
        return 1

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for name in required:
        shutil.copy2(evidence_dir / name, output / name)
    shutil.copytree(evidence_dir / "app", output / "app")
    shutil.copy2(evidence_dir / "manifest.json", output / "manifest.json")
    print(f"Submission package created at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
