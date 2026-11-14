"""Immutable interactive-football coach catalog and typed perk definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from src.engine.football import (
    DefensiveSchemeAction,
    FootballCoachAssignment,
    FootballPosition,
    OffensivePlayAction,
    matchup_for_play,
)


class FootballCoachSide(str, Enum):
    OFFENSE = "offense"
    DEFENSE = "defense"


class FootballCoachPerkKind(str, Enum):
    FIRST_RUN_YARDS = "first_run_yards"
    FOURTH_DOWN_SUCCESS_BONUS = "fourth_down_success_bonus"
    FIRST_COMPLETED_PASS_YARDS = "first_completed_pass_yards"
    FIRST_DOWN_PASS_YARDS = "first_down_pass_yards"
    MATCHED_RUN_YARDS_REDUCTION = "matched_run_yards_reduction"
    MATCHED_PASS_INTERCEPTION_BONUS = "matched_pass_interception_bonus"
    MATCHED_PASS_INCOMPLETE_BONUS = "matched_pass_incomplete_bonus"
    INTERCEPTION_RETURN_YARDS = "interception_return_yards"


OFFENSIVE_POSITIONS = (
    FootballPosition.QB,
    FootballPosition.RB,
    FootballPosition.WR,
    FootballPosition.O_LINE,
)
DEFENSIVE_POSITIONS = (
    FootballPosition.D_LINE,
    FootballPosition.LINEBACKERS,
    FootballPosition.CORNERBACKS,
    FootballPosition.SAFETIES,
)
OFFENSIVE_ACTIONS = tuple(OffensivePlayAction)
DEFENSIVE_ACTIONS = tuple(DefensiveSchemeAction)


@dataclass(frozen=True)
class FootballCoachPerk:
    kind: FootballCoachPerkKind
    value: float
    trigger: str
    effect: str
    duration: str
    reset: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FootballCoachPerkKind):
            raise ValueError("Perk kind must be a FootballCoachPerkKind.")
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not isfinite(self.value)
            or self.value < 0
        ):
            raise ValueError("Perk value must be a finite non-negative number.")
        if not all(
            isinstance(text, str) and text.strip()
            for text in (self.trigger, self.effect, self.duration, self.reset)
        ):
            raise ValueError("Perk trigger, effect, duration, and reset must be described.")


@dataclass(frozen=True)
class FootballCoachProfile:
    coach_id: str
    name: str
    side: FootballCoachSide
    position_modifiers: Mapping[FootballPosition, float]
    perk: FootballCoachPerk | None
    balanced: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.coach_id, str)
            or not self.coach_id.strip()
            or not isinstance(self.name, str)
            or not self.name.strip()
        ):
            raise ValueError("Coach profile identifiers and names must be non-empty.")
        if not isinstance(self.side, FootballCoachSide):
            raise ValueError("Coach profile side must be a FootballCoachSide.")
        if not isinstance(self.position_modifiers, Mapping):
            raise ValueError("Coach modifiers must map positions to bonus values.")
        if not isinstance(self.balanced, bool):
            raise ValueError("Balanced must be a boolean.")
        if self.perk is not None and not isinstance(self.perk, FootballCoachPerk):
            raise ValueError("Coach perk must be a FootballCoachPerk or None.")
        positions = (
            OFFENSIVE_POSITIONS
            if self.side is FootballCoachSide.OFFENSE
            else DEFENSIVE_POSITIONS
        )
        if set(self.position_modifiers) != set(positions):
            raise ValueError("Coach modifiers must cover exactly the positions on their side.")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value not in (-0.1, 0.0, 0.05, 0.1, 0.2)
            for value in self.position_modifiers.values()
        ):
            raise ValueError("Coach position modifiers must use supported bonus values.")
        values = tuple(self.position_modifiers.values())
        if self.balanced:
            if self.perk is not None or any(value != 0.05 for value in values):
                raise ValueError("Balanced coaches require +5% at each position and no perk.")
        elif self.perk is None or sorted(values) != [-0.1, 0.0, 0.1, 0.2]:
            raise ValueError("Specialists require one +20%, +10%, -10%, and neutral position.")
        object.__setattr__(
            self, "position_modifiers", MappingProxyType(dict(self.position_modifiers))
        )

    def __hash__(self) -> int:
        return hash(self.coach_id)

    @property
    def actions(self) -> tuple[OffensivePlayAction, ...] | tuple[DefensiveSchemeAction, ...]:
        return (
            OFFENSIVE_ACTIONS
            if self.side is FootballCoachSide.OFFENSE
            else DEFENSIVE_ACTIONS
        )

    @property
    def action_percentages(
        self,
    ) -> Mapping[OffensivePlayAction | DefensiveSchemeAction, int]:
        percentages = {}
        for play in OFFENSIVE_ACTIONS:
            offense_positions, _ = matchup_for_play(play)
            positions = (
                offense_positions
                if self.side is FootballCoachSide.OFFENSE
                else matchup_for_play(OffensivePlayAction(play.value))[1]
            )
            action = (
                play
                if self.side is FootballCoachSide.OFFENSE
                else DefensiveSchemeAction(play.value)
            )
            bonus = sum(self.position_modifiers[position] for position in positions)
            percentages[action] = round((1.0 + bonus) * 100)
        return MappingProxyType(percentages)


@dataclass(frozen=True)
class FootballCoachPair:
    offense: FootballCoachProfile
    defense: FootballCoachProfile

    def __post_init__(self) -> None:
        if (
            not isinstance(self.offense, FootballCoachProfile)
            or self.offense.side is not FootballCoachSide.OFFENSE
        ):
            raise ValueError("Coach pair offense must be an offensive profile.")
        if (
            not isinstance(self.defense, FootballCoachProfile)
            or self.defense.side is not FootballCoachSide.DEFENSE
        ):
            raise ValueError("Coach pair defense must be a defensive profile.")

    @property
    def assignment(self) -> FootballCoachAssignment:
        return FootballCoachAssignment(self.offense.coach_id, self.defense.coach_id)


def _perk(
    kind: FootballCoachPerkKind,
    value: float,
    trigger: str,
    effect: str,
    duration: str,
    reset: str,
) -> FootballCoachPerk:
    return FootballCoachPerk(kind, value, trigger, effect, duration, reset)


def _profile(
    coach_id: str,
    name: str,
    side: FootballCoachSide,
    modifiers: Mapping[FootballPosition, float],
    perk: FootballCoachPerk | None,
    *,
    balanced: bool = False,
) -> FootballCoachProfile:
    return FootballCoachProfile(coach_id, name, side, modifiers, perk, balanced)


_OFFENSE = FootballCoachSide.OFFENSE
_DEFENSE = FootballCoachSide.DEFENSE

OFFENSIVE_COACHES = (
    _profile(
        "ground_and_pound",
        "Ground and Pound",
        _OFFENSE,
        {
            FootballPosition.O_LINE: 0.2,
            FootballPosition.RB: 0.1,
            FootballPosition.WR: -0.1,
            FootballPosition.QB: 0.0,
        },
        _perk(
            FootballCoachPerkKind.FIRST_RUN_YARDS,
            3,
            "First RB Run attempt per offensive drive.",
            "+3 yards on a non-turnover run.",
            "That run.",
            "Attempt is spent on turnover; refreshes next offensive drive.",
        ),
    ),
    _profile(
        "option_spread",
        "Option / Spread",
        _OFFENSE,
        {
            FootballPosition.RB: 0.2,
            FootballPosition.WR: 0.1,
            FootballPosition.QB: -0.1,
            FootballPosition.O_LINE: 0.0,
        },
        _perk(
            FootballCoachPerkKind.FOURTH_DOWN_SUCCESS_BONUS,
            0.1,
            "The offense chooses Go For It on fourth down.",
            "+10 percentage points success chance; capped at 78%.",
            "That decision.",
            "Eligible on every Go For It decision.",
        ),
    ),
    _profile(
        "air_raid",
        "Air Raid",
        _OFFENSE,
        {
            FootballPosition.WR: 0.2,
            FootballPosition.QB: 0.1,
            FootballPosition.O_LINE: -0.1,
            FootballPosition.RB: 0.0,
        },
        _perk(
            FootballCoachPerkKind.FIRST_COMPLETED_PASS_YARDS,
            3,
            "First completed pass per offensive drive.",
            "+3 yards to the pass.",
            "That pass.",
            "Incomplete/INT does not consume it; refreshes next drive.",
        ),
    ),
    _profile(
        "pro_style",
        "Pro Style",
        _OFFENSE,
        {
            FootballPosition.QB: 0.2,
            FootballPosition.O_LINE: 0.1,
            FootballPosition.RB: -0.1,
            FootballPosition.WR: 0.0,
        },
        _perk(
            FootballCoachPerkKind.FIRST_DOWN_PASS_YARDS,
            2,
            "A completed, non-turnover pass called on first down.",
            "Add 2 yards to the pass.",
            "That play.",
            "Eligible on every first-down pass.",
        ),
    ),
    _profile(
        "balanced_offense",
        "Balanced Offense",
        _OFFENSE,
        {position: 0.05 for position in OFFENSIVE_POSITIONS},
        None,
        balanced=True,
    ),
)

DEFENSIVE_COACHES = (
    _profile(
        "run_stop",
        "Run Stop",
        _DEFENSE,
        {
            FootballPosition.D_LINE: 0.2,
            FootballPosition.LINEBACKERS: 0.1,
            FootballPosition.CORNERBACKS: -0.1,
            FootballPosition.SAFETIES: 0.0,
        },
        _perk(
            FootballCoachPerkKind.MATCHED_RUN_YARDS_REDUCTION,
            2,
            "The opponent runs RB Run against the RB Run scheme.",
            "Reduce the non-turnover result by 2 yards.",
            "That snap.",
            "Eligible on every matching snap.",
        ),
    ),
    _profile(
        "pressure_blitz",
        "Pressure / Blitz",
        _DEFENSE,
        {
            FootballPosition.LINEBACKERS: 0.2,
            FootballPosition.CORNERBACKS: 0.1,
            FootballPosition.SAFETIES: -0.1,
            FootballPosition.D_LINE: 0.0,
        },
        _perk(
            FootballCoachPerkKind.MATCHED_PASS_INTERCEPTION_BONUS,
            0.05,
            "A pass play matches the selected scheme.",
            "+5 percentage points to interception chance.",
            "That snap.",
            "Eligible on every matching pass.",
        ),
    ),
    _profile(
        "coverage",
        "Coverage",
        _DEFENSE,
        {
            FootballPosition.CORNERBACKS: 0.2,
            FootballPosition.SAFETIES: 0.1,
            FootballPosition.D_LINE: -0.1,
            FootballPosition.LINEBACKERS: 0.0,
        },
        _perk(
            FootballCoachPerkKind.MATCHED_PASS_INCOMPLETE_BONUS,
            0.05,
            "A pass play matches the selected scheme.",
            "+5 percentage points to incompletion chance.",
            "That snap.",
            "Eligible on every matching pass.",
        ),
    ),
    _profile(
        "ball_hawk",
        "Ball-Hawk",
        _DEFENSE,
        {
            FootballPosition.SAFETIES: 0.2,
            FootballPosition.D_LINE: 0.1,
            FootballPosition.LINEBACKERS: -0.1,
            FootballPosition.CORNERBACKS: 0.0,
        },
        _perk(
            FootballCoachPerkKind.INTERCEPTION_RETURN_YARDS,
            10,
            "The defense intercepts a pass.",
            "Add 10 yards to resulting field position, capped at 100.",
            "That interception.",
            "Eligible on every interception.",
        ),
    ),
    _profile(
        "balanced_defense",
        "Balanced Defense",
        _DEFENSE,
        {position: 0.05 for position in DEFENSIVE_POSITIONS},
        None,
        balanced=True,
    ),
)

COACHES_BY_ID = MappingProxyType(
    {coach.coach_id: coach for coach in (*OFFENSIVE_COACHES, *DEFENSIVE_COACHES)}
)
COACH_PAIR_OFFERS = tuple(
    FootballCoachPair(offense, defense)
    for offense in OFFENSIVE_COACHES
    for defense in DEFENSIVE_COACHES
)


def coach_for_id(coach_id: str) -> FootballCoachProfile:
    try:
        return COACHES_BY_ID[coach_id]
    except KeyError as error:
        raise ValueError(f"Unknown coach identifier: {coach_id!r}.") from error


def coaches_for_assignment(
    assignment: FootballCoachAssignment | None,
) -> tuple[FootballCoachProfile | None, FootballCoachProfile | None]:
    if assignment is None:
        return None, None
    offense = coach_for_id(assignment.offensive_coach_id)
    defense = coach_for_id(assignment.defensive_coach_id)
    if offense.side is not FootballCoachSide.OFFENSE:
        raise ValueError("Assigned offensive coach must have an offensive profile.")
    if defense.side is not FootballCoachSide.DEFENSE:
        raise ValueError("Assigned defensive coach must have a defensive profile.")
    return offense, defense
