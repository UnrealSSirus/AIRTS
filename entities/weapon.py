from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Weapon:
    name: str
    damage: float           # negative = healing
    range: float
    cooldown: float
    laser_color: tuple      # RGB
    laser_width: int = 1
    hits_only_friendly: bool = False
