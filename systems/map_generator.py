"""
Map generators.

Each generator populates a list of entities for a given map size.
Swap generators to create different map layouts.
"""
from __future__ import annotations
import random
import math
from entities.base import Entity
from entities.shapes import RectEntity, CircleEntity
from entities.command_center import CommandCenter
from entities.metal_spot import MetalSpot
from config.settings import OBSTACLE_COLOR, CC_SPAWN_INTERVAL, METAL_SPOT_RADIUS, CC_OBSTACLE_EXCLUSION


class BaseMapGenerator:
    """Interface for map generators."""

    def generate(self, width: int, height: int, player_team: dict | None = None) -> list[Entity]:
        raise NotImplementedError


class DefaultMapGenerator(BaseMapGenerator):
    """Random obstacles, command centers placed by team layout."""

    def __init__(self, obstacle_count: tuple[int, int] = (4, 8),
                 metal_spots_per_side: int = 0):
        self._obs_range = obstacle_count
        self._metal_spots_per_side = metal_spots_per_side

    def generate(self, width: int, height: int, player_team: dict | None = None) -> list[Entity]:
        entities: list[Entity] = []
        pt = player_team or {1: 1, 2: 2}
        self._place_command_centers(entities, width, height, pt)
        n_teams = len({t for t in pt.values()})
        self._place_metal_spots(entities, width, height, n_teams)
        self._place_obstacles(entities, width, height)
        return entities

    def _random_point_in_rectangle(self, x1: int, y1: int, x2: int, y2: int) -> tuple[float, float]:
        return random.uniform(x1, x2), random.uniform(y1, y2)

    def _find_obstacle_position(self,
        x1: int, y1: int, x2: int, y2: int,
        obs_width: int, obs_height: int,
        obs_type: str,
        entities: list[Entity]
    ) -> tuple[float, float]:
        command_centers = [e for e in entities if isinstance(e, CommandCenter)]
        while True:
            x, y = self._random_point_in_rectangle(x1, y1, x2, y2)

            # Enforce exclusion zone around command centers
            if obs_type == "rect":
                cx, cy = x + obs_width / 2, y + obs_height / 2
            else:
                cx, cy = x, y
            if any(math.hypot(cx - cc.x, cy - cc.y) < CC_OBSTACLE_EXCLUSION for cc in command_centers):
                continue

            if obs_type == "rect":
                if not any(e.get_rect().colliderect(x, y, obs_width, obs_height) for e in entities):
                    return x, y
            elif obs_type == "circle":
                if not any(math.hypot(x - e.x, y - e.y) < e.collision_radius() for e in entities):
                    return x, y
            else:
                raise ValueError(f"Invalid obstacle type: {obs_type}")


    def _place_obstacles(self, entities: list[Entity], width: int, height: int):
        for _ in range(random.randint(*self._obs_range)):
            if random.random() < 0.5:
                w = random.uniform(30, 80)
                h = random.uniform(30, 80)
                x, y = self._find_obstacle_position(0, 0, width, height, w, h, "rect", entities)
                obs = RectEntity(
                    x=x,
                    y=y,
                    width=w, height=h,
                )
            else:
                r = random.uniform(15, 40)
                x, y = self._find_obstacle_position(0, 0, width, height, r, r, "circle", entities)
                obs = CircleEntity(
                    x=x,
                    y=y,
                    radius=r,
                )
            obs.obstacle = True
            obs.color = OBSTACLE_COLOR
            entities.append(obs)

    def _place_command_centers(self, entities: list[Entity], width: int, height: int,
                                player_team: dict):
        # Group players by team, preserving sorted order within each team
        team_players: dict[int, list[int]] = {}
        for pid in sorted(player_team):
            tid = player_team[pid]
            team_players.setdefault(tid, []).append(pid)

        sorted_teams = sorted(team_players)
        n_teams = len(sorted_teams)

        if n_teams <= 2:
            # Classic left/right placement
            inset = 80
            n_slots = max(n_teams, 2)
            if n_slots == 2 and n_teams == 2:
                side_xs = {sorted_teams[0]: inset, sorted_teams[1]: width - inset}
            elif n_teams == 1:
                side_xs = {sorted_teams[0]: inset}
            else:
                side_xs = {sorted_teams[0]: inset, sorted_teams[1]: width - inset}

            for tid, pids in team_players.items():
                sx = side_xs[tid]
                m = len(pids)
                for j, pid in enumerate(pids):
                    sy = height * (j + 1) / (m + 1)
                    cc = CommandCenter(sx, sy, team=tid, player_id=pid)
                    cc._bounds = (width, height)
                    cc._spawn_timer = CC_SPAWN_INTERVAL
                    entities.append(cc)
        else:
            # Radial placement for 3+ teams
            cx, cy = width / 2, height / 2
            radius = min(width, height) * 0.35
            for i, tid in enumerate(sorted_teams):
                angle = 2 * math.pi * i / n_teams - math.pi / 2  # start at top
                sx = cx + radius * math.cos(angle)
                sy = cy + radius * math.sin(angle)
                pids = team_players[tid]
                m = len(pids)
                for j, pid in enumerate(pids):
                    # Offset multiple players on same team perpendicular to radial
                    if m > 1:
                        perp_angle = angle + math.pi / 2
                        offset = (j - (m - 1) / 2) * 40
                        px = sx + offset * math.cos(perp_angle)
                        py = sy + offset * math.sin(perp_angle)
                    else:
                        px, py = sx, sy
                    cc = CommandCenter(px, py, team=tid, player_id=pid)
                    cc._bounds = (width, height)
                    cc._spawn_timer = CC_SPAWN_INTERVAL
                    entities.append(cc)

    def _place_metal_spots(self, entities: list[Entity], width: int, height: int,
                           n_teams: int = 2):
        count = self._metal_spots_per_side if self._metal_spots_per_side > 0 else random.randint(2, 4)

        if n_teams <= 2:
            # Classic mirror: left half → right half
            for _ in range(count):
                x = random.uniform(200 + METAL_SPOT_RADIUS, width // 2 - METAL_SPOT_RADIUS)
                y = random.uniform(60 + METAL_SPOT_RADIUS, height // 2 - METAL_SPOT_RADIUS)
                metal_spot = MetalSpot(x, y)
                metal_spot_2 = MetalSpot(width - x, height - y)
                entities.append(metal_spot)
                entities.append(metal_spot_2)
        else:
            # N-fold rotational symmetry around map center
            cx, cy = width / 2, height / 2
            min_dist = 60.0
            max_dist = min(width, height) * 0.35 - 20
            sector_angle = 2 * math.pi / n_teams
            ccs = [e for e in entities if isinstance(e, CommandCenter)]

            for _ in range(count):
                # Pick random point in one sector (the first sector)
                for _attempt in range(50):
                    angle = random.uniform(0.1, sector_angle - 0.1)
                    dist = random.uniform(min_dist, max_dist)
                    valid = True
                    # Check all N rotated copies are within bounds and away from CCs
                    spots_to_add = []
                    for k in range(n_teams):
                        rot = sector_angle * k
                        mx = cx + dist * math.cos(angle + rot)
                        my = cy + dist * math.sin(angle + rot)
                        # Bounds check with margin
                        if mx < METAL_SPOT_RADIUS + 10 or mx > width - METAL_SPOT_RADIUS - 10:
                            valid = False
                            break
                        if my < METAL_SPOT_RADIUS + 10 or my > height - METAL_SPOT_RADIUS - 10:
                            valid = False
                            break
                        # CC exclusion
                        if any(math.hypot(mx - cc.x, my - cc.y) < CC_OBSTACLE_EXCLUSION
                               for cc in ccs):
                            valid = False
                            break
                        # Overlap with existing metal spots
                        if any(math.hypot(mx - e.x, my - e.y) < METAL_SPOT_RADIUS * 3
                               for e in entities if isinstance(e, MetalSpot)):
                            valid = False
                            break
                        spots_to_add.append(MetalSpot(mx, my))
                    if valid and len(spots_to_add) == n_teams:
                        for ms in spots_to_add:
                            entities.append(ms)
                        break
