"""One-time tips: a small card the first time each key moment happens.

Tips never block input. A tip sits in free space beside the relevant area (the
shop header's message spot, or the match's outcome strip), shows a GOT IT button,
and disappears on GOT IT, Esc, or as soon as the player makes that decision. Only
one tip shows at a time, and each shows once: seen tip ids are remembered in the
team profile's ``seen_tips`` (see ``DesktopApplication``).
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable

import pygame

from src.ui.football_ui_kit import (
    MATCH_FOCUS,
    MATCH_INK,
    MATCH_MUTED,
    MATCH_PANEL_DEEP,
    MATCH_PANEL_EDGE,
    MATCH_PANEL_HIGH,
    MATCH_TEXT,
    blit_text,
    fit_wrapped,
    mix,
    plain_font,
)

TIP_SHOP = "shop"
TIP_OFFENSE = "offense"
TIP_DEFENSE = "defense"
TIP_FOURTH_DOWN = "fourth_down"
TIP_TWO_POINT = "two_point"

TIP_TEXT = {
    TIP_SHOP: "Spend AP on upgrades and cards. Unspent AP is lost at kickoff. "
              "Hover any card for details.",
    TIP_OFFENSE: "Play a card. Their scheme is hidden; learn what works from your yards.",
    TIP_DEFENSE: "Pick one defense for the whole drive. It stops one kind of play.",
    TIP_FOURTH_DOWN: "Go for it, punt, or kick a field goal.",
    TIP_TWO_POINT: "Kick for 1, or play a card to try for 2.",
}
TIP_IDS = tuple(TIP_TEXT)
GOT_IT = "GOT IT"
TIP_LABEL = "TIP"


class TipState:
    """Which tip is showing, which have been seen, and the GOT IT button's hit area."""

    def __init__(
        self,
        seen: Iterable[str] = (),
        on_seen: Callable[[str], None] = lambda _tip_id: None,
    ) -> None:
        self.seen: set[str] = set(seen)
        self.on_seen = on_seen
        self.current: str | None = None
        self._key: Hashable | None = None
        self.rect: pygame.Rect | None = None
        self.button_rect: pygame.Rect | None = None
        self._pressed = False
        self._pointer: tuple[int, int] | None = None

    def reset_seen(self) -> None:
        """Settings > SHOW TIPS AGAIN: every tip shows again."""
        self.seen.clear()
        self.dismiss()

    def update(self, tip_id: str | None, key: Hashable = None, *, hold: bool = False) -> str | None:
        """The tip to draw this frame, given the one the screen offers now.

        ``key`` identifies the decision; the tip hides for good once the offered
        tip or its key changes (the player made the decision). ``hold`` keeps the
        current state without drawing (e.g. while a popup covers the screen).
        """
        if hold:
            return None
        if self.current is not None:
            if (tip_id, key) == (self.current, self._key):
                return self.current
            self.dismiss()
        if tip_id is None or tip_id in self.seen:
            return None
        self.current, self._key = tip_id, key
        self.seen.add(tip_id)
        self.on_seen(tip_id)
        return tip_id

    def begin_frame(self) -> None:
        """Forget last frame's placement; only a tip drawn this frame takes GOT IT or Esc."""
        self.rect = None
        self.button_rect = None

    def dismiss(self) -> None:
        self.current = None
        self.rect = None
        self.button_rect = None
        self._pressed = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """GOT IT and Esc dismiss a visible tip (True when the event was used).

        Every other event passes through, so a tip never blocks clicks or keys.
        """
        if event.type == pygame.MOUSEMOTION:
            self._pointer = event.pos
            return False
        if self.current is None or self.rect is None:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.dismiss()
            return True
        button = self.button_rect
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._pressed = button is not None and button.collidepoint(event.pos)
            return self._pressed
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._pressed:
            self._pressed = False
            if button is not None and button.collidepoint(event.pos):
                self.dismiss()
            return True
        return False

    def draw(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        """Draw the current tip inside ``rect`` (the caller picks free space)."""
        if self.current is None:
            return
        self.rect = pygame.Rect(rect)
        self.button_rect = draw_tip(
            surface, self.rect, TIP_TEXT[self.current],
            hovered=self._pointer is not None and self._button_hit(self._pointer),
            pressed=self._pressed,
        )

    def _button_hit(self, pos: tuple[int, int]) -> bool:
        return self.button_rect is not None and self.button_rect.collidepoint(pos)


def draw_tip(
    surface: pygame.Surface,
    rect: pygame.Rect,
    text: str,
    *,
    hovered: bool = False,
    pressed: bool = False,
) -> pygame.Rect:
    """A gold-edged tip card with a TIP label, the text, and GOT IT; returns its button."""
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=10)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=10)
    pygame.draw.rect(surface, MATCH_FOCUS, rect, 2, border_radius=10)
    pygame.draw.rect(surface, MATCH_FOCUS, (rect.left + 7, rect.top + 8, 4, rect.height - 16),
                     border_radius=2)
    button_font = plain_font(12)
    button = pygame.Rect(0, 0, button_font.size(GOT_IT)[0] + 22, min(28, rect.height - 14))
    hint = rect.height >= 50
    button.midright = (rect.right - 10, rect.centery - (5 if hint else 0))
    face = button.move(0, 1) if pressed else button
    fill = MATCH_FOCUS if hovered else mix(MATCH_FOCUS, MATCH_PANEL_HIGH, 0.15)
    pygame.draw.rect(surface, fill, face, border_radius=7)
    blit_text(surface, button_font, GOT_IT, MATCH_INK, face.inflate(2, 2), center=face.center)
    hint_font = plain_font(9)
    if hint:
        blit_text(surface, hint_font, "OR ESC", MATCH_MUTED, rect,
                  midtop=(button.centerx, button.bottom + 1))
    label_font = plain_font(11)
    label = blit_text(surface, label_font, TIP_LABEL, MATCH_FOCUS, rect,
                      midleft=(rect.left + 18, rect.centery))
    body = pygame.Rect(label.right + 12, rect.top + 4, button.left - 12 - (label.right + 12),
                       rect.height - 8)
    max_lines = 3 if body.height >= 3 * plain_font(12).get_height() else 2
    font, lines = fit_wrapped(text, body.width, (15, 14, 13, 12, 11), max_lines)
    line_height = font.get_height()
    y = body.top + max(0, (body.height - line_height * len(lines)) // 2)
    for line in lines:
        blit_text(surface, font, line, MATCH_TEXT, body, topleft=(body.left, y))
        y += line_height
    return button

