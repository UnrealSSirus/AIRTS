"""Regenerate stat tables in docs/ and the web client's build-time gamedata.

Everything is derived from config/settings.py + config/unit_types.py via
config/gamedata.py — run this after any balance change:

    python tools/gen_docs.py

Outputs:
  - docs/game-mechanics.md   (regions between <!-- AUTOGEN:name --> markers)
  - docs/ai-guide.md         (same marker scheme)
  - web/src/generated/gamedata.json  (data for the browser's Learn to Play
    screen; picked up by `npm run dev` / `npm run build`)

The npm build also runs this automatically via web/scripts/sync-assets.mjs.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import settings as s                                  # noqa: E402
from config.gamedata import (                                     # noqa: E402
    UNIT_PASSIVES, build_gamedata, _n, _pct,
)
from config.unit_types import (                                   # noqa: E402
    UNIT_TYPES, get_spawnable_types, get_t2_name, get_t2_type,
)

# One-line role blurbs for the docs tables (prose only — no numbers here).
_FLAVOR = {
    "soldier": "Basic all-rounder",
    "medic": "Support healer",
    "tank": "Frontline damage soak",
    "sniper": "Long-range assassin",
    "machine_gunner": "Sustained rapid fire",
    "scout": "Fast, fragile swarmer",
    "shockwave": "Chain-laser crowd damage",
    "artillery": "Siege splash damage",
    "engineer": "Economy support",
    "sweeper": "Vision support",
}


def _title(ut: str) -> str:
    return ut.replace("_", " ").title()


def _weapon_cols(ut: str) -> tuple[str, str, str]:
    """(damage, range, cooldown) column values for a unit type."""
    stats = UNIT_TYPES[ut]
    w = stats.get("weapon") or {}
    if not stats.get("can_attack", True) or not w:
        return "—", "—", "—"
    dmg = w["damage"]
    dmg_str = "—" if dmg <= 0 else _n(dmg)
    return dmg_str, _n(w["range"]), f"{_n(w['cooldown'])} s"


def _special(ut: str) -> str:
    parts = []
    flavor = _FLAVOR.get(ut.removesuffix("_t2"))
    if flavor:
        parts.append(flavor)
    names = [c["name"] for c in UNIT_PASSIVES.get(ut, [])]
    if names:
        parts.append("**" + "**, **".join(names) + "**")
    return "; ".join(parts) or "—"


def t1_table() -> str:
    lines = [
        "| Type | HP | Speed | Radius | Damage | Range | Cooldown | Special |",
        "|------|----|-------|--------|--------|-------|----------|---------|",
    ]
    for ut in get_spawnable_types():
        st = UNIT_TYPES[ut]
        dmg, rng, cd = _weapon_cols(ut)
        lines.append(
            f"| `{ut}` | {_n(st['hp'])} | {_n(st['speed'])} | "
            f"{_n(st['radius'])} | {dmg} | {rng} | {cd} | {_special(ut)} |")
    return "\n".join(lines)


def _key_changes(t1: str, t2: str) -> str:
    a, b = UNIT_TYPES[t1], UNIT_TYPES[t2]
    aw, bw = a.get("weapon") or {}, b.get("weapon") or {}
    parts: list[str] = []

    def diff(label: str, x, y, suffix: str = ""):
        if x is None or y is None or x == y:
            return
        d = round(y - x, 2)
        parts.append(f"{'+' if d > 0 else ''}{_n(d)}{suffix} {label}")

    diff("HP", a["hp"], b["hp"])
    diff("speed", a["speed"], b["speed"])
    if bw.get("damage", 0) > 0:
        diff("damage", aw.get("damage"), bw.get("damage"))
    else:
        diff("heal", abs(aw.get("damage", 0)), abs(bw.get("damage", 0)))
    diff("range", aw.get("range"), bw.get("range"))
    diff("cooldown", aw.get("cooldown"), bw.get("cooldown"), "s")
    diff("splash radius", aw.get("splash_radius"), bw.get("splash_radius"))
    if a.get("spawn_count", 1) != b.get("spawn_count", 1):
        parts.append(f"spawns {b.get('spawn_count', 1)} per cycle "
                     f"(was {a.get('spawn_count', 1)})")
    # Passive swaps (e.g. Reactive Armor -> Electric Armor)
    n1 = {c["name"] for c in UNIT_PASSIVES.get(t1, [])}
    n2 = {c["name"] for c in UNIT_PASSIVES.get(t2, [])}
    for gained in sorted(n2 - n1):
        parts.append(f"**{gained}**")
    return ", ".join(parts) or "—"


def t2_table() -> str:
    lines = [
        "| Type | HP | Speed | Damage | Range | Cooldown | Key changes vs T1 |",
        "|------|----|-------|--------|-------|----------|-------------------|",
    ]
    for t1 in get_spawnable_types():
        t2 = get_t2_type(t1)
        if t2 not in UNIT_TYPES:
            continue
        st = UNIT_TYPES[t2]
        dmg, rng, cd = _weapon_cols(t2)
        lines.append(
            f"| `{t2}` ({get_t2_name(t1)}) | {_n(st['hp'])} | "
            f"{_n(st['speed'])} | {dmg} | {rng} | {cd} | "
            f"{_key_changes(t1, t2)} |")
    return "\n".join(lines)


def unit_details() -> str:
    blocks: list[str] = []
    for t1 in get_spawnable_types():
        t2 = get_t2_type(t1)
        cards_t1 = UNIT_PASSIVES.get(t1, [])
        cards_t2 = UNIT_PASSIVES.get(t2, []) if t2 in UNIT_TYPES else []
        if not cards_t1 and not cards_t2:
            continue
        header = _title(t1)
        if t2 in UNIT_TYPES:
            header += f" / {get_t2_name(t1)} (T2)"
        lines = [f"#### {header}", ""]
        for c in cards_t1:
            lines.append(f"- **{c['name']}** (T1): {c['desc']}")
        for c in cards_t2:
            lines.append(f"- **{c['name']}** (T2): {c['desc']}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def passives_table() -> str:
    lines = [
        "| Unit | Ability | Effect |",
        "|------|---------|--------|",
    ]
    order = list(UNIT_TYPES) + ["command_center", "metal_extractor"]
    for ut in order:
        name = get_t2_name(ut) + " (T2)" if ut.endswith("_t2") else _title(ut)
        for c in UNIT_PASSIVES.get(ut, []):
            lines.append(f"| {name} | **{c['name']}** | {c['desc']} |")
    return "\n".join(lines)


def cc_stats_table() -> str:
    rows = [
        ("HP", _n(s.CC_HP)),
        ("Spawn interval", f"{_n(s.CC_SPAWN_INTERVAL)} s (base)"),
        ("Spawn radius", f"{_n(s.CC_SPAWN_RANGE)} px around the CC"),
        ("Defensive laser range", f"{_n(s.CC_LASER_RANGE)} px"),
        ("Defensive laser damage", _n(s.CC_LASER_DAMAGE)),
        ("Defensive laser cooldown", f"{_n(s.CC_LASER_COOLDOWN)} s"),
        ("Default spawn type", "Soldier"),
    ]
    lines = ["| Property | Value |", "|----------|-------|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


def extractor_stats_table() -> str:
    lines = [
        "| Property | Value |",
        "|----------|-------|",
        f"| HP | {_n(s.METAL_EXTRACTOR_HP)} |",
        f"| Spawn boost | +{_pct(s.METAL_EXTRACTOR_SPAWN_BONUS)}% additive per extractor |",
    ]
    return "\n".join(lines)


def upgrades_table() -> str:
    outpost = (
        f"Fires a defensive laser ({_n(s.OUTPOST_LASER_RANGE)} px range, "
        f"{_n(s.OUTPOST_LASER_DAMAGE)} dmg, {_n(s.OUTPOST_LASER_COOLDOWN)} s CD); "
        f"heals self at {_n(s.OUTPOST_HEAL_PER_SEC)} HP/s; "
        f"+{_n(s.OUTPOST_HP_BONUS)} HP; extended line of sight "
        f"({_n(s.OUTPOST_LOS)} px); +{_pct(s.T2_SPAWN_BONUS)}% spawn bonus"
    )
    lab = (
        f"Enables T2 unit spawns from the CC; +{_pct(s.T2_SPAWN_BONUS)}% "
        f"spawn bonus; +{_n(s.RESEARCH_LAB_HP_BONUS)} CC max HP"
    )
    return "\n".join([
        "| Structure | Upgrade time | Effect |",
        "|-----------|--------------|--------|",
        f"| **Outpost** | {_n(s.OUTPOST_UPGRADE_DURATION)} s | {outpost} |",
        f"| **Research Lab** | {_n(s.RESEARCH_LAB_UPGRADE_DURATION)} s | {lab} |",
        "",
        "During an upgrade the extractor provides no spawn bonus.",
    ])


SECTIONS: dict[str, str] = {}


def _build_sections() -> None:
    SECTIONS.update({
        "cc-stats": cc_stats_table(),
        "t1-units": t1_table(),
        "t2-units": t2_table(),
        "unit-details": unit_details(),
        "passives": passives_table(),
        "extractor-stats": extractor_stats_table(),
        "upgrades": upgrades_table(),
    })


def apply_markers(path: Path) -> int:
    """Replace every AUTOGEN region found in *path*; return replacement count."""
    text = path.read_text(encoding="utf-8")
    count = 0
    for name, body in SECTIONS.items():
        pattern = re.compile(
            rf"(<!-- AUTOGEN:{re.escape(name)}\b[^>]*-->)(.*?)(<!-- /AUTOGEN:{re.escape(name)} -->)",
            re.DOTALL,
        )

        def _sub(m: re.Match) -> str:
            nonlocal count
            count += 1
            return f"{m.group(1)}\n{body}\n{m.group(3)}"

        text = pattern.sub(_sub, text)
    path.write_text(text, encoding="utf-8")
    return count


def main() -> None:
    _build_sections()

    for rel in ("docs/game-mechanics.md", "docs/ai-guide.md"):
        path = ROOT / rel
        n = apply_markers(path)
        print(f"{rel}: {n} section(s) regenerated")

    out = ROOT / "web" / "src" / "generated" / "gamedata.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_gamedata(), indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"web/src/generated/gamedata.json: written")


if __name__ == "__main__":
    main()
