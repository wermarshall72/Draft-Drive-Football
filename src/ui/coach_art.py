"""Original recruiting-room artwork and playbook marks."""

import logging
from functools import lru_cache
from pathlib import Path

import pygame

from src.ui.theme import readable_ink, relative_luminance

_LOG = logging.getLogger(__name__)
_TABLE_PATH = Path(__file__).parent / "assets" / "recruiting_table.png"
_COACH_DIR = Path(__file__).parent / "assets" / "draft_coaches"
COACH_PORTRAITS = {
    "ground_and_pound": "ground_and_pound",
    "option_spread": "option_spread",
    "air_raid": "air_raid",
    "pro_style": "pro_style",
    "run_stop": "run_stop",
    "pressure_blitz": "pressure_blitz",
    "coverage": "coverage",
    "ball_hawk": "ball_hawk",
    "balanced_offense": "balanced",
    "balanced_defense": "balanced",
}


@lru_cache(maxsize=9)
def coach_portrait_layers(coach_id: str) -> tuple[pygame.Surface, pygame.Surface]:
    name = COACH_PORTRAITS[coach_id]
    return tuple(
        pygame.image.load(_COACH_DIR / f"{name}_{layer}.png")
        for layer in ("base", "primary")
    )


@lru_cache(maxsize=128)
def _colored_coach(coach_id: str, primary: tuple[int, int, int]) -> pygame.Surface:
    base, mask = coach_portrait_layers(coach_id)
    sprite = base.copy()
    tint = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
    tint.fill((*primary, 255))
    tint.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    sprite.blit(tint, (0, 0))
    return sprite


def draw_coach_portrait(
    surface: pygame.Surface, rect: pygame.Rect, coach_id: str, primary: pygame.Color,
) -> None:
    sprite = _colored_coach(coach_id, tuple(primary[:3]))
    scale = min(rect.width / sprite.get_width(), rect.height / sprite.get_height())
    size = (max(1, round(sprite.get_width() * scale)),
            max(1, round(sprite.get_height() * scale)))
    scaled = pygame.transform.scale(sprite, size)
    surface.blit(scaled, scaled.get_rect(midbottom=rect.midbottom))


@lru_cache(maxsize=1)
def recruiting_table() -> pygame.Surface | None:
    try:
        image = pygame.image.load(str(_TABLE_PATH))
        return pygame.transform.smoothscale(image, (1280, 720))
    except (OSError, pygame.error) as error:
        _LOG.warning("Could not load recruiting table artwork: %s", error)
        return None


def draw_recruiting_table(surface: pygame.Surface) -> None:
    image = recruiting_table()
    if image is None:
        surface.fill("#282c24")
        for y in range(0, surface.get_height(), 90):
            pygame.draw.line(surface, "#414038", (0, y), (surface.get_width(), y), 2)
    else:
        background = (
            image if surface.get_size() == image.get_size()
            else pygame.transform.smoothscale(image, surface.get_size())
        )
        surface.blit(background, (0, 0))


def draw_playbook_mark(
    surface: pygame.Surface, rect: pygame.Rect, *, offense: bool, color: pygame.Color
) -> None:
    """Draw the original offset X/O marks in the selected team colors."""
    surface.blit(_playbook_mark(rect.size, offense, tuple(color[:3])), rect.topleft)


@lru_cache(maxsize=128)
def _playbook_mark(
    size: tuple[int, int], offense: bool, color: tuple[int, int, int]
) -> pygame.Surface:
    scale = 3
    ink = pygame.Color(*color)
    ghost = readable_ink(ink)
    mark = pygame.Surface((size[0] * scale, size[1] * scale), pygame.SRCALPHA)
    w, h = mark.get_size()
    paper = pygame.Color("#a1a8a3")
    low, high = sorted((relative_luminance(ink), relative_luminance(paper)))
    needs_keyline = (high + 0.05) / (low + 0.05) < 3
    if offense:
        if needs_keyline:
            for path in (
                [(w * 0.22, h * 0.20), (w * 0.50, h * 0.49), (w * 0.77, h * 0.78)],
                [(w * 0.76, h * 0.19), (w * 0.50, h * 0.50), (w * 0.20, h * 0.79)],
            ):
                pygame.draw.lines(mark, readable_ink(paper), False, path, 27)
        for stroke_color, offset, width in ((ghost, 6, 9), (ink, 0, 15)):
            pygame.draw.lines(mark, stroke_color, False, [
                (w * 0.22 + offset, h * 0.20), (w * 0.50, h * 0.49),
                (w * 0.77 + offset, h * 0.78),
            ], width)
            pygame.draw.lines(mark, stroke_color, False, [
                (w * 0.76 + offset, h * 0.19), (w * 0.50, h * 0.50),
                (w * 0.20 + offset, h * 0.79),
            ], width)
    else:
        if needs_keyline:
            pygame.draw.ellipse(mark, readable_ink(paper),
                                (w * 0.21, h * 0.19, w * 0.60, h * 0.61), 27)
        pygame.draw.ellipse(mark, ghost, (w * 0.18, h * 0.16, w * 0.65, h * 0.68), 9)
        pygame.draw.ellipse(mark, ink, (w * 0.21, h * 0.19, w * 0.60, h * 0.61), 15)
    return pygame.transform.smoothscale(mark, size)
