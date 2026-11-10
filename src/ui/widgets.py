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

    def draw(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font,
        theme: Theme,
        *,
        hovered: bool = False,
    ) -> None:
        if not self.enabled:
            fill = theme.panel
            border = theme.border
            foreground = theme.muted
        elif self.focused or hovered:
            fill = theme.primary
            border = theme.secondary
            foreground = theme.text
        else:
            fill = theme.panel_alt
            border = theme.border
            foreground = theme.text

        pygame.draw.rect(surface, fill, self.rect, border_radius=8)
        pygame.draw.rect(
            surface,
            border,
            self.rect,
            width=3 if self.focused or hovered else 1,
            border_radius=8,
        )
        label = font.render(self.label, True, foreground)
        surface.blit(
            label,
            label.get_rect(midleft=(self.rect.left + 20, self.rect.centery)),
        )
        if self.focused or hovered:
            pygame.draw.polygon(
                surface,
                theme.secondary,
                (
                    (self.rect.right - 20, self.rect.centery - 6),
                    (self.rect.right - 10, self.rect.centery),
                    (self.rect.right - 20, self.rect.centery + 6),
                ),
            )


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    theme: Theme,
    *,
    selected: bool = False,
) -> None:
    pygame.draw.rect(surface, theme.panel, rect, border_radius=12)
    pygame.draw.rect(
        surface,
        theme.primary if selected else theme.border,
        rect,
        width=3 if selected else 1,
        border_radius=12,
    )
    if selected:
        marker = pygame.Rect(rect.left, rect.top + 16, 5, rect.height - 32)
        pygame.draw.rect(surface, theme.secondary, marker, border_radius=3)


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
