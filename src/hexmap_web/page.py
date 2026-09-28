"""Turn a MapSpec into page data, and write the pages.

    write_3d(spec, "map3d.html")    deck.gl extruded hexagons over a MapLibre basemap
    write_2d(spec, "map2d.html")    pre-projected SVG hexagons, zoomable, light and dark themes
    artifact_form(path)             the same page without its document shell (Claude Artifacts)

Pages are single files: data inlined as JSON, libraries from a pinned CDN, the basemap style
fetched at load (and a plain ground if it cannot be).
"""
from __future__ import annotations

import html
import itertools
import json
import math
from importlib import resources
from pathlib import Path

import numpy as np
import pandas as pd

from hexmap_web import colour, geometry
from hexmap_web.hexbin import hex_vertices
from hexmap_web.spec import MapSpec, slice_key

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


def _abs_max(values) -> float:
    """The tallest column's value: the largest size, either sign, ignoring missing values."""
    v = np.abs(np.asarray(values, dtype=float))
    v = v[np.isfinite(v)]
    return float(v.max()) if v.size else 0.0


def _shares(row, split, get=None, digits: int = 3) -> list[float] | None:
    """Each part's share of the total; `get(row, key)` reads a column (default: row[key])."""
    if split is None:
        return None
    get = get or (lambda r, k: r[k])
    total = get(row, split.total)
    if not total or not math.isfinite(float(total)) or total <= 0:
        return None
    return [round(float(get(row, c)) / float(total), digits) for c in split.columns]


# ------------------------------------------------------------------ slices (0.3.0)
#
# A page with toggles holds every slice, so its size grows with their number. A sliced metric is
# stored once as a table of the distinct values it takes (rounded to spec.slice_digits significant
# figures), each with its text and colour, and every cell keeps one index into that table per
# slice. The page copies the chosen slice into the same fields an unsliced page reads (a cell's
# v, t, c, s, f; an area's h, f, s; a ranking row's value, text, parts), so the drawing code is
# the same with or without toggles.

def _combos(spec: MapSpec) -> list[tuple[str, ...]]:
    """Every slice, first toggle outermost: the page finds one by the same mixed-radix count."""
    return list(itertools.product(*[[k for k, _ in t.options] for t in spec.toggles])) if spec.toggles else []


def _is_sliced(frame, key: str, combos) -> bool:
    """True when `frame` holds `key` for every slice; raises if it holds it for only some."""
    if not combos:
        return False
    have = [slice_key(key, *c) in frame.columns for c in combos]
    if any(have) and not all(have):
        missing = [slice_key(key, *c) for c, h in zip(combos, have, strict=True) if not h]
        raise ValueError(f"{key!r} is sliced for some slices but not {missing[:3]}{' ...' if len(missing) > 3 else ''}")
    return all(have)


def _sig(x, digits: int) -> np.ndarray:
    """Round to `digits` significant figures; zero and missing values stay as they are."""
    x = np.array(x, dtype=float)
    ok = np.isfinite(x) & (x != 0)
    scale = 10.0 ** (digits - 1 - np.floor(np.log10(np.abs(x[ok]))))
    x[ok] = np.round(x[ok] * scale) / scale
    return x


class _Table:
    """One sliced metric's distinct values, each with a text and a colour; the last entry is 'missing'."""

    def __init__(self, metric, arrays, digits: int):
        self.m, self.digits = metric, digits
        r = _sig(np.concatenate([np.asarray(a, dtype=float).ravel() for a in arrays]), digits)
        self.uniq = np.unique(r[np.isfinite(r)])
        self.missing = len(self.uniq)
        self.values = [float(f"{u:.{digits}g}") for u in self.uniq] + [None]

    def index(self, values) -> np.ndarray:
        r = _sig(values, self.digits)
        ok = np.isfinite(r)
        return np.where(ok, np.searchsorted(self.uniq, np.where(ok, r, 0.0)), self.missing)

    def payload(self, hex_colours: bool) -> dict:
        vals = [np.nan if v is None else v for v in self.values]
        cols = colour.rgb(vals, colour.colormap(self.m.cmap), self.m.norm)
        return {"v": self.values, "t": [self.m.fmt(v) for v in vals],
                "c": [colour.hex_colour(c) for c in cols] if hex_colours else cols}


class _Slices:
    """What a spec slices, checked once: metrics, the cell fields that repeat them, the split."""

    def __init__(self, spec: MapSpec):
        self.combos = _combos(spec)
        self.tables: dict[str, _Table] = {}
        for m in spec.metrics:
            flags = [_is_sliced(v.cells, m.key, self.combos) for v in spec.views]
            if any(flags) and not all(flags):
                raise ValueError(f"metric {m.key!r} is sliced in some views but not all")
            if flags and all(flags):
                self.tables[m.key] = _Table(m, [v.cells[slice_key(m.key, *c)] for v in spec.views for c in self.combos],
                                            spec.slice_digits)
        self.field_metric = []
        for f in spec.cell_fields:
            s = any(_is_sliced(v.cells, f.key, self.combos) for v in spec.views)
            if s and f.key not in self.tables:
                raise ValueError(f"cell field {f.key!r} is sliced: a sliced cell field must repeat a sliced metric's key")
            self.field_metric.append(f.key if s else None)
        sp = spec.split
        flags = [_is_sliced(v.cells, c, self.combos) for v in spec.views for c in ([sp.total, *sp.columns] if sp else [])]
        if any(flags) and not all(flags):
            raise ValueError("the split is sliced for some of its columns or views but not all")
        self.split = bool(flags) and all(flags)

    def view(self, spec: MapSpec, cells: pd.DataFrame) -> dict:
        """Per view: each sliced metric's table index per cell and slice (cells x slices), and the sliced split."""
        idx = {k: np.stack([t.index(cells[slice_key(k, *c)]) for c in self.combos], axis=1)
               for k, t in self.tables.items()}
        shares = None
        if self.split:
            shares = [[_shares(row, spec.split, lambda r, k, c=c: r[slice_key(k, *c)], digits=2) for c in self.combos]
                      for _, row in cells.iterrows()]
        return {"idx": idx, "shares": shares}

    def max(self, cells: pd.DataFrame, key: str) -> float:
        """The tallest column over every slice, so heights compare between slices."""
        if key not in self.tables:
            return _abs_max(cells[key])
        return max(_abs_max(cells[slice_key(key, *c)]) for c in self.combos)


def _getter(frame, keys, combos):
    """get(row, key, combo), reading the slice column where `key` is sliced in `frame`; and whether any is."""
    sliced = {k for k in keys if _is_sliced(frame, k, combos)}
    return (lambda row, k, c: row[slice_key(k, *c)] if k in sliced else row[k]), bool(sliced)


# ------------------------------------------------------------------ common parts

def _common(spec: MapSpec, sl: _Slices) -> dict:
    metrics = []
    for m in spec.metrics:
        cm = colour.colormap(m.cmap)
        metrics.append({"key": m.key, "label": m.label, "noun": m.noun,
                        "legend": colour.legend(cm, m.norm, m.tick_fmt),
                        "note": m.note or colour.note(m.norm, m.tick_fmt),
                        "height": ("height is the size of the difference, either sign" if colour.is_diverging(m.norm)
                                   else "height is proportional"),
                        "sliced": m.key in sl.tables})
    return {
        "title": spec.title, "lede": spec.lede, "footnote": spec.footnote,
        "credit": spec.basemap_credit, "blank_label": spec.blank_label,
        "metrics": metrics,
        "toggles": [{"key": t.key, "label": t.label, "options": [list(o) for o in t.options]} for t in spec.toggles],
        "field_metric": sl.field_metric,
        "cell_fields": [f.label for f in spec.cell_fields],
        "split": ({"labels": spec.split.labels, "colours": spec.split.colours,
                   "title": spec.split.title} if spec.split else None),
        "summary_title": spec.summary_title, "summary": spec.summary,
        "layers": [{"key": a.key, "label": a.label} for a in spec.areas],
        "outline_layers": [{"key": o.key, "label": o.label, "show": o.show,
                            "dark": list(o.colour_dark), "light": list(o.colour_light)}
                           for o in spec.outlines],
        "rankings": [_ranking(o, spec, sl) for o in spec.outlines if o.ranking],
        "has": {"roads": spec.context.roads is not None, "water": spec.context.water is not None,
                "places": spec.context.places is not None},
    }


def _ranking(o, spec, sl: _Slices) -> dict:
    r = o.ranking
    keys = [r.value.key, *(r.parts or [])]
    get, sliced = _getter(o.items, keys, sl.combos)
    combos = sl.combos if sliced else [()]
    rows = []
    for _, it in o.items.iterrows():
        V = [_num(get(it, r.value.key, c)) for c in combos]
        T = [r.value.fmt(get(it, r.value.key, c)) for c in combos]
        P = [[_num(get(it, k, c)) for k in r.parts] for c in combos] if r.parts else None
        row = {"name": it["name"], "short": it["short"], "value": V[0], "text": T[0], "parts": P[0] if P else None}
        if sliced:
            row.update(V=V, T=T, P=P)
        rows.append(row)
    return {"key": o.key, "title": r.title, "rows": rows}


def _cell_payloads(spec: MapSpec, view, cells: pd.DataFrame, sl: _Slices, tables: dict, as_hex: bool) -> list[dict]:
    """Every cell's values, texts and colours (`c`: hex strings or RGB lists; from `tables` for a sliced
    metric), shown at the first slice; a sliced metric's table indices (`z`) and the sliced split (`zs`)
    let the page switch slices."""
    static = [m for m in spec.metrics if m.key not in sl.tables]
    cols = {m.key: colour.rgb(cells[m.key], colour.colormap(m.cmap), m.norm) for m in static}
    vs = sl.view(spec, cells) if sl.combos else {"idx": {}, "shares": None}
    out = []
    for i, row in cells.iterrows():
        blank = bool(row.get("blank", False))
        v, t, c = {}, {}, {}
        for m in spec.metrics:
            if m.key in sl.tables:
                j, T = int(vs["idx"][m.key][i, 0]), tables[m.key]
                v[m.key], t[m.key], c[m.key] = T["v"][j], T["t"][j], T["c"][j]
            else:
                v[m.key], t[m.key] = _num(row[m.key]), m.fmt(row[m.key])
                c[m.key] = colour.hex_colour(cols[m.key][i]) if as_hex else cols[m.key][i]
        f = [tables[k]["t"][int(vs["idx"][k][i, 0])] if k else fl.fmt(row[fl.key])
             for fl, k in zip(spec.cell_fields, sl.field_metric, strict=True)]
        p = {"blank": blank, "v": v, "t": t, "c": c, "f": f,
             "w": [[k, *(view.where[k][i] or [None, None])] for k in view.where]}
        if vs["shares"] is not None:
            p["zs"] = None if blank else vs["shares"][i]
            p["s"] = p["zs"][0] if p["zs"] else None
        else:
            p["s"] = None if blank else _shares(row, spec.split)
        if vs["idx"]:
            p["z"] = {k: vs["idx"][k][i].tolist() for k in vs["idx"]}
        out.append(p)
    return out


def _area_items(spec: MapSpec, layer, sl: _Slices) -> list[dict]:
    fields = [*layer.headline, *layer.fields]
    split_keys = [spec.split.total, *spec.split.columns] if spec.split else []
    get, sliced = _getter(layer.items, [f.key for f in fields] + split_keys, sl.combos)
    combos = sl.combos if sliced else [()]
    out = []
    for _, it in layer.items.iterrows():
        H, F, S = [], [], []
        for c in combos:
            H.append(list(next(((f.fmt(get(it, f.key, c)), f.label) for f in layer.headline
                                if _num(get(it, f.key, c)) is not None), ("—", ""))))
            F.append([[f.label, f.fmt(get(it, f.key, c))] for f in layer.fields])
            S.append(_shares(it, spec.split, lambda r, k, c=c: get(r, k, c)))
        item = {"name": it["name"], "kind": layer.kind, "h": H[0], "f": F[0], "s": S[0],
                "notes": layer.notes(it) if layer.notes else []}
        if sliced:
            item.update(H=H, F=F, S=S)
        out.append(item)
    return out


# ------------------------------------------------------------------ 3D

def payload_3d(spec: MapSpec) -> dict:
    sl = _Slices(spec)
    d = _common(spec, sl)
    d["tables"] = {k: t.payload(hex_colours=False) for k, t in sl.tables.items()}
    crs = spec.crs
    lonlat = lambda pts: np.round(geometry.to_lonlat(pts, crs), 5).tolist()  # noqa: E731
    rings_ll = lambda g, tol: [lonlat(r) for r in geometry.rings(  # noqa: E731
        g.simplify(tol, preserve_topology=True))]
    d["views"] = []
    for v in spec.views:
        cells = v.cells.reset_index(drop=True)
        verts = geometry.to_lonlat(hex_vertices(cells.q, cells.r, v.side), crs)
        feats = []
        for i, p in enumerate(_cell_payloads(spec, v, cells, sl, d["tables"], as_hex=False)):
            ring = np.round(verts[i], 5).tolist()
            feats.append({"type": "Feature", "properties": p,
                          "geometry": {"type": "Polygon", "coordinates": [[*ring, ring[0]]]}})
        minx, miny, maxx, maxy = v.frame.bounds
        b = geometry.to_lonlat(np.array([[minx, miny], [maxx, maxy]]), crs).tolist()
        d["views"].append({
            "key": v.key, "label": v.label, "description": v.description, "noun": v.cell_noun,
            "bounds": b, "height": v.height, "places": v.place_labels,
            "max": {m.key: sl.max(cells, m.key) for m in spec.metrics},
            "cells": {"type": "FeatureCollection", "features": feats},
            "frame": rings_ll(v.frame, 100)})
    d["areas"] = {}
    for a in spec.areas:
        items = _area_items(spec, a, sl)
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

    sl = _Slices(spec)
    d = _common(spec, sl)
    d["tables"] = {k: t.payload(hex_colours=True) for k, t in sl.tables.items()}
    fr = geometry.SvgFrame(shapely.unary_union([v.frame for v in spec.views]).bounds)
    d["w"], d["h"] = fr.w, fr.h
    d["views"] = []
    for v in spec.views:
        cells = v.cells.reset_index(drop=True)
        verts = hex_vertices(cells.q, cells.r, v.side)
        out = []
        for i, p in enumerate(_cell_payloads(spec, v, cells, sl, d["tables"], as_hex=True)):
            p["d"] = fr.path(verts[i])
            out.append(p)
        d["views"].append({"key": v.key, "label": v.label, "description": v.description,
                           "noun": v.cell_noun, "box": fr.box(v.frame), "places": v.place_labels,
                           "cells": out, "frame": fr.polygon(v.frame, 100)})
    d["areas"] = {}
    for a in spec.areas:
        items = _area_items(spec, a, sl)
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
