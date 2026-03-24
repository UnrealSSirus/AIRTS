"""Game class — owns the loop, wires systems together."""
from __future__ import annotations
import math
import random
import sys
import time
from typing import Any
import pygame
import pygame.sndarray

from entities.base import Entity
from entities.unit import Unit
from entities.command_center import CommandCenter
from entities.laser import LaserFlash, SplashEffect
from systems.combat import combat_step, PendingChain
from systems.physics import clamp_units_to_bounds
from systems.spawning import spawn_step
from systems.selection import click_select, apply_circle_selection, select_all_of_type
from systems.ai import BaseAI, WanderAI
from systems.map_generator import BaseMapGenerator, DefaultMapGenerator
from systems.capturing import capture_step
from entities.metal_spot import MetalSpot
from entities.metal_extractor import MetalExtractor
from config.settings import (
    SELECTION_FILL_COLOR, SELECTION_RECT_COLOR,
    COMMAND_PATH_COLOR, COMMAND_DOT_COLOR, PATH_SAMPLE_MIN_DIST,
    FIXED_DT, MAX_FRAME_DT, CC_RADIUS,
    PLAYER_COLORS, TEAM_COLORS, HEALTH_BAR_OFFSET,
    CAMERA_ZOOM_STEP, CAMERA_MAX_ZOOM,
    EDGE_PAN_MARGIN, EDGE_PAN_SPEED,
)
from entities.shapes import RectEntity, CircleEntity, PolygonEntity
from systems.commands import GameCommand, CommandQueue
from systems.replay import ReplayRecorder
from systems.stats import GameStats
from core.vectorized import build_obstacle_arrays, batch_obstacle_push, batch_unit_collisions, batch_facing_update
from core.quadfield import QuadField
from core.camera import Camera
import numpy as np

try:
    from core.fast_collisions import collision_pass as _cy_collision_pass
    _HAS_CYTHON = True
except ImportError:
    _HAS_CYTHON = False

import os
from ui.widgets import Slider, Button
import gui

_DBLCLICK_MS = 400

# -- metallic border colours (outer highlight → inner shadow) ----------
_BORDER_OUTER = (160, 165, 175)
_BORDER_MID = (100, 105, 115)
_BORDER_INNER = (60, 62, 70)


def _draw_metallic_border(surface: pygame.Surface, rect: pygame.Rect,
                          thickness: int = 3) -> None:
    """Draw a bevelled metallic border around *rect*."""
    colors = [_BORDER_OUTER, _BORDER_MID, _BORDER_INNER]
    for i in range(min(thickness, len(colors))):
        c = colors[i]
        r = rect.inflate(-i * 2, -i * 2)
        if r.w > 0 and r.h > 0:
            pygame.draw.rect(surface, c, r, 1)

# Type registry for deserialization dispatch
_ENTITY_TYPES: dict[str, type] = {
    "Entity": Entity,
    "RectEntity": RectEntity,
    "CircleEntity": CircleEntity,
    "PolygonEntity": PolygonEntity,
    "Unit": Unit,
    "CommandCenter": CommandCenter,
    "MetalSpot": MetalSpot,
    "MetalExtractor": MetalExtractor,
}


class Game:
    def __init__(
        self,
        width: int = 800,
        height: int = 600,
        title: str = "AIRTS",
        map_generator: BaseMapGenerator | None = None,
        player_ai: dict[int, BaseAI] | None = None,
        player_team: dict[int, int] | None = None,
        team_ai: dict[int, BaseAI] | None = None,  # legacy alias for player_ai
        screen: pygame.Surface | None = None,
        clock: pygame.time.Clock | None = None,
        replay_config: dict | None = None,
        player_name: str = "Human",
        headless: bool = False,
        max_ticks: int = 0,
        save_replay: bool = True,
        save_debug_summary: bool = False,
        step_timeout_ms: float = 0,
        replay_output_dir: str = "replays",
        screen_width: int | None = None,
        screen_height: int | None = None,
        is_multiplayer: bool = False,
        selectable_teams: set[int] | None = None,
        enable_t2: bool = False,
        server_mode: bool = False,
    ):
        """
        *team_ai* maps team numbers to AI controllers.  Teams **not** present
        in the dict are human-controlled.  At least one team must have an AI
        (Human-vs-Human is not supported).

        Legacy *team_ai* (maps team_id → AI) is still accepted and treated as
        player_ai with team_id == player_id (1v1 default).

        Examples::

            player_ai={2: WanderAI()}, player_team={1:1, 2:2}  # Human (P1/T1) vs AI (P2/T2)
            player_ai={1: EasyAI(), 2: WanderAI(), 3: EasyAI(), 4: WanderAI()},
            player_team={1:1, 2:1, 3:2, 4:2}  # 2v2
        """
        # Backward compat: treat team_ai as player_ai when player_ai not given
        if player_ai is None and team_ai is not None:
            player_ai = team_ai

        self._server_mode = server_mode

        if server_mode:
            # Headless dedicated server — no display, no fonts, no UI
            self.screen = pygame.Surface((1, 1))
            self._owns_pygame = False
            headless = True
            save_replay = False
        elif screen is None:
            pygame.init()
            self.screen = pygame.display.set_mode((width, height))
            pygame.display.set_caption(title)
            self._owns_pygame = True
        else:
            self.screen = screen
            self._owns_pygame = False

        # Map dimensions (world)
        self.width = width
        self.height = height

        # Screen dimensions (display) — defaults to map dims for backward compat
        self._screen_width = screen_width if screen_width is not None else width
        self._screen_height = screen_height if screen_height is not None else height

        if not server_mode:
            # Layout areas
            self._header_h = 40
            self._hud_h = int(self._screen_height * 0.20)
            self._header_rect = pygame.Rect(0, 0, self._screen_width, self._header_h)
            self._hud_rect = pygame.Rect(0, self._screen_height - self._hud_h,
                                         self._screen_width, self._hud_h)
            self._game_area = pygame.Rect(0, self._header_h, self._screen_width,
                                          self._screen_height - self._header_h - self._hud_h)

        self.clock = clock or pygame.time.Clock()
        self.running = False
        self.fps = 60
        self._headless = headless
        self._max_ticks = max_ticks
        self._save_replay = save_replay
        self._save_debug_summary = save_debug_summary
        self.enable_t2 = enable_t2
        self._step_timeout_ms = step_timeout_ms
        self._replay_output_dir = replay_output_dir
        self._player_name = player_name
        if not server_mode:
            self._fps_font = pygame.font.SysFont(None, 22)
            self._label_font = pygame.font.SysFont(None, 20)
        else:
            self._fps_font = None
            self._label_font = None

        self.entities: list[Entity] = []
        self.laser_flashes: list[LaserFlash] = []
        self.splash_effects: list[SplashEffect] = []
        self._pending_chains: list[PendingChain] = []

        # -- sounds -----------------------------------------------------------
        if not headless:
            _sounds_dir = os.path.join(os.path.dirname(__file__), "sounds")
            self._sounds: dict[str, pygame.mixer.Sound] = {
                "fast_laser": pygame.mixer.Sound(os.path.join(_sounds_dir, "fast_laser.mp3")),
                "laser": pygame.mixer.Sound(os.path.join(_sounds_dir, "laser.mp3")),
            }
            # Generate "artillery" sound: pitch-shift laser.mp3 down ~8 semitones
            # by stretching the raw PCM array 1.7x longer.
            try:
                _base = pygame.mixer.Sound(os.path.join(_sounds_dir, "laser.mp3"))
                _arr = pygame.sndarray.array(_base)
                _factor = 1.7  # slower = lower pitch
                _n = int(len(_arr) * _factor)
                _idx = np.linspace(0, len(_arr) - 1, _n).astype(np.int32)
                _heavy = _arr[_idx]
                # Boost amplitude by 40% and clip to dtype range
                _heavy_f = _heavy.astype(np.float32) * 1.4
                if np.issubdtype(_arr.dtype, np.integer):
                    _info = np.iinfo(_arr.dtype)
                    _heavy = np.clip(_heavy_f, _info.min, _info.max).astype(_arr.dtype)
                else:
                    _heavy = np.clip(_heavy_f, -1.0, 1.0).astype(_arr.dtype)
                self._sounds["artillery"] = pygame.sndarray.make_sound(_heavy)
            except Exception:
                self._sounds["artillery"] = self._sounds["laser"]
        else:
            self._sounds: dict[str, pygame.mixer.Sound] = {}

        # -- player/team resolution -------------------------------------------
        _default_ai: dict[int, BaseAI] = {2: WanderAI()}
        self.player_ai: dict[int, BaseAI] = player_ai if player_ai is not None else _default_ai

        if player_team is not None:
            self.player_team: dict[int, int] = player_team
        else:
            # Default: each player is their own team (1v1 / AI-vs-AI)
            _all_pids = set(self.player_ai.keys()) | {1, 2}
            self.player_team = {p: p for p in _all_pids}

        self.all_teams: set[int] = set(self.player_team.values())
        self.all_players: set[int] = set(self.player_team.keys())
        self.human_players: set[int] = self.all_players - set(self.player_ai.keys())
        self.human_teams: set[int] = {self.player_team[p] for p in self.human_players}
        self._selectable_teams: set[int] = (
            set(selectable_teams) if selectable_teams is not None else set(self.human_teams)
        )
        # Players whose spawned units should be selectable — derived from
        # _selectable_teams so multiplayer host (selectable_teams={1}) never
        # gets client-side units marked selectable.
        self._selectable_players: set[int] = {
            p for p, t in self.player_team.items() if t in self._selectable_teams
        }

        # Legacy alias so external code (Perigee, arena, etc.) keeps working
        self.team_ai: dict[int, BaseAI] = self.player_ai

        gen = map_generator or DefaultMapGenerator()
        self.entities = gen.generate(width, height, player_team=self.player_team)
        self.metal_spots: list[MetalSpot] = [
            e for e in self.entities if isinstance(e, MetalSpot)
        ]
        self.units: list[Unit] = [e for e in self.entities if isinstance(e, Unit)]
        self.team_units: dict[int, list[Unit]] = {
            t: [u for u in self.units if u.team == t] for t in self.all_teams
        }
        # Backward-compat references
        self.team_1_units: list[Unit] = self.team_units.get(1, [])
        self.team_2_units: list[Unit] = self.team_units.get(2, [])
        self.command_centers: list[CommandCenter] = [
            e for e in self.entities if isinstance(e, CommandCenter)
        ]
        self.metal_extractors: list[MetalExtractor] = [
            e for e in self.entities if isinstance(e, MetalExtractor)
        ]
        self._precompute_obstacles()

        # -- spatial index for fast proximity queries --------------------------
        self._quadfield = QuadField(width, height, cell_size=10)
        self._quadfield.rebuild(self.units)

        self._next_entity_id: int = 1
        self._speed_multiplier: float = 1.0
        self._accumulator: float = 0.0
        self._assign_entity_ids()

        self._iteration = 0
        self._winner = 0  # 0 = undecided, positive = winning team, -1 = draw
        self._stats = GameStats(teams=self.all_teams)

        self._command_queue = CommandQueue()

        # T2 upgrade tracking: team → set of unit_type strings upgraded to T2
        self._t2_upgrades: dict[int, set[str]] = {t: set() for t in self.all_teams}

        self._apply_selectability()
        self._bind_and_start_ais()

        self._has_human = len(self.human_players) > 0
        self._is_multiplayer = is_multiplayer
        self._dragging = False
        self._drag_start: tuple[int, int] = (0, 0)
        self._drag_end: tuple[int, int] = (0, 0)

        self._rdragging = False
        self._rpath: list[tuple[float, float]] = []

        # Double-click detection
        self._last_click_time: int = 0
        self._last_click_pos: tuple[int, int] = (0, 0)

        self._paused = False
        self._mouse_grabbed = False

        if not server_mode:
            self._selection_surface = pygame.Surface((width, height), pygame.SRCALPHA)
            self._speed_slider = Slider(self._screen_width - 170, 10, 150, "Speed %", 25, 800, 100, 25)
            self._pause_btn = Button(self._screen_width - 210, 12, 32, 24, "||", icon="pause")
            self._reset_cam_btn = Button(70, 12, 50, 24, "Reset", font_size=18)
            self._pause_font = pygame.font.SysFont(None, 48)

            # -- camera & world surface -------------------------------------------
            self._world_surface = pygame.Surface((width, height))
            self._camera = Camera(self._game_area.w, self._game_area.h, width, height,
                                  max_zoom=CAMERA_MAX_ZOOM)
            self._mid_dragging = False
            self._mid_last: tuple[int, int] = (0, 0)

        if save_replay:
            self._replay_recorder = ReplayRecorder(width, height, replay_config)
        else:
            self._replay_recorder = None

        # -- phase state machine: warp_in → playing → explode ----------------
        self._phase: str = "warp_in"
        self._anim_timer: float = 0.0
        self._fragments: list[dict] = []
        if not server_mode:
            self._anim_surface = pygame.Surface((width, height), pygame.SRCALPHA)
            self._fog_surface = pygame.Surface((width, height), pygame.SRCALPHA)
            self._fog_border = pygame.Surface((width, height))
            self._fog_border.set_colorkey((0, 0, 0))

        self._physics_cooldown: int = 60  # ticks remaining; handles initial spawn settling

        # Cache CC visual data at init (CCs don't move), keyed by player_id
        self._cc_data: dict[int, dict] = {}
        for e in self.entities:
            if isinstance(e, CommandCenter):
                self._cc_data[e.player_id] = {
                    "x": e.x, "y": e.y,
                    "color": e.color,
                    "points": list(e.points),
                    "team": e.team,
                }

    # -- init helpers -------------------------------------------------------

    def _assign_entity_ids(self):
        for e in self.entities:
            if e.entity_id == 0:
                e.entity_id = self._next_entity_id
                self._next_entity_id += 1

    def _apply_selectability(self):
        for e in self.entities:
            if hasattr(e, "team") and hasattr(e, "selectable"):
                e.selectable = e.team in self._selectable_teams

    def _refresh_t2_upgrades(self):
        """Rebuild T2 upgrade sets from living Research Labs."""
        for t in self.all_teams:
            self._t2_upgrades[t] = set()
        for me in self.metal_extractors:
            if me.alive and me.upgrade_state == "research_lab" and me.researched_unit_type:
                self._t2_upgrades[me.team].add(me.researched_unit_type)

    def _bind_and_start_ais(self):
        for pid, ai in self.player_ai.items():
            ai._bind(pid, self.player_team[pid], self, stats=self._stats,
                     command_queue=self._command_queue)
            ai.on_start()

    # -- queries ------------------------------------------------------------

    def _precompute_obstacles(self):
        """Cache static obstacle geometry (CircleEntity/RectEntity never move)."""
        self._static_obstacles = [e for e in self.entities if e.obstacle]
        self._obs_circle = tuple(
            (obs.x, obs.y, obs.radius)
            for obs in self._static_obstacles if isinstance(obs, CircleEntity)
        )
        self._obs_rect = tuple(
            (obs.x, obs.y, obs.width, obs.height)
            for obs in self._static_obstacles if isinstance(obs, RectEntity)
        )
        self._circle_obs_np, self._rect_obs_np = build_obstacle_arrays(
            self._obs_circle, self._obs_rect
        )
        self._static_steer = tuple(
            (*e.center(), e.collision_radius())
            for e in self._static_obstacles if e.alive
        )

    def _refresh_steer_obstacles(self):
        """Build flat tuple of (x, y, radius) for unit steering."""
        bldg = tuple(
            (e.x, e.y, e.radius)
            for e in self.units if e.is_building and e.alive
        )
        Unit._steer_obstacles = self._static_steer + bldg

    # -- selection helpers --------------------------------------------------

    def _selection_center(self) -> tuple[float, float]:
        return (float(self._drag_start[0]), float(self._drag_start[1]))

    def _selection_radius(self) -> float:
        cx, cy = self._selection_center()
        return math.hypot(self._drag_end[0] - cx, self._drag_end[1] - cy)

    # -- right-click path ---------------------------------------------------

    def _path_total_length(self) -> float:
        total = 0.0
        for i in range(1, len(self._rpath)):
            ax, ay = self._rpath[i - 1]
            bx, by = self._rpath[i]
            total += math.hypot(bx - ax, by - ay)
        return total

    def _resample_path(self, n: int) -> list[tuple[float, float]]:
        if n <= 0 or len(self._rpath) < 2:
            return list(self._rpath[:n])

        total = self._path_total_length()
        if total < 1e-6:
            return [self._rpath[0]] * n

        if n == 1:
            return [self._rpath[len(self._rpath) // 2]]

        spacing = total / (n - 1)
        points: list[tuple[float, float]] = [self._rpath[0]]
        accumulated = 0.0
        seg = 1
        seg_start = self._rpath[0]

        for i in range(1, n - 1):
            target_dist = i * spacing
            while seg < len(self._rpath):
                sx, sy = seg_start
                ex, ey = self._rpath[seg]
                seg_len = math.hypot(ex - sx, ey - sy)
                if accumulated + seg_len >= target_dist:
                    frac = (target_dist - accumulated) / seg_len if seg_len > 0 else 0
                    px = sx + (ex - sx) * frac
                    py = sy + (ey - sy) * frac
                    points.append((px, py))
                    break
                accumulated += seg_len
                seg_start = self._rpath[seg]
                seg += 1
            else:
                points.append(self._rpath[-1])

        points.append(self._rpath[-1])
        return points

    def _set_rally_points(self):
        if not self._rpath:
            return
        rally = self._rpath[-1]
        for entity in self.entities:
            if isinstance(entity, CommandCenter) and entity.selected:
                pid = entity.player_id
                if pid in self.human_players:
                    self._command_queue.enqueue(GameCommand(
                        type="set_rally",
                        player_id=pid,
                        tick=self._iteration,
                        data={"position": list(rally)},
                    ))
                    self._stats.record_action(entity.team)

    def _assign_path_goals(self):
        selected = [e for e in self.entities if isinstance(e, Unit) and e.selected]
        if not selected or len(self._rpath) < 2:
            if selected and len(self._rpath) == 1:
                px, py = self._rpath[0]
                by_player: dict[int, list[int]] = {}
                for u in selected:
                    if u.player_id in self.human_players:
                        self._stats.record_action(u.team)
                    by_player.setdefault(u.player_id, []).append(u.entity_id)
                for pid, uids in by_player.items():
                    self._command_queue.enqueue(GameCommand(
                        type="move",
                        player_id=pid,
                        tick=self._iteration,
                        data={"unit_ids": uids, "targets": [(px, py)] * len(uids)},
                    ))
            return

        goals = self._resample_path(len(selected))
        assigned: set[int] = set()
        # (player_id, entity_id, target)
        assignments: list[tuple[int, int, tuple[float, float]]] = []

        for gx, gy in goals:
            best_idx = -1
            best_dist = float("inf")
            for i, unit in enumerate(selected):
                if i in assigned:
                    continue
                d = math.hypot(unit.x - gx, unit.y - gy)
                if d < best_dist:
                    best_dist = d
                    best_idx = i
            if best_idx >= 0:
                u = selected[best_idx]
                assignments.append((u.player_id, u.entity_id, (gx, gy)))
                assigned.add(best_idx)
                if u.player_id in self.human_players:
                    self._stats.record_action(u.team)

        by_player: dict[int, tuple[list[int], list[tuple[float, float]]]] = {}
        for pid, eid, tgt in assignments:
            if pid not in by_player:
                by_player[pid] = ([], [])
            by_player[pid][0].append(eid)
            by_player[pid][1].append(tgt)
        for pid, (uids, tgts) in by_player.items():
            self._command_queue.enqueue(GameCommand(
                type="move",
                player_id=pid,
                tick=self._iteration,
                data={"unit_ids": uids, "targets": tgts},
            ))

    # -- pause / mouse grab ------------------------------------------------

    def _toggle_pause(self):
        self._paused = not self._paused
        if self._paused:
            self._pause_btn.label = ">"
            self._pause_btn.icon = "play"
            self._set_mouse_grab(False)
        else:
            self._pause_btn.label = "||"
            self._pause_btn.icon = "pause"
            self._set_mouse_grab(True)

    def _set_mouse_grab(self, grab: bool):
        self._mouse_grabbed = grab
        pygame.event.set_grab(grab)

    def _update_edge_pan(self, dt: float):
        """Pan camera when mouse is at the game area edge (only while grabbed)."""
        if not self._mouse_grabbed:
            return
        mx, my = pygame.mouse.get_pos()
        ga = self._game_area
        if not ga.collidepoint(mx, my):
            return
        dx = 0.0
        dy = 0.0
        if mx <= ga.left + EDGE_PAN_MARGIN:
            dx = EDGE_PAN_SPEED * dt
        elif mx >= ga.right - EDGE_PAN_MARGIN - 1:
            dx = -EDGE_PAN_SPEED * dt
        if my <= ga.top + EDGE_PAN_MARGIN:
            dy = EDGE_PAN_SPEED * dt
        elif my >= ga.bottom - EDGE_PAN_MARGIN - 1:
            dy = -EDGE_PAN_SPEED * dt
        if dx or dy:
            self._camera.pan(dx, dy)

    # -- coordinate helpers ------------------------------------------------

    def _screen_to_world(self, pos: tuple[int, int]) -> tuple[float, float]:
        """Convert a screen position to world coordinates via the camera."""
        return self._camera.screen_to_world(
            float(pos[0] - self._game_area.x),
            float(pos[1] - self._game_area.y),
        )

    # -- events -------------------------------------------------------------

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._set_mouse_grab(False)
                self.running = False

            if self._pause_btn.handle_event(event):
                self._toggle_pause()
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if self._paused:
                        # Already paused — quit the game
                        self._set_mouse_grab(False)
                        self.running = False
                    else:
                        self._toggle_pause()
                    continue

            # Scroll wheel zoom (available always, even while paused)
            if event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if self._game_area.collidepoint(mx, my):
                    vx = mx - self._game_area.x
                    vy = my - self._game_area.y
                    if event.y > 0:
                        self._camera.zoom_at(vx, vy, CAMERA_ZOOM_STEP)
                    elif event.y < 0:
                        self._camera.zoom_at(vx, vy, 1.0 / CAMERA_ZOOM_STEP)

            # Middle mouse pan (available always, even while paused)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
                if self._game_area.collidepoint(event.pos):
                    self._mid_dragging = True
                    self._mid_last = event.pos
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 2:
                self._mid_dragging = False
            elif event.type == pygame.MOUSEMOTION and self._mid_dragging:
                dx = event.pos[0] - self._mid_last[0]
                dy = event.pos[1] - self._mid_last[1]
                self._camera.pan(dx, dy)
                self._mid_last = event.pos

            # Skip all other input while paused (use pause button or ESC)
            if self._paused:
                continue

            if self._speed_slider.handle_event(event):
                self._speed_multiplier = self._speed_slider.value / 100.0

            if self._reset_cam_btn.handle_event(event):
                self._camera.reset()
                continue

            if not self._has_human:
                continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # HUD click — consume all clicks in the HUD area
                if self._hud_rect.collidepoint(event.pos):
                    hud_result = gui.handle_hud_click(
                        self.entities, event.pos[0], event.pos[1],
                        self._screen_width, self._screen_height, self._hud_h,
                        enable_t2=self.enable_t2, t2_upgrades=self._t2_upgrades,
                    )
                    if hud_result is not None:
                        self._handle_hud_action(hud_result)
                    continue
                # Only start drag if click is in game area
                if not self._game_area.collidepoint(event.pos):
                    continue
                # Drag start: store in world coords
                wx, wy = self._screen_to_world(event.pos)
                self._dragging = True
                self._drag_start = (int(wx), int(wy))
                self._drag_end = (int(wx), int(wy))

            elif event.type == pygame.MOUSEMOTION:
                if self._dragging:
                    wx, wy = self._screen_to_world(event.pos)
                    self._drag_end = (int(wx), int(wy))
                if self._rdragging:
                    wx, wy = self._screen_to_world(event.pos)
                    pos_w = (wx, wy)
                    if self._rpath:
                        last = self._rpath[-1]
                        if math.hypot(pos_w[0] - last[0], pos_w[1] - last[1]) >= PATH_SAMPLE_MIN_DIST:
                            self._rpath.append(pos_w)
                    else:
                        self._rpath.append(pos_w)

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._dragging:
                wx, wy = self._screen_to_world(event.pos)
                self._drag_end = (int(wx), int(wy))
                shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
                sr = self._selection_radius()
                now = pygame.time.get_ticks()
                if sr < 5:
                    # Double-click detection uses screen-space distance
                    if (now - self._last_click_time < _DBLCLICK_MS
                            and math.hypot(event.pos[0] - self._last_click_pos[0],
                                           event.pos[1] - self._last_click_pos[1]) < 10):
                        select_all_of_type(
                            self.entities, wx, wy,
                        )
                    else:
                        click_select(
                            self.entities, wx, wy,
                            additive=bool(shift),
                        )
                    self._last_click_time = now
                    self._last_click_pos = event.pos  # screen space for distance check
                else:
                    cx, cy = self._selection_center()
                    apply_circle_selection(
                        self.entities, cx, cy, sr,
                        additive=bool(shift),
                    )
                self._dragging = False

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                if not self._game_area.collidepoint(event.pos):
                    continue
                wx, wy = self._screen_to_world(event.pos)
                self._rdragging = True
                self._rpath = [(wx, wy)]

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 3 and self._rdragging:
                self._rdragging = False
                self._assign_path_goals()
                self._set_rally_points()
                self._rpath = []

    # -- command application ------------------------------------------------

    def _apply_command(self, cmd: GameCommand) -> None:
        """Resolve entity IDs in *cmd* and execute the mutation."""
        id_map: dict[int, Entity] = {e.entity_id: e for e in self.entities}
        data = cmd.data

        if cmd.type == "move":
            for uid, (tx, ty) in zip(data["unit_ids"], data["targets"]):
                unit = id_map.get(uid)
                if isinstance(unit, Unit) and unit.alive and unit.player_id == cmd.player_id:
                    unit.move(tx, ty)

        elif cmd.type == "attack":
            unit = id_map.get(data["unit_id"])
            target = id_map.get(data["target_id"])
            if (isinstance(unit, Unit) and unit.alive and unit.player_id == cmd.player_id
                    and target is not None and target.alive):
                unit.attack_target = target

        elif cmd.type == "stop":
            for uid in data["unit_ids"]:
                unit = id_map.get(uid)
                if isinstance(unit, Unit) and unit.alive and unit.player_id == cmd.player_id:
                    unit.stop()

        elif cmd.type == "set_rally":
            pos = tuple(data["position"])
            for e in self.entities:
                if isinstance(e, CommandCenter) and e.player_id == cmd.player_id:
                    e.rally_point = pos

        elif cmd.type == "set_spawn_type":
            for e in self.entities:
                if isinstance(e, CommandCenter) and e.player_id == cmd.player_id:
                    e.spawn_type = data["unit_type"]

        elif cmd.type == "upgrade_extractor":
            entity = id_map.get(data["entity_id"])
            path = data["path"]  # "watch_tower" or "research_lab"
            if (isinstance(entity, MetalExtractor)
                    and entity.alive
                    and entity.upgrade_state == "base"
                    and entity.is_fully_reinforced
                    and entity.team == self.player_team.get(cmd.player_id)
                    and self.enable_t2):
                if path == "watch_tower":
                    entity.start_upgrade("tower")
                elif path == "research_lab":
                    entity.upgrade_state = "choosing_research"

        elif cmd.type == "set_research_type":
            entity = id_map.get(data["entity_id"])
            unit_type = data["unit_type"]
            if (isinstance(entity, MetalExtractor)
                    and entity.alive
                    and entity.upgrade_state == "choosing_research"
                    and entity.team == self.player_team.get(cmd.player_id)
                    and self.enable_t2
                    and unit_type not in self._t2_upgrades.get(entity.team, set())):
                entity.researched_unit_type = unit_type
                entity.start_upgrade("lab")

        elif cmd.type == "set_pause":
            self._paused = bool(data.get("paused", False))

        elif cmd.type == "set_speed":
            self._speed_multiplier = max(0.25, min(8.0, float(data.get("speed", 1.0))))

    def _handle_hud_action(self, result: dict):
        """Process an action dict returned by gui.handle_hud_click."""
        action = result["action"]
        if action == "set_spawn_type":
            cc = gui.get_selected_cc(self.entities)
            if cc is not None:
                self._command_queue.enqueue(GameCommand(
                    type="set_spawn_type",
                    player_id=cc.player_id,
                    tick=self._iteration,
                    data={"unit_type": result["unit_type"]},
                ))
        elif action == "stop":
            selected = [e for e in self.entities
                        if isinstance(e, Unit) and e.selected and not e.is_building]
            if selected:
                by_player: dict[int, list[int]] = {}
                for u in selected:
                    by_player.setdefault(u.player_id, []).append(u.entity_id)
                for pid, uids in by_player.items():
                    self._command_queue.enqueue(GameCommand(
                        type="stop",
                        player_id=pid,
                        tick=self._iteration,
                        data={"unit_ids": uids},
                    ))
        elif action == "upgrade_extractor":
            eid = result["entity_id"]
            path = result["path"]
            # Find the player_id of a human on the extractor's team
            me = next((e for e in self.entities
                       if isinstance(e, MetalExtractor) and e.entity_id == eid), None)
            if me is not None:
                pid = next((p for p in self.human_players
                            if self.player_team.get(p) == me.team), None)
                if pid is not None:
                    self._command_queue.enqueue(GameCommand(
                        type="upgrade_extractor",
                        player_id=pid,
                        tick=self._iteration,
                        data={"entity_id": eid, "path": path},
                    ))
        elif action == "set_research_type":
            eid = result["entity_id"]
            unit_type = result["unit_type"]
            me = next((e for e in self.entities
                       if isinstance(e, MetalExtractor) and e.entity_id == eid), None)
            if me is not None:
                pid = next((p for p in self.human_players
                            if self.player_team.get(p) == me.team), None)
                if pid is not None:
                    self._command_queue.enqueue(GameCommand(
                        type="set_research_type",
                        player_id=pid,
                        tick=self._iteration,
                        data={"entity_id": eid, "unit_type": unit_type},
                    ))

    # -- step ---------------------------------------------------------------

    def step(self, dt: float):
        _t0 = time.perf_counter()
        _perf = time.perf_counter

        # Drain and apply all pending commands before simulation
        _t = _perf()
        for cmd in self._command_queue.drain(self._iteration):
            self._apply_command(cmd)

        self._refresh_steer_obstacles()
        self._stats.record_subsystem("commands", (_perf() - _t) * 1000)

        # -- QuadField-based targeting build ------------------------------------
        qf = self._quadfield
        alive_units = [u for u in self.units if u.alive]

        # Sync quadfield with current positions (early-outs when cell unchanged)
        _t_tgt = _perf()
        for u in alive_units:
            qf.moved_unit(u)
        self._stats.record_subsystem("tgt_qf_sync", (_perf() - _t_tgt) * 1000)

        _t_tgt = _perf()
        # Vectorized nearest-enemy and nearest-ally calculation every 15 ticks
        if self._iteration % 15 == 0 and alive_units:
            positions = np.array([[u.x, u.y] for u in alive_units], dtype=np.float64)
            teams = np.array([u.team for u in alive_units], dtype=np.int8)

            for team_id in np.unique(teams):
                team_mask = teams == team_id
                enemy_mask = ~team_mask

                team_indices = np.where(team_mask)[0]
                enemy_indices = np.where(enemy_mask)[0]

                team_pos = positions[team_mask]      # (N, 2)

                # Nearest enemy
                if len(enemy_indices) > 0:
                    enemy_pos = positions[enemy_mask]     # (M, 2)
                    diffs = team_pos[:, np.newaxis, :] - enemy_pos[np.newaxis, :, :]  # (N, M, 2)
                    dists_sq = np.sum(diffs ** 2, axis=2)                              # (N, M)
                    nearest_enemy_idx = np.argmin(dists_sq, axis=1)                    # (N,)

                    enemy_units = [alive_units[j] for j in enemy_indices]
                    for i, ti in enumerate(team_indices):
                        alive_units[ti].nearest_enemy = enemy_units[nearest_enemy_idx[i]]

                # Nearest ally (excluding self via inf on the diagonal)
                n_team = len(team_indices)
                if n_team > 1:
                    ally_diffs = team_pos[:, np.newaxis, :] - team_pos[np.newaxis, :, :]  # (N, N, 2)
                    ally_dists_sq = np.sum(ally_diffs ** 2, axis=2)                        # (N, N)
                    np.fill_diagonal(ally_dists_sq, np.inf)
                    nearest_ally_idx = np.argmin(ally_dists_sq, axis=1)                    # (N,)

                    ally_units = [alive_units[j] for j in team_indices]
                    for i, ti in enumerate(team_indices):
                        alive_units[ti].nearest_ally = ally_units[nearest_ally_idx[i]]
        self._stats.record_subsystem("tgt_nearest_enemy", (_perf() - _t_tgt) * 1000)



        # Collision detection + resolution
        _t_tgt = _perf()
        if _HAS_CYTHON:
            # Cython fast path: spatial hash + resolution entirely in C
            _cy_collision_pass(alive_units)
        else:
            # Pure Python fallback via QuadField queries
            _reuse_nearby: list = []
            for u in alive_units:
                if u.is_building:
                    continue
                nearby = qf.get_units_exact(u.x, u.y, u.radius, out=_reuse_nearby)
                for other in nearby:
                    if other is u:
                        continue
                    dx = other.x - u.x
                    dy = other.y - u.y
                    dist_sq = dx * dx + dy * dy
                    min_dist = u.radius + other.radius
                    if dist_sq < min_dist * min_dist:
                        dist = math.sqrt(max(dist_sq, 1e-24))
                        overlap = min_dist - dist
                        nx = dx / dist
                        ny = dy / dist
                        if other.is_building:
                            u.x -= nx * overlap
                            u.y -= ny * overlap
                        elif id(u) < id(other):
                            half = overlap * 0.5
                            u.x -= nx * half
                            u.y -= ny * half
                            other.x += nx * half
                            other.y += ny * half
        self._stats.record_subsystem("tgt_populate", (_perf() - _t_tgt) * 1000)

        # Batch facing update (replaces per-unit _update_facing)
        _t = _perf()
        facing_units = [u for u in alive_units if not u.is_building and u._tick % 5 == 0]
        batch_facing_update(facing_units, dt * 5)

        for entity in self.entities:
            entity.update(dt)
        self._stats.record_subsystem("entity_update", (_perf() - _t) * 1000)

        units = self.units
        obstacles = self._static_obstacles
        metal_extractors = self.metal_extractors

        _t = _perf()
        for player_id, ai in self.player_ai.items():
            try:
                ai.on_step(self._iteration)
            except Exception:
                failing_team = self.player_team.get(player_id)
                surviving = self.all_teams - ({failing_team} if failing_team else set())
                self._winner = next(iter(surviving)) if len(surviving) == 1 else -1
                self._phase = "explode"
                self._anim_timer = 0.0
        self._stats.record_subsystem("ai_step", (_perf() - _t) * 1000)

        # Capture — track new entities so extractors join units + team lists
        entity_count_before_capture = len(self.entities)
        _t = _perf()
        capture_step(self.entities, self.command_centers, self.units, self.metal_spots, metal_extractors, dt, stats=self._stats, grid=self._quadfield, teams=self.all_teams)

        if len(self.entities) > entity_count_before_capture:
            for e in self.entities[entity_count_before_capture:]:
                if isinstance(e, Unit):
                    self.units.append(e)
                    self._quadfield.add_unit(e)
                    self.team_units.setdefault(e.team, []).append(e)
                if hasattr(e, "selectable"):
                    e.selectable = e.team in self._selectable_teams
        self._stats.record_subsystem("capture", (_perf() - _t) * 1000)

        _t = _perf()
        combat_step(alive_units, obstacles, self.laser_flashes, dt,
                    quadfield=self._quadfield,
                    circle_obs=self._obs_circle, rect_obs=self._obs_rect,
                    splash_effects=None if self._headless else self.splash_effects,
                    sounds=None if self._headless else self._sounds,
                    pending_chains=self._pending_chains, stats=self._stats)
        self._stats.record_subsystem("combat", (_perf() - _t) * 1000)

        # Spawn — spawn_step already appends to self.units; add to team lists
        entity_count_before_spawn = len(self.entities)
        _t = _perf()
        spawn_step(self.entities, self.command_centers, self._selectable_players, stats=self._stats, tick=self._iteration, units=self.units,
                   t2_upgrades=self._t2_upgrades if self.enable_t2 else None)

        if len(self.entities) > entity_count_before_spawn:
            self._physics_cooldown = 60  # 1 second to settle after spawn
            for e in self.entities[entity_count_before_spawn:]:
                if isinstance(e, Unit):
                    self._quadfield.add_unit(e)
                    self.team_units.setdefault(e.team, []).append(e)
        self._stats.record_subsystem("spawn", (_perf() - _t) * 1000)

        _t = _perf()
        # Always assign IDs (cheap — skips entities that already have one)
        self._assign_entity_ids()
        # Remove dead units from quadfield; only rebuild lists if something died
        _had_deaths = False
        for u in self.units:
            if not u.alive:
                self._quadfield.remove_unit(u)
                _had_deaths = True
        if _had_deaths:
            self.entities = [e for e in self.entities if e.alive]
            self.units = [u for u in self.units if u.alive]
            for t in self.all_teams:
                if t in self.team_units:
                    self.team_units[t] = [u for u in self.team_units[t] if u.alive]
            self.command_centers = [c for c in self.command_centers if c.alive]
            self.metal_extractors = [m for m in self.metal_extractors if m.alive]
        if self.enable_t2:
            self._refresh_t2_upgrades()
        self._stats.record_subsystem("cleanup", (_perf() - _t) * 1000)

        # Physics cooldown: detect movement to keep physics running
        _t = _perf()
        units = self.units
        mobile_units = [u for u in units if not u.is_building]

        any_moving = False
        for u in mobile_units:
            if u.target is not None:
                any_moving = True
                break
        if any_moving:
            self._physics_cooldown = 10  # keep running 10 ticks after movement stops

        if self._physics_cooldown > 0:
            self._physics_cooldown -= 1

            # Obstacle push (unit-unit collision already resolved above)
            if units:
                _tp = _perf()
                all_positions = np.column_stack([
                    np.array([u.x for u in units], dtype=np.float64),
                    np.array([u.y for u in units], dtype=np.float64),
                ])
                all_radii = np.array([u.radius for u in units], dtype=np.float64)
                all_is_bld = np.array([u.is_building for u in units], dtype=bool)
                self._stats.record_subsystem("phys_array_build", (_perf() - _tp) * 1000)
                self._stats.record_subsystem("phys_unit_collisions", 0.0)

                # Obstacle push on mobile units only
                _tp = _perf()
                mobile_mask = ~all_is_bld
                if np.any(mobile_mask):
                    mob_pos = all_positions[mobile_mask]
                    mob_radii = all_radii[mobile_mask]
                    mob_pos = batch_obstacle_push(mob_pos, mob_radii, self._circle_obs_np, self._rect_obs_np)
                    all_positions[mobile_mask] = mob_pos
                self._stats.record_subsystem("phys_obstacle_push", (_perf() - _tp) * 1000)

                # Write back positions
                _tp = _perf()
                for i, u in enumerate(units):
                    u.x = float(all_positions[i, 0])
                    u.y = float(all_positions[i, 1])
                self._stats.record_subsystem("phys_writeback", (_perf() - _tp) * 1000)
            else:
                self._stats.record_subsystem("phys_array_build", 0.0)
                self._stats.record_subsystem("phys_unit_collisions", 0.0)
                self._stats.record_subsystem("phys_obstacle_push", 0.0)
                self._stats.record_subsystem("phys_writeback", 0.0)

            _tp = _perf()
            clamp_units_to_bounds(units, self.width, self.height)
            self._stats.record_subsystem("phys_clamp", (_perf() - _tp) * 1000)
        else:
            # Skip physics — just clamp bounds
            clamp_units_to_bounds(units, self.width, self.height)
            # Record zeros so sub-component averages use the same sample count
            self._stats.record_subsystem("phys_array_build", 0.0)
            self._stats.record_subsystem("phys_unit_collisions", 0.0)
            self._stats.record_subsystem("phys_obstacle_push", 0.0)
            self._stats.record_subsystem("phys_writeback", 0.0)
            self._stats.record_subsystem("phys_clamp", 0.0)
        self._stats.record_subsystem("physics", (_perf() - _t) * 1000)

        _t = _perf()
        self.laser_flashes = [lf for lf in self.laser_flashes if lf.update(dt)]
        self.splash_effects = [se for se in self.splash_effects if se.update(dt)]
        self._iteration += 1

        # Sample stats time-series every SAMPLE_INTERVAL ticks
        if self._iteration % GameStats.SAMPLE_INTERVAL == 0:
            self._stats.sample_tick(self._iteration, self.entities)

        if self._headless and not self._server_mode and (self._iteration == 1 or self._iteration % 5000 == 0):
            self._take_headless_snapshot()

        if self._replay_recorder is not None:
            self._replay_recorder.capture_tick(
                self._iteration, self.entities, self.laser_flashes,
            )

        # -- win condition: check if < all teams have a living CC ---------------
        surviving_teams = {cc.team for cc in self.command_centers if cc.alive}
        if len(surviving_teams) < len(self.all_teams) and self._winner == 0:
            if len(surviving_teams) == 1:
                self._winner = next(iter(surviving_teams))
            else:
                self._winner = -1  # draw
            # Transition to explode phase instead of ending immediately
            self._phase = "explode"
            self._anim_timer = 0.0
            # Init fragments for all losing teams
            losing_teams = self.all_teams - surviving_teams
            for t in losing_teams:
                self._init_fragments(t)

        # Tick limit — force draw if exceeded
        if self._max_ticks > 0 and self._iteration >= self._max_ticks and self._winner == 0:
            self._winner = -1
            self._phase = "explode"
            self._anim_timer = 0.0
        self._stats.record_subsystem("bookkeeping", (_perf() - _t) * 1000)

        _elapsed_ms = (time.perf_counter() - _t0) * 1000.0
        self._stats.record_step_time(_elapsed_ms)

        # Step timeout — force draw if a single step is too slow
        if self._step_timeout_ms > 0 and _elapsed_ms > self._step_timeout_ms and self._winner == 0:
            self._winner = -1
            self._phase = "explode"
            self._anim_timer = 0.0

    # -- serialization --------------------------------------------------------

    def save_state(self) -> dict[str, Any]:
        pending = []
        for ch in self._pending_chains:
            pending.append({
                "source_id": ch.source.entity_id,
                "last_target_id": ch.last_target.entity_id,
                "hit_set": list(ch.hit_set),
                "delay": ch.delay,
                "team": ch.team,
            })
        return {
            "entities": [e.to_dict() for e in self.entities],
            "laser_flashes": [lf.to_dict() for lf in self.laser_flashes],
            "pending_chains": pending,
            "iteration": self._iteration,
            "winner": self._winner,
            "next_entity_id": self._next_entity_id,
        }

    def load_state(self, data: dict[str, Any]):
        raw_entities = data["entities"]

        # Pass 1: create all entities from flat dicts
        pairs: list[tuple[Entity, dict]] = []
        for ed in raw_entities:
            cls = _ENTITY_TYPES[ed["type"]]
            entity = cls.from_dict(ed)
            pairs.append((entity, ed))

        # Pass 2: build lookup map, resolve cross-references
        id_map: dict[int, Entity] = {e.entity_id: e for e, _ in pairs}

        for entity, ed in pairs:
            if isinstance(entity, Unit):
                # Unit cross-references (applies to all Units including CC/ME)
                fid = ed.get("_follow_entity_id")
                if fid is not None and fid in id_map:
                    entity._follow_entity = id_map[fid]
                aid = ed.get("attack_target_id")
                if aid is not None and aid in id_map:
                    entity.attack_target = id_map[aid]
                # CC-specific cross-references
                if isinstance(entity, CommandCenter):
                    me_ids = ed.get("metal_extractor_ids", [])
                    entity.metal_extractors = [
                        id_map[mid] for mid in me_ids if mid in id_map
                    ]
                    entity._bounds = (self.width, self.height)
                # ME-specific cross-references
                elif isinstance(entity, MetalExtractor):
                    ms_id = ed.get("metal_spot_id")
                    if ms_id is not None and ms_id in id_map:
                        entity.metal_spot = id_map[ms_id]

        self.entities = [e for e, _ in pairs]
        self.metal_spots = [e for e in self.entities if isinstance(e, MetalSpot)]
        self.units = [e for e in self.entities if isinstance(e, Unit)]
        self.team_units = {t: [u for u in self.units if u.team == t] for t in self.all_teams}
        self.command_centers = [e for e in self.entities if isinstance(e, CommandCenter)]
        self.metal_extractors = [e for e in self.entities if isinstance(e, MetalExtractor)]
        self._precompute_obstacles()
        self._quadfield.rebuild(self.units)
        self.laser_flashes = [LaserFlash.from_dict(lfd) for lfd in data["laser_flashes"]]
        for lf, lfd in zip(self.laser_flashes, data["laser_flashes"]):
            sid = lfd.get("source_id")
            if sid is not None and sid in id_map:
                lf.source = id_map[sid]
            tid = lfd.get("target_id")
            if tid is not None and tid in id_map:
                lf.target = id_map[tid]
        self._pending_chains = []
        for chd in data.get("pending_chains", []):
            src_id = chd["source_id"]
            lt_id = chd["last_target_id"]
            if src_id not in id_map or lt_id not in id_map:
                continue
            src = id_map[src_id]
            if not hasattr(src, "weapon") or src.weapon is None:
                continue
            self._pending_chains.append(PendingChain(
                source=src,
                weapon=src.weapon,
                last_target=id_map[lt_id],
                hit_set=set(chd["hit_set"]),
                delay=chd["delay"],
                team=chd["team"],
            ))
        self._iteration = data["iteration"]
        self._winner = data["winner"]
        self._next_entity_id = data["next_entity_id"]
        self._apply_selectability()

    # -- render -------------------------------------------------------------

    def render(self):
        ws = self._world_surface
        ws.fill((0, 0, 0))

        if self._phase == "warp_in":
            self._render_warp_in()
        elif self._phase == "explode":
            self._render_explode()
        else:
            # Normal playing render
            for entity in self.entities:
                entity.draw(ws)
            self._draw_fog()

        if self._phase != "warp_in":
            # Charge previews: targeting beam + splash zone while artillery charges
            for unit in self.units:
                if not unit.alive or unit._charge_pos is None or unit.weapon is None:
                    continue
                tx, ty = unit._charge_pos
                wpn = unit.weapon
                charge_frac = 1.0 - unit._charge_timer / wpn.charge_time
                beam_alpha = int(80 + 80 * charge_frac)
                ring_alpha = int(60 + 80 * charge_frac)

                # Targeting beam
                _ct = pygame.Surface(ws.get_size(), pygame.SRCALPHA)
                pygame.draw.line(_ct, (255, 160, 30, beam_alpha),
                                 (unit.x, unit.y), (tx, ty), wpn.laser_width)
                ws.blit(_ct, (0, 0))

                # Splash zone ring
                vis_r = int(wpn.splash_radius)
                if vis_r > 0:
                    _cr = pygame.Surface((vis_r * 2 + 4, vis_r * 2 + 4), pygame.SRCALPHA)
                    pygame.draw.circle(_cr, (255, 100, 30, ring_alpha),
                                       (vis_r + 2, vis_r + 2), vis_r, 2)
                    ws.blit(_cr, (int(tx) - vis_r - 2, int(ty) - vis_r - 2))

            for se in self.splash_effects:
                se.draw(ws)
            for lf in self.laser_flashes:
                lf.draw(ws)

        # AI / Human name labels above command centers (with bonus %)
        for entity in self.entities:
            if isinstance(entity, CommandCenter) and entity.alive:
                ai = self.player_ai.get(entity.player_id)
                name = ai.ai_name if ai else self._player_name
                bonus_pct = entity.get_total_bonus_percent()
                if bonus_pct > 0:
                    name = f"{name} (+{bonus_pct}%)"
                label_color = PLAYER_COLORS[entity.player_id - 1]
                name_surf = self._label_font.render(name, True, label_color)
                nx = int(entity.x) - name_surf.get_width() // 2
                ny = int(entity.y) - 40
                ws.blit(name_surf, (nx, ny))

        # Extractor bonus labels
        for entity in self.metal_extractors:
            if entity.alive:
                bonus = entity.get_spawn_bonus()
                pct = round(bonus * 100)
                label = f"+{pct}%"
                label_surf = self._label_font.render(label, True, (255, 255, 255))
                lx = int(entity.x) - label_surf.get_width() // 2
                ly = int(entity.y) - int(entity.radius + HEALTH_BAR_OFFSET + 12)
                ws.blit(label_surf, (lx, ly))

        if self._dragging:
            sr = self._selection_radius()
            if sr >= 5:
                cx, cy = self._selection_center()
                self._selection_surface.fill((0, 0, 0, 0))
                pygame.draw.circle(self._selection_surface, SELECTION_FILL_COLOR,
                                   (int(cx), int(cy)), int(sr))
                pygame.draw.circle(self._selection_surface, SELECTION_RECT_COLOR,
                                   (int(cx), int(cy)), int(sr), 1)
                ws.blit(self._selection_surface, (0, 0))

        if self._rdragging and len(self._rpath) >= 2:
            pygame.draw.lines(ws, COMMAND_PATH_COLOR, False,
                              [(int(px), int(py)) for px, py in self._rpath], 2)
            selected_count = sum(
                1 for e in self.entities if isinstance(e, Unit) and e.selected
            )
            if selected_count > 0:
                preview = self._resample_path(selected_count)
                for px, py in preview:
                    pygame.draw.circle(ws, COMMAND_DOT_COLOR, (int(px), int(py)), 4, 1)

        # -- Composite to screen --
        self.screen.fill((0, 0, 0))

        # Header bar
        pygame.draw.rect(self.screen, (20, 20, 30), self._header_rect)
        pygame.draw.line(self.screen, (40, 40, 55),
                         (0, self._header_h - 1),
                         (self._screen_width, self._header_h - 1))

        # Header widgets
        self._pause_btn.draw(self.screen)
        self._reset_cam_btn.draw(self.screen)
        self._speed_slider.draw(self.screen)
        fps_val = self.clock.get_fps()
        fps_surf = self._fps_font.render(f"FPS: {fps_val:.0f}", True, (200, 200, 200))
        self.screen.blit(fps_surf, (4, 12))

        # Game area: black dead-space background then camera projection
        ga = self._game_area
        pygame.draw.rect(self.screen, (0, 0, 0), ga)
        self._camera.apply(ws, self.screen, dest=(ga.x, ga.y))

        # Metallic border around the world edge (rendered in screen space)
        bx0, by0 = self._camera.world_to_screen(0, 0)
        bx1, by1 = self._camera.world_to_screen(self.width, self.height)
        border_rect = pygame.Rect(
            int(bx0) + ga.x, int(by0) + ga.y,
            int(bx1 - bx0), int(by1 - by0),
        )
        # Clip border drawing to the game area
        clip_save = self.screen.get_clip()
        self.screen.set_clip(ga)
        _draw_metallic_border(self.screen, border_rect, 3)
        self.screen.set_clip(clip_save)

        # HUD area
        pygame.draw.rect(self.screen, (20, 20, 30), self._hud_rect)
        pygame.draw.line(self.screen, (40, 40, 55),
                         (0, self._hud_rect.top),
                         (self._screen_width, self._hud_rect.top))
        if self._has_human:
            gui.draw_hud(self.screen, self.entities,
                         self._screen_width, self._screen_height, self._hud_h,
                         enable_t2=self.enable_t2, t2_upgrades=self._t2_upgrades)

        # Paused overlay (centered on game area)
        if self._paused:
            pause_surf = self._pause_font.render("PAUSED", True, (220, 220, 240))
            hint_surf = self._fps_font.render("ESC again to quit", True, (140, 140, 160))
            px = ga.centerx - pause_surf.get_width() // 2
            py = ga.centery - pause_surf.get_height() // 2 - 10
            self.screen.blit(pause_surf, (px, py))
            hx = ga.centerx - hint_surf.get_width() // 2
            self.screen.blit(hint_surf, (hx, py + pause_surf.get_height() + 4))

        pygame.display.flip()

    # -- drawing helpers ----------------------------------------------------

    def _draw_fog(self):
        """Draw fog of war overlay — only when a human is playing.

        Fog is skipped entirely in local games where humans play on multiple teams
        (useful for debugging / local co-op/vs). Online multiplayer always keeps fog.
        """
        if not self._has_human:
            return
        # Local game with humans on both teams → no fog (full visibility)
        if not self._is_multiplayer and len(self.human_teams) > 1:
            return

        FOG_ALPHA = 200
        self._fog_surface.fill((0, 0, 0, FOG_ALPHA))

        # Collect LOS sources for all human teams
        los_circles: list[tuple[int, int, int]] = []
        for entity in self.entities:
            if not entity.alive:
                continue
            if not hasattr(entity, "line_of_sight") or not hasattr(entity, "team"):
                continue
            if entity.team not in self.human_teams:
                continue
            r = int(entity.line_of_sight)
            if r <= 0:
                continue
            los_circles.append((int(entity.x), int(entity.y), r))

        # Punch transparent holes
        for ex, ey, r in los_circles:
            size = r * 2
            cutout = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(cutout, (0, 0, 0, FOG_ALPHA), (r, r), r)
            self._fog_surface.blit(cutout, (ex - r, ey - r),
                                   special_flags=pygame.BLEND_RGBA_SUB)

        self._world_surface.blit(self._fog_surface, (0, 0))

        # Border at the fog edge — outline of the union (no venn diagram)
        self._fog_border.fill((0, 0, 0))
        for ex, ey, r in los_circles:
            pygame.draw.circle(self._fog_border, (160, 160, 160), (ex, ey), r)
        for ex, ey, r in los_circles:
            pygame.draw.circle(self._fog_border, (0, 0, 0), (ex, ey), max(r - 1, 0))
        self._world_surface.blit(self._fog_border, (0, 0))

    # -- animation helpers --------------------------------------------------

    def _render_warp_in(self):
        """Render warp-in phase: non-CC entities normal, CCs scale in with glow."""
        ws = self._world_surface
        t = min(self._anim_timer / 3.0, 1.0)
        scale = t * (2.0 - t)  # ease-out curve

        # Draw all non-CC entities normally
        for entity in self.entities:
            if not isinstance(entity, CommandCenter):
                entity.draw(ws)

        # Draw CCs at scaled size
        for entity in self.entities:
            if isinstance(entity, CommandCenter) and entity.alive:
                entity.draw_scaled(ws, scale)

                # Glow ring: expands outward, fading
                glow_radius = int(CC_RADIUS * 3 * t)
                glow_alpha = int(120 * (1.0 - t))
                if glow_radius > 0 and glow_alpha > 0:
                    self._anim_surface.fill((0, 0, 0, 0))
                    glow_color = (*entity.color[:3], glow_alpha)
                    pygame.draw.circle(
                        self._anim_surface, glow_color,
                        (int(entity.x), int(entity.y)), glow_radius, 3,
                    )
                    ws.blit(self._anim_surface, (0, 0))

        self._draw_fog()

    def _init_fragments(self, team: int):
        """Create 6 triangular fragments from each losing CC's hexagon."""
        for pid, data in self._cc_data.items():
            if data.get("team") != team:
                continue
            self._init_fragments_for_cc(data)

    def _init_fragments_for_cc(self, data: dict):
        if not data:
            return

        cx, cy = data["x"], data["y"]
        color = data["color"]
        pts = data["points"]  # hex vertex offsets relative to center

        for i in range(len(pts)):
            p1 = pts[i]
            p2 = pts[(i + 1) % len(pts)]
            # Triangle: center, vertex i, vertex i+1
            tri = [(0.0, 0.0), p1, p2]

            # Outward direction: average of the two outer vertices
            out_x = (p1[0] + p2[0]) / 2
            out_y = (p1[1] + p2[1]) / 2
            dist = math.hypot(out_x, out_y) or 1.0
            out_x /= dist
            out_y /= dist

            speed = random.uniform(40, 120)
            self._fragments.append({
                "points": tri,
                "cx": cx, "cy": cy,
                "vx": out_x * speed + random.uniform(-20, 20),
                "vy": out_y * speed + random.uniform(-20, 20),
                "angle": 0.0,
                "rot_speed": random.uniform(-4, 4),
                "color": color,
            })

    def _update_fragments(self, dt: float):
        """Move and rotate explosion fragments."""
        for frag in self._fragments:
            frag["cx"] += frag["vx"] * dt
            frag["cy"] += frag["vy"] * dt
            frag["angle"] += frag["rot_speed"] * dt

    def _render_explode(self):
        """Render explode phase: surviving entities normal, fragments fly out."""
        ws = self._world_surface
        # Draw all surviving entities normally
        for entity in self.entities:
            entity.draw(ws)
        self._draw_fog()

        # Draw explosion fragments
        t = min(self._anim_timer / 3.0, 1.0)
        alpha = int(255 * (1.0 - t))
        if alpha <= 0:
            return

        self._anim_surface.fill((0, 0, 0, 0))
        for frag in self._fragments:
            cos_a = math.cos(frag["angle"])
            sin_a = math.sin(frag["angle"])
            rotated = []
            for px, py in frag["points"]:
                rx = px * cos_a - py * sin_a + frag["cx"]
                ry = px * sin_a + py * cos_a + frag["cy"]
                rotated.append((rx, ry))

            frag_color = (*frag["color"][:3], alpha)
            pygame.draw.polygon(self._anim_surface, frag_color, rotated)

        ws.blit(self._anim_surface, (0, 0))

    # -- headless snapshot ----------------------------------------------------

    _SNAP_W = 240
    _SNAP_H = 180
    _SNAP_PAD = 10

    def _take_headless_snapshot(self) -> None:
        """Render a small top-down minimap of the current game state."""
        sw, sh = self._SNAP_W, self._SNAP_H
        surf = pygame.Surface((sw, sh))
        surf.fill((20, 20, 30))

        sx = sw / self.width
        sy = sh / self.height

        gold = (255, 200, 60)
        obstacle_col = (80, 80, 80)

        # Obstacles
        for e in self.entities:
            if isinstance(e, (RectEntity, CircleEntity, PolygonEntity)):
                r = max(int(getattr(e, "radius", 4) * sx), 2)
                pygame.draw.circle(surf, obstacle_col,
                                   (int(e.x * sx), int(e.y * sy)), r)

        # Metal spots
        for ms in self.metal_spots:
            col = gold if ms.owner is None else TEAM_COLORS.get(ms.owner, gold)
            pygame.draw.circle(surf, col,
                               (int(ms.x * sx), int(ms.y * sy)), 3)

        # Metal extractors
        for e in self.metal_extractors:
            if e.alive:
                col = TEAM_COLORS.get(e.team, PLAYER_COLORS[0])
                px, py = int(e.x * sx), int(e.y * sy)
                pygame.draw.polygon(surf, col,
                                    [(px, py - 3), (px + 3, py + 2), (px - 3, py + 2)])

        # Command centers
        for cc in self.command_centers:
            col = PLAYER_COLORS[cc.player_id - 1]
            pygame.draw.circle(surf, col,
                               (int(cc.x * sx), int(cc.y * sy)), 5)
            pygame.draw.circle(surf, (255, 255, 255),
                               (int(cc.x * sx), int(cc.y * sy)), 5, 1)

        # Mobile units
        for u in self.units:
            if u.is_building or not u.alive:
                continue
            col = PLAYER_COLORS[u.player_id - 1]
            r = 2 if u.unit_type != "tank" else 3
            pygame.draw.circle(surf, col,
                               (int(u.x * sx), int(u.y * sy)), r)

        # Border
        pygame.draw.rect(surf, (100, 100, 120), (0, 0, sw, sh), 1)

        # Tick label
        game_secs = self._iteration / 60.0
        m, s = divmod(int(game_secs), 60)
        label = self._headless_snap_font.render(
            f"tick {self._iteration}  ({m}:{s:02d})", True, (180, 180, 200))
        surf.blit(label, (4, sh - label.get_height() - 2))

        self._headless_snap_surf = surf

    # -- run ----------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Run the game loop. Returns a result dict with winner info."""
        self.running = True

        if self._headless:
            self._phase = "playing"  # skip warp_in
            headless_font = pygame.font.SysFont(None, 28)
            self._headless_snap_font = pygame.font.SysFont(None, 18)
            self._headless_snap_surf: pygame.Surface | None = None
            while self.running:
                self.clock.tick(0)  # uncapped
                self.handle_events()  # pump events for QUIT/ESCAPE
                if not self._paused:
                    for _ in range(200):  # batch 200 ticks per frame
                        if self._phase != "playing":
                            break
                        self.step(FIXED_DT)
                if self._phase == "explode":
                    self.running = False  # skip explosion anim
                # Minimal display: black screen with in-game timer + snapshot
                self.screen.fill((0, 0, 0))
                game_secs = self._iteration / 60.0
                m, s = divmod(int(game_secs), 60)
                timer_str = f"Headless  —  {m}:{s:02d}  (tick {self._iteration})"
                timer_surf = headless_font.render(timer_str, True, (160, 160, 180))
                tx = self._screen_width // 2 - timer_surf.get_width() // 2
                ty = self._screen_height // 2 - timer_surf.get_height() // 2 - self._SNAP_H // 2 - 20
                self.screen.blit(timer_surf, (tx, ty))
                if self._headless_snap_surf is not None:
                    snap_x = self._screen_width // 2 - self._SNAP_W // 2
                    snap_y = ty + timer_surf.get_height() + self._SNAP_PAD
                    self.screen.blit(self._headless_snap_surf, (snap_x, snap_y))
                pygame.display.flip()
        else:
            # Grab the mouse at game start
            self._set_mouse_grab(True)

            while self.running:
                raw_dt = self.clock.tick(self.fps) / 1000.0
                real_dt = min(raw_dt, MAX_FRAME_DT)

                self.handle_events()
                self._update_edge_pan(real_dt)

                if self._paused:
                    self.render()

                elif self._phase == "warp_in":
                    self._anim_timer += real_dt
                    if self._anim_timer >= 3.0:
                        self._phase = "playing"
                    self.render()

                elif self._phase == "playing":
                    if self._speed_multiplier <= 0:
                        sim_dt = FIXED_DT * 100  # unlimited: up to 100 ticks/frame
                    else:
                        sim_dt = real_dt * self._speed_multiplier

                    self._accumulator += sim_dt

                    while self._accumulator >= FIXED_DT and self.running:
                        self.step(FIXED_DT)
                        self._accumulator -= FIXED_DT

                    self.render()

                elif self._phase == "explode":
                    self._anim_timer += real_dt
                    self._update_fragments(real_dt)
                    if self._anim_timer >= 3.0:
                        self.running = False
                    self.render()

            # Release mouse on game exit
            self._set_mouse_grab(False)

        stats_data = self._stats.finalize(self._winner, self.entities)
        if self._replay_recorder is not None:
            replay_path = self._replay_recorder.save(
                self._winner, self.human_teams, stats=stats_data,
                output_dir=self._replay_output_dir,
            )
        else:
            replay_path = ""

        # Build per-player name: AI name for AI players, player_name for humans
        player_names: dict[int, str] = {
            pid: (self.player_ai[pid].ai_name if pid in self.player_ai
                  else self._player_name)
            for pid in sorted(self.all_players)
        }

        # Build per-team name: join all player names with " & "
        team_names: dict[int, str] = {}
        for team in self.all_teams:
            names = [
                player_names[pid]
                for pid in sorted(self.all_players)
                if self.player_team.get(pid) == team
            ]
            team_names[team] = " & ".join(names) if names else f"Team {team}"

        if self._save_debug_summary:
            log_path = self._stats.save_summary_log(
                stats_data, self._winner, team_names=team_names,
            )
            print(f"[AIRTS] Game summary saved to {log_path}")

        result = {
            "winner": self._winner,
            "human_teams": self.human_teams,
            "stats": stats_data,
            "replay_filepath": replay_path,
            "team_names": team_names,
            "player_names": player_names,
            "player_team": dict(self.player_team),
        }

        if self._owns_pygame:
            pygame.quit()
            import sys
            sys.exit()

        return result

    def run_server(
        self,
        pre_step: "callable | None" = None,
        post_step: "callable | None" = None,
    ) -> dict[str, Any]:
        """Run the game loop for a dedicated server — no display, real-time 60Hz.

        *pre_step* is called before each tick (e.g. to inject remote commands).
        *post_step(tick, entities, laser_flashes, winner)* is called after each
        tick (e.g. to broadcast state to clients).
        """
        # On Windows, increase timer resolution from ~15.6ms to ~1ms so that
        # time.sleep() is accurate enough for a 60Hz game loop.
        _win_timer = False
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.winmm.timeBeginPeriod(1)
                _win_timer = True
            except Exception:
                pass

        self.running = True
        self._phase = "playing"

        tick_interval = FIXED_DT / 1.0  # ~16.67ms at 60 ticks/sec
        next_tick = time.perf_counter()

        try:
            while self.running and self._phase == "playing":
                now = time.perf_counter()

                # Always drain commands even while paused (so unpause arrives)
                if pre_step:
                    pre_step()

                if self._paused:
                    time.sleep(0.016)
                    # Still broadcast current state so clients stay in sync
                    if post_step:
                        post_step(self._iteration, self.entities,
                                  self.laser_flashes, self._winner)
                    next_tick = time.perf_counter()
                    continue

                effective_interval = tick_interval / self._speed_multiplier
                if now < next_tick:
                    sleep_time = next_tick - now
                    # Sleep most of the remaining time, then yield for the rest.
                    # Use a shorter sleep to avoid Windows oversleeping.
                    if sleep_time > 0.002:
                        time.sleep(sleep_time - 0.002)
                    else:
                        time.sleep(0)  # yield timeslice to other threads
                    continue

                # Cap catch-up: if we fell too far behind (e.g. GIL contention),
                # don't try to replay dozens of ticks — just reset to now.
                if now - next_tick > effective_interval * 4:
                    next_tick = now

                next_tick += effective_interval

                self.step(FIXED_DT)

                if post_step:
                    post_step(self._iteration, self.entities,
                              self.laser_flashes, self._winner)

                # If phase transitioned to explode, the game is over
                if self._phase == "explode":
                    self.running = False
        finally:
            if _win_timer:
                try:
                    ctypes.windll.winmm.timeEndPeriod(1)
                except Exception:
                    pass

        # Build result dict (same as run())
        stats_data = self._stats.finalize(self._winner, self.entities)
        player_names: dict[int, str] = {
            pid: (self.player_ai[pid].ai_name if pid in self.player_ai
                  else self._player_name)
            for pid in sorted(self.all_players)
        }
        team_names: dict[int, str] = {}
        for team in self.all_teams:
            names = [
                player_names[pid]
                for pid in sorted(self.all_players)
                if self.player_team.get(pid) == team
            ]
            team_names[team] = " & ".join(names) if names else f"Team {team}"

        return {
            "winner": self._winner,
            "human_teams": self.human_teams,
            "stats": stats_data,
            "replay_filepath": "",
            "team_names": team_names,
            "player_names": player_names,
            "player_team": dict(self.player_team),
        }
