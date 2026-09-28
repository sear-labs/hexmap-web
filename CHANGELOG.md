# Changelog

Semantic versioning. The public API is `hexmap_web.__all__`.

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
