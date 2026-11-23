"""Portrait faces for plays, schemes, bonus cards, and Remove One Card.

Shared by the shop and the Playbook so both match the match-hand cards: family
tile art, a run (red) / pass (blue) / bonus (gold) band, the name, a family
label, and one compact stat cell.
"""

from __future__ import annotations

import pygame

from src.engine.football_decks import (
    FootballBonusCardDefinition,
    FootballPlayDefinition,
    FootballSchemeDefinition,
)
from src.engine.football_simulator import calculate_standardized_play_estimate
from src.ui.football_card_art import (
    REMOVE_ONE_CARD_ART,
    bonus_card_art,
    play_card_art,
    scheme_card_art,
)
from src.ui.football_match_events import bonus_effect, play_family_kind
from src.ui.football_match_field import PLAY_LINE_COLORS
from src.ui.football_ui_kit import (
    MATCH_GOLD,
    MATCH_MUTED,
    MATCH_PANEL_DEEP,
    MATCH_PANEL_HIGH,
    MATCH_TEXT,
    PLAY_LINE_OTHER,
    blit_text,
    draw_card_shell,
    draw_two_cells,
    fit_wrapped,
    mix,
    plain_font,
    rarity_color,
)
from src.ui.text import fit_text

CardDefinition = FootballPlayDefinition | FootballSchemeDefinition | FootballBonusCardDefinition | None


def card_art_name(definition: CardDefinition) -> str:
    """Tile for a definition; ``None`` means the Remove One Card service."""
    if definition is None:
        return REMOVE_ONE_CARD_ART
    if isinstance(definition, FootballBonusCardDefinition):
        return bonus_card_art(definition.action)
    if isinstance(definition, FootballPlayDefinition):
        return play_card_art(definition.family)
    return scheme_card_art(definition.family)


def card_band(definition: CardDefinition) -> pygame.Color:
    if definition is None:
        return PLAY_LINE_OTHER
    if isinstance(definition, FootballBonusCardDefinition):
        return MATCH_GOLD
    return PLAY_LINE_COLORS[play_family_kind(definition.family)]


def draw_play_card_face(
    surface: pygame.Surface,
    rect: pygame.Rect,
    definition: CardDefinition,
    rarity: object,
    *,
    bottom_gap: int,
    service_line: str = "PICK ANY COPY",
) -> pygame.Rect:
    """Draw the face above a ``bottom_gap`` footer strip; returns the inner rect."""
    band = card_band(definition)
    if definition is None:
        name, family, fill = "REMOVE 1 CARD", "SHOP SERVICE", MATCH_PANEL_HIGH
    elif isinstance(definition, FootballBonusCardDefinition):
        name, family, fill = definition.name.upper(), "BONUS CARD", mix(MATCH_PANEL_HIGH, MATCH_GOLD, 0.12)
    elif isinstance(definition, FootballPlayDefinition):
        name, family, fill = definition.name.upper(), definition.family.label.upper(), MATCH_PANEL_HIGH
    else:
        name, family, fill = definition.name.upper(), "DEFENSIVE SCHEME", MATCH_PANEL_HIGH
    tile_height = max(64, min(90, rect.height - 160))
    inner, tile, stats = draw_card_shell(
        surface, rect, art=card_art_name(definition), band=band, fill=fill,
        edge=rarity_color(rarity), border=2, tile_height=tile_height, stats_height=42,
        stats_bottom_gap=bottom_gap,
    )
    text_box = pygame.Rect(inner.left, tile.bottom, inner.width, stats.top - tile.bottom)
    family_font = plain_font(11, False)
    room = text_box.height - 6 - family_font.get_height() - 3
    sizes = (16, 15, 14, 13, 12, 11)
    for start in range(len(sizes)):
        font, lines = fit_wrapped(name, inner.width, sizes[start:], 2)
        if len(lines) * (font.get_height() - 1) <= room:
            break
    y = tile.bottom + 6
    for line in lines:
        blit_text(surface, font, line, MATCH_TEXT, text_box, midtop=(rect.centerx, y))
        y += font.get_height() - 1
    blit_text(surface, family_font, fit_text(family, family_font, inner.width), MATCH_MUTED, text_box,
              midtop=(rect.centerx, y + 1))
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, stats, border_radius=6)
    if isinstance(definition, FootballPlayDefinition):
        yards = calculate_standardized_play_estimate(definition.action).expected_yards
        draw_two_cells(surface, stats, ((f"~{yards:.1f}", "EST YDS"),
                                        (f"{definition.clock_seconds}s", "CLOCK")))
    elif isinstance(definition, FootballSchemeDefinition):
        blit_text(surface, plain_font(9), "COUNTERS", MATCH_MUTED, stats, midtop=(stats.centerx, stats.top + 4))
        font, lines = fit_wrapped(definition.family.label.upper(), stats.width - 6, (14, 13, 12, 11), 1)
        blit_text(surface, font, lines[0], band, stats, midbottom=(stats.centerx, stats.bottom - 3))
    else:
        text = bonus_effect(definition.action) if definition is not None else service_line
        font, lines = fit_wrapped(text, stats.width - 10, (13, 12, 11, 10), 2)
        total = len(lines) * (font.get_height() - 2)
        y = stats.centery - total // 2
        for line in lines:
            blit_text(surface, font, line, MATCH_TEXT, stats, midtop=(stats.centerx, y))
            y += font.get_height() - 2
    return inner
