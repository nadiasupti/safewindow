"""Which villages can still reach a shelter by road (Step 6).

Roads with status 'unknown' (cloud / no image) are handled honestly by
solving the network twice:
  pessimistic graph: only roads seen to be open
  optimistic graph : every road not seen to be cut
A village is 'connected' if it reaches a shelter in the pessimistic graph,
'isolated' if it cannot even in the optimistic graph, and 'uncertain' in
between. Villages more than BOAT_DEPENDENT_M from any road are
'boat_dependent'.
"""
from __future__ import annotations

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely

from . import config
from .roads import build_graph


def snap(points: gpd.GeoSeries, nodes: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Nearest road node id and distance (m) for each point."""
    tree = shapely.STRtree(nodes.geometry.to_numpy())
    (src, idx), dist = tree.query_nearest(points.to_numpy(), return_distance=True, all_matches=False)
    order = np.argsort(src)
    return nodes["node_id"].to_numpy()[idx[order]], dist[order]


def snap_villages(villages: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    v = villages.copy()
    v["node_id"], v["snap_dist_m"] = snap(v.geometry, nodes)
    v["boat_dependent"] = v["snap_dist_m"] > config.BOAT_DEPENDENT_M
    return v


def snap_shelters(shelters: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    s = shelters.copy()
    s["node_id"], s["snap_dist_m"] = snap(s.geometry, nodes)
    s["road_reachable"] = s["snap_dist_m"] <= config.SHELTER_SNAP_MAX_M
    return s


def reachable_from(g: nx.Graph, sources) -> set:
    """All nodes in the same connected group as at least one source."""
    seen: set = set()
    for s in sources:
        if s in g and s not in seen:
            seen |= nx.node_connected_component(g, s)
    return seen


def shelter_distances(g: nx.Graph, shelter_nodes) -> tuple[dict, dict]:
    """Shortest road distance from every reachable node to its nearest shelter,
    and the path (node list, starting at the shelter)."""
    src = [s for s in set(shelter_nodes) if s in g]
    if not src:
        return {}, {}
    return nx.multi_source_dijkstra(g, src, weight="length_m")


def status_for_date(edges: pd.DataFrame, road_status: pd.Series,
                    villages: gpd.GeoDataFrame, shelters: gpd.GeoDataFrame) -> pd.DataFrame:
    """Village status for one date.

    road_status: Series indexed by edge_id with values open / cut / unknown.
    villages / shelters: outputs of snap_villages / snap_shelters."""
    status = road_status.reindex(edges["edge_id"]).fillna("unknown")
    open_pes = status.index[status == "open"]
    open_opt = status.index[status != "cut"]
    g_pes, g_opt = build_graph(edges, open_pes), build_graph(edges, open_opt)

    shelter_nodes = shelters.loc[shelters["road_reachable"], "node_id"].tolist()
    reach_opt = reachable_from(g_opt, shelter_nodes)
    dist, paths = shelter_distances(g_pes, shelter_nodes)
    shelter_by_node = shelters.drop_duplicates("node_id").set_index("node_id")["shelter_id"]

    rows = []
    for vid, node, boat in villages[["village_id", "node_id", "boat_dependent"]].itertuples(index=False):
        if boat:
            st = "boat_dependent"
        elif node in dist:
            st = "connected"
        elif node not in reach_opt:
            st = "isolated"
        else:
            st = "uncertain"
        rows.append({
            "village_id": vid, "status": st,
            "dist_to_shelter_m": round(dist[node], 1) if node in dist else np.nan,
            "nearest_shelter_id": shelter_by_node.get(paths[node][0]) if node in dist else None,
        })
    return pd.DataFrame(rows)


def routes_to_shelters(edges: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame, road_status: pd.Series,
                       village_nodes: dict, shelters: gpd.GeoDataFrame) -> dict:
    """Shortest path over roads seen to be open, from each village to its
    nearest shelter, on one date.

    village_nodes: {village_id: node_id}. Returns {village_id: (shelter_id,
    length_m, LineString)} for villages that can reach a shelter."""
    status = road_status.reindex(edges["edge_id"]).fillna("unknown")
    g = build_graph(edges, status.index[status == "open"])
    dist, paths = shelter_distances(g, shelters.loc[shelters["road_reachable"], "node_id"])
    geom_by_id = edges.set_index("edge_id").geometry
    node_geom = nodes.set_index("node_id").geometry
    shelter_by_node = shelters.drop_duplicates("node_id").set_index("node_id")["shelter_id"]

    out = {}
    for vid, node in village_nodes.items():
        if node not in dist:
            continue
        path = paths[node][::-1]   # village -> shelter
        parts = [geom_by_id[g[a][b]["edge_id"]] for a, b in zip(path[:-1], path[1:])]
        if parts:
            line = shapely.line_merge(shapely.MultiLineString(parts))
        else:   # village and shelter share a junction
            line = shapely.LineString([node_geom[node], node_geom[node]])
        out[vid] = (shelter_by_node[path[-1]], float(dist[node]), line)
    return out
