import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.application import ApplicationController
from src.engine.football_controller import FootballRunPhase
from src.profile import load_profile
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
    assert not next(
        button for button in menu.buttons if button.label == "CREATE PROFILE"
    ).enabled
    assert profile_path.read_text(encoding="utf-8") == "{"


def test_resize_preserves_aspect_ratio_and_transforms_mouse_coordinates(tmp_path: Path) -> None:
    desktop = DesktopApplication(
        ApplicationController(tmp_path / "team.json", tmp_path / "game.db"),
        window_size=(1600, 900),
    )
    desktop.window_size = (1600, 900)
    event = pygame.event.Event(
        pygame.MOUSEBUTTONDOWN,
        {"pos": (800, 450), "button": 1},
    )

    logical_event = desktop._logical_event(event)

    assert logical_event.pos == (640, 360)
    assert desktop.window_size != LOGICAL_SIZE


def _click(desktop: DesktopApplication, label: str) -> None:
    desktop.router.draw(pygame.Surface(LOGICAL_SIZE))
    button = next(button for button in desktop.router.current.buttons if button.label == label)
    assert button.enabled
    for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        desktop.router.handle_event(
            pygame.event.Event(event_type, {"pos": button.rect.center, "button": 1})
        )


def _type_name(desktop: DesktopApplication, text: str) -> None:
    desktop.router.handle_event(pygame.event.Event(pygame.TEXTINPUT, {"text": text}))


def test_create_profile_in_desktop_and_start_run(tmp_path: Path) -> None:
    path = tmp_path / "team.json"
    database = tmp_path / "game.db"
    desktop = DesktopApplication(ApplicationController(path, database))
    _click(desktop, "CREATE PROFILE")
    desktop.router.draw(pygame.Surface(LOGICAL_SIZE))
    _type_name(desktop, "New Owls")
    _click(desktop, "GOLD")
    _click(desktop, "SECONDARY  /  NAVY")
    _click(desktop, "BLUE")
    _click(desktop, "SAVE PROFILE")

    profile = load_profile(path)
    assert profile is not None
    assert (profile.team_name, profile.primary_color_id, profile.secondary_color_id) == (
        "New Owls", "gold", "blue",
    )
    assert desktop.router.current_id == "main_menu"
    assert desktop.menu_state is not None and desktop.menu_state.profile == profile
    assert desktop.theme.primary == pygame.Color(profile.primary_color.hex_value)
    assert desktop.run_screen.team_name == profile.team_name
    _click(desktop, "START RUN")
    assert desktop.football_controller is not None
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    assert not database.exists()


def test_edit_profile_preserves_id_updates_theme_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "team.json"
    controller = ApplicationController(path, tmp_path / "game.db")
    original = controller.create_profile("Old Team", "crimson", "gold")
    desktop = DesktopApplication(controller)
    _click(desktop, "SETTINGS")
    _click(desktop, "Old Team")
    for _ in original.team_name:
        desktop.router.handle_event(
            pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_BACKSPACE})
        )
    _type_name(desktop, "New Team")
    _click(desktop, "NAVY")
    _click(desktop, "SAVE PROFILE")

    updated = load_profile(path)
    assert updated is not None
    assert updated.profile_id == original.profile_id
    assert (updated.team_name, updated.primary_color_id, updated.secondary_color_id) == (
        "New Team", "navy", "gold",
    )
    assert desktop.profile == updated
    assert desktop.run_screen.theme == desktop.theme
    assert desktop.run_screen.team_name == "New Team"
    restarted = DesktopApplication(ApplicationController(path, tmp_path / "other.db"))
    assert restarted.profile == updated
    _click(desktop, "START RUN")
    assert desktop.football_controller is not None
    controller = desktop.football_controller
    controller.choose_coach(0)
    while controller.state.phase is FootballRunPhase.PLAYER_DRAFT:
        controller.choose_player(controller.state.team_builder.required_position, 0)
    assert controller.state.shop is not None
    assert controller.state.shop.roster.team_name == "New Team"


def test_profile_validation_and_cancel_do_not_change_saved_profile(tmp_path: Path) -> None:
    path = tmp_path / "team.json"
    controller = ApplicationController(path, tmp_path / "game.db")
    original = controller.create_profile("Safe Team", "crimson", "gold")
    desktop = DesktopApplication(controller)
    _click(desktop, "SETTINGS")
    _click(desktop, "GOLD")
    _click(desktop, "SAVE PROFILE")
    assert desktop.router.current_id == "settings"
    assert desktop.profile_screen.error == "Primary and secondary colors must be different."
    assert load_profile(path) == original
    _click(desktop, "CANCEL")
    _click(desktop, "SETTINGS")
    assert desktop.profile_screen.primary_color_id == "crimson"
    assert desktop.profile_screen.error is None
    assert load_profile(path) == original


def test_profile_keyboard_entry_validation_and_navigation(tmp_path: Path) -> None:
    path = tmp_path / "team.json"
    desktop = DesktopApplication(ApplicationController(path, tmp_path / "game.db"))
    _click(desktop, "CREATE PROFILE")
    desktop.router.draw(pygame.Surface(LOGICAL_SIZE))
    _click(desktop, "SAVE PROFILE")
    assert desktop.profile_screen.error == "Team name cannot be empty."
    assert not path.exists()
    _click(desktop, "TYPE TEAM NAME")
    _type_name(desktop, "Keyboard Team")
    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB})
    )
    assert desktop.profile_screen.focus_index == 1
    _click(desktop, "SAVE PROFILE")
    assert load_profile(path).team_name == "Keyboard Team"


def test_existing_profile_appearing_during_creation_is_not_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "team.json"
    desktop = DesktopApplication(ApplicationController(path, tmp_path / "game.db"))
    _click(desktop, "CREATE PROFILE")
    desktop.router.draw(pygame.Surface(LOGICAL_SIZE))
    _type_name(desktop, "New Team")
    path.write_text("external profile", encoding="utf-8")
    _click(desktop, "SAVE PROFILE")
    assert "already exists" in desktop.profile_screen.error
    assert path.read_text(encoding="utf-8") == "external profile"


def test_profile_save_error_is_visible_and_keeps_existing_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "team.json"
    controller = ApplicationController(path, tmp_path / "game.db")
    original = controller.create_profile("Safe Team", "crimson", "gold")
    desktop = DesktopApplication(controller)
    _click(desktop, "SETTINGS")

    def fail_save(_profile: object) -> None:
        raise OSError("Profile save failed")

    monkeypatch.setattr(controller, "save_profile", fail_save)
    _click(desktop, "SAVE PROFILE")
    assert desktop.profile_screen.error == "Profile save failed"
    assert desktop.profile == original
    assert load_profile(path) == original


def test_profile_name_focus_survives_mouse_motion(tmp_path: Path) -> None:
    desktop = DesktopApplication(
        ApplicationController(tmp_path / "team.json", tmp_path / "game.db")
    )
    _click(desktop, "CREATE PROFILE")
    desktop.router.draw(pygame.Surface(LOGICAL_SIZE))
    palette = next(button for button in desktop.profile_screen.buttons if button.label == "GOLD")
    desktop.router.handle_event(
        pygame.event.Event(pygame.MOUSEMOTION, {"pos": palette.rect.center})
    )
    _type_name(desktop, "New Team")
    assert desktop.profile_screen.name == "New Team"


def test_window_loop_creates_profile_and_enters_run(tmp_path: Path) -> None:
    path = tmp_path / "team.json"
    desktop = DesktopApplication(ApplicationController(path, tmp_path / "game.db"))
    stage = 0

    def click_events(label: str) -> list[pygame.event.Event]:
        button = next(button for button in desktop.router.current.buttons if button.label == label)
        return [
            pygame.event.Event(event_type, {"pos": button.rect.center, "button": 1})
            for event_type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP)
        ]

    def events() -> list[pygame.event.Event]:
        nonlocal stage
        if desktop._transition_is_active(pygame.time.get_ticks()):
            return []
        if stage == 0:
            stage += 1
            return click_events("CREATE PROFILE")
        if stage == 1:
            stage += 1
            return [pygame.event.Event(pygame.TEXTINPUT, {"text": "Window Team"})]
        if stage == 2:
            stage += 1
            return click_events("SAVE PROFILE")
        if stage == 3:
            stage += 1
            return click_events("START RUN")
        return [pygame.event.Event(pygame.QUIT)]

    desktop.run(event_source=events)

    assert load_profile(path).team_name == "Window Team"
    assert desktop.router.current_id == "football_run"
    assert desktop.football_controller is not None
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    assert not (tmp_path / "game.db").exists()
