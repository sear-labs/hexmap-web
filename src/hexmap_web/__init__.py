"""hexmap_web: interactive 3D and 2D web maps of equal-area hexagons.

A project bins its data into hexagons (hexbin.bin_points), describes the map (spec.MapSpec) and
writes the pages (page.write_3d, page.write_2d). See README.md and examples/synthetic_map.py.
"""
from hexmap_web import colour, fmt, geometry, hexbin
from hexmap_web.page import artifact_form, payload_2d, payload_3d, write_2d, write_3d
from hexmap_web.spec import (
    AreaLayer,
    Context,
    Field,
    MapSpec,
    Metric,
    Outline,
    Ranking,
    Split,
    View,
)

__version__ = "0.2.0"

__all__ = [
    "AreaLayer", "Context", "Field", "MapSpec", "Metric", "Outline", "Ranking", "Split", "View",
    "artifact_form", "colour", "fmt", "geometry", "hexbin", "payload_2d", "payload_3d",
    "write_2d", "write_3d",
]
