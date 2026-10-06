"""Road network and road cutting (Steps 3 and 5).

The road network is stored as two plain files so the engine does not need
osmnx at runtime:
  road_nodes.gpkg  node_id, geometry (Point)
  road_edges.gpkg  edge_id, u, v, length_m, highway, geometry (LineString)
Edges are undirected: a flooded road blocks travel both ways.
"""
from __future__ import annotations

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import shapely

from . import config
from .config import FLOODED, UNKNOWN
from .flood import Grid


def load_network(paths=None) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    paths = paths or config.get_paths()
    nodes = gpd.read_file(paths.road_nodes).to_crs(config.CRS)
    edges = gpd.read_file(paths.road_edges).to_crs(config.CRS)
    nodes["node_id"] = nodes["node_id"].astype(str)
    for c in ("edge_id", "u", "v"):
        edges[c] = edges[c].astype(str)
    return nodes, edges


def build_graph(edges: pd.DataFrame, open_edge_ids=None) -> nx.Graph:
    """Undirected graph weighted by length. If ``open_edge_ids`` is given, only
    those edges are added (the others are treated as cut). Parallel roads
    between the same two junctions keep the shortest open one."""
    g = nx.Graph()
    g.add_nodes_from(pd.unique(edges[["u", "v"]].values.ravel()))
    sub = edges if open_edge_ids is None else edges[edges["edge_id"].isin(open_edge_ids)]
    for eid, u, v, length in sub[["edge_id", "u", "v", "length_m"]].itertuples(index=False):
        if u == v:
            continue
        if not g.has_edge(u, v) or g[u][v]["length_m"] > length:
            g.add_edge(u, v, length_m=float(length), edge_id=eid)
    return g


# --- Step 5: check-points and cutting ------------------------------------------

def sample_points(edges: gpd.GeoDataFrame, spacing: float = config.SAMPLE_SPACING_M):
    """Check-points every ``spacing`` metres along each edge (both ends included).

    Returns (edge_index, x, y) arrays, where edge_index is the positional
    index into ``edges``."""
    lengths = edges.geometry.length.to_numpy()
    counts = np.maximum(2, np.ceil(lengths / spacing).astype(int) + 1)
    edge_idx = np.repeat(np.arange(len(edges)), counts)
    # fraction 0..1 along each line, evenly spaced
    starts = np.repeat(np.cumsum(counts) - counts, counts)
    frac = (np.arange(counts.sum()) - starts) / np.repeat(counts - 1, counts)
    lines = edges.geometry.to_numpy()[edge_idx]
    pts = shapely.line_interpolate_point(lines, frac, normalized=True)
    return edge_idx, shapely.get_x(pts), shapely.get_y(pts)


def lookup(raster: np.ndarray, grid: Grid, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Raster value at each point; points outside the grid are UNKNOWN."""
    col = np.floor((x - grid.xmin) / grid.res).astype(int)
    row = np.floor((grid.ymax - y) / grid.res).astype(int)
    inside = (col >= 0) & (col < grid.width) & (row >= 0) & (row < grid.height)
    out = np.full(x.shape, UNKNOWN, dtype="uint8")
    out[inside] = raster[row[inside], col[inside]]
    return out


def edge_fractions(values: np.ndarray, edge_idx: np.ndarray, n_edges: int):
    """Share of flooded and unknown check-points per edge."""
    n = np.bincount(edge_idx, minlength=n_edges)
    flooded = np.bincount(edge_idx, weights=(values == FLOODED), minlength=n_edges)
    unknown = np.bincount(edge_idx, weights=(values == UNKNOWN), minlength=n_edges)
    return flooded / n, unknown / n


def classify(frac_flooded: np.ndarray, frac_unknown: np.ndarray,
             threshold: float = config.CUT_THRESHOLD,
             unknown_majority: float = config.UNKNOWN_MAJORITY) -> np.ndarray:
    """'cut' if more than ``threshold`` of check-points are flooded; otherwise
    'unknown' if most check-points are unknown (cloud, no coverage); else 'open'.
    Cut is tested first: if the visible part alone is already over the
    threshold, missing pixels cannot make the road passable."""
    return np.where(frac_flooded > threshold, "cut",
                    np.where(frac_unknown > unknown_majority, "unknown", "open"))
