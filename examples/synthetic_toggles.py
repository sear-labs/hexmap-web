"""A map with toggles from made-up data: where power is made and used, by season and time of day.

    python examples/synthetic_toggles.py [out_dir]   writes toggles_3d.html and toggles_2d.html

Homes around an imaginary city use power (more on summer evenings); a solar farm and a wind farm out of
town make it (solar at midday, wind at night, more in spring). Every quantity is an average in MW over the
hours of a slice, so slices of different lengths compare. The net map is supply minus use on a signed log
scale: blue where a hexagon makes more than it uses, orange where it uses more, pale where they balance.

Each metric is given once per slice, as columns named hw.slice_key(key, season, time); `Toggle`s name the
options. Sums are binned first and divided after, as `hexbin` requires.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

import hexmap_web as hw
from hexmap_web import colour, fmt, hexbin

CRS = 32614
CITY, SOLAR, WIND = (600_000, 3_600_000), (660_000, 3_560_000), (540_000, 3_650_000)
CELL = 25e6
SEASONS = [("all", "All year"), ("summer", "Summer"), ("winter", "Winter")]
TIMES = [("all", "All day"), ("midday", "Midday"), ("evening", "Evening"), ("night", "Night")]
# MW per person (use) and per MW of capacity (output) in each slice; "all" is the mean of the others
USE = {"summer": {"midday": 1.3e-3, "evening": 1.8e-3, "night": 1.0e-3},
       "winter": {"midday": 1.0e-3, "evening": 1.4e-3, "night": 1.1e-3}}
SUN = {"summer": {"midday": 0.8, "evening": 0.1, "night": 0.0}, "winter": {"midday": 0.55, "evening": 0.0, "night": 0.0}}
WINDY = {"summer": {"midday": 0.25, "evening": 0.35, "night": 0.5}, "winter": {"midday": 0.35, "evening": 0.4, "night": 0.45}}


def _with_all(f: dict) -> dict:
    """Add the 'all' options as plain means (the slices here are equal-length, which a real map must weight)."""
    out = {s: {**t, "all": float(np.mean(list(t.values())))} for s, t in f.items()}
    out["all"] = {t: float(np.mean([out[s][t] for s in f])) for t in [*next(iter(f.values())), "all"]}
    return out


def points(seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 3000
    r, a = rng.gamma(2.0, 6000, n), rng.uniform(0, 2 * np.pi, n)
    homes = pd.DataFrame({"x": CITY[0] + r * np.cos(a), "y": CITY[1] + r * np.sin(a), "people": rng.lognormal(6, 0.5, n),
                          "solar_mw": 0.0, "wind_mw": 0.0})
    farms = pd.DataFrame({"x": [SOLAR[0], WIND[0]], "y": [SOLAR[1], WIND[1]], "people": 0.0,
                          "solar_mw": [400.0, 0.0], "wind_mw": [0.0, 600.0]})
    return pd.concat([homes, farms], ignore_index=True)


def cells_for(p: pd.DataFrame) -> pd.DataFrame:
    use, sun, windy = _with_all(USE), _with_all(SUN), _with_all(WINDY)
    cols = {}
    for s, _ in SEASONS:
        for t, _ in TIMES:
            k = lambda name, s=s, t=t: hw.slice_key(name, s, t)  # noqa: E731
            cols[k("use")] = p.people * use[s][t]
            cols[k("solar")] = p.solar_mw * sun[s][t]
            cols[k("wind")] = p.wind_mw * windy[s][t]
    p = pd.concat([p, pd.DataFrame(cols)], axis=1)
    h = hexbin.bin_points(p, CELL, ["people", *cols])
    for s, _ in SEASONS:
        for t, _ in TIMES:
            k = lambda name, s=s, t=t: hw.slice_key(name, s, t)  # noqa: E731
            h[k("supply")] = h[k("solar")] + h[k("wind")]
            h[k("net")] = h[k("supply")] - h[k("use")]
    return h


def main(out: Path) -> tuple[Path, Path]:
    cells = cells_for(points())
    mw = lambda v: fmt.number(v) + " MW" if v is not None and np.isfinite(v) else "—"  # noqa: E731
    net = fmt.signed(" MW", 1)
    spec = hw.MapSpec(
        title="Synthetic Power Map",
        lede="Made-up homes, a solar farm and a wind farm: where power is used and made, by season and time of day.",
        footnote="Synthetic data (examples/synthetic_toggles.py). Average MW over the hours of the chosen slice.",
        crs=CRS,
        metrics=[hw.Metric("use", "Use", "used", colour.log_norm(0.05, 12.8), mw, mw, cmap="viridis"),
                 hw.Metric("supply", "Supply", "made", colour.log_norm(1, 512), mw, mw, cmap="viridis"),
                 hw.Metric("net", "Net", "made minus used", colour.signed_log_norm(0.1, 409.6), net, net,
                           cmap=colour.diverging(), note="blue, makes more than it uses; orange, uses more")],
        views=[hw.View("all", "Area", "City and farms, 25 km² hexagons", cells, hexbin.hex_side(CELL),
                       box(500_000, 3_520_000, 700_000, 3_690_000), cell_noun="25 km² hexagon", place_labels=True,
                       height=20_000)],
        cell_fields=[hw.Field("people", "People", fmt.number), hw.Field("net", "Net", net)],
        split=hw.Split(["Solar", "Wind"], ["solar", "wind"], "supply", title="Supply by source"),
        toggles=[hw.Toggle("season", "Season", SEASONS), hw.Toggle("time", "Time of day", TIMES)],
        context=hw.Context(places=gpd.GeoDataFrame({"name": ["City", "Solar farm", "Wind farm"]},
                                                   geometry=[Point(CITY), Point(SOLAR), Point(WIND)], crs=CRS)),
    )
    return hw.write_3d(spec, out / "toggles_3d.html"), hw.write_2d(spec, out / "toggles_2d.html")


if __name__ == "__main__":
    for f in main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("examples/out")):
        print(f, f"{f.stat().st_size / 1e3:,.0f} kB")
