"""Client-side game screen — thin renderer that receives state from host."""
from __future__ import annotations

import math
import pygame
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
    TEAM1_COLOR, TEAM2_COLOR, TEAM_COLORS,
    CAMERA_ZOOM_STEP, CAMERA_MAX_ZOOM,
    EDGE_PAN_MARGIN, EDGE_PAN_SPEED,
    GUI_BORDER, GUI_BTN_SELECTED, GUI_BTN_HOVER, GUI_BTN_NORMAL,
    GUI_TEXT_COLOR,
)
from core.camera import Camera
from config.unit_types import UNIT_TYPES, get_spawnable_types
from ui.widgets import _get_font

_STATUS_COLOR = (180, 180, 200)
_DISCONNECT_COLOR = (255, 100, 100)

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
    ):
        super().__init__(screen, clock)
        self._client = client
        self._my_team: int = client.client_team
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
        self._PATH_MIN_DIST = 10.0

        # Selection surface for circle draw
        self._selection_surface = pygame.Surface((mw, mh), pygame.SRCALPHA)

        # Fog surfaces
        self._fog_surface = pygame.Surface((mw, mh), pygame.SRCALPHA)
        self._fog_border = pygame.Surface((mw, mh))
        self._fog_border.set_colorkey((0, 0, 0))

        # Disconnect tracking
        self._disconnect_timer: float = 0.0

        # HUD build button rects (cached)
        self._build_btns = self._compute_build_btn_rects()

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
        while True:
            dt = self.clock.tick(60) / 1000.0

            # Poll for new state from host
            frame = self._client.poll_state()
            if frame:
                msg_type = frame.get("msg")
                if msg_type == "state":
                    self._entities = frame.get("entities", [])
                    self._lasers = frame.get("lasers", [])
                    self._tick = frame.get("tick", 0)
                    self._winner = frame.get("winner", 0)
                    self._disconnect_timer = 0.0
                elif msg_type == "game_over":
                    self._winner = frame.get("winner", 0)
            else:
                self._disconnect_timer += dt

            # Check for disconnect or game over
            if self._client.error:
                return self._build_result()
            if self._winner != 0:
                # Show result briefly then return
                self._draw()
                pygame.time.wait(2000)
                return self._build_result()

            # Handle input
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._client.stop()
                    return ScreenResult("quit")

                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self._client.stop()
                    return ScreenResult("main_menu")

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
                        self._handle_hud_click(event.pos)
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

            # Edge panning
            mx, my = pygame.mouse.get_pos()
            ga = self._game_area
            if ga.collidepoint(mx, my):
                dx = dy = 0.0
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

            self._draw()

    # -- selection ----------------------------------------------------------

    def _handle_selection(self, pos: tuple[int, int]) -> None:
        sx, sy = self._drag_start
        drag_r = math.hypot(pos[0] - sx, pos[1] - sy)
        additive = pygame.key.get_mods() & pygame.KMOD_SHIFT

        if drag_r < 5:
            # Click select
            wx, wy = self._screen_to_world(pos)
            if not additive:
                self._selected_ids.clear()
            best_id = None
            best_dist = float("inf")
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
            if best_id is not None:
                self._selected_ids.add(best_id)
        else:
            # Circle select
            if not additive:
                self._selected_ids.clear()
            w_sx, w_sy = self._screen_to_world(self._drag_start)
            w_ex, w_ey = self._screen_to_world(pos)
            ccx = (w_sx + w_ex) / 2.0
            ccy = (w_sy + w_ey) / 2.0
            sr = math.hypot(w_ex - w_sx, w_ey - w_sy) / 2.0
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
                        self._selected_ids.add(eid)

    # -- HUD interaction ----------------------------------------------------

    def _get_selected_cc(self) -> dict | None:
        for ent in self._entities:
            if ent.get("t") == "CC" and ent.get("id") in self._selected_ids:
                return ent
        return None

    def _handle_hud_click(self, pos: tuple[int, int]) -> None:
        cc = self._get_selected_cc()
        if cc is None or cc.get("tm") != self._my_team:
            return
        mx, my = pos
        for br, ut in self._build_btns:
            if br.collidepoint(mx, my):
                self._client.send_command(GameCommand(
                    type="set_spawn_type",
                    team=self._my_team,
                    tick=self._tick,
                    data={"team": self._my_team, "unit_type": ut},
                ))
                return

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
        return ScreenResult("results", data={
            "winner": self._winner,
            "human_teams": {self._my_team},
            "stats": None,
            "replay_filepath": "",
            "team_names": {
                self._my_team: self._client._player_name,
                3 - self._my_team: self._client.host_name,
            },
        })

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

        for ent in entities:
            t = ent.get("t")
            if t == "MS":
                self._draw_metal_spot(ent)
            elif t == "ME":
                self._draw_metal_extractor(ent)
            elif t == "CC":
                self._draw_command_center(ent)
            elif t == "U":
                self._draw_unit(ent)

        # Selection rings
        for ent in entities:
            eid = ent.get("id")
            if eid in self._selected_ids:
                t = ent.get("t")
                ex = ent.get("x", 0)
                ey = ent.get("y", 0)
                r = CC_RADIUS + 2 if t == "CC" else ent.get("r", 5) + 2
                pygame.draw.circle(ws, SELECTED_COLOR, (int(ex), int(ey)), int(r), 1)

        # Lasers
        for lf in self._lasers:
            self._draw_laser(lf)

        # Team labels
        self._draw_team_labels(entities)

        # Drag selection circle
        if self._dragging:
            sx, sy = self._drag_start
            ex, ey = self._drag_end
            screen_r = math.hypot(ex - sx, ey - sy) / 2.0
            if screen_r >= 5:
                w_sx, w_sy = self._screen_to_world(self._drag_start)
                w_ex, w_ey = self._screen_to_world(self._drag_end)
                wcx = (w_sx + w_ex) / 2.0
                wcy = (w_sy + w_ey) / 2.0
                wr = math.hypot(w_ex - w_sx, w_ey - w_sy) / 2.0
                self._selection_surface.fill((0, 0, 0, 0))
                pygame.draw.circle(self._selection_surface, SELECTION_FILL_COLOR,
                                   (int(wcx), int(wcy)), int(wr))
                pygame.draw.circle(self._selection_surface, SELECTION_RECT_COLOR,
                                   (int(wcx), int(wcy)), int(wr), 1)
                ws.blit(self._selection_surface, (0, 0))

        # Right-click path
        if self._rdragging and len(self._rpath) > 1:
            for i in range(1, len(self._rpath)):
                ax, ay = self._rpath[i - 1]
                bx, by = self._rpath[i]
                pygame.draw.line(ws, (0, 200, 60), (ax, ay), (bx, by), 1)

        # Fog of war
        self._draw_fog(entities)

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
        team_color = TEAM1_COLOR if self._my_team == 1 else TEAM2_COLOR
        team_label = font.render(f"Team {self._my_team}", True, team_color)
        self.screen.blit(team_label, (10, 10))

        # Game time (centered)
        m, s = divmod(self._tick // 60, 60)
        timer = font.render(f"{m}:{s:02d}", True, _STATUS_COLOR)
        self.screen.blit(timer, (self.width // 2 - timer.get_width() // 2, 10))

        # Disconnect warning
        if self._disconnect_timer > 3.0:
            warn = font.render("Connection lost...", True, _DISCONNECT_COLOR)
            self.screen.blit(warn, (self.width - warn.get_width() - 10, 10))

        # FPS
        fps_font = _get_font(18)
        fps_val = self.clock.get_fps()
        fps_surf = fps_font.render(f"FPS: {fps_val:.0f}", True, (200, 200, 200))
        self.screen.blit(fps_surf, (team_label.get_width() + 20, 12))

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

        pygame.display.flip()

    # -- HUD drawing --------------------------------------------------------

    def _draw_hud(self) -> None:
        """Draw the HUD panel at the bottom of the screen."""
        cc = self._get_selected_cc()
        selected_units = [
            ent for ent in self._entities
            if ent.get("id") in self._selected_ids and ent.get("t") == "U"
        ]

        # Action panel (rightmost section)
        action_w = max(220, int(self.width * 0.20))
        ar = pygame.Rect(self.width - action_w, self.height - self._hud_h,
                         action_w, self._hud_h)
        pygame.draw.rect(self.screen, _SECTION_BG, ar)
        pygame.draw.line(self.screen, _DIVIDER,
                         (ar.left, ar.top), (ar.left, ar.bottom))

        tf = _get_font(18)
        mx, my = pygame.mouse.get_pos()

        if cc is not None and cc.get("tm") == self._my_team:
            # Build options for CC
            ts = tf.render("Build", True, _TITLE_COLOR)
            self.screen.blit(ts, (ar.left + 8, ar.top + 6))

            current_spawn = cc.get("st", "soldier")
            for br, ut in self._build_btns:
                is_sel = current_spawn == ut
                is_hov = br.collidepoint(mx, my)
                bg = (GUI_BTN_SELECTED if is_sel
                      else GUI_BTN_HOVER if is_hov
                      else GUI_BTN_NORMAL)

                pygame.draw.rect(self.screen, bg, br, border_radius=4)
                pygame.draw.rect(self.screen, GUI_BORDER, br, 1, border_radius=4)

                st = UNIT_TYPES.get(ut, {})
                sym = st.get("symbol")
                cx, cy = br.centerx, br.centery
                my_color = TEAM1_COLOR if self._my_team == 1 else TEAM2_COLOR
                highlight = (150, 220, 255) if self._my_team == 1 else (255, 140, 140)
                if sym is not None:
                    sc = 0.9
                    pts = [(cx + px * sc, cy + py * sc) for px, py in sym]
                    pygame.draw.polygon(self.screen, my_color, pts)
                    pygame.draw.polygon(self.screen, highlight, pts, 1)
                else:
                    pygame.draw.circle(self.screen, my_color, (cx, cy), 7)
                    pygame.draw.circle(self.screen, highlight, (cx, cy), 7, 1)

            # Tooltip for hovered button
            for br, ut in self._build_btns:
                if br.collidepoint(mx, my):
                    self._draw_tooltip(ut, ar)
                    break
        elif selected_units:
            ts = tf.render("Actions", True, _TITLE_COLOR)
            self.screen.blit(ts, (ar.left + 8, ar.top + 6))

        # Display panel (left of action panel) — show selected unit info
        display_rect = pygame.Rect(0, self.height - self._hud_h,
                                   self.width - action_w, self._hud_h)
        pygame.draw.rect(self.screen, _SECTION_BG, display_rect)

        if selected_units:
            self._draw_unit_info(display_rect, selected_units)
        elif cc is not None and cc.get("tm") == self._my_team:
            self._draw_cc_info(display_rect, cc)

    def _draw_unit_info(self, r: pygame.Rect, units: list[dict]) -> None:
        """Show selected unit info in the display panel."""
        pad = 8
        tf = _get_font(18)
        sf = _get_font(16)

        if len(units) == 1:
            ent = units[0]
            ut = ent.get("ut", "soldier")
            hp = ent.get("hp", 100)
            stats = UNIT_TYPES.get(ut, {})
            max_hp = stats.get("hp", 100)
            name = ut.replace("_", " ").title()

            y = r.top + pad
            ns = tf.render(name, True, _TITLE_COLOR)
            self.screen.blit(ns, (r.left + pad, y))
            y += ns.get_height() + 4

            # HP bar
            bw = min(r.width - pad * 2, 150)
            bh = 6
            ratio = hp / max_hp if max_hp > 0 else 0
            pygame.draw.rect(self.screen, HEALTH_BAR_BG, (r.left + pad, y, bw, bh))
            fg = HEALTH_BAR_FG if ratio > 0.35 else HEALTH_BAR_LOW
            pygame.draw.rect(self.screen, fg, (r.left + pad, y, int(bw * ratio), bh))
            ht = sf.render(f"{int(hp)}/{int(max_hp)}", True, (200, 200, 220))
            self.screen.blit(ht, (r.left + pad + bw + 6, y - 2))
        else:
            # Group count
            count_text = tf.render(f"{len(units)} units selected", True, _TITLE_COLOR)
            self.screen.blit(count_text, (r.left + pad, r.top + pad))

            # Type breakdown
            type_counts: dict[str, int] = {}
            for ent in units:
                ut = ent.get("ut", "soldier")
                type_counts[ut] = type_counts.get(ut, 0) + 1
            y = r.top + pad + count_text.get_height() + 4
            for ut, cnt in type_counts.items():
                name = ut.replace("_", " ").title()
                ts = sf.render(f"{name}: {cnt}", True, _STAT_LABEL)
                self.screen.blit(ts, (r.left + pad, y))
                y += ts.get_height() + 2

    def _draw_cc_info(self, r: pygame.Rect, cc: dict) -> None:
        """Show command center info in the display panel."""
        pad = 8
        tf = _get_font(18)
        sf = _get_font(16)

        y = r.top + pad
        ns = tf.render("Command Center", True, _TITLE_COLOR)
        self.screen.blit(ns, (r.left + pad, y))
        y += ns.get_height() + 4

        hp = cc.get("hp", CC_HP)
        bw = min(r.width - pad * 2, 150)
        bh = 6
        ratio = hp / CC_HP if CC_HP > 0 else 0
        pygame.draw.rect(self.screen, HEALTH_BAR_BG, (r.left + pad, y, bw, bh))
        fg = HEALTH_BAR_FG if ratio > 0.35 else HEALTH_BAR_LOW
        pygame.draw.rect(self.screen, fg, (r.left + pad, y, int(bw * ratio), bh))
        ht = sf.render(f"{int(hp)}/{int(CC_HP)}", True, (200, 200, 220))
        self.screen.blit(ht, (r.left + pad + bw + 6, y - 2))
        y += bh + 6

        spawn_type = cc.get("st", "soldier")
        st_text = sf.render(f"Spawning: {spawn_type.replace('_', ' ').title()}", True, _STAT_LABEL)
        self.screen.blit(st_text, (r.left + pad, y))

    def _draw_tooltip(self, utype: str, action_rect: pygame.Rect) -> None:
        """Draw a stats tooltip above the action panel."""
        stats = UNIT_TYPES.get(utype, {})
        tf = _get_font(20)
        bf = _get_font(16)

        rows: list[tuple[str, str]] = [
            ("HP", str(stats.get("hp", 100))),
            ("Speed", str(stats.get("speed", 0))),
        ]
        wpn = stats.get("weapon")
        if wpn:
            if wpn["damage"] < 0:
                rows.append(("Heal/pulse", str(abs(wpn["damage"]))))
            else:
                rows.append(("Damage", str(wpn["damage"])))
            rows.append(("Range", str(wpn["range"])))
            cd = wpn["cooldown"]
            rows.append(("Cooldown", f"{cd:.1f}s" if cd != int(cd)
                          else f"{int(cd)}s"))

        name = utype.replace("_", " ").title()
        tt_pad = 10
        tt_line_h = 20
        tt_width = 170
        tt_h = tt_pad + tt_line_h + 4 + len(rows) * tt_line_h + tt_pad
        tt_x = action_rect.left + 10
        tt_y = action_rect.top - tt_h - 6

        rect = pygame.Rect(tt_x, tt_y, tt_width, tt_h)
        pygame.draw.rect(self.screen, (22, 22, 34), rect, border_radius=6)
        pygame.draw.rect(self.screen, (70, 70, 100), rect, 1, border_radius=6)

        ts = tf.render(name, True, (220, 220, 240))
        self.screen.blit(ts, (tt_x + tt_pad, tt_y + tt_pad))

        ry = tt_y + tt_pad + tt_line_h + 4
        for label, value in rows:
            ls = bf.render(label, True, (140, 140, 165))
            vs = bf.render(value, True, (200, 200, 220))
            self.screen.blit(ls, (tt_x + tt_pad, ry))
            self.screen.blit(vs, (tt_x + tt_width - tt_pad - vs.get_width(), ry))
            ry += tt_line_h

    # -- entity drawing (adapted from ReplayPlaybackScreen) -----------------

    def _draw_unit(self, ent: dict) -> None:
        ws = self._world_surface
        x, y = ent.get("x", 0), ent.get("y", 0)
        c = tuple(ent.get("c", [255, 255, 255]))
        r = ent.get("r", 5)
        hp = ent.get("hp", 100)
        ut = ent.get("ut", "soldier")

        pygame.draw.circle(ws, c, (x, y), r)

        stats = UNIT_TYPES.get(ut, {})
        symbol = stats.get("symbol")
        if symbol:
            scale = r / 16.0
            translated = [(x + px * scale, y + py * scale) for px, py in symbol]
            pygame.draw.polygon(ws, (0, 0, 0), translated)
            pygame.draw.polygon(ws, c, translated, 1)

        max_hp = stats.get("hp", 100)
        if hp < max_hp:
            self._draw_health_bar(x, y, r + HEALTH_BAR_OFFSET, hp, max_hp)

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
            outline = (150, 220, 255) if tm == 1 else (255, 140, 140)
            pygame.draw.polygon(ws, outline, translated, 2)

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
        elif ow == 1:
            color = (80, 140, 255)
        else:
            color = (255, 80, 80)
        pygame.draw.circle(ws, color, (int(x), int(y)), int(r))

        if ow is None and abs(cp) > 0.01:
            progress_color = (TEAM_COLORS.get(1, (80, 140, 255)) if cp > 0
                              else TEAM_COLORS.get(2, (255, 80, 80)))
            arc_r = METAL_SPOT_CAPTURE_RADIUS + METAL_SPOT_CAPTURE_ARC_WIDTH
            start_angle = math.pi / 2
            end_angle = start_angle + cp * math.tau
            if cp > 0:
                a, b = start_angle, end_angle
            else:
                a, b = end_angle, start_angle
            rect = pygame.Rect(int(x - arc_r), int(y - arc_r),
                               int(arc_r * 2), int(arc_r * 2))
            pygame.draw.arc(ws, progress_color, rect, a, b,
                            int(METAL_SPOT_CAPTURE_ARC_WIDTH))

    def _draw_metal_extractor(self, ent: dict) -> None:
        ws = self._world_surface
        x, y = ent.get("x", 0), ent.get("y", 0)
        r = ent.get("r", METAL_EXTRACTOR_RADIUS)
        rot = ent.get("rot", 0.0)
        hp = ent.get("hp", 200)

        s = r * math.sqrt(3) / 2
        static_points = [
            complex(0, r),
            complex(-s, -r / 2),
            complex(s, -r / 2),
        ]
        rotated = [p * complex(math.cos(rot), math.sin(rot)) for p in static_points]
        points = [(p.real + x, p.imag + y) for p in rotated]
        pygame.draw.polygon(ws, (0, 0, 0), points, 1)

        if hp < METAL_EXTRACTOR_HP:
            self._draw_health_bar(x, y, r + HEALTH_BAR_OFFSET,
                                  hp, METAL_EXTRACTOR_HP)

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
        names = {
            self._my_team: self._client._player_name,
            3 - self._my_team: self._client.host_name,
        }
        for ent in entities:
            if ent.get("t") != "CC":
                continue
            tm = ent.get("tm", 1)
            name = names.get(tm, f"Team {tm}")
            team_color = TEAM1_COLOR if tm == 1 else TEAM2_COLOR
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
