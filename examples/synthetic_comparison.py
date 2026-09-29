"""A diverging map from made-up data: door-to-door time saved by a new service against two alternatives.

    python examples/synthetic_comparison.py [out_dir]   writes comparison_3d.html and comparison_2d.html

Neighbourhoods around two imaginary cities, A and B, 250 km apart, and a small town, C, off to one side, in UTM
zone 14N (metres). A new fast service links stations at the two city centres. Each neighbourhood's trip to the
other city is timed three ways: by the new service (reach the station on its side, ride, then a short last leg), by car
and by air (only from within reach of an airport, so town C has no air time). The map shows hours saved by the new
service against the faster alternative, against the car, and against air, on a diverging scale: blue where the new
service is faster, orange where it is slower, grey where the alternative does not exist.

Time saved is not additive, so it is binned the way `hexbin` requires: sum people x hours saved and people, then
divide. A hexagon's value is the average saving per person living in it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, box

import hexmap_web as hw
from hexmap_web import colour, fmt, hexbin

CRS = 32614                                          # UTM zone 14N, metres
A, B, C = (600_000, 3_600_000), (850_000, 3_600_000), (725_000, 3_510_000)
AIRPORTS = {"A": (600_000, 3_620_000), "B": (835_000, 3_588_000)}
CELL = 25e6                                          # 25 km2 hexagons
AIR_REACH = 60_000                                   # metres: farther than this from an airport, no air option


def neighbourhoods(seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    parts = []
    for name, (x0, y0), n, spread in (("A", A, 6000, 9000), ("B", B, 4000, 7500), ("C", C, 800, 3000)):
        r, a = rng.gamma(2.0, spread / 2, n), rng.uniform(0, 2 * np.pi, n)
        parts.append(pd.DataFrame({"city": name, "x": x0 + r * np.cos(a), "y": y0 + r * np.sin(a),
                                   "people": np.round(rng.lognormal(7.6, 0.5, n))}))
    return pd.concat(parts, ignore_index=True)


def _km(x, y, to) -> np.ndarray:
    return np.hypot(np.asarray(x) - to[0], np.asarray(y) - to[1]) / 1000


def trip_times(p: pd.DataFrame, dest: str) -> pd.DataFrame:
    """Hours to the centre of `dest` by the new service, car and air, for every neighbourhood not in it."""
    q = p[p.city != dest].copy()
    d_xy, o_st = {"A": A, "B": B}[dest], {"A": B, "B": A}[dest]
    q["car_h"] = _km(q.x, q.y, d_xy) * 1.25 / 95 + 0.3
    ride_h = float(_km(o_st[0], o_st[1], d_xy)) / 250 + 0.5                 # 250 km/h, plus time at the station
    q["new_h"] = _km(q.x, q.y, o_st) * 1.3 / 40 + 0.1 + ride_h + 0.3        # reach the station, wait, ride, last leg
    port = AIRPORTS[{"A": "B", "B": "A"}[dest]]
    reach = _km(q.x, q.y, port)
    q["air_h"] = np.where(reach * 1000 <= AIR_REACH, reach * 1.3 / 50 + 1.25 + 1.0 + 0.6, np.nan)
    return q


def cells_for(q: pd.DataFrame) -> pd.DataFrame:
    """People-weighted hours saved per hexagon, against the faster alternative, the car and air."""
    best = np.fmin(q.car_h, q.air_h)
    has_air = q.air_h.notna()
    q = q.assign(w_best=q.people * (best - q.new_h), w_car=q.people * (q.car_h - q.new_h),
                 people_air=q.people.where(has_air, 0.0), w_air=(q.people * (q.air_h - q.new_h)).fillna(0.0),
                 faster=q.people * (q.new_h < best))
    h = hexbin.bin_points(q, CELL, ["people", "w_best", "w_car", "people_air", "w_air", "faster"])
    return h.assign(saved_best=h.w_best / h.people, saved_car=h.w_car / h.people,
                    saved_air=np.where(h.people_air > 0, h.w_air / h.people_air.where(h.people_air > 0), np.nan),
                    faster_share=h.faster / h.people)


def main(out: Path) -> tuple[Path, Path]:
    p = neighbourhoods()
    side = hexbin.hex_side(CELL)
    frame = box(540_000, 3_455_000, 910_000, 3_660_000)
    hours = fmt.signed(" h")
    div = dict(fmt=hours, tick_fmt=hours, cmap=colour.diverging(),
               note="blue, the new service is faster; orange, slower; grey, no such alternative")
    views, summary = [], []
    for dest in ("B", "A"):
        q = trip_times(p, dest)
        views.append(hw.View(f"to_{dest}", f"Trips to {dest}", f"Neighbourhoods travelling to city {dest}, 25 km² hexagons",
                             cells_for(q), side, frame, cell_noun="25 km² hexagon", place_labels=True, height=20_000))
        summary.append((f"Faster by the new service, to {dest}", fmt.percent(
            (q.people * (q.new_h < np.fmin(q.car_h, q.air_h))).sum() / q.people.sum())))
    spec = hw.MapSpec(
        title="Synthetic Time Saved",
        lede="Made-up neighbourhoods and a new service between two cities: hours saved door to door, against each alternative.",
        footnote="Synthetic data (examples/synthetic_comparison.py). Each hexagon is the people-weighted average of its "
                 "neighbourhoods.",
        crs=CRS,
        metrics=[hw.Metric("saved_best", "Against the faster", "saved against the faster alternative",
                           colour.diverging_norm(-1.5, 1.5), **div),
                 hw.Metric("saved_car", "Against the car", "saved against the car", colour.diverging_norm(-1.5, 1.5), **div),
                 hw.Metric("saved_air", "Against air", "saved against air", colour.diverging_norm(-1.5, 1.5), **div)],
        views=views,
        cell_fields=[hw.Field("people", "People", fmt.number),
                     hw.Field("faster_share", "Faster by the new service", fmt.percent)],
        context=hw.Context(
            roads=gpd.GeoDataFrame({"major": [True, False]}, geometry=[LineString([A, B]), LineString([C, A])], crs=CRS),
            places=gpd.GeoDataFrame({"name": ["City A", "City B", "Town C"]}, geometry=[Point(A), Point(B), Point(C)],
                                    crs=CRS)),
        summary_title="Share of people",
        summary=summary,
    )
    return (hw.write_3d(spec, out / "comparison_3d.html"), hw.write_2d(spec, out / "comparison_2d.html"))


if __name__ == "__main__":
    for f in main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("examples/out")):
        print(f, f"{f.stat().st_size / 1e3:,.0f} kB")
