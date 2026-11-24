"""Shared navy-stadium look for the match, shop, Depth Chart, and Playbook screens.

Colors, fonts, the fit-audited ``blit_text``, the stadium backdrop, popup panels and
buttons, rarity colors, and the portrait card shell used by match hands and shop
offers all live here so no screen has to import another screen's modules.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import pygame

from src.ui.coach_fonts import staff_font
from src.ui.football_card_art import draw_card_art
from src.ui.stat_icons import StatIconFont, stat_icon, without_stat_icons
from src.ui.text import fit_text, wrap_text_lines

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
MATCH_GOOD = pygame.Color("#7ee2a0")

# Coach position modifiers (Depth Chart and coach selection): up, down, unchanged.
MODIFIER_POSITIVE = pygame.Color("#9fe4ad")
MODIFIER_NEGATIVE = pygame.Color("#ff9d98")
MODIFIER_NEUTRAL = pygame.Color("#c1cbd5")

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

# One rarity palette for every screen: border and rarity text share the color.
RARITY_COLORS = {
    "common": pygame.Color("#abb6c2"),
    "uncommon": pygame.Color("#68c58a"),
    "rare": pygame.Color("#65b5ff"),
    "very_rare": pygame.Color("#c18be8"),
}


def rarity_color(rarity: object) -> pygame.Color:
    """Rarity color for a ``FootballShopRarity`` (or its string value)."""
    return pygame.Color(RARITY_COLORS[getattr(rarity, "value", rarity)])


def rarity_label(rarity: object) -> str:
    return str(getattr(rarity, "value", rarity)).replace("_", " ").upper()


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


def team_accent(color: pygame.Color) -> pygame.Color:
    """The team color nudged so it stays visible on the navy panels."""
    color = pygame.Color(color)
    luminance = (0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b) / 255
    if luminance < 0.16:
        return mix(color, MATCH_TEXT, 0.35)
    return color


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


def fit_wrapped(
    text: str, width: int, sizes: tuple[int, ...], max_lines: int
) -> tuple[pygame.font.Font, tuple[str, ...]]:
    """The largest size whose words each fit ``width`` within ``max_lines`` lines.

    Words are never split mid-word unless even the smallest size cannot fit one;
    then the final line is shortened with an ellipsis.
    """
    for size in sizes:
        font = plain_font(size)
        if all(font.size(word)[0] <= width for word in text.split()):
            lines = wrap_text_lines(text, font, width)
            if len(lines) <= max_lines:
                return font, lines
    font = plain_font(sizes[-1])
    lines = wrap_text_lines(text, font, width)
    if len(lines) > max_lines:
        lines = (*lines[: max_lines - 1], fit_text(" ".join(lines[max_lines - 1:]), font, width))
    return font, lines


def blit_wrapped(
    surface: pygame.Surface,
    text: str,
    rect: pygame.Rect,
    sizes: tuple[int, ...],
    color: pygame.Color,
    *,
    max_lines: int,
    align: str = "center",
    line_step: int = -1,
) -> int:
    """Wrap ``text`` into ``rect`` (top-aligned); returns the bottom y."""
    font, lines = fit_wrapped(text, rect.width, sizes, max_lines)
    y = rect.top
    for line in lines:
        if align == "center":
            blit_text(surface, font, line, color, rect, midtop=(rect.centerx, y))
        else:
            blit_text(surface, font, line, color, rect, topleft=(rect.left, y))
        y += font.get_height() + line_step
    return y


# -- stat icons drawn directly -------------------------------------------------------

def draw_stat_value(
    surface: pygame.Surface,
    stat: str,
    value: str,
    container: pygame.Rect,
    *,
    size: int = 22,
    color: pygame.Color = MATCH_TEXT,
    center: tuple[int, int] | None = None,
    midleft: tuple[int, int] | None = None,
) -> pygame.Rect:
    """An explicit stat icon followed by ``value`` (never the stat word)."""
    font = plain_font(size)
    icon = stat_icon(stat, round(font.get_height() * 0.82))
    gap = 4
    width = icon.get_width() + gap + font.size(value)[0]
    box = pygame.Rect(0, 0, width, font.get_height())
    if center is not None:
        box.center = center
    else:
        box.midleft = midleft or container.midleft
    surface.blit(icon, icon.get_rect(midleft=(box.left, box.centery)))
    blit_text(surface, font, value, color, container,
              midleft=(box.left + icon.get_width() + gap, box.centery))
    return box


_ASSET_DIR = Path(__file__).parent / "assets"


@lru_cache(maxsize=16)
def asset_icon(filename: str, height: int) -> pygame.Surface:
    image = pygame.image.load(_ASSET_DIR / filename)
    width = max(1, round(image.get_width() * height / image.get_height()))
    return pygame.transform.scale(image, (width, height))


def draw_lock(surface: pygame.Surface, center: tuple[int, int], size: int,
              color: pygame.Color) -> None:
    """A simple padlock: shackle arc above a rounded body."""
    cx, cy = center
    body = pygame.Rect(0, 0, size, round(size * 0.78))
    body.midtop = (cx, cy - round(size * 0.12))
    shackle = pygame.Rect(0, 0, round(size * 0.64), round(size * 0.8))
    shackle.midbottom = (cx, body.top + round(size * 0.22))
    width = max(2, size // 7)
    pygame.draw.ellipse(surface, color, shackle, width)
    pygame.draw.rect(surface, color, body, border_radius=max(2, size // 6))
    hole = pygame.Rect(0, 0, max(2, size // 6), max(3, size // 4))
    hole.center = (cx, body.centery)
    pygame.draw.rect(surface, MATCH_INK, hole, border_radius=1)


# -- stadium backdrop and popups -----------------------------------------------------

@lru_cache(maxsize=2)
def stadium_backdrop(size: tuple[int, int]) -> pygame.Surface:
    """Navy stadium night: a soft glow under the lights and light-tower flares."""
    surface = pygame.Surface(size)
    surface.fill(MATCH_CANVAS)
    width, height = size
    glow = pygame.Surface(size, pygame.SRCALPHA)
    for radius, alpha in ((560, 22), (420, 26), (300, 30)):
        pygame.draw.ellipse(glow, (*MATCH_CANVAS_GLOW[:3], alpha),
                            pygame.Rect(width // 2 - radius, -radius // 2, radius * 2, radius))
    surface.blit(glow, (0, 0))
    for x in (40, width - 40):
        flare = pygame.Surface((180, 140), pygame.SRCALPHA)
        for radius, alpha in ((80, 18), (52, 26), (28, 40)):
            pygame.draw.circle(flare, (190, 220, 255, alpha), (90, 50), radius)
        surface.blit(flare, (x - 90, -20))
    # A faint crowd band behind the hands.
    for y in range(height - 260, height, 6):
        shade = 12 + (y % 18)
        pygame.draw.line(surface, (shade // 2, 20 + shade // 3, 40 + shade // 2), (0, y), (width, y), 1)
    return surface


def draw_veil(surface: pygame.Surface) -> None:
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((*MATCH_CANVAS[:3], 205))
    surface.blit(overlay, (0, 0))


def draw_popup_panel(surface: pygame.Surface, rect: pygame.Rect, title: str, subtitle: str) -> pygame.Rect:
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 6), border_radius=16)
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=16)
    pygame.draw.rect(surface, MATCH_PANEL_EDGE, rect, 2, border_radius=16)
    blit_text(surface, plain_font(28), title, MATCH_TEXT, rect, topleft=(rect.left + 24, rect.top + 16))
    if subtitle:
        blit_text(surface, match_font(13, False), subtitle, MATCH_MUTED, rect,
                  topleft=(rect.left + 26, rect.top + 52))
    pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (rect.left + 20, rect.top + 76),
                     (rect.right - 20, rect.top + 76))
    return pygame.Rect(rect.left + 20, rect.top + 86, rect.width - 40, rect.height - 86 - 64)


def draw_popup_button(
    surface: pygame.Surface, button, *, focused: bool, hovered: bool, pressed: bool
) -> None:
    rect = button.rect.move(0, 2) if pressed else button.rect
    primary = button.variant == "popup-primary"
    danger = button.variant == "popup-danger"
    if primary:
        fill = MATCH_FOCUS
        ink = MATCH_INK
    else:
        fill = MATCH_PANEL_HIGH if focused or hovered else MATCH_PANEL
        ink = MATCH_DANGER if danger else MATCH_TEXT
    if focused:
        pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(6, 6), 2, border_radius=11)
    pygame.draw.rect(surface, fill, rect, border_radius=9)
    pygame.draw.rect(surface, MATCH_FOCUS if focused else MATCH_PANEL_EDGE, rect, 2, border_radius=9)
    font = match_font(17)
    label = font.render(fit_text(button.label, font, rect.width - 20), True, ink)
    surface.blit(label, label.get_rect(center=rect.center))


# Variants drawn by ``draw_kit_button``; screens route them here from ``_draw_buttons``.
KIT_VARIANTS = frozenset({
    "kit", "kit-primary", "kit-danger", "kit-toggle-on", "kit-small",
})


def draw_kit_button(
    surface: pygame.Surface,
    button,
    *,
    focused: bool,
    hovered: bool,
    pressed: bool,
    font_size: int = 16,
) -> None:
    """Match-strip style footer/toolbar buttons."""
    rect = button.rect.move(0, 2) if pressed and button.enabled else button.rect
    variant = button.variant
    lit = button.enabled and (focused or hovered)
    if not button.enabled:
        fill, edge, ink = MATCH_PANEL_DEEP, MATCH_PANEL_EDGE_SOFT, MATCH_DIM
    elif variant == "kit-primary":
        fill = MATCH_FOCUS if lit else mix(MATCH_FOCUS, MATCH_PANEL, 0.12)
        edge, ink = MATCH_FOCUS, MATCH_INK
    elif variant == "kit-toggle-on":
        fill = mix(MATCH_PANEL_HIGH, MATCH_FOCUS, 0.22 if lit else 0.14)
        edge, ink = MATCH_FOCUS, MATCH_TEXT
    else:
        fill = MATCH_PANEL_HIGH if lit else MATCH_PANEL_DEEP
        edge = MATCH_FOCUS if focused else (MATCH_PANEL_EDGE if variant != "kit-danger" else
                                            mix(MATCH_DANGER, MATCH_PANEL_DEEP, 0.45))
        ink = MATCH_DANGER if variant == "kit-danger" else MATCH_TEXT
    if focused and button.enabled:
        pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(6, 6), 2, border_radius=10)
    pygame.draw.rect(surface, fill, rect, border_radius=8)
    pygame.draw.rect(surface, edge, rect, 2, border_radius=8)
    size = 13 if variant == "kit-small" else font_size
    font = match_font(size)
    text = fit_text(button.label, font, rect.width - 16)
    blit_text(surface, font, text, ink, rect, center=rect.center)


# -- portrait card shell -------------------------------------------------------------

def draw_card_shell(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    art: str | None,
    band: pygame.Color | None,
    fill: pygame.Color,
    edge: pygame.Color,
    border: int,
    tile_height: int,
    stats_height: int,
    stats_bottom_gap: int,
    radius: int = 9,
    art_drawer=None,
) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
    """Shadow, frame, colored band, and art tile; returns (inner, tile, stats)."""
    pygame.draw.rect(surface, MATCH_INK, rect.move(0, 4), border_radius=radius)
    pygame.draw.rect(surface, fill, rect, border_radius=radius)
    pygame.draw.rect(surface, edge, rect, border, border_radius=radius)
    if band is not None:
        pygame.draw.rect(surface, band, (rect.left + border + 4, rect.top + border + 1,
                                         rect.width - 2 * border - 8, 4), border_radius=2)
    inner = rect.inflate(-12, 0)
    tile = pygame.Rect(inner.left, rect.top + 12, inner.width, tile_height)
    if art is not None:
        (art_drawer or draw_card_art)(surface, art, tile)
    stats = pygame.Rect(inner.left - 2, rect.bottom - stats_bottom_gap - stats_height,
                        inner.width + 4, stats_height)
    return inner, tile, stats


def draw_two_cells(
    surface: pygame.Surface,
    stats: pygame.Rect,
    rows: tuple[tuple[str, str], tuple[str, str]],
    *,
    value_size: int = 17,
    caption_size: int = 9,
) -> None:
    """Two side-by-side value/caption cells split by a soft divider."""
    half = stats.width // 2
    for index, (value, caption) in enumerate(rows):
        cell = pygame.Rect(stats.left + index * half, stats.top, half, stats.height)
        value_font = plain_font(value_size)
        blit_text(surface, value_font, fit_text(value, value_font, cell.width - 4), MATCH_TEXT,
                  cell, midtop=(cell.centerx, cell.top + 3))
        caption_font = plain_font(caption_size)
        blit_text(surface, caption_font, fit_text(caption, caption_font, cell.width - 2),
                  MATCH_MUTED, cell, midbottom=(cell.centerx, cell.bottom - 3))
    pygame.draw.line(surface, MATCH_PANEL_EDGE_SOFT, (stats.centerx, stats.top + 6),
                     (stats.centerx, stats.bottom - 6))


def draw_alpha_veil(surface: pygame.Surface, rect: pygame.Rect, alpha: int, radius: int = 9) -> None:
    veil = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(veil, (*MATCH_CANVAS[:3], alpha), veil.get_rect(), border_radius=radius)
    surface.blit(veil, rect.topleft)


# -- buttons that paint themselves ---------------------------------------------------

from dataclasses import dataclass  # noqa: E402
from typing import Callable  # noqa: E402

from src.ui.widgets import Button  # noqa: E402


@dataclass
class PaintedButton(Button):
    """A Button drawn by ``painter(surface, button, hovered, pressed)`` or the kit style."""

    painter: Callable[..., None] | None = None

    def draw(self, surface, font, theme, *, hovered: bool = False, pressed: bool = False) -> None:
        if self.painter is not None:
            self.painter(surface, self, hovered, pressed)
        else:
            draw_kit_button(surface, self, focused=self.focused, hovered=hovered, pressed=pressed)


def kit_button(label: str, action: Callable[[], None], rect: pygame.Rect, *,
               variant: str = "kit", enabled: bool = True) -> PaintedButton:
    return PaintedButton(label, action, pygame.Rect(rect), enabled=enabled, variant=variant)


def draw_focus_ring(surface: pygame.Surface, rect: pygame.Rect, radius: int = 9) -> None:
    pygame.draw.rect(surface, MATCH_TEXT, rect.inflate(8, 8), 2, border_radius=radius + 3)


def draw_message_banner(surface: pygame.Surface, rect: pygame.Rect, text: str, *,
                        danger: bool = False) -> None:
    """A 2-line pill for transition and error messages."""
    accent = MATCH_DANGER if danger else MATCH_FOCUS
    pygame.draw.rect(surface, MATCH_PANEL_DEEP, rect, border_radius=10)
    pygame.draw.rect(surface, mix(accent, MATCH_PANEL_DEEP, 0.45), rect, 2, border_radius=10)
    pygame.draw.rect(surface, accent, (rect.left + 6, rect.top + 8, 4, rect.height - 16), border_radius=2)
    box = pygame.Rect(rect.left + 18, rect.top + 4, rect.width - 26, rect.height - 8)
    font, lines = fit_wrapped(text, box.width, (15, 14, 13, 12, 11), 2)
    total = len(lines) * font.get_height()
    y = box.centery - total // 2
    for line in lines:
        blit_text(surface, font, line, MATCH_TEXT, rect, topleft=(box.left, y))
        y += font.get_height()


@lru_cache(maxsize=16)
def smooth_icon(filename: str, height: int) -> pygame.Surface:
    """A packaged icon smoothly downscaled for small UI badges."""
    image = pygame.image.load(_ASSET_DIR / filename)
    width = max(1, round(image.get_width() * height / image.get_height()))
    if pygame.display.get_surface() is not None:
        image = image.convert_alpha()
    return pygame.transform.smoothscale(image, (width, height))
