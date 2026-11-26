"""Detailed side-view field: turf, end zones, markers, and the latest play line."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import pygame

from src.engine.football import FootballMatchState, FootballTeamSide
from src.engine.football_decks import DEFENSIVE_SCHEME_CATALOG
from src.ui.football_ai_team_colors import NEUTRAL_OPPONENT, OpponentColors
from src.ui.football_match_events import (
    PlayLine,
    PlayLineKind,
    absolute_spot,
    direction,
)
from src.ui.football_match_palette import (
    FIRST_DOWN_LINE, LINE_OF_SCRIMMAGE, MATCH_FOCUS, MATCH_INK,
    MATCH_PANEL_DEEP, MATCH_PANEL_EDGE, MATCH_TEXT, PLAY_LINE_CASING, PLAY_LINE_OTHER,
    PLAY_LINE_PASS, PLAY_LINE_RUN, TURF_DARK, TURF_EDGE, TURF_LIGHT, TURF_LINE,
    blit_text, match_font, mix, plain_font,
)
from src.ui.football_match_playback import EVENT_DURATION_MS
from src.ui.football_match_scoreboard import down_text
from src.ui.text import fit_text
from src.ui.theme import readable_ink

FIELD_HEIGHT = 286
END_ZONE_WIDTH = 92

PLAY_LINE_COLORS = {
    PlayLineKind.RUN: PLAY_LINE_RUN,
    PlayLineKind.PASS: PLAY_LINE_PASS,
    PlayLineKind.OTHER: PLAY_LINE_OTHER,
}


@dataclass(frozen=True)
class FieldGeometry:
    frame: pygame.Rect
    turf: pygame.Rect
    left_end_zone: pygame.Rect
    right_end_zone: pygame.Rect
    playing: pygame.Rect

    def x_for(self, absolute_yards: float) -> int:
        return self.playing.left + round(self.playing.width * absolute_yards / 100)

    @property
    def lane_y(self) -> int:
        """The play-line lane sits just below the ball so short gains stay visible."""
        return self.turf.centery + 20

    @property
    def ball_y(self) -> int:
        return self.turf.centery - 4


def field_geometry(rect: pygame.Rect) -> FieldGeometry:
    turf = rect.inflate(-8, -8)
    left = pygame.Rect(turf.left, turf.top, END_ZONE_WIDTH, turf.height)
    right = pygame.Rect(turf.right - END_ZONE_WIDTH, turf.top, END_ZONE_WIDTH, turf.height)
    playing = pygame.Rect(left.right, turf.top, right.left - left.right, turf.height)
    return FieldGeometry(rect, turf, left, right, playing)


@dataclass(frozen=True)
class FieldOverlay:
    """Transient things the playback layer asks the field to show."""

    line: PlayLine | None = None
    line_progress: float = 1.0
    flash_elapsed_ms: int | None = None
    banner: str | None = None
    drop_hint: bool = False


@lru_cache(maxsize=4)
def _turf_surface(size: tuple[int, int]) -> pygame.Surface:
    """Static turf (stripes, yard lines, hashes, numbers) for one playing size."""
    width, height = size
    surface = pygame.Surface(size)
    surface.fill(TURF_DARK)
    for stripe in range(20):
        if stripe % 2:
            left = round(width * stripe / 20)
            right = round(width * (stripe + 1) / 20)
            pygame.draw.rect(surface, TURF_LIGHT, (left, 0, right - left, height))
    faint = mix(TURF_LINE, TURF_DARK, 0.45)
    for yard in range(0, 101):
        x = round(width * yard / 100)
        if yard % 5 == 0:
            major = yard % 10 == 0
            thickness = 3 if yard in (0, 100) else 2 if major else 1
            color = TURF_LINE if major else mix(TURF_LINE, TURF_DARK, 0.25)
            pygame.draw.line(surface, color, (x, 0), (x, height), thickness)
        else:
            # Sideline ticks and two inner hash rows.
            pygame.draw.line(surface, faint, (x, 3), (x, 9), 1)
            pygame.draw.line(surface, faint, (x, height - 10), (x, height - 4), 1)
            for fraction in (0.36, 0.64):
                y = round(height * fraction)
                pygame.draw.line(surface, faint, (x, y - 3), (x, y + 3), 1)
    number_font = plain_font(26)
    for yard in range(10, 100, 10):
        x = round(width * yard / 100)
        value = str(yard if yard <= 50 else 100 - yard)
        for y_fraction in (0.17, 0.83):
            label = number_font.render(value, True, mix(TURF_LINE, TURF_DARK, 0.12))
            surface.blit(label, label.get_rect(center=(x, round(height * y_fraction))))
            # Direction arrows beside the numbers point toward the nearer goal.
            if yard != 50:
                arrow_x = x - 22 if yard < 50 else x + 22
                tip = -1 if yard < 50 else 1
                y = round(height * y_fraction)
                pygame.draw.polygon(
                    surface,
                    mix(TURF_LINE, TURF_DARK, 0.2),
                    ((arrow_x + tip * 4, y), (arrow_x - tip * 3, y - 4), (arrow_x - tip * 3, y + 4)),
                )
    return surface


def _end_zone(
    surface: pygame.Surface, rect: pygame.Rect, fill: pygame.Color, name: str, *, left: bool,
    short: str | None = None,
) -> None:
    """Fill and stripe an end zone and letter it with the team name (or ``short`` if it won't fit)."""
    pygame.draw.rect(surface, fill, rect)
    stripe = mix(fill, pygame.Color("#000000"), 0.16)
    clip = surface.get_clip()
    surface.set_clip(rect.clip(clip))
    for offset in range(-rect.height, rect.width, 18):
        start = (rect.left + offset, rect.bottom)
        end = (rect.left + offset + rect.height, rect.top)
        pygame.draw.line(surface, stripe, start, end, 6)
    surface.set_clip(clip)
    ink = readable_ink(fill)
    font = plain_font(30)
    available = rect.height - 24
    if short and font.size(name.upper())[0] > available:
        name = short
    text = fit_text(name.upper(), font, available)
    label = font.render(text, True, ink)
    rotated = pygame.transform.rotate(label, 90 if left else -90)
    surface.blit(rotated, rotated.get_rect(center=rect.center))


def _casing_line(
    surface: pygame.Surface,
    start: tuple[int, int],
    end: tuple[int, int],
    color: pygame.Color,
    width: int,
) -> None:
    pygame.draw.line(surface, PLAY_LINE_CASING, start, end, width + 4)
    for point in (start, end):
        pygame.draw.circle(surface, PLAY_LINE_CASING, point, (width + 4) // 2)
    pygame.draw.line(surface, color, start, end, width)
    for point in (start, end):
        pygame.draw.circle(surface, color, point, width // 2)


def _arrow_head(
    surface: pygame.Surface, tip: tuple[int, int], heading: int, color: pygame.Color
) -> None:
    x, y = tip
    points = ((x + heading * 7, y), (x - heading * 7, y - 9), (x - heading * 7, y + 9))
    pygame.draw.polygon(surface, PLAY_LINE_CASING, points)
    inner = ((x + heading * 4, y), (x - heading * 5, y - 6), (x - heading * 5, y + 6))
    pygame.draw.polygon(surface, color, inner)


def _draw_x(surface: pygame.Surface, center: tuple[int, int], size: int, color: pygame.Color) -> None:
    x, y = center
    for width, shade in ((8, PLAY_LINE_CASING), (4, color)):
        pygame.draw.line(surface, shade, (x - size, y - size), (x + size, y + size), width)
        pygame.draw.line(surface, shade, (x - size, y + size), (x + size, y - size), width)


def _tag(
    surface: pygame.Surface,
    text: str,
    anchor: tuple[int, int],
    fill: pygame.Color,
    *,
    ink: pygame.Color | None = None,
    font_size: int = 12,
    align: str = "center",
) -> pygame.Rect:
    font = match_font(font_size)
    rect = pygame.Rect((0, 0), font.size(text)).inflate(12, 4)
    if align == "left":
        rect.midleft = anchor
    elif align == "right":
        rect.midright = anchor
    else:
        rect.center = anchor
    pygame.draw.rect(surface, PLAY_LINE_CASING, rect.inflate(2, 2), border_radius=5)
    pygame.draw.rect(surface, fill, rect, border_radius=4)
    blit_text(surface, font, text, ink or readable_ink(fill), rect, center=rect.center)
    return rect


def draw_play_line(
    surface: pygame.Surface,
    geometry: FieldGeometry,
    line: PlayLine,
    progress: float,
) -> tuple[int, int] | None:
    """Draw ``line`` up to ``progress`` and return where its tip currently is."""
    lane = geometry.lane_y
    lengths = [abs(segment.end - segment.start) for segment in line.segments]
    total = sum(lengths)
    budget = total * max(0.0, min(1.0, progress))
    tip: tuple[int, int] | None = None
    for index, (segment, length) in enumerate(zip(line.segments, lengths)):
        if budget <= 0:
            break
        # Returns run in a lane just below the play so overlapping yards stay legible.
        y = lane + index * 16
        drawn = min(length, budget)
        budget -= drawn
        heading = 1 if segment.end >= segment.start else -1
        start_x = geometry.x_for(segment.start)
        end_x = geometry.x_for(segment.start + heading * drawn)
        color = PLAY_LINE_COLORS[segment.kind]
        if index:
            # A short connector shows the return starts where the ball changed hands.
            pygame.draw.line(surface, PLAY_LINE_CASING, (start_x, y - 16), (start_x, y), 3)
        _casing_line(surface, (start_x, y), (end_x, y), color, 6)
        if index == 0:
            pygame.draw.circle(surface, PLAY_LINE_CASING, (start_x, y), 7)
            pygame.draw.circle(surface, color, (start_x, y), 4)
        if drawn >= length - 0.01 or budget <= 0:
            _arrow_head(surface, (end_x, y), heading, color)
        tip = (end_x, y)
    if progress >= 0.999:
        marker_y = geometry.ball_y - 30
        if line.incomplete_at is not None:
            _draw_x(surface, (geometry.x_for(line.incomplete_at), lane), 9, PLAY_LINE_PASS)
        if line.turnover_at is not None:
            _tag(surface, "TURNOVER", (geometry.x_for(line.turnover_at), marker_y),
                 pygame.Color("#ff7a59"), ink=MATCH_INK, font_size=11)
        if line.blocked_at is not None:
            _tag(surface, "BLOCKED", (geometry.x_for(line.blocked_at), marker_y),
                 PLAY_LINE_OTHER, ink=MATCH_INK, font_size=11)
    return tip


def _draw_ball(surface: pygame.Surface, center: tuple[int, int]) -> None:
    rect = pygame.Rect(0, 0, 30, 18)
    rect.center = center
    pygame.draw.ellipse(surface, PLAY_LINE_CASING, rect.inflate(4, 4))
    pygame.draw.ellipse(surface, pygame.Color("#9b5a2a"), rect)
    pygame.draw.ellipse(surface, pygame.Color("#c47b43"), rect.inflate(-10, -8))
    pygame.draw.line(surface, MATCH_TEXT, (rect.left + 9, rect.centery), (rect.right - 9, rect.centery), 2)
    for offset in (-4, 0, 4):
        x = rect.centerx + offset
        pygame.draw.line(surface, MATCH_TEXT, (x, rect.centery - 3), (x, rect.centery + 3), 1)


def draw_match_field(
    surface: pygame.Surface,
    rect: pygame.Rect,
    match: FootballMatchState,
    team_color: pygame.Color,
    overlay: FieldOverlay,
    *,
    human_scheme_highlight: bool,
    kickoff_pending: bool = False,
    opponent: OpponentColors = NEUTRAL_OPPONENT,
    opponent_short: str | None = None,
) -> FieldGeometry:
    geometry = field_geometry(rect)
    pygame.draw.rect(surface, TURF_EDGE, rect, border_radius=10)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=10)
    surface.blit(_turf_surface(geometry.playing.size), geometry.playing.topleft)
    _end_zone(surface, geometry.left_end_zone, team_color, match.team_a.team_name, left=True)
    _end_zone(surface, geometry.right_end_zone, opponent.primary, match.team_b.team_name,
              left=False, short=opponent_short)
    for x in (geometry.playing.left, geometry.playing.right):
        pygame.draw.line(surface, TURF_LINE, (x, geometry.turf.top), (x, geometry.turf.bottom), 3)

    flash = overlay.line.flash_end_zone if overlay.line is not None else None
    if flash is not None and overlay.flash_elapsed_ms is not None and overlay.line_progress >= 1:
        elapsed = overlay.flash_elapsed_ms
        if elapsed < EVENT_DURATION_MS:
            zone = geometry.left_end_zone if flash <= 0 else geometry.right_end_zone
            strength = 0.5 + 0.5 * math.sin(elapsed / EVENT_DURATION_MS * math.tau * 2 - math.pi / 2)
            glow = pygame.Surface(zone.size, pygame.SRCALPHA)
            glow.fill((255, 240, 170, round(40 + 120 * strength)))
            surface.blit(glow, zone.topleft)
            pygame.draw.rect(surface, MATCH_FOCUS, zone, 4)

    side = match.possession
    offense_abs = absolute_spot(side, match.offense_field_position)
    in_progress = (
        match.status.value != "completed" and match.conversion_team is None and not kickoff_pending
    )
    los_x = geometry.x_for(offense_abs)
    if in_progress:
        gain_abs = absolute_spot(side, min(100.0, match.offense_field_position + match.yards_to_go))
        gain_x = geometry.x_for(gain_abs)
        if match.offense_field_position + match.yards_to_go < 99.95:
            pygame.draw.line(surface, PLAY_LINE_CASING, (gain_x, geometry.turf.top), (gain_x, geometry.turf.bottom), 6)
            pygame.draw.line(surface, FIRST_DOWN_LINE, (gain_x, geometry.turf.top), (gain_x, geometry.turf.bottom), 3)
        pygame.draw.line(surface, PLAY_LINE_CASING, (los_x, geometry.turf.top), (los_x, geometry.turf.bottom), 5)
        pygame.draw.line(surface, LINE_OF_SCRIMMAGE, (los_x, geometry.turf.top), (los_x, geometry.turf.bottom), 3)
        marker = pygame.Rect(0, 0, 24, 24)
        marker.midtop = (los_x, geometry.turf.top + 30)
        pygame.draw.circle(surface, PLAY_LINE_CASING, marker.center, 13)
        pygame.draw.circle(surface, MATCH_TEXT, marker.center, 11)
        down = plain_font(15).render(str(match.down), True, MATCH_INK)
        surface.blit(down, down.get_rect(center=marker.center))

    tip = None
    if overlay.line is not None:
        tip = draw_play_line(surface, geometry, overlay.line, overlay.line_progress)
    ball_center = (los_x, geometry.ball_y)
    if overlay.line is not None and overlay.line_progress < 1 and tip is not None:
        ball_center = (tip[0], geometry.ball_y)
    _draw_ball(surface, ball_center)
    if in_progress:
        heading = direction(side)
        arrow_y = geometry.turf.bottom - 26
        color = team_color if side is FootballTeamSide.TEAM_A else opponent.accent
        tip_x = los_x + heading * 34
        pygame.draw.line(surface, PLAY_LINE_CASING, (los_x, arrow_y), (tip_x, arrow_y), 7)
        pygame.draw.line(surface, MATCH_TEXT, (los_x, arrow_y), (tip_x, arrow_y), 3)
        _arrow_head(surface, (tip_x, arrow_y), heading, color)
        _tag(
            surface,
            down_text(match),
            (los_x - heading * 8, arrow_y),
            MATCH_PANEL_DEEP,
            ink=MATCH_TEXT,
            align="right" if heading > 0 else "left",
        )

    if not kickoff_pending:
        _draw_scheme_tag(surface, geometry, match, human_scheme_highlight)
    if overlay.banner:
        _draw_banner(surface, geometry, overlay.banner)
    if overlay.drop_hint:
        hint = pygame.Surface(rect.size, pygame.SRCALPHA)
        hint.fill((255, 215, 94, 38))
        surface.blit(hint, rect.topleft)
        pygame.draw.rect(surface, MATCH_FOCUS, rect, 3, border_radius=10)
        _tag(surface, "RELEASE TO PLAY", (rect.centerx, rect.top + 22), MATCH_FOCUS,
             ink=MATCH_INK, font_size=14)
    return geometry


def _draw_scheme_tag(
    surface: pygame.Surface,
    geometry: FieldGeometry,
    match: FootballMatchState,
    human_highlight: bool,
) -> None:
    scheme = match.current_drive_defensive_scheme
    if scheme is None or match.conversion_team is not None:
        return
    human_defending = match.possession is FootballTeamSide.TEAM_B
    if not human_defending:
        return  # the rival's defense call is secret
    definition = DEFENSIVE_SCHEME_CATALOG[scheme.value]
    text = f"YOUR DEFENSE: {definition.name.upper()}"
    fill = MATCH_FOCUS if human_defending and human_highlight else MATCH_PANEL_DEEP
    ink = MATCH_INK if fill == MATCH_FOCUS else MATCH_TEXT
    font_width = geometry.playing.width // 2
    text = fit_text(text, match_font(13), font_width)
    _tag(surface, text, (geometry.playing.right - 10, geometry.turf.top + 18), fill,
         ink=ink, font_size=13, align="right")


def _draw_banner(surface: pygame.Surface, geometry: FieldGeometry, text: str) -> None:
    font = plain_font(34)
    rendered = font.render(text, True, MATCH_INK)
    band = pygame.Rect(0, 0, rendered.get_width() + 80, 52)
    band.center = (geometry.turf.centerx, geometry.turf.top + 70)
    pygame.draw.rect(surface, PLAY_LINE_CASING, band.inflate(6, 6), border_radius=10)
    pygame.draw.rect(surface, MATCH_FOCUS, band, border_radius=8)
    surface.blit(rendered, rendered.get_rect(center=band.center))
