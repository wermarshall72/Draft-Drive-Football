"""Settings: helmet preview, color swatches, audio volumes (settings.json), and the
pause menu's AUDIO view."""

import json
import logging
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src import audio_settings as audio_module
from src.audio_settings import (
    AudioSettings, load_audio_settings, save_audio_settings, settings_path,
)
from src.profile import COLOR_BY_ID
from src.ui import main_menu_art, profile_screen as profile_module, team_helmet
from src.ui.football_ui_kit import text_audit
from src.ui.team_helmet import draw_team_helmet, helmet_sprite, letter_rect
from src.ui.volume_slider import VolumeSlider

from test_football_desktop import (
    _activate, _assert_text_fits, _draft_to_shop, _new_desktop, _start_match, _start_run,
    _surface,
)

pytestmark = pytest.mark.usefixtures("tips_seen")


def _draw(desktop) -> None:
    desktop.router.draw(_surface())


def _labels(desktop) -> list[str]:
    _draw(desktop)
    return [button.label for button in desktop.router.current.buttons]


def _key(desktop, key) -> None:
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key}))


def _mouse(desktop, kind, pos) -> None:
    data = {"pos": pos}
    if kind == pygame.MOUSEMOTION:
        data.update(rel=(0, 0), buttons=(1, 0, 0))
    else:
        data["button"] = 1
    desktop.router.handle_event(pygame.event.Event(kind, data))


def _slider(desktop, label: str) -> VolumeSlider:
    _draw(desktop)
    return next(b for b in desktop.router.current.buttons if b.label == label)


def _open_settings(tmp_path: Path, **kwargs):
    desktop = _new_desktop(tmp_path, **kwargs)
    desktop.navigate("settings")
    _draw(desktop)
    return desktop


def _saved(desktop) -> dict:
    return json.loads(desktop.settings_path.read_text(encoding="utf-8"))


# -- settings.json -------------------------------------------------------------------


def test_missing_settings_file_means_default_volumes(tmp_path: Path) -> None:
    settings = load_audio_settings(tmp_path / "settings.json")
    assert settings == AudioSettings(70, 80)
    assert (settings.music_gain, settings.effects_gain) == (0.7, 0.8)
    assert not (tmp_path / "settings.json").exists()


def test_settings_file_lives_in_the_app_data_folder(isolated_data_folders: Path) -> None:
    assert settings_path() == isolated_data_folders / "settings.json"
    save_audio_settings(AudioSettings(10, 95))
    assert load_audio_settings() == AudioSettings(10, 95)
    assert (isolated_data_folders / "settings.json").is_file()


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    save_audio_settings(AudioSettings(0, 100), path)
    assert load_audio_settings(path) == AudioSettings(0, 100)
    assert json.loads(path.read_text())["music_volume"] == 0


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", "\x00\xff", '"music"'])
def test_damaged_settings_fall_back_and_are_kept(tmp_path: Path, caplog, text: str) -> None:
    path = tmp_path / "settings.json"
    path.write_text(text, encoding="latin-1")
    with caplog.at_level(logging.WARNING):
        assert load_audio_settings(path) == AudioSettings()
    assert caplog.records
    assert path.read_text(encoding="latin-1") == text  # never deleted or rewritten


@pytest.mark.parametrize(
    ("music", "effects", "expected"),
    [
        (150, -20, (100, 0)),
        (42, 43, (40, 45)),
        (37.5, 2.4, (40, 0)),
        ("loud", None, (70, 80)),
        (True, [5], (70, 80)),
    ],
)
def test_bad_volume_values_clamp_or_fall_back(tmp_path: Path, music, effects, expected) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"music_volume": music, "effects_volume": effects}))
    settings = load_audio_settings(path)
    assert (settings.music_volume, settings.effects_volume) == expected


def test_non_finite_volume_falls_back(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"music_volume": NaN, "effects_volume": Infinity}')
    assert load_audio_settings(path) == AudioSettings()


def test_desktop_loads_volumes_and_survives_a_failed_save(
    tmp_path: Path, monkeypatch, caplog,
) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    save_audio_settings(AudioSettings(25, 50), tmp_path / "settings.json")
    desktop = _new_desktop(tmp_path)
    assert desktop.settings_path == tmp_path / "settings.json"
    assert desktop.audio_settings == AudioSettings(25, 50)
    assert (desktop.music_gain, desktop.effects_gain) == (0.25, 0.5)

    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("src.ui.application.save_audio_settings", fail)
    with caplog.at_level(logging.WARNING):
        desktop.update_audio_settings(AudioSettings(30, 50), True)
    assert desktop.audio_settings == AudioSettings(30, 50)
    assert "disk full" in caplog.text


def test_damaged_settings_never_block_startup(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "settings.json").write_text("{{{")
    desktop = _new_desktop(tmp_path)
    assert desktop.audio_settings == AudioSettings()
    assert (tmp_path / "settings.json").read_text() == "{{{"


def test_settings_model_rejects_off_step_values() -> None:
    with pytest.raises(ValueError):
        AudioSettings(72, 80)
    assert audio_module.normalize_volume(97.5) == 100


# -- the Settings screen's sliders ------------------------------------------------------


def test_dragging_a_slider_saves_on_release_and_cancel_keeps_it(tmp_path: Path) -> None:
    desktop = _open_settings(tmp_path)
    music = _slider(desktop, "Music")
    track = music.track
    _mouse(desktop, pygame.MOUSEBUTTONDOWN, (track.left + track.width // 4, track.centery))
    assert desktop.audio_settings.music_volume == 25
    _mouse(desktop, pygame.MOUSEMOTION, (track.left + track.width // 2, track.centery))
    assert desktop.audio_settings.music_volume == 50
    assert _slider(desktop, "Music").active and _slider(desktop, "Music").value == 50
    assert not desktop.settings_path.exists()  # nothing written mid-drag
    _mouse(desktop, pygame.MOUSEMOTION, (track.right + 80, track.centery))
    _mouse(desktop, pygame.MOUSEBUTTONUP, (track.right + 80, track.centery))
    assert desktop.audio_settings.music_volume == 100
    assert _saved(desktop)["music_volume"] == 100
    assert desktop.profile_screen.buttons[desktop.profile_screen.focus_index].label == "Music"

    _activate(desktop, "CANCEL")
    assert desktop.router.current_id == "main_menu"
    assert desktop.audio_settings.music_volume == 100
    assert _saved(desktop)["music_volume"] == 100


def test_keyboard_steps_save_each_change(tmp_path: Path) -> None:
    desktop = _open_settings(tmp_path)
    screen = desktop.profile_screen
    while screen.buttons[screen.focus_index].label != "Sound effects":
        _key(desktop, pygame.K_TAB)
        _draw(desktop)
    for key, expected in (
        (pygame.K_RIGHT, 85), (pygame.K_d, 90), (pygame.K_LEFT, 85), (pygame.K_a, 80),
        (pygame.K_END, 100), (pygame.K_RIGHT, 100), (pygame.K_HOME, 0),
    ):
        _key(desktop, key)
        assert desktop.audio_settings.effects_volume == expected
        assert _saved(desktop)["effects_volume"] == expected
    assert screen.buttons[screen.focus_index].label == "Sound effects"
    _key(desktop, pygame.K_DOWN)  # Up/Down/Tab still move focus
    _draw(desktop)
    assert screen.buttons[screen.focus_index].label != "Sound effects"


def test_audio_is_available_while_creating_the_first_profile(tmp_path: Path) -> None:
    from src.application import ApplicationController
    from src.ui.application import DesktopApplication

    desktop = DesktopApplication(ApplicationController(tmp_path / "team.json", tmp_path / "x.db"))
    desktop.navigate("settings")
    labels = _labels(desktop)
    assert {"Music", "Sound effects"} <= set(labels)
    assert "SHOW TIPS AGAIN" not in labels
    music = _slider(desktop, "Music")
    _mouse(desktop, pygame.MOUSEBUTTONDOWN, music.track.midleft)
    _mouse(desktop, pygame.MOUSEBUTTONUP, music.track.midleft)
    assert _saved(desktop)["music_volume"] == 0
    assert not (tmp_path / "team.json").exists()


# -- colors, toggle, and helmet preview --------------------------------------------------


def test_swatch_for_the_other_side_is_disabled_and_labels_follow_colors(tmp_path: Path) -> None:
    desktop = _open_settings(tmp_path, primary="violet", secondary="silver")
    screen = desktop.profile_screen
    labels = _labels(desktop)
    assert "PRIMARY · VIOLET" in labels and "SECONDARY · SILVER" in labels
    swatches = {b.label: b for b in screen.buttons[3:33]}
    assert list(swatches) == [color.display_name.upper() for color in COLOR_BY_ID.values()]
    assert not swatches["SILVER"].enabled and swatches["VIOLET"].enabled
    _activate(desktop, "GOLD")
    assert screen.primary_color_id == "gold"
    assert "PRIMARY · GOLD" in _labels(desktop)
    _activate(desktop, "SECONDARY · SILVER")
    _draw(desktop)
    swatches = {b.label: b for b in screen.buttons[3:33]}
    assert not swatches["GOLD"].enabled and swatches["SILVER"].enabled
    _activate(desktop, "NAVY")
    assert (screen.primary_color_id, screen.secondary_color_id) == ("gold", "navy")
    assert "SECONDARY · NAVY" in _labels(desktop)
    assert desktop.profile.primary_color_id == "violet"  # unchanged until SAVE PROFILE


def test_hover_caption_names_the_swatch(tmp_path: Path) -> None:
    desktop = _open_settings(tmp_path, primary="violet", secondary="silver")
    screen = desktop.profile_screen
    assert screen.swatch_caption() == profile_module.SWATCH_HINT
    rects = dict(screen._swatch_rects)
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": rects["gold"].center, "rel": (0, 0), "buttons": (0, 0, 0)}))
    assert screen.swatch_caption() == "Gold"
    desktop.router.handle_event(pygame.event.Event(
        pygame.MOUSEMOTION, {"pos": rects["silver"].center, "rel": (0, 0), "buttons": (0, 0, 0)}))
    assert screen.swatch_caption().startswith("Silver")
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)


def test_preview_uses_primary_for_the_helmet_and_secondary_for_the_letter(
    tmp_path: Path, monkeypatch,
) -> None:
    calls = []
    original = profile_module.draw_team_helmet

    def spy(surface, box, name, primary, secondary, *, height):
        calls.append((name, tuple(primary[:3]), tuple(secondary[:3]), height))
        return original(surface, box, name, primary, secondary, height=height)

    monkeypatch.setattr(profile_module, "draw_team_helmet", spy)
    desktop = _open_settings(tmp_path, team_name="Mustangs", primary="navy", secondary="gold")
    navy = tuple(pygame.Color(COLOR_BY_ID["navy"].hex_value)[:3])
    gold = tuple(pygame.Color(COLOR_BY_ID["gold"].hex_value)[:3])
    assert calls[-1][:3] == ("Mustangs", navy, gold)
    assert 90 <= calls[-1][3] <= 110

    surface = pygame.Surface((300, 200))
    red, green = pygame.Color(255, 0, 0), pygame.Color(0, 255, 0)
    helmet, letter = draw_team_helmet(surface, surface.get_rect(), "mustangs", red, green, height=100)
    assert letter is not None and helmet.contains(letter)
    letter_pixels = [surface.get_at((x, y))[:3] for x in range(letter.left, letter.right)
                     for y in range(letter.top, letter.bottom)]
    assert (0, 255, 0) in letter_pixels
    helmet_pixels = [surface.get_at((x, y))[:3] for x in range(helmet.left, helmet.right, 3)
                     for y in range(helmet.top, helmet.bottom, 3)]
    assert any(r > 200 and g < 60 and b < 60 for r, g, b in helmet_pixels)


@pytest.mark.parametrize("letter", ["W", "M", "A", "I"])
def test_letter_stays_on_the_shell_clear_of_facemask_and_ear_hole(letter: str) -> None:
    helmet = pygame.Rect(40, 30, 145, 108)
    rect = letter_rect(letter, helmet)
    assert helmet.contains(rect)
    assert rect.right <= helmet.left + helmet.width * 0.43  # facemask starts beyond this
    assert rect.bottom <= helmet.top + helmet.height * 0.66  # ear hole sits below this
    assert rect.left >= helmet.left + helmet.width * 0.08
    assert rect.height <= helmet.height * 0.45 + 4
    assert abs(rect.centerx - (helmet.left + helmet.width * 0.30)) <= 1
    assert abs(rect.centery - (helmet.top + helmet.height * 0.40)) <= 1


def test_settings_screen_letter_clears_the_facemask(tmp_path: Path) -> None:
    for name in ("Wolverines", "Mustangs"):
        desktop = _open_settings(tmp_path / name, team_name=name)
        screen = desktop.profile_screen
        helmet, letter = screen.helmet_rect, screen.letter_rect
        assert letter is not None
        assert letter.right <= helmet.left + helmet.width * 0.43
        assert letter.bottom <= helmet.top + helmet.height * 0.66


def test_empty_name_draws_no_letter(tmp_path: Path) -> None:
    desktop = _open_settings(tmp_path)
    desktop.profile_screen.name = "   "
    _draw(desktop)
    assert desktop.profile_screen.letter_rect is None
    assert team_helmet.team_initial("") == "" and team_helmet.team_initial(" owls") == "O"


def test_missing_artwork_falls_back_to_a_square(monkeypatch, caplog) -> None:
    def missing(_rgb):
        raise FileNotFoundError("menu_helmet_base.png")

    helmet_sprite.cache_clear()
    monkeypatch.setattr(main_menu_art, "_tinted_helmet", missing)
    surface = pygame.Surface((200, 200))
    try:
        with caplog.at_level(logging.WARNING):
            helmet, letter = draw_team_helmet(
                surface, surface.get_rect(), "Owls", pygame.Color("#ff0000"),
                pygame.Color("#00ff00"), height=100,
            )
    finally:
        helmet_sprite.cache_clear()
    assert helmet.size == (100, 100)
    assert surface.get_at(helmet.move(6, 0).midleft)[:3] == (255, 0, 0)
    assert letter is not None and helmet.contains(letter)
    assert "helmet artwork" in caplog.text


def test_tinted_helmet_is_cached_between_frames(tmp_path: Path, monkeypatch) -> None:
    calls = []
    original = main_menu_art._tinted_helmet.__wrapped__

    def counting(rgb):
        calls.append(rgb)
        return original(rgb)

    helmet_sprite.cache_clear()
    monkeypatch.setattr(main_menu_art, "_tinted_helmet", counting)
    try:
        desktop = _open_settings(tmp_path, primary="violet", secondary="silver")
        for _ in range(3):
            _draw(desktop)
        assert len(calls) == 1
        _activate(desktop, "GOLD")
        _draw(desktop)
        _draw(desktop)
        assert len(calls) == 2
    finally:
        helmet_sprite.cache_clear()


def test_settings_layout_has_no_overlaps(tmp_path: Path) -> None:
    desktop = _open_settings(tmp_path)
    desktop.profile_screen.error = (
        "Team name contains profanity. This local filter checks a small list of terms "
        "and may not catch every variation."
    )
    _draw(desktop)
    screen = desktop.profile_screen
    rects = [button.rect for button in screen.buttons]
    for index, first in enumerate(rects):
        for second in rects[index + 1:]:
            # The two toggle halves share their border edge.
            assert not first.inflate(-2, -2).colliderect(second.inflate(-2, -2)), (first, second)
    footer = [b.rect for b in screen.buttons if b.label in ("CANCEL", "SAVE PROFILE")]
    assert all(not screen.error_rect.colliderect(rect) for rect in footer)
    assert all(not screen.error_rect.colliderect(rect) for rect in rects)
    assert all(_surface().get_rect().contains(rect) for rect in rects)


# -- the pause menu's AUDIO view ---------------------------------------------------------


def _to_shop(desktop) -> None:
    _start_run(desktop)
    _draft_to_shop(desktop)


def test_pause_audio_view_changes_show_in_settings(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _to_shop(desktop)
    screen = desktop.run_screen
    _key(desktop, pygame.K_ESCAPE)
    labels = _labels(desktop)
    assert labels.index("AUDIO") == labels.index("RETURN TO MENU") - 1
    _activate(desktop, "AUDIO")
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    assert [b.label for b in screen.buttons] == ["Music", "Sound effects", "BACK"]
    assert screen.focus_index == 0
    _key(desktop, pygame.K_RIGHT)
    assert desktop.audio_settings.music_volume == 75
    assert _saved(desktop)["music_volume"] == 75
    effects = _slider(desktop, "Sound effects")
    _mouse(desktop, pygame.MOUSEBUTTONDOWN, effects.track.midleft)
    _mouse(desktop, pygame.MOUSEBUTTONUP, effects.track.midleft)
    assert _saved(desktop)["effects_volume"] == 0

    _key(desktop, pygame.K_ESCAPE)  # back to the list, menu still open, focus on AUDIO
    assert screen.pause.is_open and not screen.pause.audio_open
    labels = _labels(desktop)
    assert labels[screen.focus_index] == "AUDIO"
    _activate(desktop, "AUDIO")
    _activate(desktop, "BACK")
    assert screen.pause.is_open and _labels(desktop)[screen.focus_index] == "AUDIO"

    _activate(desktop, "RETURN TO MENU")
    desktop.navigate("settings")
    assert _slider(desktop, "Music").value == 75
    assert _slider(desktop, "Sound effects").value == 0


def test_second_escape_closes_and_quit_run_still_needs_two_presses(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _to_shop(desktop)
    screen = desktop.run_screen
    _key(desktop, pygame.K_ESCAPE)
    _activate(desktop, "AUDIO")
    _key(desktop, pygame.K_ESCAPE)
    _key(desktop, pygame.K_ESCAPE)
    assert not screen.pause.is_open
    _key(desktop, pygame.K_ESCAPE)
    _draw(desktop)
    assert not screen.pause.audio_open  # reopening starts on the list
    _activate(desktop, "AUDIO")
    _activate(desktop, "BACK")
    _activate(desktop, "QUIT RUN")
    assert _labels(desktop)[-1] == "CONFIRM QUIT"
    _activate(desktop, "CONFIRM QUIT")
    assert desktop.router.current_id == "main_menu" and desktop.football_controller is None


def test_match_pause_audio_view_backs_out_in_order(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    screen = desktop.run_screen
    _draw(desktop)
    _key(desktop, pygame.K_ESCAPE)
    labels = _labels(desktop)
    assert labels == ["KEEP PLAYING", "DEPTH CHART", "PLAY LOG", "AUDIO", "RETURN TO MENU",
                      "QUIT RUN"]
    _activate(desktop, "AUDIO")
    assert _labels(desktop) == ["Music", "Sound effects", "BACK"]
    _key(desktop, pygame.K_LEFT)
    assert desktop.audio_settings.music_volume == 65
    _key(desktop, pygame.K_ESCAPE)
    assert screen.pause_open
    assert _labels(desktop)[screen.focus_index] == "AUDIO"
    _key(desktop, pygame.K_ESCAPE)
    _draw(desktop)
    assert not screen.pause_open


# -- the stadium (football_ui_kit) style -------------------------------------------------


def _texts(desktop) -> set[str]:
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    return {text for text, _rect, _container in records}


def test_settings_uses_the_run_screen_header_not_the_old_one(tmp_path: Path, monkeypatch) -> None:
    from src.ui.screens import Screen

    def old_header(*_args, **_kwargs):
        raise AssertionError("Settings must not draw the old Theme header")

    monkeypatch.setattr(Screen, "_header", old_header)
    desktop = _open_settings(tmp_path, team_name="Mustangs")
    texts = _texts(desktop)
    assert "SETTINGS" in texts and "MUSTANGS" in texts
    assert not {"COLLEGE FOOTBALL", "SEASON MODE"} & texts
    desktop.profile_screen.name = ""
    assert "NEW TEAM" in _texts(desktop)


def test_create_mode_title(tmp_path: Path) -> None:
    from src.application import ApplicationController
    from src.ui.application import DesktopApplication

    desktop = DesktopApplication(ApplicationController(tmp_path / "team.json", tmp_path / "x.db"))
    desktop.navigate("settings")
    texts = _texts(desktop)
    assert "CREATE YOUR TEAM" in texts and "NEW TEAM" in texts
    assert "SETTINGS" not in texts


def test_footer_buttons_use_kit_styles(tmp_path: Path) -> None:
    from src.ui.football_ui_kit import PaintedButton

    desktop = _open_settings(tmp_path)
    buttons = {b.label: b for b in desktop.profile_screen.buttons}
    assert isinstance(buttons["SAVE PROFILE"], PaintedButton)
    assert buttons["SAVE PROFILE"].variant == "kit-primary"
    assert buttons["CANCEL"].variant == "kit" and buttons["SHOW TIPS AGAIN"].variant == "kit"


def test_settings_and_pause_audio_share_one_slider_palette(tmp_path: Path) -> None:
    from src.ui.volume_slider import match_slider_palette

    desktop = _open_settings(tmp_path)
    settings_palette = _slider(desktop, "Music").palette
    assert settings_palette == match_slider_palette()
    _activate(desktop, "CANCEL")
    _to_shop(desktop)
    _key(desktop, pygame.K_ESCAPE)
    _activate(desktop, "AUDIO")
    assert _slider(desktop, "Music").palette == settings_palette
    assert _slider(desktop, "Sound effects").palette == settings_palette


@pytest.mark.parametrize("mode", ["profile", "create", "error", "long-name"])
def test_nothing_on_settings_overflows(tmp_path: Path, mode: str) -> None:
    from src.application import ApplicationController
    from src.ui.application import DesktopApplication

    if mode == "create":
        desktop = DesktopApplication(ApplicationController(tmp_path / "t.json", tmp_path / "x.db"))
        desktop.navigate("settings")
    else:
        desktop = _open_settings(tmp_path)
    screen = desktop.profile_screen
    if mode == "error":
        screen.name = "Damn Team"
        _activate(desktop, "SAVE PROFILE")
        assert screen.error
        screen._reset_tips()
    if mode == "long-name":
        screen.name = "The Extraordinarily Long Named Mountain Valley Wolverines"
    _texts(desktop)  # asserts every line fits its container
