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
    FOURTH_DOWN_DECISION = "fourth_down_decision"


class OffensivePlayAction(str, Enum):
    RB_RUN = "rb_run"
    SCREEN_PASS = "screen_pass"
    PA_PASS = "pa_pass"
    SHORT_PASS = "short_pass"
    MEDIUM_PASS = "medium_pass"
    DEEP_PASS = "deep_pass"


class DefensiveSchemeAction(str, Enum):
    RB_RUN = "rb_run"
    SCREEN_PASS = "screen_pass"
    PA_PASS = "pa_pass"
    SHORT_PASS = "short_pass"
    MEDIUM_PASS = "medium_pass"
    DEEP_PASS = "deep_pass"


class FootballFourthDownAction(str, Enum):
    GO_FOR_IT = "go_for_it"
    PUNT = "punt"
    FIELD_GOAL = "field_goal"


FOOTBALL_PLAY_MATCHUPS = MappingProxyType({
    OffensivePlayAction.RB_RUN: (
        (FootballPosition.O_LINE, FootballPosition.RB),
        (FootballPosition.D_LINE, FootballPosition.LINEBACKERS),
    ),
    OffensivePlayAction.SCREEN_PASS: (
        (FootballPosition.O_LINE, FootballPosition.WR),
        (FootballPosition.D_LINE, FootballPosition.CORNERBACKS),
    ),
    OffensivePlayAction.PA_PASS: (
        (FootballPosition.QB, FootballPosition.RB),
        (FootballPosition.SAFETIES, FootballPosition.LINEBACKERS),
    ),
    OffensivePlayAction.SHORT_PASS: (
        (FootballPosition.RB, FootballPosition.WR),
        (FootballPosition.LINEBACKERS, FootballPosition.CORNERBACKS),
    ),
    OffensivePlayAction.MEDIUM_PASS: (
        (FootballPosition.QB, FootballPosition.O_LINE),
        (FootballPosition.SAFETIES, FootballPosition.D_LINE),
    ),
    OffensivePlayAction.DEEP_PASS: (
        (FootballPosition.QB, FootballPosition.WR),
        (FootballPosition.SAFETIES, FootballPosition.CORNERBACKS),
    ),
})


def matchup_for_play(
    play: OffensivePlayAction,
) -> tuple[tuple[FootballPosition, ...], tuple[FootballPosition, ...]]:
    if not isinstance(play, OffensivePlayAction) or play not in FOOTBALL_PLAY_MATCHUPS:
        raise ValueError(f"Unsupported play: {play!r}")
    return FOOTBALL_PLAY_MATCHUPS[play]


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
    player_type_id: str | None = None

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
        if self.player_type_id is not None:
            _validate_name(self.player_type_id, "Player type identifier")
            from src.engine.football_player_catalog import player_type_for_id

            player_type = player_type_for_id(self.player_type_id)
            if player_type.position is not self.position:
                raise ValueError("Player type position must match the player's position.")


@dataclass(frozen=True)
class FootballCoach:
    name: str

    def __post_init__(self) -> None:
        _validate_name(self.name, "Coach name")


@dataclass(frozen=True)
class FootballCoachAssignment:
    offensive_coach_id: str
    defensive_coach_id: str

    def __post_init__(self) -> None:
        _validate_name(self.offensive_coach_id, "Offensive coach identifier")
        _validate_name(self.defensive_coach_id, "Defensive coach identifier")


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
    coach_assignment: FootballCoachAssignment | None = None

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
        if self.coach_assignment is not None and not isinstance(
            self.coach_assignment, FootballCoachAssignment
        ):
            raise ValueError("Coach assignment must be a FootballCoachAssignment or None.")
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
    incomplete: bool = False
    offense_power: float = 0.0
    defense_power: float = 0.0
    perk_effects: tuple[str, ...] = ()

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
        if not isinstance(self.incomplete, bool):
            raise ValueError("Incomplete must be a boolean.")
        if (
            self.defensive_scheme is not None
            and not isinstance(self.defensive_scheme, DefensiveSchemeAction)
        ):
            raise ValueError("Defensive scheme must be a DefensiveSchemeAction or None.")
        _validate_finite_number(self.offense_power, "Offense power")
        _validate_finite_number(self.defense_power, "Defense power")
        if self.offense_power < 0 or self.defense_power < 0:
            raise ValueError("Play powers must be non-negative.")
        if not isinstance(self.perk_effects, tuple) or any(
            not isinstance(effect, str) or not effect.strip()
            for effect in self.perk_effects
        ):
            raise ValueError("Perk effects must be a tuple of non-empty strings.")


@dataclass(frozen=True)
class FootballMatchEvent:
    """Immutable record of one caller action and the resulting match snapshot."""

    sequence: int
    action: OffensivePlayAction | DefensiveSchemeAction | FootballFourthDownAction
    team_a_score: int
    team_b_score: int
    possession: FootballTeamSide
    offense_field_position: float
    down: int
    yards_to_go: float
    game_clock_seconds: int
    period: int
    status: FootballMatchStatus
    clock_seconds_used: int = 0
    play_result: FootballPlayResult | None = None
    points_scored: int = 0
    scoring_team: FootballTeamSide | None = None
    field_goal_distance: float | None = None
    perk_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_nonnegative_int(self.sequence, "Event sequence")
        if self.sequence == 0:
            raise ValueError("Event sequence must be positive.")
        if not isinstance(
            self.action,
            (OffensivePlayAction, DefensiveSchemeAction, FootballFourthDownAction),
        ):
            raise ValueError("Event action must be a supported football action.")
        if self.play_result is not None and not isinstance(
            self.play_result, FootballPlayResult
        ):
            raise ValueError("Play result must be a FootballPlayResult or None.")
        if isinstance(self.action, OffensivePlayAction):
            if self.play_result is None or self.play_result.offensive_play is not self.action:
                raise ValueError("Offensive-play events must include their matching result.")
        elif self.play_result is not None:
            raise ValueError("Only offensive-play events can include a play result.")
        _validate_nonnegative_int(self.points_scored, "Event points scored")
        if self.points_scored and not isinstance(self.scoring_team, FootballTeamSide):
            raise ValueError("Scoring events must identify the scoring team.")
        if not self.points_scored and self.scoring_team is not None:
            raise ValueError("Non-scoring events cannot identify a scoring team.")
        if not isinstance(self.possession, FootballTeamSide):
            raise ValueError("Event possession must be a FootballTeamSide.")
        _validate_finite_number(self.offense_field_position, "Event field position")
        if not 0 <= self.offense_field_position <= 100:
            raise ValueError("Event field position must be between 0 and 100.")
        if isinstance(self.down, bool) or not isinstance(self.down, int) or not 1 <= self.down <= 4:
            raise ValueError("Event down must be an integer from 1 through 4.")
        _validate_finite_number(self.yards_to_go, "Event yards to go")
        if self.yards_to_go <= 0:
            raise ValueError("Event yards to go must be positive.")
        _validate_nonnegative_int(self.game_clock_seconds, "Event game clock seconds")
        _validate_nonnegative_int(self.clock_seconds_used, "Event clock seconds used")
        _validate_nonnegative_int(self.period, "Event period")
        if self.period == 0:
            raise ValueError("Event period must be positive.")
        if not isinstance(self.status, FootballMatchStatus):
            raise ValueError("Event status must be a FootballMatchStatus.")
        _validate_nonnegative_int(self.team_a_score, "Event team A score")
        _validate_nonnegative_int(self.team_b_score, "Event team B score")
        if self.field_goal_distance is not None:
            _validate_finite_number(self.field_goal_distance, "Field-goal distance")
            if self.field_goal_distance < 0:
                raise ValueError("Field-goal distance must be non-negative.")
        if isinstance(self.action, FootballFourthDownAction):
            if (
                self.action is FootballFourthDownAction.FIELD_GOAL
            ) != (self.field_goal_distance is not None):
                raise ValueError("Only field-goal events must record field-goal distance.")
            if self.action is FootballFourthDownAction.FIELD_GOAL and self.points_scored not in (0, 3):
                raise ValueError("Field-goal events can score zero or three points.")
        elif self.field_goal_distance is not None:
            raise ValueError("Only field-goal events can record field-goal distance.")
        if (
            self.play_result is not None
            and self.clock_seconds_used != self.play_result.clock_seconds_used
        ):
            raise ValueError("Event clock use must match its play result.")
        if self.play_result is not None and self.points_scored != self.play_result.points_scored:
            raise ValueError("Event scoring must match its play result.")
        if not isinstance(self.perk_effects, tuple) or any(
            not isinstance(effect, str) or not effect.strip()
            for effect in self.perk_effects
        ):
            raise ValueError("Perk effects must be a tuple of non-empty strings.")
        if self.play_result is not None and self.perk_effects != self.play_result.perk_effects:
            raise ValueError("Event perk effects must match its play result.")


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
    match_events: tuple[FootballMatchEvent, ...] = ()

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
        maximum_clock = 900 if self.period <= 2 else 300
        if self.game_clock_seconds > maximum_clock:
            raise ValueError(
                f"Game clock seconds cannot exceed {maximum_clock} in period {self.period}."
            )
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
        if not isinstance(self.match_events, tuple) or any(
            not isinstance(event, FootballMatchEvent) for event in self.match_events
        ):
            raise ValueError("Match events must be an immutable tuple of football events.")
        if any(event.sequence != index for index, event in enumerate(self.match_events, 1)):
            raise ValueError("Match event sequence numbers must be contiguous.")
        if self.status is FootballMatchStatus.COMPLETED:
            if self.final_result is None or not self.final_result.completed:
                raise ValueError("A completed match must have a completed final result.")
            if self.team_a_score == self.team_b_score:
                raise ValueError("A completed match cannot end in a tie.")
            if (
                self.final_result.team_a_score != self.team_a_score
                or self.final_result.team_b_score != self.team_b_score
            ):
                raise ValueError("Final result scores must match the match state.")
            if self.final_result.winner is not (
                FootballTeamSide.TEAM_A
                if self.team_a_score > self.team_b_score
                else FootballTeamSide.TEAM_B
            ):
                raise ValueError("Final result winner must match the match scores.")
            if self.awaited_action is not None or self.current_drive_defensive_scheme is not None:
                raise ValueError("A completed match cannot await an action or retain a scheme.")
        elif self.final_result is not None:
            raise ValueError("An in-progress match cannot have a final result.")
        if self.awaited_action is FootballAwaitedAction.DEFENSIVE_SCHEME:
            if self.down != 1:
                raise ValueError("A new defensive drive must start on first down.")
            if self.current_drive_defensive_scheme is not None:
                raise ValueError("A new defensive drive cannot already have a scheme.")
        elif self.awaited_action is FootballAwaitedAction.OFFENSIVE_PLAY:
            if self.current_drive_defensive_scheme is None:
                raise ValueError("An active drive must have a defensive scheme.")
            if self.down == 4:
                raise ValueError("A fourth-down state must await a fourth-down decision.")
        elif self.awaited_action is FootballAwaitedAction.FOURTH_DOWN_DECISION:
            if self.current_drive_defensive_scheme is None:
                raise ValueError("An active drive must have a defensive scheme.")
        if (
            self.awaited_action is FootballAwaitedAction.FOURTH_DOWN_DECISION
            and self.down != 4
        ):
            raise ValueError("A fourth-down decision must be awaited on fourth down.")
