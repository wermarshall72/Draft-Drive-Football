"""Display colors for a local AI team, from its catalog color ids.

Without a team (a legacy state or a test fixture) the AI keeps the neutral
steel uniform. ``accent`` is the primary nudged to stay visible on the navy
panels (rails, markers, swatch edges); ``primary`` tints the helmet and fills
the end zone; ``dark`` fills card backs.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from src.engine.football_ai_teams import FootballAITeam
from src.profile import COLOR_BY_ID
from src.ui.football_ui_kit import MATCH_OPPONENT, MATCH_OPPONENT_DARK, mix, team_accent


@dataclass(frozen=True)
class OpponentColors:
    primary: pygame.Color
    secondary: pygame.Color
    accent: pygame.Color
    dark: pygame.Color


NEUTRAL_OPPONENT = OpponentColors(
    primary=pygame.Color(MATCH_OPPONENT),
    secondary=pygame.Color(MATCH_OPPONENT_DARK),
    accent=pygame.Color(MATCH_OPPONENT),
    dark=pygame.Color(MATCH_OPPONENT_DARK),
)


def opponent_colors(team: FootballAITeam | None) -> OpponentColors:
    if team is None:
        return NEUTRAL_OPPONENT
    primary = pygame.Color(COLOR_BY_ID[team.primary_color_id].hex_value)
    secondary = pygame.Color(COLOR_BY_ID[team.secondary_color_id].hex_value)
    return OpponentColors(
        primary=primary,
        secondary=secondary,
        accent=team_accent(primary),
        dark=mix(primary, pygame.Color("#000000"), 0.55),
    )


def draw_team_chip(
    surface: pygame.Surface, rect: pygame.Rect, colors: OpponentColors
) -> None:
    """A small two-color swatch: primary on the left half, secondary on the right."""
    pygame.draw.rect(surface, colors.primary, rect, border_radius=3)
    half = pygame.Rect(rect.centerx, rect.top, rect.right - rect.centerx, rect.height)
    pygame.draw.rect(surface, colors.secondary, half,
                     border_top_right_radius=3, border_bottom_right_radius=3)
    pygame.draw.rect(surface, mix(colors.accent, pygame.Color("#f4f3ed"), 0.4), rect, 1,
                     border_radius=3)
