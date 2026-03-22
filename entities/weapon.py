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
    sound: str = "fast_laser"
    chain_range: float = 0.0    # 0 = no chaining
    chain_delay: float = 0.0    # seconds between bounces
    splash_radius: float = 0.0  # 0 = no splash
    splash_damage_max: float = 0.0  # damage at impact point
    splash_damage_min: float = 0.0  # damage at splash edge (linear falloff)
    laser_flash_duration: float = 0.0  # 0 = use global default
    charge_time: float = 0.0   # 0 = fire immediately; >0 = lock target pos and delay
