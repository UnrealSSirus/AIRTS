# Game Mechanics

## Objective

Destroy the enemy team's **Command Center** (CC). Each team starts with one CC; the game ends when a CC reaches 0 HP.

## Command Centers

<!-- AUTOGEN:cc-stats (regenerate with `python tools/gen_docs.py` — do not edit by hand) -->
| Property | Value |
|----------|-------|
| HP | 1000 |
| Spawn interval | 10 s (base) |
| Spawn radius | 50 px around the CC |
| Defensive laser range | 75 px |
| Defensive laser damage | 20 |
| Defensive laser cooldown | 1 s |
| Default spawn type | Soldier |
<!-- /AUTOGEN:cc-stats -->

Command Centers are hexagonal structures placed symmetrically on opposite sides of the map. They automatically:
- **Spawn units** of the selected type on a fixed interval (boosted by metal extractors).
- **Fire a defensive laser** at the closest enemy in range.
- **Send newly spawned units to a rally point**, if one is set.

CCs start with a full spawn timer so the first unit spawns immediately.

## Units

Every Tier 1 unit type has a Tier 2 variant unlocked by building a **Research Lab** from a captured metal extractor. All T2 variants are suffixed `_t2` (e.g. `"soldier_t2"`).

### Tier 1 Units

<!-- AUTOGEN:t1-units -->
| Type | HP | Speed | Radius | Damage | Range | Cooldown | Special |
|------|----|-------|--------|--------|-------|----------|---------|
| `soldier` | 100 | 40 | 5 | 10 | 50 | 1.5 s | Basic all-rounder |
| `medic` | 50 | 40 | 5 | — | 60 | 0.4 s | Support healer; **Heal Beam** |
| `tank` | 250 | 20 | 7 | 8 | 45 | 2 s | Frontline damage soak; **Reactive Armor** |
| `sniper` | 50 | 35 | 5 | 40 | 140 | 6 s | Long-range assassin; **Lock-On** |
| `machine_gunner` | 70 | 40 | 5 | 4 | 50 | 0.4 s | Sustained rapid fire |
| `scout` | 15 | 90 | 4 | 3 | 40 | 0.5 s | Fast, fragile swarmer; **Pack Hunter** |
| `shockwave` | 70 | 30 | 5 | 8 | 60 | 3.5 s | Chain-laser crowd damage; **Chain Lightning** |
| `artillery` | 50 | 20 | 7 | 50 | 160 | 6 s | Siege splash damage; **Charged Shot** |
| `engineer` | 50 | 40 | 5 | 3 | 70 | 1 s | Economy support; **Overclock** |
| `sweeper` | 30 | 30 | 3 | — | — | — | Vision support; **Detection** |
<!-- /AUTOGEN:t1-units -->

### Tier 2 Units

<!-- AUTOGEN:t2-units -->
| Type | HP | Speed | Damage | Range | Cooldown | Key changes vs T1 |
|------|----|-------|--------|-------|----------|-------------------|
| `soldier_t2` (Marine) | 125 | 40 | 12 | 60 | 1.5 s | +25 HP, +2 damage, +10 range, **Combat Stim** |
| `medic_t2` (Priest) | 75 | 60 | — | 60 | 0.5 s | +25 HP, +20 speed, +6 heal, +0.1s cooldown |
| `tank_t2` (Heavy Tank) | 400 | 20 | 10 | 50 | 2 s | +150 HP, +2 damage, +5 range, **Electric Armor** |
| `sniper_t2` (Marksman) | 75 | 40 | 55 | 150 | 5 s | +25 HP, +5 speed, +15 damage, +10 range, -1s cooldown |
| `machine_gunner_t2` (Plasma Beamer) | 80 | 40 | 6 | 60 | 0.4 s | +10 HP, +2 damage, +10 range |
| `scout_t2` (Drone Swarm) | 12 | 110 | 5 | 50 | 0.5 s | -3 HP, +20 speed, +2 damage, +10 range, spawns 5 per cycle (was 3), **Swarm** |
| `shockwave_t2` (Disruptor) | 50 | 30 | 15 | 80 | 3 s | -20 HP, +7 damage, +20 range, -0.5s cooldown, **Arc Lightning** |
| `artillery_t2` (Mortar) | 75 | 15 | 70 | 180 | 6 s | +25 HP, -5 speed, +20 damage, +20 range, +20 splash radius |
| `engineer_t2` (Mechanic) | 65 | 50 | 7 | 70 | 1 s | +15 HP, +10 speed, +4 damage |
| `sweeper_t2` (Sweeper T2) | 30 | 30 | — | — | — | — |
<!-- /AUTOGEN:t2-units -->

### Unit Traits & Details

<!-- AUTOGEN:unit-details -->
#### Soldier / Marine (T2)

- **Combat Stim** (T2): For every 10 missing HP: -0.1s weapon cooldown and +5% movement speed.

#### Medic / Priest (T2)

- **Heal Beam** (T1): Heals friendly units instead of dealing damage: 2 HP per pulse every 0.4s (~5.0 HP/s).
- **Heal Beam** (T2): Heals friendly units instead of dealing damage: 8 HP per pulse every 0.5s (~16.0 HP/s).

#### Tank / Heavy Tank (T2)

- **Reactive Armor** (T1): Every 5s gain a charge (max 2). Each charge reduces incoming damage by 50%. All charges are consumed when hit.
- **Electric Armor** (T2): Gains a stack every 3s (max 5). While any stacks are active: 60% damage reduction. Each stack: +0.25 HP/s regen, +15% speed. Loses one stack when hit.

#### Sniper / Marksman (T2)

- **Lock-On** (T1): Locks onto a target for 1.25s before firing. Once locked, the shot always fires — even if the target dies first. Cannot move while locking on.
- **Lock-On** (T2): Locks onto a target for 1.25s before firing. Once locked, the shot always fires — even if the target dies first. Cannot move while locking on.

#### Scout / Drone Swarm (T2)

- **Pack Hunter** (T1): Spawns in groups of 3.
- **Swarm** (T2): Spawns in groups of 5.

#### Shockwave / Disruptor (T2)

- **Chain Lightning** (T1): Laser chains to nearby enemies within 40px after a 0.1s delay.
- **Arc Lightning** (T2): Laser chains to nearby enemies within 40px after a 0.1s delay.

#### Artillery / Mortar (T2)

- **Charged Shot** (T1): Locks a ground position and fires after a 2.5s charge. Splash hits everything within 40px for 40-1 damage — including allies.
- **Charged Shot** (T2): Locks a ground position and fires after a 2.5s charge. Splash hits everything within 60px for 60-5 damage — including allies.

#### Engineer / Mechanic (T2)

- **Overclock** (T1): Allied metal extractors within 70px gain +1 HP/s regeneration and an extra +2% spawn boost.
- **Overclock** (T2): Allied metal extractors within 70px gain +2 HP/s regeneration and an extra +3% spawn boost.

#### Sweeper / Sweeper T2 (T2)

- **Detection** (T1): Nearby allied sweepers stack line of sight (+50 per sweeper, max +200). Allied units in range gain +5 attack range per sweeper (max +20).
- **Detection** (T2): Nearby allied sweepers stack line of sight (+50 per sweeper, max +200). Allied units in range gain +5 attack range per sweeper (max +20).
<!-- /AUTOGEN:unit-details -->

## Combat

### Laser Attacks

All combat is resolved through laser attacks. When a unit or CC fires:
1. The attacker checks for enemies within its attack range.
2. A **line-of-sight (LOS)** check ensures no obstacles block the shot.
3. If a valid target is found, the target takes damage immediately and a laser flash visual is spawned.
4. The attacker enters cooldown and cannot fire again until the cooldown elapses.

### Fire Modes

Units have three fire modes that control targeting behavior:

| Mode          | Constant       | Behavior                                                            |
|---------------|----------------|---------------------------------------------------------------------|
| **Free Fire** | `FREE_FIRE`    | Prefer the assigned `attack_target`; otherwise shoot the closest enemy in range. This is the default. |
| **Target Fire** | `TARGET_FIRE` | Only fire at the assigned `attack_target`. Do nothing if no target is assigned or it's out of range. |
| **Hold Fire** | `HOLD_FIRE`    | Never fire, regardless of nearby enemies.                           |

Fire mode constants are imported from `entities.unit`:
```python
from entities.unit import HOLD_FIRE, TARGET_FIRE, FREE_FIRE
```

### CC Defensive Laser

Command Centers always fire at the closest enemy within range (75 px). They do not use fire modes — they behave like permanent Free Fire.

## Passive Abilities

Certain unit types carry passive abilities that activate automatically.

<!-- AUTOGEN:passives -->
| Unit | Ability | Effect |
|------|---------|--------|
| Medic | **Heal Beam** | Heals friendly units instead of dealing damage: 2 HP per pulse every 0.4s (~5.0 HP/s). |
| Tank | **Reactive Armor** | Every 5s gain a charge (max 2). Each charge reduces incoming damage by 50%. All charges are consumed when hit. |
| Sniper | **Lock-On** | Locks onto a target for 1.25s before firing. Once locked, the shot always fires — even if the target dies first. Cannot move while locking on. |
| Scout | **Pack Hunter** | Spawns in groups of 3. |
| Shockwave | **Chain Lightning** | Laser chains to nearby enemies within 40px after a 0.1s delay. |
| Artillery | **Charged Shot** | Locks a ground position and fires after a 2.5s charge. Splash hits everything within 40px for 40-1 damage — including allies. |
| Engineer | **Overclock** | Allied metal extractors within 70px gain +1 HP/s regeneration and an extra +2% spawn boost. |
| Sweeper | **Detection** | Nearby allied sweepers stack line of sight (+50 per sweeper, max +200). Allied units in range gain +5 attack range per sweeper (max +20). |
| Command Center | **Unit Production** | Spawns a unit every 10s. Metal extractors boost spawn speed. |
| Command Center | **Defensive Laser** | Fires at the closest enemy within 75px for 20 damage every 1s. |
| Metal Extractor | **Spawn Boost** | Provides +8% spawn speed to its Command Center. |
| Metal Extractor | **Reinforce** | Builds plating every 15s (max 4). At full stacks gains +100 HP and 2x spawn bonus. |
| Marine (T2) | **Combat Stim** | For every 10 missing HP: -0.1s weapon cooldown and +5% movement speed. |
| Priest (T2) | **Heal Beam** | Heals friendly units instead of dealing damage: 8 HP per pulse every 0.5s (~16.0 HP/s). |
| Heavy Tank (T2) | **Electric Armor** | Gains a stack every 3s (max 5). While any stacks are active: 60% damage reduction. Each stack: +0.25 HP/s regen, +15% speed. Loses one stack when hit. |
| Marksman (T2) | **Lock-On** | Locks onto a target for 1.25s before firing. Once locked, the shot always fires — even if the target dies first. Cannot move while locking on. |
| Drone Swarm (T2) | **Swarm** | Spawns in groups of 5. |
| Disruptor (T2) | **Arc Lightning** | Laser chains to nearby enemies within 40px after a 0.1s delay. |
| Mortar (T2) | **Charged Shot** | Locks a ground position and fires after a 2.5s charge. Splash hits everything within 60px for 60-5 damage — including allies. |
| Mechanic (T2) | **Overclock** | Allied metal extractors within 70px gain +2 HP/s regeneration and an extra +3% spawn boost. |
| Sweeper T2 (T2) | **Detection** | Nearby allied sweepers stack line of sight (+50 per sweeper, max +200). Allied units in range gain +5 attack range per sweeper (max +20). |
| Command Center | **Unit Production** | Spawns a unit every 10s. Metal extractors boost spawn speed. |
| Command Center | **Defensive Laser** | Fires at the closest enemy within 75px for 20 damage every 1s. |
| Metal Extractor | **Spawn Boost** | Provides +8% spawn speed to its Command Center. |
| Metal Extractor | **Reinforce** | Builds plating every 15s (max 4). At full stacks gains +100 HP and 2x spawn bonus. |
<!-- /AUTOGEN:passives -->

## Metal Spots & Extractors

Metal spots are neutral resource nodes scattered symmetrically across the map. Capturing them boosts your CC's spawn rate.

### Capture Mechanics

1. Metal spots have a **capture radius** of **15 px**.
2. The capture progress is a float from **-1.0** (Team 2) to **+1.0** (Team 1).
3. Each frame, progress changes by `(team1_units - team2_units) * 0.05 * dt`, where the count only includes units within the capture radius.
4. When progress reaches +1.0 or -1.0, a **Metal Extractor** is built on the spot for that team.
5. Once claimed, a spot cannot be re-contested (the extractor must be destroyed first).

### Metal Extractor Stats

<!-- AUTOGEN:extractor-stats -->
| Property | Value |
|----------|-------|
| HP | 200 |
| Spawn boost | +8% additive per extractor |
<!-- /AUTOGEN:extractor-stats -->

Each extractor's spawn boost stacks additively per extractor owned by a CC. Metal extractors are **selectable** — clicking one shows its health bar and info.

### T2 Extractor Upgrades

A captured metal extractor can be upgraded (when T2 is enabled) into one of two structures:

<!-- AUTOGEN:upgrades -->
| Structure | Upgrade time | Effect |
|-----------|--------------|--------|
| **Outpost** | 30 s | Fires a defensive laser (75 px range, 15 dmg, 2 s CD); heals self at 1 HP/s; +50 HP; extended line of sight (140 px); +20% spawn bonus |
| **Research Lab** | 60 s | Enables T2 unit spawns from the CC; +20% spawn bonus; +100 CC max HP |

During an upgrade the extractor provides no spawn bonus.
<!-- /AUTOGEN:upgrades -->

## Map Layout

The `DefaultMapGenerator` creates maps with:
- **Two Command Centers** placed symmetrically: Team 1 at `(80, height/2)`, Team 2 at `(width-80, height/2)`.
- **2–4 metal spot pairs** placed randomly in the left half of the map, then mirrored to the right half (point symmetry around the map center).
- **4–8 random obstacles** (mix of rectangles and circles) scattered across the map.

Default map size is **800 x 600** pixels.

## Player Controls (Human Teams)

### Selection
- **Left-click** a unit, CC, or metal extractor to select it (deselects others).
- **Left-click + drag** to draw a circle selection. All units inside are selected. If only a CC is enclosed, it is selected instead.
- **Shift + click/drag** adds to the current selection without deselecting.

### Movement & Commands
- **Right-click** to move selected units to that point.
- **Right-click + drag** to draw a path. Selected units are distributed evenly along the path.
- When a CC is selected, right-click sets a **rally point** — newly spawned units will automatically move there.

### Spawn Type Selection
- When a CC is selected, a GUI panel appears at the bottom of the screen with buttons for each unit type.
- Click a button to change which unit type the CC will spawn next.

### Camera
- **Edge pan** — move the mouse to the screen edge to pan the camera.
- **Scroll wheel** — zoom in/out.

### Other
- **Escape** quits the game.
