"""Football card definitions and the run's initial playbook."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType

from src.engine.football import (
    DEFENSIVE_SCHEME_FAMILIES,
    DefensiveSchemeAction,
    FootballCardFamily,
    FootballCardCopy,
    FootballPosition,
    OffensivePlayAction,
    OFFENSIVE_PLAY_FAMILIES,
    matchup_for_scheme,
    matchup_for_play,
)

FootballPlayFamily = FootballCardFamily


@dataclass(frozen=True)
class FootballPlayDefinition:
    action: OffensivePlayAction
    name: str
    description: str
    contributors: tuple[FootballPosition, ...]
    family: FootballCardFamily
    base_yards: float
    clock_seconds: int

    @property
    def card_id(self) -> str:
        return self.action.value

    def __post_init__(self) -> None:
        if not isinstance(self.action, OffensivePlayAction):
            raise ValueError("Play definition action must be an OffensivePlayAction.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Play definition name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Play definition description must be a non-empty string.")
        if not isinstance(self.family, FootballCardFamily):
            raise ValueError("Play definition family must be a FootballCardFamily.")
        if self.family is not OFFENSIVE_PLAY_FAMILIES[self.action]:
            raise ValueError("Play definition family does not match its action.")
        if not isinstance(self.contributors, tuple) or not self.contributors or any(
            not isinstance(position, FootballPosition)
            for position in self.contributors
        ):
            raise ValueError("Play contributors must be a non-empty position tuple.")
        if self.contributors != matchup_for_play(self.action)[0]:
            raise ValueError("Play contributors must match their family's matchup.")
        if isinstance(self.base_yards, bool) or not isinstance(
            self.base_yards, (int, float)
        ) or not isfinite(self.base_yards):
            raise ValueError("Play base yards must be finite.")
        if isinstance(self.clock_seconds, bool) or not isinstance(
            self.clock_seconds, int
        ) or self.clock_seconds <= 0:
            raise ValueError("Play clock duration must be a positive integer.")


@dataclass(frozen=True)
class FootballSchemeDefinition:
    action: DefensiveSchemeAction
    name: str
    description: str
    contributors: tuple[FootballPosition, ...]
    family: FootballCardFamily
    counters: frozenset[OffensivePlayAction]

    @property
    def card_id(self) -> str:
        return self.action.value

    def __post_init__(self) -> None:
        if not isinstance(self.action, DefensiveSchemeAction):
            raise ValueError("Scheme definition action must be a DefensiveSchemeAction.")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Scheme definition name must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Scheme definition description must be a non-empty string.")
        if not isinstance(self.family, FootballCardFamily):
            raise ValueError("Scheme definition family must be a FootballCardFamily.")
        if self.family is not DEFENSIVE_SCHEME_FAMILIES[self.action]:
            raise ValueError("Scheme definition family does not match its action.")
        if not isinstance(self.contributors, tuple) or not self.contributors or any(
            not isinstance(position, FootballPosition)
            for position in self.contributors
        ):
            raise ValueError("Scheme contributors must be a non-empty position tuple.")
        if not isinstance(self.counters, frozenset) or any(
            not isinstance(play, OffensivePlayAction) for play in self.counters
        ):
            raise ValueError("Scheme counters must be an immutable set of offensive plays.")
        contributors, counters = matchup_for_scheme(self.action)
        if self.contributors != contributors or self.counters != counters:
            raise ValueError("Scheme contributors and counters must match its family.")


def _play(
    action: OffensivePlayAction,
    name: str,
    description: str,
    base_yards: float,
    clock_seconds: int,
) -> FootballPlayDefinition:
    contributors, _ = matchup_for_play(action)
    return FootballPlayDefinition(
        action,
        name,
        description,
        contributors,
        OFFENSIVE_PLAY_FAMILIES[action],
        base_yards,
        clock_seconds,
    )


def _scheme(
    action: DefensiveSchemeAction,
    name: str,
    description: str,
) -> FootballSchemeDefinition:
    contributors, counters = matchup_for_scheme(action)
    return FootballSchemeDefinition(
        action,
        name,
        description,
        contributors,
        DEFENSIVE_SCHEME_FAMILIES[action],
        counters,
    )


OFFENSIVE_PLAY_CATALOG = MappingProxyType(
    {
        definition.card_id: definition
        for definition in (
            _play(
                OffensivePlayAction.RB_RUN,
                "Inside Run",
                "O-line and running back press the interior gap.",
                4.0,
                26,
            ),
            _play(
                OffensivePlayAction.SCREEN_PASS,
                "Screen Pass",
                "O-line releases the receiver into space behind the rush.",
                3.5,
                24,
            ),
            _play(
                OffensivePlayAction.PA_PASS,
                "Play-Action Pass",
                "Quarterback and running back sell the run before a pass.",
                5.0,
                28,
            ),
            _play(
                OffensivePlayAction.SHORT_PASS,
                "Short Pass",
                "Running back and receiver work underneath against close coverage.",
                5.5,
                24,
            ),
            _play(
                OffensivePlayAction.MEDIUM_PASS,
                "Medium Pass",
                "Quarterback and O-line hold up for an intermediate route.",
                6.5,
                26,
            ),
            _play(
                OffensivePlayAction.DEEP_PASS,
                "Deep Pass",
                "Quarterback and receiver challenge coverage downfield.",
                8.0,
                28,
            ),
            _play(
                OffensivePlayAction.QB_SNEAK,
                "Quarterback Sneak",
                "A short, direct push through the interior run lane.",
                2.8,
                24,
            ),
            _play(
                OffensivePlayAction.JET_SWEEP,
                "Jet Sweep",
                "A fast handoff sweeps toward the edge behind the run block.",
                4.0,
                22,
            ),
            _play(
                OffensivePlayAction.QUICK_OUT,
                "Quick Out",
                "A quick underneath throw breaks toward the sideline.",
                4.5,
                20,
            ),
            _play(
                OffensivePlayAction.POWER_TOSS,
                "Power Toss",
                "The back follows the line laterally before turning upfield.",
                4.5,
                29,
            ),
            _play(
                OffensivePlayAction.BUBBLE_SCREEN,
                "Bubble Screen",
                "A quick screen puts the receiver in space outside.",
                4.0,
                19,
            ),
            _play(
                OffensivePlayAction.BOOTLEG_KEEPER,
                "Bootleg Keeper",
                "The quarterback sells the run fake, rolls out, and throws on the move.",
                6.0,
                30,
            ),
            _play(
                OffensivePlayAction.SLOT_SLANT,
                "Slot Slant",
                "The receiver cuts inside for a fast underneath target.",
                6.0,
                22,
            ),
            _play(
                OffensivePlayAction.DEEP_DIG,
                "Deep Dig",
                "The receiver bends into an intermediate window across the field.",
                7.0,
                29,
            ),
            _play(
                OffensivePlayAction.GO_ROUTE,
                "Go Route",
                "The receiver pushes vertically for a deep sideline throw.",
                8.5,
                32,
            ),
        )
    }
)

DEFENSIVE_SCHEME_CATALOG = MappingProxyType(
    {
        definition.card_id: definition
        for definition in (
            _scheme(action, name, description)
            for action, name, description in (
                (
                    DefensiveSchemeAction.RB_RUN,
                    "Run Fit",
                    "D-line and linebackers fit the RB Run family.",
                ),
                (
                    DefensiveSchemeAction.SCREEN_PASS,
                    "Screen Read",
                    "D-line and corners close down screen routes.",
                ),
                (
                    DefensiveSchemeAction.PA_PASS,
                    "Play-Action Read",
                    "Safeties and linebackers read the play fake.",
                ),
                (
                    DefensiveSchemeAction.SHORT_PASS,
                    "Under Coverage",
                    "Linebackers and corners contest short routes.",
                ),
                (
                    DefensiveSchemeAction.MEDIUM_PASS,
                    "Pressure Shell",
                    "Safeties and D-line challenge intermediate routes.",
                ),
                (
                    DefensiveSchemeAction.DEEP_PASS,
                    "Deep Coverage",
                    "Safeties and corners protect the deep passing family.",
                ),
                (
                    DefensiveSchemeAction.GOAL_LINE_FRONT,
                    "Goal-Line Front",
                    "A tight front against the RB Run family.",
                ),
                (
                    DefensiveSchemeAction.COVER_TWO_SHELL,
                    "Cover Two Shell",
                    "Safeties and corners bracket the Deep Pass family.",
                ),
                (
                    DefensiveSchemeAction.FIRE_ZONE_BLITZ,
                    "Fire-Zone Blitz",
                    "Safeties and D-line pressure the Medium Pass family.",
                ),
                (
                    DefensiveSchemeAction.SPILL_FRONT,
                    "Spill Front",
                    "D-line and linebackers set the edge against the run.",
                ),
                (
                    DefensiveSchemeAction.PERIMETER_CHECK,
                    "Perimeter Check",
                    "D-line and corners rally to the screen.",
                ),
                (
                    DefensiveSchemeAction.READ_REACT,
                    "Read and React",
                    "Safeties and linebackers stay disciplined against the fake.",
                ),
                (
                    DefensiveSchemeAction.NICKEL_UNDER,
                    "Nickel Under",
                    "Linebackers and corners close the underneath windows.",
                ),
                (
                    DefensiveSchemeAction.TWO_HIGH_PRESSURE,
                    "Two-High Pressure",
                    "Safeties and D-line contest intermediate routes.",
                ),
                (
                    DefensiveSchemeAction.QUARTERS_COVERAGE,
                    "Quarters Coverage",
                    "Safeties and corners protect the deep routes.",
                ),
            )
        )
    }
)

STARTING_OFFENSIVE_ACTIONS = tuple(
    action
    for action in OffensivePlayAction
    if action
    in (
        OffensivePlayAction.RB_RUN,
        OffensivePlayAction.SCREEN_PASS,
        OffensivePlayAction.PA_PASS,
        OffensivePlayAction.SHORT_PASS,
        OffensivePlayAction.MEDIUM_PASS,
        OffensivePlayAction.DEEP_PASS,
    )
)
STARTING_DEFENSIVE_ACTIONS = tuple(
    action
    for action in DefensiveSchemeAction
    if action
    in (
        DefensiveSchemeAction.RB_RUN,
        DefensiveSchemeAction.SCREEN_PASS,
        DefensiveSchemeAction.PA_PASS,
        DefensiveSchemeAction.SHORT_PASS,
        DefensiveSchemeAction.MEDIUM_PASS,
        DefensiveSchemeAction.DEEP_PASS,
    )
)


def starting_offensive_deck(prefix: str) -> tuple[FootballCardCopy, ...]:
    return tuple(
        FootballCardCopy(f"{prefix}:offense:{action.value}:1", action.value)
        for action in STARTING_OFFENSIVE_ACTIONS
    )


def starting_defensive_deck(prefix: str) -> tuple[FootballCardCopy, ...]:
    return tuple(
        FootballCardCopy(f"{prefix}:defense:{action.value}:1", action.value)
        for action in STARTING_DEFENSIVE_ACTIONS
    )
