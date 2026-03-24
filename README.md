# AIRTS

A modular RTS game built with Pygame — designed as a platform for writing AI controllers that compete against humans or other AIs. Built for the 2026 BlueOrange "AI Jam" event.

## Setup

```bash
git clone <repo-url>
cd AIRTS

python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
pip install -r requirements.txt

python main.py
```

Requires **Python 3.10+**, **Pygame 2.6+**, and **NumPy 2.4+**.

### Optional: Cython acceleration

Building the Cython extension speeds up unit collision resolution significantly.
The game works without it (falls back to pure Python).

```bash
pip install cython

# Windows (requires MSVC / "Desktop development with C++" in Visual Studio)
python setup_cython.py build_ext --inplace

# Linux (requires gcc / build-essential)
python setup_cython.py build_ext --inplace

# macOS (requires Xcode CLI tools: xcode-select --install)
python setup_cython.py build_ext --inplace
```

## Running

```bash
# Interactive UI
python main.py

# Headless AI vs AI (no window, auto-exits)
python main.py --headless --team1 wander --team2 wander --time-limit 15

# List available AI ids
python main.py --list-ais

# Custom map size / obstacle count
python main.py --headless --team1 wander --team2 wander --width 1200 --height 800 --obs-min 6 --obs-max 12
```

## Game Modes

The Create Lobby screen lets you configure player slots and AI assignments. The game supports:

| Mode | Description |
|---|---|
| Human vs AI | You control one team; an AI controls the other |
| AI vs AI | Watch two AIs battle in spectator mode |
| Multiplayer | Host or join a networked game (LAN/local) |

## Project Structure

```
AIRTS/
├── main.py                     Entry point (argparse CLI)
├── app.py                      Screen routing and pygame lifecycle
├── game.py                     Game loop, event handling, rendering
├── gui.py                      CC spawn-type selection panel + HUD
├── config/
│   ├── settings.py             Tuning constants (HP, damage, colors, physics)
│   └── unit_types.py           Data-driven unit type registry (T1 + T2)
├── core/
│   ├── helpers.py              Geometry helpers (LOS, hexagon points)
│   ├── quadfield.py            Uniform-grid spatial index for proximity queries
│   ├── vectorized.py           NumPy-vectorized batch operations
│   ├── camera.py               Camera pan/zoom
│   └── fast_collisions.pyx     Cython collision pass (optional)
├── entities/
│   ├── base.py                 Entity base class + Damageable mixin
│   ├── shapes.py               Rect, Circle, Polygon, Sprite entities
│   ├── unit.py                 Unit class (commands, fire modes, movement, abilities)
│   ├── command_center.py       CommandCenter (spawning, healing, rally points)
│   ├── metal_spot.py           Capturable resource node
│   ├── metal_extractor.py      Built on captured metal spots (selectable)
│   ├── weapon.py               Weapon dataclass
│   └── laser.py                Laser visual effect
├── systems/
│   ├── ai/                     AI controllers
│   │   ├── base.py             BaseAI abstract class
│   │   ├── wander.py           Built-in WanderAI
│   │   └── registry.py         Auto-discovers AIs from ais/ and systems/ai/
│   ├── abilities.py            Passive ability system (ReactiveArmor, ElectricArmor, Focus, Reinforce)
│   ├── commands.py             Command serialization layer (multiplayer-ready)
│   ├── combat.py               Laser attacks, healing, chain/splash, CC aura
│   ├── physics.py              Collision resolution, bounds clamping
│   ├── spawning.py             Unit spawning from command centers (T2-aware)
│   ├── capturing.py            Metal spot capture logic
│   ├── selection.py            Click and drag selection
│   ├── map_generator.py        Map generation
│   ├── replay.py               Replay recording
│   ├── stats.py                Game statistics tracking
│   └── crash_handler.py        Crash log handler
├── networking/                 Host/client multiplayer support
├── screens/                    Menu screens (main menu, lobby, results, etc.)
├── ui/                         Reusable UI widgets and theming
└── ais/                        Drop your AI files here (auto-discovered)
    └── example_ai.py           Reference AI implementation
```

## Documentation

| Topic | Link |
|---|---|
| Write an AI controller | [docs/ai-guide.md](docs/ai-guide.md) |
| Understand the game rules | [docs/game-mechanics.md](docs/game-mechanics.md) |
| Understand the codebase internals | [docs/architecture.md](docs/architecture.md) |
| Add new units, maps, or systems | [docs/extending.md](docs/extending.md) |

## Quick Start: Writing an AI

Create a file in the `ais/` folder — it will be auto-discovered at startup:

```python
# ais/my_ai.py
from systems.ai.base import BaseAI

class MyAI(BaseAI):
    ai_id = "my_ai"
    ai_name = "My Custom AI"

    def on_start(self) -> None:
        self.set_build("soldier")

    def on_step(self, iteration: int) -> None:
        for unit in self.get_own_units():
            if unit.target is None:
                bw, _ = self.bounds
                cc = self.get_cc()
                if cc:
                    self.move_unit(unit, bw - cc.x, cc.y)
```

See [docs/ai-guide.md](docs/ai-guide.md) for the full API reference, unit stats, fire modes, and example strategies.
