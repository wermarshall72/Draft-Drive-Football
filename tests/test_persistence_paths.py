"""Data-folder resolution per OS, overrides, and the one-time profile move."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.application import ApplicationController
from src.persistence.paths import (
    APP_DATA_NAME,
    DATA_DIR_ENV,
    LINUX_APP_DATA_NAME,
    app_data_dir,
)
from src.profile import (
    PROFILE_FILE_NAME,
    default_profile_path,
    legacy_profile_path,
    load_profile,
    new_team_profile,
    save_profile,
)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv(DATA_DIR_ENV)
    return home


def test_macos_uses_application_support(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert app_data_dir(create=False) == (
        home / "Library" / "Application Support" / "Draft Drive Football"
    )


def test_windows_uses_appdata(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert app_data_dir(create=False) == tmp_path / "Roaming" / "Draft Drive Football"
    monkeypatch.delenv("APPDATA")
    assert app_data_dir(create=False) == home / "AppData" / "Roaming" / APP_DATA_NAME


def test_linux_uses_xdg_data_home_then_local_share(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert app_data_dir(create=False) == tmp_path / "xdg" / "draft-drive-football"
    monkeypatch.setenv("XDG_DATA_HOME", "relative/ignored")
    assert app_data_dir(create=False) == home / ".local" / "share" / "draft-drive-football"
    monkeypatch.delenv("XDG_DATA_HOME")
    assert app_data_dir(create=False) == home / ".local" / "share" / LINUX_APP_DATA_NAME


def test_argument_and_environment_overrides(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "from-env"))
    assert app_data_dir() == tmp_path / "from-env"
    assert app_data_dir(tmp_path / "from-arg" / "nested") == tmp_path / "from-arg" / "nested"
    assert (tmp_path / "from-arg" / "nested").is_dir()  # created on demand
    assert not home.exists()


def test_app_data_name_is_defined_once() -> None:
    assert APP_DATA_NAME == "Draft Drive Football"
    assert LINUX_APP_DATA_NAME == "draft-drive-football"


def _legacy_profile(name: str = "Legacy Owls"):
    profile = new_team_profile(name, "navy", "gold")
    save_profile(profile, legacy_profile_path())
    return profile


def test_legacy_profile_is_copied_once_and_kept(home: Path, tmp_path: Path) -> None:
    profile = _legacy_profile()
    legacy = home / ".cfb-auto-battler" / "profile.json"
    assert legacy_profile_path() == legacy
    data_dir = tmp_path / "data"

    path = default_profile_path(data_dir)

    assert path == data_dir / PROFILE_FILE_NAME
    assert load_profile(path) == profile
    assert legacy.exists() and load_profile(legacy) == profile

    # Not repeated once the new profile exists, even if the old one changes.
    save_profile(new_team_profile("Changed Legacy", "crimson", "gold"), legacy)
    assert load_profile(default_profile_path(data_dir)) == profile


def test_no_legacy_profile_means_no_copy(home: Path, tmp_path: Path) -> None:
    path = default_profile_path(tmp_path / "data")
    assert not path.exists()
    assert load_profile(path) is None


def test_application_controller_defaults_to_the_data_folder(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _legacy_profile("Default Owls")
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "data"))
    controller = ApplicationController(db_path=tmp_path / "game.db")
    assert Path(controller.profile_path) == tmp_path / "data" / PROFILE_FILE_NAME
    assert controller.load_profile() == profile
