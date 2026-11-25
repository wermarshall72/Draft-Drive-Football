"""Display colors for AI teams on the match, result, bracket, and shop screens."""

from __future__ import annotations

import pygame
import pytest

from src.engine.football_ai_teams import AI_TEAMS_BY_ID, AI_TEAM_CATALOG
from src.profile import COLOR_BY_ID
from src.ui.football_ai_team_colors import (
    NEUTRAL_OPPONENT,
    draw_team_chip,
    opponent_colors,
)
from src.ui.football_ui_kit import MATCH_OPPONENT


@pytest.fixture(scope="module", autouse=True)
def _pygame():
    pygame.init()
    yield


def test_no_team_keeps_the_neutral_steel_uniform() -> None:
    assert opponent_colors(None) is NEUTRAL_OPPONENT
    assert NEUTRAL_OPPONENT.primary == MATCH_OPPONENT


def test_catalog_colors_come_from_the_profile_palette() -> None:
    for team in AI_TEAM_CATALOG:
        colors = opponent_colors(team)
        assert colors.primary == pygame.Color(COLOR_BY_ID[team.primary_color_id].hex_value)
        assert colors.secondary == pygame.Color(COLOR_BY_ID[team.secondary_color_id].hex_value)


def test_dark_primaries_get_a_visible_accent() -> None:
    corsairs = opponent_colors(AI_TEAMS_BY_ID["corsairs"])  # navy
    assert sum(corsairs.accent[:3]) > sum(corsairs.primary[:3])
    tigers = opponent_colors(AI_TEAMS_BY_ID["tigers"])  # orange is already bright
    assert tigers.accent == tigers.primary


def test_team_chip_shows_both_colors() -> None:
    surface = pygame.Surface((40, 20))
    colors = opponent_colors(AI_TEAMS_BY_ID["flamingos"])
    draw_team_chip(surface, pygame.Rect(0, 0, 40, 20), colors)
    assert surface.get_at((10, 10))[:3] == tuple(colors.primary)[:3]
    assert surface.get_at((30, 10))[:3] == tuple(colors.secondary)[:3]


def test_match_field_and_scoreboard_wear_the_rivals_colors() -> None:
    from src.engine.football_controller import FootballGameController
    from src.engine.football_ai import FootballAIDifficulty
    from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
    from src.ui.football_match_field import FieldOverlay, draw_match_field, field_geometry
    from src.ui.football_match_scoreboard import draw_scoreboard
    from src.ui.theme import Theme

    controller = FootballGameController(
        "Test Owls", difficulty=FootballAIDifficulty.EASY,
        builder_seed=1, shop_seed=2, ai_seed=3, match_seed=4,
    )
    controller.choose_coach(0)
    for position in PLAYER_DRAFT_ORDER:
        controller.choose_player(position, 0)
    state = controller.finish_shop()
    colors = opponent_colors(state.opponent_team)
    surface = pygame.Surface((1280, 720))
    field = pygame.Rect(10, 110, 1260, 286)
    draw_match_field(surface, field, state.match, pygame.Color("#d70000"),
                     FieldOverlay(line=None, line_progress=1.0, flash_elapsed_ms=None,
                                  banner=None, drop_hint=False),
                     human_scheme_highlight=True, opponent=colors,
                     opponent_short=state.opponent_team.abbreviation)
    zone = field_geometry(field).right_end_zone
    pixels = [surface.get_at((x, y))[:3] for x in range(zone.left, zone.right, 3)
              for y in range(zone.top, zone.bottom, 3)]
    assert pixels.count(tuple(colors.primary)[:3]) > len(pixels) // 3

    board = pygame.Rect(10, 10, 1260, 92)
    draw_scoreboard(surface, board, state.match,
                    Theme.from_profile(None), game_number=1, wins=0, losses=0, opponent=colors)
    rail = surface.get_at((board.right - 60, board.bottom - 5))[:3]
    assert rail != tuple(MATCH_OPPONENT)[:3]
