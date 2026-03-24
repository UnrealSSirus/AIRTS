# AIRTS Documentation

AIRTS is a real-time strategy game built with Pygame for the BlueOrange AI Jam. Two teams battle for control of the map — each with a Command Center that spawns units, metal spots to capture for economic advantage, and five distinct unit types. The game is designed as a platform for writing AI controllers that compete against humans or other AIs.

All player actions (human and AI) flow through a serializable command system, making the game multiplayer-ready.

## Reading Guide

| You want to…                        | Read                                      |
|--------------------------------------|-------------------------------------------|
| Write an AI controller               | [ai-guide.md](ai-guide.md)               |
| Understand the game rules            | [game-mechanics.md](game-mechanics.md)    |
| Understand the codebase internals    | [architecture.md](architecture.md)        |
| Add new units, maps, or systems      | [extending.md](extending.md)             |

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd AIRTS

# Create a virtual environment and install dependencies
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
pip install -r requirements.txt

# Run the game
python main.py
```

### Requirements

- Python 3.10+
- `pygame >= 2.6.0`
- `numpy >= 2.4.2`

### Optional: Cython acceleration

Building the Cython extension speeds up unit collision resolution significantly.
The game works without it (falls back to pure Python).

```bash
pip install cython
python setup_cython.py build_ext --inplace
```

Requires a C compiler: MSVC on Windows ("Desktop development with C++" workload),
`gcc`/`build-essential` on Linux, or Xcode CLI tools on macOS.

## Game Modes

The Create Lobby screen lets you configure player slots and AI assignments:

| Mode | Description |
|---|---|
| Human vs AI | You control one team; an AI controls the other |
| AI vs AI | Watch two AIs battle in spectator mode |
| Multiplayer | Host or join a networked game (LAN/local) |

### Headless (command line)

```bash
python main.py --headless --team1 wander --team2 wander --time-limit 15
python main.py --list-ais   # list available AI ids
```
