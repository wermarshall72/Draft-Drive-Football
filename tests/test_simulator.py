import random

import pytest

from src.engine.simulator import simulate_drive, simulate_match
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
