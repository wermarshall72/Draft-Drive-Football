import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.application import ApplicationController
from src.ui.application import DesktopApplication
from src.ui.layout import LOGICAL_SIZE
from src.ui.theme import Theme


def test_desktop_startup_uses_saved_profile_without_initializing_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "must-not-exist.db"
    controller = ApplicationController(tmp_path / "team.json", database_path)
    profile = controller.create_profile("Arcade Owls", "navy", "gold")

    desktop = DesktopApplication(controller)

    assert desktop.router.current_id == "main_menu"
    assert desktop.menu_state is not None
    assert desktop.menu_state.profile == profile
    assert desktop.theme.primary == pygame.Color(profile.primary_color.hex_value)
    assert desktop.theme.secondary == pygame.Color(profile.secondary_color.hex_value)
    assert not database_path.exists()


def test_dark_team_color_gets_a_saturated_readable_interface_accent(
    tmp_path: Path,
) -> None:
    controller = ApplicationController(tmp_path / "team.json", tmp_path / "game.db")
    profile = controller.create_profile("Blue Team", "navy", "gold")

    theme = Theme.from_profile(profile)

    assert theme.primary == pygame.Color(profile.primary_color.hex_value)
    assert theme.primary_accent.b > 200
    assert theme.primary_accent.r > 80
    assert theme.primary_ink == pygame.Color("#fffaf0")


def test_missing_profile_has_clear_fallback_and_start_is_disabled(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "game.db"
    desktop = DesktopApplication(
        ApplicationController(tmp_path / "missing.json", database_path)
    )
    surface = pygame.Surface(LOGICAL_SIZE)

    desktop.router.draw(surface)
    menu = desktop.router.current

    assert menu.menu_state is None
    assert any(button.label == "START RUN" and not button.enabled for button in menu.buttons)
    assert desktop.theme.primary == Theme.from_profile(None).primary
    assert not (tmp_path / "missing.json").exists()
    assert not database_path.exists()


def test_keyboard_starts_a_controller_run_without_game_side_effects(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "game.db"
    controller = ApplicationController(tmp_path / "team.json", database_path)
    controller.create_profile("Route Team", "crimson", "gold")
    desktop = DesktopApplication(controller)
    batches = iter(
        (
            [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)],
            [pygame.event.Event(pygame.QUIT)],
        )
    )

    desktop.run(event_source=lambda: next(batches, []))

    assert desktop.router.current_id == "football_run"
    assert desktop.football_controller is not None
    assert desktop.football_controller.state.team_builder.selected_coach_pair is None
    assert not database_path.exists()
    assert not pygame.get_init()


def test_mouse_routes_to_settings_preview(tmp_path: Path) -> None:
    controller = ApplicationController(tmp_path / "team.json", tmp_path / "game.db")
    controller.create_profile("Mouse Team", "crimson", "gold")
    desktop = DesktopApplication(controller)
    desktop.router.draw(pygame.Surface(LOGICAL_SIZE))
    settings_button = next(
        button
        for button in desktop.router.current.buttons
        if button.label == "SETTINGS"
    )
    down_event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {"pos": settings_button.rect.center, "button": 1},
    )
    up_event = pygame.event.Event(
        pygame.MOUSEBUTTONUP,
        {"pos": settings_button.rect.center, "button": 1},
    )

    desktop.router.handle_event(down_event)
    assert desktop.router.current_id == "main_menu"
    desktop.router.handle_event(up_event)

    assert desktop.router.current_id == "settings"
    assert not (tmp_path / "game.db").exists()


def test_quit_button_exits_the_window_loop(tmp_path: Path) -> None:
    desktop = DesktopApplication(
        ApplicationController(tmp_path / "team.json", tmp_path / "game.db")
    )
    desktop.router.draw(pygame.Surface(LOGICAL_SIZE))
    quit_button = next(
        button
        for button in desktop.router.current.buttons
        if button.label == "QUIT"
    )
    events = iter(
        (
            [
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    {"pos": quit_button.rect.center, "button": 1},
                ),
                pygame.event.Event(
                    pygame.MOUSEBUTTONUP,
                    {"pos": quit_button.rect.center, "button": 1},
                ),
            ],
        )
    )

    desktop.run(event_source=lambda: next(events, []))

    assert not desktop.running
    assert not pygame.get_init()
    assert not (tmp_path / "game.db").exists()


def test_route_transition_is_brief_and_does_not_block_quit(
    tmp_path: Path,
) -> None:
    desktop = DesktopApplication(
        ApplicationController(tmp_path / "team.json", tmp_path / "game.db")
    )
    pygame.init()
    try:
        pygame.display.set_mode(LOGICAL_SIZE)
        desktop.running = True
        desktop.navigate("settings")

        assert desktop.router.current_id == "settings"
        transition_start = desktop._transition_started
        assert transition_start is not None
        assert desktop._transition_is_active(transition_start)
        canvas = pygame.Surface(LOGICAL_SIZE)
        desktop.router.draw(canvas)
        original_pixel = canvas.get_at((640, 288))
        desktop._draw_transition(canvas, transition_start)
        assert canvas.get_at((640, 288)) != original_pixel
        assert not desktop._transition_is_active(
            transition_start + desktop.TRANSITION_MS
        )
        assert desktop._transition_started is None

        desktop.quit()
        assert not desktop.running
    finally:
        pygame.quit()


def test_corrupt_profile_shows_recovery_message_and_quit_button_exits(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "bad-profile.json"
    profile_path.write_text("{", encoding="utf-8")
    desktop = DesktopApplication(
        ApplicationController(profile_path, tmp_path / "game.db")
    )
    surface = pygame.Surface(LOGICAL_SIZE)

    desktop.router.draw(surface)
    menu = desktop.router.current

    assert desktop.profile_error is not None
    assert menu.profile_error == desktop.profile_error
    assert next(button for button in menu.buttons if button.label == "QUIT").enabled


def test_resize_preserves_aspect_ratio_and_transforms_mouse_coordinates() -> None:
    desktop = DesktopApplication(window_size=(1600, 900))
    desktop.window_size = (1600, 900)
    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {"pos": (800, 450), "button": 1},
    )

    logical_event = desktop._logical_event(event)

    assert logical_event.pos == (640, 360)
    assert desktop.window_size != LOGICAL_SIZE
