"""Colour scales: one sequential colormap, light = low and dark = high, on a clipped log scale.

The same scale is used on every background: a colour means the same value on a dark basemap and
a light one. The colormap's ends are trimmed so the palest cells do not vanish into a white page
and the darkest do not swallow an outline.
"""
from __future__ import annotations

import math

import matplotlib
import numpy as np
from matplotlib.colors import ListedColormap, LogNorm

TRIM = (0.06, 0.90)


def colormap(name: str = "inferno", trim: tuple[float, float] = TRIM) -> ListedColormap:
    """The named matplotlib colormap, oriented light = low, trimmed at both ends."""
    base = matplotlib.colormaps[name]
    luma = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b, _ in base([0.0, 1.0])]
    if luma[0] < luma[1]:                     # viridis, magma, inferno run dark -> light
        base = base.reversed()
    lo, hi = trim
    return ListedColormap(base(np.linspace(lo, hi, 256)), name)


def log_norm(lo: float, hi: float) -> LogNorm:
    """A clipped log scale: values below `lo` take the lowest colour, above `hi` the highest."""
    return LogNorm(vmin=lo, vmax=hi, clip=True)


def doublings(norm: LogNorm) -> list[float]:
    """Ticks at the minimum, doubled until the maximum."""
    n = round(math.log2(norm.vmax / norm.vmin))
    return [norm.vmin * 2 ** i for i in range(n + 1)]


def rgb(values, cmap, norm) -> list[list[int]]:
    """0-255 RGB per value."""
    c = cmap(norm(np.asarray(values, dtype=float)))[:, :3]
    return np.round(c * 255).astype(int).tolist()


def hex_colour(c: list[int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*c)


def legend(cmap, norm: LogNorm, fmt, stops: int = 12) -> dict:
    """Gradient stops and tick positions (0-1 along the bar) with labels."""
    ticks = doublings(norm)
    pos = [(math.log(t) - math.log(norm.vmin)) / (math.log(norm.vmax) - math.log(norm.vmin))
           for t in ticks]
    labels = [fmt(t) for t in ticks]
    labels[-1] = labels[-1] + "+"
    s = np.linspace(0, 1, stops)
    return {"ticks": [round(p, 4) for p in pos], "labels": labels,
            "stops": [matplotlib.colors.to_hex(cmap(x)) for x in s]}
