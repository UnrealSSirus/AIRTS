"""Uniform-cell spatial hash grid for broad-phase spatial queries."""
from __future__ import annotations


class SpatialGrid:
    """A spatial hash that buckets objects by their (x, y) position.

    Cell size should be at least as large as the smallest query radius
    you plan to use frequently.  Objects must have ``.x`` and ``.y`` attrs.
    """

    def __init__(self, cell_size: float = 50.0):
        self.cell_size = cell_size
        self._inv = 1.0 / cell_size
        self._cells: dict[tuple[int, int], list] = {}

    def clear(self):
        self._cells.clear()

    def insert(self, obj):
        """Insert an object with .x, .y attributes."""
        key = (int(obj.x * self._inv), int(obj.y * self._inv))
        bucket = self._cells.get(key)
        if bucket is None:
            self._cells[key] = [obj]
        else:
            bucket.append(obj)

    def query_radius(self, x: float, y: float, radius: float) -> list:
        """Return all objects whose cell is within *radius* of (x, y).

        This is a broad-phase check — callers must still do a precise
        distance check on returned objects.  Returns candidates that
        could possibly be within radius (with one cell of margin).
        """
        r = radius + self.cell_size          # margin for cell boundary
        inv = self._inv
        min_cx = int((x - r) * inv)
        max_cx = int((x + r) * inv)
        min_cy = int((y - r) * inv)
        max_cy = int((y + r) * inv)
        cells = self._cells
        result = []
        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                bucket = cells.get((cx, cy))
                if bucket is not None:
                    result.extend(bucket)
        return result

    def query_pairs(self, max_dist: float) -> list[tuple]:
        """Return all (a, b) pairs from same or adjacent cells.

        For collision detection — only checks 4 neighbor directions
        to avoid duplicate pairs (right, below-left, below, below-right).
        """
        cells = self._cells
        neighbor_offsets = ((1, 0), (-1, 1), (0, 1), (1, 1))
        pairs = []
        for key, bucket in cells.items():
            # Pairs within this cell
            for i in range(len(bucket)):
                for j in range(i + 1, len(bucket)):
                    pairs.append((bucket[i], bucket[j]))
            # Pairs with neighboring cells
            cx, cy = key
            for dx, dy in neighbor_offsets:
                other = cells.get((cx + dx, cy + dy))
                if other is not None:
                    for a in bucket:
                        for b in other:
                            pairs.append((a, b))
        return pairs
