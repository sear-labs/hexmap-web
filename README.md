# hexmap-web

**Interactive web maps of equal-area hexagons, from Python:** a 3D map (deck.gl columns over a
MapLibre basemap) and a 2D map (zoomable SVG), each one self-contained HTML file.

| | |
|---|---|
| **Status** | v0.3, SEAR Lab. First used by [`sear-labs/tarrant-landvalue-gis`](https://github.com/sear-labs/tarrant-landvalue-gis) |
| **Standard** | https://github.com/sear-labs/code-standard: read it first and last |
| **Licence** | MIT |

## What you get

**Both maps**
- Hexagons coloured on a clipped log scale (darker is always higher, on every background), or on
  a **diverging** scale for a difference that can be either sign: time or money saved by one
  option against another, or a net flow on a signed log scale. A missing value is grey.
- **Toggles** (for example, season and time of day): every combination is a slice, and metrics,
  cards, splits, areas and rankings switch with it.
- Hover or click a hexagon for its numbers, how its total splits between parts, and the named
  areas covering most of it (for example, census tract, ZIP, city, district, with the share).
- **Click to inspect:** any area layer you supply (cities, districts, ZIP codes, tracts ...),
  with its totals on a card.
- Outlines with a ranked list (for example, districts by value per resident).
- Roads, water and place labels, so the map reads without a basemap.

**3D map**
- Column height is proportional to the chosen metric (its size, on a diverging one).
- Compass (click for north), zoom, tilt and fit buttons.
- Dark or light basemap: free CARTO styles, no token.
- If the basemap can't load (offline, or a Claude Artifact), the page says so and draws on a plain
  ground.

**2D map**
- Wheel, drag and pinch zoom; lines stay thin and labels stay readable at any zoom.
- Light and dark themes.

## Install

```bash
pip install "hexmap-web @ git+https://github.com/sear-labs/hexmap-web.git@v0.3.1"
```

The repo is public, so this needs no GitHub sign-in. Pin a tag, not a branch. For development:

```bash
pip install -e ".[dev]"
pytest -q
python examples/synthetic_map.py        # writes examples/out/synthetic_3d.html and _2d.html
python examples/synthetic_comparison.py # writes examples/out/comparison_3d.html and _2d.html
python examples/synthetic_toggles.py    # writes examples/out/toggles_3d.html and _2d.html
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

### A diverging map: what one option saves against another

`examples/synthetic_comparison.py` maps door-to-door hours saved by a new service against the
faster alternative, against the car and against air, with one metric per comparison:

```python
hours = fmt.signed(" h")
hw.Metric("saved_car", "Against the car", "saved against the car",
          colour.diverging_norm(-1.5, 1.5), fmt=hours, tick_fmt=hours, cmap=colour.diverging(),
          note="blue, the new service is faster; orange, slower; grey, no such alternative")
```

A saving per person is not additive, so bin what is: people x hours saved and people, then
divide per hexagon. Where an alternative does not exist (no airport in reach), leave its value
NaN; the hexagon is grey under that metric only.

### Toggles: the same map by season, time of day, scenario ...

`examples/synthetic_toggles.py` maps power used and made by season and time of day. Give each
sliced quantity one column per combination of options, named with `hw.slice_key`, and name the
options:

```python
for s in ("all", "summer", "winter"):
    for t in ("all", "midday", "evening", "night"):
        cells[hw.slice_key("net", s, t)] = ...           # "net@summer@evening"
spec = hw.MapSpec(..., toggles=[hw.Toggle("season", "Season", [("all", "All year"), ...]),
                                hw.Toggle("time", "Time of day", [("all", "All day"), ...])])
```

The first option of each toggle is shown first. Anything without slice columns stays as it is.
For a net quantity that spans decades on both sides of zero, use
`colour.signed_log_norm(linthresh, vmax)` with `cmap=colour.diverging()`. Sliced values are
rounded to `MapSpec.slice_digits` significant figures (default 3), which keeps a page with many
slices a few MB.

### The spec, in one table

| Part | What it is |
|---|---|
| `Metric` | a column that colours hexagons (and sets 3D height), with its colour scale (log or diverging), number formats and legend note |
| `View` | one set of hexagons (`q`, `r`, metric and field columns; optional `blank`), their side, the frame to fit, and `where` (per-cell `[name, share]`, e.g. from `geometry.dominant`) |
| `Field` | a labelled value on a card: column, label, format |
| `Split` | how a total divides into parts (columns and colours), drawn as a stacked bar |
| `AreaLayer` | areas that can be selected: `name`, stat columns, geometry, the headline and fields on their card, optional notes |
| `Outline` | named boundaries drawn over the map (`name`, `short`), with an optional `Ranking` list |
| `Context` | roads (`major` bool), road labels, water and place labels |
| `Toggle` | a row of option buttons; with `slice_key` columns, every combination of options is a slice |
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
