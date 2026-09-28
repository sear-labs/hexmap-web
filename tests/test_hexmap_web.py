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


# ------------------------------------------------------------------ diverging (0.2.0)

def test_diverging_scale_centres_and_marks_its_ends():
    cm, norm = colour.diverging(), colour.diverging_norm(-2, 1)
    lg = colour.legend(cm, norm, fmt.signed(" h"))
    assert lg["ticks"] == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert lg["labels"] == ["≤" + fmt.MINUS + "2.0 h", fmt.MINUS + "1.0 h", "0.0 h", "+0.5 h", "≥+1.0 h"]
    lo, mid, hi, beyond, missing = colour.rgb([-2, 0, 1, 50, float("nan")], cm, norm)
    assert colour.hex_colour(lo) == colour.DIVERGING[0] and colour.hex_colour(hi) == colour.DIVERGING[2]
    assert beyond == hi and missing == colour.MISSING and sum(mid) > sum(lo)
    with pytest.raises(ValueError):
        colour.diverging_norm(1, 2)


def test_signed_format():
    f = fmt.signed(" h")
    assert [f(0.44), f(-1.25), f(0.01), f(float("nan"))] == ["+0.4 h", fmt.MINUS + "1.2 h", "0.0 h", "—"]


@pytest.fixture(scope="module")
def comparison(tmp_path_factory):
    sys.path.insert(0, str(ROOT / "examples"))
    import synthetic_comparison

    out = tmp_path_factory.mktemp("cmp")
    p3, p2 = synthetic_comparison.main(out)
    return synthetic_comparison, p3, p2


def test_comparison_example_weights_by_people_and_greys_what_is_missing(comparison):
    ex, p3, p2 = comparison
    d3, d2 = _data(p3.read_text(encoding="utf-8")), _data(p2.read_text(encoding="utf-8"))
    p = ex.neighbourhoods()
    q = ex.trip_times(p, "B")
    cells = ex.cells_for(q)
    assert cells.people.sum() == pytest.approx(q.people.sum())
    # the people-weighted mean over all hexagons equals the one over all neighbourhoods
    assert (cells.saved_car * cells.people).sum() / cells.people.sum() == pytest.approx(
        ((q.car_h - q.new_h) * q.people).sum() / q.people.sum())
    feats = d3["views"][0]["cells"]["features"]
    no_air = [f["properties"] for f in feats if f["properties"]["v"]["saved_air"] is None]
    assert no_air and all(x["c"]["saved_air"] == colour.MISSING and x["t"]["saved_air"] == "—" for x in no_air)
    vals = [f["properties"]["v"]["saved_best"] for f in feats]
    assert min(vals) < 0 < max(vals)                                  # both signs, so both colours
    assert d3["views"][0]["max"]["saved_best"] == pytest.approx(max(abs(v) for v in vals))
    m = d2["metrics"][0]
    assert "grey, no such alternative" in m["note"] and m["legend"]["labels"][2] == "0.0 h"
    assert d3["metrics"][0]["height"].startswith("height is the size")


def test_a_sequential_metric_keeps_its_default_note(example):
    _, p3, _ = example
    m = _data(p3.read_text(encoding="utf-8"))["metrics"][0]
    assert m["note"] == "darker is higher (log scale)" and m["height"] == "height is proportional"
