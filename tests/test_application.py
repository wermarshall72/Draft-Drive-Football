from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.application import ApplicationController
from src.engine.game_run import GameRun
from src.engine.shop import Shop
from src.engine.simulator import MatchResult
from src.engine.units import COACH_PAIRINGS
from src.profile import load_profile


def _match_result(
    team: str,
    opponent: str,
    winner: str,
    *,
    tied: bool = False,
) -> MatchResult:
    if tied:
        team_score, opponent_score = 0, 0
    elif winner == team:
        team_score, opponent_score = 7, 0
    else:
        team_score, opponent_score = 0, 7
    return {
        "team_a": team,
        "team_b": opponent,
        "team_a_score": team_score,
        "team_b_score": opponent_score,
        "winner": winner,
        "final_momentum": 1.5,
        "events": [
            {
                "drive_number": 1,
                "cycle_number": 1,
                "team": team,
                "opponent": opponent,
                "outcome": "Touchdown",
                "detail": "Touchdown and successful conversion (7 points).",
                "points": 7,
                "team_a_score": team_score,
                "team_b_score": opponent_score,
            }
        ]
        if not tied
        else [],
    }


def test_controller_drives_run_from_profile_to_championship(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_path = tmp_path / "profile" / "team.json"
    database_path = tmp_path / "game.db"
    application = ApplicationController(profile_path, database_path)

    assert application.load_profile() is None
    with pytest.raises(RuntimeError, match="before opening the menu"):
        application.main_menu_state()

    profile = application.create_profile("Boundary Team", "crimson", "scarlet")
    assert load_profile(profile_path) == profile
    menu = application.main_menu_state()
    assert menu.profile.team_name == "Boundary Team"
    assert menu.available_actions == ("start_run", "settings", "quit")

    monkeypatch.setattr(
        "src.application.random_coach_options",
        lambda: list(COACH_PAIRINGS[:3]),
    )
    monkeypatch.setattr(
        "src.engine.shop.random.sample",
        lambda population, count: list(population[:count]),
    )
    monkeypatch.setattr(
        "src.engine.shop.random.choices",
        lambda values, **_: [values[0]],
    )
    monkeypatch.setattr(
        "src.engine.shop.random.choice",
        lambda values: values[0],
    )

    state = application.start_run()
    assert state.step == "coach_selection"
    assert state.phase == "opening_draft"
    assert state.days_remaining == Shop.OPENING_AP
    assert len(state.coach_choices) == 3
    assert state.available_actions == ("select_coach",)
    with pytest.raises(RuntimeError, match="current step is coach_selection"):
        application.roll_opening_offer()
    with pytest.raises(RuntimeError, match="match step"):
        application.advance_match()
    with pytest.raises(ValueError, match="1 to 3"):
        application.select_coach(0)

    state = application.select_coach(1)
    assert state.step == "opening_draft"
    assert state.roster.coach.name == COACH_PAIRINGS[0].name
    with pytest.raises(FrozenInstanceError):
        state.roster.players[0].power = 999.0
    assert application.run_state().roster.players[0].power == 10.0

    for position in Shop.OPENING_ORDER:
        assert state.required_position == position
        offer = application.roll_opening_offer()
        assert len(offer) == Shop.PORTAL_SIZE
        assert {player.position for player in offer} == {position}
        with pytest.raises(ValueError, match="1 to 3"):
            application.select_opening_player(0)
        state = application.select_opening_player(1)

    assert state.step == "shop"
    assert state.phase == "regular_season"
    assert state.days_remaining == Shop.DAYS_PER_SHOP
    assert len(state.roster.players) == len(Shop.OPENING_ORDER)
    with pytest.raises(RuntimeError, match="Roll the current action offer"):
        application.move_to_next_day()
    with pytest.raises(RuntimeError, match="current step is shop"):
        application.advance_match()

    state = application.roll_action_offer()
    assert state.shop_offer
    assert "buy_action" in state.available_actions
    with pytest.raises(ValueError, match="current offer"):
        application.buy_action(150)
    action = state.shop_offer[0]
    state = application.buy_action(action.id)
    assert state.days_remaining == Shop.DAYS_PER_SHOP - action.ap_cost
    state = application.move_to_next_day()
    assert state.days_remaining == Shop.DAYS_PER_SHOP - action.ap_cost - 1
    assert state.shop_offer
    state = application.finish_shop()
    assert state.step == "match"
    assert state.available_actions == ("advance_match",)

    match_calls = 0

    def win_match(team, opponent) -> MatchResult:
        nonlocal match_calls
        match_calls += 1
        if match_calls == 1:
            return _match_result(
                team.player_name, opponent.player_name, "Tie", tied=True
            )
        return _match_result(team.player_name, opponent.player_name, team.player_name)

    monkeypatch.setattr("src.engine.game_run.simulate_match", win_match)
    result = application.advance_match()
    assert result.winner == "Boundary Team"
    assert result.team_a_score == 7
    assert result.events[0].detail.startswith("Touchdown")
    assert match_calls == 2
    state = application.run_state()
    assert state.step == "shop"
    assert state.wins == 1
    assert state.losses == 0

    for _ in range(GameRun.REGULAR_SEASON_GAMES + GameRun.PLAYOFF_ROUNDS - 1):
        application.finish_shop()
        application.advance_match()

    final_state = application.run_state()
    assert final_state.step == "terminal"
    assert final_state.phase == "won"
    assert final_state.outcome == "champion"
    assert final_state.wins == GameRun.REGULAR_SEASON_GAMES + GameRun.PLAYOFF_ROUNDS
    assert final_state.losses == 0
    assert final_state.available_actions == ()
    assert database_path.exists()
    assert profile_path.exists()


def test_controller_reports_fired_after_three_regular_season_losses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = ApplicationController(
        tmp_path / "profile.json", tmp_path / "game.db"
    )
    application.create_profile("Losing Team", "crimson", "scarlet")
    monkeypatch.setattr(
        "src.application.random_coach_options",
        lambda: list(COACH_PAIRINGS[:3]),
    )
    monkeypatch.setattr(
        "src.engine.shop.random.sample",
        lambda population, count: list(population[:count]),
    )

    application.start_run()
    application.select_coach(1)
    for _ in Shop.OPENING_ORDER:
        application.roll_opening_offer()
        application.select_opening_player(1)

    def lose_match(team, opponent) -> MatchResult:
        return _match_result(team.player_name, opponent.player_name, opponent.player_name)

    monkeypatch.setattr("src.engine.game_run.simulate_match", lose_match)
    for _ in range(GameRun.LOSSES_TO_BE_FIRED):
        application.finish_shop()
        application.advance_match()

    final_state = application.run_state()
    assert final_state.step == "terminal"
    assert final_state.phase == "lost"
    assert final_state.outcome == "fired"
    assert final_state.wins == 0
    assert final_state.losses == GameRun.LOSSES_TO_BE_FIRED
