"""Step 6 - Which villages are isolated from every shelter, per date.

    python pipeline/06_isolation.py

  1. Snap each village and shelter to its nearest road junction. Villages more
     than 500 m from any road are 'boat_dependent'.
  2. For each date, remove cut roads and check which villages can still reach
     a shelter (see safewindow/isolation.py for how 'unknown' roads are handled).

Writes data/results/:
  village_status.csv   threshold, date, village_id, status, dist_to_shelter_m, nearest_shelter_id
  villages_snapped.csv, shelters_snapped.csv
  sensitivity.csv      village counts per status, date and threshold
"""
import pandas as pd

from safewindow import config
from safewindow.isolation import snap_shelters, snap_villages, status_for_date
from safewindow.places import load_shelters, load_villages
from safewindow.roads import load_network


def main():
    paths = config.get_paths().ensure()
    nodes, edges = load_network(paths)
    villages = snap_villages(load_villages(paths), nodes)
    shelters = snap_shelters(load_shelters(paths), nodes)
    villages.drop(columns="geometry").to_csv(paths.results / "villages_snapped.csv", index=False)
    shelters.drop(columns="geometry").to_csv(paths.results / "shelters_snapped.csv", index=False)

    print(f"{len(villages)} villages ({villages['boat_dependent'].sum()} boat-dependent, > "
          f"{config.BOAT_DEPENDENT_M} m from a road); {len(shelters)} shelters")
    far = shelters[~shelters["road_reachable"]]
    if len(far):
        print(f"  WARNING: {len(far)} shelters > {config.SHELTER_SNAP_MAX_M} m from any road are ignored: "
              f"{far['name'].tolist()}")

    rs = pd.read_csv(paths.road_status, dtype={"edge_id": str})
    out = []
    for t in config.SENSITIVITY_THRESHOLDS:
        col = f"status_{round(t * 100)}"
        for day, grp in rs.groupby("date"):
            st = status_for_date(edges, grp.set_index("edge_id")[col], villages, shelters)
            out.append(st.assign(threshold=t, date=day))
    vs = pd.concat(out)[["threshold", "date", "village_id", "status", "dist_to_shelter_m", "nearest_shelter_id"]]
    vs.to_csv(paths.village_status, index=False)

    sens = (vs.groupby(["threshold", "date", "status"]).size().unstack(fill_value=0).reset_index())
    sens.to_csv(paths.sensitivity, index=False)
    print(sens.to_string(index=False))
    print(f"saved {paths.village_status}")


if __name__ == "__main__":
    main()
