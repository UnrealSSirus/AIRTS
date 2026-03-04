"""Bounds clamping for units."""
from __future__ import annotations
from entities.unit import Unit


def clamp_units_to_bounds(units: list[Unit], width: int, height: int):
    for u in units:
        if u.is_building:
            continue
        r = u.radius
        u.x = max(r, min(u.x, width - r))
        u.y = max(r, min(u.y, height - r))
