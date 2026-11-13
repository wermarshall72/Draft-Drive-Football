from dataclasses import replace
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.application import ApplicationController
from src.engine.football import (
    DefensiveSchemeAction,
    FootballFourthDownAction,
    FootballMatchResult,
    FootballMatchStatus,
    FootballPosition,
    FootballTeamSide,
    OffensivePlayAction,
)
from src.engine.football_ai import FootballAIDifficulty
from src.engine.football_controller import (
    FootballHumanDecision,
    FootballRunPhase,
)
from src.engine.football_simulator import FootballMatchSimulator
from src.engine.football_team_builder import PLAYER_DRAFT_ORDER
from src.ui.application import DesktopApplication
from src.ui.layout import LOGICAL_SIZE


def _new_desktop(
    tmp_path: Path,
    *,
    team_name: str = "Test Owls",
    seeds: tuple[int, int, int, int] = (17, 29, 4, 1),
) -> DesktopApplication:
    tmp_path.mkdir(parents=True, exist_ok=True)
    application_controller = ApplicationController(
        tmp_path / "team.json",
        tmp_path / "legacy-game.db",
    )
    application_controller.create_profile(team_name, "navy", "gold")
    seed_values = iter(seeds)
    return DesktopApplication(
        application_controller,
        seed_factory=lambda: next(seed_values),
    )


def _surface() -> pygame.Surface:
    return pygame.Surface(LOGICAL_SIZE)


def _activate(
    desktop: DesktopApplication,
    label: str,
    *,
    index: int = 0,
    keyboard: bool = False,
) -> None:
    desktop.router.draw(_surface())
    screen = desktop.router.current
    matching = [button for button in screen.buttons if button.label == label]
    button = matching[index]
    if keyboard:
        screen.focus_index = screen.buttons.index(button)
        desktop.router.handle_event(
            pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RETURN})
        )
    else:
        desktop.router.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN,
                {"pos": button.rect.center, "button": 1},
            )
        )
        desktop.router.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONUP,
                {"pos": button.rect.center, "button": 1},
            )
        )


def _start_run(
    desktop: DesktopApplication,
    difficulty: FootballAIDifficulty = FootballAIDifficulty.STANDARD,
) -> None:
    _activate(desktop, difficulty.value.upper())
    _activate(desktop, "START RUN")


def _draft_to_shop(desktop: DesktopApplication) -> None:
    _activate(desktop, "CHOOSE COACH AVERY")
    for position in PLAYER_DRAFT_ORDER:
        state = desktop.football_controller.state
        assert state.phase is FootballRunPhase.PLAYER_DRAFT
        assert state.team_builder.required_position is position
        button_label = f"DRAFT {position.value}"
        _activate(desktop, button_label, keyboard=True)


def _start_match(desktop: DesktopApplication) -> None:
    _start_run(desktop)
    _draft_to_shop(desktop)
    _activate(desktop, "FINISH SHOP / START MATCH")


def _force_result(monkeypatch, winner: FootballTeamSide) -> None:
    def finish(simulator: FootballMatchSimulator, _play: OffensivePlayAction):
        score_a = 7 if winner is FootballTeamSide.TEAM_A else 0
        score_b = 7 if winner is FootballTeamSide.TEAM_B else 0
        result = FootballMatchResult(score_a, score_b, winner, True)
        simulator.state = replace(
            simulator.state,
            team_a_score=score_a,
            team_b_score=score_b,
            status=FootballMatchStatus.COMPLETED,
            awaited_action=None,
            current_drive_defensive_scheme=None,
            final_result=result,
        )
        return simulator.state

    monkeypatch.setattr(FootballMatchSimulator, "resolve_offensive_play", finish)


def test_menu_uses_selected_difficulty_and_four_independent_seeds(
    tmp_path: Path,
) -> None:
    values = iter((101, 202, 303, 404))
    calls = 0

    def seed_factory() -> int:
        nonlocal calls
        calls += 1
        return next(values)

    application_controller = ApplicationController(
        tmp_path / "team.json",
        tmp_path / "legacy-game.db",
    )
    application_controller.create_profile("Difficulty Owls", "crimson", "gold")
    desktop = DesktopApplication(application_controller, seed_factory=seed_factory)

    _activate(desktop, "HARD")
    _activate(desktop, "START RUN")

    assert desktop.router.current_id == "football_run"
    assert desktop.football_controller is not None
    state = desktop.football_controller.state
    assert state.team_builder.current_offer == state.team_builder.coach_offer
    assert state.opponent_difficulty is FootballAIDifficulty.HARD
    assert calls == 4
    assert not (tmp_path / "legacy-game.db").exists()
    with pytest.raises(ValueError, match="Unknown desktop screen"):
        desktop.router.show("roster")


def test_coach_and_eight_position_draft_are_controller_driven(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop, FootballAIDifficulty.EASY)
    controller = desktop.football_controller
    assert controller is not None
    coach_offer = controller.state.team_builder.coach_offer

    _activate(desktop, f"CHOOSE {coach_offer[0].name.upper()}", keyboard=True)
    assert controller.state.team_builder.selected_coach is coach_offer[0]
    assert controller.state.team_builder.required_position is FootballPosition.QB

    for position in PLAYER_DRAFT_ORDER:
        state = controller.state
        assert state.human_decision is FootballHumanDecision.DRAFT_PLAYER
        assert state.team_builder.required_position is position
        assert len(state.team_builder.current_offer) == 3
        candidates = state.team_builder.current_offer
        assert all(candidate.position is position for candidate in candidates)
        assert all(candidate.description for candidate in candidates)
        _activate(desktop, f"DRAFT {position.value}", keyboard=True)

    state = controller.state
    assert state.phase is FootballRunPhase.PRE_MATCH_SHOP
    assert state.team_builder.completed
    assert set(state.team_builder.selected_players) == set(FootballPosition)
    assert state.shop is not None and state.shop.remaining_budget == 6


def test_shop_purchase_and_finish_start_the_match(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    _draft_to_shop(desktop)
    controller = desktop.football_controller
    assert controller is not None
    shop = controller.state.shop
    assert shop is not None
    assert shop.remaining_budget == 6

    _activate(desktop, "BUY UPGRADE")
    purchased = controller.state.shop
    assert purchased is not None
    assert purchased.remaining_budget == 6 - shop.offer[0].cost
    assert purchased.purchased_upgrades == (shop.offer[0],)
    _activate(desktop, "BUY UPGRADE", index=1)
    purchased_twice = controller.state.shop
    assert purchased_twice is not None
    assert len(purchased_twice.purchased_upgrades) == 2
    assert purchased_twice.remaining_budget < purchased.remaining_budget

    _activate(desktop, "FINISH SHOP / START MATCH")
    state = controller.state
    assert state.phase is FootballRunPhase.MATCH
    assert state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY
    assert state.shop is not None and state.shop.finished
    assert state.match is not None
    assert state.match.team_a.team_name == "Test Owls"
    assert state.match.team_b.team_name == "Local AI"


def test_match_controls_follow_decisions_ai_advances_and_game_finishes(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None
    screen = desktop.run_screen
    initial = controller.state.match
    assert initial is not None
    assert initial.team_a.team_name == "Test Owls"
    assert initial.team_b.team_name == "Local AI"

    seen_offense = False
    seen_defense = False
    seen_fourth_down = False
    seen_ai_play = False
    for _ in range(1200):
        state = controller.state
        if state.phase is not FootballRunPhase.MATCH:
            break
        assert state.match is not None
        desktop.router.draw(_surface())
        labels = {button.label: button for button in screen.buttons}
        event_count = len(state.match.match_events)
        if state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY:
            seen_offense = True
            expected = OffensivePlayAction.DEEP_PASS
            allowed = {
                "RB RUN",
                "SCREEN PASS",
                "PLAY-ACTION PASS",
                "SHORT PASS",
                "MEDIUM PASS",
                "DEEP PASS",
            }
            assert set(labels) - {"PAUSE"} == allowed
            labels["DEEP PASS"].action()
        elif state.human_decision is FootballHumanDecision.DEFENSIVE_SCHEME:
            seen_defense = True
            expected = DefensiveSchemeAction.RB_RUN
            allowed = {
                "RB RUN SCHEME",
                "SCREEN PASS SCHEME",
                "PLAY-ACTION SCHEME",
                "SHORT PASS SCHEME",
                "MEDIUM PASS SCHEME",
                "DEEP PASS SCHEME",
            }
            assert set(labels) - {"PAUSE"} == allowed
            labels["RB RUN SCHEME"].action()
        elif state.human_decision is FootballHumanDecision.FOURTH_DOWN:
            seen_fourth_down = True
            expected = FootballFourthDownAction.PUNT
            assert set(labels) - {"PAUSE"} == {
                "GO FOR IT",
                "PUNT",
                "FIELD GOAL",
            }
            labels["PUNT"].action()
        else:
            pytest.fail(f"Unexpected match decision: {state.human_decision}")

        updated = controller.state
        assert updated.match is not None
        new_events = updated.match.match_events[event_count:]
        assert new_events
        assert new_events[0].action is expected
        seen_ai_play = seen_ai_play or any(
            event.possession is FootballTeamSide.TEAM_B
            and isinstance(event.action, OffensivePlayAction)
            for event in new_events
        )
    else:
        pytest.fail("The seeded desktop match did not finish.")

    final = controller.state
    assert final.phase in (
        FootballRunPhase.READY_FOR_NEXT_GAME,
        FootballRunPhase.FIRED,
        FootballRunPhase.PLAYOFFS,
    )
    assert final.match is not None
    assert final.match.status is FootballMatchStatus.COMPLETED
    assert final.match.final_result is not None
    assert seen_offense and seen_defense and seen_fourth_down and seen_ai_play
    desktop.router.draw(_surface())
    assert any(
        button.label in {"NEXT REGULAR-SEASON GAME", "RETURN TO MAIN MENU"}
        for button in screen.buttons
    )


def test_match_screen_uses_pause_and_numbered_play_calls(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    controller = desktop.football_controller
    assert controller is not None
    screen = desktop.run_screen

    desktop.router.draw(_surface())
    labels = {button.label: button for button in screen.buttons}
    assert set(labels) == {
        "RB RUN",
        "SCREEN PASS",
        "PLAY-ACTION PASS",
        "SHORT PASS",
        "MEDIUM PASS",
        "DEEP PASS",
        "PAUSE",
    }

    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_2})
    )
    match = controller.state.match
    assert match is not None
    assert match.match_events[-1].action is OffensivePlayAction.SCREEN_PASS

    desktop.router.draw(_surface())
    next(button for button in screen.buttons if button.label == "PAUSE").action()
    desktop.router.draw(_surface())
    assert {button.label for button in screen.buttons} == {
        "DISCARD RUN",
        "KEEP PLAYING",
    }


@pytest.mark.parametrize(
    ("winner", "games", "expected_phase", "expected_button"),
    (
        (
            FootballTeamSide.TEAM_B,
            3,
            FootballRunPhase.FIRED,
            "RETURN TO MAIN MENU",
        ),
        (
            FootballTeamSide.TEAM_A,
            10,
            FootballRunPhase.PLAYOFFS,
            "RETURN TO MAIN MENU",
        ),
    ),
)
def test_result_routes_fired_and_game_ten_playoffs_without_bracket(
    tmp_path: Path,
    monkeypatch,
    winner: FootballTeamSide,
    games: int,
    expected_phase: FootballRunPhase,
    expected_button: str,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _force_result(monkeypatch, winner)
    controller = desktop.football_controller
    assert controller is not None

    for game_number in range(1, games + 1):
        _activate(desktop, "DEEP PASS")
        state = controller.state
        if game_number < games:
            assert state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
            _activate(desktop, "NEXT REGULAR-SEASON GAME")
            assert controller.state.game_number == game_number + 1

    final = controller.state
    assert final.phase is expected_phase
    assert final.game_number == games
    assert final.match is not None and final.match.final_result is not None
    desktop.router.draw(_surface())
    assert any(button.label == expected_button for button in desktop.run_screen.buttons)
    assert desktop.run_screen.state == final
    assert not (tmp_path / "legacy-game.db").exists()


def test_ready_for_next_game_button_starts_the_next_regular_season_match(
    tmp_path: Path,
    monkeypatch,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_match(desktop)
    _force_result(monkeypatch, FootballTeamSide.TEAM_A)
    _activate(desktop, "DEEP PASS")

    controller = desktop.football_controller
    assert controller is not None
    assert controller.state.phase is FootballRunPhase.READY_FOR_NEXT_GAME
    _activate(desktop, "NEXT REGULAR-SEASON GAME", keyboard=True)
    assert controller.state.phase is FootballRunPhase.MATCH
    assert controller.state.game_number == 2
    assert controller.state.human_decision is FootballHumanDecision.OFFENSIVE_PLAY


def test_invalid_action_is_visible_and_does_not_change_controller_state(
    tmp_path: Path,
) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    desktop.router.draw(_surface())
    coach_button = next(
        button
        for button in desktop.run_screen.buttons
        if button.label == "CHOOSE COACH AVERY"
    )
    coach_button.action()
    controller = desktop.football_controller
    assert controller is not None
    before = controller.state

    coach_button.action()

    assert controller.state == before
    assert desktop.run_screen.state == before
    assert desktop.run_screen.last_error is not None
    assert "phase" in desktop.run_screen.last_error
    canvas = _surface()
    desktop.router.draw(canvas)
    assert desktop.run_screen.last_error is not None
    assert desktop.run_screen.state == before
    error_visible = any(
        canvas.get_at((x, y)) == desktop.theme.danger
        for x in range(24, 800)
        for y in range(canvas.get_height() - 55, canvas.get_height() - 35)
    )
    assert error_visible


def test_repeated_draws_do_not_change_state_or_consume_gameplay_rng(
    tmp_path: Path,
) -> None:
    first = _new_desktop(tmp_path / "first", team_name="Same Team")
    replay = _new_desktop(tmp_path / "replay", team_name="Same Team")
    _start_run(first)
    _start_run(replay)
    for desktop in (first, replay):
        _activate(desktop, "CHOOSE COACH AVERY")
    first_controller = first.football_controller
    replay_controller = replay.football_controller
    assert first_controller is not None and replay_controller is not None
    assert first_controller.state == replay_controller.state

    for _ in range(30):
        first.router.draw(_surface())
    assert first_controller.state == replay_controller.state
    for position in PLAYER_DRAFT_ORDER:
        _activate(first, f"DRAFT {position.value}")
        _activate(replay, f"DRAFT {position.value}")
        assert first_controller.state == replay_controller.state
    for _ in range(30):
        first.router.draw(_surface())
    assert first_controller.state == replay_controller.state

    _activate(first, "FINISH SHOP / START MATCH")
    _activate(replay, "FINISH SHOP / START MATCH")
    for _ in range(30):
        first.router.draw(_surface())
    assert first_controller.state == replay_controller.state
    _activate(first, "DEEP PASS")
    _activate(replay, "DEEP PASS")
    assert first_controller.state == replay_controller.state
    assert not (tmp_path / "first" / "legacy-game.db").exists()
    assert not (tmp_path / "replay" / "legacy-game.db").exists()


def test_escape_requests_explicit_discard_confirmation(tmp_path: Path) -> None:
    desktop = _new_desktop(tmp_path)
    _start_run(desktop)
    screen = desktop.run_screen
    desktop.router.handle_event(
        pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})
    )
    assert desktop.router.current_id == "football_run"
    desktop.router.draw(_surface())
    assert {button.label for button in screen.buttons} == {
        "DISCARD RUN",
        "KEEP PLAYING",
    }

    _activate(desktop, "KEEP PLAYING")
    assert desktop.router.current_id == "football_run"
    assert not screen.confirm_exit
