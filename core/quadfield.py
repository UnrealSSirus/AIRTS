"""QuadField — uniform-grid spatial index for fast proximity queries.

Divides the map into fixed-size cells.  Each cell tracks which units
overlap it, split by team.  Units are updated incrementally via
moved_unit() which early-outs when the unit hasn't crossed a cell
boundary (the common case).

Dead units must be removed via remove_unit() — queries assume all
units in the grid are alive (no per-unit alive check).

Deduplication uses an integer stamp (BAR-style) instead of a set:
each query bumps a counter, and units whose _temp_num already matches
the current stamp are skipped.  O(1) per unit with zero allocation.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from entities.unit import Unit


class QuadCell:
    __slots__ = ("units", "team_units")

    def __init__(self):
        self.units: list[Unit] = []
        self.team_units: dict[int, list[Unit]] = {}

    def add(self, unit: Unit) -> None:
        self.units.append(unit)
        team_list = self.team_units.get(unit.team)
        if team_list is None:
            self.team_units[unit.team] = [unit]
        else:
            team_list.append(unit)

    def remove(self, unit: Unit) -> None:
        try:
            self.units.remove(unit)
        except ValueError:
            pass
        team_list = self.team_units.get(unit.team)
        if team_list is not None:
            try:
                team_list.remove(unit)
            except ValueError:
                pass


class QuadField:
    """Uniform grid spatial index.

    Parameters
    ----------
    width, height : int
        Map dimensions in world-space pixels.
    cell_size : int
        Side length of each square cell (pixels).
    """

    __slots__ = ("cell_size", "inv_cell", "num_cols", "num_rows", "cells",
                 "_query_counter")

    def __init__(self, width: int, height: int, cell_size: int = 64):
        self.cell_size = cell_size
        self.inv_cell = 1.0 / cell_size
        self.num_cols = math.ceil(width / cell_size) + 1
        self.num_rows = math.ceil(height / cell_size) + 1
        self.cells: list[QuadCell] = [
            QuadCell() for _ in range(self.num_cols * self.num_rows)
        ]
        self._query_counter: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cell_index(self, col: int, row: int) -> int:
        return row * self.num_cols + col

    def get_quads(self, x: float, y: float, radius: float) -> list[int]:
        """Return cell indices overlapping the circle (x, y, radius)."""
        inv = self.inv_cell
        col_min = max(int((x - radius) * inv), 0)
        col_max = min(int((x + radius) * inv), self.num_cols - 1)
        row_min = max(int((y - radius) * inv), 0)
        row_max = min(int((y + radius) * inv), self.num_rows - 1)

        nc = self.num_cols
        result: list[int] = []
        for r in range(row_min, row_max + 1):
            base = r * nc
            for c in range(col_min, col_max + 1):
                result.append(base + c)
        return result

    # ------------------------------------------------------------------
    # Unit lifecycle
    # ------------------------------------------------------------------

    def add_unit(self, unit: Unit) -> None:
        """Insert a unit into all overlapping cells."""
        quads = self.get_quads(unit.x, unit.y, unit.radius)
        cells = self.cells
        for qi in quads:
            cells[qi].add(unit)
        unit._quad_cells = quads

    def remove_unit(self, unit: Unit) -> None:
        """Remove a unit from all its current cells."""
        cells = self.cells
        for qi in unit._quad_cells:
            cells[qi].remove(unit)
        unit._quad_cells = []

    def moved_unit(self, unit: Unit) -> None:
        """Incrementally update a unit's cell memberships.

        Early-outs when the unit is still in the same set of cells,
        which is the overwhelmingly common case (~95%+ of frames).
        """
        new_quads = self.get_quads(unit.x, unit.y, unit.radius)
        old_quads = unit._quad_cells

        # Fast equality check — same length and same contents
        if len(new_quads) == len(old_quads):
            same = True
            for i in range(len(new_quads)):
                if new_quads[i] != old_quads[i]:
                    same = False
                    break
            if same:
                return

        cells = self.cells
        old_set = set(old_quads)
        new_set = set(new_quads)

        for qi in old_set - new_set:
            cells[qi].remove(unit)
        for qi in new_set - old_set:
            cells[qi].add(unit)

        unit._quad_cells = new_quads

    # ------------------------------------------------------------------
    # Queries
    #
    # All query methods use stamp-based deduplication: a global counter
    # is bumped each call and compared against unit._temp_num.  No set
    # allocation, no hashing — just an int compare and write per unit.
    #
    # Units in the grid are assumed alive; dead units must be removed
    # via remove_unit() at cleanup time.
    #
    # An optional *out* list can be passed in for reuse on hot paths.
    # ------------------------------------------------------------------

    def get_units_in_cells(self, x: float, y: float, radius: float,
                           out: list[Unit] | None = None) -> list[Unit]:
        """Return all unique units from cells overlapping (x, y, radius).

        May include units outside the actual radius — use
        get_units_exact() for precise distance filtering.
        """
        self._query_counter += 1
        stamp = self._query_counter
        quads = self.get_quads(x, y, radius)
        cells = self.cells
        if out is None:
            result: list[Unit] = []
        else:
            result = out
            result.clear()
        for qi in quads:
            for u in cells[qi].units:
                if u._temp_num == stamp:
                    continue
                u._temp_num = stamp
                result.append(u)
        return result

    def get_units_exact(self, x: float, y: float, radius: float,
                        out: list[Unit] | None = None) -> list[Unit]:
        """Return units within *radius + unit.radius* of (x, y)."""
        self._query_counter += 1
        stamp = self._query_counter
        quads = self.get_quads(x, y, radius)
        cells = self.cells
        if out is None:
            result: list[Unit] = []
        else:
            result = out
            result.clear()
        for qi in quads:
            for u in cells[qi].units:
                if u._temp_num == stamp:
                    continue
                u._temp_num = stamp
                dx = u.x - x
                dy = u.y - y
                max_d = radius + u.radius
                if dx * dx + dy * dy <= max_d * max_d:
                    result.append(u)
        return result

    def get_team_units_exact(
        self, x: float, y: float, radius: float, team: int,
        out: list[Unit] | None = None,
    ) -> list[Unit]:
        """Return same-team units within *radius + unit.radius*."""
        self._query_counter += 1
        stamp = self._query_counter
        quads = self.get_quads(x, y, radius)
        cells = self.cells
        if out is None:
            result: list[Unit] = []
        else:
            result = out
            result.clear()
        for qi in quads:
            team_list = cells[qi].team_units.get(team)
            if team_list is None:
                continue
            for u in team_list:
                if u._temp_num == stamp:
                    continue
                u._temp_num = stamp
                dx = u.x - x
                dy = u.y - y
                max_d = radius + u.radius
                if dx * dx + dy * dy <= max_d * max_d:
                    result.append(u)
        return result

    def get_enemy_units_exact(
        self, x: float, y: float, radius: float, my_team: int,
        out: list[Unit] | None = None,
    ) -> list[Unit]:
        """Return enemy units within *radius + unit.radius*.

        Iterates only enemy-team lists in each cell (zero filtering cost).
        """
        self._query_counter += 1
        stamp = self._query_counter
        quads = self.get_quads(x, y, radius)
        cells = self.cells
        if out is None:
            result: list[Unit] = []
        else:
            result = out
            result.clear()
        for qi in quads:
            cell_teams = cells[qi].team_units
            for team_id, team_list in cell_teams.items():
                if team_id == my_team:
                    continue
                for u in team_list:
                    if u._temp_num == stamp:
                        continue
                    u._temp_num = stamp
                    dx = u.x - x
                    dy = u.y - y
                    max_d = radius + u.radius
                    if dx * dx + dy * dy <= max_d * max_d:
                        result.append(u)
        return result

    def get_nearby_split(
        self, x: float, y: float, radius: float, my_team: int,
        out_enemies: list[Unit] | None = None,
        out_allies: list[Unit] | None = None,
    ) -> tuple[list[Unit], list[Unit]]:
        """Single-pass query returning (enemies, allies) within radius.

        Iterates each cell's team_units once, partitioning into two
        output lists.  One get_quads call, one stamp increment — half
        the work of calling get_enemy_units_exact + get_team_units_exact.
        """
        self._query_counter += 1
        stamp = self._query_counter
        quads = self.get_quads(x, y, radius)
        cells = self.cells

        if out_enemies is None:
            enemies: list[Unit] = []
        else:
            enemies = out_enemies
            enemies.clear()
        if out_allies is None:
            allies: list[Unit] = []
        else:
            allies = out_allies
            allies.clear()

        for qi in quads:
            cell_teams = cells[qi].team_units
            for team_id, team_list in cell_teams.items():
                is_ally = team_id == my_team
                target = allies if is_ally else enemies
                for u in team_list:
                    if u._temp_num == stamp:
                        continue
                    u._temp_num = stamp
                    dx = u.x - x
                    dy = u.y - y
                    max_d = radius + u.radius
                    if dx * dx + dy * dy <= max_d * max_d:
                        target.append(u)

        return enemies, allies

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def rebuild(self, units) -> None:
        """Clear the grid and re-insert all units from scratch."""
        for cell in self.cells:
            cell.units.clear()
            cell.team_units.clear()
        for u in units:
            if u.alive:
                self.add_unit(u)

    def clear(self) -> None:
        """Remove everything from the grid."""
        for cell in self.cells:
            cell.units.clear()
            cell.team_units.clear()
