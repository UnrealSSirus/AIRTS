"""Internal server — runs Game + GameHost in a background thread for local play.

Used for singleplayer and LAN-host modes so that ALL game modes route through
the same GameClient → ClientGameScreen rendering path (Minecraft-style).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from networking.host import GameHost
from systems.commands import CommandQueue


class InternalServer:
    """Runs Game + GameHost in a background thread for local play."""

    def __init__(
        self,
        width: int,
        height: int,
        map_generator,
        player_ai: dict,
        player_team: dict[int, int] | None,
        replay_config: dict | None,
        player_name: str,
        max_ticks: int = 0,
        enable_t2: bool = False,
        max_players: int = 1,
        host_name: str = "Host",
        save_replay: bool = True,
        existing_host: GameHost | None = None,
    ):
        self._width = width
        self._height = height
        self._map_generator = map_generator
        self._player_ai = player_ai
        self._player_team = player_team
        self._replay_config = replay_config
        self._player_name = player_name
        self._max_ticks = max_ticks
        self._enable_t2 = enable_t2
        self._max_players = max_players
        self._host_name = host_name
        self._save_replay = save_replay
        self._owns_host = existing_host is None

        self._command_queue = CommandQueue()
        if existing_host is not None:
            self._host = existing_host
            # Update its broadcast interval for local play
            self._host._broadcast_interval = 2
        else:
            self._host = GameHost(
                command_queue=self._command_queue,
                port=0,  # ephemeral — OS picks a free port
                host_name=host_name,
                max_players=max_players,
                broadcast_interval=2,  # ~33ms for local play (smoother than default 6)
            )

        self._result: dict[str, Any] | None = None
        self._done_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._game = None  # set on game thread

    # -- public API ---------------------------------------------------------

    @property
    def port(self) -> int:
        """Actual bound port (blocks briefly until server socket is ready)."""
        return self._host.bound_port

    @property
    def host(self) -> GameHost:
        return self._host

    def start(self) -> None:
        """Start the GameHost networking, then launch the game thread."""
        self._host.start()
        self._thread = threading.Thread(target=self._run_game, daemon=True)
        self._thread.start()

    def wait_ready(self, timeout: float = 10.0) -> bool:
        """Block until the server is listening and ready for connections."""
        return self._host._bound_event.wait(timeout=timeout)

    def wait_done(self, timeout: float | None = None) -> bool:
        """Block until the game finishes."""
        return self._done_event.wait(timeout=timeout)

    @property
    def result(self) -> dict[str, Any] | None:
        """Game result dict (available after game finishes)."""
        return self._result

    def stop(self) -> None:
        """Clean shutdown of game and networking."""
        if self._game is not None:
            self._game.running = False
        self._host.stop()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    # -- game thread --------------------------------------------------------

    def _run_game(self) -> None:
        """Entry point for the background game thread."""
        from game import Game

        game = Game(
            width=self._width,
            height=self._height,
            map_generator=self._map_generator,
            player_ai=self._player_ai,
            player_team=self._player_team,
            player_name=self._player_name,
            headless=True,
            max_ticks=self._max_ticks,
            is_multiplayer=True,
            selectable_teams=set(),  # no local selection on server thread
            enable_t2=self._enable_t2,
            server_mode=True,
            save_replay=self._save_replay,
            replay_config=self._replay_config,
        )
        self._game = game

        # Bind host's command queue to the game's actual queue
        self._host._command_queue = game._command_queue

        # Wait for all clients to connect and be ready
        while not self._host.all_clients_ready:
            if not self._host._running:
                self._done_event.set()
                return
            time.sleep(0.05)

        # Build player_names for game_start message
        client_names = self._host.client_names
        player_names: dict[int, str] = {}
        for pid in sorted(game.all_players):
            if pid in client_names and client_names[pid]:
                player_names[pid] = client_names[pid]
            elif pid in game.player_ai:
                player_names[pid] = game.player_ai[pid].ai_name
            else:
                player_names[pid] = self._player_name

        # Send game_start
        self._host.send_game_start(
            game.entities, self._width, self._height,
            enable_t2=self._enable_t2,
            player_team=dict(game.player_team),
            player_names=player_names,
        )

        # Run simulation with networked callbacks
        def pre_step():
            self._host.inject_remote_commands()

        def post_step(tick, entities, laser_flashes, winner):
            self._host.broadcast_state(
                tick, entities, laser_flashes, winner,
                splash_effects=game.splash_effects,
            )

        try:
            result = game.run_server(pre_step=pre_step, post_step=post_step)
        except Exception as exc:
            result = {"winner": 0, "error": str(exc)}

        # Notify clients of game over
        self._host.send_game_over(result.get("winner", 0))
        time.sleep(0.3)  # brief delay for message to transmit

        self._result = result
        self._result["player_names"] = player_names
        self._done_event.set()
