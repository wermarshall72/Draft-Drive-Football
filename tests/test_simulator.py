import random

import pytest

from src.engine.coaching_actions import ACTION_BY_ID
from src.engine.shop import Shop
from src.engine.simulator import simulate_drive, simulate_match
from src.engine.units import Roster
from src.main import build_dummy_team


def _set_team_power(roster: Roster, offense: float, defense: float) -> None:
    for unit in roster.get_offensive_units():
        unit.power = offense / len(roster.get_offensive_units())
        unit.volatility = 0.0
    for unit in roster.get_defensive_units():
        unit.power = defense / len(roster.get_defensive_units())
        unit.volatility = 0.0
    roster.special_teams.momentum_swing_chance = 0.0


def test_stronger_team_and_favorable_matchup_score_more_with_seeded_randomness(
) -> None:
    stronger = build_dummy_team("Stronger", coach_off=1.2, coach_def=1.2)
    weaker = build_dummy_team("Weaker", coach_off=0.8, coach_def=0.8)
    random.seed(41)

    scores = [simulate_match(stronger, weaker) for _ in range(60)]

    stronger_average = sum(result["team_a_score"] for result in scores) / len(scores)
    weaker_average = sum(result["team_b_score"] for result in scores) / len(scores)
    assert stronger_average > weaker_average


def test_identical_teams_produce_a_tie_under_controlled_randomness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team_a = build_dummy_team("A", coach_off=1.0, coach_def=1.0)
    team_b = build_dummy_team("B", coach_off=1.0, coach_def=1.0)
    monkeypatch.setattr(random, "random", lambda: 0.99)
    monkeypatch.setattr(random, "uniform", lambda low, high: (low + high) / 2)

    result = simulate_match(team_a, team_b)

    assert result["winner"] == "Tie"
    assert result["team_a_score"] == result["team_b_score"] == 0
    assert result["final_momentum"] == pytest.approx(0)


def test_equal_score_remains_a_tie_when_final_momentum_is_not_even(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team_a = build_dummy_team("A", coach_off=1.0, coach_def=1.0)
    team_b = build_dummy_team("B", coach_off=1.0, coach_def=1.0)
    monkeypatch.setattr(random, "random", lambda: 0.99)
    monkeypatch.setattr(
        "src.engine.simulator.simulate_drive",
        lambda offense, *_: 1.0 if offense is team_a else -1.0,
    )

    result = simulate_match(team_a, team_b, num_drives=1)

    assert result["team_a_score"] == result["team_b_score"] == 0
    assert result["winner"] == "Tie"
    assert result["final_momentum"] != 0


def test_default_match_logs_two_possessions_per_cycle_and_reconciles_score() -> None:
    team_a = build_dummy_team("A", coach_off=1.0, coach_def=1.0)
    team_b = build_dummy_team("B", coach_off=1.0, coach_def=1.0)
    random.seed(17)

    result = simulate_match(team_a, team_b)

    assert len(result["events"]) == 20
    assert [event["team"] for event in result["events"][:4]] == [
        "A",
        "B",
        "A",
        "B",
    ]
    assert sum(
        event["points"] for event in result["events"] if event["team"] == "A"
    ) == result["team_a_score"]
    assert sum(
        event["points"] for event in result["events"] if event["team"] == "B"
    ) == result["team_b_score"]

    running_a = 0
    running_b = 0
    for event in result["events"]:
        assert event["points"] in (0, 3, 7)
        if event["team"] == "A":
            running_a += event["points"]
        else:
            running_b += event["points"]
        assert event["team_a_score"] == running_a
        assert event["team_b_score"] == running_b
        if event["outcome"] == "Touchdown":
            assert event["points"] == 7
        elif event["outcome"] == "Field goal":
            assert event["points"] == 3
        else:
            assert event["points"] == 0
    assert (running_a, running_b) == (
        result["team_a_score"],
        result["team_b_score"],
    )
    expected_winner = (
        "Tie"
        if running_a == running_b
        else "A"
        if running_a > running_b
        else "B"
    )
    assert result["winner"] == expected_winner


def test_close_high_offense_matchup_can_produce_a_high_scoring_game() -> None:
    team_a = build_dummy_team("A", coach_off=1.0, coach_def=1.0)
    team_b = build_dummy_team("B", coach_off=1.0, coach_def=1.0)
    _set_team_power(team_a, offense=70.0, defense=70.0)
    _set_team_power(team_b, offense=70.0, defense=70.0)
    random.seed(12)

    result = simulate_match(team_a, team_b)

    assert result["team_a_score"] + result["team_b_score"] >= 50
    assert abs(result["team_a_score"] - result["team_b_score"]) <= 10


def test_strong_defenses_hold_low_offenses_to_plausible_lower_scores() -> None:
    team_a = build_dummy_team("A", coach_off=1.0, coach_def=1.0)
    team_b = build_dummy_team("B", coach_off=1.0, coach_def=1.0)
    _set_team_power(team_a, offense=40.0, defense=70.0)
    _set_team_power(team_b, offense=40.0, defense=70.0)
    random.seed(11)

    result = simulate_match(team_a, team_b)

    assert result["team_a_score"] + result["team_b_score"] < 40
    assert all(
        event["points"] in (0, 3, 7) for event in result["events"]
    )


@pytest.mark.parametrize(
    ("draws", "expected_outcome"),
    [
        ([0.0, 0.99, 0.99, 0.99, 0.99], "Turnover"),
        ([0.99, 0.0, 0.99, 0.99, 0.99], "Penalty"),
    ],
)
def test_rare_penalties_and_turnovers_are_logged(
    draws: list[float],
    expected_outcome: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offense = build_dummy_team("Offense", coach_off=1.0, coach_def=1.0)
    defense = build_dummy_team("Defense", coach_off=1.0, coach_def=1.0)
    monkeypatch.setattr("src.engine.simulator.simulate_drive", lambda *_: 0.0)
    random_draws = iter(draws + [0.99] * 8)
    monkeypatch.setattr(random, "random", lambda: next(random_draws))

    result = simulate_match(offense, defense, num_drives=1)

    assert result["events"][0]["outcome"] == expected_outcome
    assert result["events"][0]["points"] == 0
    assert expected_outcome.lower() in result["events"][0]["detail"].lower()


def test_low_stamina_loses_more_power_late_in_the_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    low_stamina = build_dummy_team("Low stamina", coach_off=1.0, coach_def=1.0)
    high_stamina = build_dummy_team("High stamina", coach_off=1.0, coach_def=1.0)
    for unit in (
        low_stamina.qb,
        low_stamina.rb,
        low_stamina.wr,
        low_stamina.oline,
        low_stamina.front7,
        low_stamina.secondary,
    ):
        unit.stamina = 0.0
    for unit in (
        high_stamina.qb,
        high_stamina.rb,
        high_stamina.wr,
        high_stamina.oline,
        high_stamina.front7,
        high_stamina.secondary,
    ):
        unit.stamina = 1.0
    monkeypatch.setattr(random, "random", lambda: 0.99)
    monkeypatch.setattr(random, "uniform", lambda low, high: (low + high) / 2)

    opening_shift = simulate_drive(low_stamina, high_stamina, drive_index=0)
    late_shift = simulate_drive(low_stamina, high_stamina, drive_index=9)

    assert opening_shift == 0
    assert late_shift < opening_shift


def test_match_actions_set_drive_count_and_fatigue_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team = build_dummy_team("Home", coach_off=1.0, coach_def=1.0)
    opponent = build_dummy_team("Opponent", coach_off=1.0, coach_def=1.0)
    shop = Shop(team)
    shop.action_offer = [ACTION_BY_ID[102], ACTION_BY_ID[103]]
    shop.take_action(ACTION_BY_ID[102])
    shop.take_action(ACTION_BY_ID[103])
    effective = shop.effective_roster()
    observed_drive_counts: list[int] = []

    def observe_drive(
        drive_offense,
        drive_defense,
        drive_index,
        num_drives,
        offense_fatigue_limit,
        defense_fatigue_limit,
    ) -> float:
        assert drive_offense is effective or drive_offense is opponent
        assert drive_defense is opponent or drive_defense is effective
        assert drive_index >= 0
        assert offense_fatigue_limit in (0.06, 0.10)
        assert defense_fatigue_limit in (0.06, 0.10)
        observed_drive_counts.append(num_drives)
        return 1.0

    monkeypatch.setattr("src.engine.simulator.simulate_drive", observe_drive)
    monkeypatch.setattr(random, "random", lambda: 0.99)
    simulate_match(effective, opponent)

    assert observed_drive_counts == [12] * 24
    assert effective.match_fatigue_limit == pytest.approx(0.06)


def test_special_teams_action_changes_return_swing_magnitude(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offense = build_dummy_team("Offense", coach_off=1.0, coach_def=1.0)
    defense = build_dummy_team("Defense", coach_off=1.0, coach_def=1.0)
    shop = Shop(offense)
    shop.action_offer = [ACTION_BY_ID[105]]
    shop.take_action(ACTION_BY_ID[105])
    effective_offense = shop.effective_roster()
    monkeypatch.setattr(random, "random", lambda: 0.0)

    assert simulate_drive(effective_offense, defense) == 18.0


def test_field_goal_reliability_changes_logged_scoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offense = build_dummy_team("Offense", coach_off=1.0, coach_def=1.0)
    defense = build_dummy_team("Defense", coach_off=1.0, coach_def=1.0)
    shop = Shop(offense)
    shop.action_offer = [ACTION_BY_ID[69]]
    shop.take_action(ACTION_BY_ID[69])
    effective_offense = shop.effective_roster()
    draws = iter([0.99, 0.99, 0.99, 0.0, 0.82] + [0.99] * 4)
    monkeypatch.setattr("src.engine.simulator.simulate_drive", lambda *_: 0.0)
    monkeypatch.setattr(random, "random", lambda: next(draws))

    result = simulate_match(effective_offense, defense, num_drives=1)

    assert result["events"][0]["outcome"] == "Field goal"
    assert result["events"][0]["points"] == 3
    assert result["team_a_score"] == 3
