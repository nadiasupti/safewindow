"""Step 5 - Which roads are cut on each flood date.

    python pipeline/05_cut_roads.py

For every road segment: check-points every 20 m, look up the merged flood map
at each one, then
  cut      more than X% of check-points flooded
  unknown  otherwise, if most check-points are unknown (cloud / no image)
  open     otherwise
X is run at 10%, 20% (main result) and 40% for the sensitivity test.

Writes data/results/road_status.csv with one row per (date, road) and one
status column per threshold: status_10, status_20, status_40.
"""
import pandas as pd
import rasterio

from safewindow import config
from safewindow.flood import Grid, merged_dates, merged_path
from safewindow.roads import classify, edge_fractions, load_network, lookup, sample_points


def status_col(t: float) -> str:
    return f"status_{round(t * 100)}"


def main():
    paths = config.get_paths().ensure()
    grid = Grid.load(paths.grid)
    _, edges = load_network(paths)
    dates = merged_dates(paths)
    if not dates:
        raise SystemExit("No merged flood maps - run pipeline/02e_merge_flood.py first.")

    edge_idx, x, y = sample_points(edges)
    print(f"{len(edges)} roads, {len(x)} check-points, {len(dates)} dates")

    out, summary = [], []
    for day in dates:
        with rasterio.open(merged_path(day, paths)) as src:
            raster = src.read(1)
        ff, fu = edge_fractions(lookup(raster, grid, x, y), edge_idx, len(edges))
        df = pd.DataFrame({"date": day, "edge_id": edges["edge_id"],
                           "frac_flooded": ff.round(3), "frac_unknown": fu.round(3)})
        row = {"date": day}
        for t in config.SENSITIVITY_THRESHOLDS:
            df[status_col(t)] = classify(ff, fu, t)
            km = edges["length_m"].groupby(df[status_col(t)].to_numpy()).sum() / 1000
            row[f"cut_km_{round(t * 100)}"] = round(km.get("cut", 0), 1)
        row["unknown_km"] = round(km.get("unknown", 0), 1)
        summary.append(row)
        out.append(df)

    pd.concat(out).to_csv(paths.road_status, index=False)
    s = pd.DataFrame(summary)
    s.to_csv(paths.results / "road_cut_summary.csv", index=False)
    print(s.to_string(index=False))
    print(f"saved {paths.road_status}")


if __name__ == "__main__":
    main()
