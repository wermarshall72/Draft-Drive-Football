from pathlib import Path

import pygame
import pytest

from src.ui import coach_fonts


@pytest.mark.parametrize(
    ("options", "filename"),
    [
        ({}, "AtkinsonHyperlegible-Regular.ttf"),
        ({"bold": True}, "AtkinsonHyperlegible-Bold.ttf"),
        ({"handwritten": True}, "Kalam-Bold.ttf"),
    ],
)
def test_coach_fonts_load_bundled_files(monkeypatch, options, filename) -> None:
    pygame.font.init()
    original = pygame.font.Font
    paths: list[Path] = []

    def load_font(path, size):
        paths.append(Path(path))
        return original(path, size)

    monkeypatch.setattr(coach_fonts.pygame.font, "Font", load_font)
    font = coach_fonts.coach_font(16, **options)
    assert paths == [coach_fonts._FONT_DIR / filename]
    assert font.size("QB +20%")[0] > 0
    assert font.get_bold() == ("Bold" in filename)


def test_missing_coach_font_warns_and_uses_fallback(tmp_path, monkeypatch, caplog) -> None:
    pygame.font.init()
    monkeypatch.setattr(coach_fonts, "_FONT_DIR", tmp_path)
    font = coach_fonts.coach_font(16, bold=True)
    assert font.size("Coach")[0] > 0
    assert "Could not load coach font AtkinsonHyperlegible-Bold.ttf" in caplog.text
