"""Victory / Defeat / Draw results screen with post-game statistics."""
from __future__ import annotations
import pygame
from screens.base import BaseScreen, ScreenResult
from ui.theme import (
    MENU_BG, BTN_WIDTH, BTN_HEIGHT,
    GRAPH_LINE_T1, GRAPH_LINE_T2,
    SCORE_FONT_SIZE, SCORE_T1_COLOR, SCORE_T2_COLOR,
    STATS_HEADER_FONT_SIZE, STATS_SUB_FONT_SIZE,
    BUILD_ORDER_RADIUS,
)
from ui.widgets import Button, ToggleGroup, LineGraph, _get_font
from config.unit_types import UNIT_TYPES

# Tab definitions: (value, label)
_TABS = [
    ("cc_health", "CC HP"),
    ("army_count", "Army"),
    ("units_killed", "Kills"),
    ("damage_dealt", "Damage"),
    ("healing_done", "Healing"),
    ("metal_spots", "Metal"),
    ("apm", "APM"),
    ("build_order", "Build"),
]

_WHITE = (220, 220, 240)


class ResultsScreen(BaseScreen):
    """Shows game outcome with tabbed stat graphs and build order."""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock,
                 winner: int = 0, human_teams: set[int] | None = None,
                 stats: dict | None = None,
                 replay_filepath: str | None = None):
        super().__init__(screen, clock)
        self._winner = winner
        self._human_teams = human_teams or set()
        self._stats = stats  # the full stats dict from GameStats.finalize()
        self._replay_filepath = replay_filepath

        # Buttons — centered side by side at bottom
        gap = 20
        total_w = BTN_WIDTH * 2 + gap
        start_x = self.width // 2 - total_w // 2
        btn_y = self.height - 50

        self._btn = Button(start_x, btn_y, BTN_WIDTH, BTN_HEIGHT, "Return to Menu")
        self._replay_btn = Button(start_x + BTN_WIDTH + gap, btn_y,
                                  BTN_WIDTH, BTN_HEIGHT, "Watch Replay",
                                  enabled=replay_filepath is not None)

        # Build order scroll state
        self._build_scroll: int = 0

        # Tab bar and graph (only if stats available)
        self._has_stats = stats is not None and "teams" in (stats or {})
        if self._has_stats:
            tab_options = [(key, label) for key, label in _TABS]
            total_tabs = len(tab_options)
            tab_w = min(90, (self.width - 40) // total_tabs - 2)
            tab_x = (self.width - total_tabs * (tab_w + 2)) // 2
            self._tabs = ToggleGroup(tab_x, 90, tab_options,
                                     selected_index=0, btn_w=tab_w, btn_h=28)

            self._graph = LineGraph(30, 125, self.width - 60, 340,
                                    color1=GRAPH_LINE_T1, color2=GRAPH_LINE_T2)
            self._update_graph()

    def _update_graph(self):
        if not self._has_stats:
            return
        key = self._tabs.value
        if key == "build_order":
            return  # build order tab doesn't use graph
        t1 = self._stats["teams"].get("1", {}).get(key, [])
        t2 = self._stats["teams"].get("2", {}).get(key, [])

        # Build time labels from timestamps
        timestamps = self._stats.get("timestamps", [])
        x_labels = []
        for ts in timestamps:
            secs = ts / 60.0
            m, s = divmod(int(secs), 60)
            x_labels.append(f"{m}:{s:02d}")

        title = dict(_TABS).get(key, key)
        self._graph.title = title
        self._graph.set_data(t1, t2, x_labels)

    def _is_build_tab(self) -> bool:
        return self._has_stats and self._tabs.value == "build_order"

    def run(self) -> ScreenResult:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return ScreenResult("quit")
                if self._btn.handle_event(event):
                    return ScreenResult("main_menu")
                if self._replay_btn.handle_event(event):
                    return ScreenResult("replay_playback",
                                        data={"filepath": self._replay_filepath})
                if self._has_stats:
                    if self._tabs.handle_event(event):
                        self._build_scroll = 0
                        self._update_graph()
                    if self._is_build_tab():
                        if event.type == pygame.MOUSEWHEEL:
                            self._build_scroll -= event.y * 18
                            self._build_scroll = max(0, self._build_scroll)
                    else:
                        self._graph.handle_event(event)

            self._draw()
            self.clock.tick(60)

    def _draw(self):
        self.screen.fill(MENU_BG)

        if self._has_stats:
            self._draw_stats_view()
        else:
            self._draw_simple_view()

        self._btn.draw(self.screen)
        self._replay_btn.draw(self.screen)
        pygame.display.flip()

    def _header_text(self) -> str:
        """Return header string: 'Draw', 'Team X Victory', or 'Team X Defeat'."""
        if self._winner == -1:
            return "Draw"
        if self._winner in self._human_teams:
            return f"Team {self._winner} Victory"
        if self._human_teams:
            human_team = next(iter(self._human_teams))
            return f"Team {human_team} Defeat"
        # AI vs AI
        return f"Team {self._winner} Victory"

    def _draw_simple_view(self):
        """Fallback when no stats available."""
        text = self._header_text()

        font_big = _get_font(72)
        surf = font_big.render(text, True, _WHITE)
        x = self.width // 2 - surf.get_width() // 2
        y = self.height // 2 - surf.get_height() // 2 - 30
        self.screen.blit(surf, (x, y))

        font_sub = _get_font(24)
        if self._winner > 0:
            sub = f"Team {self._winner} destroyed the enemy Command Center."
        else:
            sub = "Both Command Centers were destroyed."
        sub_surf = font_sub.render(sub, True, (160, 160, 180))
        sx = self.width // 2 - sub_surf.get_width() // 2
        sy = y + surf.get_height() + 8
        self.screen.blit(sub_surf, (sx, sy))

    def _draw_stats_view(self):
        """Full stats dashboard with header, tabs, graph, build order."""
        # -- Header: result text in white --
        result_text = self._header_text()

        header_font = _get_font(STATS_HEADER_FONT_SIZE)
        h_surf = header_font.render(result_text, True, _WHITE)

        # Center header
        hx = self.width // 2 - h_surf.get_width() // 2
        self.screen.blit(h_surf, (hx, 10))

        # Duration top-right
        duration = self._stats.get("game_duration_seconds", 0)
        m, s = divmod(int(duration), 60)
        dur_str = f"Game Length: {m}:{s:02d}"
        sub_font = _get_font(STATS_SUB_FONT_SIZE)
        dur_surf = sub_font.render(dur_str, True, (160, 160, 180))
        self.screen.blit(dur_surf, (self.width - dur_surf.get_width() - 15, 15))

        # -- Scores --
        final = self._stats.get("final", {})
        score1 = final.get("1", {}).get("score", 0)
        score2 = final.get("2", {}).get("score", 0)

        score_font = _get_font(SCORE_FONT_SIZE)
        s1_surf = score_font.render(f"Team 1: {score1:,}", True, SCORE_T1_COLOR)
        s2_surf = score_font.render(f"Team 2: {score2:,}", True, SCORE_T2_COLOR)

        gap = 40
        total_score_w = s1_surf.get_width() + gap + s2_surf.get_width()
        score_x = self.width // 2 - total_score_w // 2
        score_y = 52
        self.screen.blit(s1_surf, (score_x, score_y))
        self.screen.blit(s2_surf, (score_x + s1_surf.get_width() + gap, score_y))

        # -- Tab bar --
        self._tabs.draw(self.screen)

        # -- Graph or Build Order --
        if self._is_build_tab():
            self._draw_build_order_tab()
        else:
            self._graph.draw(self.screen)

    def _draw_build_order_tab(self):
        """Draw two-column scrollable build order within the graph area."""
        # Use same area as graph
        area = self._graph.rect
        ax, ay, aw, ah = area.x, area.y, area.w, area.h

        # Background
        pygame.draw.rect(self.screen, (20, 20, 32), area, border_radius=4)
        pygame.draw.rect(self.screen, (40, 40, 55), area, 1, border_radius=4)

        final = self._stats.get("final", {})
        bo1 = final.get("1", {}).get("build_order", [])
        bo2 = final.get("2", {}).get("build_order", [])

        font = _get_font(14)
        row_h = 18
        r = BUILD_ORDER_RADIUS
        pad_x = 12
        pad_y = 8
        col_w = aw // 2

        # Clip to graph area
        clip_rect = pygame.Rect(ax, ay, aw, ah)
        old_clip = self.screen.get_clip()
        self.screen.set_clip(clip_rect)

        # Column headers
        hdr_y = ay + pad_y - self._build_scroll
        hdr_font = _get_font(16)
        h1 = hdr_font.render("Team 1", True, GRAPH_LINE_T1)
        h2 = hdr_font.render("Team 2", True, GRAPH_LINE_T2)
        self.screen.blit(h1, (ax + pad_x, hdr_y))
        self.screen.blit(h2, (ax + col_w + pad_x, hdr_y))

        start_y = hdr_y + row_h + 4

        def _draw_column(entries: list, col_x: int, color: tuple):
            for i, entry in enumerate(entries):
                ey = start_y + i * row_h
                if ey + row_h < ay or ey > ay + ah:
                    continue  # clipped
                cx = col_x + pad_x + r
                cy = ey + row_h // 2
                pygame.draw.circle(self.screen, color, (cx, cy), r)
                ut = entry.get("unit_type", "soldier") if isinstance(entry, dict) else "soldier"
                name = ut.replace("_", " ").title()
                name_surf = font.render(name, True, (200, 200, 220))
                self.screen.blit(name_surf, (cx + r + 6, cy - name_surf.get_height() // 2))

        _draw_column(bo1, ax, GRAPH_LINE_T1)
        _draw_column(bo2, ax + col_w, GRAPH_LINE_T2)

        # Clamp scroll to content
        max_rows = max(len(bo1), len(bo2))
        max_scroll = max(0, (max_rows * row_h + pad_y + row_h + 4) - ah)
        self._build_scroll = min(self._build_scroll, max_scroll)

        self.screen.set_clip(old_clip)
