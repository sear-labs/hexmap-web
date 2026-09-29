"""What a project supplies to make a map: plain dataclasses, no page code.

A map has one or more views (sets of hexagons over a frame), one or more metrics (each drives
the colour and, on the 3D map, the height), a card of fields for a hexagon, optional area layers
that can be inspected (cities, districts, ZIPs ...), outlines with an optional ranking list, and
context (roads, water, place labels). Every number reaches the page already formatted by the
`fmt` callables given here.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from hexmap_web import fmt as F

# Reference categorical palette, first five slots in fixed order (CVD-checked for adjacent pairs,
# which is how a stacked split bar uses them).
SPLIT_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]


@dataclass
class Field:
    """One labelled value on a card: `key` is a column, `fmt` turns it into text."""
    key: str
    label: str
    fmt: Callable[[Any], str] = F.number


@dataclass
class Metric:
    """A quantity that colours the hexagons (and sets their height on the 3D map).

    Sequential (`colour.log_norm`, the default kind) or diverging (`colour.diverging_norm` with
    `cmap=colour.diverging()`), for a difference that can be either sign. On the 3D map a column's
    height is the value's size either way; its colour gives the sign. A missing value (NaN) is grey.
    """
    key: str                          # column in every view's cells
    label: str                        # button text, e.g. "Tax per acre"
    noun: str                         # after a value on a card, e.g. "tax per acre"
    norm: Any                         # colour.log_norm(lo, hi) or colour.diverging_norm(lo, hi)
    fmt: Callable[[Any], str] = F.money
    tick_fmt: Callable[[Any], str] = F.money_short
    cmap: Any = "inferno"             # a matplotlib name, or a Colormap such as colour.diverging()
    note: str = ""                    # what the colours mean, after the label on the legend;
                                      # empty: colour.note (e.g. "darker is higher (log scale)")


@dataclass
class View:
    """One set of hexagons, e.g. a city at a fine size or a county at a coarse one."""
    key: str
    label: str                        # button text
    description: str                  # e.g. "Fort Worth, 0.5 sq mi hexagons"
    cells: pd.DataFrame               # q, r, metric and field columns; optional bool `blank`
    side: float                       # hexagon side, CRS units (hexbin.hex_side)
    frame: Any                        # shapely polygon: drawn, and fitted to the screen
    cell_noun: str = "hexagon"        # e.g. "half-square-mile hexagon"
    where: dict[str, list] = field(default_factory=dict)   # label -> per cell [name, share]|None
    height: float = 6000.0            # metres, the tallest column at 1x exaggeration
    place_labels: bool = False        # show Context.places in this view


@dataclass
class Split:
    """How a total divides between parts (e.g. county, city, school), as a stacked bar."""
    labels: list[str]
    columns: list[str]                # amounts, in cells and in area items
    total: str                        # the column the shares are of
    title: str = "Split"              # above the bar on a card, e.g. "Where its tax goes"
    colours: list[str] = field(default_factory=lambda: SPLIT_COLOURS.copy())


@dataclass
class AreaLayer:
    """Areas that can be selected to see their totals, e.g. ZIP codes."""
    key: str
    label: str                        # in the "Click to inspect" menu
    kind: str                         # under an area's name on its card
    items: Any                        # GeoDataFrame: `name`, stat columns, geometry (spec CRS)
    headline: list[Field]             # the first with a value is the card's big number
    fields: list[Field]
    notes: Callable[[pd.Series], list[str]] | None = None
    tolerance: float = 100.0          # simplification, CRS units


@dataclass
class Ranking:
    """A ranked list of an outline layer's areas, e.g. council districts by tax per resident."""
    title: str
    value: Field                      # the number and text on each row
    parts: list[str] | None = None    # columns, in Split order, that make each row's bar


@dataclass
class Outline:
    """Named boundaries drawn over the map, e.g. council districts."""
    key: str
    label: str                        # the "Show" checkbox
    items: Any                        # GeoDataFrame: `name`, `short` (the label), geometry
    colour_dark: tuple[int, int, int] = (120, 180, 255)
    colour_light: tuple[int, int, int] = (42, 120, 214)
    show: bool = True
    ranking: Ranking | None = None
    tolerance: float = 80.0


@dataclass
class Context:
    """Reference layers so the map reads without a basemap."""
    roads: Any = None                 # GeoDataFrame of lines with a bool `major`
    road_labels: Any = None           # GeoDataFrame of points with `name`
    water: Any = None                 # GeoDataFrame of polygons
    places: Any = None                # GeoDataFrame of points with `name`
    tolerance: float = 100.0


@dataclass
class MapSpec:
    title: str
    lede: str                         # one or two sentences under the title
    footnote: str                     # method and sources
    crs: Any                          # of every geometry and every view's grid
    metrics: list[Metric]
    views: list[View]
    cell_fields: list[Field] = field(default_factory=list)
    split: Split | None = None
    areas: list[AreaLayer] = field(default_factory=list)
    outlines: list[Outline] = field(default_factory=list)
    context: Context = field(default_factory=Context)
    summary_title: str = ""
    summary: list[tuple[str, str]] = field(default_factory=list)   # (label, formatted value)
    blank_label: str = "No value"     # a cell with `blank` True, e.g. "All land exempt ($0)"
    basemap_credit: str = "Basemap © OpenStreetMap contributors © CARTO."
