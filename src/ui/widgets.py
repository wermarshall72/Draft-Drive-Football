from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import pygame

from src.ui.theme import Theme


@dataclass
class Button:
    label: str
    action: Callable[[], None]
    rect: pygame.Rect
    enabled: bool = True
    focused: bool = False
    variant: str = "quiet"
    pressed: bool = False

    def draw(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        theme: Theme,
        *,
        hovered: bool = False,
        pressed: bool = False,
    ) -> None:
        if self.variant == "primary" and self.enabled:
            fill = theme.primary_accent if self.focused or hovered else theme.primary
            border = theme.primary_accent
            foreground = theme.primary_ink
        elif not self.enabled:
            fill = theme.panel
            border = theme.border_soft
            foreground = theme.muted
        elif self.focused or hovered:
            fill = theme.panel_high
            border = theme.primary_accent
            foreground = theme.text
        else:
            fill = theme.panel
            border = theme.border_soft
            foreground = theme.text

        button_rect = self.rect.move(0, 3) if pressed and self.enabled else self.rect
        _draw_shadow(
            surface,
            button_rect,
            theme,
            radius=14,
            strength=34 if pressed else 52,
        )
        pygame.draw.rect(surface, fill, button_rect, border_radius=14)
        pygame.draw.rect(
            surface,
            border,
            button_rect,
            width=2 if self.focused or hovered else 1,
            border_radius=14,
        )
        pygame.draw.line(
            surface,
            _shade(fill, 1.22),
            (button_rect.left + 14, button_rect.top + 2),
            (button_rect.right - 14, button_rect.top + 2),
            1,
        )
        pygame.draw.line(
            surface,
            _shade(fill, 0.78),
            (button_rect.left + 14, button_rect.bottom - 2),
            (button_rect.right - 14, button_rect.bottom - 2),
            1,
        )
        if self.focused or hovered:
            pygame.draw.rect(
                surface,
                theme.secondary_accent,
                pygame.Rect(
                    button_rect.left,
                    button_rect.top + 10,
                    3,
                    button_rect.height - 20,
                ),
                border_radius=2,
            )
        label = font.render(self.label, True, foreground)
        surface.blit(
            label,
            label.get_rect(midleft=(button_rect.left + 18, button_rect.centery)),
        )
        if self.variant == "primary" and self.enabled:
            pygame.draw.polygon(
                surface,
                foreground,
                (
                    (button_rect.right - 20, button_rect.centery - 6),
                    (button_rect.right - 10, button_rect.centery),
                    (button_rect.right - 20, button_rect.centery + 6),
                ),
            )


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    theme: Theme,
    *,
    selected: bool = False,
    fill: pygame.Color | None = None,
) -> None:
    panel_fill = fill or theme.panel
    radius = 16
    _draw_shadow(surface, rect, theme, radius=radius, strength=48)
    pygame.draw.rect(surface, panel_fill, rect, border_radius=radius)
    previous_clip = surface.get_clip()
    band_height = max(1, rect.height // 8)
    for band in range(8):
        top = rect.top + band * band_height
        bottom = rect.bottom if band == 7 else min(rect.bottom, top + band_height)
        amount = 0.13 * (1 - band / 7)
        surface.set_clip(pygame.Rect(rect.left, top, rect.width, bottom - top))
        pygame.draw.rect(
            surface,
            _mix(panel_fill, theme.panel_top, amount),
            rect,
            border_radius=radius,
        )
    surface.set_clip(previous_clip)
    pygame.draw.rect(
        surface,
        theme.primary_accent if selected else theme.border_soft,
        rect,
        width=2 if selected else 1,
        border_radius=radius,
    )
    pygame.draw.line(
        surface,
        _shade(panel_fill, 1.55),
        (rect.left + radius, rect.top + 1),
        (rect.right - radius, rect.top + 1),
        1,
    )
    pygame.draw.line(
        surface,
        _shade(panel_fill, 0.76),
        (rect.left + radius, rect.bottom - 2),
        (rect.right - radius, rect.bottom - 2),
        1,
    )
    if selected:
        marker = pygame.Rect(rect.left + 18, rect.top, rect.width - 36, 3)
        pygame.draw.rect(surface, theme.secondary_accent, marker, border_radius=2)


def _draw_shadow(
    surface: pygame.Surface,
    rect: pygame.Rect,
    theme: Theme,
    *,
    radius: int,
    strength: int,
) -> None:
    shadow = _shadow_surface(
        rect.width,
        rect.height,
        tuple(theme.shadow[:3]),
        radius,
        strength,
    )
    padding = 18
    surface.blit(shadow, (rect.left - padding, rect.top - padding + 3))


@lru_cache(maxsize=128)
def _shadow_surface(
    width: int,
    height: int,
    color: tuple[int, int, int],
    radius: int,
    strength: int,
) -> pygame.Surface:
    padding = 18
    shadow = pygame.Surface(
        (width + padding * 2, height + padding * 2),
        pygame.SRCALPHA,
    )
    pygame.draw.rect(
        shadow,
        (*color, strength),
        pygame.Rect(padding, padding, width, height),
        border_radius=radius,
    )
    return pygame.transform.gaussian_blur(shadow, 7)


def _shade(color: pygame.Color, factor: float) -> pygame.Color:
    return pygame.Color(
        min(255, round(color.r * factor)),
        min(255, round(color.g * factor)),
        min(255, round(color.b * factor)),
        color.a,
    )


def _mix(
    first: pygame.Color, second: pygame.Color, amount: float
) -> pygame.Color:
    return pygame.Color(
        round(first.r + (second.r - first.r) * amount),
        round(first.g + (second.g - first.g) * amount),
        round(first.b + (second.b - first.b) * amount),
    )


def draw_text(
    surface: pygame.Surface,
    text: str,
    position: tuple[int, int],
    font: pygame.font.Font,
    color: pygame.Color,
) -> None:
    surface.blit(font.render(text, True, color), position)


def draw_wrapped_text(
    surface: pygame.Surface,
    text: str,
    rect: pygame.Rect,
    font: pygame.font.Font,
    color: pygame.Color,
    *,
    line_gap: int = 6,
) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and font.size(candidate)[0] > rect.width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    y = rect.top
    for line in lines:
        rendered = font.render(line, True, color)
        if y + rendered.get_height() > rect.bottom:
            break
        surface.blit(rendered, (rect.left, y))
        y += rendered.get_height() + line_gap
