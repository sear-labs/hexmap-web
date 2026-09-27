import json
import math
import re
import sys
from importlib import resources
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, box

import hexmap_web as hw
from hexmap_web import colour, fmt, geometry, hexbin, page

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ hexagons

def test_hexagon_side_gives_the_requested_area():
    s = hexbin.hex_side(2.5e6)
    assert 3 * math.sqrt(3) / 2 * s ** 2 == pytest.approx(2.5e6)


def test_a_hexagon_centre_indexes_to_itself():
    s = hexbin.hex_side(1e6)
    q, r = np.array([0, 3, -2, 5]), np.array([0, -1, 4, 5])
    cx, cy = hexbin.hex_centres(q, r, s)
    q2, r2 = hexbin.hex_index(cx, cy, s)
    assert q2.tolist() == q.tolist() and r2.tolist() == r.tolist()


def _points(n=500, seed=1):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"id": range(n), "x": rng.uniform(0, 20_000, n), "y": rng.uniform(0, 20_000, n),
                         "a": rng.uniform(1, 5, n), "b": rng.uniform(0, 100, n)})


def test_binning_conserves_every_total():
    p = _points()
    h = hexbin.bin_points(p, 1e6, ["a", "b"])
    assert h.a.sum() == pytest.approx(p.a.sum()) and h.b.sum() == pytest.approx(p.b.sum())
    assert h.n.sum() == len(p)


def test_large_features_are_split_by_area_and_still_conserve():
    p = _points()
    big = gpd.GeoDataFrame({"id": [0]}, geometry=[box(0, 0, 8000, 8000)], crs=32614)
    h = hexbin.bin_points(p, 1e6, ["a", "b"], big=big, big_id="id")
    assert h.b.sum() == pytest.approx(p.b.sum())
    assert h.n.sum() == len(p) - 1                     # the big one was split, not placed
    whole = hexbin.bin_points(p, 1e6, ["a", "b"])
    assert (h.q.astype(str) + h.r.astype(str)).nunique() >= (whole.q.astype(str) + whole.r.astype(str)).nunique()


# ------------------------------------------------------------------ colour, format, geometry

def test_darker_is_higher():
    cm, norm = colour.colormap("inferno"), colour.log_norm(1000, 64000)
    lo, hi = colour.rgb([10, 1e6], cm, norm)
    assert sum(lo) > sum(hi)


def test_legend_ticks_run_the_bar():
    lg = colour.legend(colour.colormap(), colour.log_norm(2000, 64000), fmt.money_short)
    assert lg["ticks"][0] == 0 and lg["ticks"][-1] == 1 and lg["labels"][-1] == "$64k+"


def test_formats_show_a_dash_for_missing():
    assert fmt.money(float("nan")) == "—" and fmt.money(None) == "—"
    assert fmt.money(1_234_567) == "$1.2 M" and fmt.money(2.5e9) == "$2.50 B"


def test_svg_frame_is_north_up():
    fr = geometry.SvgFrame((0, 0, 1000, 500), width=1000, pad=0.0)
    assert fr.xy(np.array([[0, 500], [1000, 0]])).tolist() == [[0, 0], [1000, 500]]


def test_dominant_names_the_area_covering_most_of_each_cell():
    cells = gpd.GeoDataFrame(geometry=[box(0, 0, 10, 10), box(100, 100, 110, 110)], crs=32614)
    areas = gpd.GeoDataFrame({"name": ["A", "B"]}, geometry=[box(0, 0, 7, 10), box(7, 0, 20, 10)], crs=32614)
    out = geometry.dominant(cells, areas)
    assert out[0] == ["A", 0.7] and out[1] is None


def test_polygonal_drops_lines_left_by_an_intersection():
    g = box(0, 0, 1, 1).union(LineString([(1, 0), (2, 0)]))
    assert geometry.polygonal(g).geom_type == "Polygon"


# ------------------------------------------------------------------ pages

def test_templates_are_generic():
    """No project's wording may creep back into the shared templates."""
    for t in ("deck_map.html", "svg_map.html"):
        s = resources.files("hexmap_web").joinpath("templates", t).read_text(encoding="utf-8")
        for word in ("Tarrant", "Fort Worth", "Arlington", "council", "TAD"):
            assert word not in s, (t, word)


def _data(html: str) -> dict:
    return json.loads(re.search(r"const D = (\{.*?\});\n", html, re.S).group(1))


@pytest.fixture(scope="module")
def example(tmp_path_factory):
    sys.path.insert(0, str(ROOT / "examples"))
    import synthetic_map

    out = tmp_path_factory.mktemp("maps")
    p3, p2 = synthetic_map.main(out)
    return synthetic_map, p3, p2


def test_example_pages_are_complete_and_conserve_the_data(example):
    _, p3, p2 = example
    d3, d2 = _data(p3.read_text(encoding="utf-8")), _data(p2.read_text(encoding="utf-8"))
    assert d3["title"] == d2["title"] == "Synthetic City Map"
    assert "<title>Synthetic City Map</title>" in p3.read_text(encoding="utf-8")
    cells3 = d3["views"][0]["cells"]["features"]
    assert len(cells3) == len(d2["views"][0]["cells"]) > 100
    # every cell has colours and a formatted value for every metric
    for f in cells3[:50]:
        assert set(f["properties"]["c"]) == set(f["properties"]["t"]) == {"tax_per_ha", "value_per_ha"}
    assert {a["name"] for a in d3["areas"]["quad"]} == {"North-east", "North-west", "South-west", "South-east"}
    assert d3["rankings"][0]["rows"] and d3["roads"] and d3["water"] and d3["places"]


def test_artifact_form_strips_only_the_shell(example):
    _, p3, _ = example
    s = page.artifact_form(p3)
    assert s.startswith("<title>") and "<!doctype" not in s and "const D = " in s


def test_inlined_data_cannot_close_the_script(tmp_path):
    out = page.render("svg_map.html", {"title": "x", "note": "</script><b>"}, tmp_path / "p.html")
    s = out.read_text(encoding="utf-8")
    assert "</script><b>" not in s and _data(s)["note"] == "</script><b>"


def test_nan_becomes_null():
    assert page.clean({"a": float("nan"), "b": [1.0, float("inf"), np.float64(2)]}) == {"a": None, "b": [1.0, None, 2.0]}


def test_public_api():
    assert set(hw.__all__) >= {"MapSpec", "View", "Metric", "write_3d", "write_2d", "hexbin"}
