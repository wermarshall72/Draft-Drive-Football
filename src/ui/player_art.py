"""One original generated player illustration with runtime team-color masks."""

from functools import lru_cache
from pathlib import Path

import pygame

_ASSET_DIR = Path(__file__).parent / "assets" / "draft_players"
_PLATFORM_SHADOW = pygame.Color("#101712")
_PLATFORM_DARK = pygame.Color("#536846")
_PLATFORM_LIGHT = pygame.Color("#879257")
_PLATFORM_HIGHLIGHT = pygame.Color("#bac184")


@lru_cache(maxsize=1)
def _player_layers() -> tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    return tuple(
        pygame.image.load(_ASSET_DIR / f"player_{layer}.png")
        for layer in ("base", "primary_mask", "secondary_mask")
    )


@lru_cache(maxsize=32)
def _tinted_player(
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
) -> pygame.Surface:
    base, primary_mask, secondary_mask = _player_layers()
    sprite = base.copy()
    for mask, color in zip((primary_mask, secondary_mask), (primary, secondary)):
        tint = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
        tint.fill((*color, 255))
        tint.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        sprite.blit(tint, (0, 0))
    return sprite


def draw_draft_player(
    surface: pygame.Surface,
    rect: pygame.Rect,
    primary: pygame.Color,
    secondary: pygame.Color,
) -> None:
    """Draw the shared standing-player sprite in the saved team colors."""
    pygame.draw.ellipse(
        surface,
        _PLATFORM_SHADOW,
        pygame.Rect(rect.centerx - 76, rect.bottom - 20, 152, 15),
    )
    platform = pygame.Rect(rect.centerx - 75, rect.bottom - 25, 150, 21)
    pygame.draw.ellipse(surface, _PLATFORM_DARK, platform)
    pygame.draw.ellipse(surface, _PLATFORM_LIGHT, platform.inflate(-4, -5))
    pygame.draw.arc(
        surface,
        _PLATFORM_HIGHLIGHT,
        platform.inflate(-12, -8),
        0.1,
        2.9,
        2,
    )

    sprite = _tinted_player(tuple(primary[:3]), tuple(secondary[:3]))
    height = max(1, rect.height - 12)
    width = min(rect.width - 4, round(height * 0.64))
    scaled = pygame.transform.smoothscale(sprite, (width, height))
    destination = scaled.get_rect(midbottom=(rect.centerx, rect.bottom - 17))
    surface.blit(scaled, destination)
