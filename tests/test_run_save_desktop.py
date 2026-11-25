"""Desktop flow around the saved run: restart, continue, replace, quit, failures."""

from __future__ import annotations

import json
import os
import random
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.application import ApplicationController
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import (
    FootballGameController,
    FootballHumanDecision,
    FootballRunPhase,
)
from src.persistence.migrations import CURRENT_SCHEMA_VERSION
from src.persistence.run_save import (
    BACKUP_FILE_NAME,
    RUN_FILE_NAME,
    RunSaveStore,
    encode_envelope,
)
from src.ui import main_menu
from src.ui.application import (
    DAMAGED_NOTICE,
    NEWER_VERSION_NOTICE,
    RESTORED_NOTICE,
    SAVE_FAILED_NOTICE,
    DesktopApplication,
)
from src.ui.football_run_summary import run_summary
from src.ui.layout import LOGICAL_SIZE
from tests.football_run_driver import new_controller, step


def _desktop(data_dir: Path, seed: int = 11) -> DesktopApplication:
    data_dir.mkdir(parents=True, exist_ok=True)
    controller = ApplicationController(data_dir / "profile.json", data_dir / "legacy.db")
    if controller.load_profile() is None:
        controller.create_profile("Save Owls", "navy", "gold")
    seeds = random.Random(seed)
    return DesktopApplication(
        controller,
        seed_factory=lambda: seeds.getrandbits(64),
        run_store=RunSaveStore(data_dir),
    )


def _draw(desktop: DesktopApplication) -> pygame.Surface:
    surface = pygame.Surface(LOGICAL_SIZE)
    desktop.router.draw(surface)
    return surface


def _ui_step(desktop: DesktopApplication, rng: random.Random) -> bool:
    """One decision submitted through the run screen, as a click would."""
    outcome: list[bool] = []
    controller = desktop.run_screen.controller
    desktop.run_screen._submit(lambda: outcome.append(step(controller, rng)))
    return outcome[0]


def _play_until(desktop: DesktopApplication, rng: random.Random, predicate) -> None:
    for _ in range(5000):
        if predicate(desktop.run_screen.controller):
            return
        assert _ui_step(desktop, rng)
    pytest.fail("The run never reached the requested point.")


def _saved(data_dir: Path) -> dict:
    return json.loads((data_dir / RUN_FILE_NAME).read_text(encoding="utf-8"))["payload"]["run"]


def _menu_button(desktop: DesktopApplication, label: str):
    _draw(desktop)
    return next(button for button in desktop.menu_screen.buttons if button.label == label)


def _write_save(data_dir: Path, run: dict, version: int = CURRENT_SCHEMA_VERSION) -> None:
    from datetime import datetime, timezone

    envelope = json.loads(encode_envelope({"run": run}, datetime.now(timezone.utc)))
    envelope["schema_version"] = version
    (data_dir / RUN_FILE_NAME).write_text(json.dumps(envelope), encoding="utf-8")


def _in_match(controller: FootballGameController) -> bool:
    state = controller.state
    return (
        state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
        and len(state.match.match_events) > 12
    )


def test_continue_run_after_restart_resumes_the_same_match_decision(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    _play_until(desktop, random.Random(4), _in_match)
    original = desktop.run_screen.controller
    expected = original.to_save_data()
    assert _saved(tmp_path) == json.loads(json.dumps(expected))

    restarted = _desktop(tmp_path)

    assert restarted.router.current_id == "main_menu"
    summary = restarted.remembered_run_summary()
    assert summary is not None and summary[0] == run_summary(original.state)
    _menu_button(restarted, main_menu.CONTINUE_RUN).action()
    assert restarted.router.current_id == "football_run"
    screen = restarted.run_screen
    assert screen.controller.to_save_data() == expected
    assert screen.state == original.state
    assert screen.team_name == "Save Owls"
    _draw(restarted)
    assert not screen.match_screen.playback.blocking()  # no replay of seen plays
    assert screen.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    hand = {card.copy_id for card in screen.state.match.team_a_offense_deck.hand}
    assert hand == {card.copy_id for card in original.state.match.team_a_offense_deck.hand}


def test_continue_run_reopens_a_pending_removal_in_the_playbook(tmp_path: Path) -> None:
    controller = new_controller(2)
    rng = random.Random(2)
    while not (
        controller.state.shop is not None
        and controller.state.phase is FootballRunPhase.PRE_MATCH_SHOP
        and controller.state.shop.pending_removal is not None
    ):
        assert step(controller, rng)
    tmp_path.mkdir(exist_ok=True)
    RunSaveStore(tmp_path).save(controller)

    restarted = _desktop(tmp_path)
    restarted.continue_run()

    assert restarted.run_screen.shop_review.mode == "playbook"
    assert restarted.run_screen.state.shop.pending_removal is not None
    _draw(restarted)


def test_starting_a_new_run_over_a_save_confirms_then_replaces_it(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    for _ in range(5):
        _ui_step(desktop, random.Random(1))
    old_seed = _saved(tmp_path)["builder"]["seed"]

    restarted = _desktop(tmp_path, seed=12)
    _menu_button(restarted, main_menu.START_RUN).action()
    assert restarted.menu_screen.confirm_replace
    assert restarted.router.current_id == "main_menu"
    _draw(restarted)
    next(
        button for button in restarted.menu_screen.buttons
        if button.label == main_menu.START_NEW_RUN
    ).action()

    assert restarted.router.current_id == "football_run"
    saved = _saved(tmp_path)
    assert saved["phase"] == FootballRunPhase.COACH_DRAFT.value
    assert saved["builder"]["seed"] != old_seed


def test_quit_run_deletes_the_save(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    for _ in range(12):
        _ui_step(desktop, random.Random(3))
    assert (tmp_path / RUN_FILE_NAME).exists() and (tmp_path / BACKUP_FILE_NAME).exists()

    desktop.run_screen._quit_run()

    assert not (tmp_path / RUN_FILE_NAME).exists()
    assert not (tmp_path / BACKUP_FILE_NAME).exists()
    assert _desktop(tmp_path).remembered_run_summary() is None


def test_an_ended_run_deletes_its_save(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    rng = random.Random(8)
    while _ui_step(desktop, rng):
        pass
    assert desktop.run_screen.controller.state.phase in (
        FootballRunPhase.FIRED, FootballRunPhase.ELIMINATED, FootballRunPhase.CHAMPION,
    )
    assert not (tmp_path / RUN_FILE_NAME).exists()
    assert not (tmp_path / BACKUP_FILE_NAME).exists()
    assert _desktop(tmp_path).remembered_run_summary() is None


def test_return_to_menu_and_quit_save_the_run(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    for _ in range(15):
        _ui_step(desktop, random.Random(5))
    expected = json.loads(json.dumps(desktop.run_screen.controller.to_save_data()))

    desktop.run_store.delete()
    desktop.run_screen._return_to_menu()
    assert desktop.router.current_id == "main_menu"
    assert _saved(tmp_path) == expected

    desktop.run_store.delete()
    desktop.quit()
    assert _saved(tmp_path) == expected


def test_window_close_event_saves_the_run(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    _ui_step(desktop, random.Random(6))
    desktop.run_store.delete()

    desktop.run(event_source=lambda: [pygame.event.Event(pygame.QUIT)])

    assert _saved(tmp_path)["phase"] == FootballRunPhase.PLAYER_DRAFT.value


def test_write_failure_shows_one_notice_and_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    store = desktop.run_store
    real_save = store.save
    calls: list[int] = []

    def failing_save(controller: FootballGameController) -> None:
        calls.append(1)
        raise PermissionError("read-only folder")

    monkeypatch.setattr(store, "save", failing_save)
    rng = random.Random(7)
    _ui_step(desktop, rng)
    screen = desktop.run_screen
    assert screen.save_notice == SAVE_FAILED_NOTICE
    _draw(desktop)  # draws the banner without blocking play
    screen.save_notice = None
    _ui_step(desktop, rng)
    assert screen.save_notice is None  # shown once, not on every retry
    assert len(calls) == 2

    monkeypatch.setattr(store, "save", real_save)
    _ui_step(desktop, rng)
    assert _saved(tmp_path) == json.loads(json.dumps(screen.controller.to_save_data()))
    monkeypatch.setattr(store, "save", failing_save)
    _ui_step(desktop, rng)
    assert screen.save_notice == SAVE_FAILED_NOTICE  # a new failure after a success


def test_restored_from_backup_shows_a_notice(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    for _ in range(6):
        _ui_step(desktop, random.Random(9))
    backup = _saved(tmp_path)
    _ui_step(desktop, random.Random(10))
    (tmp_path / RUN_FILE_NAME).write_bytes((tmp_path / RUN_FILE_NAME).read_bytes()[:-40])

    restarted = _desktop(tmp_path)

    assert restarted.save_notice == RESTORED_NOTICE
    assert restarted.remembered_run_summary() is not None
    assert json.loads(json.dumps(restarted.run_screen.controller.to_save_data())) == backup
    _draw(restarted)


def test_both_files_damaged_reports_and_starts_fresh(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    for _ in range(4):
        _ui_step(desktop, random.Random(9))
    (tmp_path / RUN_FILE_NAME).write_text("{}", encoding="utf-8")
    (tmp_path / BACKUP_FILE_NAME).write_text("[", encoding="utf-8")

    restarted = _desktop(tmp_path)

    assert restarted.save_notice == DAMAGED_NOTICE
    assert restarted.remembered_run_summary() is None
    assert len(list(tmp_path.glob("run*.damaged-*.json"))) == 2
    _menu_button(restarted, main_menu.START_RUN).action()
    assert restarted.router.current_id == "football_run"
    assert (tmp_path / RUN_FILE_NAME).exists()


def test_unknown_card_offers_abandon_and_keeps_the_file(tmp_path: Path) -> None:
    controller = new_controller(4)
    rng = random.Random(4)
    for _ in range(30):
        step(controller, rng)
    run = json.loads(json.dumps(controller.to_save_data()))
    run["shop"]["defensive_deck"][0][1] = "retired_scheme"
    tmp_path.mkdir(exist_ok=True)
    _write_save(tmp_path, run)
    original = (tmp_path / RUN_FILE_NAME).read_bytes()

    restarted = _desktop(tmp_path)

    notice = restarted.save_notice
    assert notice is not None and notice.abandonable and "retired_scheme" in notice.message
    assert restarted.remembered_run_summary() is None
    restarted.quit()  # nothing to save, and the unloadable file is untouched
    assert (tmp_path / RUN_FILE_NAME).read_bytes() == original

    _menu_button(restarted, main_menu.ABANDON_SAVE).action()

    assert restarted.save_notice is None
    assert not (tmp_path / RUN_FILE_NAME).exists()
    abandoned = list(tmp_path.glob("run.abandoned-*.json"))
    assert len(abandoned) == 1 and abandoned[0].read_bytes() == original
    _draw(restarted)
    assert all(b.label != main_menu.ABANDON_SAVE for b in restarted.menu_screen.buttons)


def test_newer_version_save_needs_confirmation_before_a_new_run(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    controller = new_controller(6)
    _write_save(tmp_path, controller.to_save_data(), CURRENT_SCHEMA_VERSION + 1)
    original = (tmp_path / RUN_FILE_NAME).read_bytes()

    restarted = _desktop(tmp_path)

    assert restarted.save_notice == NEWER_VERSION_NOTICE
    _menu_button(restarted, main_menu.START_RUN).action()
    assert restarted.menu_screen.confirm_replace
    assert (tmp_path / RUN_FILE_NAME).read_bytes() == original
    _draw(restarted)
    next(
        button for button in restarted.menu_screen.buttons
        if button.label == main_menu.START_NEW_RUN
    ).action()

    assert restarted.router.current_id == "football_run"
    assert _saved(tmp_path)["phase"] == FootballRunPhase.COACH_DRAFT.value
    abandoned = list(tmp_path.glob("run.abandoned-*.json"))
    assert len(abandoned) == 1 and abandoned[0].read_bytes() == original


def test_profile_color_edit_keeps_the_saved_run_jerseys(tmp_path: Path) -> None:
    desktop = _desktop(tmp_path)
    desktop.start_new_run(FootballAIDifficulty.STANDARD)
    for _ in range(4):
        _ui_step(desktop, random.Random(2))
    appearances = dict(desktop.run_screen.controller.state.player_appearances)
    assert appearances

    restarted = _desktop(tmp_path)
    restarted.save_profile("Renamed Owls", "crimson", "silver")
    restarted.continue_run()

    assert restarted.theme.primary == pygame.Color("#D70000")
    assert restarted.run_screen.team_name == "Save Owls"
    assert dict(restarted.run_screen.controller.state.player_appearances) == appearances
    _draw(restarted)


def test_startup_without_a_profile_leaves_a_save_alone(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    RunSaveStore(tmp_path).save(new_controller(1))
    controller = ApplicationController(tmp_path / "missing.json", tmp_path / "legacy.db")
    desktop = DesktopApplication(controller, run_store=RunSaveStore(tmp_path))
    assert desktop.remembered_run_summary() is None
    assert (tmp_path / RUN_FILE_NAME).exists()
