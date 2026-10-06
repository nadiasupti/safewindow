"""Step 9 - Compare model isolation dates with places reported cut off in June 2022.

    python pipeline/09_validate.py --template   # creates data/validation/news_reports.csv to fill in
    python pipeline/09_validate.py              # match reports to villages and score

news_reports.csv columns (one row per report, aim for 20-40):
  place_name, place_name_bn, upazila, date_reported (YYYY-MM-DD),
  reported_isolated (yes / no), source_name, source_url, village_id, notes
Fill village_id by hand when the automatic name match is wrong or missing.

Outputs data/results/validation.csv and prints:
  * hit table: model isolated vs. report says isolated
  * date error in days: model's first isolated date minus the report date
    (positive = model was late), and how often the report falls inside the
    model's isolation range

There is no perfect ground truth: news reports are incomplete and mostly cover
easy-to-reach places. Say this next to every number.
"""
import argparse
import difflib

import pandas as pd

from safewindow import config

COLS = ["place_name", "place_name_bn", "upazila", "date_reported", "reported_isolated",
        "source_name", "source_url", "village_id", "notes"]


def match(name: str, choices: dict) -> tuple[str | None, float]:
    best = difflib.get_close_matches(str(name).lower(), list(choices), n=1, cutoff=0.75)
    if not best:
        return None, 0.0
    return choices[best[0]], difflib.SequenceMatcher(None, str(name).lower(), best[0]).ratio()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", action="store_true")
    args = ap.parse_args()
    paths = config.get_paths().ensure()

    if args.template:
        paths.validation_reports.parent.mkdir(parents=True, exist_ok=True)
        if paths.validation_reports.exists():
            raise SystemExit(f"{paths.validation_reports} already exists - not overwriting")
        pd.DataFrame(columns=COLS).to_csv(paths.validation_reports, index=False)
        return print(f"created {paths.validation_reports}")

    rep = pd.read_csv(paths.validation_reports, dtype=str).fillna("")
    s = pd.read_csv(paths.village_summary, dtype={"village_id": str},
                    parse_dates=["first_isolated", "isolated_from_earliest"])
    names = {str(n).lower(): vid for n, vid in zip(s["name"], s["village_id"])}

    rows = []
    for r in rep.itertuples(index=False):
        vid, how = r.village_id or None, "manual"
        if not vid:
            vid, score = match(r.place_name, names)
            how = f"auto ({score:.2f})" if vid else "no match"
        row = r._asdict() | {"village_id": vid, "match": how}
        if vid and vid in set(s["village_id"]):
            v = s[s["village_id"] == vid].iloc[0]
            row.update(model_name=v["name"], model_outcome=v["outcome"],
                       model_isolated=v["outcome"] == "isolated")
            if v["outcome"] == "isolated" and r.date_reported:
                d = pd.Timestamp(r.date_reported)
                lo, hi = v["isolated_from_earliest"], v["first_isolated"]
                row["error_days"] = (hi - d).days
                row["report_in_range"] = lo <= d <= hi
                row["days_outside_range"] = 0 if lo <= d <= hi else min(abs((lo - d).days), abs((hi - d).days))
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(paths.validation_results, index=False)

    matched = out[out["village_id"].notna() & out.get("model_outcome", pd.Series(dtype=str)).notna()]
    print(f"{len(rep)} reports, {len(matched)} matched to a model village")
    print("\nAuto matches to check by hand:")
    print(out[out["match"].str.startswith("auto")][["place_name", "model_name", "match"]].to_string(index=False))
    if len(matched):
        rep_iso = matched["reported_isolated"].str.lower().isin(["yes", "y", "true", "1", ""])
        print("\nModel isolated vs. report says isolated:")
        print(pd.crosstab(matched["model_isolated"].rename("model isolated"), rep_iso.rename("report isolated")))
        err = matched["error_days"].dropna() if "error_days" in matched else pd.Series(dtype=float)
        if len(err):
            print(f"\nDate error (model first isolated - report date), n={len(err)}: "
                  f"mean {err.mean():+.1f} d, mean absolute {err.abs().mean():.1f} d, median {err.median():+.0f} d")
            print(f"Report date inside model's isolation range: {matched['report_in_range'].mean() * 100:.0f}%")
    print("\nReminder: news reports are incomplete and favour easy-to-reach places; "
          "this is a sanity check, not ground truth.")


if __name__ == "__main__":
    main()
