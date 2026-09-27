"""Number formats for the pages. The pages show text formatted here, so a project changes how a
number reads in Python, once, and both maps agree."""
from __future__ import annotations

import math


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and not math.isfinite(v))


def money(v) -> str:
    """$1.23 B, $45.6 M, $12,345; a missing value is a dash."""
    if not _ok(v):
        return "—"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f} B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.1f} M"
    return f"${v:,.0f}"


def money_short(v) -> str:
    """For legend ticks: $2k, $1.5M."""
    if not _ok(v):
        return "—"
    if v >= 1e6:
        return f"${v / 1e6:g}M"
    return f"${v / 1e3:g}k" if v >= 1e3 else f"${v:g}"


def number(v) -> str:
    return "—" if not _ok(v) else f"{v:,.0f}"


def percent(v) -> str:
    return "—" if not _ok(v) else f"{v * 100:.0f}%"
