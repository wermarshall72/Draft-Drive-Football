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


def _tint_to_readable(color: pygame.Color) -> pygame.Color:
    if color.r == color.g == color.b:
        return color
    hue, _, _, _ = color.hsva
    accent = pygame.Color(0)
    accent.hsva = (hue, 46, 100, 100)
    return accent


def _contrast_ink(color: pygame.Color) -> pygame.Color:
    luminance = (color.r * 299 + color.g * 587 + color.b * 114) / 1000
    return pygame.Color("#10151b") if luminance > 155 else pygame.Color("#fffaf0")


@dataclass(frozen=True)
class Theme:
    canvas: pygame.Color
    canvas_lift: pygame.Color
    panel: pygame.Color
    panel_alt: pygame.Color
    panel_high: pygame.Color
    panel_top: pygame.Color
    text: pygame.Color
    muted: pygame.Color
    border: pygame.Color
    border_soft: pygame.Color
    shadow: pygame.Color
    primary: pygame.Color
    primary_dark: pygame.Color
    primary_accent: pygame.Color
    primary_ink: pygame.Color
    secondary: pygame.Color
    secondary_dark: pygame.Color
    secondary_accent: pygame.Color
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
        primary_accent = _tint_to_readable(primary)
        secondary_accent = _tint_to_readable(secondary)
        return cls(
            canvas=pygame.Color("#10161b"),
            canvas_lift=pygame.Color("#18232b"),
            panel=pygame.Color("#1a2730"),
            panel_alt=pygame.Color("#22323b"),
            panel_high=pygame.Color("#2b3e47"),
            panel_top=pygame.Color("#30434c"),
            text=pygame.Color("#f5f2e9"),
            muted=pygame.Color("#a7b2b4"),
            border=pygame.Color("#3b4b50"),
            border_soft=pygame.Color("#29373d"),
            shadow=pygame.Color("#05090c"),
            primary=primary,
            primary_dark=_shade(primary, 0.18),
            primary_accent=primary_accent,
            primary_ink=_contrast_ink(primary_accent),
            secondary=secondary,
            secondary_dark=_shade(secondary, 0.18),
            secondary_accent=secondary_accent,
            danger=pygame.Color("#f06a57"),
            warning=(
                "A saved team color could not be applied; using the fallback palette."
                if primary_fallback or secondary_fallback
                else None
            ),
        )
