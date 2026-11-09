from pathlib import Path

import pytest

from src.engine.game_run import GameRun
from src.engine.shop import Shop
from src.main import create_starter_team


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
        lambda *_: {"winner": "Home Team", "final_momentum": 1.0},
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
        lambda *_: {"winner": "Opponent", "final_momentum": -1.0},
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
        lambda *_: {"winner": "Home Team", "final_momentum": 1.0},
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
        lambda *_: {"winner": "Home Team", "final_momentum": 1.0},
    )
    game.start_regular_season()
    for _ in range(10):
        game.combat_phase()

    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lambda *_: {"winner": "Opponent", "final_momentum": -1.0},
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
            {"winner": "Tie", "final_momentum": 0.0},
            {"winner": "Home Team", "final_momentum": 1.0},
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

    def lose_to_opponent(team, opponent):
        assert team.player_name != opponent.player_name
        return {"winner": opponent.player_name, "final_momentum": -1.0}

    monkeypatch.setattr(
        "src.engine.game_run.simulate_match",
        lose_to_opponent,
    )
    game.start_regular_season()

    game.combat_phase()

    assert game.losses == 1
    assert game.wins == 0
