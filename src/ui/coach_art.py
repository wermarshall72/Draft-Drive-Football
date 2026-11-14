"""Original recruiting-room artwork and compact sideline illustrations."""

import logging
from functools import lru_cache
from pathlib import Path

import pygame

_LOG = logging.getLogger(__name__)
_TABLE_PATH = Path(__file__).parent / "assets" / "recruiting_table.png"


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


def draw_sideline_coach(
    surface: pygame.Surface, rect: pygame.Rect, *, offense: bool
) -> None:
    """Draw an anonymous sideline figure, not a depiction of a real person."""
    ground = pygame.Color("#344e46" if offense else "#713f32")
    shade = pygame.Color("#192822" if offense else "#422822")
    paper = pygame.Color("#e5d4af")
    pygame.draw.rect(surface, ground, rect)
    pygame.draw.line(surface, "#b5a684", (rect.left + 6, rect.bottom - 13),
                     (rect.right - 6, rect.bottom - 13))
    center = rect.centerx
    pygame.draw.ellipse(surface, shade, (center - 23, rect.top + 54, 46, 44))
    pygame.draw.polygon(surface, paper, [
        (center - 6, rect.top + 54), (center, rect.top + 66),
        (center + 6, rect.top + 54),
    ])
    pygame.draw.ellipse(surface, paper, (center - 11, rect.top + 24, 22, 30))
    pygame.draw.line(surface, shade, (center + 3, rect.top + 38),
                     (center + 8, rect.top + 38), 1)
    pygame.draw.line(surface, shade, (center + 2, rect.top + 48),
                     (center + 8, rect.top + 48), 1)
    pygame.draw.arc(surface, shade, (center - 16, rect.top + 19, 32, 34), 0, 3.14, 3)
    pygame.draw.rect(surface, shade, (center - 17, rect.top + 34, 5, 12))
    pygame.draw.line(surface, shade, (center + 13, rect.top + 40),
                     (center + 18, rect.top + 46), 2)
    pygame.draw.line(surface, shade, (center + 18, rect.top + 46),
                     (center + 10, rect.top + 46), 2)
    pygame.draw.polygon(surface, shade, [
        (center - 13, rect.top + 26), (center - 9, rect.top + 17),
        (center + 9, rect.top + 17), (center + 13, rect.top + 26),
        (center + 18, rect.top + 28), (center - 13, rect.top + 29),
    ])
