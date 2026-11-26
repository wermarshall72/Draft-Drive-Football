"""HOW TO PLAY: one read-only page of short sections in the navy match style.

Opened from the main menu; Esc and BACK return to it. Every line is drawn with the
fit-audited ``blit_text`` so ``text_audit`` can check it at 1280x720.
"""

from __future__ import annotations

import pygame

from src.ui.football_ui_kit import (
    MATCH_FOCUS,
    MATCH_INK,
    MATCH_MUTED,
    MATCH_PANEL,
    MATCH_PANEL_EDGE,
    MATCH_PANEL_EDGE_SOFT,
    MATCH_TEXT,
    blit_text,
    draw_kit_button,
    kit_button,
    match_font,
    plain_font,
    stadium_backdrop,
)
from src.ui.screens import Navigate, Quit, Screen
from src.ui.text import wrap_text_lines
from src.ui.theme import Theme

TITLE = "HOW TO PLAY"
SUBTITLE = "The basics in one page. Hover any card in the game for details."
BACK = "BACK"

# (heading, paragraphs); each paragraph wraps inside its panel.
SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("The run", (
        "Play a 10-week season. Three losses and you're fired.",
        "Survive week 10 to reach an eight-team playoff. Win three games for the title.",
    )),
    ("The shop", (
        "Before each week you shop. Spend AP on player upgrades, coach upgrades, "
        "and play cards. Unspent AP is lost at kickoff.",
        "NEXT DAY costs 1 AP and brings new offers.",
    )),
    ("Offense vs defense", (
        "Your defense picks one kind of play to stop. If the offense calls that kind, "
        "it's stopped and gains less.",
        "On defense you pick one defense call per drive. It stays until they score, "
        "punt, or turn it over. On offense, cards marked STOPPED gain less.",
    )),
    ("Downs and 4th down", (
        "You get four downs to gain 10 yards for a first down.",
        "On 4th down, go for it, punt, or kick a field goal. After a touchdown, "
        "kick for 1 or play a card to try for 2.",
    )),
    ("Players", (
        "Power is strength. Volatility is how swingy results are; lower is steadier.",
        "Stamina is how well they hold up over a game. Partners get +10% when both "
        "play a part.",
    )),
    ("Coaches", (
        "Your offense and defense coaches boost certain positions, for example QB +20%.",
        "Each coach also has one perk, such as extra yards on the first run of a drive.",
    )),
)

MARGIN = 28
COLUMN_GAP = 16
ROW_GAP = 14
PANEL_TOP = 104
PANEL_BOTTOM = 640
BACK_RECT = pygame.Rect(1280 - MARGIN - 160, 656, 160, 42)


class HowToPlayScreen(Screen):
    """A read-only rules page; the only control is BACK."""

    def __init__(self, theme: Theme, navigate: Navigate, quit_application: Quit) -> None:
        super().__init__(theme, navigate, quit_application)

    def on_enter(self) -> None:
        super().on_enter()
        self.focus_index = 0
        self.hover_index = None
        self.pressed_index = None

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(stadium_backdrop(surface.get_size()), (0, 0))
        page = surface.get_rect()
        blit_text(surface, plain_font(34), TITLE, MATCH_TEXT, page, topleft=(MARGIN, 22))
        blit_text(surface, match_font(15, False), SUBTITLE, MATCH_MUTED, page, topleft=(MARGIN + 2, 66))
        pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (MARGIN, 92), (page.right - MARGIN, 92))

        columns, rows = 2, (len(SECTIONS) + 1) // 2
        width = (page.width - 2 * MARGIN - COLUMN_GAP) // columns
        height = (PANEL_BOTTOM - PANEL_TOP - ROW_GAP * (rows - 1)) // rows
        for index, (heading, paragraphs) in enumerate(SECTIONS):
            column, row = index % columns, index // columns
            rect = pygame.Rect(MARGIN + column * (width + COLUMN_GAP),
                               PANEL_TOP + row * (height + ROW_GAP), width, height)
            draw_section(surface, rect, heading, paragraphs)

        back = kit_button(BACK, lambda: self.navigate("main_menu"), BACK_RECT, variant="kit-primary")
        self._set_buttons([back])
        draw_kit_button(surface, back, focused=back.focused,
                        hovered=self.hover_index == 0, pressed=self.pressed_index == 0)
        blit_text(surface, plain_font(12), "ESC ALSO RETURNS TO THE MENU", MATCH_MUTED, page,
                  midright=(BACK_RECT.left - 16, BACK_RECT.centery))


def draw_section(surface: pygame.Surface, rect: pygame.Rect, heading: str,
                 paragraphs: tuple[str, ...]) -> None:
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=12)
    pygame.draw.rect(surface, MATCH_PANEL, rect, border_radius=12)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=12)
    pygame.draw.rect(surface, MATCH_FOCUS, (rect.left + 10, rect.top + 14, 4, 20), border_radius=2)
    blit_text(surface, plain_font(19), heading.upper(), MATCH_TEXT, rect,
              topleft=(rect.left + 22, rect.top + 11))
    body = pygame.Rect(rect.left + 22, rect.top + 44, rect.width - 40, rect.height - 52)
    for size in (16, 15, 14, 13):
        font = match_font(size, False)
        laid_out = [wrap_text_lines(paragraph, font, body.width) for paragraph in paragraphs]
        needed = sum(len(lines) for lines in laid_out) * font.get_height() + 6 * (len(paragraphs) - 1)
        if needed <= body.height:
            break
    y = body.top
    for lines in laid_out:
        for line in lines:
            blit_text(surface, font, line, MATCH_TEXT, body, topleft=(body.left, y))
            y += font.get_height()
        y += 6
