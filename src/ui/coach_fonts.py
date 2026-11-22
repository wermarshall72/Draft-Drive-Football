"""Bundled Barlow typeface for the draft, shop, and staff screens."""

import logging
from pathlib import Path

import pygame

from src.ui.screens import _ui_font
from src.ui.stat_icons import StatIconFont

_LOG = logging.getLogger(__name__)
_FONT_DIR = Path(__file__).parent / "assets" / "fonts"


def staff_font(size: int, *, semibold: bool = False) -> StatIconFont:
    filename = "Barlow-SemiBold.ttf" if semibold else "Barlow-Regular.ttf"
    try:
        return StatIconFont(pygame.font.Font(str(_FONT_DIR / filename), size))
    except (OSError, pygame.error) as error:
        _LOG.warning("Could not load coach font %s: %s", filename, error)
        return _ui_font(size, bold=semibold)
