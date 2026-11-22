"""Team-colored coach portraits for the draft, shop, and Depth Chart."""

from functools import lru_cache
from pathlib import Path

import pygame

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

