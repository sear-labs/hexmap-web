"""Geometry for the pages: lon/lat for the 3D map, pre-projected SVG paths for the 2D map, and
which named area covers most of each hexagon."""
from __future__ import annotations

import numpy as np


def to_lonlat(xy: np.ndarray, crs) -> np.ndarray:
    """Coordinates in `crs` (any array ending in an x, y axis) to lon/lat."""
    from pyproj import Transformer

    t = Transformer.from_crs(crs, 4326, always_xy=True)
    xy = np.asarray(xy, dtype=float)
    lon, lat = t.transform(xy[..., 0], xy[..., 1])
    return np.stack([lon, lat], axis=-1)


def rings(geom):
    """Outer rings of a polygon or multipolygon, as coordinate arrays."""
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type == "Polygon" and not g.is_empty:
            yield np.asarray(g.exterior.coords)


def lines(geom):
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type == "LineString" and not g.is_empty:
            yield np.asarray(g.coords)


def polygonal(geom):
    """Only the polygon parts of a geometry (an intersection can leave lines and points)."""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.validation import make_valid

    g = make_valid(geom)
    parts = [p for p in getattr(g, "geoms", [g]) if p.geom_type in ("Polygon", "MultiPolygon")]
    polys = [q for p in parts for q in getattr(p, "geoms", [p])]
    return MultiPolygon(polys) if len(polys) > 1 else (polys[0] if polys else Polygon())


def dominant(cells, areas, name: str = "name") -> list:
    """For each cell (a GeoDataFrame row, in order): [name of the area covering most of it,
    share of the cell covered], or None where no area touches it."""
    import geopandas as gpd

    c = cells[["geometry"]].reset_index(drop=True).assign(_cell=lambda d: range(len(d)))
    a = areas[[name, "geometry"]].copy()
    a["geometry"] = a.geometry.map(polygonal)
    ov = gpd.overlay(c, a, how="intersection", keep_geom_type=True)
    ov["_a"] = ov.geometry.area
    best = ov.sort_values("_a", ascending=False).drop_duplicates("_cell").set_index("_cell")
    whole = c.geometry.area
    out: list = [None] * len(c)
    for i, row in best.iterrows():
        out[i] = [row[name], round(float(min(row["_a"] / whole[i], 1.0)), 2)]
    return out


class SvgFrame:
    """Projects CRS coordinates into an SVG box `width` wide, north up."""

    def __init__(self, bounds, width: float = 1000.0, pad: float = 0.02):
        minx, miny, maxx, maxy = bounds
        p = pad * max(maxx - minx, maxy - miny)
        self.minx, self.maxy = minx - p, maxy + p
        self.s = width / (maxx - minx + 2 * p)
        self.w = width
        self.h = round((maxy - miny + 2 * p) * self.s, 1)

    def xy(self, pts) -> np.ndarray:
        pts = np.asarray(pts, dtype=float)
        return np.stack([(pts[..., 0] - self.minx) * self.s, (self.maxy - pts[..., 1]) * self.s],
                        axis=-1)

    def path(self, coords, closed: bool = True) -> str:
        q = np.round(self.xy(coords), 1)
        d = "M" + "L".join(f"{x:g} {y:g}" for x, y in q)
        return d + ("Z" if closed else "")

    def polygon(self, geom, tolerance: float = 0.0) -> str:
        g = geom.simplify(tolerance, preserve_topology=True) if tolerance else geom
        return "".join(self.path(r) for r in rings(g))

    def box(self, geom) -> list[float]:
        minx, miny, maxx, maxy = geom.bounds
        (x0, y0), (x1, y1) = self.xy(np.array([[minx, maxy], [maxx, miny]])).tolist()
        return [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)]
