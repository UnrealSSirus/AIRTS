"""Passive ability system — lightweight, extensible framework."""
from __future__ import annotations
from config.settings import (
    REINFORCE_BONUS_MULTIPLIER,
    REINFORCE_HP_BONUS,
    REINFORCE_STACK_INTERVAL,
    REINFORCE_MAX_STACKS,
)


class PassiveAbility:
    name: str = "passive"
    description: str = ""

    def __init__(self):
        self.active: bool = False

    def update(self, entity, dt: float) -> None:
        pass

    def on_activate(self, entity) -> None:
        pass

    def to_dict(self) -> dict:
        return {"type": self.name, "active": self.active}

    @classmethod
    def from_dict(cls, data: dict) -> PassiveAbility:
        obj = cls()
        obj.active = data.get("active", False)
        return obj


class Reinforce(PassiveAbility):
    name = "reinforce"
    description = "Builds plating over time. At full stacks, gains bonus HP and doubles spawn bonus."

    def __init__(self):
        super().__init__()
        self.stacks: int = 0
        self.max_stacks: int = REINFORCE_MAX_STACKS
        self.stack_interval: float = REINFORCE_STACK_INTERVAL
        self.stack_timer: float = 0.0

    def update(self, entity, dt: float) -> None:
        if self.active:
            return
        self.stack_timer += dt
        while self.stack_timer >= self.stack_interval and self.stacks < self.max_stacks:
            self.stack_timer -= self.stack_interval
            self.stacks += 1
        if self.stacks >= self.max_stacks and not self.active:
            self.on_activate(entity)

    def on_activate(self, entity) -> None:
        self.active = True
        entity.max_hp += REINFORCE_HP_BONUS
        entity.hp += REINFORCE_HP_BONUS

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "stacks": self.stacks,
            "stack_timer": self.stack_timer,
        })
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Reinforce:
        obj = cls()
        obj.active = data.get("active", False)
        obj.stacks = data.get("stacks", 0)
        obj.stack_timer = data.get("stack_timer", 0.0)
        return obj


ABILITY_REGISTRY: dict[str, type[PassiveAbility]] = {
    "reinforce": Reinforce,
}


def ability_from_dict(data: dict) -> PassiveAbility:
    """Reconstruct an ability from serialized data."""
    cls = ABILITY_REGISTRY.get(data.get("type", ""), PassiveAbility)
    return cls.from_dict(data)
