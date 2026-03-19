"""Tests for BaseAI player_id / team binding and query methods."""
from __future__ import annotations
import pytest
from systems.ai.wander import WanderAI
from entities.unit import Unit
from entities.command_center import CommandCenter


class _FakeGame:
    """Minimal game stub for AI binding tests."""
    def __init__(self):
        self.entities = []
        self.bounds = (800, 600)
        self._iteration = 0

    @property
    def units(self):
        return [e for e in self.entities if isinstance(e, Unit)]

    def _enqueue(self, cmd):
        pass


def _make_game_with_units():
    g = _FakeGame()
    # P1 units (team 1)
    for i in range(3):
        u = Unit(x=100+i*10, y=100, team=1, unit_type="soldier", player_id=1)
        u.alive = True
        g.entities.append(u)
    # P2 units (team 1, 2v2 ally)
    for i in range(2):
        u = Unit(x=120+i*10, y=150, team=1, unit_type="medic", player_id=2)
        u.alive = True
        g.entities.append(u)
    # P3 units (team 2, enemy)
    for i in range(2):
        u = Unit(x=700+i*10, y=300, team=2, unit_type="soldier", player_id=3)
        u.alive = True
        g.entities.append(u)
    # CC for player 1
    cc = CommandCenter(x=80, y=300, team=1, player_id=1)
    cc.alive = True
    g.entities.append(cc)
    return g


def test_bind_sets_player_id_and_team():
    ai = WanderAI()
    g = _make_game_with_units()
    ai._bind(player_id=1, team_id=1, game=g)
    assert ai._player_id == 1
    assert ai._team == 1


def test_get_own_units_by_player_id():
    ai = WanderAI()
    g = _make_game_with_units()
    ai._bind(player_id=1, team_id=1, game=g)
    own = ai.get_own_units()
    assert all(u.player_id == 1 for u in own)
    # 3 soldiers + 1 CC (CC is a Unit subclass)
    assert len(own) == 4


def test_get_own_mobile_units_excludes_cc():
    ai = WanderAI()
    g = _make_game_with_units()
    ai._bind(player_id=1, team_id=1, game=g)
    mobile = ai.get_own_mobile_units()
    assert all(u.player_id == 1 for u in mobile)
    assert len(mobile) == 3


def test_get_ally_units_same_team_different_player():
    ai = WanderAI()
    g = _make_game_with_units()
    ai._bind(player_id=1, team_id=1, game=g)
    allies = ai.get_ally_units()
    assert all(u.team == 1 and u.player_id != 1 for u in allies)
    assert len(allies) == 2


def test_get_enemy_units_different_team():
    ai = WanderAI()
    g = _make_game_with_units()
    ai._bind(player_id=1, team_id=1, game=g)
    enemies = ai.get_enemy_units()
    assert all(u.team != 1 for u in enemies)
    assert len(enemies) == 2


def test_get_cc_by_player_id():
    ai = WanderAI()
    g = _make_game_with_units()
    ai._bind(player_id=1, team_id=1, game=g)
    cc = ai.get_cc()
    assert cc is not None
    assert cc.player_id == 1
