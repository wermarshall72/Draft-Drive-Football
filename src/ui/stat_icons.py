"""Inline Power, Stamina, and Volatility icons for any rendered text."""

import re
from functools import lru_cache
from pathlib import Path

import pygame

ICON_DIR = Path(__file__).parent / "assets" / "stat_icons"
STAT_ICON_FILES = {
    "power": "power.png",
    "stamina": "stamina.png",
    "volatility": "volatility.png",
}
STAT_PATTERN = re.compile(r"\b(power|stamina|volatility)\b", re.IGNORECASE)
_ICON_HEIGHT_RATIO = 0.8
_MIN_ICON_HEIGHT = 8
_ICON_GAP = 2


@lru_cache(maxsize=None)
def _source_icon(stat: str) -> pygame.Surface:
    image = pygame.image.load(ICON_DIR / STAT_ICON_FILES[stat])
    return image.convert_alpha() if pygame.display.get_surface() else image


def icon_height_for(font_height: int) -> int:
    return max(_MIN_ICON_HEIGHT, round(font_height * _ICON_HEIGHT_RATIO))


@lru_cache(maxsize=64)
def stat_icon(stat: str, height: int) -> pygame.Surface:
    """Return the stat's icon scaled to ``height`` with nearest-neighbour sampling."""
    source = _source_icon(stat.lower())
    width = max(1, round(source.get_width() * height / source.get_height()))
    return pygame.transform.scale(source, (width, height))


def _segments(text: str) -> list[tuple[str, str | None]]:
    """Split text into (text, stat) pieces; icons precede their stat word."""
    pieces: list[tuple[str, str | None]] = []
    position = 0
    for match in STAT_PATTERN.finditer(text):
        if match.start() > position:
            pieces.append((text[position:match.start()], None))
        pieces.append((match.group(0), match.group(1).lower()))
        position = match.end()
    if position < len(text):
        pieces.append((text[position:], None))
    return pieces


class StatIconFont:
    """Font wrapper whose ``render`` and ``size`` place stat icons beside stat words.

    Text without a stat name is delegated untouched to the wrapped font, so plain
    rendering and every other font method behave exactly as before.
    """

    def __init__(self, font: pygame.font.Font) -> None:
        self._font = font

    def __getattr__(self, name: str):
        return getattr(self._font, name)

    def _icon(self, stat: str) -> pygame.Surface:
        return stat_icon(stat, icon_height_for(self._font.get_height()))

    def size(self, text: str) -> tuple[int, int]:
        width, height = self._font.size(text)
        if not STAT_PATTERN.search(text):
            return width, height
        width = 0
        for piece, stat in _segments(text):
            width += self._font.size(piece)[0]
            if stat:
                width += self._icon(stat).get_width() + _ICON_GAP
        return width, height

    def render(self, text, antialias, color, background=None):
        if not isinstance(text, str) or not STAT_PATTERN.search(text):
            if background is None:
                return self._font.render(text, antialias, color)
            return self._font.render(text, antialias, color, background)
        height = self._font.get_height()
        width = self.size(text)[0]
        result = pygame.Surface((width, height), pygame.SRCALPHA, 32)
        if background is not None:
            result.fill(background)
        x = 0
        for piece, stat in _segments(text):
            if stat:
                icon = self._icon(stat)
                result.blit(icon, (x, (height - icon.get_height()) // 2))
                x += icon.get_width() + _ICON_GAP
            if piece:
                rendered = self._font.render(piece, antialias, color)
                result.blit(rendered, (x, 0))
                x += rendered.get_width()
        return result


def without_stat_icons(font: pygame.font.Font) -> pygame.font.Font:
    """Return the underlying font for names that mention a stat word."""
    return font._font if isinstance(font, StatIconFont) else font
