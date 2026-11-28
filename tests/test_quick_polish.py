"""The game name, the main menu's focus look, the Settings error gap, and the drive
chart's possession-change row."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pathlib import Path

import pygame
import pytest

from src.ui import main_menu, screens
from src.ui.football_match_events import PlayLine, PlayLineKind, PlaySegment
from src.ui.football_match_field import (
    CHART_BOTTOM_CLEAR, chart_rows, draw_drive_chart, field_geometry,
)
from src.ui.football_match_screen import FIELD_RECT
from src.ui.football_tips import TIP_OFFENSE, TIP_TEXT
from src.ui.screens import GAME_NAME, Screen
from src.ui.theme import Theme

from test_football_desktop import _new_desktop, _surface
from test_settings_screen import _open_settings


class _RecordingFont:
    """Wraps a font and records every string it renders or measures for drawing."""

    def __init__(self, font, seen: list[str]) -> None:
        self._font, self._seen = font, seen

    def render(self, text, *args, **kwargs):
        self._seen.append(text)
        return self._font.render(text, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._font, name)


def _menu_texts(desktop, monkeypatch) -> list[str]:
    seen: list[str] = []
    original = main_menu.draw_text

    def record(surface, text, position, font, color, *args, **kwargs):
        seen.append(text)
        return original(surface, text, position, font, color, *args, **kwargs)

    monkeypatch.setattr(main_menu, "draw_text", record)
    menu = desktop.router.current
    for name in ("title_font", "menu_font", "detail_font", "badge_font", "small_font"):
        setattr(menu, name, _RecordingFont(getattr(menu, name), seen))
    desktop.router.draw(_surface())
    return seen


def test_main_menu_title_is_the_game_name_and_fits_the_left_panel(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    assert desktop.router.current_id == "main_menu"
    texts = _menu_texts(desktop, monkeypatch)
    assert "DRAFT DRIVE FOOTBALL" in texts and "COLLEGE FOOTBALL" not in texts
    assert "BUILD YOUR PROGRAM  /  CALL THE GAME" in texts
    font = main_menu.title_font()
    assert main_menu.TITLE_POS[0] + font.size(main_menu.GAME_TITLE)[0] <= main_menu.TITLE_RULE_RIGHT


def test_main_menu_title_steps_its_font_down_instead_of_clipping(monkeypatch) -> None:
    pygame.font.init()
    full = main_menu.title_font().size(main_menu.GAME_TITLE)[0]
    narrow = main_menu.TITLE_POS[0] + full - 60
    monkeypatch.setattr(main_menu, "TITLE_RULE_RIGHT", narrow)
    font = main_menu.title_font()
    assert font.size(main_menu.GAME_TITLE)[0] <= narrow - main_menu.TITLE_POS[0] < full


def test_main_menu_focus_shows_no_focus_label(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    menu = desktop.router.current
    menu.keyboard_focus = True
    texts = _menu_texts(desktop, monkeypatch)
    assert "FOCUS" not in texts
    # Keyboard navigation still moves focus between the menu buttons.
    before = menu.focus_index
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_DOWN}))
    desktop.router.draw(_surface())
    assert menu.focus_index != before


def test_window_caption_is_the_game_name(tmp_path: Path, monkeypatch) -> None:
    captions: list[str] = []
    monkeypatch.setattr(pygame.display, "set_caption", lambda text, *_args: captions.append(text))
    desktop = _new_desktop(tmp_path)
    desktop.run(event_source=lambda: [pygame.event.Event(pygame.QUIT)])
    assert captions == ["Draft Drive Football"] and GAME_NAME == "Draft Drive Football"


def test_fallback_header_names_the_game(monkeypatch) -> None:
    pygame.font.init()
    seen: list[str] = []
    original = screens.draw_text
    monkeypatch.setattr(
        screens, "draw_text",
        lambda surface, text, *args, **kwargs: (seen.append(text), original(surface, text, *args, **kwargs))[1],
    )
    screen = Screen(Theme.from_profile(None), lambda _route: None, lambda: None)
    screen._header(pygame.Surface((1280, 720)), "TITLE", "EYEBROW", "Owls")
    assert "DRAFT DRIVE FOOTBALL" in seen and "COLLEGE FOOTBALL" not in seen


def test_offense_tip_says_the_scheme_is_hidden() -> None:
    assert TIP_TEXT[TIP_OFFENSE] == "Play a card. Their scheme is hidden; learn what works from your yards."


@pytest.mark.parametrize("size", [(1280, 720), (1024, 600)])
def test_settings_error_banner_keeps_a_gap_above_the_footer(tmp_path: Path, size) -> None:
    desktop = _open_settings(tmp_path)
    screen = desktop.profile_screen
    screen.error = (
        "Team name contains profanity. This local filter checks a small list of terms "
        "and may not catch every variation."
    )
    screen.draw(pygame.Surface(size))
    footer = [b.rect for b in screen.buttons if b.label in ("CANCEL", "SAVE PROFILE")]
    assert footer and all(rect.top - screen.error_rect.bottom >= 12 for rect in footer)
    assert screen.error_rect.height >= 40


def _line(start: float, end: float, *, ret: float | None = None) -> PlayLine:
    segments = (PlaySegment(PlayLineKind.PASS, start, end),)
    if ret is not None:
        segments += (PlaySegment(PlayLineKind.OTHER, end, ret),)
    return PlayLine(segments=segments)


@pytest.mark.parametrize("drive_rows", [2, 9, 30])
def test_possession_change_gets_its_own_row_below_the_drive(drive_rows) -> None:
    pygame.font.init()
    geometry = field_geometry(FIELD_RECT)
    rows, spacing = chart_rows(geometry, drive_rows + 1)
    # Its own row, below the last drive row, and clear of the down tag along the bottom.
    assert rows[-1] > rows[-2]
    assert rows[-1] <= geometry.turf.bottom - CHART_BOTTOM_CLEAR
    # Drawing it: the kickoff (with its return lane) never touches the row above.
    surface = pygame.Surface(FIELD_RECT.size)
    drive = tuple(_line(70.0, 60.0) for _ in range(drive_rows))
    kickoff = _line(35.0, 100.0, ret=80.0)
    shifted = field_geometry(pygame.Rect((0, 0), FIELD_RECT.size))
    surface.fill((0, 0, 0))
    draw_drive_chart(surface, shifted, drive, None, 1.0, slots=drive_rows + 1)
    held, _ = chart_rows(shifted, drive_rows + 1)
    # The reserved row stays empty while the possession change is held.
    x = shifted.x_for(90.0)
    assert surface.get_at((x, held[-1]))[:3] == (0, 0, 0)
    surface.fill((0, 0, 0))
    draw_drive_chart(surface, shifted, drive, kickoff, 1.0, slots=drive_rows + 1)
    painted = [y for y in range(shifted.turf.top, shifted.turf.bottom)
               if surface.get_at((x, y))[:3] != (0, 0, 0)]
    assert painted and min(painted) > held[-2]
