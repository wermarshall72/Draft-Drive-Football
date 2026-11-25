"""Modal match popups: Depth Chart, play-by-play log, and pile lists.

The pause menu itself is drawn by ``football_pause_menu``; ``PAUSE`` is its popup kind.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pygame

from src.engine.football import FootballMatchState
from src.engine.football_controller import FootballGameControllerState
from src.ui.football_card_art import draw_card_art
from src.ui.football_depth_chart import draw_depth_chart
from src.ui.football_match_events import (
    OutcomeEmphasis,
    outcome,
    overturned_sequences,
    perk_log_text,
    period_label,
)
from src.ui.football_match_outcome import OUTCOME_COLORS
from src.ui.football_match_palette import (
    MATCH_CANVAS, MATCH_DANGER, MATCH_DIM, MATCH_FOCUS, MATCH_GOLD, MATCH_INK,
    MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT,
    MATCH_PANEL_HIGH, MATCH_TEXT, blit_text, match_font, plain_font,
)
from src.ui.football_match_piles import card_label, pile_cards
from src.ui.football_match_scoreboard import clock_text
from src.ui.football_shop_review import ShopReviewInteraction
from src.ui.football_ui_kit import draw_popup_button, draw_popup_panel, draw_veil  # noqa: F401  (re-exported)
from src.ui.text import fit_text
from src.ui.theme import Theme
from src.ui.widgets import Button

PAUSE = "pause"
DEPTH = "depth"
LOG = "log"
PILE = "pile"

LOG_ROW_HEIGHT = 46
LOG_PERK_LINE = 16  # extra height for a row whose play fired player perks


@dataclass
class PopupState:
    kind: str | None = None
    pile_id: str | None = None
    log_scroll: int = 0
    log_max_scroll: int = 0
    log_viewport: pygame.Rect | None = None
    pile_scroll: int = 0
    pile_max_scroll: int = 0
    review: ShopReviewInteraction = field(default_factory=ShopReviewInteraction)

    @property
    def open(self) -> bool:
        return self.kind is not None

    def show(self, kind: str, pile_id: str | None = None) -> None:
        self.kind = kind
        self.pile_id = pile_id
        self.pile_scroll = 0
        if kind == LOG:
            self.log_scroll = 10**9  # clamp to the newest plays on first draw
        if kind == DEPTH:
            self.review.open_depth_chart()

    def close(self) -> None:
        self.kind = None
        self.pile_id = None
        self.review.close()

    def handle_scroll(self, event: pygame.event.Event) -> bool:
        if self.kind == DEPTH:
            return self.review.handle_scroll(event)
        if self.kind not in (LOG, PILE):
            return False
        step = 0
        if event.type == pygame.MOUSEWHEEL:
            step = -event.y * (LOG_ROW_HEIGHT if self.kind == LOG else 1)
        elif event.type == pygame.KEYDOWN and event.key in (
            pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END,
        ):
            page = 6 * LOG_ROW_HEIGHT if self.kind == LOG else 3
            step = {
                pygame.K_PAGEUP: -page, pygame.K_PAGEDOWN: page,
                pygame.K_HOME: -10**9, pygame.K_END: 10**9,
            }[event.key]
        if not step:
            return False
        if self.kind == LOG:
            self.log_scroll = max(0, min(self.log_max_scroll, self.log_scroll + step))
        else:
            self.pile_scroll = max(0, min(self.pile_max_scroll, self.pile_scroll + step))
        return True


_veil = draw_veil
_panel = draw_popup_panel


def draw_depth_popup(
    surface: pygame.Surface,
    state: FootballGameControllerState,
    theme: Theme,
    small_font: pygame.font.Font,
    label_font: pygame.font.Font,
    popup: PopupState,
    close: Callable[[], None],
) -> list[Button]:
    _veil(surface)
    rect = pygame.Rect(16, 12, surface.get_width() - 32, surface.get_height() - 24)
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 6), border_radius=16)
    pygame.draw.rect(surface, MATCH_CANVAS, rect, border_radius=16)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=16)
    content = rect.inflate(-32, -24)
    return draw_depth_chart(
        surface, content, state, theme, small_font, label_font, popup.review, close,
        back_label="CLOSE [ESC]", subtitle="THIS MATCH · READ ONLY", in_match=True,
    )


def draw_log_popup(
    surface: pygame.Surface,
    match: FootballMatchState,
    popup: PopupState,
    close: Callable[[], None],
) -> list[Button]:
    _veil(surface)
    rect = pygame.Rect(0, 0, 900, 640)
    rect.center = (surface.get_width() // 2, surface.get_height() // 2)
    events = match.match_events
    viewport = _panel(surface, rect, "PLAY LOG", f"{len(events)} events · newest at the bottom · wheel or Page Up/Down to scroll")
    team_a, team_b = match.team_a.team_name, match.team_b.team_name
    overturned = overturned_sequences(events)
    rows: list[tuple[str, object]] = []
    last_period = None
    for index, event in enumerate(events):
        previous = events[index - 1] if index else None
        period = previous.period if previous is not None else event.period
        if period != last_period:
            rows.append(("period", period))
            last_period = period
        rows.append(("event", (event, previous)))
    def row_height(kind: str, payload) -> int:
        if kind == "period":
            return 30
        return LOG_ROW_HEIGHT + (LOG_PERK_LINE if payload[0].perk_activations else 0)

    total_height = 0
    for kind, payload in rows:
        total_height += row_height(kind, payload)
    popup.log_max_scroll = max(0, total_height - viewport.height)
    popup.log_scroll = max(0, min(popup.log_scroll, popup.log_max_scroll))
    popup.log_viewport = viewport
    clip = surface.get_clip()
    surface.set_clip(viewport)
    y = viewport.top - popup.log_scroll
    headline_font = plain_font(17)
    detail_font = plain_font(13, False)
    for kind, payload in rows:
        height = row_height(kind, payload)
        if y + height < viewport.top or y > viewport.bottom:
            y += height
            continue
        if kind == "period":
            label = match_font(13).render(period_label(payload), True, MATCH_FOCUS)
            surface.blit(label, (viewport.left + 4, y + 8))
            pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (viewport.left + label.get_width() + 14, y + 16),
                             (viewport.right - 8, y + 16))
            y += height
            continue
        event, previous = payload
        result = outcome(event, previous, team_a, team_b)
        row = pygame.Rect(viewport.left, y + 2, viewport.width - 12, height - 4)
        pygame.draw.rect(surface, MATCH_PANEL, row, border_radius=7)
        struck = event.sequence in overturned
        color = OUTCOME_COLORS[result.kind]
        pygame.draw.rect(surface, color if not struck else MATCH_DIM,
                         (row.left + 6, row.top + 8, 5, row.height - 16), border_radius=2)
        time_text = clock_text((previous or event).game_clock_seconds)
        time_surface = match_font(13).render(time_text, True, MATCH_MUTED)
        surface.blit(time_surface, (row.left + 20, row.top + 6))
        text_left = row.left + 86
        text_width = row.width - 96
        tag_width = 0
        if struck:
            tag = match_font(11).render("OVERTURNED", True, MATCH_INK)
            tag_rect = tag.get_rect().inflate(10, 4)
            tag_rect.topright = (row.right - 8, row.top + 6)
            pygame.draw.rect(surface, MATCH_DIM, tag_rect, border_radius=5)
            surface.blit(tag, tag.get_rect(center=tag_rect.center))
            tag_width = tag_rect.width + 10
        elif result.emphasis is not OutcomeEmphasis.NORMAL:
            marker = MATCH_GOLD if result.emphasis is OutcomeEmphasis.SCORE else MATCH_DANGER
            pygame.draw.circle(surface, marker, (row.right - 16, row.top + 14), 5)
            tag_width = 24
        headline = fit_text(result.headline, headline_font, text_width - tag_width)
        head_surface = headline_font.render(headline, True, MATCH_DIM if struck else color)
        surface.blit(head_surface, (text_left, row.top + 3))
        if struck:
            pygame.draw.line(surface, MATCH_DIM, (text_left, row.top + 14),
                             (text_left + head_surface.get_width(), row.top + 14), 2)
        detail = result.detail
        if event.perk_effects:
            detail = f"{detail} · {'; '.join(event.perk_effects)}" if detail else "; ".join(event.perk_effects)
        detail_surface = detail_font.render(fit_text(detail, detail_font, text_width), True, MATCH_MUTED)
        surface.blit(detail_surface, (text_left, row.top + 23))
        perks = perk_log_text(event)
        if perks:
            perk_box = pygame.Rect(text_left, row.top + 38, text_width, LOG_PERK_LINE)
            blit_text(surface, detail_font, fit_text(perks, detail_font, text_width),
                      MATCH_GOLD if not struck else MATCH_DIM, perk_box, topleft=perk_box.topleft)
        y += height
    surface.set_clip(clip)
    if popup.log_max_scroll:
        track = pygame.Rect(viewport.right - 6, viewport.top, 4, viewport.height)
        pygame.draw.rect(surface, MATCH_PANEL, track, border_radius=2)
        thumb_height = max(30, round(viewport.height * viewport.height / (total_height or 1)))
        thumb_y = track.top + round((track.height - thumb_height) * popup.log_scroll / popup.log_max_scroll)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE, (track.left, thumb_y, 4, thumb_height), border_radius=2)
    if not events:
        empty = match_font(15).render("No plays yet.", True, MATCH_MUTED)
        surface.blit(empty, (viewport.left + 4, viewport.top + 6))
    close_rect = pygame.Rect(rect.right - 180, rect.bottom - 54, 160, 40)
    return [Button("CLOSE [ESC]", close, close_rect, variant="popup-primary")]


def draw_pile_popup(
    surface: pygame.Surface,
    match: FootballMatchState,
    popup: PopupState,
    close: Callable[[], None],
) -> list[Button]:
    _veil(surface)
    pile_id = popup.pile_id or "offense_draw"
    offensive = pile_id.startswith("offense")
    deck = match.team_a_offense_deck if offensive else match.team_a_defense_deck
    assert deck is not None
    cards = pile_cards(deck, pile_id, offensive=offensive)
    side = "OFFENSE" if offensive else "DEFENSE"
    draw = pile_id.endswith("_draw")
    title = f"{side} {'DRAW PILE' if draw else 'DISCARD'}"
    subtitle = (
        f"{len(cards)} cards · listed A–Z so the draw order stays hidden · read only"
        if draw
        else f"{len(cards)} cards · most recent first · read only"
    )
    rect = pygame.Rect(0, 0, 860, 560)
    rect.center = (surface.get_width() // 2, surface.get_height() // 2)
    viewport = _panel(surface, rect, title, subtitle)
    columns = 6
    gap = 12
    card_width = (viewport.width - gap * (columns - 1)) // columns
    card_height = 170
    rows = (len(cards) + columns - 1) // columns
    visible_rows = max(1, (viewport.height + gap) // (card_height + gap))
    popup.pile_max_scroll = max(0, rows - visible_rows)
    popup.pile_scroll = max(0, min(popup.pile_scroll, popup.pile_max_scroll))
    start = popup.pile_scroll * columns
    for offset, card in enumerate(cards[start:start + visible_rows * columns]):
        row, column = divmod(offset, columns)
        card_rect = pygame.Rect(
            viewport.left + column * (card_width + gap),
            viewport.top + row * (card_height + gap),
            card_width,
            card_height,
        )
        name, family, art = card_label(card, offensive)
        pygame.draw.rect(surface, MATCH_PANEL_HIGH, card_rect, border_radius=9)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE, card_rect, 2, border_radius=9)
        draw_card_art(surface, art, pygame.Rect(card_rect.left + 8, card_rect.top + 8, card_rect.width - 16, 92))
        name_font = plain_font(13)
        name_surface = name_font.render(fit_text(name.upper(), name_font, card_rect.width - 10), True, MATCH_TEXT)
        surface.blit(name_surface, name_surface.get_rect(midtop=(card_rect.centerx, card_rect.top + 110)))
        family_font = plain_font(11, False)
        family_surface = family_font.render(fit_text(family, family_font, card_rect.width - 10), True, MATCH_MUTED)
        surface.blit(family_surface, family_surface.get_rect(midtop=(card_rect.centerx, card_rect.top + 132)))
    if not cards:
        empty = match_font(16).render("This pile is empty.", True, MATCH_MUTED)
        surface.blit(empty, (viewport.left + 4, viewport.top + 6))
    if popup.pile_max_scroll:
        page = match_font(13).render(
            f"ROWS {popup.pile_scroll + 1}-{popup.pile_scroll + visible_rows} OF {rows} · SCROLL FOR MORE",
            True, MATCH_MUTED)
        surface.blit(page, (rect.left + 26, rect.bottom - 44))
    close_rect = pygame.Rect(rect.right - 180, rect.bottom - 54, 160, 40)
    return [Button("CLOSE [ESC]", close, close_rect, variant="popup-primary")]
