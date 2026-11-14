"""Football card definitions and the run's initial playbook."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from src.engine.football import (
    DefensiveSchemeAction,
    FootballCardCopy,
    FootballPosition,
    OffensivePlayAction,
    matchup_for_scheme,
    matchup_for_play,
)


class FootballPlayFamily(str, Enum):
    RUN = "run"
    PASS = "pass"


@dataclass(frozen=True)
class FootballPlayDefinition:
    action: OffensivePlayAction
    name: str
    description: str
    contributors: tuple[FootballPosition, ...]
    family: FootballPlayFamily
    base_yards: float
    clock_seconds: int

    @property
    def card_id(self) -> str:
        return self.action.value


@dataclass(frozen=True)
class FootballSchemeDefinition:
    action: DefensiveSchemeAction
    name: str
    description: str
    contributors: tuple[FootballPosition, ...]
    counters: frozenset[OffensivePlayAction]

    @property
    def card_id(self) -> str:
        return self.action.value


def _play(
    action: OffensivePlayAction,
    name: str,
    description: str,
    family: FootballPlayFamily,
    base_yards: float,
    clock_seconds: int,
) -> FootballPlayDefinition:
    contributors, _ = matchup_for_play(action)
    return FootballPlayDefinition(
        action, name, description, contributors, family, base_yards, clock_seconds
    )


OFFENSIVE_PLAY_CATALOG = MappingProxyType(
    {
        definition.card_id: definition
        for definition in (
            _play(
                OffensivePlayAction.RB_RUN,
                "Inside Run",
                "O-line and running back attack the interior; run-focused coaches apply.",
                FootballPlayFamily.RUN,
                4.0,
                18,
            ),
            _play(
                OffensivePlayAction.SCREEN_PASS,
                "Screen Pass",
                "O-line and receiver set up a quick screen against edge coverage.",
                FootballPlayFamily.PASS,
                3.5,
                18,
            ),
            _play(
                OffensivePlayAction.PA_PASS,
                "Play-Action Pass",
                "Quarterback and running back sell the run before a pass.",
                FootballPlayFamily.PASS,
                5.0,
                18,
            ),
            _play(
                OffensivePlayAction.SHORT_PASS,
                "Short Pass",
                "Running back and receiver work underneath against linebackers and corners.",
                FootballPlayFamily.PASS,
                5.5,
                18,
            ),
            _play(
                OffensivePlayAction.MEDIUM_PASS,
                "Medium Pass",
                "Quarterback and O-line hold up for an intermediate route.",
                FootballPlayFamily.PASS,
                6.5,
                18,
            ),
            _play(
                OffensivePlayAction.DEEP_PASS,
                "Deep Pass",
                "Quarterback and receiver challenge the safeties and corners downfield.",
                FootballPlayFamily.PASS,
                8.0,
                18,
            ),
            _play(
                OffensivePlayAction.QB_SNEAK,
                "Quarterback Sneak",
                "Quarterback follows the O-line into a short-yardage gap.",
                FootballPlayFamily.RUN,
                2.8,
                18,
            ),
            _play(
                OffensivePlayAction.JET_SWEEP,
                "Jet Sweep",
                "Receiver takes a handoff behind the O-line toward the edge.",
                FootballPlayFamily.RUN,
                4.0,
                18,
            ),
            _play(
                OffensivePlayAction.QUICK_OUT,
                "Quick Out",
                "Quarterback targets a receiver outside before underneath coverage closes.",
                FootballPlayFamily.PASS,
                4.5,
                18,
            ),
        )
    }
)

DEFENSIVE_SCHEME_CATALOG = MappingProxyType(
    {
        definition.card_id: definition
        for definition in (
            FootballSchemeDefinition(
                action,
                name,
                description,
                matchup_for_scheme(action)[0],
                matchup_for_scheme(action)[1],
            )
            for action, name, description in (
                (
                    DefensiveSchemeAction.RB_RUN,
                    "Run Fit",
                    "D-line and linebackers fit the interior run.",
                ),
                (
                    DefensiveSchemeAction.SCREEN_PASS,
                    "Screen Read",
                    "D-line and corners close down the screen.",
                ),
                (
                    DefensiveSchemeAction.PA_PASS,
                    "Play-Action Read",
                    "Safeties and linebackers defend the play fake.",
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
                    "Safeties and corners protect downfield.",
                ),
                (
                    DefensiveSchemeAction.GOAL_LINE_FRONT,
                    "Goal-Line Front",
                    "D-line and linebackers counter inside runs, sneaks, and sweeps.",
                ),
                (
                    DefensiveSchemeAction.COVER_TWO_SHELL,
                    "Cover Two Shell",
                    "Safeties and corners bracket deep, medium, and quick-out routes.",
                ),
                (
                    DefensiveSchemeAction.FIRE_ZONE_BLITZ,
                    "Fire-Zone Blitz",
                    "Linebackers and D-line pressure play-action and medium passes.",
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
