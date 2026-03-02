"""Collision resolution and bounds clamping."""
from __future__ import annotations
import math
import random
from entities.unit import Unit

_sqrt = math.sqrt
_hypot = math.hypot
_cos = math.cos
_sin = math.sin
_tau = math.tau
_rand = random.uniform


def _collide_pair(a, b):
    """Resolve overlap between two units."""
    dx = b.x - a.x
    dy = b.y - a.y
    dist_sq = dx * dx + dy * dy
    min_dist = a.radius + b.radius
    if dist_sq >= min_dist * min_dist:
        return
    if dist_sq > 0:
        dist = _sqrt(dist_sq)
        overlap = min_dist - dist
        nx = dx / dist
        ny = dy / dist
        a_bld = a.is_building
        b_bld = b.is_building
        if a_bld and b_bld:
            return
        if a_bld:
            b.x += nx * overlap
            b.y += ny * overlap
        elif b_bld:
            a.x -= nx * overlap
            a.y -= ny * overlap
        else:
            half = overlap * 0.5
            a.x -= nx * half
            a.y -= ny * half
            b.x += nx * half
            b.y += ny * half
    else:
        a_bld = a.is_building
        b_bld = b.is_building
        if a_bld and b_bld:
            return
        angle = _rand(0, _tau)
        c = _cos(angle) * 0.5
        s = _sin(angle) * 0.5
        if a_bld:
            b.x += c
            b.y += s
        elif b_bld:
            a.x += c
            a.y += s
        else:
            a.x += c
            a.y += s


def resolve_unit_collisions(units: list[Unit], dt: float, grid=None):
    if grid is None:
        for i in range(len(units)):
            for j in range(i + 1, len(units)):
                _collide_pair(units[i], units[j])
        return

    # Iterate grid cells directly — avoids building an intermediate pair list
    cells = grid._cells
    _offsets = ((1, 0), (-1, 1), (0, 1), (1, 1))
    for key, bucket in cells.items():
        n = len(bucket)
        for i in range(n):
            a = bucket[i]
            for j in range(i + 1, n):
                _collide_pair(a, bucket[j])
        cx, cy = key
        for dx, dy in _offsets:
            other = cells.get((cx + dx, cy + dy))
            if other is not None:
                for a in bucket:
                    for b in other:
                        _collide_pair(a, b)


def resolve_obstacle_collisions(units: list[Unit], circle_obs, rect_obs, dt: float):
    """Resolve unit-vs-obstacle overlaps.

    circle_obs: list of (cx, cy, radius) tuples
    rect_obs:   list of (x, y, w, h) tuples
    """
    for unit in units:
        ux = unit.x
        uy = unit.y
        ur = unit.radius
        for ox, oy, orad in circle_obs:
            dx = ux - ox
            dy = uy - oy
            min_dist = ur + orad
            dist_sq = dx * dx + dy * dy
            if dist_sq < min_dist * min_dist:
                if dist_sq > 0:
                    dist = _sqrt(dist_sq)
                    push = min_dist - dist
                    nx = dx / dist
                    ny = dy / dist
                    ux += nx * push
                    uy += ny * push
                else:
                    angle = _rand(0, _tau)
                    ux += _cos(angle) * 0.5
                    uy += _sin(angle) * 0.5
        for rx, ry, rw, rh in rect_obs:
            cpx = max(rx, min(ux, rx + rw))
            cpy = max(ry, min(uy, ry + rh))
            dx = ux - cpx
            dy = uy - cpy
            dist_sq = dx * dx + dy * dy
            if dist_sq < ur * ur:
                if dist_sq > 0:
                    dist = _sqrt(dist_sq)
                    push = ur - dist
                    ux += (dx / dist) * push
                    uy += (dy / dist) * push
                else:
                    angle = _rand(0, _tau)
                    ux += _cos(angle) * 0.5
                    uy += _sin(angle) * 0.5
        unit.x = ux
        unit.y = uy


def clamp_units_to_bounds(units: list[Unit], width: int, height: int):
    for u in units:
        if u.is_building:
            continue
        r = u.radius
        u.x = max(r, min(u.x, width - r))
        u.y = max(r, min(u.y, height - r))
