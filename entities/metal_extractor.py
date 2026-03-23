from __future__ import annotations
from config.settings import (
    HEALTH_BAR_OFFSET,
    METAL_EXTRACTOR_SPAWN_BONUS,
    REINFORCE_BONUS_MULTIPLIER,
    METAL_SPOT_CAPTURE_RADIUS,
    SELECTED_COLOR,
    TEAM_COLORS, PLAYER_COLORS,
)
from entities.unit import Unit
from entities.metal_spot import MetalSpot
from systems.abilities import Reinforce, ability_from_dict
import pygame
import math


class MetalExtractor(Unit):
    def __init__(self, *, metal_spot: MetalSpot | None = None, team: int = 1,
                 x: float = 0, y: float = 0):
        if metal_spot is not None:
            x, y = metal_spot.x, metal_spot.y
        super().__init__(x, y, team, unit_type="metal_extractor")
        self.metal_spot = metal_spot
        self.rotation: float = 0.0
        self.rotation_speed: float = 10.0
        self.abilities = [Reinforce()]

    def get_spawn_bonus(self) -> float:
        """Return additive spawn bonus (e.g. 0.08 or 0.16 if reinforced)."""
        bonus = METAL_EXTRACTOR_SPAWN_BONUS
        for ability in self.abilities:
            if isinstance(ability, Reinforce) and ability.active:
                bonus *= REINFORCE_BONUS_MULTIPLIER
        return bonus

    def update(self, dt: float):
        super().update(dt)
        self.rotation = (self.rotation + dt * self.rotation_speed) % math.tau
        for ability in self.abilities:
            ability.update(self, dt)

    def on_destroy(self):
        if self.metal_spot is not None:
            self.metal_spot.release()
            self.metal_spot = None

    def draw(self, surface: pygame.Surface):
        # draw a rotating equilateral triangle centered at (x, y)
        r = self.radius
        s = r * math.sqrt(3) / 2
        static_points = [
            complex(0, r),
            complex(-s, -r / 2),
            complex(s, -r / 2),
        ]
        rotated_points = [p * complex(math.cos(self.rotation), math.sin(self.rotation)) for p in static_points]
        points = [(p.real + self.x, p.imag + self.y) for p in rotated_points]

        pygame.draw.polygon(surface, (0, 0, 0), points, 1)

        # Draw plating arcs for Reinforce ability
        for ability in self.abilities:
            if isinstance(ability, Reinforce) and ability.stacks > 0:
                self._draw_plating_arcs(surface, ability.stacks)

        if self.selected:
            pygame.draw.circle(surface, SELECTED_COLOR, (self.x, self.y), self.radius + 2, 1)

        self.draw_health_bar(surface, self.x, self.y, self.radius + HEALTH_BAR_OFFSET)

    def _draw_plating_arcs(self, surface: pygame.Surface, stacks: int):
        """Draw cardinal plating arcs on the capture radius boundary."""
        arc_color = TEAM_COLORS.get(self.team, PLAYER_COLORS[0])
        arc_r = METAL_SPOT_CAPTURE_RADIUS
        rect = pygame.Rect(
            self.x - arc_r, self.y - arc_r,
            arc_r * 2, arc_r * 2,
        )
        # Each arc spans 87.5 degrees, centered at N, E, S, W
        # pygame.draw.arc uses radians, counter-clockwise from +x axis
        arc_span = math.radians(87.5)
        half_span = arc_span / 2
        # Cardinal centers: N=90deg, E=0deg, S=270deg, W=180deg (math convention)
        cardinal_angles = [
            math.radians(90),    # N
            math.radians(0),     # E
            math.radians(270),   # S
            math.radians(180),   # W
        ]
        for i in range(min(stacks, 4)):
            center = cardinal_angles[i]
            start = center - half_span
            end = center + half_span
            pygame.draw.arc(surface, arc_color, rect, start, end, 2)

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "rotation": self.rotation,
            "rotation_speed": self.rotation_speed,
            "metal_spot_id": self.metal_spot.entity_id if self.metal_spot else None,
            "max_hp": self.max_hp,
            "abilities": [a.to_dict() for a in self.abilities],
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> MetalExtractor:
        me = cls(team=data["team"], x=data["x"], y=data["y"])
        me.entity_id = data["entity_id"]
        me.color = tuple(data["color"])
        me.selected = data["selected"]
        me.obstacle = data["obstacle"]
        me.alive = data["alive"]
        me.hp = data["hp"]
        me.max_hp = data.get("max_hp", me.max_hp)
        me.laser_cooldown = data.get("laser_cooldown", 0.0)
        me.facing_angle = data.get("facing_angle", 0.0)
        me.line_of_sight = data.get("line_of_sight", me.line_of_sight)
        me.fire_mode = data.get("fire_mode", me.fire_mode)
        me.selectable = data.get("selectable", False)
        me._bounds = tuple(data.get("_bounds", (800, 600)))
        me.target = tuple(data["target"]) if data.get("target") else None
        me._stop_dist = data.get("_stop_dist", 0.0)
        me._follow_dist = data.get("_follow_dist", 0.0)
        me._follow_entity = None
        me.attack_target = None
        me.rotation = data["rotation"]
        me.rotation_speed = data["rotation_speed"]
        # Restore abilities from save data, or keep defaults for old replays
        if "abilities" in data:
            me.abilities = [ability_from_dict(a) for a in data["abilities"]]
        # cross-reference resolved later by Game.load_state()
        me.metal_spot = None
        return me
