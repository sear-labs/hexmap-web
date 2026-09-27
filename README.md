# hexmap-web

**Interactive web maps of equal-area hexagons, from Python:** a 3D map (deck.gl columns over a
MapLibre basemap) and a 2D map (zoomable SVG), each one self-contained HTML file.

| | |
|---|---|
| **Status** | v0.1, SEAR Lab. First used by [`sear-labs/tarrant-landvalue-gis`](https://github.com/sear-labs/tarrant-landvalue-gis) |
| **Standard** | https://github.com/sear-labs/code-standard: read it first and last |
| **Licence** | MIT |

## What you get

**Both maps**
- Hexagons coloured on a clipped log scale; darker is always higher, on every background.
- Hover or click a hexagon for its numbers, how its total splits between parts, and the named
  areas covering most of it (for example, census tract, ZIP, city, district, with the share).
- **Click to inspect:** any area layer you supply (cities, districts, ZIP codes, tracts ...),
  with its totals on a card.
- Outlines with a ranked list (for example, districts by value per resident).
- Roads, water and place labels, so the map reads without a basemap.

**3D map**
- Column height is proportional to the chosen metric.
- Compass (click for north), zoom, tilt and fit buttons.
- Dark or light basemap: free CARTO styles, no token.
- If the basemap can't load (offline, or a Claude Artifact), the page says so and draws on a plain
  ground.

**2D map**
- Wheel, drag and pinch zoom; lines stay thin and labels stay readable at any zoom.
- Light and dark themes.

## Install

```bash
pip install "hexmap-web @ git+https://github.com/sear-labs/hexmap-web.git@v0.1.0"
```

This is a private repo, so installing needs GitHub access to `sear-labs` (a signed-in `gh` or git
credential manager is enough). For development:

```bash
pip install -e ".[dev]"
pytest -q
python examples/synthetic_map.py        # writes examples/out/synthetic_3d.html and _2d.html
```

## Use

```python
import hexmap_web as hw
from hexmap_web import colour, fmt, hexbin

cells = hexbin.bin_points(points, cell_area=1e6, sums=["hectares", "value"])   # CRS units
cells["value_per_ha"] = cells.value / cells.hectares
spec = hw.MapSpec(
    title="My Map", lede="What it shows.", footnote="Method and sources.", crs=32614,
    metrics=[hw.Metric("value_per_ha", "Value per hectare", "value per hectare",
                       colour.log_norm(25_000, 3_200_000))],
    views=[hw.View("all", "All", "The study area, 1 km² hexagons", cells,
                   hexbin.hex_side(1e6), study_area_polygon)],
)
hw.write_3d(spec, "map3d.html")
hw.write_2d(spec, "map2d.html")
```

`examples/synthetic_map.py` uses every part of the spec on made-up data. It is also the
end-to-end test.

### The spec, in one table

| Part | What it is |
|---|---|
| `Metric` | a column that colours hexagons (and sets 3D height), with its colour range and number formats |
| `View` | one set of hexagons (`q`, `r`, metric and field columns; optional `blank`), their side, the frame to fit, and `where` (per-cell `[name, share]`, e.g. from `geometry.dominant`) |
| `Field` | a labelled value on a card: column, label, format |
| `Split` | how a total divides into parts (columns and colours), drawn as a stacked bar |
| `AreaLayer` | areas that can be selected: `name`, stat columns, geometry, the headline and fields on their card, optional notes |
| `Outline` | named boundaries drawn over the map (`name`, `short`), with an optional `Ranking` list |
| `Context` | roads (`major` bool), road labels, water and place labels |
| `MapSpec` | the whole map, plus title, lede, footnote, summary figures and the CRS of all geometry |

**Every number reaches the page already formatted** by the `fmt` callables in the spec (`fmt.money`,
`fmt.number`, or your own). So a project changes how a number reads in Python, once, and both maps
agree.

**Hexagons.** `hexbin.bin_points` sums, never averages. A feature too large for a hexagon (pass
its polygon in `big`) is split by area over the hexagons it covers. Binning raises if any total
changes.

### Publishing as a Claude Artifact

`hw.artifact_form(path)` returns the page without its document shell, which is the form the Artifact
tool publishes. Artifacts block outside requests, so the 3D map shows a plain ground with your
roads and water instead of the basemap.

## Pinned

- deck.gl 9.4.0 and MapLibre GL 5.24.0, from jsdelivr (`page.py`).
- MapLibre 6 ships ES modules only, so 5.x is used.
- Fonts: Public Sans and IBM Plex Mono (Google Fonts).
- Colour: `colour.colormap` trims the matplotlib colormap (default inferno) so the palest cells
  stay visible on white and the darkest don't swallow an outline.
