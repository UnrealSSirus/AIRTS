"""Client-side game screen — thin renderer that receives state from host."""
from __future__ import annotations

import math
import os
import random
import pygame
import pygame.sndarray
import numpy as np
from screens.base import BaseScreen, ScreenResult
from networking.client import GameClient
from systems.commands import GameCommand
from config.settings import (
    OBSTACLE_OUTLINE, HEALTH_BAR_WIDTH, HEALTH_BAR_HEIGHT,
    HEALTH_BAR_BG, HEALTH_BAR_FG, HEALTH_BAR_LOW, HEALTH_BAR_OFFSET,
    CC_RADIUS, METAL_SPOT_CAPTURE_RADIUS,
    METAL_SPOT_CAPTURE_RANGE_COLOR, METAL_EXTRACTOR_RADIUS,
    CC_HP, METAL_EXTRACTOR_HP,
    METAL_SPOT_CAPTURE_ARC_WIDTH,
    SELECTED_COLOR, SELECTION_FILL_COLOR, SELECTION_RECT_COLOR,
    TEAM_COLORS, PLAYER_COLORS,
    CAMERA_ZOOM_STEP, CAMERA_MAX_ZOOM,
    EDGE_PAN_MARGIN, EDGE_PAN_SPEED,
    GUI_BORDER, GUI_BTN_SELECTED, GUI_BTN_HOVER, GUI_BTN_NORMAL,
    GUI_TEXT_COLOR,
    RANGE_COLOR, MEDIC_HEAL_COLOR, CC_LASER_RANGE,
    REACTIVE_ARMOR_COLOR, ELECTRIC_ARMOR_COLOR,
)
from core.camera import Camera
from config.unit_types import UNIT_TYPES, get_spawnable_types
from ui.widgets import _get_font, Slider, Button
import gui
from gui_adapter import wrap_entities
from systems.replay import normalize_cp
from config import display as display_config

_STATUS_COLOR = (180, 180, 200)
_DISCONNECT_COLOR = (255, 100, 100)

# Command arrow colours/sizes (matching replay_playback.py)
_MOVE_CMD_COLOR = (0, 140, 40)
_ATTACK_CMD_COLOR = (180, 30, 30)
_ARROW_SIZE = 6

# HUD constants (matching gui.py style)
_SECTION_BG = (22, 22, 30)
_TITLE_COLOR = (210, 210, 230)
_STAT_LABEL = (130, 130, 155)
_DIVIDER = (50, 50, 65)
_BUILD_BTN_SIZE = 38
_BUILD_BTN_GAP = 4

# Metallic border colours (matching game.py)
_BORDER_OUTER = (160, 165, 175)
_BORDER_MID = (100, 105, 115)
_BORDER_INNER = (60, 62, 70)


def _draw_metallic_border(surface: pygame.Surface, rect: pygame.Rect,
                          thickness: int = 3) -> None:
    colors = [_BORDER_OUTER, _BORDER_MID, _BORDER_INNER]
    for i in range(min(thickness, len(colors))):
        c = colors[i]
        r = rect.inflate(-i * 2, -i * 2)
        if r.w > 0 and r.h > 0:
            pygame.draw.rect(surface, c, r, 1)


class ClientGameScreen(BaseScreen):
    """Renders state received from a GameHost and sends commands."""

    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        client: GameClient,
        is_local: bool = False,
    ):
        super().__init__(screen, clock)
        self._client = client
        self._is_local = is_local
        self._my_team: int = client.client_team
        self._all_teams: set[int] = set(client.player_team.values()) if client.player_team else {1, 2}
        mw = client.map_width
        mh = client.map_height

        # Layout areas — match host's header/hud/game area proportions
        self._header_h = 40
        self._hud_h = int(self.height * 0.20)
        self._header_rect = pygame.Rect(0, 0, self.width, self._header_h)
        self._hud_rect = pygame.Rect(0, self.height - self._hud_h,
                                     self.width, self._hud_h)
        self._game_area = pygame.Rect(0, self._header_h, self.width,
                                      self.height - self._header_h - self._hud_h)

        # World surface and camera
        self._world_surface = pygame.Surface((mw, mh))
        self._map_w = mw
        self._map_h = mh
        self._camera = Camera(self._game_area.w, self._game_area.h, mw, mh,
                              max_zoom=CAMERA_MAX_ZOOM)

        # State from host
        self._obstacles: list[dict] = client.obstacles
        self._entities: list[dict] = []
        self._lasers: list[list] = []
        self._tick: int = 0
        self._winner: int = 0

        # Local selection
        self._selected_ids: set[int] = set()
        self._dragging = False
        self._drag_start: tuple[int, int] = (0, 0)
        self._drag_end: tuple[int, int] = (0, 0)

        # Middle mouse pan
        self._mid_dragging = False
        self._mid_last: tuple[int, int] = (0, 0)

        # Right-click path drawing
        self._rdragging = False
        self._rpath: list[tuple[float, float]] = []
        self._PATH_MIN_DIST = 2.5

        # Selection surface for circle draw
        self._selection_surface = pygame.Surface((mw, mh), pygame.SRCALPHA)

        # Fog surfaces
        self._fog_surface = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self._fog_border = pygame.Surface((mw, mh))
        self._fog_border.set_colorkey((0, 0, 0))

        # Disconnect tracking
        self._disconnect_timer: float = 0.0

        # Enable T2 and upgrade tracking (from game_start message)
        self._enable_t2: bool = client.enable_t2
        self._t2_upgrades: dict[int, set[str]] = {}

        # HUD build button rects (cached) — still used for basic click detection
        self._build_btns = self._compute_build_btn_rects()

        # Animation state
        self._phase: str = "warp_in"  # warp_in → playing → explode
        self._anim_timer: float = 0.0
        self._anim_surface = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self._fragments: list[dict] = []
        self._splashes: list[dict] = []

        # Player names from game_start
        self._player_names: dict[int, str] = client.player_names or {}

        # Double-click detection
        self._last_click_time: int = 0
        self._last_click_pos: tuple[int, int] = (0, 0)
        _DBLCLICK_MS = 400

        # Local game controls (pause/speed/reset cam)
        self._paused = False
        if is_local:
            self._speed_slider = Slider(self.width - 170, 10, 150, "Speed %", 25, 800, 100, 25)
            self._pause_btn = Button(self.width - 210, 12, 32, 24, "||", icon="pause")
            self._reset_cam_btn = Button(70, 12, 50, 24, "Reset", font_size=18)
            self._pause_font = pygame.font.SysFont(None, 48)
        else:
            self._speed_slider = None
            self._pause_btn = None
            self._reset_cam_btn = None
            self._pause_font = None

        # Previous laser set for detecting new lasers (for sound)
        self._prev_laser_keys: set[tuple] = set()

        # Sound effects
        _sounds_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sounds")
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            self._sounds["fast_laser"] = pygame.mixer.Sound(os.path.join(_sounds_dir, "fast_laser.mp3"))
            self._sounds["laser"] = pygame.mixer.Sound(os.path.join(_sounds_dir, "laser.mp3"))
            # Generate artillery sound (pitch-shifted laser)
            _base = pygame.mixer.Sound(os.path.join(_sounds_dir, "laser.mp3"))
            _arr = pygame.sndarray.array(_base)
            _factor = 1.7
            _n = int(len(_arr) * _factor)
            _idx = np.linspace(0, len(_arr) - 1, _n).astype(np.int32)
            _heavy = _arr[_idx]
            _heavy_f = _heavy.astype(np.float32) * 1.4
            if np.issubdtype(_arr.dtype, np.integer):
                _info = np.iinfo(_arr.dtype)
                _heavy = np.clip(_heavy_f, _info.min, _info.max).astype(_arr.dtype)
            else:
                _heavy = np.clip(_heavy_f, -1.0, 1.0).astype(_arr.dtype)
            self._sounds["artillery"] = pygame.sndarray.make_sound(_heavy)
        except Exception:
            pass

    def _compute_build_btn_rects(self) -> list[tuple[pygame.Rect, str]]:
        """Compute spawn-type button rects inside the action panel area of the HUD."""
        # Action panel is rightmost 20% of HUD
        action_w = max(220, int(self.width * 0.20))
        ar = pygame.Rect(self.width - action_w, self.height - self._hud_h,
                         action_w, self._hud_h)
        types = list(get_spawnable_types().keys())
        pad, hdr = 8, 22
        iw = ar.width - pad * 2
        cols = max(1, (iw + _BUILD_BTN_GAP) // (_BUILD_BTN_SIZE + _BUILD_BTN_GAP))
        out: list[tuple[pygame.Rect, str]] = []
        for i, ut in enumerate(types):
            c, r = i % cols, i // cols
            bx = ar.left + pad + c * (_BUILD_BTN_SIZE + _BUILD_BTN_GAP)
            by = ar.top + pad + hdr + r * (_BUILD_BTN_SIZE + _BUILD_BTN_GAP)
            out.append((pygame.Rect(bx, by, _BUILD_BTN_SIZE, _BUILD_BTN_SIZE), ut))
        return out

    def run(self) -> ScreenResult:
        pygame.event.set_grab(True)
        try:
            return self._run_loop()
        finally:
            pygame.event.set_grab(False)

    def _run_loop(self) -> ScreenResult:
        while True:
            dt = self.clock.tick(60) / 1000.0
            self._anim_timer += dt

            # Poll for new state from host
            frame = self._client.poll_state()
            if frame:
                msg_type = frame.get("msg")
                if msg_type == "state":
                    self._entities = frame.get("entities", [])
                    self._lasers = frame.get("lasers", [])
                    self._splashes = frame.get("splashes", [])
                    self._tick = frame.get("tick", 0)
                    self._winner = frame.get("winner", 0)
                    self._disconnect_timer = 0.0
                    # Detect new lasers and play sounds
                    self._play_laser_sounds()
                elif msg_type == "game_over":
                    self._winner = frame.get("winner", 0)
            else:
                self._disconnect_timer += dt

            # Phase transitions
            if self._phase == "warp_in" and self._anim_timer >= 3.0:
                self._phase = "playing"

            if self._winner != 0 and self._phase == "playing":
                self._phase = "explode"
                self._anim_timer = 0.0
                # Build fragments from losing CCs
                losing_teams = self._all_teams - {self._winner} if self._winner > 0 else set()
                for _lt in losing_teams:
                    self._init_fragments(_lt)

            # Update explosion fragments
            if self._phase == "explode":
                self._update_fragments(dt)

            # Check for disconnect or game over
            if self._client.error and not self._is_local:
                return self._build_result()
            if self._phase == "explode" and self._anim_timer >= 3.0:
                return self._build_result()

            # Handle input
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._client.stop()
                    return ScreenResult("quit")

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._client.stop()
                    return ScreenResult("main_menu")

                # Pause toggle (spacebar for local games)
                if (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE
                        and self._is_local):
                    self._toggle_pause()

                # Selection hotkeys
                if event.type == pygame.KEYDOWN:
                    mods = pygame.key.get_mods()
                    if event.key == pygame.K_z and mods & pygame.KMOD_CTRL:
                        # Select own CC
                        self._selected_ids.clear()
                        for ent in self._entities:
                            if ent.get("t") == "CC" and ent.get("tm") == self._my_team:
                                eid = ent.get("id")
                                if eid is not None:
                                    self._selected_ids.add(eid)
                    elif event.key == pygame.K_TAB:
                        # Select all army units
                        self._selected_ids.clear()
                        for ent in self._entities:
                            if ent.get("t") == "U" and ent.get("tm") == self._my_team:
                                eid = ent.get("id")
                                if eid is not None:
                                    self._selected_ids.add(eid)
                    elif event.key == pygame.K_c and mods & pygame.KMOD_CTRL:
                        # Expand selection to all matching unit types
                        sel_types = set()
                        for ent in self._entities:
                            if (ent.get("t") == "U"
                                    and ent.get("id") in self._selected_ids):
                                sel_types.add(ent.get("ut"))
                        if sel_types:
                            for ent in self._entities:
                                if (ent.get("t") == "U"
                                        and ent.get("tm") == self._my_team
                                        and ent.get("ut") in sel_types):
                                    eid = ent.get("id")
                                    if eid is not None:
                                        self._selected_ids.add(eid)
                    elif event.key == pygame.K_s:
                        # Stop selected units
                        stop_ids = [
                            ent.get("id") for ent in self._entities
                            if ent.get("t") == "U"
                            and ent.get("id") in self._selected_ids
                        ]
                        if stop_ids:
                            self._client.send_command(GameCommand(
                                type="stop",
                                player_id=self._my_team,
                                tick=self._tick,
                                data={"unit_ids": stop_ids},
                            ))

                # Header bar interactions (local controls)
                if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                        and self._is_local and self._header_rect.collidepoint(event.pos)):
                    mx_h, my_h = event.pos
                    if self._pause_btn and self._pause_btn.rect.collidepoint(mx_h, my_h):
                        self._toggle_pause()
                    elif self._reset_cam_btn and self._reset_cam_btn.rect.collidepoint(mx_h, my_h):
                        self._camera.reset()

                # Speed slider (local games)
                if self._is_local and self._speed_slider:
                    changed = self._speed_slider.handle_event(event)
                    if changed:
                        speed_pct = self._speed_slider.value
                        self._client.send_command(GameCommand(
                            type="set_speed",
                            player_id=self._my_team,
                            tick=self._tick,
                            data={"speed": speed_pct / 100.0},
                        ))

                # Zoom
                if event.type == pygame.MOUSEWHEEL:
                    mx, my = pygame.mouse.get_pos()
                    if self._game_area.collidepoint(mx, my):
                        vx = mx - self._game_area.x
                        vy = my - self._game_area.y
                        if event.y > 0:
                            self._camera.zoom_at(vx, vy, CAMERA_ZOOM_STEP)
                        elif event.y < 0:
                            self._camera.zoom_at(vx, vy, 1.0 / CAMERA_ZOOM_STEP)

                # Middle mouse pan
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

                # Left click — HUD or selection
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._hud_rect.collidepoint(event.pos):
                        # Minimap click — center camera
                        minimap_world = gui.handle_minimap_click(
                            event.pos[0], event.pos[1],
                            self.width, self.height, self._hud_h,
                            self._map_w, self._map_h,
                        )
                        if minimap_world is not None:
                            self._camera.center_on(*minimap_world)
                            continue
                        self._handle_hud_click(event.pos)
                        # Check if a unit in the group grid was clicked
                        self._handle_display_click(event.pos)
                        continue
                    if self._game_area.collidepoint(event.pos):
                        self._dragging = True
                        self._drag_start = event.pos
                        self._drag_end = event.pos

                elif event.type == pygame.MOUSEMOTION and self._dragging:
                    self._drag_end = event.pos

                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._dragging:
                    self._dragging = False
                    self._handle_selection(event.pos)

                # Right click — movement commands
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    if self._game_area.collidepoint(event.pos):
                        self._rdragging = True
                        wx, wy = self._screen_to_world(event.pos)
                        self._rpath = [(wx, wy)]

                elif event.type == pygame.MOUSEMOTION and self._rdragging:
                    wx, wy = self._screen_to_world(event.pos)
                    if self._rpath:
                        lx, ly = self._rpath[-1]
                        if math.hypot(wx - lx, wy - ly) >= self._PATH_MIN_DIST:
                            self._rpath.append((wx, wy))

                elif event.type == pygame.MOUSEBUTTONUP and event.button == 3 and self._rdragging:
                    self._rdragging = False
                    wx, wy = self._screen_to_world(event.pos)
                    if not self._rpath:
                        self._rpath = [(wx, wy)]
                    elif math.hypot(wx - self._rpath[-1][0], wy - self._rpath[-1][1]) > 1:
                        self._rpath.append((wx, wy))
                    self._send_move_commands()
                    self._rpath = []

            # Edge panning (use screen edges, not game area edges)
            mx, my = pygame.mouse.get_pos()
            dx = dy = 0.0
            if mx <= EDGE_PAN_MARGIN:
                dx = EDGE_PAN_SPEED * dt
            elif mx >= self.width - EDGE_PAN_MARGIN - 1:
                dx = -EDGE_PAN_SPEED * dt
            if my <= EDGE_PAN_MARGIN:
                dy = EDGE_PAN_SPEED * dt
            elif my >= self.height - EDGE_PAN_MARGIN - 1:
                dy = -EDGE_PAN_SPEED * dt
            if dx or dy:
                self._camera.pan(dx, dy)

            self._draw()

    # -- selection ----------------------------------------------------------

    def _handle_selection(self, pos: tuple[int, int]) -> None:
        sx, sy = self._drag_start
        drag_r = math.hypot(pos[0] - sx, pos[1] - sy)
        additive = pygame.key.get_mods() & pygame.KMOD_SHIFT

        if drag_r < 5:
            # Double-click detection
            now = pygame.time.get_ticks()
            is_dblclick = (
                now - self._last_click_time < 400
                and math.hypot(pos[0] - self._last_click_pos[0],
                               pos[1] - self._last_click_pos[1]) < 10
            )
            self._last_click_time = now
            self._last_click_pos = pos

            # Click select
            wx, wy = self._screen_to_world(pos)
            if not additive:
                self._selected_ids.clear()
            best_id = None
            best_dist = float("inf")
            best_ut = None
            for ent in self._entities:
                if ent.get("tm") != self._my_team:
                    continue
                t = ent.get("t")
                if t not in ("U", "CC", "ME"):
                    continue
                ex, ey = ent.get("x", 0), ent.get("y", 0)
                r = ent.get("r", 5)
                d = math.hypot(ex - wx, ey - wy)
                if d <= r + 5 and d < best_dist:
                    best_dist = d
                    best_id = ent.get("id")
                    best_ut = ent.get("ut")
            if best_id is not None:
                self._selected_ids.add(best_id)
                # Double-click: select all visible units of same type
                if is_dblclick and best_ut:
                    for ent in self._entities:
                        if (ent.get("tm") == self._my_team
                                and ent.get("ut") == best_ut
                                and ent.get("t") == "U"):
                            eid = ent.get("id")
                            if eid is not None:
                                self._selected_ids.add(eid)
        else:
            # Drag select — army units take priority over buildings
            if not additive:
                self._selected_ids.clear()
            army_ids: list[int] = []
            building_ids: list[int] = []

            if display_config.selection_mode == "rectangle":
                # Rectangle select: corners are drag_start and release pos
                wx1, wy1 = self._screen_to_world(self._drag_start)
                wx2, wy2 = self._screen_to_world(pos)
                rx = min(wx1, wx2)
                ry = min(wy1, wy2)
                rw = abs(wx2 - wx1)
                rh = abs(wy2 - wy1)
                rcx, rcy = rx + rw / 2, ry + rh / 2
                hw, hh = rw / 2, rh / 2
                for ent in self._entities:
                    if ent.get("tm") != self._my_team:
                        continue
                    t = ent.get("t")
                    if t not in ("U", "CC", "ME"):
                        continue
                    ex, ey = ent.get("x", 0), ent.get("y", 0)
                    er = ent.get("r", 5)
                    if abs(ex - rcx) <= hw + er and abs(ey - rcy) <= hh + er:
                        eid = ent.get("id")
                        if eid is not None:
                            if t == "U":
                                army_ids.append(eid)
                            else:
                                building_ids.append(eid)
            else:
                # Circle select (center = drag start, radius = distance to release)
                ccx, ccy = self._screen_to_world(self._drag_start)
                w_ex, w_ey = self._screen_to_world(pos)
                sr = math.hypot(w_ex - ccx, w_ey - ccy)
                for ent in self._entities:
                    if ent.get("tm") != self._my_team:
                        continue
                    t = ent.get("t")
                    if t not in ("U", "CC", "ME"):
                        continue
                    ex, ey = ent.get("x", 0), ent.get("y", 0)
                    if math.hypot(ex - ccx, ey - ccy) <= sr:
                        eid = ent.get("id")
                        if eid is not None:
                            if t == "U":
                                army_ids.append(eid)
                            else:
                                building_ids.append(eid)

            targets = army_ids if army_ids else building_ids
            for eid in targets:
                self._selected_ids.add(eid)

    # -- HUD interaction ----------------------------------------------------

    def _handle_hud_click(self, pos: tuple[int, int]) -> None:
        proxies = wrap_entities(self._entities, self._selected_ids)
        mx, my = pos
        result = gui.handle_hud_click(
            proxies, mx, my,
            self.width, self.height, self._hud_h,
            enable_t2=self._enable_t2,
            t2_upgrades=self._t2_upgrades,
        )
        if result is None:
            return
        action = result["action"]
        if action == "set_spawn_type":
            self._client.send_command(GameCommand(
                type="set_spawn_type",
                player_id=self._my_team,
                tick=self._tick,
                data={"unit_type": result["unit_type"]},
            ))
        elif action == "stop":
            selected = [
                ent for ent in self._entities
                if ent.get("id") in self._selected_ids and ent.get("t") == "U"
            ]
            if selected:
                self._client.send_command(GameCommand(
                    type="stop",
                    player_id=self._my_team,
                    tick=self._tick,
                    data={"unit_ids": [e["id"] for e in selected]},
                ))
        elif action == "upgrade_extractor":
            self._client.send_command(GameCommand(
                type="upgrade_extractor",
                player_id=self._my_team,
                tick=self._tick,
                data={"entity_id": result["entity_id"], "path": result["path"]},
            ))
        elif action == "set_research_type":
            self._client.send_command(GameCommand(
                type="set_research_type",
                player_id=self._my_team,
                tick=self._tick,
                data={"entity_id": result["entity_id"], "unit_type": result["unit_type"]},
            ))

    # -- commands -----------------------------------------------------------

    def _send_move_commands(self) -> None:
        """Send move commands for selected units to the drawn path."""
        selected = [
            ent for ent in self._entities
            if ent.get("id") in self._selected_ids and ent.get("t") == "U"
        ]
        if not selected or not self._rpath:
            # Check for rally point on selected CC
            if self._rpath:
                rally = self._rpath[-1]
                for ent in self._entities:
                    if (ent.get("id") in self._selected_ids
                            and ent.get("t") == "CC"
                            and ent.get("tm") == self._my_team):
                        self._client.send_command(GameCommand(
                            type="set_rally",
                            player_id=self._my_team,
                            tick=self._tick,
                            data={"position": list(rally)},
                        ))
            return

        # Single point: all units go to same location
        if len(self._rpath) == 1:
            px, py = self._rpath[0]
            unit_ids = [e["id"] for e in selected]
            targets = [(px, py)] * len(unit_ids)
        else:
            # Resample path and assign goals
            goals = self._resample_path(len(selected))
            assigned: set[int] = set()
            unit_ids: list[int] = []
            targets: list[tuple[float, float]] = []
            for gx, gy in goals:
                best_idx = -1
                best_dist = float("inf")
                for i, ent in enumerate(selected):
                    if i in assigned:
                        continue
                    d = math.hypot(ent.get("x", 0) - gx, ent.get("y", 0) - gy)
                    if d < best_dist:
                        best_dist = d
                        best_idx = i
                if best_idx >= 0:
                    unit_ids.append(selected[best_idx]["id"])
                    targets.append((gx, gy))
                    assigned.add(best_idx)

        if unit_ids:
            self._client.send_command(GameCommand(
                type="move",
                player_id=self._my_team,
                tick=self._tick,
                data={"unit_ids": unit_ids, "targets": targets},
            ))

    def _resample_path(self, n: int) -> list[tuple[float, float]]:
        path = self._rpath
        if n <= 0 or len(path) < 2:
            return list(path[:n])
        total = sum(
            math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
            for i in range(1, len(path))
        )
        if total < 1e-6:
            return [path[0]] * n
        if n == 1:
            return [path[len(path) // 2]]
        spacing = total / (n - 1)
        points: list[tuple[float, float]] = [path[0]]
        accumulated = 0.0
        seg = 1
        seg_start = path[0]
        for i in range(1, n - 1):
            target_dist = i * spacing
            while seg < len(path):
                sx, sy = seg_start
                ex, ey = path[seg]
                seg_len = math.hypot(ex - sx, ey - sy)
                if accumulated + seg_len >= target_dist:
                    frac = (target_dist - accumulated) / seg_len if seg_len > 0 else 0
                    points.append((sx + (ex - sx) * frac, sy + (ey - sy) * frac))
                    break
                accumulated += seg_len
                seg_start = path[seg]
                seg += 1
            else:
                points.append(path[-1])
        points.append(path[-1])
        return points

    # -- coordinate helpers -------------------------------------------------

    def _screen_to_world(self, pos: tuple[int, int]) -> tuple[float, float]:
        return self._camera.screen_to_world(
            float(pos[0] - self._game_area.x),
            float(pos[1] - self._game_area.y),
        )

    # -- result -------------------------------------------------------------

    def _build_result(self) -> ScreenResult:
        self._client.stop()
        # Build team_names from player_names / player_team, supporting N teams
        team_names: dict[int, str] = {}
        if self._player_names and self._client.player_team:
            for pid, pname in self._player_names.items():
                tm = self._client.player_team.get(pid, pid)
                team_names[tm] = pname
        if not team_names:
            team_names[self._my_team] = self._client._player_name
            opponent_name = self._client.opponent_name or self._client.host_name
            for t in self._all_teams - {self._my_team}:
                team_names[t] = opponent_name
        return ScreenResult("results", data={
            "winner": self._winner,
            "human_teams": {self._my_team},
            "stats": None,
            "replay_filepath": "",
            "team_names": team_names,
        })

    # -- display click (group grid → center camera) --------------------------

    def _handle_display_click(self, pos: tuple[int, int]) -> None:
        """If a unit box in the group grid was clicked, select only that unit."""
        proxies = wrap_entities(self._entities, self._selected_ids)
        mx, my = pos
        unit = gui.handle_display_click(
            proxies, mx, my,
            self.width, self.height, self._hud_h,
        )
        if unit is not None:
            self._selected_ids.clear()
            self._selected_ids.add(unit.entity_id)

    # -- pause / mouse grab -------------------------------------------------

    def _toggle_pause(self):
        self._paused = not self._paused
        pygame.event.set_grab(not self._paused)
        self._client.send_command(GameCommand(
            type="set_pause",
            player_id=self._my_team,
            tick=self._tick,
            data={"paused": self._paused},
        ))

    # -- sound effects ------------------------------------------------------

    def _play_laser_sounds(self) -> None:
        """Detect new lasers by comparing to previous frame and play sounds."""
        if not self._sounds:
            return
        cur_keys: set[tuple] = set()
        for lf in self._lasers:
            if len(lf) >= 6:
                # Use source position + target position as key
                cur_keys.add((round(lf[0], 0), round(lf[1], 0),
                              round(lf[2], 0), round(lf[3], 0)))
        new_keys = cur_keys - self._prev_laser_keys
        self._prev_laser_keys = cur_keys

        for lf in self._lasers:
            if len(lf) < 6:
                continue
            key = (round(lf[0], 0), round(lf[1], 0),
                   round(lf[2], 0), round(lf[3], 0))
            if key not in new_keys:
                continue
            width = lf[5]
            if width >= 4:
                snd = self._sounds.get("artillery")
            elif width >= 2:
                snd = self._sounds.get("laser")
            else:
                snd = self._sounds.get("fast_laser")
            if snd:
                snd.play()

    # -- animations ---------------------------------------------------------

    def _init_fragments(self, losing_team: int) -> None:
        """Create 6 triangular fragments from each losing CC's hexagon."""
        for ent in self._entities:
            if ent.get("t") != "CC":
                continue
            if ent.get("tm") != losing_team:
                continue
            cx, cy = ent.get("x", 0), ent.get("y", 0)
            color = tuple(ent.get("c", [255, 255, 255]))
            pts = ent.get("pts", [])
            for i in range(len(pts)):
                p1 = pts[i]
                p2 = pts[(i + 1) % len(pts)]
                tri = [(0.0, 0.0), (p1[0], p1[1]), (p2[0], p2[1])]
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

    def _update_fragments(self, dt: float) -> None:
        for frag in self._fragments:
            frag["cx"] += frag["vx"] * dt
            frag["cy"] += frag["vy"] * dt
            frag["angle"] += frag["rot_speed"] * dt

    def _render_warp_in(self, ws: pygame.Surface) -> None:
        """Draw CCs scaled in with glow rings during warp_in phase."""
        t = min(self._anim_timer / 3.0, 1.0)
        scale = t * (2.0 - t)  # ease-out

        for ent in self._entities:
            if ent.get("t") != "CC":
                continue
            cx, cy = ent.get("x", 0), ent.get("y", 0)
            color = tuple(ent.get("c", [255, 255, 255]))
            pts = ent.get("pts", [])
            tm = ent.get("tm", 1)
            if pts:
                scaled = [(cx + px * scale, cy + py * scale) for px, py in pts]
                pygame.draw.polygon(ws, color, scaled)
                outline = TEAM_COLORS.get(tm, PLAYER_COLORS[0])
                pygame.draw.polygon(ws, outline, scaled, 2)

            # Glow ring
            glow_radius = int(CC_RADIUS * 3 * t)
            glow_alpha = int(120 * (1.0 - t))
            if glow_radius > 0 and glow_alpha > 0:
                self._anim_surface.fill((0, 0, 0, 0))
                glow_color = (*color[:3], glow_alpha)
                pygame.draw.circle(self._anim_surface, glow_color,
                                   (int(cx), int(cy)), glow_radius, 3)
                ws.blit(self._anim_surface, (0, 0))

    def _render_explode(self, ws: pygame.Surface) -> None:
        """Draw explosion fragments flying out."""
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

    # -- rendering ----------------------------------------------------------

    def _draw(self) -> None:
        ws = self._world_surface
        ws.fill((0, 0, 0))

        # Obstacles
        for obs in self._obstacles:
            c = tuple(obs.get("c", [120, 120, 120]))
            if obs["shape"] == "rect":
                x, y, w, h = obs["x"], obs["y"], obs["w"], obs["h"]
                pygame.draw.rect(ws, c, (x, y, w, h))
                pygame.draw.rect(ws, OBSTACLE_OUTLINE, (x, y, w, h), 1)
            elif obs["shape"] == "circle":
                cx, cy, r = int(obs["x"]), int(obs["y"]), int(obs["r"])
                pygame.draw.circle(ws, c, (cx, cy), r)
                pygame.draw.circle(ws, OBSTACLE_OUTLINE, (cx, cy), r, 1)

        # Sort entities by type for layering
        order = {"MS": 0, "ME": 1, "CC": 2, "U": 3}
        entities = sorted(self._entities,
                          key=lambda e: order.get(e.get("t", ""), 4))

        is_warp_in = self._phase == "warp_in"
        for ent in entities:
            t = ent.get("t")
            if t == "MS":
                self._draw_metal_spot(ent)
            elif t == "ME":
                self._draw_metal_extractor(ent)
            elif t == "CC":
                if not is_warp_in:
                    self._draw_command_center(ent)
            elif t == "U":
                if not is_warp_in:
                    self._draw_unit(ent)

        # Warp-in animation overlays CCs with scale + glow
        if is_warp_in:
            self._render_warp_in(ws)

        # Selection rings + FOV arcs
        for ent in entities:
            eid = ent.get("id")
            if eid in self._selected_ids:
                t = ent.get("t")
                ex = ent.get("x", 0)
                ey = ent.get("y", 0)
                r = CC_RADIUS + 2 if t == "CC" else ent.get("r", 5) + 2
                pygame.draw.circle(ws, SELECTED_COLOR, (int(ex), int(ey)), int(r), 1)
                self._draw_fov_arc(ent)

        # Lasers
        for lf in self._lasers:
            self._draw_laser(lf)

        # Charge beams (artillery charge preview)
        for ent in entities:
            chx = ent.get("chx")
            if chx is not None:
                chy = ent.get("chy", 0)
                chp = ent.get("chp", 0)
                ex, ey = ent.get("x", 0), ent.get("y", 0)
                orange = (255, 140, 0, int(100 + 100 * chp))
                temp = pygame.Surface(ws.get_size(), pygame.SRCALPHA)
                pygame.draw.line(temp, orange, (int(ex), int(ey)),
                                 (int(chx), int(chy)), 2)
                # Splash ring at target
                splash_r = int(30 * chp)
                if splash_r > 0:
                    pygame.draw.circle(temp, (255, 100, 0, int(60 * chp)),
                                       (int(chx), int(chy)), splash_r, 1)
                ws.blit(temp, (0, 0))

        # Splash effects (expanding red circles)
        for s in self._splashes:
            sx, sy = s.get("x", 0), s.get("y", 0)
            sr = s.get("r", 30)
            sp = s.get("p", 0)
            cur_r = int(sr * sp)
            alpha = int(180 * (1.0 - sp))
            if cur_r > 0 and alpha > 0:
                temp = pygame.Surface(ws.get_size(), pygame.SRCALPHA)
                pygame.draw.circle(temp, (255, 60, 30, alpha),
                                   (int(sx), int(sy)), cur_r, 2)
                ws.blit(temp, (0, 0))

        # ME spawn bonus labels (white, above extractor — matching game.py)
        for ent in entities:
            if ent.get("t") == "ME":
                meb = ent.get("meb", 0)
                if meb > 0:
                    label = _get_font(14).render(f"+{meb}%", True, (255, 255, 255))
                    lx = int(ent.get("x", 0)) - label.get_width() // 2
                    ly = int(ent.get("y", 0)) - int(ent.get("r", 10)) - HEALTH_BAR_OFFSET - 12
                    ws.blit(label, (lx, ly))

        # Team labels
        self._draw_team_labels(entities)

        # Drag selection visual
        if self._dragging:
            sx, sy = self._drag_start
            ex, ey = self._drag_end
            screen_r = math.hypot(ex - sx, ey - sy)
            if screen_r >= 5:
                self._selection_surface.fill((0, 0, 0, 0))
                if display_config.selection_mode == "rectangle":
                    wcx1, wcy1 = self._screen_to_world(self._drag_start)
                    wcx2, wcy2 = self._screen_to_world(self._drag_end)
                    rx = min(wcx1, wcx2)
                    ry = min(wcy1, wcy2)
                    rw = abs(wcx2 - wcx1)
                    rh = abs(wcy2 - wcy1)
                    rect = pygame.Rect(int(rx), int(ry), int(rw), int(rh))
                    pygame.draw.rect(self._selection_surface, SELECTION_FILL_COLOR, rect)
                    pygame.draw.rect(self._selection_surface, SELECTION_RECT_COLOR, rect, 1)
                else:
                    wcx, wcy = self._screen_to_world(self._drag_start)
                    w_ex, w_ey = self._screen_to_world(self._drag_end)
                    wr = math.hypot(w_ex - wcx, w_ey - wcy)
                    pygame.draw.circle(self._selection_surface, SELECTION_FILL_COLOR,
                                       (int(wcx), int(wcy)), int(wr))
                    pygame.draw.circle(self._selection_surface, SELECTION_RECT_COLOR,
                                       (int(wcx), int(wcy)), int(wr), 1)
                ws.blit(self._selection_surface, (0, 0))

        # Right-click path with unit-count dots
        if self._rdragging and len(self._rpath) > 1:
            path_color = (0, 200, 60)
            for i in range(1, len(self._rpath)):
                ax, ay = self._rpath[i - 1]
                bx, by = self._rpath[i]
                pygame.draw.line(ws, path_color, (ax, ay), (bx, by), 1)
            selected_count = sum(
                1 for e in self._entities
                if e.get("id") in self._selected_ids and e.get("t") == "U"
            )
            if selected_count > 0:
                preview = self._resample_path(selected_count)
                for px, py in preview:
                    pygame.draw.circle(ws, path_color, (int(px), int(py)), 3)

        # Fog of war
        self._draw_fog(entities)

        # Explosion fragments overlay
        if self._phase == "explode":
            self._render_explode(ws)

        # -- Composite to screen --
        self.screen.fill((0, 0, 0))

        # Header bar
        pygame.draw.rect(self.screen, (20, 20, 30), self._header_rect)
        pygame.draw.line(self.screen, (40, 40, 55),
                         (0, self._header_h - 1),
                         (self.width, self._header_h - 1))

        # Header content
        font = _get_font(22)

        # Team indicator
        team_color = TEAM_COLORS.get(self._my_team, PLAYER_COLORS[0])
        team_label = font.render(f"Team {self._my_team}", True, team_color)
        self.screen.blit(team_label, (10, 10))

        # Game time (centered)
        m, s = divmod(self._tick // 60, 60)
        timer = font.render(f"{m}:{s:02d}", True, _STATUS_COLOR)
        self.screen.blit(timer, (self.width // 2 - timer.get_width() // 2, 10))

        # Disconnect warning (suppress for local games)
        if self._disconnect_timer > 3.0 and not self._is_local:
            warn = font.render("Connection lost...", True, _DISCONNECT_COLOR)
            self.screen.blit(warn, (self.width - warn.get_width() - 10, 10))

        # FPS
        fps_font = _get_font(18)
        fps_val = self.clock.get_fps()
        fps_surf = fps_font.render(f"FPS: {fps_val:.0f}", True, (200, 200, 200))
        self.screen.blit(fps_surf, (team_label.get_width() + 20, 12))

        # Local game controls in header
        if self._is_local:
            if self._speed_slider:
                self._speed_slider.draw(self.screen)
            if self._pause_btn:
                self._pause_btn.draw(self.screen)
            if self._reset_cam_btn:
                self._reset_cam_btn.draw(self.screen)

        # Game area: black background then camera projection
        ga = self._game_area
        pygame.draw.rect(self.screen, (0, 0, 0), ga)
        self._camera.apply(ws, self.screen, dest=(ga.x, ga.y))

        # Metallic border around the world edge (rendered in screen space)
        bx0, by0 = self._camera.world_to_screen(0, 0)
        bx1, by1 = self._camera.world_to_screen(self._map_w, self._map_h)
        border_rect = pygame.Rect(
            int(bx0) + ga.x, int(by0) + ga.y,
            int(bx1 - bx0), int(by1 - by0),
        )
        clip_save = self.screen.get_clip()
        self.screen.set_clip(ga)
        _draw_metallic_border(self.screen, border_rect, 3)
        self.screen.set_clip(clip_save)

        # HUD area
        pygame.draw.rect(self.screen, (20, 20, 30), self._hud_rect)
        pygame.draw.line(self.screen, (40, 40, 55),
                         (0, self._hud_rect.top),
                         (self.width, self._hud_rect.top))
        self._draw_hud()

        # Winner overlay
        if self._winner:
            big_font = pygame.font.SysFont(None, 64)
            if self._winner == self._my_team:
                text = "VICTORY!"
                color = (100, 255, 140)
            else:
                text = "DEFEAT"
                color = (255, 100, 100)
            surf = big_font.render(text, True, color)
            self.screen.blit(surf, (self.width // 2 - surf.get_width() // 2,
                                    self.height // 2 - surf.get_height() // 2))

        # PAUSED overlay (local games)
        if self._paused and self._is_local and self._pause_font:
            pause_surf = self._pause_font.render("PAUSED", True, (255, 255, 255))
            px = self.width // 2 - pause_surf.get_width() // 2
            py = self.height // 2 - pause_surf.get_height() // 2
            self.screen.blit(pause_surf, (px, py))

        pygame.display.flip()

    # -- HUD drawing (delegated to gui.py via adapter) -----------------------

    def _draw_hud(self) -> None:
        """Draw the full HUD bar using gui.py through adapter proxies."""
        proxies = wrap_entities(self._entities, self._selected_ids)
        gui.draw_hud(
            self.screen, proxies,
            self.width, self.height, self._hud_h,
            enable_t2=self._enable_t2,
            t2_upgrades=self._t2_upgrades,
            camera=self._camera,
            world_w=self._map_w,
            world_h=self._map_h,
            obstacles=self._obstacles,
        )

    # -- entity drawing (adapted from ReplayPlaybackScreen) -----------------

    def _draw_command_line(self, x1: float, y1: float, x2: float, y2: float,
                           color: tuple) -> None:
        """Draw a command line with arrowhead from (x1,y1) to (x2,y2)."""
        ws = self._world_surface
        pygame.draw.line(ws, color, (x1, y1), (x2, y2), 1)
        dx = x2 - x1
        dy = y2 - y1
        dist = math.hypot(dx, dy)
        if dist < 1:
            return
        ux, uy = dx / dist, dy / dist
        px, py = -uy, ux
        s = _ARROW_SIZE
        wing1 = (x2 - ux * s + px * s * 0.5, y2 - uy * s + py * s * 0.5)
        wing2 = (x2 - ux * s - px * s * 0.5, y2 - uy * s - py * s * 0.5)
        pygame.draw.polygon(ws, color, [(x2, y2), wing1, wing2])

    def _draw_fov_arc(self, ent: dict) -> None:
        """Draw FOV/range arc for a selected unit."""
        t = ent.get("t")
        ut = ent.get("ut", "soldier")
        stats = UNIT_TYPES.get(ut, {})
        fov_deg = stats.get("fov", 90)
        fov = math.radians(fov_deg)

        ws = self._world_surface
        ex = ent.get("x", 0)
        ey = ent.get("y", 0)

        # CC: show attack range circle
        if t == "CC":
            atk_r = int(CC_LASER_RANGE)
            temp = pygame.Surface((atk_r * 2, atk_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(temp, RANGE_COLOR, (atk_r, atk_r), atk_r, 1)
            ws.blit(temp, (int(ex) - atk_r, int(ey) - atk_r))
            return

        if t == "ME":
            return

        weapon = stats.get("weapon")
        if not weapon:
            return
        r = int(weapon.get("range", 50))
        if r <= 0:
            return
        is_healer = weapon.get("hits_only_friendly", False)
        color = MEDIC_HEAL_COLOR if is_healer else RANGE_COLOR
        fa = ent.get("fa", 0.0)

        half_fov = fov / 2.0
        if fov >= math.tau - 0.01:
            temp = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(temp, color, (r, r), r, 1)
            ws.blit(temp, (int(ex) - r, int(ey) - r))
            return

        start = fa - half_fov
        steps = max(int(math.degrees(fov) / 3), 8)
        points = [(ex, ey)]
        for i in range(steps + 1):
            a = start + fov * i / steps
            points.append((ex + r * math.cos(a), ey + r * math.sin(a)))
        points.append((ex, ey))

        temp_size = r * 2 + 4
        temp = pygame.Surface((temp_size, temp_size), pygame.SRCALPHA)
        ox = temp_size // 2 - ex
        oy = temp_size // 2 - ey
        shifted = [(px + ox, py + oy) for px, py in points]
        pygame.draw.lines(temp, color, False, shifted, 1)
        ws.blit(temp, (ex - temp_size // 2, ey - temp_size // 2))

    def _draw_unit(self, ent: dict) -> None:
        ws = self._world_surface
        x, y = ent.get("x", 0), ent.get("y", 0)
        c = tuple(ent.get("c", [255, 255, 255]))
        r = ent.get("r", 5)
        hp = ent.get("hp", 100)
        ut = ent.get("ut", "soldier")

        # Command arrows for selected units
        eid = ent.get("id")
        if eid in self._selected_ids:
            if "atx" in ent and "aty" in ent:
                self._draw_command_line(x, y, ent["atx"], ent["aty"], _ATTACK_CMD_COLOR)
            elif "tx" in ent and "ty" in ent:
                self._draw_command_line(x, y, ent["tx"], ent["ty"], _MOVE_CMD_COLOR)

        pygame.draw.circle(ws, c, (x, y), r)

        stats = UNIT_TYPES.get(ut, {})
        symbol = stats.get("symbol")
        if symbol:
            scale = r / 16.0
            translated = [(x + px * scale, y + py * scale) for px, py in symbol]
            pygame.draw.polygon(ws, (0, 0, 0), translated)
            pygame.draw.polygon(ws, c, translated, 1)

        max_hp = ent.get("mhp", stats.get("hp", 100))
        if hp < max_hp:
            self._draw_health_bar(x, y, r + HEALTH_BAR_OFFSET, hp, max_hp)

        # Ability indicators above unit
        _ABILITY_COLORS = {
            "reactive_armor": REACTIVE_ARMOR_COLOR,
            "electric_armor": ELECTRIC_ARMOR_COLOR,
        }
        for ab in ent.get("abs", []):
            ab_name = ab.get("n", "")
            # Stack-based abilities: diamond indicators
            stacks = ab.get("s", 0)
            if stacks > 0 and ab_name in _ABILITY_COLORS:
                color = _ABILITY_COLORS[ab_name]
                size = 2 if ab_name == "electric_armor" else 3
                spacing = 5 if ab_name == "electric_armor" else 6
                y_off = r + 6
                start_x = x - (stacks - 1) * spacing / 2
                for i in range(stacks):
                    cx = start_x + i * spacing
                    cy = y - y_off
                    pts = [
                        (cx, cy - size),
                        (cx + size, cy),
                        (cx, cy + size),
                        (cx - size, cy),
                    ]
                    pygame.draw.polygon(ws, color, pts)
            # Combat stim: green chevron when active
            elif ab_name == "combat_stim" and ab.get("a", False):
                cy = y - r - 6
                size = 3
                pts = [(x - size, cy + size), (x, cy - size), (x + size, cy + size)]
                pygame.draw.lines(ws, (100, 255, 100), False, pts, 2)

    def _draw_command_center(self, ent: dict) -> None:
        ws = self._world_surface
        x, y = ent.get("x", 0), ent.get("y", 0)
        c = tuple(ent.get("c", [255, 255, 255]))
        pts = ent.get("pts", [])
        tm = ent.get("tm", 1)
        hp = ent.get("hp", 1000)

        if pts:
            translated = [(x + px, y + py) for px, py in pts]
            pygame.draw.polygon(ws, c, translated)
            outline = TEAM_COLORS.get(tm, PLAYER_COLORS[0])
            pygame.draw.polygon(ws, outline, translated, 2)

        # Spawn progress arc
        spt = ent.get("spt", 0.0)
        arc_r = CC_RADIUS + 5
        if spt < 1.0:
            start_angle = math.pi / 2
            end_angle = start_angle + spt * math.tau
            rect = pygame.Rect(x - arc_r, y - arc_r, arc_r * 2, arc_r * 2)
            pygame.draw.arc(ws, SELECTED_COLOR, rect, start_angle, end_angle, 2)
        else:
            pygame.draw.circle(ws, SELECTED_COLOR, (int(x), int(y)), int(arc_r), 2)

        # Rally point line + flag (only when selected)
        rx = ent.get("rx")
        if rx is not None and ent.get("id") in self._selected_ids:
            ry = ent.get("ry", 0)
            pygame.draw.line(ws, c, (x, y), (rx, ry), 1)
            pygame.draw.line(ws, (200, 200, 200), (rx, ry), (rx, ry - 14), 1)
            flag_pts = [(rx, ry - 14), (rx + 8, ry - 10), (rx, ry - 6)]
            pygame.draw.polygon(ws, c, flag_pts)
            pygame.draw.circle(ws, c, (int(rx), int(ry)), 3, 1)

        if hp < CC_HP:
            self._draw_health_bar(x, y, CC_RADIUS + HEALTH_BAR_OFFSET,
                                  hp, CC_HP, bar_w=40)

    def _draw_metal_spot(self, ent: dict) -> None:
        ws = self._world_surface
        x, y = ent.get("x", 0), ent.get("y", 0)
        r = ent.get("r", 5)
        ow = ent.get("ow")
        cp = ent.get("cp", 0.0)

        cr = int(METAL_SPOT_CAPTURE_RADIUS)
        size = cr * 2
        temp = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(temp, METAL_SPOT_CAPTURE_RANGE_COLOR, (cr, cr), cr)
        ws.blit(temp, (int(x) - cr, int(y) - cr))

        if ow is None:
            color = (255, 200, 60)
        else:
            color = TEAM_COLORS.get(ow, PLAYER_COLORS[0])
        pygame.draw.circle(ws, color, (int(x), int(y)), int(r))

        cp_dict = normalize_cp(cp)
        if ow is None and cp_dict:
            arc_r = METAL_SPOT_CAPTURE_RADIUS + METAL_SPOT_CAPTURE_ARC_WIDTH
            rect = pygame.Rect(int(x - arc_r), int(y - arc_r),
                               int(arc_r * 2), int(arc_r * 2))
            start_angle = math.pi / 2
            for team_id, progress in cp_dict.items():
                if progress < 0.01:
                    continue
                progress_color = TEAM_COLORS.get(team_id, PLAYER_COLORS[0])
                end_angle = start_angle + progress * math.tau
                pygame.draw.arc(ws, progress_color, rect,
                                start_angle, end_angle,
                                int(METAL_SPOT_CAPTURE_ARC_WIDTH))

    def _draw_metal_extractor(self, ent: dict) -> None:
        ws = self._world_surface
        x, y = ent.get("x", 0), ent.get("y", 0)
        r = ent.get("r", METAL_EXTRACTOR_RADIUS)
        rot = ent.get("rot", 0.0)
        hp = ent.get("hp", 200)
        tm = ent.get("tm", 1)

        s = r * math.sqrt(3) / 2
        static_points = [
            complex(0, r),
            complex(-s, -r / 2),
            complex(s, -r / 2),
        ]
        rotated = [p * complex(math.cos(rot), math.sin(rot)) for p in static_points]
        points = [(p.real + x, p.imag + y) for p in rotated]
        pygame.draw.polygon(ws, (0, 0, 0), points, 1)

        # Reinforcement plating arcs
        rst = ent.get("rst", 0)
        if rst > 0:
            arc_color = TEAM_COLORS.get(tm, PLAYER_COLORS[0])
            arc_r = METAL_SPOT_CAPTURE_RADIUS
            rect = pygame.Rect(x - arc_r, y - arc_r, arc_r * 2, arc_r * 2)
            arc_span = math.radians(87.5)
            half_span = arc_span / 2
            cardinal_angles = [
                math.radians(90),    # N
                math.radians(0),     # E
                math.radians(270),   # S
                math.radians(180),   # W
            ]
            for i in range(min(rst, 4)):
                center = cardinal_angles[i]
                start = center - half_span
                end = center + half_span
                pygame.draw.arc(ws, arc_color, rect, start, end, 2)

        max_hp = ent.get("mhp", METAL_EXTRACTOR_HP)
        if hp < max_hp:
            self._draw_health_bar(x, y, r + HEALTH_BAR_OFFSET,
                                  hp, max_hp)

    def _draw_laser(self, lf: list) -> None:
        if len(lf) < 6:
            return
        ws = self._world_surface
        x1, y1, x2, y2 = lf[0], lf[1], lf[2], lf[3]
        color = tuple(lf[4])
        width = lf[5]
        temp = pygame.Surface(ws.get_size(), pygame.SRCALPHA)
        c = (*color[:3], 200)
        pygame.draw.line(temp, c, (x1, y1), (x2, y2), width)
        ws.blit(temp, (0, 0))

    def _draw_health_bar(self, cx: float, cy: float, offset_y: float,
                         hp: float, max_hp: float,
                         bar_w: float = HEALTH_BAR_WIDTH) -> None:
        ws = self._world_surface
        ratio = hp / max_hp if max_hp > 0 else 0
        bx = cx - bar_w / 2
        by = cy - offset_y
        pygame.draw.rect(ws, HEALTH_BAR_BG,
                         (bx, by, bar_w, HEALTH_BAR_HEIGHT))
        fg = HEALTH_BAR_FG if ratio > 0.35 else HEALTH_BAR_LOW
        pygame.draw.rect(ws, fg,
                         (bx, by, bar_w * ratio, HEALTH_BAR_HEIGHT))

    def _draw_team_labels(self, entities: list[dict]) -> None:
        font = _get_font(20)
        ws = self._world_surface
        # Use enriched player_names from game_start, fallback to client/host names
        names: dict[int, str] = {}
        if self._player_names:
            # Build team→name mapping
            pt = self._client.player_team
            for pid, pname in self._player_names.items():
                tm = pt.get(pid, pid)
                names[tm] = pname
        if not names:
            names[self._my_team] = self._client._player_name
            opponent_name = self._client.opponent_name or self._client.host_name
            for t in self._all_teams - {self._my_team}:
                names[t] = opponent_name
        for ent in entities:
            if ent.get("t") != "CC":
                continue
            tm = ent.get("tm", 1)
            name = names.get(tm, f"Team {tm}")
            # Append bonus % to name (matching game.py)
            bp = ent.get("bp", 0)
            if bp > 0:
                name = f"{name} (+{bp}%)"
            team_color = TEAM_COLORS.get(tm, PLAYER_COLORS[0])
            name_surf = font.render(name, True, team_color)
            nx = int(ent.get("x", 0)) - name_surf.get_width() // 2
            ny = int(ent.get("y", 0)) - 40
            ws.blit(name_surf, (nx, ny))

    def _draw_fog(self, entities: list[dict]) -> None:
        """Draw fog of war — only show own team's vision."""
        FOG_ALPHA = 200
        self._fog_surface.fill((0, 0, 0, FOG_ALPHA))

        los_circles: list[tuple[int, int, int]] = []
        for ent in entities:
            t = ent.get("t")
            if t not in ("U", "CC", "ME"):
                continue
            if ent.get("tm") != self._my_team:
                continue
            ut = ent.get("ut", "soldier")
            stats = UNIT_TYPES.get(ut, {})
            los = int(stats.get("los", 100))
            if los <= 0:
                continue
            los_circles.append((int(ent.get("x", 0)), int(ent.get("y", 0)), los))

        for ex, ey, r in los_circles:
            size = r * 2
            cutout = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(cutout, (0, 0, 0, FOG_ALPHA), (r, r), r)
            self._fog_surface.blit(cutout, (ex - r, ey - r),
                                   special_flags=pygame.BLEND_RGBA_SUB)

        ws = self._world_surface
        ws.blit(self._fog_surface, (0, 0))

        self._fog_border.fill((0, 0, 0))
        for ex, ey, r in los_circles:
            pygame.draw.circle(self._fog_border, (160, 160, 160), (ex, ey), r)
        for ex, ey, r in los_circles:
            pygame.draw.circle(self._fog_border, (0, 0, 0), (ex, ey), max(r - 1, 0))
        ws.blit(self._fog_border, (0, 0))
