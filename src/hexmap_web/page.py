"""Turn a MapSpec into page data, and write the pages.

    write_3d(spec, "map3d.html")    deck.gl extruded hexagons over a MapLibre basemap
    write_2d(spec, "map2d.html")    pre-projected SVG hexagons, zoomable, light and dark themes
    artifact_form(path)             the same page without its document shell (Claude Artifacts)

Pages are single files: data inlined as JSON, libraries from a pinned CDN, the basemap style
fetched at load (and a plain ground if it cannot be).
"""
from __future__ import annotations

import html
import json
import math
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd

from hexmap_web import colour, geometry
from hexmap_web.hexbin import hex_vertices
from hexmap_web.spec import MapSpec

# Pinned: a page must render the same next year. MapLibre 6 ships ES modules only; 5.x keeps
# the single-file build that deck.gl's scripting API uses.
DECK_GL = "https://cdn.jsdelivr.net/npm/deck.gl@9.4.0/dist.min.js"
MAPLIBRE = "https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.js"
BASEMAPS = {"dark": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            "light": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"}


def clean(o):
    """NaN and infinity to None, recursively (JSON has no NaN; the pages show a dash)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.generic):
        return clean(o.item())
    return o


def _num(v):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else float(v)


def _shares(row, split) -> list[float] | None:
    if split is None:
        return None
    total = row[split.total]
    if not total or not math.isfinite(float(total)) or total <= 0:
        return None
    return [round(float(row[c]) / float(total), 3) for c in split.columns]


# ------------------------------------------------------------------ common parts

def _common(spec: MapSpec) -> dict:
    metrics = []
    for m in spec.metrics:
        cm = colour.colormap(m.cmap)
        metrics.append({"key": m.key, "label": m.label, "noun": m.noun,
                        "legend": colour.legend(cm, m.norm, m.tick_fmt)})
    return {
        "title": spec.title, "lede": spec.lede, "footnote": spec.footnote,
        "credit": spec.basemap_credit, "blank_label": spec.blank_label,
        "metrics": metrics,
        "cell_fields": [f.label for f in spec.cell_fields],
        "split": ({"labels": spec.split.labels, "colours": spec.split.colours,
                   "title": spec.split.title} if spec.split else None),
        "summary_title": spec.summary_title, "summary": spec.summary,
        "layers": [{"key": a.key, "label": a.label} for a in spec.areas],
        "outline_layers": [{"key": o.key, "label": o.label, "show": o.show,
                            "dark": list(o.colour_dark), "light": list(o.colour_light)}
                           for o in spec.outlines],
        "rankings": [_ranking(o, spec) for o in spec.outlines if o.ranking],
        "has": {"roads": spec.context.roads is not None, "water": spec.context.water is not None,
                "places": spec.context.places is not None},
    }


def _ranking(o, spec) -> dict:
    r = o.ranking
    rows = []
    for _, it in o.items.iterrows():
        rows.append({"name": it["name"], "short": it["short"], "value": _num(it[r.value.key]),
                     "text": r.value.fmt(it[r.value.key]),
                     "parts": ([_num(it[c]) for c in r.parts] if r.parts else None)})
    return {"key": o.key, "title": r.title, "rows": rows}


def _cell_payload(spec: MapSpec, view, i: int, row) -> dict:
    blank = bool(row.get("blank", False))
    out = {"blank": blank,
           "v": {m.key: _num(row[m.key]) for m in spec.metrics},
           "t": {m.key: m.fmt(row[m.key]) for m in spec.metrics},
           "f": [f.fmt(row[f.key]) for f in spec.cell_fields],
           "w": [[k, *(view.where[k][i] or [None, None])] for k in view.where],
           "s": None if blank else _shares(row, spec.split)}
    return out


def _cell_colours(spec: MapSpec, cells: pd.DataFrame) -> dict[str, list]:
    return {m.key: colour.rgb(cells[m.key], colour.colormap(m.cmap), m.norm) for m in spec.metrics}


def _area_items(spec: MapSpec, layer) -> list[dict]:
    out = []
    for _, it in layer.items.iterrows():
        head = next(((f.fmt(it[f.key]), f.label) for f in layer.headline
                     if _num(it[f.key]) is not None), ("—", ""))
        out.append({"name": it["name"], "kind": layer.kind, "h": list(head),
                    "f": [[f.label, f.fmt(it[f.key])] for f in layer.fields],
                    "s": _shares(it, spec.split),
                    "notes": layer.notes(it) if layer.notes else []})
    return out


# ------------------------------------------------------------------ 3D

def payload_3d(spec: MapSpec) -> dict:
    d = _common(spec)
    crs = spec.crs
    lonlat = lambda pts: np.round(geometry.to_lonlat(pts, crs), 5).tolist()  # noqa: E731
    rings_ll = lambda g, tol: [lonlat(r) for r in geometry.rings(  # noqa: E731
        g.simplify(tol, preserve_topology=True))]
    d["views"] = []
    for v in spec.views:
        cells = v.cells.reset_index(drop=True)
        verts = geometry.to_lonlat(hex_vertices(cells.q, cells.r, v.side), crs)
        cols = _cell_colours(spec, cells)
        feats = []
        for i, row in cells.iterrows():
            ring = np.round(verts[i], 5).tolist()
            p = _cell_payload(spec, v, i, row)
            p["c"] = {k: cols[k][i] for k in cols}
            feats.append({"type": "Feature", "properties": p,
                          "geometry": {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}})
        minx, miny, maxx, maxy = v.frame.bounds
        b = geometry.to_lonlat(np.array([[minx, miny], [maxx, maxy]]), crs).tolist()
        d["views"].append({
            "key": v.key, "label": v.label, "description": v.description, "noun": v.cell_noun,
            "bounds": b, "height": v.height, "places": v.place_labels,
            "max": {m.key: float(np.nanmax(cells[m.key])) for m in spec.metrics},
            "cells": {"type": "FeatureCollection", "features": feats},
            "frame": rings_ll(v.frame, 100)})
    d["areas"] = {}
    for a in spec.areas:
        items = _area_items(spec, a)
        for it, g in zip(items, a.items.geometry, strict=True):
            it["rings"] = rings_ll(geometry.polygonal(g), a.tolerance)
        d["areas"][a.key] = items
    d["outlines"] = {}
    for o in spec.outlines:
        rows = []
        for _, it in o.items.iterrows():
            p = it.geometry.representative_point()
            rows.append({"name": it["name"], "short": it["short"],
                         "rings": rings_ll(it.geometry, o.tolerance),
                         "at": lonlat(np.array([p.x, p.y]))})
        d["outlines"][o.key] = rows
    c = spec.context
    d["roads"] = ([{"p": lonlat(ln), "major": bool(r.major)}
                   for _, r in c.roads.iterrows()
                   for ln in geometry.lines(r.geometry.simplify(c.tolerance))]
                  if c.roads is not None else [])
    d["road_labels"] = ([{"name": r["name"], "at": lonlat(np.array([r.geometry.x, r.geometry.y]))}
                         for _, r in c.road_labels.iterrows()] if c.road_labels is not None else [])
    d["water"] = ([lonlat(r) for g in c.water.geometry
                   for r in geometry.rings(g.simplify(c.tolerance * 0.6))]
                  if c.water is not None else [])
    d["places"] = ([{"name": r["name"], "at": lonlat(np.array([r.geometry.x, r.geometry.y]))}
                    for _, r in c.places.iterrows()] if c.places is not None else [])
    return d


# ------------------------------------------------------------------ 2D

def payload_2d(spec: MapSpec) -> dict:
    import shapely

    d = _common(spec)
    fr = geometry.SvgFrame(shapely.unary_union([v.frame for v in spec.views]).bounds)
    d["w"], d["h"] = fr.w, fr.h
    d["views"] = []
    for v in spec.views:
        cells = v.cells.reset_index(drop=True)
        verts = hex_vertices(cells.q, cells.r, v.side)
        cols = _cell_colours(spec, cells)
        out = []
        for i, row in cells.iterrows():
            p = _cell_payload(spec, v, i, row)
            p["c"] = {k: colour.hex_colour(cols[k][i]) for k in cols}
            p["d"] = fr.path(verts[i])
            out.append(p)
        d["views"].append({"key": v.key, "label": v.label, "description": v.description,
                           "noun": v.cell_noun, "box": fr.box(v.frame), "places": v.place_labels,
                           "cells": out, "frame": fr.polygon(v.frame, 100)})
    d["areas"] = {}
    for a in spec.areas:
        items = _area_items(spec, a)
        for it, g in zip(items, a.items.geometry, strict=True):
            it["d"] = fr.polygon(geometry.polygonal(g), a.tolerance)
        d["areas"][a.key] = items
    d["outlines"] = {}
    for o in spec.outlines:
        rows = []
        for _, it in o.items.iterrows():
            p = it.geometry.representative_point()
            x, y = fr.xy(np.array([p.x, p.y])).tolist()
            rows.append({"name": it["name"], "short": it["short"],
                         "d": fr.polygon(it.geometry, o.tolerance), "x": round(x, 1), "y": round(y, 1)})
        d["outlines"][o.key] = rows
    c = spec.context

    def pt(geom):
        x, y = fr.xy(np.array([geom.x, geom.y])).tolist()
        return round(x, 1), round(y, 1)

    d["roads"] = ([{"d": fr.path(ln, closed=False), "major": bool(r.major)}
                   for _, r in c.roads.iterrows()
                   for ln in geometry.lines(r.geometry.simplify(c.tolerance))]
                  if c.roads is not None else [])
    d["road_labels"] = ([dict(zip(("x", "y"), pt(r.geometry), strict=True), name=r["name"])
                         for _, r in c.road_labels.iterrows()] if c.road_labels is not None else [])
    d["water"] = ([fr.polygon(g, c.tolerance * 0.6) for g in c.water.geometry]
                  if c.water is not None else [])
    d["places"] = ([dict(zip(("x", "y"), pt(r.geometry), strict=True), name=r["name"])
                    for _, r in c.places.iterrows()] if c.places is not None else [])
    return d


# ------------------------------------------------------------------ writing

def render(template: str, data: dict, out: str | Path, wrap: bool = True) -> Path:
    """templates/<template> with the data inlined and the pinned library URLs filled in.

    Templates are Artifact pages (no doctype, html, head or body); `wrap` adds that shell, with
    the title, fonts and style in the head, so the file is a complete page on its own.
    """
    page = resources.files("hexmap_web").joinpath("templates", template).read_text(encoding="utf-8")
    blob = json.dumps(clean(data), separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    for key, value in (("__TITLE__", html.escape(str(data.get("title", "Map")))),
                       ("__DECK_GL__", DECK_GL), ("__MAPLIBRE__", MAPLIBRE),
                       ("__BASEMAPS__", json.dumps(BASEMAPS))):
        page = page.replace(key, value)
    if page.count("/*__DATA__*/null") != 1:
        raise ValueError(f"{template}: expected exactly one /*__DATA__*/null placeholder")
    page = page.replace("/*__DATA__*/null", blob)
    if wrap:
        cut = page.index("</style>") + len("</style>")
        page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, '
                'viewport-fit=cover">\n' + page[:cut] + "\n</head>\n<body>\n" + page[cut:]
                + "\n</body>\n</html>\n")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8", newline="\n")
    return out


def write_3d(spec: MapSpec, out: str | Path, wrap: bool = True, title: str | None = None) -> Path:
    """The 3D page. `title` overrides spec.title (e.g. to name the two pages differently)."""
    d = payload_3d(spec)
    d["title"] = title or d["title"]
    return render("deck_map.html", d, out, wrap)


def write_2d(spec: MapSpec, out: str | Path, wrap: bool = True, title: str | None = None) -> Path:
    """The 2D page. `title` overrides spec.title."""
    d = payload_2d(spec)
    d["title"] = title or d["title"]
    return render("svg_map.html", d, out, wrap)


SHELL = ('<!doctype html>\n', '<html lang="en">\n', '<head>\n', '<meta charset="utf-8">\n',
         '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n',
         '\n</head>\n<body>\n', '\n</body>\n</html>\n')


def artifact_form(path: str | Path) -> str:
    """A written page without its document shell, for publishing as a Claude Artifact."""
    s = Path(path).read_text(encoding="utf-8")
    for tag in SHELL:
        if s.count(tag) != 1:
            raise ValueError(f"{path}: not a page written with wrap=True")
        s = s.replace(tag, "", 1)
    return s
