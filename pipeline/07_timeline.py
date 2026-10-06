"""Step 7 - Isolation date range, safe exit window + route, aid deadline, ranking.

    python pipeline/07_timeline.py

Uses the main threshold (config.CUT_THRESHOLD) and writes data/results/:
  village_summary.csv     one row per village (see safewindow/timeline.py)
  exit_routes.gpkg        route to the nearest shelter on the last safe exit date
  sensitivity_summary.csv how isolation results change at 10% / 20% / 40%
All of this is computed ahead of time; the app only reads these files.
"""
import geopandas as gpd
import pandas as pd

from safewindow import config
from safewindow.isolation import routes_to_shelters
from safewindow.places import load_shelters, load_villages
from safewindow.roads import load_network
from safewindow.timeline import isolation_range_text, summarise


def sensitivity(vs: pd.DataFrame, villages: pd.DataFrame) -> pd.DataFrame:
    main = summarise(vs[vs["threshold"] == config.CUT_THRESHOLD], villages).set_index("village_id")
    rows = []
    for t in config.SENSITIVITY_THRESHOLDS:
        s = summarise(vs[vs["threshold"] == t], villages).set_index("village_id")
        both = s.index[(s["outcome"] == "isolated") & (main["outcome"].reindex(s.index) == "isolated")]
        shift = (s.loc[both, "first_isolated"] - main.loc[both, "first_isolated"]).dt.days
        rows.append({"threshold": t, "villages_isolated": int((s["outcome"] == "isolated").sum()),
                     "people_isolated": int(s.loc[s["outcome"] == "isolated", "population"].fillna(0).sum()),
                     "mean_shift_days_vs_main": round(shift.mean(), 2) if len(shift) else None,
                     "villages_changed_outcome": int((s["outcome"] != main["outcome"].reindex(s.index)).sum())})
    return pd.DataFrame(rows)


def main():
    paths = config.get_paths().ensure()
    nodes, edges = load_network(paths)
    villages = load_villages(paths)
    snapped = pd.read_csv(paths.results / "villages_snapped.csv", dtype={"village_id": str, "node_id": str})
    shelters = load_shelters(paths).merge(
        pd.read_csv(paths.results / "shelters_snapped.csv", dtype={"shelter_id": str, "node_id": str})
        [["shelter_id", "node_id", "road_reachable"]], on="shelter_id")
    vs = pd.read_csv(paths.village_status, dtype={"village_id": str, "nearest_shelter_id": str})

    summary = summarise(vs[vs["threshold"] == config.CUT_THRESHOLD], villages)
    summary["isolation_range"] = summary.apply(isolation_range_text, axis=1)

    # exit routes: one shortest-path search per safe-exit date
    rs = pd.read_csv(paths.road_status, dtype={"edge_id": str})
    col = f"status_{round(config.CUT_THRESHOLD * 100)}"
    node_of = snapped.set_index("village_id")["node_id"]
    routes = []
    exits = summary.dropna(subset=["safe_exit_date"])
    for day, grp in exits.groupby("safe_exit_date"):
        d = pd.Timestamp(day).strftime("%Y-%m-%d")
        road_status = rs[rs["date"] == d].set_index("edge_id")[col]
        found = routes_to_shelters(edges, nodes, road_status, node_of[grp["village_id"]].to_dict(), shelters)
        routes += [{"village_id": v, "date": d, "shelter_id": s, "length_m": round(L), "geometry": g}
                   for v, (s, L, g) in found.items()]
    routes = gpd.GeoDataFrame(routes, geometry="geometry", crs=config.CRS) if routes else \
        gpd.GeoDataFrame(columns=["village_id", "date", "shelter_id", "length_m", "geometry"],
                         geometry="geometry", crs=config.CRS)
    names = shelters.set_index("shelter_id")["name"]
    routes["shelter_name"] = routes["shelter_id"].map(names)
    routes.to_file(paths.exit_routes, driver="GPKG")

    summary = summary.merge(routes[["village_id", "shelter_id", "shelter_name", "length_m"]]
                            .rename(columns={"length_m": "exit_route_m", "shelter_id": "exit_shelter_id",
                                             "shelter_name": "exit_shelter"}), on="village_id", how="left")
    summary.to_csv(paths.village_summary, index=False)

    sens = sensitivity(vs, villages)
    sens.to_csv(paths.results / "sensitivity_summary.csv", index=False)

    print(summary["outcome"].value_counts().to_string())
    print("\nTop 10 most urgent:")
    print(summary.head(10)[["urgency_rank", "name", "population", "isolation_range", "aid_deadline",
                            "exit_shelter"]].to_string(index=False))
    print("\nSensitivity:")
    print(sens.to_string(index=False))


if __name__ == "__main__":
    main()
