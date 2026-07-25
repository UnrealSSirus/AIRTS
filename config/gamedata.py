"""Single source of truth for player-facing game text derived from live constants.

Every stat number shown to a player — ability tooltips, the Unit Overview
screen, the Guides screen, the web client's Learn to Play page, and the
generated tables in docs/ — is built HERE from ``config/settings.py`` and
``config/unit_types.py``. Tweak numbers in those two files only; never
hand-write a stat number in UI text or docs.

Consumers:
  - ``systems/abilities.py``        ability class ``description`` (HUD tooltips)
  - ``screens/unit_overview.py``    passive cards (``UNIT_PASSIVES``)
  - ``screens/guides.py``           guide topics (``GUIDE_TOPICS``)
  - ``networking/static_config.py`` browser handshake (via ability registry)
  - ``tools/gen_docs.py``           regenerates docs tables and the web
                                    client's build-time ``gamedata.json``
                                    (run after balancing changes)
"""
from __future__ import annotations

from config import settings as s
from config.unit_types import UNIT_TYPES, T2_NAMES, get_spawnable_types


# -- formatting helpers -------------------------------------------------------

def _n(x) -> str:
    """Format a number without a trailing .0 (2.0 -> '2', 1.25 -> '1.25')."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def _pct(x) -> str:
    """Format a fraction as a percentage string (0.08 -> '8')."""
    return _n(round(x * 100, 2))


def _weapon(ut: str) -> dict:
    return UNIT_TYPES[ut].get("weapon") or {}


# -- ability descriptions (registry name -> text) -----------------------------
# Used as the ``description`` attribute of the ability classes, which the
# browser HUD receives via the server handshake.

_LOCK_ON_TIME = _weapon("sniper").get("lock_on_time", 0.0)

ABILITY_DESCRIPTIONS: dict[str, str] = {
    "reinforce": (
        f"Builds plating every {_n(s.REINFORCE_STACK_INTERVAL)}s "
        f"(max {s.REINFORCE_MAX_STACKS}). At full stacks gains "
        f"+{s.REINFORCE_HP_BONUS} HP and "
        f"{_n(s.REINFORCE_BONUS_MULTIPLIER)}x spawn bonus."
    ),
    "reactive_armor": (
        f"Every {_n(s.REACTIVE_ARMOR_INTERVAL)}s gain a charge "
        f"(max {s.REACTIVE_ARMOR_MAX_STACKS}). Each charge reduces incoming "
        f"damage by {_pct(s.REACTIVE_ARMOR_REDUCTION)}%. "
        "All charges are consumed when hit."
    ),
    "lock_on": (
        f"Locks onto a target for {_n(_LOCK_ON_TIME)}s before firing. "
        "Once locked, the shot always fires — even if the target dies first. "
        "Cannot move while locking on."
    ),
    "electric_armor": (
        f"Gains a stack every {_n(s.ELECTRIC_ARMOR_INTERVAL)}s "
        f"(max {s.ELECTRIC_ARMOR_MAX_STACKS}). While any stacks are active: "
        f"{_pct(s.ELECTRIC_ARMOR_REDUCTION)}% damage reduction. Each stack: "
        f"+{_n(s.ELECTRIC_ARMOR_REGEN_PER_STACK)} HP/s regen, "
        f"+{_pct(s.ELECTRIC_ARMOR_SPEED_BONUS)}% speed. "
        "Loses one stack when hit."
    ),
    "combat_stim": (
        f"For every {_n(s.COMBAT_STIM_MISSING_HP_PER_STACK)} missing HP: "
        f"-{_n(s.COMBAT_STIM_COOLDOWN_REDUCTION)}s weapon cooldown and "
        f"+{_pct(s.COMBAT_STIM_SPEED_BONUS)}% movement speed."
    ),
    "overclock": (
        f"Allied metal extractors within {_n(s.OVERCLOCK_RANGE)}px gain "
        f"+{_n(s.OVERCLOCK_REGEN)} HP/s regeneration (T2: "
        f"+{_n(s.OVERCLOCK_REGEN_T2)}) and an extra "
        f"+{_pct(s.OVERCLOCK_BONUS)}% (T2: +{_pct(s.OVERCLOCK_BONUS_T2)}%) "
        "spawn boost."
    ),
    "detection": (
        f"Nearby allied sweepers stack line of sight "
        f"(+{_n(s.DETECTION_LOS_PER_STACK)} per sweeper, max "
        f"+{_n(s.DETECTION_LOS_MAX_BONUS)}). Allied units in range gain "
        f"+{_n(s.DETECTION_RANGE_PER_STACK)} attack range per sweeper "
        f"(max +{_n(s.DETECTION_RANGE_MAX_BONUS)})."
    ),
}

# Registry name -> player-facing name.
ABILITY_DISPLAY_NAMES: dict[str, str] = {
    "reinforce": "Reinforce",
    "reactive_armor": "Reactive Armor",
    "lock_on": "Lock-On",
    "electric_armor": "Electric Armor",
    "combat_stim": "Combat Stim",
    "overclock": "Overclock",
    "detection": "Detection",
}


# -- per-unit passive cards ---------------------------------------------------

def _card(name: str, desc: str) -> dict[str, str]:
    return {"name": name, "desc": desc}


def _registry_card(reg_name: str, desc: str | None = None) -> dict[str, str]:
    return _card(ABILITY_DISPLAY_NAMES[reg_name],
                 desc or ABILITY_DESCRIPTIONS[reg_name])


def build_unit_passives() -> dict[str, list[dict[str, str]]]:
    """unit_type -> list of {name, desc} passive/trait cards.

    Mirrors the ability assignment in ``Unit.__init__`` plus weapon-derived
    traits (heal beam, chaining, charge, spawn count) so every number a player
    sees comes from the live config values.
    """
    passives: dict[str, list[dict[str, str]]] = {}

    for ut in UNIT_TYPES:
        cards: list[dict[str, str]] = []
        w = _weapon(ut)

        # Weapon-derived: heal beam (medics)
        if w.get("hits_only_friendly"):
            heal = abs(w["damage"])
            cd = w["cooldown"]
            cards.append(_card(
                "Heal Beam",
                f"Heals friendly units instead of dealing damage: "
                f"{_n(heal)} HP per pulse every {_n(cd)}s "
                f"(~{heal / cd:.1f} HP/s)."))

        # Class abilities (must match Unit.__init__ assignment)
        if ut == "tank":
            cards.append(_registry_card("reactive_armor"))
        elif ut == "tank_t2":
            cards.append(_registry_card("electric_armor"))
        elif ut in ("sniper", "sniper_t2"):
            lock = w.get("lock_on_time", 0.0)
            cards.append(_registry_card("lock_on", (
                f"Locks onto a target for {_n(lock)}s before firing. "
                "Once locked, the shot always fires — even if the target "
                "dies first. Cannot move while locking on.")))
        elif ut == "soldier_t2":
            cards.append(_registry_card("combat_stim"))
        elif ut == "engineer":
            cards.append(_registry_card("overclock", (
                f"Allied metal extractors within {_n(s.OVERCLOCK_RANGE)}px "
                f"gain +{_n(s.OVERCLOCK_REGEN)} HP/s regeneration and an "
                f"extra +{_pct(s.OVERCLOCK_BONUS)}% spawn boost.")))
        elif ut == "engineer_t2":
            cards.append(_registry_card("overclock", (
                f"Allied metal extractors within {_n(s.OVERCLOCK_RANGE)}px "
                f"gain +{_n(s.OVERCLOCK_REGEN_T2)} HP/s regeneration and an "
                f"extra +{_pct(s.OVERCLOCK_BONUS_T2)}% spawn boost.")))
        elif ut in ("sweeper", "sweeper_t2"):
            cards.append(_registry_card("detection"))

        # Weapon-derived: chain laser (shockwaves)
        if w.get("chain_range", 0) > 0:
            cards.append(_card(
                "Arc Lightning" if UNIT_TYPES[ut].get("is_t2") else "Chain Lightning",
                f"Laser chains to nearby enemies within "
                f"{_n(w['chain_range'])}px after a {_n(w['chain_delay'])}s "
                f"delay."))

        # Weapon-derived: charged shot (artillery)
        if w.get("charge_time", 0) > 0:
            splash = w.get("splash_radius", 0)
            desc = (f"Locks a ground position and fires after a "
                    f"{_n(w['charge_time'])}s charge.")
            if splash > 0:
                desc += (f" Splash hits everything within {_n(splash)}px for "
                         f"{_n(w.get('splash_damage_max', 0))}-"
                         f"{_n(w.get('splash_damage_min', 0))} damage")
                desc += (" — including allies." if w.get("friendly_fire")
                         else ".")
            cards.append(_card("Charged Shot", desc))

        # Spawn count (scouts)
        sc = UNIT_TYPES[ut].get("spawn_count", 1)
        if sc > 1:
            cards.append(_card(
                "Swarm" if UNIT_TYPES[ut].get("is_t2") else "Pack Hunter",
                f"Spawns in groups of {sc}."))

        passives[ut] = cards

    # Buildings
    passives["command_center"] = [
        _card("Unit Production",
              f"Spawns a unit every {_n(s.CC_SPAWN_INTERVAL)}s. "
              "Metal extractors boost spawn speed."),
        _card("Defensive Laser",
              f"Fires at the closest enemy within {_n(s.CC_LASER_RANGE)}px "
              f"for {_n(s.CC_LASER_DAMAGE)} damage every "
              f"{_n(s.CC_LASER_COOLDOWN)}s."),
    ]
    passives["metal_extractor"] = [
        _card("Spawn Boost",
              f"Provides +{_pct(s.METAL_EXTRACTOR_SPAWN_BONUS)}% spawn "
              "speed to its Command Center."),
        _registry_card("reinforce"),
    ]
    return passives


UNIT_PASSIVES: dict[str, list[dict[str, str]]] = build_unit_passives()


# -- guide topics -------------------------------------------------------------
# (title, paragraphs). Empty string = paragraph break. The last topic is the
# link to the Unit Overview browser (both clients treat it specially).

GUIDE_TOPICS: list[tuple[str, list[str]]] = [
    (
        "Overview",
        [
            "AIRTS is an AI Real-Time Strategy game built for the BlueOrange AI Jam.",
            "",
            "Two teams compete to destroy each other's Command Center. Each team "
            "can be controlled by a human player or an AI controller.",
            "",
            "Games end when a Command Center is destroyed, or both are destroyed "
            "simultaneously (draw).",
            "",
            "Build units, capture metal spots for faster spawning, and use tactical "
            "movement to outplay your opponent.",
        ],
    ),
    (
        "Selection & Movement",
        [
            "LEFT CLICK on a unit to select it. Hold SHIFT to add to selection.",
            "",
            "LEFT CLICK + DRAG draws a circle selection around multiple units.",
            "",
            "RIGHT CLICK + DRAG draws a movement path. Selected units are "
            "distributed along the path using nearest-neighbor assignment.",
            "",
            "RIGHT CLICK on a single point to move all selected units there.",
            "",
            "When a Command Center is selected, RIGHT CLICK sets a rally point "
            "for newly spawned units.",
        ],
    ),
    (
        "Combat & Fire Modes",
        [
            "Units with 'can_attack = True' automatically fire at enemies within range.",
            "",
            "Attacks are laser-based with damage, range, and cooldown stats.",
            "",
            "Command Centers also have a defensive laser that fires at nearby enemies.",
            "",
            "Medics do not attack but heal nearby friendly units instead.",
            "",
            "Combat is resolved every frame — position your units wisely to focus fire "
            "and avoid taking unnecessary damage.",
        ],
    ),
    (
        "Command Centers",
        [
            "Each team starts with one Command Center (CC).",
            "",
            f"CCs spawn units every {_n(s.CC_SPAWN_INTERVAL)}s. Click the GUI "
            "panel at the bottom to choose which unit type to spawn.",
            "",
            f"CCs have a defensive laser (range {_n(s.CC_LASER_RANGE)}, damage "
            f"{_n(s.CC_LASER_DAMAGE)}, cooldown {_n(s.CC_LASER_COOLDOWN)}s).",
            "",
            f"Metal Extractors boost the CC's spawn speed by "
            f"{_pct(s.METAL_EXTRACTOR_SPAWN_BONUS)}% each.",
            "",
            "If your CC is destroyed, you lose!",
        ],
    ),
    (
        "Metal Spots & Economy",
        [
            "Metal Spots are golden circles scattered across the map.",
            "",
            "Send units near a Metal Spot to capture it. The capture progress "
            "depends on how many units are within range.",
            "",
            "Once captured, a Metal Extractor is built on the spot.",
            "",
            f"Each Metal Extractor ({_n(s.METAL_EXTRACTOR_HP)} HP) boosts your "
            f"CC's spawn speed by {_pct(s.METAL_EXTRACTOR_SPAWN_BONUS)}%, and "
            "can later be upgraded into an Outpost or a Research Lab.",
            "",
            "Extractors can be destroyed by the enemy team.",
            "",
            "Controlling metal spots gives you a significant unit production advantage.",
        ],
    ),
    (
        "Unit Overview",
        [
            "Click here to open the interactive Unit Overview browser, where you "
            "can inspect each unit type's symbol, stats, and special abilities.",
        ],
    ),
]


# -- full snapshot (docs generation + web client build-time data) -------------

def build_gamedata() -> dict:
    """JSON-able snapshot consumed by tools/gen_docs.py and the web client."""
    return {
        "unit_types": UNIT_TYPES,
        "t2_names": T2_NAMES,
        "spawnable_types": list(get_spawnable_types().keys()),
        "building_types": ["command_center", "metal_extractor"],
        "unit_passives": UNIT_PASSIVES,
        "ability_descriptions": ABILITY_DESCRIPTIONS,
        "guide_topics": [{"title": t, "lines": lines} for t, lines in GUIDE_TOPICS],
        "command_center": {
            "hp": s.CC_HP,
            "radius": s.CC_RADIUS,
            "spawn_interval": s.CC_SPAWN_INTERVAL,
            "spawn_range": s.CC_SPAWN_RANGE,
            "laser_range": s.CC_LASER_RANGE,
            "laser_damage": s.CC_LASER_DAMAGE,
            "laser_cooldown": s.CC_LASER_COOLDOWN,
        },
        "metal": {
            "extractor_hp": s.METAL_EXTRACTOR_HP,
            "spawn_bonus": s.METAL_EXTRACTOR_SPAWN_BONUS,
            "capture_radius": s.METAL_SPOT_CAPTURE_RADIUS,
        },
    }
