import fnmatch
import os
import tomllib
from importlib.resources import files
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from src.ui import stat_icons
from src.ui.coach_fonts import coach_font, staff_font
from src.ui.screens import _ui_font
from src.ui.stat_icons import (
    STAT_ICON_FILES,
    StatIconFont,
    icon_height_for,
    stat_icon,
    without_stat_icons,
)
from src.ui.text import draw_complete_wrapped_text, fit_text, wrap_text_lines
from src.ui.widgets import Button
from src.ui.theme import Theme

STATS = tuple(STAT_ICON_FILES)
WHITE = pygame.Color("#ffffff")


@pytest.fixture(autouse=True)
def _pygame():
    pygame.font.init()
    yield


def _bytes(surface: pygame.Surface) -> bytes:
    return pygame.image.tobytes(surface, "RGBA")


def _plain(size: int = 14) -> pygame.font.Font:
    return staff_font(size)._font


@pytest.mark.parametrize("stat", STATS)
def test_icon_assets_are_transparent_trimmed_packaged_and_keep_artwork(stat: str) -> None:
    asset = files("src.ui").joinpath("assets", "stat_icons", STAT_ICON_FILES[stat])
    assert asset.is_file()
    image = pygame.image.load(str(asset))
    assert image.get_bounding_rect() == image.get_rect()
    assert image.get_at((0, 0)).a == 0
    assert image.get_at((image.get_width() - 1, image.get_height() - 1)).a == 0
    opaque = pygame.mask.from_surface(image, 128).count()
    assert opaque > image.get_width() * image.get_height() * 0.3
    colors = {tuple(image.get_at((x, y)))[:3] for y in range(0, image.get_height(), 2)
              for x in range(0, image.get_width(), 2) if image.get_at((x, y)).a == 255}
    assert len(colors) > 20

    def count(predicate) -> int:
        return sum(1 for r, g, b in colors if predicate(r, g, b))

    if stat == "power":
        assert count(lambda r, g, b: r > 200 and 120 < g < 220 and b < 80) > 3
    elif stat == "stamina":
        # The battery charge is bright green and must not be keyed out.
        assert count(lambda r, g, b: g > 180 and r < 120 and b < 120) > 3
    else:
        assert count(lambda r, g, b: r > 180 and g < 80 and b < 80) > 3
        assert count(lambda r, g, b: r > 220 and g > 220 and b > 220) > 3
    # No opaque keyed-green backdrop remains on the borders of the trimmed image.
    edge = [image.get_at((x, y)) for x in range(image.get_width()) for y in (0, image.get_height() - 1)]
    assert not any(c.a and c.g > 150 and c.g > c.r * 1.6 and c.g > c.b * 1.6 for c in edge)


def test_icons_are_included_by_package_data_patterns() -> None:
    root = Path(__file__).resolve().parents[1]
    patterns = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["setuptools"]["package-data"]["src.ui"]
    for filename in STAT_ICON_FILES.values():
        relative = f"assets/stat_icons/{filename}"
        assert any(fnmatch.fnmatch(relative, pattern) for pattern in patterns)


def test_every_ui_font_factory_returns_icon_font_and_nothing_else_builds_fonts() -> None:
    for font in (staff_font(14), staff_font(14, semibold=True), coach_font(15),
                 coach_font(15, handwritten=True), _ui_font(16, bold=True)):
        assert isinstance(font, StatIconFont)
    ui = Path(__file__).resolve().parents[1] / "src"
    builders = {path.name for path in ui.rglob("*.py") if "pygame.font.Font(" in path.read_text()
                and not path.name.startswith("test_")}
    assert builders <= {"screens.py", "coach_fonts.py"}


def test_plain_text_rendering_and_metrics_are_unchanged() -> None:
    wrapped, plain = staff_font(14), _plain(14)
    for text in ("QB / Boundary Captain", "Empowered powerful staminas", "", "A  B"):
        assert wrapped.size(text) == plain.size(text)
        if text:
            assert _bytes(wrapped.render(text, True, WHITE)) == _bytes(plain.render(text, True, WHITE))
    assert wrapped.get_height() == plain.get_height()
    assert wrap_text_lines("one two three four five six", wrapped, 60) == \
        wrap_text_lines("one two three four five six", plain, 60)


def test_stat_words_in_names_can_render_without_icons() -> None:
    font = staff_font(16)
    plain = without_stat_icons(font)
    assert plain is font._font
    assert plain.size("Power Toss") == font._font.size("Power Toss")
    assert _bytes(plain.render("Power Toss", True, WHITE)) == _bytes(
        font._font.render("Power Toss", True, WHITE)
    )
    assert font.size("Power +5%")[0] > plain.size("Power +5%")[0]


@pytest.mark.parametrize("stat", STATS)
@pytest.mark.parametrize("variant", ("{}", "{}".upper(), "{}".title()))
def test_each_stat_word_gets_its_matching_inline_icon(stat: str, variant: str) -> None:
    font = staff_font(16)
    word = stat.upper() if variant == "{}".upper() else stat.title() if variant == "{}".title() else stat
    text = f"{word} +5%"
    icon = stat_icon(stat, icon_height_for(font.get_height()))
    gap = stat_icons._ICON_GAP
    plain = font._font
    rendered = font.render(text, True, WHITE)
    assert rendered.get_height() == font.get_height()
    assert abs(font.size(text)[0] - (plain.size(text)[0] + icon.get_width() + gap)) <= 2
    assert rendered.get_width() == font.size(text)[0]
    top = (rendered.get_height() - icon.get_height()) // 2
    assert 0 <= top and top + icon.get_height() <= rendered.get_height()
    assert _bytes(rendered.subsurface((0, top, *icon.get_size()))) == _bytes(icon)
    # Text keeps rendering after the icon, immediately beside its word.
    word_surface = plain.render(text, True, WHITE)
    assert _bytes(rendered.subsurface((icon.get_width() + gap, 0, word_surface.get_width(), rendered.get_height()))) \
        == _bytes(word_surface)


def test_icon_is_text_scaled_nearest_neighbour_and_small() -> None:
    for size in (12, 14, 16, 25):
        font = staff_font(size)
        height = icon_height_for(font.get_height())
        assert 0.6 * font.get_height() <= height <= font.get_height()
        for stat in STATS:
            icon = stat_icon(stat, height)
            assert icon.get_height() == height
            source = stat_icons._source_icon(stat)
            palette = {tuple(source.get_at((x, y))) for x in range(source.get_width())
                       for y in range(source.get_height())}
            assert {tuple(icon.get_at((x, y))) for x in range(icon.get_width())
                    for y in range(icon.get_height())} <= palette


def test_multiple_stats_and_word_boundaries() -> None:
    font = staff_font(14)
    text = "Power, stamina and volatility; empower staminas"
    plain = font._font
    extra = sum(stat_icon(s, icon_height_for(font.get_height())).get_width() + stat_icons._ICON_GAP
                for s in STATS)
    # Piece-wise measuring may differ from whole-string kerning by a pixel or two.
    assert abs(font.size(text)[0] - (plain.size(text)[0] + extra)) <= 3


@pytest.mark.parametrize("width", (90, 140, 220))
def test_wrapped_paragraphs_keep_icons_inside_rect_and_wrap_within_width(width: int) -> None:
    font = staff_font(14)
    text = ("Power excludes fatigue. Stamina max 100%; volatility min 0%. "
            "Volatility is a coached player stat; POWER and STAMINA matter.")
    lines = wrap_text_lines(text, font, width)
    assert all(font.size(line)[0] <= width for line in lines)
    assert " ".join(lines).split() == text.split()
    height = len(lines) * (font.get_height() + 2)
    surface = pygame.Surface((width + 40, height + 40), pygame.SRCALPHA)
    rect = pygame.Rect(20, 20, width, height)
    used = draw_complete_wrapped_text(surface, text, rect, font, WHITE)
    assert used == height - 2
    drawn = surface.get_bounding_rect()
    assert rect.contains(drawn.move(0, 0))
    plain_lines = wrap_text_lines(text, font._font, width)
    assert len(lines) >= len(plain_lines)
    with pytest.raises(ValueError):
        draw_complete_wrapped_text(surface, text, pygame.Rect(20, 20, width, 5), font, WHITE)


def test_wrapped_line_spacing_is_unchanged_by_icons() -> None:
    font = staff_font(14)
    with_icons = font.render("Power Stamina Volatility", True, WHITE)
    without = font.render("Plain words here", True, WHITE)
    assert with_icons.get_height() == without.get_height() == font.get_height()


def test_labels_cards_and_buttons_render_icons_without_clipping() -> None:
    font = staff_font(14, semibold=True)
    label = font.render("VOLATILITY -2%", True, WHITE)
    assert label.get_bounding_rect().top >= 0 and label.get_bounding_rect().right <= label.get_width()
    button = Button("STAMINA +20%", lambda: None, pygame.Rect(10, 10, 220, 30))
    surface = pygame.Surface((260, 60))
    button.draw(surface, font, Theme.from_profile(None))
    plain_button = Button("QUALITY +20%", lambda: None, pygame.Rect(10, 10, 220, 30))
    other = pygame.Surface((260, 60))
    plain_button.draw(other, font, Theme.from_profile(None))
    assert _bytes(surface) != _bytes(other)
    fitted = fit_text("POWER 50", font, 500)
    assert fitted == "POWER 50"


def test_background_argument_and_non_string_pass_through() -> None:
    font = staff_font(14)
    rendered = font.render("Power", True, WHITE, pygame.Color("#102030"))
    assert rendered.get_at((rendered.get_width() - 1, 0)) != (0, 0, 0, 0)
