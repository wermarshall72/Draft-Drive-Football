from pathlib import Path
import json
import sqlite3

import pytest

from src.engine.coaching_actions import ACTION_BY_ID
from src.engine.game_run import GameRun
from src.engine.shop import Shop
from src.engine.simulator import MatchResult
from src.main import create_starter_team


def _match_result(
    winner: str,
    momentum: float,
    team_a: str = "Home Team",
    team_b: str = "Opponent",
) -> MatchResult:
    team_a_score = 7 if winner == team_a else 0
    team_b_score = 7 if winner == team_b else 0
    return {
        "team_a": team_a,
        "team_b": team_b,
        "team_a_score": team_a_score,
        "team_b_score": team_b_score,
        "winner": winner,
        "final_momentum": momentum,
        "events": [],
    }


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "game-test.db"


def test_run_enters_playoffs_after_ten_regular_season_games(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("Home Team")
    game = GameRun(roster, Shop(roster), db_path=db_path)
    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lambda *_: _match_result("Home Team", 1.0),
    )
    game.start_regular_season()

    for _ in range(10):
        game.combat_phase()

    assert game.wins == 10
    assert game.losses == 0
    assert game.round_number == 10
    assert game.phase == "playoffs"
    assert game.playoff_round == 1
    assert not game.is_game_over()


def test_three_regular_season_losses_end_the_run(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("Home Team")
    game = GameRun(roster, Shop(roster), db_path=db_path)
    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lambda *_: _match_result("Opponent", -1.0),
    )
    game.start_regular_season()

    for _ in range(3):
        game.combat_phase()

    assert game.losses == 3
    assert game.phase == "lost"
    assert game.is_game_over()


def test_three_playoff_wins_complete_the_run(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("Home Team")
    game = GameRun(roster, Shop(roster), db_path=db_path)
    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lambda *_: _match_result("Home Team", 1.0),
    )
    game.start_regular_season()

    for _ in range(10):
        game.combat_phase()
    for expected_round in (1, 2, 3):
        assert game.playoff_round == expected_round
        game.combat_phase()

    assert game.phase == "won"
    assert game.wins == 13
    assert game.is_game_over()


def test_playoff_loss_is_elimination(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("Home Team")
    game = GameRun(roster, Shop(roster), db_path=db_path)
    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lambda *_: _match_result("Home Team", 1.0),
    )
    game.start_regular_season()
    for _ in range(10):
        game.combat_phase()

    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lambda *_: _match_result("Opponent", -1.0),
    )
    game.combat_phase()

    assert game.phase == "lost"
    assert game.losses == 1
    assert game.is_game_over()


def test_tied_match_replays_until_decisive(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("Home Team")
    game = GameRun(roster, Shop(roster), db_path=db_path)
    outcomes = iter(
        (
            _match_result("Tie", 0.0),
            _match_result("Home Team", 1.0),
        )
    )
    monkeypatch.setattr(
        "src.engine.game_run.simulate_match", lambda *_: next(outcomes)
    )
    game.start_regular_season()

    result = game.combat_phase()

    assert result["winner"] == "Home Team"
    assert game.wins == 1
    assert game.losses == 0


def test_dummy_opponent_name_never_matches_player_name(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("FCS Cupcake")
    game = GameRun(roster, Shop(roster), db_path=db_path)

    def lose_to_opponent(team, opponent) -> MatchResult:
        assert team.player_name != opponent.player_name
        return _match_result(
            opponent.player_name, -1.0, team.player_name, opponent.player_name
        )

    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lose_to_opponent,
    )
    game.start_regular_season()

    game.combat_phase()

    assert game.losses == 1
    assert game.wins == 0


def test_temporary_action_survives_tie_replay_then_expires(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    game = GameRun(roster, shop, db_path=db_path)
    game.start_regular_season()
    shop.action_offer = [ACTION_BY_ID[25]]
    shop.take_action(ACTION_BY_ID[25])
    outcomes = iter(
        (
            _match_result("Tie", 0.0),
            _match_result("Home Team", 1.0),
        )
    )
    seen_power: list[float] = []

    def observe_match(team, opponent):
        assert team.player_name != opponent.player_name
        seen_power.append(team.qb.power)
        return next(outcomes)

    monkeypatch.setattr("src.engine.game_run.simulate_match", observe_match)

    game.combat_phase()

    assert seen_power == pytest.approx([10.8, 10.8])
    assert not shop.match_actions
    assert shop.effective_roster().qb.power == 10.0


def test_permanent_action_is_in_snapshot_but_temporary_action_is_not(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    game = GameRun(roster, shop, db_path=db_path)
    game.start_regular_season()
    shop.action_offer = [ACTION_BY_ID[9], ACTION_BY_ID[25]]
    shop.take_action(ACTION_BY_ID[9])
    shop.take_action(ACTION_BY_ID[25])
    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lambda *_: _match_result("Home Team", 1.0),
    )

    game.combat_phase()

    with sqlite3.connect(db_path) as connection:
        qb_json = connection.execute(
            "SELECT qb_data FROM snapshots WHERE player_name = ?",
            ("Home Team",),
        ).fetchone()[0]
    saved_qb = json.loads(qb_json)
    assert saved_qb["power"] == pytest.approx(10.3)
    assert shop.effective_roster().qb.power == pytest.approx(10.3)


def test_permanent_ap_bonus_and_banked_ap_restore_at_prep_phase(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roster = create_starter_team("Home Team")
    shop = Shop(roster)
    shop.permanent_ap = 1
    shop.pending_ap = 2
    game = GameRun(roster, shop, db_path=db_path)
    game.start_regular_season()
    assert shop.days == Shop.DAYS_PER_SHOP + 3

    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lambda *_: _match_result("Home Team", 1.0),
    )
    game.combat_phase()
    game.prep_phase()

    assert shop.days == Shop.DAYS_PER_SHOP + 1
