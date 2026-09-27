"""Equal-area hexagons in a projected CRS, and binning additive quantities into them.

The grid is pointy-top, in axial coordinates (q, r). Units are the CRS's: give the cell area in
squared CRS units (square feet for EPSG:2276, square metres for a UTM zone).

Binning is by sum, never by mean: a hexagon's "per acre" is the sum of its features' quantities
divided by the sum of their areas. A small feature goes whole to the hexagon holding its point.
A large one (an airport, a ranch) can be cut along hexagon edges and every quantity split by area,
so it spreads over the hexagons it actually covers; `bin_points` checks that the split neither
creates nor loses any total.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

SQFT_PER_SQMI = 5280.0 ** 2
SQM_PER_SQMI = 2_589_988.110336


def hex_side(cell_area: float) -> float:
    """Side (= centre-to-vertex distance) of a regular hexagon of the given area."""
    return math.sqrt(2 * cell_area / (3 * math.sqrt(3)))


def hex_index(x, y, side: float) -> tuple[np.ndarray, np.ndarray]:
    """Axial (q, r) of the pointy-top hexagon containing each point, by cube rounding."""
    cx = (math.sqrt(3) / 3 * np.asarray(x, dtype=float) - np.asarray(y, dtype=float) / 3) / side
    cz = (2 / 3 * np.asarray(y, dtype=float)) / side
    cy = -cx - cz
    rx, ry, rz = np.round(cx), np.round(cy), np.round(cz)
    dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
    fx = (dx > dy) & (dx > dz)
    fz = ~fx & (dz >= dy)
    rx = np.where(fx, -ry - rz, rx)
    rz = np.where(fz, -rx - ry, rz)
    return rx.astype(int), rz.astype(int)


def hex_centres(q, r, side: float) -> tuple[np.ndarray, np.ndarray]:
    q, r = np.asarray(q), np.asarray(r)
    return side * math.sqrt(3) * (q + r / 2), side * 1.5 * r


def hex_vertices(q, r, side: float) -> np.ndarray:
    """(n, 6, 2) vertex array of the hexagons (q, r)."""
    cx, cy = hex_centres(q, r, side)
    ang = np.radians(30 + 60 * np.arange(6))
    return np.stack([np.column_stack([x + side * np.cos(ang), y + side * np.sin(ang)])
                     for x, y in zip(np.atleast_1d(cx), np.atleast_1d(cy), strict=True)])


def hex_polygons(q, r, side: float) -> list:
    from shapely.geometry import Polygon

    return [Polygon(v) for v in hex_vertices(q, r, side)]


def bin_points(df: pd.DataFrame, cell_area: float, sums: Sequence[str], *, x: str = "x",
               y: str = "y", big=None, big_id: str | None = None,
               tolerance: float = 1e-6) -> pd.DataFrame:
    """Sum `sums` per hexagon of area `cell_area`.

    `df` has one row per feature with a point (`x`, `y`, in the CRS) and additive columns.
    `big` (optional) is a GeoDataFrame of polygons, keyed by `big_id` (a column of both), for
    the features to be split by area rather than placed whole: their rows in `df` supply the
    quantities, their polygons the shares. Returns one row per hexagon: q, r, cx, cy, the sums
    and `n` (features placed whole). Raises if splitting changed any total by more than
    `tolerance` (relative).
    """
    import geopandas as gpd

    side = hex_side(cell_area)
    sums = list(sums)
    g = df[df[x].notna() & df[y].notna()]
    is_big = g[big_id].isin(big[big_id]) if big is not None else pd.Series(False, index=g.index)
    small = g[~is_big].copy()
    small["q"], small["r"] = hex_index(small[x], small[y], side)
    small["n"] = 1
    parts = [small[["q", "r", "n", *sums]]]
    if big is not None and is_big.any():
        geo = big[big[big_id].isin(g.loc[is_big, big_id])][[big_id, "geometry"]]
        geo = geo.merge(g.loc[is_big, [big_id, *sums]], on=big_id)
        geo["_whole"] = geo.geometry.area
        minx, miny, maxx, maxy = geo.total_bounds
        xs = np.arange(minx - 2 * side, maxx + 2 * side, side)
        ys = np.arange(miny - 2 * side, maxy + 2 * side, side)
        gx, gy = np.meshgrid(xs, ys)
        q, r = hex_index(gx.ravel(), gy.ravel(), side)
        cells = pd.DataFrame({"q": q, "r": r}).drop_duplicates()
        grid = gpd.GeoDataFrame(cells, geometry=hex_polygons(cells.q, cells.r, side), crs=geo.crs)
        pieces = gpd.overlay(geo, grid, how="intersection", keep_geom_type=True)
        share = pieces.geometry.area / pieces["_whole"]
        parts.append(pd.DataFrame({"q": pieces.q, "r": pieces.r, "n": 0,
                                   **{c: pieces[c] * share for c in sums}}))
    h = pd.concat(parts).groupby(["q", "r"], as_index=False).sum()
    for c in sums:
        a, b = h[c].sum(), g[c].sum()
        if abs(a - b) > tolerance * max(abs(b), 1):
            raise ValueError(f"binning changed the total of {c}: {a:,.4f} != {b:,.4f}")
    h["cx"], h["cy"] = hex_centres(h.q, h.r, side)
    h.attrs["side"] = side
    return h
