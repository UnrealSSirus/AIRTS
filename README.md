# AIRTS

## Project Description

A simple, modular RTS game built with Pygame.
Designed to be easy to extend with new units, AI, and game systems.
Used as a learning project for Pygame and game development, as well as for the 2026 BlueOrange "AI Jam" event.

---

## Setup

```bash
pip install -r requirements.txt
python main.py
```

Requires **Python 3.8+** and **Pygame 2.x**.

## Game Modes

Configure via the `team_ai` parameter in `main.py`:

| Config | Mode |
|---|---|
| `team_ai={2: WanderAI()}` | Human (Team 1) vs AI (Team 2) |
| `team_ai={1: MyAI()}` | AI (Team 1) vs Human (Team 2) |
| `team_ai={1: MyAI(), 2: WanderAI()}` | AI vs AI (spectator) |

Human-vs-Human is not supported; at least one team must be AI-controlled.

## Project Structure

```
AIRTS/
├── main.py                  # Entry point
├── game.py                  # Game loop, event handling, rendering
├── gui.py                   # Command-center spawn panel
├── config/
│   ├── settings.py          # Colors, physics, combat, GUI constants
│   └── unit_types.py        # Data-driven unit type registry
├── core/
│   └── helpers.py           # Geometry helpers (LOS, hexagon points)
├── entities/
│   ├── base.py              # Entity base class + Damageable mixin
│   ├── shapes.py            # Rect, Circle, Polygon, Sprite entities
│   ├── unit.py              # Unit class with commands and fire modes
│   ├── command_center.py    # HQ: spawning, healing aura, rally points
│   ├── metal_spot.py        # Capturable resource node
│   ├── metal_extractor.py   # Built on captured metal spots
│   └── laser.py             # Laser visual effect
└── systems/
    ├── ai/                  # AI controllers (one file per AI)
    │   ├── base.py          # BaseAI interface
    │   └── wander.py        # Example: random wandering AI
    ├── combat.py            # Laser attacks, medic healing, CC aura
    ├── physics.py           # Collision resolution, bounds clamping
    ├── spawning.py          # Unit spawning from command centers
    ├── capturing.py         # Metal spot capture logic
    ├── selection.py         # Click and drag selection
    └── map_generator.py     # Map generation (obstacles, CCs, metal spots)
```

---

## Extending the Game

### Creating a New AI

1. Create a file in `systems/ai/`, e.g. `systems/ai/rush.py`.
2. Subclass `BaseAI` and implement `on_start` and `on_step`:

```python
from systems.ai.base import BaseAI

class RushAI(BaseAI):
    def on_start(self) -> None:
        self.set_build("soldier")

    def on_step(self, iteration: int) -> None:
        enemies = self.get_enemy_units()
        if not enemies:
            return
        # pick closest enemy to our CC
        cc = self.get_cc()
        if cc is None:
            return
        nearest = min(enemies, key=lambda e: (e.x - cc.x)**2 + (e.y - cc.y)**2)
        for unit in self.get_own_units():
            unit.attack(nearest)
            unit.move(nearest.x, nearest.y, stop_dist=unit.attack_range * 0.8)
```

3. Use it in `main.py`:

```python
from systems.ai.rush import RushAI
game = Game(team_ai={2: RushAI()})
```

#### Available AI Helpers

| Method | Returns | Description |
|---|---|---|
| `get_entities()` | `set[Entity]` | All entities in the world |
| `get_units()` | `set[Unit]` | All alive units (any team) |
| `get_own_units()` | `set[Unit]` | Your team's alive units |
| `get_enemy_units()` | `set[Unit]` | Enemy alive units |
| `get_obstacles()` | `set[Entity]` | Obstacle entities |
| `get_metal_spots()` | `set[MetalSpot]` | All metal spot nodes |
| `get_metal_extractors()` | `set[MetalExtractor]` | All alive extractors |
| `get_own_metal_extractors()` | `set[MetalExtractor]` | Your team's extractors |
| `get_cc()` | `CommandCenter \| None` | Your team's command center |
| `bounds` | `(int, int)` | Map width and height |
| `set_build(type)` | — | Set what unit type the CC will spawn |

#### Unit Commands

| Method | Description |
|---|---|
| `unit.move(x, y, stop_dist=0)` | Move to position; stop when center is within `stop_dist` |
| `unit.follow(target, distance)` | Continuously follow an entity, maintaining `distance` |
| `unit.attack(target)` | Set a priority attack target |
| `unit.stop()` | Cancel movement and follow |

#### Fire Modes (`unit.fire_mode`)

| Mode | Behavior |
|---|---|
| `HOLD_FIRE` | Never shoots |
| `TARGET_FIRE` | Only shoots the assigned `attack_target` |
| `FREE_FIRE` | Shoots `attack_target` if in range, else closest enemy (default) |

Import them from `entities.unit`:

```python
from entities.unit import HOLD_FIRE, TARGET_FIRE, FREE_FIRE
```

---

### Adding a New Unit Type

Add an entry to `UNIT_TYPES` in `config/unit_types.py`:

```python
UNIT_TYPES["engineer"] = {
    "hp": 80, "speed": 60, "radius": 10,
    "damage": 5, "range": 50, "cooldown": 1.5,
    "symbol": MY_SYMBOL_TUPLE,  # or None for a plain circle
    "can_attack": True,
    # optional keys for special behavior:
    # "heal_rate": 0, "heal_range": 0, "heal_targets": 0,
}
```

The spawning system, combat, GUI, and AI `set_build` all read from this dict automatically. If the unit type needs custom behavior beyond stat differences, you can check `unit.unit_type` in the relevant system.

Symbol tuples are `(x, y)` offsets assuming a 16px reference radius, drawn as a filled polygon over the unit circle.

---

### Adding a New Game System

1. Create a module in `systems/`, e.g. `systems/fog_of_war.py`.
2. Write a step function that takes the data it needs:

```python
def fog_step(units, bounds, dt):
    ...
```

3. Wire it into `Game.step()` in `game.py`:

```python
from systems.fog_of_war import fog_step

def step(self, dt):
    ...
    fog_step(units, (self.width, self.height), dt)
    ...
```

---

### Creating a New Map Generator

Subclass `BaseMapGenerator` in `systems/map_generator.py` (or a new file):

```python
from systems.map_generator import BaseMapGenerator

class ArenaMapGenerator(BaseMapGenerator):
    def generate(self, width, height):
        entities = []
        # place obstacles, command centers, metal spots, etc.
        return entities
```

Pass it when creating the game:

```python
game = Game(map_generator=ArenaMapGenerator())
```
