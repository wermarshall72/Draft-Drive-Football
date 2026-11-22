"""Draw and discard piles for the human's offensive and defensive decks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pygame

from src.engine.football import FootballCardCopy, FootballDeckState
from src.engine.football_decks import (
    BONUS_CARD_CATALOG,
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
)
from src.ui.football_card_art import bonus_card_art, draw_card_art, play_card_art, scheme_card_art
from src.ui.football_match_palette import (
    MATCH_DIM, MATCH_FOCUS, MATCH_INK, MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_DEEP,
    MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT, MATCH_PANEL_HIGH, MATCH_TEXT,
    blit_text, match_font, mix, plain_font,
)
from src.ui.football_match_scoreboard import draw_football_icon
from src.ui.text import fit_text
from src.ui.widgets import Button

PILE_IDS = ("offense_draw", "offense_discard", "defense_draw", "defense_discard")


@dataclass(frozen=True)
class PileCounts:
    hand: int
    draw: int
    discard: int
    owned: int

    @property
    def consistent(self) -> bool:
        return self.hand + self.draw + self.discard == self.owned


def pile_counts(deck: FootballDeckState) -> PileCounts:
    return PileCounts(len(deck.hand), len(deck.draw_pile), len(deck.discard_pile), len(deck.owned))


def card_label(card: FootballCardCopy, offensive: bool) -> tuple[str, str, str]:
    """(name, family/kind label, art filename) for one owned copy."""
    if offensive and card.card_id in BONUS_CARD_CATALOG:
        bonus = BONUS_CARD_CATALOG[card.card_id]
        return bonus.name, "BONUS CARD", bonus_card_art(bonus.action)
    if offensive:
        play = OFFENSIVE_PLAY_CATALOG[card.card_id]
        return play.name, play.family.label.upper(), play_card_art(play.family)
    scheme = DEFENSIVE_SCHEME_CATALOG[card.card_id]
    return scheme.name, f"VS {scheme.family.label.upper()}", scheme_card_art(scheme.family)


def pile_cards(
    deck: FootballDeckState, pile_id: str, *, offensive: bool
) -> tuple[FootballCardCopy, ...]:
    """Draw piles list alphabetically so the popup never reveals the draw order;
    discard piles list the most recent card first."""
    if pile_id.endswith("_draw"):
        return tuple(sorted(deck.draw_pile, key=lambda card: card_label(card, offensive)[0]))
    return tuple(reversed(deck.discard_pile))


def _draw_shield(surface: pygame.Surface, center: tuple[int, int], size: int, color: pygame.Color) -> None:
    x, y = center
    points = (
        (x - size, y - size), (x + size, y - size), (x + size, y),
        (x, y + size + 3), (x - size, y),
    )
    pygame.draw.polygon(surface, color, points)


def draw_pile_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    deck: FootballDeckState,
    *,
    offensive: bool,
    back_color: pygame.Color,
    back_ink: pygame.Color,
    initial: str,
    focus_index: int,
    hover_index: int | None,
    button_offset: int,
    open_pile: Callable[[str], None],
    enabled: bool,
) -> list[Button]:
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=12)
    pygame.draw.rect(surface, MATCH_PANEL, rect.inflate(-4, -4), border_radius=11)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=12)
    header = pygame.Rect(rect.left + 2, rect.top + 2, rect.width - 4, 30)
    pygame.draw.rect(surface, MATCH_PANEL_HIGH, header, border_top_left_radius=10,
                     border_top_right_radius=10)
    title = "OFFENSE DECK" if offensive else "DEFENSE DECK"
    if offensive:
        draw_football_icon(surface, (header.left + 20, header.centery), 20, pygame.Color("#b5733d"))
    else:
        _draw_shield(surface, (header.left + 20, header.centery - 1), 7, MATCH_MUTED)
    title_rect = blit_text(surface, plain_font(16), title, MATCH_TEXT, header,
                           midleft=(header.left + 36, header.centery))
    counts = pile_counts(deck)
    owned_box = pygame.Rect(title_rect.right + 6, header.top, header.right - title_rect.right - 6, header.height)
    blit_text(surface, match_font(12), f"{counts.owned} OWNED", MATCH_MUTED, owned_box,
              midright=(header.right - 10, header.centery))

    prefix = "offense" if offensive else "defense"
    body_top = header.bottom + 8
    column_width = (rect.width - 30) // 2
    buttons: list[Button] = []
    for column, (pile, caption, count) in enumerate(
        (("draw", "DRAW", counts.draw), ("discard", "DISCARD", counts.discard))
    ):
        pile_id = f"{prefix}_{pile}"
        cell = pygame.Rect(rect.left + 10 + column * (column_width + 10), body_top,
                           column_width, rect.bottom - body_top - 10)
        index = button_offset + len(buttons)
        highlighted = enabled and (focus_index == index or hover_index == index)
        if highlighted:
            pygame.draw.rect(surface, mix(MATCH_PANEL_HIGH, MATCH_FOCUS, 0.1), cell, border_radius=8)
            pygame.draw.rect(surface, MATCH_FOCUS, cell, 2, border_radius=8)
        card_rect = pygame.Rect(0, 0, min(cell.width - 22, 84), min(cell.height - 62, 116))
        card_rect.midtop = (cell.centerx, cell.top + 8)
        if pile == "draw":
            _draw_stack(surface, card_rect, count, back_color, back_ink, initial)
        else:
            _draw_discard_top(surface, card_rect, deck, offensive)
        blit_text(surface, plain_font(30), str(count), MATCH_TEXT if count else MATCH_DIM, cell,
                  midtop=(cell.centerx, card_rect.bottom + 8))
        blit_text(surface, match_font(12), caption, MATCH_MUTED, cell,
                  midtop=(cell.centerx, card_rect.bottom + 42))
        buttons.append(
            Button(
                f"{title.split()[0]} {caption}",
                lambda pile_id=pile_id: open_pile(pile_id),
                cell,
                enabled=enabled,
                variant="pile",
            )
        )
    return buttons


def _draw_stack(
    surface: pygame.Surface,
    rect: pygame.Rect,
    count: int,
    fill: pygame.Color,
    ink: pygame.Color,
    initial: str,
) -> None:
    if count == 0:
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=8)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, rect, 2, border_radius=8)
        empty = match_font(11).render("EMPTY", True, MATCH_DIM)
        surface.blit(empty, empty.get_rect(center=rect.center))
        return
    layers = min(5, count)
    for layer in range(layers - 1, -1, -1):
        offset = rect.move(layer * 3, layer * 3 - 6)
        pygame.draw.rect(surface, MATCH_INK, offset.move(0, 2), border_radius=8)
        pygame.draw.rect(surface, fill, offset, border_radius=8)
        pygame.draw.rect(surface, mix(fill, pygame.Color("#ffffff"), 0.55), offset, 2, border_radius=8)
    top = rect.move(0, -6)
    pygame.draw.rect(surface, mix(fill, ink, 0.35), top.inflate(-14, -14), 2, border_radius=5)
    letter = plain_font(38).render(initial, True, ink)
    surface.blit(letter, letter.get_rect(center=top.center))


def _draw_discard_top(
    surface: pygame.Surface, rect: pygame.Rect, deck: FootballDeckState, offensive: bool
) -> None:
    if not deck.discard_pile:
        pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect.move(0, -6), border_radius=8)
        pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, rect.move(0, -6), 2, border_radius=8)
        empty = match_font(11).render("EMPTY", True, MATCH_DIM)
        surface.blit(empty, empty.get_rect(center=rect.move(0, -6).center))
        return
    top = rect.move(0, -6)
    if len(deck.discard_pile) > 1:
        pygame.draw.rect(surface, MATCH_PANEL_HIGH, top.move(4, 3), border_radius=8)
    name, _, art = card_label(deck.discard_pile[-1], offensive)
    pygame.draw.rect(surface, MATCH_INK, top.move(0, 2), border_radius=8)
    pygame.draw.rect(surface, MATCH_PANEL_HIGH, top, border_radius=8)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, top, 2, border_radius=8)
    draw_card_art(surface, art, top.inflate(-12, -34).move(0, -8))
    font = plain_font(10)
    blit_text(surface, font, fit_text(name.upper(), font, top.width - 8), MATCH_TEXT, top,
              midbottom=(top.centerx, top.bottom - 5))
