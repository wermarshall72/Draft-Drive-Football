"""Shared artwork mappings and pixel-preserving rendering for football cards."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import pygame

from src.engine.football import FootballBonusCardAction, FootballCardFamily

CARD_ART_DIR = Path(__file__).parent / "assets" / "football_cards"

FAMILY_CARD_ART = MappingProxyType(
    {
        FootballCardFamily.RB_RUN: (
            "offense_rb_run.png",
            "defense_rb_run.png",
        ),
        FootballCardFamily.SCREEN_PASS: (
            "offense_screen_pass.png",
            "defense_screen_pass.png",
        ),
        FootballCardFamily.PA_PASS: (
            "offense_pa_pass.png",
            "defense_pa_pass.png",
        ),
        FootballCardFamily.SHORT_PASS: (
            "offense_short_pass.png",
            "defense_short_pass.png",
        ),
        FootballCardFamily.MEDIUM_PASS: (
            "offense_medium_pass.png",
            "defense_medium_pass.png",
        ),
        FootballCardFamily.DEEP_PASS: (
            "offense_deep_pass.png",
            "defense_deep_pass.png",
        ),
    }
)

BONUS_CARD_ART = MappingProxyType(
    {
        FootballBonusCardAction.OFFENSIVE_DRAW: "bonus_offensive_draw.png",
        FootballBonusCardAction.DEFENSIVE_DRAW: "bonus_defensive_draw.png",
        FootballBonusCardAction.OPPONENT_DISCARD: "bonus_opponent_discard.png",
        FootballBonusCardAction.OFFENSIVE_DRAW_DISCARD:
            "bonus_offensive_draw_discard.png",
        FootballBonusCardAction.DEFENSIVE_DRAW_DISCARD:
            "bonus_defensive_draw_discard.png",
        FootballBonusCardAction.CHALLENGE: "bonus_challenge.png",
    }
)

REMOVE_ONE_CARD_ART = "shop_remove_one_card.png"


def play_card_art(family: FootballCardFamily) -> str:
    return FAMILY_CARD_ART[family][0]


def scheme_card_art(family: FootballCardFamily) -> str:
    return FAMILY_CARD_ART[family][1]


def bonus_card_art(action: FootballBonusCardAction) -> str:
    return BONUS_CARD_ART[action]


@lru_cache(maxsize=None)
def _source_art(filename: str) -> pygame.Surface:
    image = pygame.image.load(CARD_ART_DIR / filename)
    return image.convert_alpha() if pygame.display.get_surface() else image


def draw_card_art(
    surface: pygame.Surface,
    filename: str,
    rect: pygame.Rect,
) -> pygame.Rect:
    """Draw a contained card tile with nearest-neighbour scaling."""
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("Card artwork must have a positive display area.")
    source = _source_art(filename)
    scale = min(rect.width / source.get_width(), rect.height / source.get_height())
    size = (
        max(1, round(source.get_width() * scale)),
        max(1, round(source.get_height() * scale)),
    )
    image = pygame.transform.scale(source, size)
    destination = image.get_rect(center=rect.center)
    surface.blit(image, destination)
    return destination
