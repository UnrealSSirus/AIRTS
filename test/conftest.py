"""Shared pytest fixtures for AIRTS core mechanics tests."""
from __future__ import annotations
import os
import sys
import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Minimal pygame stub so tests don't need a display
import pygame
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()


@pytest.fixture
def player_team_1v1():
    return {1: 1, 2: 2}


@pytest.fixture
def player_team_2v2():
    return {1: 1, 2: 1, 3: 2, 4: 2}


def _init_headless_fonts(g):
    """Set headless snapshot attributes required when calling step() directly."""
    g._headless_snap_font = pygame.font.SysFont(None, 18)
    g._headless_snap_surf = None


@pytest.fixture
def headless_game_1v1(player_team_1v1):
    """Minimal headless 1v1 Game with WanderAI on both sides."""
    from game import Game
    from systems.map_generator import DefaultMapGenerator
    from systems.ai.wander import WanderAI

    g = Game(
        width=800, height=600,
        map_generator=DefaultMapGenerator(obstacle_count=(0, 0)),
        player_ai={1: WanderAI(), 2: WanderAI()},
        player_team=player_team_1v1,
        headless=True,
    )
    _init_headless_fonts(g)
    return g


@pytest.fixture
def headless_game_2v2(player_team_2v2):
    """Minimal headless 2v2 Game with WanderAI on all slots."""
    from game import Game
    from systems.map_generator import DefaultMapGenerator
    from systems.ai.wander import WanderAI

    g = Game(
        width=1200, height=800,
        map_generator=DefaultMapGenerator(obstacle_count=(0, 0)),
        player_ai={1: WanderAI(), 2: WanderAI(), 3: WanderAI(), 4: WanderAI()},
        player_team=player_team_2v2,
        headless=True,
    )
    _init_headless_fonts(g)
    return g
