"""The end of a rival drive: the field's SKIP button and the drive result box.

Presentation only. The box announces how the rival's drive ended (never the
rival's defense call) over the drive chart, shows the score, and offers one
button that plays the held possession change.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from src.ui.football_match_events import RivalDriveEnd
from src.ui.football_match_field import field_geometry
from src.ui.football_match_palette import (
    MATCH_INK, MATCH_MUTED, MATCH_PANEL, MATCH_PANEL_EDGE, MATCH_PANEL_HIGH, MATCH_TEXT,
    blit_text, match_font, mix, plain_font,
)
from src.ui.football_ui_kit import MATCH_FOCUS, team_accent
from src.ui.text import fit_text

SKIP_DRIVE_LABEL = "SKIP TO END OF DRIVE"
SKIP_LABEL = "SKIP"
SKIP_VARIANT = "match-skip"
BOX_BUTTON_VARIANT = "drive-box"
SKIP_FONT_SIZE = 13
BOX_SIZE = (540, 206)
BOX_ALPHA = 212  # about 83% opaque, so the drive chart shows through
BOX_BUTTON_SIZE = (200, 36)
BOX_GREY = mix(MATCH_PANEL_HIGH, pygame.Color("#8d99a6"), 0.32)


def skip_button_rect(field_rect: pygame.Rect, label: str) -> pygame.Rect:
    """Bottom-right of the playing area, under the yard numbers and clear of the end zone."""
    geometry = field_geometry(field_rect)
    width = match_font(SKIP_FONT_SIZE).size(label)[0] + 24
    rect = pygame.Rect(0, 0, width, 22)
    rect.bottomright = (geometry.playing.right - 8, geometry.turf.bottom - 3)
    return rect


@dataclass(frozen=True)
class ScoreSide:
    name: str
    score: int
    primary: pygame.Color
    secondary: pygame.Color


def box_rect(field_rect: pygame.Rect) -> pygame.Rect:
    rect = pygame.Rect((0, 0), BOX_SIZE)
    rect.center = field_rect.center
    return rect


def box_button_rect(field_rect: pygame.Rect) -> pygame.Rect:
    box = box_rect(field_rect)
    rect = pygame.Rect((0, 0), BOX_BUTTON_SIZE)
    rect.midbottom = (box.centerx, box.bottom - 14)
    return rect


def _fitted_font(text: str, width: int, sizes: tuple[int, ...]) -> pygame.font.Font:
    for size in sizes:
        font = plain_font(size)
        if font.size(text)[0] <= width:
            return font
    return plain_font(sizes[-1])


def _outlined_number(
    surface: pygame.Surface, text: str, center: tuple[int, int], fill: pygame.Color,
    outline: pygame.Color,
) -> pygame.Rect:
    """A large score filled with the team's primary and outlined in its secondary."""
    font = plain_font(42)
    edge = font.render(text, True, outline)
    body = font.render(text, True, fill)
    rect = body.get_rect(center=center)
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            if abs(dx) == 2 or abs(dy) == 2:
                surface.blit(edge, rect.move(dx, dy))
    surface.blit(body, rect)
    return rect.inflate(4, 4)


def score_colors(primary: pygame.Color, secondary: pygame.Color) -> tuple[pygame.Color, pygame.Color]:
    """Fill and outline kept visible on navy; a fill matching its outline gets ink edges."""
    fill = team_accent(primary)
    outline = team_accent(secondary)
    if _distance(fill, outline) < 60:
        outline = MATCH_INK if sum(fill[:3]) > 380 else MATCH_TEXT
    return fill, outline


def _distance(first: pygame.Color, second: pygame.Color) -> float:
    return sum((a - b) ** 2 for a, b in zip(first[:3], second[:3])) ** 0.5


def draw_drive_box(
    surface: pygame.Surface,
    field_rect: pygame.Rect,
    drive: RivalDriveEnd,
    human: ScoreSide,
    rival: ScoreSide,
    *,
    focused: bool,
    hovered: bool,
    pressed: bool,
) -> pygame.Rect:
    """Draw the box over the middle of the field; returns its button's rect."""
    rect = box_rect(field_rect)
    shadow = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shadow, (*MATCH_INK[:3], 150), shadow.get_rect(), border_radius=16)
    surface.blit(shadow, rect.move(0, 5).topleft)
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel, (*MATCH_PANEL[:3], BOX_ALPHA), panel.get_rect(), border_radius=16)
    surface.blit(panel, rect.topleft)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=16)

    inner = rect.inflate(-40, 0)
    headline_font = _fitted_font(drive.headline, inner.width, (30, 26, 22, 19))
    headline = fit_text(drive.headline, headline_font, inner.width)
    blit_text(surface, headline_font, headline, MATCH_TEXT, rect,
              midtop=(rect.centerx, rect.top + 14))
    if drive.detail:
        detail_font = match_font(13)
        blit_text(surface, detail_font, fit_text(drive.detail, detail_font, inner.width),
                  MATCH_MUTED, rect, midtop=(rect.centerx, rect.top + 50))

    name_font = match_font(13)
    half = inner.width // 2
    for index, side in enumerate((human, rival)):
        cell = pygame.Rect(inner.left + index * half, rect.top + 72, half, 74)
        blit_text(surface, name_font, fit_text(side.name.upper(), name_font, half - 16),
                  MATCH_TEXT, cell, midtop=(cell.centerx, cell.top))
        fill, outline = score_colors(side.primary, side.secondary)
        _outlined_number(surface, str(side.score), (cell.centerx, cell.top + 46), fill, outline)
    pygame.draw.line(surface, MATCH_PANEL_EDGE, (rect.centerx, rect.top + 86),
                     (rect.centerx, rect.top + 136), 1)

    button = box_button_rect(field_rect)
    draw_box_button(surface, button, drive.button, focused=focused, hovered=hovered, pressed=pressed)
    return button


def draw_box_button(
    surface: pygame.Surface, rect: pygame.Rect, label: str, *, focused: bool, hovered: bool,
    pressed: bool,
) -> None:
    """The neutral grey button at the bottom of the box."""
    rect = rect.move(0, 2) if pressed else rect
    fill = mix(BOX_GREY, MATCH_TEXT, 0.12) if focused or hovered else BOX_GREY
    if focused:
        pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(6, 6), 2, border_radius=11)
    pygame.draw.rect(surface, fill, rect, border_radius=9)
    pygame.draw.rect(surface, MATCH_FOCUS if focused else mix(BOX_GREY, MATCH_TEXT, 0.35), rect, 2,
                     border_radius=9)
    font = match_font(16)
    blit_text(surface, font, fit_text(label, font, rect.width - 20), MATCH_TEXT, rect,
              center=rect.center)
