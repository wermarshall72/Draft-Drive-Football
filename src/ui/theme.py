from dataclasses import dataclass

import pygame

from src.profile import COLOR_BY_ID, TeamProfile

_FALLBACK_PRIMARY = COLOR_BY_ID["crimson"].hex_value
_FALLBACK_SECONDARY = COLOR_BY_ID["navy"].hex_value


def _color_or_fallback(
    value: str, fallback: str
) -> tuple[pygame.Color, bool]:
    try:
        return pygame.Color(value), False
    except ValueError:
        return pygame.Color(fallback), True


def _shade(color: pygame.Color, factor: float) -> pygame.Color:
    return pygame.Color(
        round(color.r * factor),
        round(color.g * factor),
        round(color.b * factor),
    )


@dataclass(frozen=True)
class Theme:
    canvas: pygame.Color
    panel: pygame.Color
    panel_alt: pygame.Color
    text: pygame.Color
    muted: pygame.Color
    border: pygame.Color
    primary: pygame.Color
    primary_dark: pygame.Color
    secondary: pygame.Color
    secondary_dark: pygame.Color
    danger: pygame.Color
    warning: str | None

    @classmethod
    def from_profile(cls, profile: TeamProfile | None) -> "Theme":
        primary_hex = (
            profile.primary_color.hex_value if profile is not None else _FALLBACK_PRIMARY
        )
        secondary_hex = (
            profile.secondary_color.hex_value
            if profile is not None
            else _FALLBACK_SECONDARY
        )
        primary, primary_fallback = _color_or_fallback(
            primary_hex, _FALLBACK_PRIMARY
        )
        secondary, secondary_fallback = _color_or_fallback(
            secondary_hex, _FALLBACK_SECONDARY
        )
        return cls(
            canvas=pygame.Color("#10151b"),
            panel=pygame.Color("#1a242e"),
            panel_alt=pygame.Color("#24313d"),
            text=pygame.Color("#f7f1e3"),
            muted=pygame.Color("#aeb8c2"),
            border=pygame.Color("#40505e"),
            primary=primary,
            primary_dark=_shade(primary, 0.28),
            secondary=secondary,
            secondary_dark=_shade(secondary, 0.28),
            danger=pygame.Color("#f06a57"),
            warning=(
                "A saved team color could not be applied; using the fallback palette."
                if primary_fallback or secondary_fallback
                else None
            ),
        )
