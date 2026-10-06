"""Unit tests for the engine on a tiny hand-made network.

    A ---- B ---- C ---- S(shelter)
                  |
                  D        V1 at A, V2 at D, V3 far from every road
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from safewindow import config
from safewindow.flood import Grid
from safewindow.isolation import routes_to_shelters, snap_shelters, snap_villages, status_for_date
from safewindow.roads import classify, edge_fractions, lookup, sample_points
from safewindow.timeline import isolation_range_text, summarise

XY = {"A": (0, 0), "B": (1000, 0), "C": (2000, 0), "S": (3000, 0), "D": (2000, -1000)}
EDGES = [("AB", "A", "B"), ("BC", "B", "C"), ("CS", "C", "S"), ("CD", "C", "D")]


@pytest.fixture
def net():
    nodes = gpd.GeoDataFrame({"node_id": list(XY)}, geometry=[Point(p) for p in XY.values()], crs=config.CRS)
    edges = gpd.GeoDataFrame({
        "edge_id": [e for e, *_ in EDGES], "u": [u for _, u, _ in EDGES], "v": [v for *_, v in EDGES],
        "length_m": [1000.0] * len(EDGES)},
        geometry=[LineString([XY[u], XY[v]]) for _, u, v in EDGES], crs=config.CRS)
    villages = gpd.GeoDataFrame({"village_id": ["V1", "V2", "V3"], "name": ["One", "Two", "Three"],
                                 "population": [100, 500, 50]},
                                geometry=[Point(10, 10), Point(2000, -1050), Point(1000, 3000)], crs=config.CRS)
    shelters = gpd.GeoDataFrame({"shelter_id": ["S1"], "name": ["School"]},
                                geometry=[Point(3010, 0)], crs=config.CRS)
    return nodes, edges, snap_villages(villages, nodes), snap_shelters(shelters, nodes)


def test_snap_and_boat_dependent(net):
    _, _, v, s = net
    assert v.set_index("village_id")["node_id"].to_dict() == {"V1": "A", "V2": "D", "V3": "B"}
    assert v.set_index("village_id")["boat_dependent"].to_dict() == {"V1": False, "V2": False, "V3": True}
    assert s["node_id"].iloc[0] == "S"


def test_status_open_cut_unknown(net):
    _, edges, v, s = net
    rs = pd.Series({"AB": "open", "BC": "open", "CS": "open", "CD": "open"})
    st = status_for_date(edges, rs, v, s).set_index("village_id")
    assert st["status"].to_dict() == {"V1": "connected", "V2": "connected", "V3": "boat_dependent"}
    assert st.loc["V1", "dist_to_shelter_m"] == 3000
    assert st.loc["V1", "nearest_shelter_id"] == "S1"

    rs["BC"] = "cut"          # V1 loses its only road; V2 still fine
    st = status_for_date(edges, rs, v, s).set_index("village_id")["status"]
    assert st["V1"] == "isolated" and st["V2"] == "connected"

    rs["BC"] = "unknown"      # cloud over BC -> cannot tell
    assert status_for_date(edges, rs, v, s).set_index("village_id").loc["V1", "status"] == "uncertain"


def test_route(net):
    nodes, edges, v, s = net
    rs = pd.Series("open", index=edges["edge_id"])
    found = routes_to_shelters(edges, nodes, rs, {"V1": "A", "V2": "D"}, s)
    assert found["V1"][0] == "S1" and found["V1"][1] == 3000
    assert found["V1"][2].length == pytest.approx(3000)
    rs["CD"] = "cut"
    assert "V2" not in routes_to_shelters(edges, nodes, rs, {"V2": "D"}, s)


def test_cut_rule():
    ff = np.array([0.0, 0.25, 0.1, 0.1, 0.5])
    fu = np.array([0.0, 0.0, 0.8, 0.3, 0.5])
    assert classify(ff, fu, 0.2).tolist() == ["open", "cut", "unknown", "open", "cut"]


def test_sampling_and_lookup():
    grid = Grid(xmin=0, ymax=100, width=10, height=10, res=10)
    raster = np.zeros((10, 10), dtype="uint8")
    raster[:, 5:] = config.FLOODED          # east half flooded
    edges = gpd.GeoDataFrame(geometry=[LineString([(0, 50), (100, 50)]), LineString([(5, 0), (5, 100)])],
                             crs=config.CRS)
    idx, x, y = sample_points(edges, spacing=20)
    assert np.bincount(idx).tolist() == [6, 6]
    vals = lookup(raster, grid, x, y)
    ff, fu = edge_fractions(vals, idx, 2)
    # check-points at x = 0,20,40,60,80,100: 60 and 80 flooded; x=100 is on the
    # grid's outer edge -> outside -> unknown
    assert ff[1] == 0 and ff[0] == pytest.approx(2 / 6)
    assert fu[0] == pytest.approx(1 / 6)
    assert lookup(raster, grid, np.array([-5.0]), np.array([50.0]))[0] == config.UNKNOWN


def test_timeline():
    villages = pd.DataFrame({"village_id": ["a", "b", "c", "d"], "name": list("abcd"),
                             "population": [10, 20, 30, 40]})
    dates = ["2022-06-07", "2022-06-14", "2022-06-19"]
    status = pd.DataFrame({
        "village_id": ["a"] * 3 + ["b"] * 3 + ["c"] * 3 + ["d"] * 3,
        "date": dates * 4,
        "status": ["connected", "isolated", "isolated",      # a: cut between 8 and 14 Jun
                   "isolated", "isolated", "connected",      # b: isolated already on first image
                   "connected", "connected", "connected",    # c: never
                   "connected", "connected", "isolated"],    # d: cut between 15 and 19 Jun
    })
    s = summarise(status, villages, supply_days=7).set_index("village_id")
    assert s.loc["a", "isolated_from_earliest"] == pd.Timestamp("2022-06-08")
    assert s.loc["a", "safe_exit_date"] == pd.Timestamp("2022-06-07")
    assert s.loc["a", "aid_deadline"] == pd.Timestamp("2022-06-15")
    assert pd.isna(s.loc["b", "safe_exit_date"]) and s.loc["b", "reconnected"] == pd.Timestamp("2022-06-19")
    assert s.loc["c", "outcome"] == "never_isolated" and pd.isna(s.loc["c", "urgency_rank"])
    # earliest deadline first: b (7 Jun + 7), a (8 Jun + 7), d (15 Jun + 7)
    assert s["urgency_rank"].dropna().sort_values().index.tolist() == ["b", "a", "d"]
    assert isolation_range_text(s.loc["a"].to_dict() | {"outcome": "isolated"}) == "isolated between 08 Jun and 14 Jun"
    assert isolation_range_text(s.loc["b"]) == "isolated on or before 07 Jun"
