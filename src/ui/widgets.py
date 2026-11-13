from dataclasses import dataclass
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
            fill = theme.primary_accent
            border = theme.primary_accent
            foreground = theme.primary_ink
        elif not self.enabled:
            fill = theme.panel
            border = theme.border_soft
            foreground = theme.muted
        elif self.focused or hovered:
            fill = theme.panel_high
            fill = _mix(fill, theme.primary_accent, 0.18)
            border = theme.secondary_accent if self.focused else theme.border
            foreground = theme.text
        else:
            fill = theme.panel
            border = theme.border_soft
            foreground = theme.text

        button_rect = self.rect.move(0, 2) if pressed and self.enabled else self.rect
        if self.focused and self.enabled:
            focus_rect = button_rect.inflate(6, 6)
            pygame.draw.rect(
                surface,
                theme.secondary_accent,
                focus_rect,
                width=2,
                border_radius=10,
            )
        pygame.draw.rect(surface, fill, button_rect, border_radius=8)
        pygame.draw.rect(
            surface,
            border,
            button_rect,
            width=2 if self.focused else 1,
            border_radius=8,
        )
        label = font.render(self.label, True, foreground)
        max_width = max(1, button_rect.width - 22)
        if label.get_width() > max_width:
            target_height = max(1, round(label.get_height() * max_width / label.get_width()))
            label = pygame.transform.smoothscale(label, (max_width, target_height))
        surface.blit(label, label.get_rect(center=button_rect.center))


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    theme: Theme,
    *,
    selected: bool = False,
    fill: pygame.Color | None = None,
) -> None:
    panel_fill = fill or theme.panel
    radius = 10
    pygame.draw.rect(surface, panel_fill, rect, border_radius=radius)
    pygame.draw.rect(
        surface,
        theme.primary_accent if selected else theme.border_soft,
        rect,
        width=2 if selected else 1,
        border_radius=radius,
    )
    if selected:
        marker = pygame.Rect(rect.left + 12, rect.top, rect.width - 24, 3)
        pygame.draw.rect(surface, theme.secondary_accent, marker, border_radius=2)


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
