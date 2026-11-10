import random
from typing import Literal, TypedDict

from src.engine.units import Roster, Unit

DriveOutcome = Literal[
    "Touchdown",
    "Field goal",
    "Missed field goal",
    "Punt",
    "Penalty",
    "Turnover",
]


class DriveEvent(TypedDict):
    drive_number: int
    cycle_number: int
    team: str
    opponent: str
    outcome: DriveOutcome
    detail: str
    points: int
    team_a_score: int
    team_b_score: int


class MatchResult(TypedDict):
    team_a: str
    team_b: str
    team_a_score: int
    team_b_score: int
    winner: str
    final_momentum: float
    events: list[DriveEvent]


BASE_TURNOVER_CHANCE = 0.04
BASE_PENALTY_CHANCE = 0.03
MOMENTUM_EDGE_LIMIT = 8.0
MOMENTUM_LIMIT = 100.0


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
    """Calculate an offense's power edge for a single possession."""
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

    active_off = apply_volatility(
        base_off, _average_stat(offense.get_offensive_units(), "volatility")
    )
    active_def = apply_volatility(
        base_def, _average_stat(defense.get_defensive_units(), "volatility")
    )
    return active_off - active_def


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


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


def _momentum_edge(momentum: float) -> float:
    """Convert game momentum into a bounded matchup nudge, never points."""
    return _clamp(momentum * 0.08, -MOMENTUM_EDGE_LIMIT, MOMENTUM_EDGE_LIMIT)


def _resolve_possession(
    offense: Roster, edge: float
) -> tuple[DriveOutcome, str, int, float]:
    """Resolve a generic possession using the power matchup and bounded odds.

    Turnovers and penalty stalls have baseline odds of 4% and 3%. Touchdowns
    start at 32%, adjusted by offensive power and matchup edge, then clamped to
    8-68%. Otherwise, field-goal attempts start at 20%, adjust with the edge,
    and clamp to 8-35%; Special Teams field-goal reliability determines makes.
    """
    if random.random() < BASE_TURNOVER_CHANCE:
        return "Turnover", "Turnover; the possession ends without points.", 0, -6.0
    if random.random() < BASE_PENALTY_CHANCE:
        return "Penalty", "Penalty stalls the possession; no points.", 0, -2.0

    offense_power = offense.get_offensive_power()
    touchdown_chance = _clamp(
        0.32 + (offense_power - 40.0) * 0.005 + edge * 0.008,
        0.08,
        0.68,
    )
    if random.random() < touchdown_chance:
        return (
            "Touchdown",
            "Touchdown and successful conversion (7 points).",
            7,
            6.0,
        )

    field_goal_chance = _clamp(0.20 - edge * 0.004, 0.08, 0.35)
    if random.random() < field_goal_chance:
        reliability = _clamp(
            offense.special_teams.field_goal_reliability, 0.0, 1.0
        )
        if random.random() < reliability:
            return "Field goal", "Field goal is good (3 points).", 3, 3.0
        return "Missed field goal", "Field goal is missed; no points.", 0, -1.0

    return "Punt", "The drive stalls; punt with no points.", 0, -1.0


def simulate_match(
    team_a: Roster, team_b: Roster, num_drives: int | None = None
) -> MatchResult:
    """Simulate alternating possessions and derive the score from their events.

    Each cycle gives both teams one possession. Touchdown, field-goal, turnover,
    and penalty probabilities are deliberately generic; successful touchdowns
    are worth 7 and field goals 3. Momentum nudges the matchup edge by at most
    8 power points and never changes the score directly. The only player-derived
    inputs are supported power, volatility, and stamina stats.
    """
    drive_count = team_a.match_drive_count if num_drives is None else num_drives
    if drive_count < 1:
        raise ValueError("A match must simulate at least one drive.")

    team_a_score = 0
    team_b_score = 0
    momentum = 0.0
    events: list[DriveEvent] = []

    for cycle_index in range(drive_count):
        cycle_momentum_change = 0.0
        for offense, defense, is_team_a in (
            (team_a, team_b, True),
            (team_b, team_a, False),
        ):
            offense_momentum = momentum if is_team_a else -momentum
            drive_edge = simulate_drive(
                offense,
                defense,
                cycle_index,
                drive_count,
                offense.match_fatigue_limit,
                defense.match_fatigue_limit,
            )
            drive_edge += _momentum_edge(offense_momentum)
            outcome, detail, points, outcome_momentum = _resolve_possession(
                offense, drive_edge
            )

            if is_team_a:
                team_a_score += points
                cycle_momentum_change += drive_edge * 0.35 + outcome_momentum
            else:
                team_b_score += points
                cycle_momentum_change -= drive_edge * 0.35 + outcome_momentum

            events.append(
                {
                    "drive_number": len(events) + 1,
                    "cycle_number": cycle_index + 1,
                    "team": offense.player_name,
                    "opponent": defense.player_name,
                    "outcome": outcome,
                    "detail": detail,
                    "points": points,
                    "team_a_score": team_a_score,
                    "team_b_score": team_b_score,
                }
            )
        momentum = _clamp(
            momentum + cycle_momentum_change,
            -MOMENTUM_LIMIT,
            MOMENTUM_LIMIT,
        )

    if team_a_score > team_b_score:
        winner = team_a.player_name
    elif team_b_score > team_a_score:
        winner = team_b.player_name
    else:
        winner = "Tie"

    return {
        "team_a": team_a.player_name,
        "team_b": team_b.player_name,
        "team_a_score": team_a_score,
        "team_b_score": team_b_score,
        "winner": winner,
        "final_momentum": momentum,
        "events": events,
    }
