"""The Settings screen's team helmet: the menu helmet in the primary color with
the team's initial on the back of the shell in the secondary color.

``main_menu_art._tinted_helmet`` recolors pixel by pixel, so the cropped,
scaled sprite and the outlined letter are cached by color and size; drawing a
frame with unchanged colors never recolors.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import pygame

from src.ui import main_menu_art
from src.ui.football_ui_kit import plain_font

LOGGER = logging.getLogger(__name__)

LETTER_OUTLINE = pygame.Color("#05101f")
OUTLINE_WIDTH = 2
LETTER_CENTER = (0.30, 0.40)  # of the cropped helmet's width and height
LETTER_HEIGHT = 0.45  # of the helmet height
# The part of the side shell the letter may cover (left, top, right, bottom as
# fractions of the cropped helmet): clear of the facemask (which starts near
# 43% of the width at the letter's lower edge) and the ear hole (below 66%).
LETTER_SAFE_AREA = (0.08, 0.14, 0.42, 0.64)
FALLBACK_LETTER_HEIGHT = 0.55


def team_initial(name: str) -> str:
    """The uppercased first character of the name, or '' when it is empty."""
    stripped = name.strip()
    return stripped[0].upper() if stripped else ""


@lru_cache(maxsize=16)
def helmet_sprite(primary_rgb: tuple[int, int, int], height: int) -> pygame.Surface | None:
    """The tinted menu helmet cropped to its pixels and scaled to ``height``."""
    try:
        sprite = main_menu_art._tinted_helmet(primary_rgb)
    except (OSError, pygame.error, ValueError) as error:
        LOGGER.warning("Could not load the settings helmet artwork: %s", error)
        return None
    sprite = sprite.subsurface(sprite.get_bounding_rect()).copy()
    width = max(1, round(sprite.get_width() * height / sprite.get_height()))
    return pygame.transform.smoothscale(sprite, (width, height))


@lru_cache(maxsize=64)
def outlined_letter(letter: str, size: int, rgb: tuple[int, int, int]) -> pygame.Surface:
    """``letter`` in ``rgb`` with a dark outline, cropped to its drawn pixels."""
    font = plain_font(size)
    fill = font.render(letter, True, rgb)
    edge = font.render(letter, True, LETTER_OUTLINE)
    pad = OUTLINE_WIDTH
    canvas = pygame.Surface((fill.get_width() + pad * 2, fill.get_height() + pad * 2),
                            pygame.SRCALPHA)
    for dx in range(-pad, pad + 1):
        for dy in range(-pad, pad + 1):
            if dx * dx + dy * dy <= pad * pad + 1:
                canvas.blit(edge, (pad + dx, pad + dy))
    canvas.blit(fill, (pad, pad))
    bounds = canvas.get_bounding_rect()
    if bounds.width == 0 or bounds.height == 0:
        return canvas
    return canvas.subsurface(bounds).copy()


@lru_cache(maxsize=128)
def _fitted_size(letter: str, max_width: int, max_height: int) -> int:
    """The largest font size whose outlined letter fits the box."""
    size = max(8, round(max_height * 1.6))
    while size > 8:
        drawn = outlined_letter(letter, size, (255, 255, 255))
        if drawn.get_width() <= max_width and drawn.get_height() <= max_height:
            break
        size -= 1
    return size


def _letter_fit(letter: str, helmet: pygame.Rect, fallback: bool) -> tuple[int, pygame.Rect]:
    """(font size, drawn rect) for ``letter`` on a helmet occupying ``helmet``."""
    width, height = helmet.size
    if fallback:
        center = helmet.center
        box_w, box_h = round(width * 0.8), round(height * FALLBACK_LETTER_HEIGHT)
    else:
        left, top, right, bottom = LETTER_SAFE_AREA
        cx, cy = LETTER_CENTER[0] * width, LETTER_CENTER[1] * height
        half_w = min(cx - left * width, right * width - cx)
        half_h = min(cy - top * height, bottom * height - cy)
        box_w = int(half_w * 2)
        box_h = int(min(LETTER_HEIGHT * height + OUTLINE_WIDTH * 2, half_h * 2))
        center = (helmet.left + round(cx), helmet.top + round(cy))
    size = _fitted_size(letter, box_w, box_h)
    rect = outlined_letter(letter, size, (255, 255, 255)).get_rect()
    rect.center = center
    return size, rect


def letter_rect(letter: str, helmet: pygame.Rect, *, fallback: bool = False) -> pygame.Rect:
    """Where ``letter`` is drawn on a helmet occupying ``helmet`` (screen coordinates)."""
    return _letter_fit(letter, helmet, fallback)[1]


def draw_team_helmet(
    surface: pygame.Surface, box: pygame.Rect, name: str,
    primary: pygame.Color, secondary: pygame.Color, *, height: int,
) -> tuple[pygame.Rect, pygame.Rect | None]:
    """Draw the helmet centered in ``box``; return (helmet rect, letter rect or None).

    Without the artwork it falls back to a rounded square in the primary color.
    """
    letter = team_initial(name)
    sprite = helmet_sprite(tuple(primary[:3]), height)
    fallback = sprite is None
    if sprite is None:
        helmet = pygame.Rect(0, 0, height, height)
        helmet.center = box.center
        radius = max(6, height // 5)
        pygame.draw.rect(surface, primary, helmet, border_radius=radius)
        pygame.draw.rect(surface, LETTER_OUTLINE, helmet, 2, border_radius=radius)
    else:
        helmet = sprite.get_rect(center=box.center)
        surface.blit(sprite, helmet)
    if not letter:
        return helmet, None
    size, rect = _letter_fit(letter, helmet, fallback)
    surface.blit(outlined_letter(letter, size, tuple(secondary[:3])), rect)
    return helmet, rect
