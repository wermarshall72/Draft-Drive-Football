from pathlib import Path

import pytest

from src.main import main


def test_cli_completes_setup_regular_season_and_playoffs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "cli-game.db"
    responses = ["CLI Team", "1", *("1" for _ in range(6))]
    for match_number in range(1, 14):
        responses.append("2")
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
