"""Tests for player_id / team split on Unit and CommandCenter."""
from __future__ import annotations
import pytest
from config.settings import PLAYER_COLORS
from entities.unit import Unit
from entities.command_center import CommandCenter


def test_unit_player_id_stored():
    u = Unit(x=100, y=100, team=1, unit_type="soldier", player_id=2)
    assert u.player_id == 2


def test_unit_team_independent_of_player_id():
    u = Unit(x=0, y=0, team=1, unit_type="soldier", player_id=2)
    assert u.team == 1
    assert u.player_id == 2


def test_unit_color_uses_player_id():
    for pid in range(1, len(PLAYER_COLORS) + 1):
        u = Unit(x=0, y=0, team=1, unit_type="soldier", player_id=pid)
        assert u.color == PLAYER_COLORS[pid - 1]


def test_cc_player_id_stored():
    cc = CommandCenter(x=80, y=300, team=1, player_id=1)
    assert cc.player_id == 1
    assert cc.team == 1


def test_cc_different_player_same_team():
    cc = CommandCenter(x=80, y=200, team=1, player_id=2)
    assert cc.player_id == 2
    assert cc.team == 1


def test_unit_to_dict_includes_player_id():
    u = Unit(x=50, y=50, team=2, unit_type="scout", player_id=3)
    d = u.to_dict()
    assert d["player_id"] == 3


def test_unit_from_dict_round_trip():
    u = Unit(x=50, y=50, team=2, unit_type="scout", player_id=3)
    d = u.to_dict()
    u2 = Unit.from_dict(d)
    assert u2.player_id == 3
    assert u2.team == 2


def test_unit_from_dict_legacy_fallback():
    """Old serialized dicts without 'player_id' key fall back to 'team'."""
    # Build a valid dict from a real unit, then remove player_id
    original = Unit(x=10, y=10, team=2, unit_type="soldier", player_id=2)
    d = original.to_dict()
    d.pop("player_id", None)  # simulate old format
    u = Unit.from_dict(d)
    # Falls back: player_id = data.get("player_id", data.get("team", 1))
    assert u.player_id == 2


def test_player_colors_eight_entries():
    assert len(PLAYER_COLORS) == 8
