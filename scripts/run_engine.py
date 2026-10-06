"""Run the engine steps in order once the inputs exist:
merge flood maps -> cut roads -> isolation -> timeline -> validation -> app data.

    python scripts/run_engine.py
    python scripts/run_engine.py --from 06     # restart from a later step
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ["02e_merge_flood", "05_cut_roads", "06_isolation", "07_timeline", "09_validate", "08_build_app_data"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default="02e")
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    from safewindow import config
    paths = config.get_paths()

    started = False
    for step in STEPS:
        started = started or step.startswith(args.start)
        if not started:
            continue
        if step == "09_validate" and not paths.validation_reports.exists():
            print(f"== skipping {step}: no {paths.validation_reports}", flush=True)
            continue
        print(f"\n== {step}  (data: {paths.data})", flush=True)
        r = subprocess.run([sys.executable, str(ROOT / "pipeline" / f"{step}.py")], env=os.environ, cwd=ROOT)
        if r.returncode:
            sys.exit(f"{step} failed")


if __name__ == "__main__":
    main()
