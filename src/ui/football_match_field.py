"""The match field presentation, independent of the run-screen coordinator."""

from collections.abc import Mapping

import pygame

from src.engine.football import DefensiveSchemeAction, FootballMatchState, FootballTeamSide
from src.ui.football_match_interaction import MatchInteraction
from src.ui.football_match_palette import (
    MATCH_PANEL as _MATCH_PANEL, MATCH_CHALK as _MATCH_CHALK,
    MATCH_MUTED as _MATCH_MUTED, MATCH_BRASS as _MATCH_BRASS,
    MATCH_INK as _MATCH_INK,
)
from src.ui.screens import _ui_font
from src.ui.text import fit_text as _fit_text
from src.ui.widgets import draw_text

_MATCH_TURF = pygame.Color("#244a35")
_MATCH_TURF_ALT = pygame.Color("#28513a")
_MATCH_TURF_LINE = pygame.Color("#8da891")


def draw_match_field(
    surface: pygame.Surface,
    rect: pygame.Rect,
    match: FootballMatchState,
    team_accent: pygame.Color,
    opponent_accent: pygame.Color,
    small_font: pygame.font.Font,
    interaction: MatchInteraction,
    scheme_labels: Mapping[DefensiveSchemeAction, str],
) -> None:
    pygame.draw.rect(surface, _MATCH_PANEL, rect)
    field = rect.inflate(-10, -10)
    pygame.draw.rect(surface, _MATCH_TURF, field)
    end_zone_width = max(42, round(field.width * 0.075))
    pygame.draw.rect(
        surface,
        team_accent,
        pygame.Rect(field.left, field.top, end_zone_width, field.height),
    )
    pygame.draw.rect(
        surface,
        opponent_accent,
        pygame.Rect(field.right - end_zone_width, field.top, end_zone_width, field.height),
    )

    left_end = pygame.Rect(field.left, field.top, end_zone_width, field.height)
    right_end = pygame.Rect(
        field.right - end_zone_width,
        field.top,
        end_zone_width,
        field.height,
    )
    for end_zone, name, color in (
        (left_end, match.team_a.team_name.upper(), _MATCH_INK),
        (right_end, match.team_b.team_name.upper(), _MATCH_INK),
    ):
        end_text = _fit_text(name, _ui_font(11, bold=True), end_zone.height - 18)
        label = _ui_font(11, bold=True).render(end_text, True, color)
        rotated = pygame.transform.rotate(label, 90)
        surface.blit(rotated, rotated.get_rect(center=end_zone.center))

    playing_left = field.left + end_zone_width
    playing_right = field.right - end_zone_width
    playing_width = playing_right - playing_left
    for stripe_index in range(10):
        stripe = pygame.Rect(
            playing_left + round(playing_width * stripe_index / 10),
            field.top,
            max(1, round(playing_width / 20)),
            field.height,
        )
        if stripe_index % 2:
            pygame.draw.rect(surface, _MATCH_TURF_ALT, stripe)

    line_color = (*_MATCH_TURF_LINE[:3], 155)
    for yard in range(0, 101, 5):
        x = playing_left + round(playing_width * yard / 100)
        is_major = yard % 10 == 0
        pygame.draw.line(
            surface,
            _MATCH_TURF_LINE if is_major else line_color,
            (x, field.top + 5),
            (x, field.bottom - 5),
            2 if is_major else 1,
        )
        if yard % 10 == 0 and yard not in (0, 100):
            number = yard if yard <= 50 else 100 - yard
            label = _ui_font(15, bold=True).render(str(number), True, _MATCH_CHALK)
            surface.blit(
                label,
                label.get_rect(center=(x, field.centery - 2)),
            )
        for hash_fraction in (0.32, 0.68):
            hash_y = field.top + round(field.height * hash_fraction)
            pygame.draw.line(
                surface,
                line_color,
                (x, hash_y - 4),
                (x, hash_y + 4),
                1,
            )

    field_label = (
        f"OWN {match.offense_field_position:.0f}"
        if match.offense_field_position <= 50
        else f"OPP {100 - match.offense_field_position:.0f}"
    )
    down_suffix = {1: "ST", 2: "ND", 3: "RD", 4: "TH"}[match.down]
    situation = (
        f"{match.down}{down_suffix} & {match.yards_to_go:g}"
    )
    draw_text(
        surface,
        situation,
        (playing_left + 16, rect.top + 15),
        _ui_font(22, bold=True),
        _MATCH_CHALK,
    )
    draw_text(
        surface,
        f"BALL AT {field_label}",
        (playing_left + 16, rect.top + 46),
        small_font,
        _MATCH_MUTED,
    )
    scheme = (
        scheme_labels[match.current_drive_defensive_scheme]
        if match.current_drive_defensive_scheme is not None
        else "NO DRIVE SCHEME"
    )
    possession_name = (
        match.team_a.team_name
        if match.possession is FootballTeamSide.TEAM_A
        else match.team_b.team_name
    )
    status_text = f"{possession_name.upper()} BALL   /   {scheme}"
    status_width = playing_width - 32
    status = small_font.render(
        _fit_text(status_text, small_font, status_width),
        True,
        _MATCH_MUTED,
    )
    surface.blit(
        status,
        status.get_rect(topright=(playing_right - 16, rect.top + 17)),
    )

    direction = 1 if match.possession is FootballTeamSide.TEAM_A else -1
    position, line_to_gain = interaction.field_positions(match, pygame.time.get_ticks())
    ball_x = playing_left + round(playing_width * position / 100)
    target_x = playing_left + round(playing_width * line_to_gain / 100)
    if direction < 0:
        ball_x = playing_right - round(playing_width * position / 100)
        target_x = playing_right - round(playing_width * line_to_gain / 100)
    ball_color = team_accent if match.possession is FootballTeamSide.TEAM_A else opponent_accent
    pygame.draw.line(
        surface,
        _MATCH_BRASS,
        (target_x, field.top + 8),
        (target_x, field.bottom - 8),
        3,
    )
    pygame.draw.line(
        surface,
        ball_color,
        (ball_x, field.top + 8),
        (ball_x, field.bottom - 8),
        2,
    )
    ball_center = (ball_x, field.centery)
    ball_rect = pygame.Rect(0, 0, 28, 17)
    ball_rect.center = ball_center
    pygame.draw.ellipse(surface, _MATCH_CHALK, ball_rect)
    pygame.draw.line(
        surface,
        _MATCH_INK,
        (ball_x - 2, ball_rect.top + 3),
        (ball_x - 2, ball_rect.bottom - 3),
        2,
    )
    for seam_offset in (-5, 1):
        pygame.draw.line(
            surface,
            _MATCH_INK,
            (ball_x + seam_offset, field.centery - 3),
            (ball_x + seam_offset, field.centery + 3),
            1,
        )
    arrow_direction = direction
    arrow_y = field.bottom - 18
    arrow_tip = ball_x + arrow_direction * 24
    pygame.draw.line(
        surface,
        ball_color,
        (ball_x, arrow_y),
        (arrow_tip, arrow_y),
        2,
    )
    pygame.draw.polygon(
        surface,
        ball_color,
        (
            (arrow_tip, arrow_y),
            (arrow_tip - arrow_direction * 7, arrow_y - 5),
            (arrow_tip - arrow_direction * 7, arrow_y + 5),
        ),
    )
