from pathlib import Path

import pytest

from src.engine.game_run import GameRun
from src.engine.shop import Shop
from src.main import _run_shop, create_starter_team, main


def test_cli_completes_setup_regular_season_and_playoffs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "cli-game.db"
    responses = ["CLI Team", "1", *("1" for _ in range(6))]
    for match_number in range(1, 14):
        responses.append("0")
        if match_number < 13:
            responses.append("")
    answers = iter(responses)

    def read_answer(prompt: str = "") -> str:
        print(prompt, end="")
        return next(answers)

    def win_match(team, opponent):
        assert team is not opponent
        return {
            "winner": team.player_name,
            "final_momentum": 1.0,
        }

    monkeypatch.setattr("builtins.input", read_answer)
    monkeypatch.setattr("src.engine.game_run.simulate_match", win_match)

    main(db_path=database)

    output = capsys.readouterr().out
    assert "Choose your coach" in output
    assert "Offense:" in output
    assert "Defense:" in output
    assert "Effects:" in output
    assert "National Signing Day" in output
    assert output.index("Choose your QB") < output.index("Choose your RB")
    assert output.index("Choose your RB") < output.index("Choose your WR")
    assert "Roster QB:" in output
    assert "Opening AP remaining: 0" in output
    assert output.index("Opening lineup:") < output.index("Week 1 of 10")
    assert "Week 1 of 10" in output
    assert "Week 10 of 10" in output
    assert "Playoff Round 3 of 3" in output
    assert "Championship! You won the run." in output
    assert database.exists()


def test_cli_buys_multiple_actions_and_repeats_move_to_next_day(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    roster = create_starter_team("CLI Team")
    shop = Shop(roster)
    game = GameRun(roster, shop)
    answers = iter(("1", "M", "1", "0"))

    def read_answer(prompt: str = "") -> str:
        print(prompt, end="")
        return next(answers)

    monkeypatch.setattr("builtins.input", read_answer)
    monkeypatch.setattr(
        "src.engine.shop.random.choices",
        lambda values, **_: [values[0]],
    )
    monkeypatch.setattr("src.engine.shop.random.choice", lambda values: values[0])

    _run_shop(game, "Week 1")

    assert shop.move_count == 1
    assert [action.id for action, _ in shop.match_actions] == [1, 2]
    output = capsys.readouterr().out
    assert "Move to next day (1 AP)" in output
    assert "Quick-Count Offense" not in output
