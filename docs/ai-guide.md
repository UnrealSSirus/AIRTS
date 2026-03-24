# AI Development Guide

This is the primary reference for writing custom AI controllers for AIRTS. By the end of this guide you'll have a working AI that can be dropped into a game.

## Quick Start

Create a file (e.g., `my_ai.py`) in the `ais/` folder at the project root:

```python
from systems.ai.base import BaseAI


class MyAI(BaseAI):
    ai_id = "my_ai"        # unique slug — used internally
    ai_name = "My Custom AI"  # shown in the lobby dropdown

    def on_start(self) -> None:
        """Called once before the first frame."""
        self.set_build("soldier")

    def on_step(self, iteration: int) -> None:
        """Called every frame (60 FPS)."""
        for unit in self.get_own_units():
            if unit.target is None and unit.attack_target is None:
                cc = self.get_cc()
                if cc:
                    # Send idle units toward the enemy side
                    bw, _ = self.bounds
                    enemy_x = bw - cc.x
                    self.move_unit(unit, enemy_x, cc.y)
```

That's it! The game auto-discovers AI files in `ais/` at startup. Your AI will appear in the Create Lobby screen's dropdown menu.

### Requirements

Every AI class **must** have:
- **`ai_id`** — a unique string slug (e.g. `"my_ai"`). Used to identify the AI internally.
- **`ai_name`** — a human-readable name (e.g. `"My Custom AI"`). Shown in the lobby UI.
- Both `on_start()` and `on_step()` methods implemented.

### AI Folder Structure

```
ais/                    ← Drop your AI files here (auto-discovered)
  example_ai.py         ← Ships with the game as a reference
  my_ai.py              ← Your custom AI

systems/ai/             ← Built-in AIs (also auto-discovered)
  wander.py             ← Default opponent AI
```

### Running Without the Menu

You can run AIs headlessly from the command line:

```bash
python main.py --headless --team1 my_ai --team2 wander --time-limit 15
```

Or from a script:

```python
from game import Game
from systems.map_generator import DefaultMapGenerator
from ais.my_ai import MyAI
from systems.ai import WanderAI

def main():
    game = Game(
        width=800,
        height=600,
        map_generator=DefaultMapGenerator(),
        team_ai={1: MyAI(), 2: WanderAI()},  # AI vs AI
    )
    game.run()

if __name__ == "__main__":
    main()
```

## AI Lifecycle

1. **`__init__()`** — The game constructs your AI before the world exists. Don't query game state here.
2. **`_bind(player_id, team_id, game, stats, command_queue)`** — Called internally by the Game. Gives your AI its player ID, team ID, a reference to the game, stats tracker, and the shared command queue. You never call this yourself.
3. **`on_start()`** — Called once after the map is generated and all entities are placed, but before the first `step()`. Use this for initial setup (e.g., choosing a starting spawn type).
4. **`on_step(iteration)`** — Called every frame (60 FPS) with a 0-based iteration counter. This is where all your logic goes.

## World Query API

All query methods are inherited from `BaseAI`. They return live objects sorted by entity ID — you can read their properties to make decisions.

**Important:** To issue commands (move, attack, set build), always use the `BaseAI` helper methods (`self.move_unit()`, `self.attack_unit()`, `self.set_build()`). These route through the command system for multiplayer compatibility. Do not call `unit.move()` or set `unit.attack_target` directly.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `self.bounds` | `tuple[int, int]` | Map dimensions `(width, height)` |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_entities()` | `list[Entity]` | All entities (units, CCs, obstacles, metal spots, extractors) |
| `get_units()` | `list[Unit]` | All living units on both teams |
| `get_own_units()` | `list[Unit]` | All living units belonging to your player |
| `get_ally_units()` | `list[Unit]` | Living units on the same team but controlled by a different player (co-op multiplayer) |
| `get_enemy_units()` | `list[Unit]` | All living enemy units |
| `get_mobile_units()` | `list[Unit]` | All living non-building units (both teams) |
| `get_own_mobile_units()` | `list[Unit]` | Your living non-building units |
| `get_obstacles()` | `list[Entity]` | All obstacle entities |
| `get_metal_spots()` | `list[MetalSpot]` | All metal spots (claimed and unclaimed) |
| `get_metal_extractors()` | `list[MetalExtractor]` | All living metal extractors (both teams) |
| `get_own_metal_extractors()` | `list[MetalExtractor]` | Your team's living metal extractors |
| `get_cc()` | `CommandCenter \| None` | Your Command Center (or `None` if destroyed) |
| `move_unit(unit, x, y)` | `None` | Move a unit to `(x, y)` |
| `attack_unit(unit, target)` | `None` | Assign a specific attack target to a unit |
| `stop(unit_ids)` | `None` | Clear movement for a list of unit IDs |
| `set_rally(cc_id, pos)` | `None` | Set the CC's rally point to `pos` |
| `set_build(unit_type)` | `None` | Change your CC's spawn type. Raises `ValueError` for unknown types. |

Valid `unit_type` strings for `set_build()`:
`"soldier"`, `"medic"`, `"tank"`, `"sniper"`, `"machine_gunner"`, `"scout"`, `"shockwave"`, `"artillery"`

## Unit Commands

Use the `BaseAI` helper methods to issue commands. These route through the serializable command system so they work correctly in multiplayer.

### `self.move_unit(unit, x, y)`

Move a unit toward `(x, y)`. Clears any active `follow` command on that unit.

```python
self.move_unit(unit, 400, 300)  # Move to the center
```

### `self.attack_unit(unit, target)`

Assign a specific attack target. The unit will prefer this target when firing (behavior depends on fire mode). Does not cancel movement — the unit can move and attack simultaneously.

```python
enemy = min(enemies, key=lambda e: math.hypot(e.x - unit.x, e.y - unit.y))
self.attack_unit(unit, enemy)
```

### `self.set_build(unit_type)`

Change which unit type your CC will spawn next. Raises `ValueError` for unknown types.

```python
self.set_build("sniper")
```

### Direct Unit Methods (read the note below)

Units also have direct methods you can call for operations not covered by the helpers above:

| Method | Description |
|---|---|
| `unit.follow(target, distance)` | Follow an entity, maintaining `distance` px of separation |
| `unit.stop()` | Clear move and follow commands |

> **Note:** `unit.move()`, `unit.attack()`, and setting `cc.spawn_type` directly will still work, but bypass the command system. For multiplayer compatibility, prefer `self.move_unit()`, `self.attack_unit()`, and `self.set_build()`.

## Fire Modes

Fire modes control when and how a unit chooses targets. Import and set them like this:

```python
from entities.unit import HOLD_FIRE, TARGET_FIRE, FREE_FIRE

unit.fire_mode = FREE_FIRE     # Default — shoot closest enemy, prefer attack_target
unit.fire_mode = TARGET_FIRE   # Only fire at the assigned attack_target
unit.fire_mode = HOLD_FIRE     # Never fire
```

| Mode | Behavior |
|------|----------|
| `FREE_FIRE` | Prefer the assigned `attack_target` if in range and LOS; otherwise shoot the closest enemy. **Default for all units.** |
| `TARGET_FIRE` | Only shoot the assigned `attack_target`. If no target is assigned, or it's out of range / no LOS, do nothing. |
| `HOLD_FIRE` | Never fire. Useful for scouts or retreating units. |

## Unit Stats Reference

### Tier 1

| Type              | HP  | Speed | Radius | Damage | Range | Cooldown | Special                                        |
|-------------------|-----|-------|--------|--------|-------|----------|------------------------------------------------|
| `soldier`         | 100 | 40    | 5      | 10     | 50    | 1.5 s    | —                                              |
| `medic`           | 50  | 40    | 5      | —      | 50    | 0.3 s    | Heal laser (friendly-only); heals ~3 HP/s      |
| `tank`            | 250 | 20    | 7      | 7      | 50    | 2.0 s    | ReactiveArmor passive                          |
| `sniper`          | 50  | 30    | 5      | 35     | 140   | 6.0 s    | Long range; Focus passive (slows after shot)   |
| `machine_gunner`  | 70  | 40    | 5      | 1      | 50    | 0.1 s    | 10 shots/sec, low per-shot damage              |
| `scout`           | 15  | 90    | 4      | 4      | 15    | 0.5 s    | Spawns 3 per cycle; short range                |
| `shockwave`       | 70  | 30    | 5      | 7      | 60    | 3.0 s    | Chain laser bounces to enemies within 70 px    |
| `artillery`       | 50  | 20    | 10     | 100    | 160   | 6.0 s    | Splash 40 px; friendly fire; 2 s charge time  |

### Tier 2

| Type                  | HP  | Speed | Damage | Range | Cooldown | Key changes                                  |
|-----------------------|-----|-------|--------|-------|----------|----------------------------------------------|
| `soldier_t2`          | 125 | 42    | 15     | 55    | 1.4 s    | Better stats across the board                |
| `medic_t2`            | 75  | 60    | —      | 70    | 0.2 s    | Faster, longer reach                         |
| `tank_t2`             | 400 | 20    | 7      | 50    | 2.0 s    | More HP; ElectricArmor passive               |
| `sniper_t2`           | 65  | 35    | 45     | 150   | 5.0 s    | More HP and damage, faster shots             |
| `machine_gunner_t2`   | 80  | 30    | 3      | 75    | 0.1 s    | More HP, extended range, higher damage       |
| `scout_t2`            | 12  | 110   | 5      | 30    | 0.3 s    | Spawns 6 per cycle                           |
| `shockwave_t2`        | 50  | 30    | 15     | 90    | 3.0 s    | More damage; chain range 50 px               |
| `artillery_t2`        | 120 | 15    | 100    | 180   | 6.0 s    | More HP; splash 75 px; charge 3 s            |

T2 units require a **Research Lab** extractor upgrade on your team's side. Use `set_build("soldier_t2")` etc. once T2 is available.

## Key Entity Properties

### Unit

| Property | Type | Description |
|----------|------|-------------|
| `x`, `y` | `float` | Position |
| `hp` | `float` | Current health |
| `max_hp` | `float` | Maximum health |
| `alive` | `bool` | `False` when HP reaches 0 |
| `team` | `int` | Team number (1 or 2) |
| `player_id` | `int` | Player controlling this unit |
| `unit_type` | `str` | `"soldier"`, `"tank"`, etc. |
| `speed` | `float` | Movement speed in px/s |
| `radius` | `float` | Collision radius |
| `is_building` | `bool` | `True` for non-mobile units (extractors, CCs) |
| `is_t2` | `bool` | `True` for Tier 2 unit variants |
| `target` | `tuple[float,float] \| None` | Current move destination |
| `attack_target` | `Entity \| None` | Assigned attack target |
| `fire_mode` | `str` | One of the fire mode constants |

### CommandCenter

| Property | Type | Description |
|----------|------|-------------|
| `x`, `y` | `float` | Position |
| `hp` | `float` | Current health (max 1000) |
| `alive` | `bool` | `False` when destroyed |
| `team` | `int` | `1` or `2` |
| `player_id` | `int` | Player controlling this CC |
| `spawn_type` | `str` | Unit type to spawn next |
| `rally_point` | `tuple[float,float] \| None` | Where spawned units auto-move |
| `metal_extractors` | `list[MetalExtractor]` | Extractors boosting this CC |

### MetalSpot

| Property | Type | Description |
|----------|------|-------------|
| `x`, `y` | `float` | Position |
| `owner` | `int \| None` | Team that owns it, or `None` if unclaimed |
| `capture_progress` | `float` | -1.0 (Team 2) to +1.0 (Team 1) |

### MetalExtractor

| Property | Type | Description |
|----------|------|-------------|
| `x`, `y` | `float` | Position (same as its metal spot) |
| `hp` | `float` | Current health (max 150) |
| `alive` | `bool` | `False` when destroyed |
| `team` | `int` | `1` or `2` |
| `metal_spot` | `MetalSpot` | The underlying metal spot |

## Game Rules Summary

- **Objective:** Destroy the enemy Command Center.
- **Spawn rate:** One unit every 10 seconds (base), boosted by +8% per owned metal extractor.
- **CC healing aura:** 5 HP/s to friendly units within 40 px.
- **CC defensive laser:** 20 damage, 75 px range, 1 s cooldown.
- **Metal spot capture:** Net unit presence within 15 px radius shifts progress at 0.05/s per unit. At ±1.0, an extractor is built.
- **Metal extractor:** 150 HP, destroyed = spot released.
- **LOS:** Obstacles block laser fire (both unit and CC lasers).
- **Map:** 800x600, CCs at x=80 and x=720, 2–4 mirrored metal spot pairs, 4–8 random obstacles.

## Strategy Tips

- **Economy matters.** Each metal extractor gives an 8% additive spawn speed boost. Capturing spots early generates more units over time.
- **Composition.** Soldiers are fine early, but mixing scouts for numbers, shockwaves for chain damage, and artillery for area denial can be decisive.
- **Use terrain.** Obstacles block LOS. Position snipers behind cover so melee-range enemies can't shoot back.
- **Focus fire.** Using `self.attack_unit(unit, target)` to concentrate damage on a single enemy kills it faster than letting units shoot random targets.
- **Protect your CC.** If the enemy pushes into your base, your CC's healing aura and defensive laser help — but 1000 HP goes fast under sustained fire.
- **Target fire for snipers.** Set snipers to `TARGET_FIRE` and manually assign high-value targets (enemy medics, damaged units) to maximize their impact.
- **Artillery friendly fire.** Artillery splash damages your own units. Keep friendlies out of the blast radius or use `HOLD_FIRE` on artillery when allies are nearby.

## Complete Example: Rush AI

This AI captures nearby metal spots, then rushes all units at the enemy CC:

```python
import math
from systems.ai.base import BaseAI


class RushAI(BaseAI):
    ai_id = "rush"
    ai_name = "Rush AI"

    def on_start(self) -> None:
        self.set_build("machine_gunner")
        self._phase = "expand"

    def on_step(self, iteration: int) -> None:
        cc = self.get_cc()
        if cc is None:
            return

        own_units = self.get_own_units()
        enemies = self.get_enemy_units()
        spots = self.get_metal_spots()

        # Find unclaimed metal spots
        unclaimed = [s for s in spots if s.owner is None]

        if self._phase == "expand" and len(own_units) >= 5:
            self._phase = "rush"

        if self._phase == "expand":
            # Send units to capture the nearest unclaimed metal spot
            for unit in own_units:
                if unit.target is not None:
                    continue
                if unclaimed:
                    nearest_spot = min(unclaimed,
                        key=lambda s: math.hypot(s.x - unit.x, s.y - unit.y))
                    self.move_unit(unit, nearest_spot.x, nearest_spot.y)
        else:
            # Rush the enemy CC area
            bw, bh = self.bounds
            enemy_cc_x = bw - cc.x
            enemy_cc_y = cc.y

            for unit in own_units:
                # Move toward enemy CC
                if unit.target is None:
                    self.move_unit(unit, enemy_cc_x, enemy_cc_y)

                # Focus fire on the closest enemy
                if enemies:
                    closest = min(enemies,
                        key=lambda e: math.hypot(e.x - unit.x, e.y - unit.y))
                    self.attack_unit(unit, closest)

        # Switch to soldiers once we have extractors
        if len(self.get_own_metal_extractors()) >= 2:
            self.set_build("soldier")
```

## Testing & Debugging

- **AI vs AI mode** is the fastest way to iterate. Run `python main.py --headless --team1 my_ai --team2 wander --time-limit 5` for a quick test.
- **Throttle expensive logic.** `on_step()` runs at 60 FPS. If you have O(n^2) distance calculations, run them every N frames:
  ```python
  def on_step(self, iteration):
      if iteration % 10 == 0:  # every ~0.16 seconds
          self._recalculate_targets()
      self._execute_commands()
  ```
- **Check `alive` before using entities.** Units and CCs can die between frames. Always verify `entity.alive` or check for `None` returns from `get_cc()`.
- **Print debugging.** Add `print()` statements in `on_step()` — output goes to the terminal that launched the game.
- **Use `iteration` for timing.** At 60 FPS, `iteration // 60` gives approximate seconds elapsed.
