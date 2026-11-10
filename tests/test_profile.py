import re
from io import StringIO
from pathlib import Path

import pytest

from src.main import _edit_settings, _load_or_create_profile
from src.profile import (
    COLOR_CHOICES,
    ProfileError,
    TeamProfile,
    format_color_grid,
    load_profile,
    new_team_profile,
    save_profile,
    style_text,
    supports_ansi_color,
)


def test_first_launch_creates_and_saves_profile(tmp_path: Path) -> None:
    profile_path = tmp_path / "nested" / "team.json"
    answers = iter(("Home Team", "1", "2"))
    output: list[str] = []
    profile = _load_or_create_profile(
        profile_path,
        reader=lambda _prompt: next(answers),
        writer=output.append,
        ansi_enabled=False,
    )

    assert profile.team_name == "Home Team"
    assert profile.primary_color_id == "crimson"
    assert profile.secondary_color_id == "scarlet"
    assert len(profile.profile_id) == 36
    assert load_profile(profile_path) == profile
    assert any("Saved profile" in message for message in output)


def test_saved_profile_reloads_without_prompting(tmp_path: Path) -> None:
    profile_path = tmp_path / "team.json"
    expected = new_team_profile("Returning Team", "navy", "gold")
    save_profile(expected, profile_path)

    def unexpected_prompt(_prompt: str) -> str:
        raise AssertionError("A saved profile should not prompt for onboarding.")

    assert (
        _load_or_create_profile(profile_path, reader=unexpected_prompt) == expected
    )


def test_settings_edit_name_and_both_colors(tmp_path: Path) -> None:
    profile_path = tmp_path / "team.json"
    original = new_team_profile("Old Team", "crimson", "scarlet")
    save_profile(original, profile_path)
    answers = iter(("1", "Updated Team", "4", "4", "3", "0"))

    updated = _edit_settings(
        original,
        profile_path,
        reader=lambda _prompt: next(answers),
        writer=lambda _text: None,
        ansi_enabled=False,
    )

    assert updated.profile_id == original.profile_id
    assert updated.team_name == "Updated Team"
    assert updated.primary_color_id == "coral"
    assert updated.secondary_color_id == "rose"
    assert load_profile(profile_path) == updated


def test_first_launch_rejects_duplicate_colors(tmp_path: Path) -> None:
    answers = iter(("Home Team", "1", "1", "2"))
    output: list[str] = []

    profile = _load_or_create_profile(
        tmp_path / "team.json",
        reader=lambda _prompt: next(answers),
        writer=output.append,
        ansi_enabled=False,
    )

    assert profile.primary_color_id != profile.secondary_color_id
    assert any("must be different" in message for message in output)


def test_first_launch_rejects_invalid_color_choices(tmp_path: Path) -> None:
    answers = iter(("Home Team", "0", "31", "nope", "²", "1", "2"))
    output: list[str] = []

    profile = _load_or_create_profile(
        tmp_path / "team.json",
        reader=lambda _prompt: next(answers),
        writer=output.append,
        ansi_enabled=False,
    )

    assert profile.primary_color_id == "crimson"
    assert profile.secondary_color_id == "scarlet"
    assert sum("color number from 1 to 30" in text for text in output) == 4


def test_team_name_rejects_blank_and_listed_profanity(tmp_path: Path) -> None:
    answers = iter(("", "   ", "Shit Team", "Clean Team", "1", "2"))
    output: list[str] = []

    profile = _load_or_create_profile(
        tmp_path / "team.json",
        reader=lambda _prompt: next(answers),
        writer=output.append,
        ansi_enabled=False,
    )

    assert profile.team_name == "Clean Team"
    assert sum("Team name cannot be empty." in text for text in output) == 2
    assert any("local filter checks a small list" in text for text in output)

    with pytest.raises(ProfileError):
        TeamProfile("not-a-uuid", "Bad Team", "crimson", "scarlet")


def test_color_palette_is_six_by_five_and_has_ansi_and_plain_modes() -> None:
    assert len(COLOR_CHOICES) == 30
    assert len({color.id for color in COLOR_CHOICES}) == 30
    assert all(color.hex_value.startswith("#") for color in COLOR_CHOICES)
    assert all(color.ansi_foreground_code for color in COLOR_CHOICES)
    assert all(color.ansi_background_code for color in COLOR_CHOICES)

    plain_grid = format_color_grid(ansi_enabled=False)
    rows = plain_grid.splitlines()
    assert len(rows) == 5
    assert all(len(re.findall(r"\b\d{2} ", row)) == 6 for row in rows)
    assert "\033[" not in plain_grid

    ansi_grid = format_color_grid(ansi_enabled=True)
    assert ansi_grid.count("\033[48;5;") == 30
    assert ansi_grid.count("\033[0m") == 30
    assert style_text("team", enabled=False) == "team"
    assert style_text("team", foreground=COLOR_CHOICES[0], enabled=True).startswith(
        "\033[38;5;160m"
    )


def test_ansi_detection_respects_terminal_and_no_color() -> None:
    class TTY(StringIO):
        def isatty(self) -> bool:
            return True

    assert supports_ansi_color(TTY(), {})
    assert not supports_ansi_color(TTY(), {"NO_COLOR": ""})
    assert not supports_ansi_color(TTY(), {"TERM": "dumb"})
    assert not supports_ansi_color(StringIO(), {})
