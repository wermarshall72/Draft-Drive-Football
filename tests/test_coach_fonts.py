from pathlib import Path

import pygame
import pytest

from src.ui import coach_fonts


@pytest.mark.parametrize(("semibold", "filename"), [
    (False, "Barlow-Regular.ttf"),
    (True, "Barlow-SemiBold.ttf"),
])
def test_staff_fonts_load_bundled_files(monkeypatch, semibold, filename) -> None:
    pygame.font.init()
    original = pygame.font.Font
    paths: list[Path] = []

    def load_font(path, size):
        paths.append(Path(path))
        return original(path, size)

    monkeypatch.setattr(coach_fonts.pygame.font, "Font", load_font)
    assert coach_fonts.staff_font(16, semibold=semibold).size("QB +20%")[0] > 0
    assert paths == [coach_fonts._FONT_DIR / filename]
    license_text = (coach_fonts._FONT_DIR / "Barlow-OFL.txt").read_text()
    assert "SIL OPEN FONT LICENSE Version 1.1" in license_text
    assert "Barlow Project Authors" in license_text


def test_missing_staff_font_warns_and_uses_fallback(tmp_path, monkeypatch, caplog) -> None:
    pygame.font.init()
    monkeypatch.setattr(coach_fonts, "_FONT_DIR", tmp_path)
    assert coach_fonts.staff_font(16, semibold=True).size("Coach")[0] > 0
    assert "Could not load coach font Barlow-SemiBold.ttf" in caplog.text
