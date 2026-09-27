"""A complete map from made-up data: what a project supplies, end to end, with no downloads.

    python examples/synthetic_map.py [out_dir]      writes synthetic_3d.html and synthetic_2d.html

Ten thousand "parcels" around an imaginary city centre, in UTM zone 14N (metres). Each has an
area and a value that falls off with distance from the centre; tax is 2% of value. The map shows
value and tax per hectare in 1 km2 hexagons, with two inspectable area layers, an outline layer
with a ranking, one road, one lake and a place label.
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

CRS = 32614                                   # UTM zone 14N, metres
X0, Y0 = 650_000, 3_625_000                   # an imaginary centre near Dallas-Fort Worth


def parcels(n: int = 10_000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = rng.gamma(2.0, 3500, n)
    a = rng.uniform(0, 2 * np.pi, n)
    x, y = X0 + r * np.cos(a), Y0 + r * np.sin(a)
    hectares = rng.uniform(0.05, 1.5, n)
    value = hectares * 4e6 * np.exp(-r / 6000) * rng.lognormal(0, 0.4, n)
    tax = np.where(rng.random(n) < 0.05, 0.0, 0.02 * value)          # 5% exempt
    return pd.DataFrame({"x": x, "y": y, "hectares": hectares, "value": value, "tax": tax,
                         "tax_local": tax * 0.4, "tax_school": tax * 0.6})


def per_ha(df: pd.DataFrame) -> pd.DataFrame:
    return df.assign(value_per_ha=df.value / df.hectares, tax_per_ha=df.tax / df.hectares,
                     blank=df.tax <= 0)


def main(out: Path) -> tuple[Path, Path]:
    p = parcels()
    cells = per_ha(hexbin.bin_points(p, 1_000_000, ["hectares", "value", "tax", "tax_local",
                                                    "tax_school"]))
    side = hexbin.hex_side(1_000_000)
    frame = box(X0 - 25_000, Y0 - 25_000, X0 + 25_000, Y0 + 25_000)

    quadrants = gpd.GeoDataFrame({"name": ["North-east", "North-west", "South-west", "South-east"],
                                  "short": ["NE", "NW", "SW", "SE"]},
                                 geometry=[box(X0, Y0, X0 + 25e3, Y0 + 25e3), box(X0 - 25e3, Y0, X0, Y0 + 25e3),
                                           box(X0 - 25e3, Y0 - 25e3, X0, Y0), box(X0, Y0 - 25e3, X0 + 25e3, Y0)],
                                 crs=CRS)
    # area totals: sum over the parcels whose point falls in each quadrant
    pts = gpd.GeoDataFrame(p, geometry=gpd.points_from_xy(p.x, p.y), crs=CRS)
    j = gpd.sjoin(pts, quadrants[["name", "geometry"]], predicate="within")
    tot = j.groupby("name")[["hectares", "value", "tax", "tax_local", "tax_school"]].sum()
    quadrants = quadrants.join(per_ha(tot), on="name")

    cells_gdf = gpd.GeoDataFrame(geometry=hexbin.hex_polygons(cells.q, cells.r, side), crs=CRS)
    road = gpd.GeoDataFrame({"major": [True]}, geometry=[LineString([(X0 - 25e3, Y0 - 3e3), (X0 + 25e3, Y0 + 4e3)])], crs=CRS)
    spec = hw.MapSpec(
        title="Synthetic City Map",
        lede="Made-up parcels around an imaginary centre, to show what hexmap_web draws.",
        footnote="Synthetic data (examples/synthetic_map.py).",
        crs=CRS,
        metrics=[hw.Metric("tax_per_ha", "Tax per hectare", "tax per hectare", colour.log_norm(500, 64_000)),
                 hw.Metric("value_per_ha", "Value per hectare", "value per hectare",
                           colour.log_norm(25_000, 3_200_000))],
        views=[hw.View("city", "City", "Synthetic city, 1 km² hexagons", cells, side, frame,
                       cell_noun="square-kilometre hexagon", place_labels=True,
                       where={"Quadrant": hw.geometry.dominant(cells_gdf, quadrants)})],
        cell_fields=[hw.Field("hectares", "Land", lambda v: f"{v:,.0f} ha")],
        split=hw.Split(["Local", "School"], ["tax_local", "tax_school"], "tax", title="Where the tax goes"),
        areas=[hw.AreaLayer("quad", "Quadrants", "Quadrant", quadrants,
                            headline=[hw.Field("tax_per_ha", "tax per hectare", fmt.money)],
                            fields=[hw.Field("tax", "Tax", fmt.money), hw.Field("hectares", "Land", fmt.number)])],
        outlines=[hw.Outline("quad", "Quadrants", quadrants,
                             ranking=hw.Ranking("Tax per hectare by quadrant",
                                                hw.Field("tax_per_ha", "Tax per hectare", fmt.money)))],
        context=hw.Context(
            roads=road,
            road_labels=gpd.GeoDataFrame({"name": ["Main Fwy"]}, geometry=[Point(X0 + 12e3, Y0 + 2.2e3)], crs=CRS),
            water=gpd.GeoDataFrame(geometry=[Point(X0 - 12e3, Y0 + 12e3).buffer(2500)], crs=CRS),
            places=gpd.GeoDataFrame({"name": ["Centre"]}, geometry=[Point(X0, Y0)], crs=CRS)),
        summary_title="Totals",
        summary=[("Tax raised", fmt.money(p.tax.sum())), ("Parcels", fmt.number(len(p)))],
        blank_label="All exempt ($0)",
    )
    return hw.write_3d(spec, out / "synthetic_3d.html"), hw.write_2d(spec, out / "synthetic_2d.html")


if __name__ == "__main__":
    for f in main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("examples/out")):
        print(f, f"{f.stat().st_size / 1e3:,.0f} kB")
