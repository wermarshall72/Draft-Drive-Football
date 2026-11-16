"""Pixel-art draft poses and independently tinted uniform and skin layers."""

from functools import lru_cache
from pathlib import Path

import pygame

_ASSET_DIR = Path(__file__).parent / "assets" / "draft_players"
SKIN_TONES = (
    (255, 213, 180), (235, 181, 139), (201, 143, 102),
    (165, 108, 73), (126, 76, 48), (91, 52, 33),
)


@lru_cache(maxsize=2)
def _player_layers(active: bool) -> tuple[pygame.Surface, ...]:
    pose = "active" if active else "standing"
    return tuple(
        pygame.image.load(_ASSET_DIR / f"{pose}_{layer}.png")
        for layer in ("base", "primary", "secondary", "skin")
    )


@lru_cache(maxsize=128)
def _tinted_player(
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
    skin: tuple[int, int, int],
    active: bool,
) -> pygame.Surface:
    base, *masks = _player_layers(active)
    sprite = base.copy()
    for mask, color in zip(masks, (primary, secondary, skin)):
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
    skin: tuple[int, int, int] = SKIN_TONES[2],
    active: bool = False,
) -> None:
    sprite = _tinted_player(tuple(primary[:3]), tuple(secondary[:3]), skin, active)
    scale = min(rect.width / sprite.get_width(), rect.height / sprite.get_height())
    size = (max(1, round(sprite.get_width() * scale)),
            max(1, round(sprite.get_height() * scale)))
    scaled = pygame.transform.scale(sprite, size)
    surface.blit(scaled, scaled.get_rect(center=rect.center))
