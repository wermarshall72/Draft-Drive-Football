"""Validated domain models for interactive football matches.

This module is intentionally separate from the legacy auto-battler models.
Future match resolution must create a ``random.Random`` instance from the
match's ``random_seed`` and use that instance for all match randomness.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Real
from types import MappingProxyType
from typing import Mapping


class FootballPosition(str, Enum):
    QB = "QB"
    RB = "RB"
    WR = "WR"
    O_LINE = "O_LINE"
    D_LINE = "D_LINE"
    LINEBACKERS = "LINEBACKERS"
    CORNERBACKS = "CORNERBACKS"
    SAFETIES = "SAFETIES"


class FootballTeamSide(str, Enum):
    TEAM_A = "team_a"
    TEAM_B = "team_b"


class FootballMatchStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class FootballAwaitedAction(str, Enum):
    OFFENSIVE_PLAY = "offensive_play"
    DEFENSIVE_SCHEME = "defensive_scheme"


class OffensivePlayAction(str, Enum):
    RUN = "run"
    SHORT_PASS = "short_pass"
    DEEP_PASS = "deep_pass"
    PLAY_ACTION = "play_action"
    QB_KEEPER = "qb_keeper"


class DefensiveSchemeAction(str, Enum):
    BASE = "base"
    BLITZ = "blitz"
    MAN_COVERAGE = "man_coverage"
    ZONE_COVERAGE = "zone_coverage"
    PREVENT = "prevent"


def _validate_name(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


def _validate_finite_number(value: Real, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field_name} must be a finite number.")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{field_name} must be a finite number.")


def _validate_nonnegative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer.")


@dataclass(frozen=True)
class FootballPlayer:
    name: str
    position: FootballPosition
    power: float
    volatility: float
    stamina: float

    def __post_init__(self) -> None:
        _validate_name(self.name, "Player name")
        if not isinstance(self.position, FootballPosition):
            raise ValueError("Player position must be a FootballPosition.")
        _validate_finite_number(self.power, "Power")
        if self.power < 0:
            raise ValueError("Power must be non-negative.")
        _validate_finite_number(self.volatility, "Volatility")
        if not 0 <= self.volatility <= 1:
            raise ValueError("Volatility must be between 0 and 1.")
        _validate_finite_number(self.stamina, "Stamina")
        if not 0 <= self.stamina <= 1:
            raise ValueError("Stamina must be between 0 and 1.")


@dataclass(frozen=True)
class FootballCoach:
    name: str

    def __post_init__(self) -> None:
        _validate_name(self.name, "Coach name")


@dataclass(frozen=True)
class FootballSpecialTeams:
    name: str = "Special Teams"

    def __post_init__(self) -> None:
        _validate_name(self.name, "Special-teams name")


@dataclass(frozen=True)
class FootballRoster:
    team_name: str
    players: Mapping[FootballPosition, FootballPlayer]
    coach: FootballCoach
    special_teams: FootballSpecialTeams

    def __post_init__(self) -> None:
        _validate_name(self.team_name, "Team name")
        if not isinstance(self.players, Mapping):
            raise ValueError("Players must map each FootballPosition to a player.")
        if any(not isinstance(position, FootballPosition) for position in self.players):
            raise ValueError("Player slots must use FootballPosition identifiers.")

        expected_positions = set(FootballPosition)
        actual_positions = set(self.players)
        if actual_positions != expected_positions:
            missing = expected_positions - actual_positions
            extra = actual_positions - expected_positions
            raise ValueError(
                f"Roster must contain exactly one player for each position "
                f"(missing={sorted(position.value for position in missing)}, "
                f"extra={sorted(str(position) for position in extra)})."
            )
        for position, player in self.players.items():
            if not isinstance(player, FootballPlayer):
                raise ValueError(f"The {position.value} slot must contain a FootballPlayer.")
            if player.position is not position:
                raise ValueError(
                    f"The {position.value} slot cannot contain a "
                    f"{player.position.value} player."
                )
        if not isinstance(self.coach, FootballCoach):
            raise ValueError("Coach must be a FootballCoach.")
        if not isinstance(self.special_teams, FootballSpecialTeams):
            raise ValueError("Special teams must be a FootballSpecialTeams object.")
        object.__setattr__(self, "players", MappingProxyType(dict(self.players)))


@dataclass(frozen=True)
class FootballPlayResult:
    offensive_play: OffensivePlayAction
    yards_gained: float
    clock_seconds_used: int
    points_scored: int = 0
    turnover: bool = False
    possession_changed: bool = False
    defensive_scheme: DefensiveSchemeAction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.offensive_play, OffensivePlayAction):
            raise ValueError("Offensive play must be an OffensivePlayAction.")
        _validate_finite_number(self.yards_gained, "Yards gained")
        _validate_nonnegative_int(self.clock_seconds_used, "Clock seconds used")
        _validate_nonnegative_int(self.points_scored, "Points scored")
        if not isinstance(self.turnover, bool):
            raise ValueError("Turnover must be a boolean.")
        if not isinstance(self.possession_changed, bool):
            raise ValueError("Possession changed must be a boolean.")
        if (
            self.defensive_scheme is not None
            and not isinstance(self.defensive_scheme, DefensiveSchemeAction)
        ):
            raise ValueError("Defensive scheme must be a DefensiveSchemeAction or None.")


@dataclass(frozen=True)
class FootballMatchResult:
    team_a_score: int
    team_b_score: int
    winner: FootballTeamSide | None
    completed: bool

    def __post_init__(self) -> None:
        _validate_nonnegative_int(self.team_a_score, "Team A score")
        _validate_nonnegative_int(self.team_b_score, "Team B score")
        if self.winner is not None and not isinstance(self.winner, FootballTeamSide):
            raise ValueError("Winner must be a FootballTeamSide or None.")
        if not isinstance(self.completed, bool):
            raise ValueError("Completed must be a boolean.")


@dataclass(frozen=True)
class FootballMatchState:
    """Match snapshot; field position is yards from the offense's own goal line.

    Position 0 is the offense's own goal line and 100 is the opponent's goal
    line. Resolution must use a per-match ``random.Random`` initialized from
    ``random_seed`` rather than module-global randomness.
    """

    team_a: FootballRoster
    team_b: FootballRoster
    random_seed: int
    team_a_score: int
    team_b_score: int
    possession: FootballTeamSide
    down: int
    yards_to_go: float
    offense_field_position: float
    game_clock_seconds: int
    period: int
    status: FootballMatchStatus = FootballMatchStatus.IN_PROGRESS
    awaited_action: FootballAwaitedAction | None = None
    current_drive_defensive_scheme: DefensiveSchemeAction | None = None
    final_result: FootballMatchResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.team_a, FootballRoster) or not isinstance(
            self.team_b, FootballRoster
        ):
            raise ValueError("Both teams must be FootballRoster objects.")
        if (
            isinstance(self.random_seed, bool)
            or not isinstance(self.random_seed, int)
        ):
            raise ValueError("Random seed must be an integer.")
        _validate_nonnegative_int(self.team_a_score, "Team A score")
        _validate_nonnegative_int(self.team_b_score, "Team B score")
        if not isinstance(self.possession, FootballTeamSide):
            raise ValueError("Possession must be a FootballTeamSide.")
        if (
            isinstance(self.down, bool)
            or not isinstance(self.down, int)
            or not 1 <= self.down <= 4
        ):
            raise ValueError("Down must be an integer from 1 through 4.")
        _validate_finite_number(self.yards_to_go, "Yards to go")
        if self.yards_to_go <= 0:
            raise ValueError("Yards to go must be positive.")
        _validate_finite_number(self.offense_field_position, "Offense field position")
        if not 0 <= self.offense_field_position <= 100:
            raise ValueError("Offense field position must be between 0 and 100.")
        _validate_nonnegative_int(self.game_clock_seconds, "Game clock seconds")
        if (
            isinstance(self.period, bool)
            or not isinstance(self.period, int)
            or self.period < 1
        ):
            raise ValueError("Period must be a positive integer.")
        if not isinstance(self.status, FootballMatchStatus):
            raise ValueError("Status must be a FootballMatchStatus.")
        if self.awaited_action is not None and not isinstance(
            self.awaited_action, FootballAwaitedAction
        ):
            raise ValueError("Awaited action must be a FootballAwaitedAction or None.")
        if self.current_drive_defensive_scheme is not None and not isinstance(
            self.current_drive_defensive_scheme, DefensiveSchemeAction
        ):
            raise ValueError(
                "Current defensive scheme must be a DefensiveSchemeAction or None."
            )
        if self.final_result is not None and not isinstance(
            self.final_result, FootballMatchResult
        ):
            raise ValueError("Final result must be a FootballMatchResult or None.")
        if self.status is FootballMatchStatus.COMPLETED:
            if self.final_result is None or not self.final_result.completed:
                raise ValueError("A completed match must have a completed final result.")
            if (
                self.final_result.team_a_score != self.team_a_score
                or self.final_result.team_b_score != self.team_b_score
            ):
                raise ValueError("Final result scores must match the match state.")
        elif self.final_result is not None:
            raise ValueError("An in-progress match cannot have a final result.")
