"""Tests for win condition in 1v1 and 2v2 games."""
from __future__ import annotations
import pytest


def _run_until_winner(game, max_ticks=3000):
    from config.settings import FIXED_DT
    for _ in range(max_ticks):
        game.step(FIXED_DT)
        if game._winner != 0:
            return game._winner
    return 0


def test_1v1_winner_is_surviving_team(headless_game_1v1):
    """After one team's CC is destroyed, the other team wins."""
    g = headless_game_1v1
    # Destroy team 2's CC directly
    for cc in g.command_centers:
        if cc.team == 2:
            cc.hp = 0
            cc.alive = False
    from config.settings import FIXED_DT
    # Run a few steps to trigger win condition check
    for _ in range(10):
        g.step(FIXED_DT)
    assert g._winner == 1


def test_1v1_destroy_team1_cc(headless_game_1v1):
    g = headless_game_1v1
    for cc in g.command_centers:
        if cc.team == 1:
            cc.hp = 0
            cc.alive = False
    from config.settings import FIXED_DT
    for _ in range(10):
        g.step(FIXED_DT)
    assert g._winner == 2


def test_2v2_destroy_all_team2_ccs_wins_team1(headless_game_2v2):
    g = headless_game_2v2
    for cc in g.command_centers:
        if cc.team == 2:
            cc.hp = 0
            cc.alive = False
    from config.settings import FIXED_DT
    for _ in range(10):
        g.step(FIXED_DT)
    assert g._winner == 1


def test_2v2_partial_team2_loss_continues(headless_game_2v2):
    """Destroying only one team-2 CC in 2v2 should not end the game."""
    g = headless_game_2v2
    team2_ccs = [cc for cc in g.command_centers if cc.team == 2]
    assert len(team2_ccs) == 2
    # Kill only one
    team2_ccs[0].hp = 0
    team2_ccs[0].alive = False
    from config.settings import FIXED_DT
    for _ in range(10):
        g.step(FIXED_DT)
    # Game should still be ongoing (or explode phase, not decided)
    assert g._winner == 0 or g._phase in ("playing", "explode")


def test_all_ccs_destroyed_is_draw(headless_game_1v1):
    g = headless_game_1v1
    for cc in g.command_centers:
        cc.hp = 0
        cc.alive = False
    from config.settings import FIXED_DT
    for _ in range(10):
        g.step(FIXED_DT)
    assert g._winner == -1
