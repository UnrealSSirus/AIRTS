"""Dedicated server — runs Game headlessly with all players as remote clients."""
from __future__ import annotations

import time
from typing import Any

from networking.host import GameHost
from networking.protocol import DEFAULT_PORT
from systems.commands import CommandQueue


class DedicatedServer:
    """Wires a headless Game + multi-client GameHost into a runnable server.

    Usage::

        server = DedicatedServer(port=7777, width=800, height=600)
        result = server.run()  # blocks until game ends
        print(result["winner"])
    """

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        width: int = 800,
        height: int = 600,
        obstacle_count: int = 0,
        max_ticks: int = 0,
        enable_t2: bool = False,
        host_name: str = "Server",
    ):
        self._port = port
        self._width = width
        self._height = height
        self._obstacle_count = obstacle_count
        self._max_ticks = max_ticks
        self._enable_t2 = enable_t2
        self._host_name = host_name

        self._game = None
        self._host: GameHost | None = None

    def run(self) -> dict[str, Any]:
        """Start server, wait for 2 clients, run game, return result."""
        from game import Game
        from systems.map_generator import DefaultMapGenerator

        obs = (self._obstacle_count, self._obstacle_count)

        # Create game in server mode — no display, no audio
        game = Game(
            width=self._width,
            height=self._height,
            map_generator=DefaultMapGenerator(obstacle_count=obs),
            player_ai={},  # both teams human (remote)
            player_team={1: 1, 2: 2},
            player_name=self._host_name,
            headless=True,
            max_ticks=self._max_ticks,
            is_multiplayer=True,
            selectable_teams=set(),  # no local selection
            enable_t2=self._enable_t2,
            server_mode=True,
        )
        self._game = game

        # Create host accepting 2 remote clients
        host = GameHost(
            command_queue=game._command_queue,
            port=self._port,
            host_name=self._host_name,
            max_players=2,
        )
        self._host = host
        host.start()

        print(f"[Server] Listening on port {self._port}")
        print(f"[Server] Local IP: {host.local_ip}")
        print(f"[Server] Connect to: {host.local_ip}:{self._port}")
        print(f"[Server] Waiting for 2 players...")

        # Wait for both players to connect and be ready
        while not host.all_clients_ready:
            time.sleep(0.1)
            names = host.client_names
            # Show progress
            connected = host.connected_count
            if connected > 0:
                name_list = ", ".join(f"P{pid}: {n}" for pid, n in names.items() if n)
                if name_list:
                    print(f"\r[Server] {connected}/2 players ready: {name_list}    ", end="", flush=True)

        names = host.client_names
        print(f"\n[Server] All players ready: {names}")

        # Update player names in the game result
        for pid, name in names.items():
            # Game tracks human_players via player_name; for server mode
            # we store names for the result dict
            pass

        # Send game_start to all clients
        host.send_game_start(game.entities, self._width, self._height)

        print("[Server] Game started!")

        # Run the game with networked callbacks
        def pre_step():
            host.inject_remote_commands()

        def post_step(tick, entities, laser_flashes, winner):
            host.broadcast_state(tick, entities, laser_flashes, winner,
                                 splash_effects=game.splash_effects)

        result = game.run_server(pre_step=pre_step, post_step=post_step)

        # Send game_over to all clients
        host.send_game_over(result.get("winner", 0))
        time.sleep(0.5)  # brief delay for message to transmit
        host.stop()

        # Override team_names with actual player names
        result["team_names"] = {pid: name for pid, name in names.items()}
        result["player_names"] = {pid: name for pid, name in names.items()}

        return result
