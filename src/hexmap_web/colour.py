"""Colour scales. Two kinds, and each means the same thing on every background:

- sequential: one colormap, light = low and dark = high, on a clipped log scale (`log_norm`). The
  colormap's ends are trimmed so the palest cells do not vanish into a white page and the darkest
  do not swallow an outline.
- diverging: two hues either side of a pale centre (`diverging`, `diverging_norm`), for a
  difference that can be either sign, such as time saved by one option against another.

A value that is missing (NaN) takes one neutral grey, `MISSING`, under both.
"""
from __future__ import annotations

import math

import matplotlib
import numpy as np
from matplotlib.colors import Colormap, LinearSegmentedColormap, ListedColormap, LogNorm, TwoSlopeNorm

TRIM = (0.06, 0.90)
MISSING = [160, 158, 152]          # a value the metric does not have, e.g. no such alternative here
# Reference diverging pair: orange below the centre, blue above, a warm pale grey between.
DIVERGING = ("#eb6834", "#f2f1ec", "#2a78d6")


def colormap(name: str | Colormap = "inferno", trim: tuple[float, float] = TRIM) -> Colormap:
    """The named matplotlib colormap, oriented light = low, trimmed at both ends. A Colormap
    (e.g. from `diverging`) is returned as it is."""
    if isinstance(name, Colormap):
        return name
    base = matplotlib.colormaps[name]
    luma = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b, _ in base([0.0, 1.0])]
    if luma[0] < luma[1]:                     # viridis, magma, inferno run dark -> light
        base = base.reversed()
    lo, hi = trim
    return ListedColormap(base(np.linspace(lo, hi, 256)), name)


def diverging(low: str = DIVERGING[0], mid: str = DIVERGING[1], high: str = DIVERGING[2]) -> Colormap:
    """`low` below the centre, `mid` at it, `high` above."""
    return LinearSegmentedColormap.from_list("diverging", [low, mid, high])


def log_norm(lo: float, hi: float) -> LogNorm:
    """A clipped log scale: values below `lo` take the lowest colour, above `hi` the highest."""
    return LogNorm(vmin=lo, vmax=hi, clip=True)


def diverging_norm(lo: float, hi: float, centre: float = 0.0) -> TwoSlopeNorm:
    """A linear scale with `centre` in the middle of the bar, each side stretched to its own end.
    Values beyond `lo` or `hi` take the end colours."""
    if not lo < centre < hi:
        raise ValueError(f"need lo < centre < hi, got {lo}, {centre}, {hi}")
    return TwoSlopeNorm(vcenter=centre, vmin=lo, vmax=hi)


def is_diverging(norm) -> bool:
    return isinstance(norm, TwoSlopeNorm)


def doublings(norm: LogNorm) -> list[float]:
    """Ticks at the minimum, doubled until the maximum."""
    n = round(math.log2(norm.vmax / norm.vmin))
    return [norm.vmin * 2 ** i for i in range(n + 1)]


def ticks(norm) -> list[float]:
    """Doublings on a log scale; on a diverging one the two ends, the centre and the halfway points."""
    if isinstance(norm, LogNorm):
        return doublings(norm)
    if is_diverging(norm):
        lo, c, hi = norm.vmin, norm.vcenter, norm.vmax
        return [lo, (lo + c) / 2, c, (c + hi) / 2, hi]
    return np.linspace(norm.vmin, norm.vmax, 5).tolist()


def rgb(values, cmap, norm) -> list[list[int]]:
    """0-255 RGB per value; a missing value is `MISSING`."""
    v = np.asarray(values, dtype=float)
    ok = np.isfinite(v)
    c = cmap(norm(np.where(ok, v, norm.vmin)))[:, :3]         # out of range takes the end colours
    out = np.round(c * 255).astype(int)
    out[~ok] = MISSING
    return out.tolist()


def hex_colour(c: list[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*c)


def legend(cmap, norm, fmt, stops: int = 12) -> dict:
    """Gradient stops and tick positions (0-1 along the bar) with labels. A clipped end is marked:
    "+" on a log scale's top, and "≤" / "≥" on a diverging scale's two ends."""
    t = ticks(norm)
    pos = [float(np.clip(norm(x), 0.0, 1.0)) for x in t]
    labels = [fmt(x) for x in t]
    if is_diverging(norm):
        labels[0], labels[-1] = "≤" + labels[0], "≥" + labels[-1]
    else:
        labels[-1] = labels[-1] + "+"
    s = np.linspace(0, 1, stops)
    return {"ticks": [round(p, 4) for p in pos], "labels": labels,
            "stops": [matplotlib.colors.to_hex(cmap(x)) for x in s]}


def note(norm, fmt) -> str:
    """What the colours mean, for a metric that does not say."""
    if is_diverging(norm):
        return f"pale is {fmt(norm.vcenter)}; the two colours run apart either side"
    return "darker is higher (log scale)"
