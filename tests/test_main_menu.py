import os
import random
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.application import ApplicationController
from src.engine.football_ai import FootballAIDifficulty
from src.ui.application import DesktopApplication
from src.ui.layout import LOGICAL_SIZE
from src.ui import main_menu, main_menu_art
from src.ui.main_menu_art import MENU_BACKDROP, draw_menu_stadium
from src.ui.theme import readable_ink, relative_luminance


def _desktop(tmp_path: Path, *, profile: bool = True) -> DesktopApplication:
    controller = ApplicationController(tmp_path / "team.json", tmp_path / "game.db")
    if profile:
        controller.create_profile("Mountain State University", "navy", "gold")
    return DesktopApplication(controller, seed_factory=lambda: 42)


def _draw(desktop: DesktopApplication) -> pygame.Surface:
    surface = pygame.Surface(LOGICAL_SIZE)
    desktop.router.draw(surface)
    return surface


def _button(desktop: DesktopApplication, label: str):
    return next(button for button in desktop.menu_screen.buttons if button.label == label)


def _click(desktop: DesktopApplication, label: str) -> None:
    button = _button(desktop, label)
    for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(pygame.event.Event(kind, pos=button.rect.center, button=1))


@pytest.mark.parametrize("difficulty", list(FootballAIDifficulty))
def test_difficulty_selection_survives_redraw_and_reaches_controller(
    tmp_path: Path, difficulty: FootballAIDifficulty
) -> None:
    desktop = _desktop(tmp_path)
    _draw(desktop)
    assert desktop.menu_screen.difficulty is FootballAIDifficulty.STANDARD
    _click(desktop, difficulty.value.upper())
    _draw(desktop)
    assert desktop.menu_screen.difficulty is difficulty
    assert _button(desktop, difficulty.value.upper()).variant == "primary"
    assert sum(button.variant == "primary" for button in desktop.menu_screen.buttons) == 1
    _click(desktop, "START RUN")
    assert desktop.football_controller is not None
    assert desktop.football_controller.state.opponent_difficulty is difficulty


def test_keyboard_and_mouse_press_release_leave_and_redraw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desktop = _desktop(tmp_path)
    _draw(desktop)
    menu = desktop.menu_screen
    settings = _button(desktop, "SETTINGS")
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=settings.rect.center))
    assert menu.hover_index == menu.focus_index == 4
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=settings.rect.center, button=1))
    _draw(desktop)
    desktop.router.handle_event(pygame.event.Event(pygame.WINDOWLEAVE))
    desktop.router.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=settings.rect.center, button=1))
    assert desktop.router.current_id == "main_menu"
    assert menu.hover_index is None and menu.pressed_index is None
    active_labels = []
    original = menu._draw_menu_button

    def record(surface, button, detail, active, pressed):
        if active:
            active_labels.append(button.label)
        original(surface, button, detail, active, pressed)

    monkeypatch.setattr(menu, "_draw_menu_button", record)
    _draw(desktop)
    assert not active_labels
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    assert menu.focus_index == 5 and menu.buttons[5].label == "HOW TO PLAY"
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))
    assert menu.focus_index == 6
    desktop.running = True
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert not desktop.running


def test_scaled_input_and_multiple_events_before_redraw(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.window_size = (1600, 1000)
    _draw(desktop)
    hard = _button(desktop, "HARD")
    start = _button(desktop, "START RUN")

    def physical(pos: tuple[int, int]) -> tuple[int, int]:
        return (round(pos[0] * 1.25), round(pos[1] * 1.25 + 50))

    for button in (hard, start):
        for kind in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            event = pygame.event.Event(kind, pos=physical(button.rect.center), button=1)
            desktop.router.handle_event(desktop._logical_event(event))
    assert desktop.football_controller is not None
    assert desktop.football_controller.state.opponent_difficulty is FootballAIDifficulty.HARD


def test_missing_and_corrupt_profiles_disable_start_and_preserve_file(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path, profile=False)
    _draw(desktop)
    assert not _button(desktop, "START RUN").enabled
    assert _button(desktop, "CREATE PROFILE").enabled
    _click(desktop, "START RUN")
    assert desktop.router.current_id == "main_menu"
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    assert desktop.router.current_id == "settings"

    path = tmp_path / "team.json"
    path.write_text("{", encoding="utf-8")
    corrupt = _desktop(tmp_path, profile=False)
    _draw(corrupt)
    assert corrupt.menu_screen.profile_error is not None
    assert not _button(corrupt, "CREATE PROFILE").enabled
    assert not _button(corrupt, "START RUN").enabled
    assert _button(corrupt, "QUIT").focused
    assert path.read_text(encoding="utf-8") == "{"


def test_profile_edit_updates_badge_and_helmet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    desktop = _desktop(tmp_path)
    old = _draw(desktop)
    desktop.save_profile("Northern Prairie University", "gold", "blue")
    captured = []
    original = main_menu._marquee

    def record(surface, text, rect, font, color):
        captured.append(text)
        original(surface, text, rect, font, color)

    monkeypatch.setattr(main_menu, "_marquee", record)
    new = _draw(desktop)
    assert "NORTHERN PRAIRIE UNIVERSITY" in captured
    assert desktop.menu_screen.theme.primary == pygame.Color("#ffd700")
    assert desktop.menu_screen.theme.secondary == pygame.Color("#0000ff")
    assert old.get_at((950, 480)) != new.get_at((950, 480))


def test_error_and_color_warning_are_persistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    desktop = _desktop(tmp_path)
    captured = []
    original = main_menu._marquee

    def record(surface, text, rect, font, color):
        captured.append(text)
        original(surface, text, rect, font, color)

    monkeypatch.setattr(main_menu, "_marquee", record)
    desktop.menu_screen.theme = replace(desktop.theme, warning="Color warning detail")
    _draw(desktop)
    assert "Color warning detail" in captured
    captured.clear()
    desktop.menu_screen.profile_error = "Profile error detail"
    _draw(desktop)
    assert "Profile error detail" in captured


@pytest.mark.parametrize("primary,secondary", [("#00005f", "#0000ff"), ("#ffff00", "#ffd700")])
def test_art_color_contrast_and_bounds_without_randomness(primary: str, secondary: str) -> None:
    primary_color = pygame.Color(primary)
    ink = readable_ink(primary_color)
    luminances = sorted((relative_luminance(primary_color), relative_luminance(ink)))
    assert (luminances[1] + 0.05) / (luminances[0] + 0.05) >= 4.5
    surface = pygame.Surface(LOGICAL_SIZE)
    state = random.getstate()
    draw_menu_stadium(surface, primary_color, pygame.Color(secondary))
    assert random.getstate() == state
    sprite = main_menu_art._tinted_helmet(tuple(primary_color[:3]))
    _, shell = main_menu_art._helmet_layers()
    colors = {tuple(sprite.get_at((x, y))) for y in range(shell.get_height())
              for x in range(shell.get_width()) if shell.get_at((x, y)).a}
    assert len(colors) > 10


def test_stadium_details_and_team_colors_are_independent() -> None:
    primary = pygame.Color("#8700ff")
    secondary = pygame.Color("#ffd700")
    base = pygame.Surface(LOGICAL_SIZE)
    changed_primary = pygame.Surface(LOGICAL_SIZE)
    changed_secondary = pygame.Surface(LOGICAL_SIZE)
    draw_menu_stadium(base, primary, secondary)
    draw_menu_stadium(changed_primary, pygame.Color("#00d700"), secondary)
    draw_menu_stadium(changed_secondary, primary, pygame.Color("#0000ff"))
    assert base.get_at((950, 480)) != changed_primary.get_at((950, 480))
    assert base.get_at((950, 480)) == changed_secondary.get_at((950, 480))
    assert any(base.get_at((x, y)) != changed_secondary.get_at((x, y))
               for x in range(624, 650, 2) for y in range(288, 304, 2))
    # The scene includes distinct illuminated lamps, shaded stands and field stripes.
    for region in ((650, 200, 125, 70), (580, 350, 190, 240), (1120, 605, 150, 34)):
        area = base.subsurface(region)
        colors = {area.get_at((x, y))[:3]
                  for y in range(0, area.get_height(), 2)
                  for x in range(0, area.get_width(), 2)}
        assert len(colors) >= 8


def test_helmet_layers_recolor_only_shell_and_remove_green() -> None:
    base, shell = main_menu_art._helmet_layers()
    first = main_menu_art._tinted_helmet((0, 0, 95))
    second = main_menu_art._tinted_helmet((255, 215, 0))
    assert base.get_size() == shell.get_size() == (174, 130)
    shell_pixels = unchanged_pixels = transparent_pixels = 0
    for y in range(base.get_height()):
        for x in range(base.get_width()):
            b = base.get_at((x, y))
            m = shell.get_at((x, y))
            if m.a:
                shell_pixels += 1
                assert first.get_at((x, y)) != second.get_at((x, y))
            elif b.a:
                unchanged_pixels += 1
                assert first.get_at((x, y)) == second.get_at((x, y)) == b
                assert not (b.g > 65 and b.g > b.r * 1.4 and b.g > b.b * 1.4)
            else:
                transparent_pixels += 1
                assert first.get_at((x, y)).a == 0
    assert min(shell_pixels, unchanged_pixels, transparent_pixels) > 1000


def test_helmet_load_failure_logs_and_draws_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(_primary):
        raise FileNotFoundError("missing helmet")

    monkeypatch.setattr(main_menu_art, "_tinted_helmet", fail)
    surface = pygame.Surface((640, 360))
    main_menu_art._helmet(surface, pygame.Color("red"), pygame.Color("blue"))
    assert "Could not load menu helmet artwork" in caplog.text
    assert surface.get_at((440, 250)) != pygame.Color("black")


def test_long_names_scroll_within_badge_and_controls_fit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    desktop = _desktop(tmp_path)
    name = "Very Long Mountain State University Football Program"
    desktop.save_profile(name, "crimson", "gold")
    _draw(desktop)
    menu = desktop.menu_screen
    canvas = pygame.Rect((0, 0), LOGICAL_SIZE)
    assert all(canvas.contains(button.rect) for button in menu.buttons)
    assert all(MENU_BACKDROP.contains(button.rect.move(0, 2).inflate(8, 8))
               for button in menu.buttons)
    assert all(not first.rect.colliderect(second.rect)
               for i, first in enumerate(menu.buttons) for second in menu.buttons[i + 1:])
    font = menu.badge_font
    rect = pygame.Rect(10, 10, 180, 30)
    assert font.size(name.upper())[0] > rect.width
    surface = pygame.Surface((220, 50))
    monkeypatch.setattr(pygame.time, "get_ticks", lambda: 0)
    main_menu._marquee(surface, name.upper(), rect, font, pygame.Color("white"))
    assert surface.get_at((rect.right + 1, rect.centery)) == pygame.Color("black")


def test_resized_presentation_keeps_art_pixel_scaled(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    canvas = _draw(desktop)
    pygame.display.init()
    try:
        window = pygame.display.set_mode((960, 600))
        desktop._present(canvas, window, menu_overlay=desktop.menu_screen.overlay, theme=desktop.theme)
        expected = pygame.Surface((960, 540))
        draw_menu_stadium(expected, desktop.theme.primary, desktop.theme.secondary)
        # This point is in the helmet, outside all overlay controls.
        assert window.get_at((660, 405)) == expected.get_at((660, 375))
        assert window.get_at((0, 0)) == pygame.Color("black")
    finally:
        pygame.display.quit()
