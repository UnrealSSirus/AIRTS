from __future__ import annotations
from config.settings import HEALTH_BAR_OFFSET
from entities.unit import Unit
from entities.metal_spot import MetalSpot
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

    def update(self, dt: float):
        super().update(dt)
        self.rotation = (self.rotation + dt * self.rotation_speed) % math.tau

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

        self.draw_health_bar(surface, self.x, self.y, self.radius + HEALTH_BAR_OFFSET)

    # -- serialization --------------------------------------------------------

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "rotation": self.rotation,
            "rotation_speed": self.rotation_speed,
            "metal_spot_id": self.metal_spot.entity_id if self.metal_spot else None,
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
        # cross-reference resolved later by Game.load_state()
        me.metal_spot = None
        return me
