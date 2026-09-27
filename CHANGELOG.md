# Changelog

Semantic versioning. The public API is `hexmap_web.__all__`.

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
