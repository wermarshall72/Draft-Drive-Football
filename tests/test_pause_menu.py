"""The unified pause menu, Return to Menu / Continue Run, and the two-step Quit Run."""

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.engine.football import FootballTeamSide
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import FootballRunPhase
from src.ui.football_pause_menu import QUIT_CONFIRM_MS, PauseMenu
from src.ui.football_run_summary import replace_run_summary, run_summary
from src.ui.football_ui_kit import text_audit

from test_football_desktop import (
    _activate,
    _assert_text_fits,
    _draft_to_shop,
    _force_result,
    _new_desktop,
    _new_desktop_with_removal_offer,
    _play_first_match_card,
    _start_match,
    _start_run,
    _surface,
)

# Esc-driven tests: a visible first-time tip would take Esc first.
pytestmark = pytest.mark.usefixtures("tips_seen")

PAUSE_LABELS = ["KEEP PLAYING", "RETURN TO MENU", "QUIT RUN"]
MATCH_PAUSE_LABELS = ["KEEP PLAYING", "DEPTH CHART", "PLAY LOG", "RETURN TO MENU", "QUIT RUN"]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000

    def __call__(self) -> int:
        return self.now


def _esc(desktop) -> None:
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE}))


def _key(desktop, key) -> None:
    desktop.router.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": key}))


def _draw(desktop) -> None:
    desktop.router.draw(_surface())


def _labels(desktop) -> list[str]:
    _draw(desktop)
    return [button.label for button in desktop.router.current.buttons]


def _menu_labels(desktop) -> list[str]:
    _draw(desktop)
    return [button.label for button in desktop.menu_screen.buttons]


def _clocked(desktop) -> FakeClock:
    clock = FakeClock()
    desktop.run_screen.pause.clock = clock
    return clock


def _to_player_draft(desktop) -> None:
    _start_run(desktop)
    _activate(desktop, "CHOOSE STAFF 01")


def _to_shop(desktop) -> None:
    _start_run(desktop)
    _draft_to_shop(desktop)


def _round_trip(desktop) -> None:
    """Pause, Return to Menu, then Continue Run."""
    _activate(desktop, "PAUSE")
    _activate(desktop, "RETURN TO MENU")
    assert desktop.router.current_id == "main_menu"
    assert _menu_labels(desktop)[0] == "CONTINUE RUN"
    assert desktop.menu_screen.buttons[0].focused
    _activate(desktop, "CONTINUE RUN")
    assert desktop.router.current_id == "football_run"


# -- component -------------------------------------------------------------------------


def test_pause_menu_quit_needs_two_presses_within_the_window() -> None:
    clock = FakeClock()
    menu = PauseMenu(clock)
    quits: list[bool] = []
    menu.press_quit(lambda: quits.append(True))
    assert menu.confirming and not quits
    clock.now += QUIT_CONFIRM_MS - 1
    assert menu.confirming and 0 < menu.remaining_fraction() < 0.01
    menu.press_quit(lambda: quits.append(True))
    assert quits == [True] and not menu.confirming

    menu.press_quit(lambda: quits.append(True))
    clock.now += QUIT_CONFIRM_MS
    assert not menu.confirming
    menu.press_quit(lambda: quits.append(True))
    assert quits == [True] and menu.confirming
    assert menu.cancel_quit() and not menu.cancel_quit()


# -- Keep Playing and Esc ---------------------------------------------------------------


def test_keep_playing_restores_focus_and_screen_on_the_shop(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _to_shop(desktop)
    screen = desktop.run_screen
    _draw(desktop)
    screen._focus(3)
    focused_label = screen.buttons[3].label
    before = desktop.football_controller.state
    _esc(desktop)
    assert screen.pause.is_open
    assert _labels(desktop) == PAUSE_LABELS and screen.buttons[0].focused
    _activate(desktop, "KEEP PLAYING")
    assert not screen.pause.is_open
    _draw(desktop)
    assert screen.focus_index == 3 and screen.buttons[3].label == focused_label
    assert desktop.football_controller.state == before


@pytest.mark.parametrize("phase", ["coach", "player", "shop", "depth", "playbook", "result"])
def test_escape_opens_and_closes_the_pause_menu_everywhere(
    tmp_path: Path, monkeypatch, phase: str,
) -> None:
    desktop = _new_desktop(tmp_path)
    if phase == "coach":
        _start_run(desktop)
    elif phase == "player":
        _to_player_draft(desktop)
    elif phase == "result":
        _start_match(desktop)
        _force_result(monkeypatch, FootballTeamSide.TEAM_A)
        _play_first_match_card(desktop)
        desktop.run_screen._result_view.clock = None
    else:
        _to_shop(desktop)
        if phase == "depth":
            _activate(desktop, "DEPTH CHART")
        elif phase == "playbook":
            _activate(desktop, "PLAYBOOK")
    screen = desktop.run_screen
    before = desktop.football_controller.state
    review_mode = screen.shop_review.mode
    assert "PAUSE" in _labels(desktop)
    _esc(desktop)
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    texts = {text for text, _r, _c in records}
    assert {"PAUSED", "Esc to keep playing", *PAUSE_LABELS} <= texts
    assert [button.label for button in screen.buttons] == PAUSE_LABELS
    # Enter on the default focus is KEEP PLAYING, never a quit.
    _key(desktop, pygame.K_RETURN)
    assert not screen.pause.is_open
    _esc(desktop)
    assert screen.pause.is_open
    _esc(desktop)
    assert not screen.pause.is_open
    assert screen.shop_review.mode == review_mode
    assert desktop.football_controller.state == before
    assert desktop.router.current_id == "football_run"


def test_match_pause_has_every_option_and_escape_backs_out_in_order(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    screen = desktop.run_screen
    _draw(desktop)
    _esc(desktop)
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    assert [button.label for button in screen.buttons] == MATCH_PAUSE_LABELS
    assert screen.buttons[0].focused
    _activate(desktop, "PLAY LOG")
    _esc(desktop)
    assert screen.match_screen.popup.kind == "pause"
    _draw(desktop)
    assert screen.buttons[screen.focus_index].label == "PLAY LOG"
    _esc(desktop)
    assert not screen.match_screen.popup.open


def test_inner_popups_keep_escape_priority_over_pause(tmp_path: Path) -> None:
    desktop = _new_desktop_with_removal_offer(tmp_path)
    _draft_to_shop(desktop)
    screen = desktop.run_screen
    controller = desktop.football_controller

    _activate(desktop, "DEPTH CHART")
    screen.shop_review.open_team_upgrades()
    _esc(desktop)
    assert not screen.shop_review.team_popup and not screen.pause.is_open
    assert screen.shop_review.mode == "depth"
    _esc(desktop)
    assert screen.pause.is_open
    _esc(desktop)
    _activate(desktop, "BACK TO SHOP")

    _activate(desktop, "PLAYBOOK")
    _draw(desktop)
    now = [0]
    screen.shop_review.inspect.clock = lambda: now[0]
    card = next(b for b in screen.buttons if getattr(b, "inspect_key", None) is not None)
    _key(desktop, pygame.K_TAB)
    screen._focus(screen.buttons.index(card))
    _draw(desktop)
    now[0] += 1000
    _draw(desktop)
    assert screen.shop_review.inspect.shown_key == card.inspect_key
    _esc(desktop)
    _draw(desktop)
    assert screen.shop_review.inspect.shown_key is None and not screen.pause.is_open
    _activate(desktop, "BACK TO SHOP")
    _draw(desktop)

    card = next(b for b in screen.buttons if getattr(b, "card_id", None) == "test-removal")
    card.action()
    assert controller.state.shop.pending_removal is not None
    _esc(desktop)
    assert controller.state.shop.pending_removal is None
    assert screen.shop_review.mode is None and not screen.pause.is_open


# -- Quit Run ---------------------------------------------------------------------------


def test_quit_run_confirms_times_out_and_cancels(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _to_shop(desktop)
    clock = _clocked(desktop)
    screen = desktop.run_screen
    _esc(desktop)
    _activate(desktop, "QUIT RUN")
    assert _labels(desktop)[-1] == "CONFIRM QUIT"
    assert desktop.router.current_id == "football_run"
    clock.now += QUIT_CONFIRM_MS
    assert _labels(desktop)[-1] == "QUIT RUN"

    _activate(desktop, "QUIT RUN")
    _esc(desktop)  # Esc cancels the armed quit first...
    assert screen.pause.is_open and _labels(desktop)[-1] == "QUIT RUN"
    _activate(desktop, "QUIT RUN")
    _key(desktop, pygame.K_UP)  # ...and moving focus away also reverts it.
    assert _labels(desktop)[-1] == "QUIT RUN"
    assert desktop.football_controller is not None

    _activate(desktop, "QUIT RUN")
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    _activate(desktop, "CONFIRM QUIT")
    assert desktop.router.current_id == "main_menu"
    assert desktop.football_controller is None and desktop.run_screen.controller is None
    assert "CONTINUE RUN" not in _menu_labels(desktop)


def test_quit_run_from_the_match_by_keyboard_clears_the_run(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _clocked(desktop)
    _draw(desktop)
    _esc(desktop)
    _draw(desktop)
    for _ in range(4):
        _key(desktop, pygame.K_DOWN)
    _key(desktop, pygame.K_RETURN)
    assert _labels(desktop)[-1] == "CONFIRM QUIT"
    _key(desktop, pygame.K_RETURN)
    assert desktop.router.current_id == "main_menu"
    assert desktop.football_controller is None
    assert "CONTINUE RUN" not in _menu_labels(desktop)


# -- Return to Menu and Continue Run ----------------------------------------------------


def test_continue_resumes_the_coach_draft_with_the_same_focus(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    screen = desktop.run_screen
    controller = desktop.football_controller
    _draw(desktop)
    _key(desktop, pygame.K_TAB)
    focus = screen.focus_index
    assert focus != 0
    before = controller.state
    _esc(desktop)
    _activate(desktop, "RETURN TO MENU")
    _activate(desktop, "CONTINUE RUN")
    _draw(desktop)
    assert screen.focus_index == focus
    assert desktop.football_controller is controller and controller.state == before


def test_continue_resumes_the_player_draft_step(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _to_player_draft(desktop)
    _activate(desktop, "DRAFT QB", keyboard=True)
    controller = desktop.football_controller
    before = controller.state
    _round_trip(desktop)
    assert controller.state == before
    assert controller.state.team_builder.required_position is before.team_builder.required_position
    assert "DRAFT RB" in _labels(desktop)


def test_continue_resumes_the_shop_day_ap_and_offers(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _to_shop(desktop)
    _activate(desktop, "NEXT DAY · 1 AP")
    controller = desktop.football_controller
    before = controller.state
    assert before.shop.day == 2
    _round_trip(desktop)
    assert desktop.run_screen.shop_review.mode is None
    assert controller.state == before
    assert "FINISH SHOP / START MATCH" in _labels(desktop)


@pytest.mark.parametrize("mode", ["depth", "playbook"])
def test_continue_returns_to_the_shop_sub_screen(tmp_path: Path, mode: str) -> None:
    desktop = _new_desktop(tmp_path)
    _to_shop(desktop)
    _activate(desktop, "DEPTH CHART" if mode == "depth" else "PLAYBOOK")
    desktop.run_screen.shop_review.modified_stats = mode == "depth"
    _round_trip(desktop)
    assert desktop.run_screen.shop_review.mode == mode
    assert "BACK TO SHOP" in _labels(desktop)
    if mode == "depth":
        assert desktop.run_screen.shop_review.modified_stats


def test_continue_returns_to_a_pending_removal(tmp_path: Path) -> None:
    desktop = _new_desktop_with_removal_offer(tmp_path)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    ap = controller.state.shop.remaining_ap
    _draw(desktop)
    next(b for b in desktop.run_screen.buttons if getattr(b, "card_id", None) == "test-removal").action()
    pending = controller.state.shop.pending_removal
    assert pending is not None
    _round_trip(desktop)
    assert controller.state.shop.pending_removal == pending
    assert controller.state.shop.remaining_ap == ap
    assert desktop.run_screen.shop_review.mode == "playbook"
    assert "CANCEL SELECTION" in _labels(desktop)


def test_continue_mid_match_keeps_the_down_hand_and_score_without_replaying(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    screen = desktop.run_screen
    match_screen = screen.match_screen
    controller = desktop.football_controller
    # Play until an AI replay is in progress, then leave mid-replay.
    for _ in range(20):
        _play_first_match_card(desktop) if controller.state.human_decision is not None else None
        _draw(desktop)
        if match_screen.playback.blocking():
            break
    assert match_screen.playback.blocking()
    before = controller.state
    target = match_screen.playback.target
    _esc(desktop)
    _activate(desktop, "RETURN TO MENU")
    assert "WEEK 1 · " in desktop.menu_screen.run_summary()[0]
    _activate(desktop, "CONTINUE RUN")
    _draw(desktop)
    assert controller.state == before
    assert not match_screen.popup.open
    assert not match_screen.playback.blocking()
    assert match_screen.playback.shown == target
    assert controller.state.phase is FootballRunPhase.MATCH


def test_continue_returns_to_the_regular_result_screen(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)
    _play_first_match_card(desktop)
    desktop.run_screen._result_view.clock = None
    _skip = desktop.run_screen.match_screen
    _draw(desktop)
    _skip.playback.skip()
    assert desktop.football_controller.state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
    _round_trip(desktop)
    assert _labels(desktop) == ["OPEN NEXT WEEK SHOP", "PAUSE"]


# -- ended runs and replacing a run -----------------------------------------------------


def test_ended_runs_are_not_resumable(tmp_path: Path, monkeypatch) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_B)
    for game_number in range(1, 4):
        _play_first_match_card(desktop)
        if game_number < 3:
            _activate(desktop, "OPEN NEXT WEEK SHOP")
            _activate(desktop, "FINISH SHOP / START MATCH")
    _draw(desktop)
    desktop.run_screen.match_screen.playback.skip()
    assert desktop.football_controller.state.phase is FootballRunPhase.FIRED
    assert "PAUSE" not in _labels(desktop)
    _esc(desktop)
    assert not desktop.run_screen.pause.is_open
    _activate(desktop, "RETURN TO MAIN MENU")
    assert desktop.router.current_id == "main_menu"
    assert desktop.football_controller is None
    assert _menu_labels(desktop)[0] == "START RUN"


def test_returning_during_a_run_ending_final_replay_clears_the_run(
    tmp_path: Path, monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_B)
    for game_number in range(1, 4):
        _play_first_match_card(desktop)
        if game_number < 3:
            _activate(desktop, "OPEN NEXT WEEK SHOP")
            _activate(desktop, "FINISH SHOP / START MATCH")
    assert desktop.football_controller.state.phase is FootballRunPhase.FIRED
    # Forced results add no events, so pin the screen on the final replay directly.
    monkeypatch.setattr(desktop.run_screen.match_screen, "holds_final_playback", lambda _state: True)
    _draw(desktop)
    _esc(desktop)
    assert _labels(desktop) == MATCH_PAUSE_LABELS
    _activate(desktop, "RETURN TO MENU")
    assert desktop.router.current_id == "main_menu"
    assert "CONTINUE RUN" not in _menu_labels(desktop)


def test_start_run_with_a_remembered_run_asks_before_replacing(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path, seeds=(17, 29, 4, 1, 18, 30, 5, 2))
    _to_shop(desktop)
    first = desktop.football_controller
    _activate(desktop, "PAUSE")
    _activate(desktop, "RETURN TO MENU")
    _activate(desktop, "START RUN")
    menu = desktop.menu_screen
    assert menu.confirm_replace
    _draw(desktop)
    assert [b.label for b in menu.buttons] == ["CANCEL", "START NEW RUN"]
    assert menu.buttons[0].focused
    _key(desktop, pygame.K_RETURN)  # default focus is CANCEL
    assert not menu.confirm_replace and desktop.football_controller is first
    _activate(desktop, "START RUN")
    _esc(desktop)
    assert not menu.confirm_replace and desktop.football_controller is first
    _activate(desktop, "HARD")
    _activate(desktop, "START RUN")
    _activate(desktop, "START NEW RUN")
    assert desktop.router.current_id == "football_run"
    assert desktop.football_controller is not first
    assert desktop.football_controller.state.phase is FootballRunPhase.COACH_DRAFT
    assert desktop.football_controller.state.opponent_difficulty is FootballAIDifficulty.HARD


def test_replace_confirmation_text_fits_with_the_run_summary(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path, team_name="Northern Saskatchewan Polytechnic Huskies")
    _to_shop(desktop)
    _activate(desktop, "PAUSE")
    _activate(desktop, "RETURN TO MENU")
    _activate(desktop, "START RUN")
    with text_audit() as records:
        _draw(desktop)
    _assert_text_fits(records)
    texts = {text for text, _r, _c in records}
    assert "START A NEW RUN?" in texts
    assert "Your current run (Week 1 · 0-0 · Standard) will be lost." in texts


# -- summaries, profile edits -----------------------------------------------------------


def test_continue_run_summary_text(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop, FootballAIDifficulty.HARD)
    state = lambda: desktop.football_controller.state  # noqa: E731
    assert run_summary(state()) == "DRAFT · COACHES · HARD"
    assert replace_run_summary(state()) == "Draft · 0-0 · Hard"
    _activate(desktop, "CHOOSE STAFF 01")
    _activate(desktop, "DRAFT QB", keyboard=True)
    assert run_summary(state()) == "DRAFT · PLAYERS 1/8 · HARD"
    from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
    for position in PLAYER_DRAFT_ORDER[1:]:
        _activate(desktop, f"DRAFT {position.value}", keyboard=True)
    assert run_summary(state()) == "WEEK 1 · SHOP DAY 1 · 0-0 · HARD"
    _activate(desktop, "FINISH SHOP / START MATCH")
    match = state().match
    assert run_summary(state()) == (
        f"WEEK 1 · 1ST HALF · {match.team_a_score}-{match.team_b_score} · HARD"
    )
    assert replace_run_summary(state()) == "Week 1 · 0-0 · Hard"


def test_continue_run_button_shows_the_summary_and_fits(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _to_shop(desktop)
    _activate(desktop, "PAUSE")
    _activate(desktop, "RETURN TO MENU")
    menu = desktop.menu_screen
    summaries: list[str] = []
    original = menu._draw_continue_button

    def record(surface, button, summary, active, pressed):
        summaries.append(summary)
        assert menu.badge_font.size(summary)[0] <= button.rect.width - 52
        original(surface, button, summary, active, pressed)

    menu._draw_continue_button = record
    _draw(desktop)
    assert summaries == ["WEEK 1 · SHOP DAY 1 · 0-0 · STANDARD"]
    buttons = menu.buttons
    assert [b.label for b in buttons] == [
        "CONTINUE RUN", "START RUN", "EASY", "STANDARD", "HARD", "SETTINGS", "HOW TO PLAY", "QUIT",
    ]
    assert all(buttons[i].rect.bottom < buttons[i + 1].rect.top for i in (0, 1, 4, 6))
    assert buttons[5].rect.top == buttons[6].rect.top and buttons[5].rect.right < buttons[6].rect.left
    assert buttons[-1].rect.bottom < 642


def test_profile_edit_while_remembered_updates_theme_but_keeps_team_name(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path, seeds=(17, 29, 4, 1, 18, 30, 5, 2))
    _to_shop(desktop)
    _activate(desktop, "PAUSE")
    _activate(desktop, "RETURN TO MENU")
    desktop.save_profile("Renamed Team", "crimson", "gold")
    assert desktop.router.current_id == "main_menu"
    _activate(desktop, "CONTINUE RUN")
    with text_audit() as records:
        _draw(desktop)
    texts = {text for text, _r, _c in records}
    assert desktop.run_screen.theme == desktop.theme
    assert desktop.run_screen.team_name == "Test Owls"
    assert any("TEST OWLS" in text for text in texts)
    assert not any("RENAMED TEAM" in text for text in texts)
    _activate(desktop, "PAUSE")
    _activate(desktop, "RETURN TO MENU")
    _activate(desktop, "START RUN")
    _activate(desktop, "START NEW RUN")
    assert desktop.run_screen.team_name == "Renamed Team"


@pytest.mark.parametrize("phase", ["coach", "shop", "playbook"])
def test_keyboard_focus_on_pause_survives_redraw_and_resume(tmp_path: Path, phase: str) -> None:
    desktop = _new_desktop(tmp_path)
    if phase == "coach":
        _start_run(desktop)
    else:
        _to_shop(desktop)
        if phase == "playbook":
            _activate(desktop, "PLAYBOOK")
    screen = desktop.run_screen
    _draw(desktop)
    pause_index = next(i for i, b in enumerate(screen.buttons) if b.label == "PAUSE")
    screen._focus(pause_index)
    _draw(desktop)
    _draw(desktop)
    assert screen.focus_index == pause_index
    _key(desktop, pygame.K_RETURN)
    assert screen.pause.is_open
    _activate(desktop, "RETURN TO MENU")
    _activate(desktop, "CONTINUE RUN")
    _draw(desktop)
    assert screen.buttons[screen.focus_index].label == "PAUSE"
