"""Bundled typefaces for the recruiting-room screen."""

import logging
from pathlib import Path

import pygame

from src.ui.screens import _ui_font

_LOG = logging.getLogger(__name__)
_FONT_DIR = Path(__file__).parent / "assets" / "fonts"


def coach_font(size: int, *, bold: bool = False, handwritten: bool = False) -> pygame.font.Font:
    filename = (
        "Kalam-Bold.ttf"
        if handwritten
        else "AtkinsonHyperlegible-Bold.ttf" if bold else "AtkinsonHyperlegible-Regular.ttf"
    )
    try:
        return pygame.font.Font(str(_FONT_DIR / filename), size)
    except (OSError, pygame.error) as error:
        _LOG.warning("Could not load coach font %s: %s", filename, error)
        return _ui_font(size, bold=bold or handwritten)


def staff_font(size: int, *, semibold: bool = False) -> pygame.font.Font:
    filename = "Barlow-SemiBold.ttf" if semibold else "Barlow-Regular.ttf"
    try:
        return pygame.font.Font(str(_FONT_DIR / filename), size)
    except (OSError, pygame.error) as error:
        _LOG.warning("Could not load coach font %s: %s", filename, error)
        return _ui_font(size, bold=semibold)
