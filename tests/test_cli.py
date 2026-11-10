from pathlib import Path

import pytest

from src.application import ApplicationController
from src.engine.shop import Shop
from src.main import _run_shop, main


def test_cli_completes_setup_regular_season_and_playoffs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database = tmp_path / "cli-game.db"
    profile_file = tmp_path / "profile" / "team.json"
    responses = ["CLI Team", "1", "2", "1", "1", *("1" for _ in range(6))]
    for match_number in range(1, 14):
        responses.append("0")
        if match_number < 13:
            responses.append("")
    responses.append("3")
    answers = iter(responses)

    def read_answer(prompt: str = "") -> str:
        print(prompt, end="")
        return next(answers)

    def win_match(team, opponent):
        assert team is not opponent
        return {
            "team_a": team.player_name,
            "team_b": opponent.player_name,
            "team_a_score": 7,
            "team_b_score": 0,
            "winner": team.player_name,
            "final_momentum": 1.0,
            "events": [
                {
                    "drive_number": 1,
                    "cycle_number": 1,
                    "team": team.player_name,
                    "opponent": opponent.player_name,
                    "outcome": "Touchdown",
                    "detail": "Touchdown and successful conversion (7 points).",
                    "points": 7,
                    "team_a_score": 7,
                    "team_b_score": 0,
                },
                {
                    "drive_number": 2,
                    "cycle_number": 1,
                    "team": opponent.player_name,
                    "opponent": team.player_name,
                    "outcome": "Punt",
                    "detail": "The drive stalls; punt with no points.",
                    "points": 0,
                    "team_a_score": 7,
                    "team_b_score": 0,
                },
            ],
        }

    monkeypatch.setattr("builtins.input", read_answer)
    monkeypatch.setattr("src.engine.game_run.simulate_match", win_match)

    main(db_path=database, profile_path=profile_file)

    output = capsys.readouterr().out
    assert "Create your team profile" in output
    assert "1. Start Run" in output
    assert "2. Settings" in output
    assert "3. Quit" in output
    assert output.count("Enter your team name:") == 1
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
    assert "CLI Team vs FCS Cupcake" in output
    assert "Drive 01 | CLI Team: Touchdown and successful conversion (7 points)." in output
    assert "Drive 02 | FCS Cupcake: The drive stalls; punt with no points." in output
    assert "Score: CLI Team 7 - FCS Cupcake 0" in output
    assert "Final score: CLI Team 7 - FCS Cupcake 0" in output
    assert "Winner: CLI Team" in output
    assert "Final momentum: +1.0 (CLI Team favored)" in output
    assert database.exists()
    assert profile_file.exists()


def test_cli_buys_multiple_actions_and_repeats_move_to_next_day(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    application = ApplicationController(
        profile_path=tmp_path / "profile.json",
        db_path=tmp_path / "game.db",
    )
    application.create_profile("CLI Team", "crimson", "scarlet")
    application.start_run()
    application.select_coach(1)
    for _ in Shop.OPENING_ORDER:
        application.roll_opening_offer()
        application.select_opening_player(1)
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

    _run_shop(application, "Week 1")

    state = application.run_state()
    assert state.step == "match"
    assert state.days_remaining == 0
    output = capsys.readouterr().out
    assert "Move to next day (1 AP)" in output
    assert "Selected Scripted Opening; 6 AP remain." in output
    assert "Quick-Count Offense" not in output
