from __future__ import annotations
import pygame
from config.settings import LASER_FLASH_DURATION

_SPLASH_COLOR = (255, 60, 60)


class SplashEffect:
    """Expanding red circle shown at the artillery impact point."""

    __slots__ = ("x", "y", "max_radius", "ttl", "_init_ttl")

    def __init__(self, x: float, y: float, radius: float, duration: float = 0.6):
        self.x = x
        self.y = y
        self.max_radius = radius
        self._init_ttl = duration
        self.ttl = duration

    def update(self, dt: float) -> bool:
        self.ttl -= dt
        return self.ttl > 0

    def draw(self, surface: pygame.Surface) -> None:
        frac = self.ttl / self._init_ttl        # 1.0 → 0.0
        r = int(self.max_radius * (1.0 - frac))  # 0 → max_radius (expanding)
        alpha = int(200 * frac)                  # 200 → 0 (fading)
        if r <= 0 or alpha <= 0:
            return
        size = r * 2 + 2
        temp = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(temp, (*_SPLASH_COLOR, alpha), (r + 1, r + 1), r)
        surface.blit(temp, (int(self.x) - r - 1, int(self.y) - r - 1))


class LaserFlash:
    __slots__ = ("x1", "y1", "x2", "y2", "color", "ttl", "_init_ttl", "width",
                 "source", "target")

    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 color: tuple, width: int = 1,
                 source=None, target=None, duration: float = 0.0):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color
        self._init_ttl = duration if duration > 0.0 else LASER_FLASH_DURATION
        self.ttl = self._init_ttl
        self.width = width
        self.source = source
        self.target = target

    def update(self, dt: float) -> bool:
        self.ttl -= dt
        # Track living entities so the beam follows movement
        if self.source is not None:
            if self.source.alive:
                self.x1 = self.source.x
                self.y1 = self.source.y
            else:
                self.source = None
        if self.target is not None:
            if self.target.alive:
                self.x2 = self.target.x
                self.y2 = self.target.y
            else:
                self.target = None
        return self.ttl > 0

    def draw(self, surface: pygame.Surface):
        alpha = max(0, min(255, int(255 * (self.ttl / self._init_ttl))))
        c = (*self.color[:3], alpha)
        temp = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.line(temp, c, (self.x1, self.y1), (self.x2, self.y2), self.width)
        surface.blit(temp, (0, 0))

    def to_dict(self) -> dict:
        d = {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "color": list(self.color),
            "ttl": self.ttl,
            "init_ttl": self._init_ttl,
            "width": self.width,
        }
        if self.source is not None:
            d["source_id"] = self.source.entity_id
        if self.target is not None:
            d["target_id"] = self.target.entity_id
        return d

    @classmethod
    def from_dict(cls, data: dict) -> LaserFlash:
        lf = cls(data["x1"], data["y1"], data["x2"], data["y2"],
                 tuple(data["color"]), data["width"],
                 duration=data.get("init_ttl", 0.0))
        lf.ttl = data["ttl"]
        # source/target resolved later by Game.load_state()
        lf.source = None
        lf.target = None
        return lf
