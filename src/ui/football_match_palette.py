"""Shared navy-stadium colors and fonts for the match presentation."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

import pygame

from src.ui.coach_fonts import staff_font
from src.ui.stat_icons import StatIconFont, without_stat_icons

# Stadium shell, matching the navy draft/shop/menu screens.
MATCH_CANVAS = pygame.Color("#061629")
MATCH_CANVAS_GLOW = pygame.Color("#0c2747")
MATCH_PANEL = pygame.Color("#0e2b47")
MATCH_PANEL_DEEP = pygame.Color("#0a2038")
MATCH_PANEL_HIGH = pygame.Color("#173d63")
MATCH_PANEL_EDGE = pygame.Color("#507397")
MATCH_PANEL_EDGE_SOFT = pygame.Color("#2a4a6b")
MATCH_TEXT = pygame.Color("#eef5ff")
MATCH_MUTED = pygame.Color("#a9bdd2")
MATCH_DIM = pygame.Color("#6f87a1")
MATCH_FOCUS = pygame.Color("#ffd75e")
MATCH_INK = pygame.Color("#08182b")
MATCH_DANGER = pygame.Color("#ff8a80")
MATCH_GOLD = pygame.Color("#ffd75e")

# The local AI wears a neutral steel uniform so it never clashes with team colors.
MATCH_OPPONENT = pygame.Color("#7d8ea3")
MATCH_OPPONENT_DARK = pygame.Color("#3f4d5e")

# Turf.
TURF_DARK = pygame.Color("#1f6b34")
TURF_LIGHT = pygame.Color("#257a3c")
TURF_LINE = pygame.Color("#e9f5e7")
TURF_EDGE = pygame.Color("#123f20")

# Play-line meaning is fixed: run red, pass blue, everything else grey. Each is
# drawn over a dark casing so it reads on turf and on any end-zone color.
PLAY_LINE_RUN = pygame.Color("#ff4f4f")
PLAY_LINE_PASS = pygame.Color("#45b6ff")
PLAY_LINE_OTHER = pygame.Color("#d5dbe3")
PLAY_LINE_CASING = pygame.Color("#06111f")

# Outcome text uses lighter tints of the same meanings for contrast on navy.
OUTCOME_RUN = pygame.Color("#ff6b6b")
OUTCOME_PASS = pygame.Color("#5cc2ff")
OUTCOME_OTHER = pygame.Color("#dfe5ec")

LINE_OF_SCRIMMAGE = pygame.Color("#3fa9ff")
FIRST_DOWN_LINE = pygame.Color("#ffe03d")


@lru_cache(maxsize=None)
def match_font(size: int, bold: bool = True) -> StatIconFont:
    """Barlow, shared with the shop and draft screens."""
    return staff_font(size, semibold=bold)


@lru_cache(maxsize=None)
def plain_font(size: int, bold: bool = True) -> pygame.font.Font:
    """A font that never inserts stat icons, for card names like 'Power Toss'."""
    return without_stat_icons(match_font(size, bold))


def mix(first: pygame.Color, second: pygame.Color, amount: float) -> pygame.Color:
    return pygame.Color(
        round(first.r + (second.r - first.r) * amount),
        round(first.g + (second.g - first.g) * amount),
        round(first.b + (second.b - first.b) * amount),
    )


# -- text placement with an optional fit audit -------------------------------------

_TEXT_AUDIT: list[tuple[str, pygame.Rect, pygame.Rect]] | None = None


@contextmanager
def text_audit() -> Iterator[list[tuple[str, pygame.Rect, pygame.Rect]]]:
    """Record every ``blit_text`` call as (text, drawn rect, container) for tests."""
    global _TEXT_AUDIT
    previous = _TEXT_AUDIT
    records: list[tuple[str, pygame.Rect, pygame.Rect]] = []
    _TEXT_AUDIT = records
    try:
        yield records
    finally:
        _TEXT_AUDIT = previous


def blit_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    color: pygame.Color,
    container: pygame.Rect,
    **anchor: tuple[int, int] | int,
) -> pygame.Rect:
    """Render ``text`` at ``anchor`` (pygame Rect keywords); it must fit ``container``."""
    rendered = font.render(text, True, color)
    rect = rendered.get_rect(**anchor)
    surface.blit(rendered, rect)
    if _TEXT_AUDIT is not None:
        _TEXT_AUDIT.append((text, rect, pygame.Rect(container)))
    return rect
