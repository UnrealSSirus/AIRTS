"""Application controller — pygame lifecycle, screen routing."""
from __future__ import annotations
import pygame
from ui.theme import MENU_WIDTH, MENU_HEIGHT
from systems.ai import AIRegistry
from screens.base import ScreenResult
from screens.main_menu import MainMenuScreen
from screens.create_lobby import CreateLobbyScreen
from screens.guides import GuidesScreen
from screens.unit_overview import UnitOverviewScreen
from screens.results import ResultsScreen
from screens.replay_list import ReplayListScreen
from screens.replay_playback import ReplayPlaybackScreen


class App:
    """Top-level application: initialises pygame once, routes between screens."""

    def __init__(self):
        pygame.init()
        self._screen = pygame.display.set_mode((MENU_WIDTH, MENU_HEIGHT))
        pygame.display.set_caption("AIRTS")
        self._clock = pygame.time.Clock()

        self._registry = AIRegistry()
        self._registry.discover()
        if self._registry.errors:
            for err in self._registry.errors:
                print(f"[AI Registry] {err}")

    def run(self):
        result = ScreenResult("main_menu")
        while result.next_screen != "quit":
            result = self._run_screen(result)
        pygame.quit()

    def _run_screen(self, prev: ScreenResult) -> ScreenResult:
        name = prev.next_screen
        data = prev.data

        if name == "main_menu":
            return MainMenuScreen(self._screen, self._clock).run()

        elif name == "create_lobby":
            choices = self._registry.get_choices()
            if not choices:
                choices = [("wander", "Wander AI")]
            return CreateLobbyScreen(self._screen, self._clock, choices).run()

        elif name == "game":
            return self._run_game(data)

        elif name == "guides":
            return GuidesScreen(self._screen, self._clock).run()

        elif name == "unit_overview":
            return UnitOverviewScreen(self._screen, self._clock).run()

        elif name == "replays":
            return ReplayListScreen(self._screen, self._clock).run()

        elif name == "replay_playback":
            return self._run_replay_playback(data)

        elif name == "results":
            winner = data.get("winner", 0)
            human_teams = data.get("human_teams", set())
            stats = data.get("stats")
            replay_filepath = data.get("replay_filepath")
            return ResultsScreen(self._screen, self._clock,
                                 winner, human_teams, stats=stats,
                                 replay_filepath=replay_filepath).run()

        else:
            # Unknown or placeholder screens → back to menu
            return ScreenResult("main_menu")

    def _run_game(self, data: dict) -> ScreenResult:
        from game import Game
        from systems.map_generator import DefaultMapGenerator

        width = data.get("width", 800)
        height = data.get("height", 600)
        obs = data.get("obstacle_count", (4, 8))
        team_ai_ids: dict[int, str] = data.get("team_ai_ids", {})

        # Build AI instances from registry
        team_ai = {}
        for team, ai_id in team_ai_ids.items():
            try:
                team_ai[team] = self._registry.create(ai_id)
            except KeyError:
                from systems.ai import WanderAI
                team_ai[team] = WanderAI()

        if not team_ai:
            from systems.ai import WanderAI
            team_ai = {2: WanderAI()}

        # Resize display for game map dimensions
        game_screen = pygame.display.set_mode((width, height))

        replay_config = {
            "team_ai_ids": team_ai_ids,
            "obstacle_count": list(obs),
        }

        game = Game(
            width=width,
            height=height,
            map_generator=DefaultMapGenerator(obstacle_count=obs),
            team_ai=team_ai,
            screen=game_screen,
            clock=self._clock,
            replay_config=replay_config,
        )
        result = game.run()

        # Restore menu display size
        self._screen = pygame.display.set_mode((MENU_WIDTH, MENU_HEIGHT))

        return ScreenResult("results", data={
            "winner": result.get("winner", 0),
            "human_teams": result.get("human_teams", set()),
            "stats": result.get("stats"),
            "replay_filepath": result.get("replay_filepath"),
        })

    def _run_replay_playback(self, data: dict) -> ScreenResult:
        from systems.replay import ReplayReader
        from screens.replay_playback import TOP_BAR_HEIGHT, BOTTOM_BAR_HEIGHT

        filepath = data.get("filepath", "")
        reader = ReplayReader(filepath)
        mw = reader.map_width
        mh = reader.map_height

        # Resize display for replay: top bar + map + bottom bar
        replay_screen = pygame.display.set_mode((mw, TOP_BAR_HEIGHT + mh + BOTTOM_BAR_HEIGHT))

        result = ReplayPlaybackScreen(replay_screen, self._clock, filepath).run()

        # Restore menu display size
        self._screen = pygame.display.set_mode((MENU_WIDTH, MENU_HEIGHT))

        return result
