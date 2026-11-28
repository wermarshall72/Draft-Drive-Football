"""Stadium scoreboard: badges, scores, clock, situation, and opponent hand counts."""

from __future__ import annotations

import logging
from functools import lru_cache

import pygame

from src.engine.football import FootballAwaitedAction, FootballMatchState, FootballTeamSide
from src.engine.football_playoffs import game_label
from src.ui.football_ai_team_colors import NEUTRAL_OPPONENT, OpponentColors
from src.ui.football_match_events import period_label
from src.ui.football_match_palette import (
    MATCH_DIM, MATCH_INK, MATCH_MUTED,
    MATCH_PANEL, MATCH_PANEL_DEEP, MATCH_PANEL_EDGE, MATCH_PANEL_EDGE_SOFT,
    MATCH_TEXT, blit_text, match_font, mix, plain_font,
)
from src.ui.text import fit_text
from src.ui.theme import Theme, readable_ink

_LOG = logging.getLogger(__name__)

SCOREBOARD_HEIGHT = 92


@lru_cache(maxsize=8)
def _helmet_sprite(rgb: tuple[int, int, int], height: int) -> pygame.Surface | None:
    try:
        from src.ui.main_menu_art import _tinted_helmet

        sprite = _tinted_helmet(rgb)
    except (OSError, pygame.error, ValueError) as error:
        _LOG.warning("Could not load scoreboard helmet artwork: %s", error)
        return None
    bounds = sprite.get_bounding_rect()
    sprite = sprite.subsurface(bounds).copy()
    width = max(1, round(sprite.get_width() * height / sprite.get_height()))
    return pygame.transform.smoothscale(sprite, (width, height))


def ball_spot_text(match: FootballMatchState) -> str:
    position = match.offense_field_position
    if abs(position - 50) < 0.5:
        return "BALL ON 50"
    if position < 50:
        return f"BALL ON OWN {round(position)}"
    return f"BALL ON OPP {max(1, round(100 - position))}"


CONVERSION_TEXT = "EXTRA POINT / 2-PT"


def is_conversion(match: FootballMatchState) -> bool:
    return (
        match.conversion_team is not None
        or match.awaited_action is FootballAwaitedAction.CONVERSION
    )


def down_text(match: FootballMatchState) -> str:
    if is_conversion(match):
        return CONVERSION_TEXT
    suffix = {1: "ST", 2: "ND", 3: "RD", 4: "TH"}[match.down]
    goal_to_go = match.offense_field_position + match.yards_to_go >= 99.95
    distance = "GOAL" if goal_to_go else (
        f"{match.yards_to_go:.0f}" if match.yards_to_go >= 1 else "INCHES"
    )
    return f"{match.down}{suffix} & {distance}"


def clock_text(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def draw_football_icon(
    surface: pygame.Surface, center: tuple[int, int], width: int, color: pygame.Color
) -> None:
    rect = pygame.Rect(0, 0, width, max(6, round(width * 0.58)))
    rect.center = center
    pygame.draw.ellipse(surface, color, rect)
    lace = mix(color, pygame.Color("#ffffff"), 0.85)
    pygame.draw.line(surface, lace, (rect.left + 4, rect.centery), (rect.right - 4, rect.centery), 1)
    for offset in (-3, 0, 3):
        x = rect.centerx + offset
        pygame.draw.line(surface, lace, (x, rect.centery - 2), (x, rect.centery + 2), 1)


def draw_card_back(
    surface: pygame.Surface, rect: pygame.Rect, fill: pygame.Color, edge: pygame.Color
) -> None:
    pygame.draw.rect(surface, fill, rect, border_radius=2)
    pygame.draw.rect(surface, edge, rect, 1, border_radius=2)
    inner = rect.inflate(-4, -4)
    if inner.width > 2 and inner.height > 2:
        pygame.draw.rect(surface, mix(fill, edge, 0.45), inner, 1, border_radius=1)


def draw_scoreboard(
    surface: pygame.Surface,
    rect: pygame.Rect,
    match: FootballMatchState,
    theme: Theme,
    *,
    game_number: int,
    wins: int,
    losses: int,
    kickoff_next: bool = False,
    opponent: OpponentColors = NEUTRAL_OPPONENT,
) -> pygame.Rect:
    """Draw everything except the PAUSE button; returns the opponent hand-count area."""
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=12)
    inner = rect.inflate(-6, -6)
    pygame.draw.rect(surface, MATCH_PANEL, inner, border_radius=10)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=12)
    # Team-colored rails; the side with the ball glows brighter.
    half = rect.width // 2
    team_rail = theme.primary_accent if match.possession is FootballTeamSide.TEAM_A else mix(
        theme.primary_accent, MATCH_PANEL, 0.55)
    opp_rail = opponent.accent if match.possession is FootballTeamSide.TEAM_B else mix(
        opponent.accent, MATCH_PANEL, 0.55)
    pygame.draw.rect(surface, team_rail, (rect.left + 14, rect.bottom - 6, half - 40, 3))
    pygame.draw.rect(surface, opp_rail, (rect.centerx + 26, rect.bottom - 6, half - 40, 3))

    _draw_team_block(surface, rect, match, theme)
    opponent_hand = _draw_opponent_block(surface, rect, match, opponent)
    _draw_center(surface, rect, match, game_number, wins, losses, kickoff_next)
    return opponent_hand


def _draw_team_block(
    surface: pygame.Surface, rect: pygame.Rect, match: FootballMatchState, theme: Theme
) -> None:
    badge = pygame.Rect(rect.left + 14, rect.top + 13, 64, 64)
    pygame.draw.rect(surface, MATCH_INK, badge.move(0, 3), border_radius=10)
    pygame.draw.rect(surface, theme.primary, badge, border_radius=10)
    pygame.draw.rect(surface, theme.primary_accent, badge, 2, border_radius=10)
    pygame.draw.rect(surface, mix(theme.primary, MATCH_INK, 0.35), badge.inflate(-10, -10), 1,
                     border_radius=7)
    initial = (match.team_a.team_name.strip()[:1] or "?").upper()
    ink = readable_ink(theme.primary)
    letter = plain_font(46).render(initial, True, ink)
    surface.blit(letter, letter.get_rect(center=(badge.centerx, badge.centery + 1)))

    name_left = badge.right + 14
    name_width = rect.width // 2 - 190 - (name_left - rect.left)
    name_font = plain_font(20)
    name = fit_text(match.team_a.team_name.upper(), name_font, max(40, name_width))
    block = pygame.Rect(rect.left, rect.top, rect.width // 2 - 180, rect.height)
    blit_text(surface, name_font, name, MATCH_TEXT, block, topleft=(name_left, rect.top + 10))
    score_font = plain_font(48)
    score = blit_text(surface, score_font, str(match.team_a_score), MATCH_TEXT, block,
                      topleft=(name_left - 2, rect.top + 30))
    if match.possession is FootballTeamSide.TEAM_A:
        draw_football_icon(
            surface,
            (score.right + 22, rect.top + 60),
            22,
            pygame.Color("#b5733d"),
        )


def _draw_opponent_block(
    surface: pygame.Surface, rect: pygame.Rect, match: FootballMatchState,
    opponent: OpponentColors = NEUTRAL_OPPONENT,
) -> pygame.Rect:
    helmet_box = pygame.Rect(rect.right - 14 - 72, rect.top + 12, 72, 66)
    sprite = _helmet_sprite(tuple(opponent.primary[:3]), 60)
    if sprite is not None:
        # The menu helmet faces right; mirror it to face our team across the board.
        sprite = pygame.transform.flip(sprite, True, False)
        surface.blit(sprite, sprite.get_rect(center=helmet_box.center))
    else:
        pygame.draw.ellipse(surface, opponent.primary, helmet_box.inflate(-8, -6))

    right = helmet_box.left - 14
    name_font = plain_font(20)
    name_width = rect.width // 2 - 190 - (rect.right - right)
    name = fit_text(match.team_b.team_name.upper(), name_font, max(40, name_width))
    block = pygame.Rect(rect.centerx + 180, rect.top, rect.right - rect.centerx - 180, rect.height)
    blit_text(surface, name_font, name, MATCH_TEXT, block, topright=(right, rect.top + 10))
    score_font = plain_font(48)
    score_rect = blit_text(surface, score_font, str(match.team_b_score), MATCH_TEXT, block,
                           topright=(right + 2, rect.top + 30))
    cursor = score_rect.left - 16
    if match.possession is FootballTeamSide.TEAM_B:
        draw_football_icon(surface, (cursor - 11, rect.top + 60), 22, pygame.Color("#b5733d"))
        cursor -= 34
    return draw_opponent_hand(surface, match, right_edge=cursor, center_y=rect.top + 60,
                              colors=opponent)


def opponent_hand_counts(match: FootballMatchState) -> tuple[int, int]:
    offense = match.team_b_offense_deck
    defense = match.team_b_defense_deck
    return (
        len(offense.hand) if offense is not None else 0,
        len(defense.hand) if defense is not None else 0,
    )


def draw_opponent_hand(
    surface: pygame.Surface, match: FootballMatchState, *, right_edge: int, center_y: int,
    colors: OpponentColors = NEUTRAL_OPPONENT,
) -> pygame.Rect:
    """Face-down backs with counts only; the AI's card identities never render."""
    offense_count, defense_count = opponent_hand_counts(match)
    label_font = match_font(13)
    groups = (("DEF", defense_count), ("OFF", offense_count))
    x = right_edge
    left = right_edge
    for label, count in groups:
        text = f"{label} ×{count}"
        x -= label_font.size(text)[0]
        blit_text(surface, label_font, text, MATCH_MUTED, surface.get_rect(), midleft=(x, center_y))
        shown = min(count, 5)
        x -= 6 + 8 * max(0, shown - 1) + 12
        for index in range(shown):
            back = pygame.Rect(x + index * 8, center_y - 9, 12, 18)
            draw_card_back(surface, back, colors.dark, colors.accent)
        if not shown:
            empty = pygame.Rect(x, center_y - 9, 12, 18)
            pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, empty, 1, border_radius=2)
        x -= 14
        left = x
    return pygame.Rect(left, center_y - 10, right_edge - left, 20)


def _draw_center(
    surface: pygame.Surface,
    rect: pygame.Rect,
    match: FootballMatchState,
    game_number: int,
    wins: int,
    losses: int,
    kickoff_next: bool = False,
) -> None:
    center = pygame.Rect(0, 0, 360, rect.height - 4)
    center.midtop = (rect.centerx, rect.top + 2)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, center, border_radius=8)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE_SOFT, center, 1, border_radius=8)
    blit_text(surface, plain_font(40), clock_text(match.game_clock_seconds), MATCH_TEXT, center,
              midtop=(rect.centerx, rect.top + 3))
    if match.status.value == "completed":
        situation = f"FINAL · {period_label(match.period)}"
    elif kickoff_next:
        team = match.team_a.team_name if match.possession is FootballTeamSide.TEAM_A else match.team_b.team_name
        situation = f"{period_label(match.period)}  ·  KICKOFF NEXT  ·  {team.upper()} KICKS"
    elif is_conversion(match):
        team = match.team_a.team_name if match.possession is FootballTeamSide.TEAM_A else match.team_b.team_name
        situation = f"{period_label(match.period)}  ·  {CONVERSION_TEXT}  ·  {team.upper()}"
    else:
        situation = f"{period_label(match.period)}  ·  {down_text(match)}  ·  {ball_spot_text(match)}"
    situation_font = match_font(16)
    situation = fit_text(situation, situation_font, center.width - 16)
    blit_text(surface, situation_font, situation, MATCH_TEXT, center, midtop=(rect.centerx, rect.top + 50))
    meta = f"{game_label(game_number)}  ·  RECORD {wins}-{losses}"
    blit_text(surface, match_font(12), meta, MATCH_DIM, center, midtop=(rect.centerx, rect.top + 71))
