# Changelog

Semantic versioning. The public API is `hexmap_web.__all__`.

## 0.3.0 (2026-09-28)

Toggles, for data that changes with a choice such as season or time of day, and a signed log
scale for a net flow. Backwards compatible: a 0.2 spec draws the same pages. One visible change:
legends on long log scales now label at most six doublings, both ends kept, where 0.2 labelled
every doubling (which overlapped on a narrow legend).

- `Toggle(key, label, options)` and `MapSpec.toggles`: rows of buttons; every combination of
  options is a slice. A column is sliced when the frame holds it once per slice, named
  `slice_key(key, option, ...)`. Metrics, the cell fields that repeat a metric's key, the split,
  area-layer fields and rankings can all be sliced; the legend and cards name the slice.
- A sliced metric is stored as one table of its distinct values (rounded to
  `MapSpec.slice_digits`, default 3 significant figures), each with its text and colour, plus one
  index per cell and slice. A page with 25 slices of nine metrics over 1,700 hexagons is about
  7 MB; stored plainly it would be about 40.
- 3D column heights are scaled to the tallest value over every slice, so heights compare between
  slices.
- Refused, with a message: a column sliced for some slices but not all, a metric sliced in some
  views but not all, a sliced cell field that is not a sliced metric.
- `colour.signed_log_norm(linthresh, vmax)`: diverging, linear within ±linthresh and logarithmic
  beyond, for sizes that span decades on both sides of zero (net supply by place). Ticks at 0,
  ±vmax and one power of two between.
- `examples/synthetic_toggles.py`: made-up homes, a solar farm and a wind farm, by season and time
  of day; use, supply and net. Tested end to end: every slice read back from the page.

Built for `sear-labs/ercot-grid-analysis`: demand and net generation by season and time of day
(Dr. Jones, 2026-09-28). Checked in a browser: both pages, toggles, legend and cards.

## 0.2.0 (2026-09-28)

Diverging metrics, for a difference that can be either sign (time or money saved by one option
against another). Backwards compatible: a 0.1 spec draws the same pages.

- `colour.diverging()` (orange below the centre, a pale middle, blue above) and
  `colour.diverging_norm(lo, hi, centre=0)`. Legends mark both clipped ends (`≤`, `≥`).
- A missing value (NaN) is one neutral grey, `colour.MISSING`, on every metric, so a metric
  can be absent where its alternative does not exist.
- `Metric.cmap` also takes a Colormap. `Metric.note` says what the colours mean on the legend;
  when it is empty, `colour.note` supplies "darker is higher (log scale)" as before.
- 3D: a column's height is the value's size, either sign; its colour gives the sign.
- `fmt.signed(unit, digits)`: "+0.4 h", "−1.2 h" with a true minus sign.
- `examples/synthetic_comparison.py`: door-to-door time saved by a new service against the
  faster alternative, the car and air, on made-up cities. It shows how to bin a quantity
  that is not additive: sum people x hours and people, then divide. Tested end to end.

Suggested by its first diverging use, `sear-labs/hsr-robotaxi-scenarios` (Dr. Jones,
2026-09-28). Checked in a browser: both pages, all three metrics, both views.

## 0.1.0 (2026-09-27)

First release, extracted from `sear-labs/tarrant-landvalue-gis`, where the maps were built and
checked in a browser against that project's data.

- `hexbin`: an exact-area pointy-top hexagon grid in any projected CRS. `bin_points` sums
  additive columns, can split large features by area, and raises if a total changes.
- `spec`: `MapSpec`, `View`, `Metric`, `Field`, `Split`, `AreaLayer`, `Outline`, `Ranking`,
  `Context`.
- `page`: `write_3d` (deck.gl 9.4.0 over MapLibre 5.24.0, CARTO basemaps, a plain-ground
  fallback), `write_2d` (zoomable SVG, light and dark themes) and `artifact_form`.
- `colour`: one light-to-dark orientation on every background, a clipped log scale, legends.
- `geometry`: lon/lat and SVG projection, `polygonal`, `dominant` (the area covering most of each
  cell).
- `fmt`: money, number and percent formats, with a dash for missing values.
- `examples/synthetic_map.py`: a complete map from made-up data, used as the end-to-end test.
