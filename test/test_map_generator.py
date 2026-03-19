"""Tests for DefaultMapGenerator with player_team support."""
from __future__ import annotations
import pytest
from systems.map_generator import DefaultMapGenerator
from entities.command_center import CommandCenter


def test_1v1_generates_two_ccs():
    gen = DefaultMapGenerator(obstacle_count=(0, 0))
    entities = gen.generate(800, 600, player_team={1: 1, 2: 2})
    ccs = [e for e in entities if isinstance(e, CommandCenter)]
    assert len(ccs) == 2


def test_2v2_generates_four_ccs():
    gen = DefaultMapGenerator(obstacle_count=(0, 0))
    entities = gen.generate(1200, 800, player_team={1: 1, 2: 1, 3: 2, 4: 2})
    ccs = [e for e in entities if isinstance(e, CommandCenter)]
    assert len(ccs) == 4


def test_1v1_cc_player_ids():
    gen = DefaultMapGenerator(obstacle_count=(0, 0))
    entities = gen.generate(800, 600, player_team={1: 1, 2: 2})
    ccs = sorted([e for e in entities if isinstance(e, CommandCenter)],
                 key=lambda c: c.player_id)
    assert ccs[0].player_id == 1
    assert ccs[0].team == 1
    assert ccs[1].player_id == 2
    assert ccs[1].team == 2


def test_2v2_cc_teams():
    gen = DefaultMapGenerator(obstacle_count=(0, 0))
    entities = gen.generate(1200, 800, player_team={1: 1, 2: 1, 3: 2, 4: 2})
    ccs = {e.player_id: e for e in entities if isinstance(e, CommandCenter)}
    assert ccs[1].team == 1
    assert ccs[2].team == 1
    assert ccs[3].team == 2
    assert ccs[4].team == 2


def test_2v2_left_side_players():
    """Players 1 and 2 should spawn on the left side (x < width/2)."""
    gen = DefaultMapGenerator(obstacle_count=(0, 0))
    entities = gen.generate(1200, 800, player_team={1: 1, 2: 1, 3: 2, 4: 2})
    ccs = {e.player_id: e for e in entities if isinstance(e, CommandCenter)}
    assert ccs[1].x < 600
    assert ccs[2].x < 600
    assert ccs[3].x > 600
    assert ccs[4].x > 600


def test_default_player_team_is_1v1():
    """generate() with no player_team defaults to 1v1."""
    gen = DefaultMapGenerator(obstacle_count=(0, 0))
    entities = gen.generate(800, 600)
    ccs = [e for e in entities if isinstance(e, CommandCenter)]
    assert len(ccs) == 2
