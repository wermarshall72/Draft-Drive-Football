import random
from typing import Literal, TypedDict

from src.engine.units import Roster, Unit


class MatchResult(TypedDict):
    winner: str
    final_momentum: float


def apply_volatility(base_power: float, volatility: float = 0.2) -> float:
    """Applies RNG variance to base power (e.g., 0.2 means +/- 20% swing)."""
    modifier = random.uniform(1.0 - volatility, 1.0 + volatility)
    return base_power * modifier

def simulate_drive(
    offense: Roster,
    defense: Roster,
    drive_index: int = 0,
    num_drives: int = 10,
    offense_fatigue_limit: float = 0.10,
    defense_fatigue_limit: float = 0.10,
) -> float:
    """
    Simulates a single drive. 
    Returns a float representing the momentum shift:
    Positive number = Offense wins the drive.
    Negative number = Defense wins the drive.
    """
    # 1. Special Teams Wildcard (Random momentum flips)
    if random.random() < offense.special_teams.momentum_swing_chance:
        return max(
            0.0,
            offense.special_teams.momentum_swing_magnitude
            - defense.special_teams.opponent_swing_reduction,
        )
    if random.random() < defense.special_teams.momentum_swing_chance:
        return -max(
            0.0,
            defense.special_teams.momentum_swing_magnitude
            - offense.special_teams.opponent_swing_reduction,
        )

    # 2. Fatigue accumulates across the match, based on the players on each side.
    base_off = _apply_fatigue(
        offense.get_offensive_power(),
        offense.get_offensive_units(),
        drive_index,
        num_drives,
        offense_fatigue_limit,
    )
    base_def = _apply_fatigue(
        defense.get_defensive_power(),
        defense.get_defensive_units(),
        drive_index,
        num_drives,
        defense_fatigue_limit,
    )

    # 3. Apply each side's average player volatility to simulate drive chaos.
    active_off = apply_volatility(
        base_off, _average_stat(offense.get_offensive_units(), "volatility")
    )
    active_def = apply_volatility(
        base_def, _average_stat(defense.get_defensive_units(), "volatility")
    )

    # 4. Tug-of-War Math
    momentum_shift = active_off - active_def
    # Only action bonuses above the legacy baseline change stalled-drive outcomes.
    reliability_bonus = max(
        0.0, offense.special_teams.field_goal_reliability - 0.80
    )
    if (
        momentum_shift < 0
        and reliability_bonus > 0
        and random.random() < min(1.0, reliability_bonus / 0.20)
    ):
        return max(3.0, momentum_shift)
    return momentum_shift


def _average_stat(
    roster_units: tuple[Unit, ...], stat: Literal["volatility", "stamina"]
) -> float:
    return sum(getattr(unit, stat) for unit in roster_units) / len(roster_units)


def _apply_fatigue(
    base_power: float,
    roster_units: tuple[Unit, ...],
    drive_index: int,
    num_drives: int,
    fatigue_limit: float = 0.10,
) -> float:
    stamina = min(1.0, max(0.0, _average_stat(roster_units, "stamina")))
    progress = drive_index / max(num_drives - 1, 1)
    return base_power * (1.0 - (1.0 - stamina) * fatigue_limit * progress)


def simulate_match(
    team_a: Roster, team_b: Roster, num_drives: int | None = None
) -> MatchResult:
    """
    Runs a full game by clashing Offenses vs Defenses over multiple drives.
    """
    drive_count = (
        team_a.match_drive_count if num_drives is None else num_drives
    )
    if drive_count < 1:
        raise ValueError("A match must simulate at least one drive.")
    momentum = 0.0  # Positive favors team_a, Negative favors team_b
    for drive_index in range(drive_count):
        # A single cycle: Team A attacks, then Team B attacks
        shift_a = simulate_drive(
            team_a,
            team_b,
            drive_index,
            drive_count,
            team_a.match_fatigue_limit,
            team_b.match_fatigue_limit,
        )
        shift_b = simulate_drive(
            team_b,
            team_a,
            drive_index,
            drive_count,
            team_b.match_fatigue_limit,
            team_a.match_fatigue_limit,
        )
        
        # Net momentum change for the cycle
        momentum += (shift_a - shift_b)
        
    if momentum > 0:
        winner = team_a.player_name
    elif momentum < 0:
        winner = team_b.player_name
    else:
        winner = "Tie"
    return {
        "winner": winner,
        "final_momentum": momentum
    }
