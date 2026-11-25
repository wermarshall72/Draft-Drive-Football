"""The legacy snapshot database lives in the app-data folder, never the repo."""

from __future__ import annotations

import importlib
import os
import pkgutil
import random
import sqlite3
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

import src
from src import desktop as desktop_entry
from src.application import ApplicationController
from src.db import schema
from src.engine.football_ai import FootballAIDifficulty
from src.persistence.paths import (
    APP_DATA_NAME,
    DATA_DIR_ENV,
    LEGACY_DATABASE_FILE_NAME,
    LINUX_APP_DATA_NAME,
    legacy_database_path,
)
from src.persistence.run_save import RunSaveStore
from src.ui.application import DesktopApplication
from tests.football_run_driver import step

REPO_ROOT = Path(__file__).resolve().parents[1]
_SKIPPED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _repo_files() -> set[Path]:
    files: set[Path] = set()
    for directory, subdirs, names in os.walk(REPO_ROOT):
        subdirs[:] = [d for d in subdirs if d not in _SKIPPED_DIRS and not d.endswith(".egg-info")]
        files.update(Path(directory) / name for name in names)
    return files


def _database_files(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.suffix in {".db", ".sqlite", ".sqlite3"}]


# --- the path helper ---------------------------------------------------------


def test_follows_the_environment_and_the_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "from-env"))
    assert legacy_database_path() == tmp_path / "from-env" / LEGACY_DATABASE_FILE_NAME
    assert legacy_database_path(tmp_path / "from-arg") == (
        tmp_path / "from-arg" / LEGACY_DATABASE_FILE_NAME
    )
    # Resolved at call time: a later change takes effect.
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "changed"))
    assert legacy_database_path() == tmp_path / "changed" / LEGACY_DATABASE_FILE_NAME
    # Asking for the path creates nothing.
    assert not (tmp_path / "from-env").exists()
    assert not (tmp_path / "from-arg").exists()


@pytest.mark.parametrize(
    ("platform", "relative"),
    [
        ("darwin", Path("Library") / "Application Support" / APP_DATA_NAME),
        ("win32", Path("AppData") / "Roaming" / APP_DATA_NAME),
        ("linux", Path(".local") / "share" / LINUX_APP_DATA_NAME),
    ],
)
def test_lands_in_the_os_app_data_folder_otherwise(
    platform: str, relative: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv(DATA_DIR_ENV)
    monkeypatch.delenv("APPDATA")
    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    assert legacy_database_path() == home / relative / LEGACY_DATABASE_FILE_NAME
    assert not home.exists()


# --- the terminal client -----------------------------------------------------


def test_terminal_start_run_creates_the_database_in_the_app_data_folder(
    isolated_data_folders: Path,
) -> None:
    before = _repo_files()
    controller = ApplicationController()
    controller.create_profile("Terminal Owls", "navy", "gold")
    assert not (isolated_data_folders / LEGACY_DATABASE_FILE_NAME).exists()

    controller.start_run()

    database = isolated_data_folders / LEGACY_DATABASE_FILE_NAME
    assert database.is_file()
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "snapshots" in tables
    assert controller._game is not None and Path(controller._game.db_path) == database
    assert _repo_files() == before


def test_schema_helpers_default_to_the_app_data_folder(isolated_data_folders: Path) -> None:
    before = _repo_files()
    schema.init_db()
    assert (isolated_data_folders / LEGACY_DATABASE_FILE_NAME).is_file()
    assert schema.get_random_snapshot(1) is None
    assert _repo_files() == before


# --- the desktop -------------------------------------------------------------


def test_desktop_flow_never_opens_a_database(
    isolated_data_folders: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[object] = []
    real_connect = sqlite3.connect

    def recording_connect(*args, **kwargs):
        opened.append(args[0] if args else kwargs.get("database"))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", recording_connect)
    before = _repo_files()

    controller = ApplicationController()
    controller.create_profile("Desktop Owls", "navy", "gold")
    seeds = random.Random(5)
    desktop = DesktopApplication(controller, seed_factory=lambda: seeds.getrandbits(64))
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    football = desktop.run_screen.controller
    rng = random.Random(3)
    for _ in range(5000):
        if football.state.games_played >= 1:
            break
        outcome: list[bool] = []
        desktop.run_screen._submit(lambda: outcome.append(step(football, rng)))
        assert outcome[0]
    else:
        pytest.fail("The first match never finished.")

    assert opened == []
    assert _database_files(isolated_data_folders) == []
    assert _repo_files() == before


def test_desktop_entry_point_keeps_the_database_path_in_the_data_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[DesktopApplication] = []
    monkeypatch.setattr(DesktopApplication, "run", lambda self: built.append(self))
    data_dir = tmp_path / "chosen"

    desktop_entry.main(["--data-dir", str(data_dir)])

    (desktop,) = built
    assert Path(desktop.controller.db_path) == data_dir / LEGACY_DATABASE_FILE_NAME
    assert isinstance(desktop.run_store, RunSaveStore)
    assert _database_files(tmp_path) == []


# --- no import-time writable paths in the repo --------------------------------


def test_schema_has_no_repo_relative_database_path() -> None:
    assert not hasattr(schema, "DB_PATH")


def test_no_module_holds_a_writable_path_inside_the_repo() -> None:
    # Read-only bundled files the game is allowed to point at.
    read_only = (REPO_ROOT / "src" / "ui" / "assets", REPO_ROOT / "pyproject.toml")
    offenders: list[str] = []
    for module_info in pkgutil.walk_packages(src.__path__, "src."):
        if module_info.name.endswith(".__main__"):
            continue  # runs the app on import
        module = importlib.import_module(module_info.name)
        for name, value in vars(module).items():
            if not isinstance(value, Path):
                continue
            resolved = value.resolve()
            if not resolved.is_relative_to(REPO_ROOT):
                continue
            if any(resolved == root or resolved.is_relative_to(root) for root in read_only):
                continue
            offenders.append(f"{module_info.name}.{name} = {value}")
    assert offenders == []
