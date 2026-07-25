"""Guides screen — sidebar with 6 topics, content pane with word-wrapped text."""
from __future__ import annotations
import pygame
from screens.base import BaseScreen, ScreenResult
from ui.theme import (
    MENU_BG, SIDEBAR_BG, SIDEBAR_WIDTH, SIDEBAR_BTN_HEIGHT,
    CONTENT_BG, CONTENT_TEXT, CONTENT_HEADING, CONTENT_FONT_SIZE,
    HEADING_FONT_SIZE,
    TG_ACTIVE, TG_INACTIVE, TG_BORDER,
)
from ui.widgets import BackButton
from config.gamedata import GUIDE_TOPICS as TOPICS


class GuidesScreen(BaseScreen):
    """Guide viewer with sidebar navigation and word-wrapped content."""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        super().__init__(screen, clock)
        self._selected = 0
        self._back = BackButton()

    def run(self) -> ScreenResult:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return ScreenResult("quit")
                if self._back.handle_event(event):
                    return ScreenResult("main_menu")

                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    for i in range(len(TOPICS)):
                        r = pygame.Rect(0, 60 + i * SIDEBAR_BTN_HEIGHT,
                                        SIDEBAR_WIDTH, SIDEBAR_BTN_HEIGHT)
                        if r.collidepoint(event.pos):
                            # "Unit Overview" topic links to that screen
                            if i == len(TOPICS) - 1:
                                return ScreenResult("unit_overview")
                            self._selected = i

            self._draw()
            self.clock.tick(60)

    def _draw(self):
        self.screen.fill(MENU_BG)

        # Sidebar
        sidebar_rect = pygame.Rect(0, 0, SIDEBAR_WIDTH, self.height)
        pygame.draw.rect(self.screen, SIDEBAR_BG, sidebar_rect)

        font_s = pygame.font.SysFont(None, CONTENT_FONT_SIZE)
        mx, my = pygame.mouse.get_pos()

        for i, (title, _) in enumerate(TOPICS):
            r = pygame.Rect(0, 60 + i * SIDEBAR_BTN_HEIGHT,
                            SIDEBAR_WIDTH, SIDEBAR_BTN_HEIGHT)
            active = i == self._selected
            hover = r.collidepoint(mx, my)
            bg = TG_ACTIVE if active else (TG_BORDER if hover else TG_INACTIVE)
            pygame.draw.rect(self.screen, bg, r)
            pygame.draw.line(self.screen, TG_BORDER,
                             (r.left, r.bottom), (r.right, r.bottom))

            suffix = " >" if i == len(TOPICS) - 1 else ""
            label = font_s.render(title + suffix, True, (255, 255, 255) if active else CONTENT_TEXT)
            self.screen.blit(label, (12, r.centery - label.get_height() // 2))

        self._back.draw(self.screen)

        # Content pane
        content_x = SIDEBAR_WIDTH + 20
        content_w = self.width - SIDEBAR_WIDTH - 40
        _, lines = TOPICS[self._selected]

        font_h = pygame.font.SysFont(None, HEADING_FONT_SIZE)
        heading = font_h.render(TOPICS[self._selected][0], True, CONTENT_HEADING)
        self.screen.blit(heading, (content_x, 20))

        font_c = pygame.font.SysFont(None, CONTENT_FONT_SIZE)
        y = 60
        for line in lines:
            if not line:
                y += 10
                continue
            wrapped = self._wrap_text(font_c, line, content_w)
            for wline in wrapped:
                surf = font_c.render(wline, True, CONTENT_TEXT)
                self.screen.blit(surf, (content_x, y))
                y += surf.get_height() + 4

        self.present()

    @staticmethod
    def _wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [""]
