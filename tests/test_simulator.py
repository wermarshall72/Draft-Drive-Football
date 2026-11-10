import random

import pytest

from src.engine.simulator import simulate_drive, simulate_match
from src.engine.coaching_actions import ACTION_BY_ID
from src.engine.shop import Shop
from src.main import build_dummy_team


def test_simulation_outcome_is_determined_by_power_when_randomness_is_controlled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stronger = build_dummy_team("Stronger", coach_off=1.2, coach_def=1.2)
    weaker = build_dummy_team("Weaker", coach_off=0.8, coach_def=0.8)
    monkeypatch.setattr(random, "random", lambda: 0.99)
    monkeypatch.setattr(random, "uniform", lambda low, high: (low + high) / 2)

    result = simulate_match(stronger, weaker)

    assert result["winner"] == "Stronger"
    assert result["final_momentum"] > 0


def test_identical_teams_produce_a_tie_under_controlled_randomness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    team_a = build_dummy_team("A", coach_off=1.0, coach_def=1.0)
    team_b = build_dummy_team("B", coach_off=1.0, coach_def=1.0)
    monkeypatch.setattr(random, "random", lambda: 0.99)
    monkeypatch.setattr(random, "uniform", lambda low, high: (low + high) / 2)

    result = simulate_match(team_a, team_b)

    assert result["winner"] == "Tie"
    assert result["final_momentum"] == 0


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


def test_field_goal_reliability_bonus_can_rescue_a_stalled_drive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offense = build_dummy_team("Offense", coach_off=1.0, coach_def=1.0)
    defense = build_dummy_team("Defense", coach_off=1.0, coach_def=1.0)
    defense.front7.power = 100.0
    defense.secondary.power = 100.0
    shop = Shop(offense)
    shop.action_offer = [ACTION_BY_ID[69]]
    shop.take_action(ACTION_BY_ID[69])
    effective_offense = shop.effective_roster()
    draws = iter((0.99, 0.99, 0.0))
    monkeypatch.setattr(random, "random", lambda: next(draws))
    monkeypatch.setattr(random, "uniform", lambda low, high: (low + high) / 2)

    assert simulate_drive(effective_offense, defense) == 3.0
