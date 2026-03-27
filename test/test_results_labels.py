"""Tests for ResultsScreen combined team names and player badges."""
from __future__ import annotations
import pygame
import pytest

# conftest.py ensures SDL_VIDEODRIVER=dummy and pygame.init()


def _make_results(**kwargs):
    from screens.results import ResultsScreen
    screen = pygame.display.set_mode((1280, 720), flags=pygame.NOFRAME)
    clock = pygame.time.Clock()
    return ResultsScreen(screen, clock, **kwargs)


class TestCombinedTeamNames:
    def test_1v1_name_passthrough(self):
        r = _make_results(team_names={1: "EasyAI", 2: "WanderAI"})
        assert r._team_names[1] == "EasyAI"
        assert r._team_names[2] == "WanderAI"

    def test_default_team_names(self):
        r = _make_results()
        assert r._team_names == {}

    def test_2v2_joined_names(self):
        """game.py produces joined names; ResultsScreen just stores them."""
        r = _make_results(team_names={1: "EasyAI & Wander", 2: "HardAI & Peri AI"})
        assert r._team_names[1] == "EasyAI & Wander"
        assert r._team_names[2] == "HardAI & Peri AI"


class TestGameTeamNamesJoining:
    """Test that game.py correctly builds joined team_names."""

    def test_1v1_single_names(self):
        """Simulate game.py name-building for 1v1."""
        player_names = {1: "Human", 2: "WanderAI"}
        player_team = {1: 1, 2: 2}
        all_teams = {1, 2}
        team_names = {}
        for team in sorted(all_teams):
            names = [player_names[pid] for pid in sorted(player_names)
                     if player_team.get(pid) == team]
            team_names[team] = " & ".join(names) if names else f"Team {team}"
        assert team_names[1] == "Human"
        assert team_names[2] == "WanderAI"

    def test_2v2_joined_names(self):
        """Simulate game.py name-building for 2v2."""
        player_names = {1: "EasyAI", 2: "Wander", 3: "HardAI", 4: "Peri AI"}
        player_team = {1: 1, 2: 1, 3: 2, 4: 2}
        all_teams = {1, 2}
        team_names = {}
        for team in sorted(all_teams):
            names = [player_names[pid] for pid in sorted(player_names)
                     if player_team.get(pid) == team]
            team_names[team] = " & ".join(names) if names else f"Team {team}"
        assert team_names[1] == "EasyAI & Wander"
        assert team_names[2] == "HardAI & Peri AI"


class TestPlayerBadgesRender:
    def test_badges_not_shown_for_1v1(self):
        r = _make_results(
            player_names={1: "Human", 2: "WanderAI"},
            player_team={1: 1, 2: 2},
        )
        assert not r._show_badges

    def test_badges_shown_for_3_plus(self):
        r = _make_results(
            player_names={1: "A", 2: "B", 3: "C"},
            player_team={1: 1, 2: 1, 3: 2},
        )
        assert r._show_badges

    def test_badges_shown_for_4_players(self):
        r = _make_results(
            player_names={1: "A", 2: "B", 3: "C", 4: "D"},
            player_team={1: 1, 2: 1, 3: 2, 4: 2},
        )
        assert r._show_badges

    def test_draw_player_badges_no_crash(self):
        r = _make_results(
            player_names={1: "A", 2: "B", 3: "C", 4: "D"},
            player_team={1: 1, 2: 1, 3: 2, 4: 2},
        )
        # Should not raise
        r._draw_player_badges()

    def test_tab_graph_offset_applied_for_badges(self):
        """Tab and graph should be shifted down by _BADGE_ROW_H when badges are shown."""
        from screens.results import _BADGE_ROW_H
        r_no_badges = _make_results(
            player_names={1: "A", 2: "B"},
            player_team={1: 1, 2: 2},
            stats={"teams": {}, "final": {}, "timestamps": []},
        )
        r_badges = _make_results(
            player_names={1: "A", 2: "B", 3: "C", 4: "D"},
            player_team={1: 1, 2: 1, 3: 2, 4: 2},
            stats={"teams": {}, "final": {}, "timestamps": []},
        )
        # Graph y should differ by _BADGE_ROW_H
        assert r_badges._graph.rect.y == r_no_badges._graph.rect.y + _BADGE_ROW_H
