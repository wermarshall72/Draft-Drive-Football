"""Caller-driven interactive football match resolution.

All randomness belongs to one ``FootballMatchSimulator`` instance for the
entire match. Yardage, clock, fatigue, and probability constants are prototype
values informed by available historical FBS summaries and arcade tuning.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from functools import lru_cache
from math import floor, isfinite
from numbers import Real

from src.engine.football import (
    DEFENSIVE_SCHEME_FAMILIES,
    DefensiveSchemeAction,
    FootballAwaitedAction,
    FootballCardFamily,
    FootballCardCopy,
    FootballCoach,
    FootballCoachUpgradeEffect,
    FootballCoachUpgradeKind,
    FootballDeckState,
    FootballFourthDownAction,
    FootballMatchEvent,
    FootballMatchResult,
    FootballMatchState,
    FootballMatchStatus,
    FootballPlayer,
    FootballPosition,
    FootballPlayResult,
    FootballRoster,
    FootballSpecialTeams,
    FootballAutomaticAction,
    FootballConversionAction,
    FootballTeamSide,
    FootballTurnoverType,
    OFFENSIVE_PLAY_FAMILIES,
    OffensivePlayAction,
    matchup_for_scheme,
    matchup_for_play,
)
from src.engine.football_coaches import (
    FootballCoachPerkKind,
    coaches_for_assignment,
)
from src.engine.football_player_catalog import player_contribution_modifier
from src.engine.football_decks import (
    DEFENSIVE_SCHEME_CATALOG,
    OFFENSIVE_PLAY_CATALOG,
    starting_defensive_deck,
    starting_offensive_deck,
)

REGULATION_PERIOD_SECONDS = 900
OVERTIME_PERIOD_SECONDS = 300
FIRST_DOWN_YARDS = 10.0
GOAL_LINE_YARDS = 100.0
FIELD_GOAL_DISTANCE_BUFFER = 10.0

# Broad historical distance bands shape this provisional curve; it is not a
# verified 2022-2024 FBS distance-stratified aggregate.
FIELD_GOAL_POINTS = 3
TOUCHDOWN_POINTS = 6
SAFETY_POINTS = 2
INCOMPLETE_PASS_CLOCK_SECONDS = 5
PUNT_CLOCK_SECONDS = 10
FIELD_GOAL_CLOCK_SECONDS = 5
KICKOFF_CLOCK_SECONDS = 10
KICKOFF_GROSS_YARDS = 65.0
PUNT_GROSS_MEAN_YARDS = 43.0
PUNT_GROSS_STANDARD_DEVIATION = 5.0
PUNT_RETURN_CHANCE = 0.48
PUNT_RETURN_MEAN_YARDS = 8.0
PUNT_RETURN_STANDARD_DEVIATION = 4.0
PUNT_BLOCK_CHANCE = 0.007
FIELD_GOAL_BLOCK_CHANCE = 0.005
BLOCKED_KICK_RECOVERY_CHANCE = 0.5
BLOCKED_KICK_OWN_RECOVERY_MEAN_YARDS = 4.0
BLOCKED_KICK_OWN_RECOVERY_STANDARD_DEVIATION = 3.0
BLOCKED_KICK_RETURN_MEAN_YARDS = 15.0
BLOCKED_KICK_RETURN_STANDARD_DEVIATION = 8.0
EXTRA_POINT_BLOCK_CHANCE = 0.003
KICKOFF_TOUCHBACK_CHANCE = 0.58
KICKOFF_RETURN_MEAN_YARDS = 25.0
KICKOFF_RETURN_STANDARD_DEVIATION = 6.0
KICKOFF_RETURN_TOUCHDOWN_CHANCE = 0.002
EXTRA_POINT_SUCCESS_CHANCE = 0.94
TWO_POINT_RETURN_TOUCHDOWN_CHANCE = 0.01
TOUCHBACK_START_YARDS = 25.0
MIN_PLAY_YARDAGE_SPREAD = 1.0
VOLATILITY_SPREAD_MULTIPLIER = 6.0
FATIGUE_RAMP_PLAYS = 30
MAX_FATIGUE_POWER_REDUCTION = 0.10
MAX_COACH_POWER_BONUS = 0.20
MAX_COACH_VOLATILITY_REDUCTION = 0.30
MAX_COACH_STAMINA_BONUS = 0.30
MAX_COACH_YARDAGE_DELTA = 0.50
MAX_COACH_RISK_REDUCTION = 0.75
MIN_COACH_CLOCK_MULTIPLIER = 0.75
MAX_COACH_CLOCK_MULTIPLIER = 1.25
MATCHED_SCHEME_DEFENSE_MULTIPLIER = 1.12
MATCHED_SCHEME_OFFENSE_MULTIPLIER = 0.96
MATCHED_SCHEME_YARDAGE_PENALTY = 0.5
PLAY_DEFENSE_BASELINE_YARDAGE_REDUCTION = 0.0
OFFENSIVE_BASELINE_YARDAGE_BONUS = 3.5
RUN_BASELINE_YARDAGE_ADJUSTMENT = -3.75
PASS_BASELINE_YARDAGE_ADJUSTMENT = 1.0
POWER_YARDAGE_MULTIPLIER = 0.16
PASS_INCOMPLETE_BASE_PROBABILITY = 0.29
MATCHED_SCHEME_INCOMPLETE_BONUS = 0.04
MATCHUP_INCOMPLETE_SENSITIVITY = 0.16
MATCHUP_TURNOVER_SENSITIVITY = 0.04
MATCHED_SCHEME_TURNOVER_BONUS = 0.005
MIN_PLAY_YARDAGE = -5.0
MAX_PLAY_YARDAGE = 25.0
MAX_NONSCORING_RETURN_FIELD_POSITION = GOAL_LINE_YARDS - 1.0
PASS_INTERCEPTION_PROBABILITIES = {
    FootballCardFamily.SCREEN_PASS: 0.015,
    FootballCardFamily.PA_PASS: 0.025,
    FootballCardFamily.SHORT_PASS: 0.015,
    FootballCardFamily.MEDIUM_PASS: 0.025,
    FootballCardFamily.DEEP_PASS: 0.04,
}
RUN_FUMBLE_PROBABILITIES = {
    FootballCardFamily.RB_RUN: 0.012,
}

_PASS_PLAYS = frozenset(
    definition.action
    for definition in OFFENSIVE_PLAY_CATALOG.values()
    if definition.family is not FootballCardFamily.RB_RUN
)
_BASE_YARDAGE = {
    definition.action: definition.base_yards
    for definition in OFFENSIVE_PLAY_CATALOG.values()
}
_FIELD_GOAL_DISTANCE_RATES = (
    (17.0, 0.950),
    (22.0, 0.936),
    (27.0, 0.880),
    (32.0, 0.813),
    (37.0, 0.744),
    (42.0, 0.652),
    (47.0, 0.588),
    (52.0, 0.486),
    (57.0, 0.387),
    (62.0, 0.385),
    (67.0, 0.10),
)


def field_goal_distance_for_position(field_position: float) -> float:
    if (
        isinstance(field_position, bool)
        or not isinstance(field_position, Real)
        or not isfinite(field_position)
    ):
        raise ValueError("Field position must be a finite number from 0 to 100.")
    if not 0 <= field_position <= GOAL_LINE_YARDS:
        raise ValueError("Field position must be between 0 and 100.")
    return (GOAL_LINE_YARDS - field_position) + FIELD_GOAL_DISTANCE_BUFFER


def field_goal_success_probability(
    distance: float, bonus_percentage_points: float = 0.0
) -> float:
    if (
        isinstance(distance, bool)
        or not isinstance(distance, Real)
        or not isfinite(distance)
        or distance < 0
    ):
        raise ValueError("Field-goal distance must be a non-negative number.")
    if (
        isinstance(bonus_percentage_points, bool)
        or not isinstance(bonus_percentage_points, Real)
        or not isfinite(bonus_percentage_points)
        or bonus_percentage_points < 0
    ):
        raise ValueError("Field-goal bonus must be a finite non-negative probability.")
    if distance <= _FIELD_GOAL_DISTANCE_RATES[0][0]:
        return _clamp(0.97 + bonus_percentage_points, 0.0, 1.0)
    for (lower_distance, lower_rate), (upper_distance, upper_rate) in zip(
        _FIELD_GOAL_DISTANCE_RATES,
        _FIELD_GOAL_DISTANCE_RATES[1:],
    ):
        if distance <= upper_distance:
            fraction = (distance - lower_distance) / (
                upper_distance - lower_distance
            )
            return _clamp(
                lower_rate + fraction * (upper_rate - lower_rate)
                + bonus_percentage_points,
                0.0,
                1.0,
            )
    return _clamp(
        _FIELD_GOAL_DISTANCE_RATES[-1][1] + bonus_percentage_points,
        0.0,
        1.0,
    )


def coach_upgrade_magnitude(
    upgrades: tuple[FootballCoachUpgradeEffect, ...],
    kind: FootballCoachUpgradeKind,
    *,
    family: FootballCardFamily | None = None,
) -> float:
    if (
        not isinstance(upgrades, tuple)
        or any(not isinstance(upgrade, FootballCoachUpgradeEffect) for upgrade in upgrades)
        or not isinstance(kind, FootballCoachUpgradeKind)
    ):
        raise ValueError("Coach effect lookup requires typed immutable upgrades.")
    return sum(
        upgrade.magnitude
        for upgrade in upgrades
        if upgrade.kind is kind
        and (family is None or upgrade.family is family)
    )


def field_goal_success_probability_for_team(
    state: FootballMatchState,
    team: FootballTeamSide,
    distance: float,
) -> float:
    if not isinstance(state, FootballMatchState) or not isinstance(team, FootballTeamSide):
        raise ValueError("Field-goal estimate requires a match and team side.")
    upgrades = (
        state.team_a_coach_upgrades
        if team is FootballTeamSide.TEAM_A
        else state.team_b_coach_upgrades
    )
    bonus = coach_upgrade_magnitude(
        upgrades, FootballCoachUpgradeKind.FIELD_GOAL_ACCURACY_BONUS
    )
    return field_goal_success_probability(distance, bonus)


def adjusted_offensive_play_clock_seconds(
    base_seconds: int,
    upgrades: tuple[FootballCoachUpgradeEffect, ...],
) -> int:
    if isinstance(base_seconds, bool) or not isinstance(base_seconds, int) or base_seconds < 1:
        raise ValueError("Offensive play clock duration must be a positive integer.")
    delta = coach_upgrade_magnitude(
        upgrades, FootballCoachUpgradeKind.OFFENSIVE_PLAY_CLOCK_DELTA
    )
    multiplier = _clamp(
        1.0 + delta,
        MIN_COACH_CLOCK_MULTIPLIER,
        MAX_COACH_CLOCK_MULTIPLIER,
    )
    return max(1, floor(base_seconds * multiplier + 0.5))


def blocked_kick_probability(
    state: FootballMatchState,
    kicking_team: FootballTeamSide,
    base_probability: float,
) -> float:
    if (
        not isinstance(state, FootballMatchState)
        or not isinstance(kicking_team, FootballTeamSide)
        or isinstance(base_probability, bool)
        or not isinstance(base_probability, Real)
        or not isfinite(base_probability)
        or not 0.0 <= base_probability <= 1.0
    ):
        raise ValueError("Blocked-kick estimate requires a valid match, team, and chance.")
    upgrades = (
        state.team_a_coach_upgrades
        if kicking_team is FootballTeamSide.TEAM_A
        else state.team_b_coach_upgrades
    )
    reduction = min(
        MAX_COACH_RISK_REDUCTION,
        coach_upgrade_magnitude(
            upgrades, FootballCoachUpgradeKind.BLOCKED_KICK_RISK_REDUCTION
        ),
    )
    return _clamp(base_probability * (1.0 - reduction), 0.0, 1.0)


def _opponent(side: FootballTeamSide) -> FootballTeamSide:
    return (
        FootballTeamSide.TEAM_B
        if side is FootballTeamSide.TEAM_A
        else FootballTeamSide.TEAM_A
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _drive_yards_remaining(position: float) -> float:
    return max(0.0, GOAL_LINE_YARDS - position)


def _scheme_matches_play(
    scheme: DefensiveSchemeAction | None, play: OffensivePlayAction
) -> bool:
    return scheme is not None and play in matchup_for_scheme(scheme)[1]


@dataclass(frozen=True)
class FootballMatchupPower:
    offense: float
    defense: float
    scheme_matches_play: bool


@dataclass(frozen=True)
class FootballPlayEstimate:
    """Expected play result from the same matchup and risk model as resolution."""

    matchup: FootballMatchupPower
    family: FootballCardFamily
    yards_on_success: float
    yardage_spread: float
    incomplete_probability: float
    turnover_probability: float
    interception_return_yards: float = 0.0
    active_perks: frozenset[FootballCoachPerkKind] = frozenset()

    @property
    def expected_yards(self) -> float:
        if self.family is not FootballCardFamily.RB_RUN:
            return (
                self.yards_on_success
                * (1.0 - self.incomplete_probability)
                * (1.0 - self.turnover_probability)
            )
        lower = self.yards_on_success - self.yardage_spread
        upper = self.yards_on_success + self.yardage_spread
        if upper <= 0:
            fumble_yards = self.yards_on_success
        elif lower >= 0:
            fumble_yards = 0.0
        else:
            fumble_yards = -(lower * lower) / (4.0 * self.yardage_spread)
        return (
            self.yards_on_success * (1.0 - self.turnover_probability)
            + fumble_yards * self.turnover_probability
        )

    def first_down_probability(self, yards_to_go: float) -> float:
        if yards_to_go <= 0:
            raise ValueError("First-down distance must be positive.")
        if yards_to_go <= self.yards_on_success - self.yardage_spread:
            yardage_probability = 1.0
        elif yards_to_go >= self.yards_on_success + self.yardage_spread:
            yardage_probability = 0.0
        else:
            yardage_probability = (
                self.yards_on_success + self.yardage_spread - yards_to_go
            ) / (2 * self.yardage_spread)
        return yardage_probability * (
            1.0
            - self.incomplete_probability
            - (1.0 - self.incomplete_probability) * self.turnover_probability
        )


def _play_risk_probabilities(
    play: OffensivePlayAction,
    matchup: FootballMatchupPower,
    *,
    incomplete_bonus: float = 0.0,
    turnover_bonus: float = 0.0,
    interception_risk_reduction: float = 0.0,
) -> tuple[float, float]:
    power_total = max(1.0, matchup.offense + matchup.defense)
    defensive_edge = (matchup.defense - matchup.offense) / power_total
    family = OFFENSIVE_PLAY_FAMILIES[play]
    if family is not FootballCardFamily.RB_RUN:
        incomplete = (
            PASS_INCOMPLETE_BASE_PROBABILITY
            + defensive_edge * MATCHUP_INCOMPLETE_SENSITIVITY
            + (
                MATCHED_SCHEME_INCOMPLETE_BONUS
                if matchup.scheme_matches_play
                else 0.0
            )
            + incomplete_bonus
        )
        interception = (
            PASS_INTERCEPTION_PROBABILITIES[family]
            + defensive_edge * MATCHUP_TURNOVER_SENSITIVITY
            + (
                MATCHED_SCHEME_TURNOVER_BONUS
                if matchup.scheme_matches_play
                else 0.0
            )
            + turnover_bonus
        )
        incomplete = _clamp(incomplete, 0.12, 0.52)
        interception = _clamp(interception, 0.005, 0.10)
        interception = _clamp(
            interception
            * (1.0 - min(interception_risk_reduction, MAX_COACH_RISK_REDUCTION)),
            0.0,
            0.10,
        )
        return incomplete, interception
    fumble = (
        RUN_FUMBLE_PROBABILITIES[family]
        + defensive_edge * MATCHUP_TURNOVER_SENSITIVITY
        + (
            MATCHED_SCHEME_TURNOVER_BONUS
            if matchup.scheme_matches_play
            else 0.0
        )
        + turnover_bonus
    )
    return 0.0, _clamp(fumble, 0.003, 0.08)


def _active_play_perks(
    offense_roster: FootballRoster,
    defense_roster: FootballRoster,
    play: OffensivePlayAction,
    scheme: DefensiveSchemeAction,
    *,
    down: int,
    drive_events: tuple[FootballMatchEvent, ...],
    is_conversion: bool,
) -> tuple[float, float, float, float, frozenset[FootballCoachPerkKind]]:
    offense_coach, _ = coaches_for_assignment(offense_roster.coach_assignment)
    _, defense_coach = coaches_for_assignment(defense_roster.coach_assignment)
    offense_perk = offense_coach.perk if offense_coach is not None else None
    defense_perk = defense_coach.perk if defense_coach is not None else None
    family = OFFENSIVE_PLAY_CATALOG[play.value].family
    is_run = family is FootballCardFamily.RB_RUN
    active: set[FootballCoachPerkKind] = set()
    yardage_bonus = 0.0
    incomplete_bonus = 0.0
    turnover_bonus = 0.0
    interception_return_yards = 0.0

    if (
        is_run
        and offense_perk is not None
        and offense_perk.kind is FootballCoachPerkKind.FIRST_RUN_YARDS
        and not any(
            isinstance(event.action, OffensivePlayAction)
            and OFFENSIVE_PLAY_CATALOG[event.action.value].family
            is FootballCardFamily.RB_RUN
            for event in drive_events
        )
    ):
        active.add(offense_perk.kind)
        yardage_bonus += offense_perk.value
    if (
        not is_run
        and offense_perk is not None
        and offense_perk.kind is FootballCoachPerkKind.FIRST_COMPLETED_PASS_YARDS
        and not any(
            event.play_result is not None
            and isinstance(event.action, OffensivePlayAction)
            and OFFENSIVE_PLAY_CATALOG[event.action.value].family
            is not FootballCardFamily.RB_RUN
            and not event.play_result.incomplete
            and not event.play_result.turnover
            for event in drive_events
        )
    ):
        active.add(offense_perk.kind)
        yardage_bonus += offense_perk.value
    if (
        not is_run
        and not is_conversion
        and down == 1
        and offense_perk is not None
        and offense_perk.kind is FootballCoachPerkKind.FIRST_DOWN_PASS_YARDS
    ):
        active.add(offense_perk.kind)
        yardage_bonus += offense_perk.value
    if (
        is_run
        and DEFENSIVE_SCHEME_FAMILIES[scheme] is FootballCardFamily.RB_RUN
        and defense_perk is not None
        and defense_perk.kind is FootballCoachPerkKind.MATCHED_RUN_YARDS_REDUCTION
    ):
        active.add(defense_perk.kind)
        yardage_bonus -= defense_perk.value
    if (
        not is_conversion
        and down == 4
        and offense_perk is not None
        and offense_perk.kind is FootballCoachPerkKind.FOURTH_DOWN_PLAY_YARDS
    ):
        active.add(offense_perk.kind)
        yardage_bonus += offense_perk.value
    if (
        not is_run
        and defense_perk is not None
        and play in matchup_for_scheme(scheme)[1]
        and defense_perk.kind
        is FootballCoachPerkKind.MATCHED_PASS_INCOMPLETE_BONUS
    ):
        active.add(defense_perk.kind)
        incomplete_bonus += defense_perk.value
    if (
        not is_run
        and defense_perk is not None
        and play in matchup_for_scheme(scheme)[1]
        and defense_perk.kind
        is FootballCoachPerkKind.MATCHED_PASS_INTERCEPTION_BONUS
    ):
        active.add(defense_perk.kind)
        turnover_bonus += defense_perk.value
    if (
        not is_run
        and defense_perk is not None
        and defense_perk.kind is FootballCoachPerkKind.INTERCEPTION_RETURN_YARDS
    ):
        active.add(defense_perk.kind)
        interception_return_yards = defense_perk.value

    return (
        yardage_bonus,
        incomplete_bonus,
        turnover_bonus,
        interception_return_yards,
        frozenset(active),
    )


def calculate_play_estimate(
    offense_roster: FootballRoster,
    defense_roster: FootballRoster,
    play: OffensivePlayAction,
    scheme: DefensiveSchemeAction,
    *,
    prior_plays: int = 0,
    down: int = 1,
    drive_events: tuple[FootballMatchEvent, ...] = (),
    is_conversion: bool = False,
    yardage_bonus: float = 0.0,
    completion_bonus: float = 0.0,
    offense_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = (),
    defense_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = (),
) -> FootballPlayEstimate:
    if not isfinite(yardage_bonus) or not isfinite(completion_bonus):
        raise ValueError("Play bonuses must be finite numbers.")
    if any(
        not isinstance(upgrades, tuple)
        or any(
            not isinstance(upgrade, FootballCoachUpgradeEffect)
            for upgrade in upgrades
        )
        for upgrades in (offense_coach_upgrades, defense_coach_upgrades)
    ):
        raise ValueError("Play estimates require typed immutable coach upgrades.")
    matchup = calculate_matchup_power(
        offense_roster,
        defense_roster,
        play,
        scheme,
        prior_plays=prior_plays,
        offense_coach_upgrades=offense_coach_upgrades,
        defense_coach_upgrades=defense_coach_upgrades,
    )
    (
        contextual_yardage_bonus,
        incomplete_bonus,
        turnover_bonus,
        interception_return_yards,
        active_perks,
    ) = _active_play_perks(
        offense_roster,
        defense_roster,
        play,
        scheme,
        down=down,
        drive_events=drive_events,
        is_conversion=is_conversion,
    )
    offense_players = tuple(
        offense_roster.players[position]
        for position in OFFENSIVE_PLAY_CATALOG[play.value].contributors
    )
    defense_players = tuple(
        defense_roster.players[position]
        for position in DEFENSIVE_SCHEME_CATALOG[scheme.value].contributors
    )
    offense_volatility_reduction = min(
        MAX_COACH_VOLATILITY_REDUCTION,
        coach_upgrade_magnitude(
            offense_coach_upgrades,
            FootballCoachUpgradeKind.OFFENSE_VOLATILITY_REDUCTION,
        ),
    )
    defense_volatility_reduction = min(
        MAX_COACH_VOLATILITY_REDUCTION,
        coach_upgrade_magnitude(
            defense_coach_upgrades,
            FootballCoachUpgradeKind.DEFENSE_VOLATILITY_REDUCTION,
        ),
    )
    spread = max(
        MIN_PLAY_YARDAGE_SPREAD,
        (
            sum(player.volatility for player in offense_players)
            * (1.0 - offense_volatility_reduction)
            / len(offense_players)
            + sum(player.volatility for player in defense_players)
            * (1.0 - defense_volatility_reduction)
            / len(defense_players)
        )
        * VOLATILITY_SPREAD_MULTIPLIER,
    )
    offensive_family = OFFENSIVE_PLAY_CATALOG[play.value].family
    defensive_family = DEFENSIVE_SCHEME_FAMILIES[scheme]
    family_yardage_delta = coach_upgrade_magnitude(
        offense_coach_upgrades,
        FootballCoachUpgradeKind.OFFENSIVE_FAMILY_YARDAGE_DELTA,
        family=offensive_family,
    )
    if defensive_family is offensive_family:
        family_yardage_delta -= coach_upgrade_magnitude(
            defense_coach_upgrades,
            FootballCoachUpgradeKind.DEFENSIVE_FAMILY_YARDAGE_REDUCTION,
            family=offensive_family,
        )
    yards = (
        _BASE_YARDAGE[play]
        - PLAY_DEFENSE_BASELINE_YARDAGE_REDUCTION
        + OFFENSIVE_BASELINE_YARDAGE_BONUS
        + (
            RUN_BASELINE_YARDAGE_ADJUSTMENT
            if offensive_family is FootballCardFamily.RB_RUN
            else PASS_BASELINE_YARDAGE_ADJUSTMENT
        )
        + (matchup.offense - matchup.defense) * POWER_YARDAGE_MULTIPLIER
        - (
            MATCHED_SCHEME_YARDAGE_PENALTY
            if matchup.scheme_matches_play
            else 0.0
        )
        + yardage_bonus
        + completion_bonus
        + contextual_yardage_bonus
    )
    family_yardage_multiplier = _clamp(
        1.0 + (
            family_yardage_delta
            if yards >= 0.0
            else -family_yardage_delta
        ),
        1.0 - MAX_COACH_YARDAGE_DELTA,
        1.0 + MAX_COACH_YARDAGE_DELTA,
    )
    yards *= family_yardage_multiplier
    yards = _clamp(yards, MIN_PLAY_YARDAGE, MAX_PLAY_YARDAGE)
    interception_risk_reduction = coach_upgrade_magnitude(
        offense_coach_upgrades,
        FootballCoachUpgradeKind.INTERCEPTION_RISK_REDUCTION,
    )
    incomplete, conditional_turnover = _play_risk_probabilities(
        play,
        matchup,
        incomplete_bonus=incomplete_bonus,
        turnover_bonus=turnover_bonus,
        interception_risk_reduction=interception_risk_reduction,
    )
    return FootballPlayEstimate(
        matchup,
        OFFENSIVE_PLAY_CATALOG[play.value].family,
        yards,
        spread,
        incomplete,
        conditional_turnover,
        interception_return_yards,
        active_perks,
    )


@lru_cache(maxsize=None)
def calculate_standardized_play_estimate(
    play: OffensivePlayAction,
) -> FootballPlayEstimate:
    """Estimate a card against equal, rested, uncoached players and a non-counter."""
    if not isinstance(play, OffensivePlayAction):
        raise ValueError("Standardized play estimate requires an OffensivePlayAction.")

    def neutral_roster(name: str) -> FootballRoster:
        players = {
            position: FootballPlayer(
                name=f"{name} {position.value}",
                position=position,
                power=10.0,
                volatility=0.0,
                stamina=1.0,
            )
            for position in FootballPosition
        }
        return FootballRoster(
            team_name=name,
            players=players,
            coach=FootballCoach(f"{name} Coach"),
            special_teams=FootballSpecialTeams(f"{name} Special Teams"),
        )

    family = OFFENSIVE_PLAY_FAMILIES[play]
    scheme = next(
        scheme
        for scheme, scheme_family in DEFENSIVE_SCHEME_FAMILIES.items()
        if scheme_family is not family
    )
    return calculate_play_estimate(
        neutral_roster("Neutral Offense"),
        neutral_roster("Neutral Defense"),
        play,
        scheme,
        prior_plays=0,
        down=1,
    )


def _drive_events_for_state(
    state: FootballMatchState,
    possession: FootballTeamSide,
) -> tuple[FootballMatchEvent, ...]:
    for index in range(len(state.match_events) - 1, -1, -1):
        event = state.match_events[index]
        if (
            isinstance(event.action, DefensiveSchemeAction)
            and event.possession is possession
        ):
            return state.match_events[index + 1 :]
    return ()


def calculate_match_play_estimate(
    state: FootballMatchState,
    play: OffensivePlayAction,
    *,
    scheme: DefensiveSchemeAction | None = None,
    offense_side: FootballTeamSide | None = None,
    is_conversion: bool = False,
) -> FootballPlayEstimate:
    if not isinstance(state, FootballMatchState):
        raise ValueError("Play estimate requires a FootballMatchState.")
    if not isinstance(play, OffensivePlayAction):
        raise ValueError("Play estimate requires an offensive play.")
    side = offense_side or state.possession
    active_scheme = scheme or state.current_drive_defensive_scheme
    if active_scheme is None:
        raise ValueError("Play estimate requires a defensive scheme.")
    offense = state.team_a if side is FootballTeamSide.TEAM_A else state.team_b
    defense = state.team_b if side is FootballTeamSide.TEAM_A else state.team_a
    prior_plays = sum(
        event.play_result is not None for event in state.match_events
    )
    return calculate_play_estimate(
        offense,
        defense,
        play,
        active_scheme,
        prior_plays=prior_plays,
        down=state.down,
        drive_events=_drive_events_for_state(state, side),
        is_conversion=is_conversion,
        offense_coach_upgrades=(
            state.team_a_coach_upgrades
            if side is FootballTeamSide.TEAM_A
            else state.team_b_coach_upgrades
        ),
        defense_coach_upgrades=(
            state.team_b_coach_upgrades
            if side is FootballTeamSide.TEAM_A
            else state.team_a_coach_upgrades
        ),
    )


def _play_perk_effect_messages(
    estimate: FootballPlayEstimate,
    play: OffensivePlayAction,
    *,
    incomplete: bool,
    turnover: bool,
) -> tuple[str, ...]:
    active = estimate.active_perks
    effects: list[str] = []
    if FootballCoachPerkKind.MATCHED_PASS_INCOMPLETE_BONUS in active:
        effects.append("Coverage: +5 percentage points to incompletion chance")
    if FootballCoachPerkKind.MATCHED_PASS_INTERCEPTION_BONUS in active:
        effects.append("Pressure / Blitz: +5 percentage points to interception chance")
    if FootballCoachPerkKind.FIRST_RUN_YARDS in active:
        effects.append(
            "Ground and Pound: first run attempt used; turnover prevented the bonus"
            if turnover
            else "Ground and Pound: +3 yards on the first run"
        )
    if not incomplete and not turnover:
        if FootballCoachPerkKind.FIRST_COMPLETED_PASS_YARDS in active:
            effects.append("Air Raid: +3 yards on the first completed pass")
        if FootballCoachPerkKind.FIRST_DOWN_PASS_YARDS in active:
            effects.append("Pro Style: +2 yards on a first-down pass")
        if (
            estimate.family is FootballCardFamily.RB_RUN
            and FootballCoachPerkKind.MATCHED_RUN_YARDS_REDUCTION in active
        ):
            effects.append("Run Stop: -2 yards on RB Run vs. RB Run scheme")
        if FootballCoachPerkKind.FOURTH_DOWN_PLAY_YARDS in active:
            effects.append("Option / Spread: +1 yard on a fourth-down play")
    return tuple(effects)


def _adjusted_player_power(
    player: FootballPlayer,
    prior_plays: int,
    *,
    stamina_bonus: float = 0.0,
) -> float:
    ramp = min(prior_plays / FATIGUE_RAMP_PLAYS, 1.0)
    effective_stamina = min(
        1.0,
        player.stamina + min(stamina_bonus, MAX_COACH_STAMINA_BONUS),
    )
    reduction = ramp * MAX_FATIGUE_POWER_REDUCTION * (1.0 - effective_stamina)
    return player.power * (1.0 - reduction)


def calculate_matchup_power(
    offense_roster: FootballRoster,
    defense_roster: FootballRoster,
    play: OffensivePlayAction,
    scheme: DefensiveSchemeAction,
    *,
    prior_plays: int = 0,
    offense_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = (),
    defense_coach_upgrades: tuple[FootballCoachUpgradeEffect, ...] = (),
) -> FootballMatchupPower:
    if not isinstance(offense_roster, FootballRoster) or not isinstance(
        defense_roster, FootballRoster
    ):
        raise ValueError("Matchup power requires two football rosters.")
    if not isinstance(play, OffensivePlayAction):
        raise ValueError("Matchup power requires an offensive play.")
    if not isinstance(scheme, DefensiveSchemeAction):
        raise ValueError("Matchup power requires a defensive scheme.")
    if isinstance(prior_plays, bool) or not isinstance(prior_plays, int) or prior_plays < 0:
        raise ValueError("Prior plays must be a non-negative integer.")

    offense_positions = OFFENSIVE_PLAY_CATALOG[play.value].contributors
    defense_positions = DEFENSIVE_SCHEME_CATALOG[scheme.value].contributors
    offense_players = tuple(
        offense_roster.players[position] for position in offense_positions
    )
    defense_players = tuple(
        defense_roster.players[position] for position in defense_positions
    )
    offense_coach, _ = coaches_for_assignment(offense_roster.coach_assignment)
    _, defense_coach = coaches_for_assignment(defense_roster.coach_assignment)
    offense_stamina_bonus = coach_upgrade_magnitude(
        offense_coach_upgrades,
        FootballCoachUpgradeKind.OFFENSE_STAMINA_BOOST,
    )
    defense_stamina_bonus = coach_upgrade_magnitude(
        defense_coach_upgrades,
        FootballCoachUpgradeKind.DEFENSE_STAMINA_BOOST,
    )
    offense_power = sum(
        _adjusted_player_power(
            player,
            prior_plays,
            stamina_bonus=offense_stamina_bonus,
        )
        * player_contribution_modifier(
            player,
            offense_players,
            offense_coach.position_modifiers[player.position]
            if offense_coach is not None
            else 0.0,
        )
        for player in offense_players
    )
    defense_power = sum(
        _adjusted_player_power(
            player,
            prior_plays,
            stamina_bonus=defense_stamina_bonus,
        )
        * player_contribution_modifier(
            player,
            defense_players,
            defense_coach.position_modifiers[player.position]
            if defense_coach is not None
            else 0.0,
        )
        for player in defense_players
    )
    matches = _scheme_matches_play(scheme, play)
    if matches:
        defense_power *= MATCHED_SCHEME_DEFENSE_MULTIPLIER
        offense_power *= MATCHED_SCHEME_OFFENSE_MULTIPLIER
    offense_power *= 1.0 + min(
        MAX_COACH_POWER_BONUS,
        coach_upgrade_magnitude(
            offense_coach_upgrades,
            FootballCoachUpgradeKind.OFFENSE_POWER_BOOST,
        ),
    )
    defense_power *= 1.0 + min(
        MAX_COACH_POWER_BONUS,
        coach_upgrade_magnitude(
            defense_coach_upgrades,
            FootballCoachUpgradeKind.DEFENSE_POWER_BOOST,
        ),
    )
    return FootballMatchupPower(offense_power, defense_power, matches)


def _complete_match(state: FootballMatchState) -> FootballMatchState:
    if state.team_a_score == state.team_b_score:
        raise ValueError("A completed match cannot end in a tie.")
    winner = (
        FootballTeamSide.TEAM_A
        if state.team_a_score > state.team_b_score
        else FootballTeamSide.TEAM_B
    )
    return replace(
        state,
        status=FootballMatchStatus.COMPLETED,
        awaited_action=None,
        current_drive_defensive_scheme=None,
        final_result=FootballMatchResult(
            team_a_score=state.team_a_score,
            team_b_score=state.team_b_score,
            winner=winner,
            completed=True,
        ),
    )


def _advance_period_if_expired(
    state: FootballMatchState, rng: random.Random
) -> FootballMatchState:
    if (
        state.status is FootballMatchStatus.COMPLETED
        or state.game_clock_seconds > 0
        or state.awaited_action is FootballAwaitedAction.CONVERSION
    ):
        return state
    if state.period == 1:
        return replace(
            state,
            period=2,
            game_clock_seconds=REGULATION_PERIOD_SECONDS,
        )
    if state.period == 2 and state.team_a_score != state.team_b_score:
        return _complete_match(state)
    if state.period >= 2:
        return replace(
            state,
            period=state.period + 1,
            game_clock_seconds=OVERTIME_PERIOD_SECONDS,
            down=1,
            yards_to_go=FIRST_DOWN_YARDS,
            offense_field_position=TOUCHBACK_START_YARDS,
            possession=rng.choice((FootballTeamSide.TEAM_A, FootballTeamSide.TEAM_B)),
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            current_drive_defensive_scheme=None,
        )
    raise ValueError(f"Unsupported match period: {state.period}")


def _after_possession_change(
    state: FootballMatchState,
    *,
    possession: FootballTeamSide,
    field_position: float,
    clock_cost: int,
) -> FootballMatchState:
    field_position = _clamp(field_position, 0.0, GOAL_LINE_YARDS)
    if field_position == GOAL_LINE_YARDS:
        # A non-scoring drive cannot start on the goal line with positive yards to go.
        field_position = MAX_NONSCORING_RETURN_FIELD_POSITION
    return replace(
        state,
        possession=possession,
        down=1,
        yards_to_go=min(FIRST_DOWN_YARDS, _drive_yards_remaining(field_position)),
        offense_field_position=field_position,
        game_clock_seconds=max(0, state.game_clock_seconds - clock_cost),
        awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
        current_drive_defensive_scheme=None,
    )


def _record_event(
    state: FootballMatchState,
    *,
    action: (
        OffensivePlayAction
        | DefensiveSchemeAction
        | FootballFourthDownAction
        | FootballConversionAction
        | FootballAutomaticAction
    ),
    play_result: FootballPlayResult | None = None,
    points_scored: int = 0,
    scoring_team: FootballTeamSide | None = None,
    field_goal_distance: float | None = None,
    clock_seconds_used: int = 0,
    perk_effects: tuple[str, ...] = (),
    description: str | None = None,
    gross_yards: float | None = None,
    return_yards: float | None = None,
    blocked: bool = False,
    card_id: str | None = None,
    card_copy_id: str | None = None,
) -> FootballMatchState:
    event = FootballMatchEvent(
        sequence=len(state.match_events) + 1,
        action=action,
        team_a_score=state.team_a_score,
        team_b_score=state.team_b_score,
        possession=state.possession,
        offense_field_position=state.offense_field_position,
        down=state.down,
        yards_to_go=state.yards_to_go,
        game_clock_seconds=state.game_clock_seconds,
        period=state.period,
        status=state.status,
        clock_seconds_used=clock_seconds_used,
        play_result=play_result,
        points_scored=points_scored,
        scoring_team=scoring_team,
        field_goal_distance=field_goal_distance,
        perk_effects=perk_effects,
        description=description,
        gross_yards=gross_yards,
        return_yards=return_yards,
        blocked=blocked,
        card_id=card_id,
        card_copy_id=card_copy_id,
    )
    events = state.match_events + (event,)
    first = events[0]
    score_a = first.team_a_score - (
        first.points_scored if first.scoring_team is FootballTeamSide.TEAM_A else 0
    )
    score_b = first.team_b_score - (
        first.points_scored if first.scoring_team is FootballTeamSide.TEAM_B else 0
    )
    for recorded_event in events:
        score_a += (
            recorded_event.points_scored
            if recorded_event.scoring_team is FootballTeamSide.TEAM_A
            else 0
        )
        score_b += (
            recorded_event.points_scored
            if recorded_event.scoring_team is FootballTeamSide.TEAM_B
            else 0
        )
        if (recorded_event.team_a_score, recorded_event.team_b_score) != (
            score_a,
            score_b,
        ):
            raise ValueError("Match event scores do not reconcile with scoring events.")
    if (state.team_a_score, state.team_b_score) != (score_a, score_b):
        raise ValueError("Match state scores do not match the recorded event history.")
    return replace(state, match_events=events)


def _add_score(
    state: FootballMatchState, team: FootballTeamSide, points: int
) -> FootballMatchState:
    return replace(
        state,
        team_a_score=state.team_a_score + (points if team is FootballTeamSide.TEAM_A else 0),
        team_b_score=state.team_b_score + (points if team is FootballTeamSide.TEAM_B else 0),
    )


class FootballMatchSimulator:
    """Resolve caller-provided match actions against a persistent seeded RNG."""

    def __init__(self, match_state: FootballMatchState):
        if not isinstance(match_state, FootballMatchState):
            raise ValueError("Match state must be a FootballMatchState.")
        if (
            match_state.status is FootballMatchStatus.IN_PROGRESS
            and match_state.game_clock_seconds == 0
        ):
            raise ValueError("An in-progress match cannot start with an expired period clock.")
        if (
            match_state.status is FootballMatchStatus.IN_PROGRESS
            and match_state.period >= 3
            and match_state.team_a_score != match_state.team_b_score
        ):
            raise ValueError("An in-progress overtime match must start tied.")
        self.state = match_state
        self.rng = random.Random(match_state.random_seed)
        self._deck_rngs = {
            "team_a_offense": random.Random(match_state.random_seed ^ 0xA110),
            "team_a_defense": random.Random(match_state.random_seed ^ 0xA120),
            "team_b_offense": random.Random(match_state.random_seed ^ 0xB110),
            "team_b_defense": random.Random(match_state.random_seed ^ 0xB120),
        }
        self._initialize_decks()

    def _initialize_decks(self) -> None:
        changes: dict[str, FootballDeckState] = {}
        for side in FootballTeamSide:
            for offensive in (True, False):
                group = "offense" if offensive else "defense"
                field_name = f"{side.value}_{group}_deck"
                deck = getattr(self.state, field_name)
                if deck is None:
                    owned = (
                        starting_offensive_deck(side.value)
                        if offensive
                        else starting_defensive_deck(side.value)
                    )
                    deck = FootballDeckState(owned)
                catalog = (
                    OFFENSIVE_PLAY_CATALOG
                    if offensive
                    else DEFENSIVE_SCHEME_CATALOG
                )
                if any(card.card_id not in catalog for card in deck.owned):
                    raise ValueError(f"{group.title()} deck contains an unknown card.")
                if not (deck.draw_pile or deck.hand or deck.discard_pile):
                    deck = self._deal_deck(
                        deck.owned,
                        self._deck_rngs[f"{side.value}_{group}"],
                        3 if offensive else 2,
                    )
                changes[field_name] = deck
        if any(getattr(self.state, field) != deck for field, deck in changes.items()):
            self.state = replace(self.state, **changes)

    @staticmethod
    def _deck_field(side: FootballTeamSide, *, offensive: bool) -> str:
        return f"{side.value}_{'offense' if offensive else 'defense'}_deck"

    def _deck_for(
        self, side: FootballTeamSide, *, offensive: bool
    ) -> FootballDeckState:
        deck = getattr(self.state, self._deck_field(side, offensive=offensive))
        if not isinstance(deck, FootballDeckState):
            raise RuntimeError("The match deck was not initialized.")
        return deck

    def _set_deck(
        self,
        side: FootballTeamSide,
        *,
        offensive: bool,
        deck: FootballDeckState,
    ) -> None:
        self.state = replace(
            self.state,
            **{self._deck_field(side, offensive=offensive): deck},
        )

    @staticmethod
    def _deal_deck(
        owned: tuple[FootballCardCopy, ...],
        rng: random.Random,
        hand_size: int,
    ) -> FootballDeckState:
        cards = list(owned)
        rng.shuffle(cards)
        hand = tuple(cards[:hand_size])
        return FootballDeckState(
            owned=owned,
            draw_pile=tuple(cards[hand_size:]),
            hand=hand,
        )

    def _select_offensive_card(
        self, selection: OffensivePlayAction | str | None
    ) -> tuple[OffensivePlayAction, FootballCardCopy | None]:
        deck = self._deck_for(self.state.possession, offensive=True)
        selected: FootballCardCopy | None = None
        action: OffensivePlayAction | None = None
        if isinstance(selection, OffensivePlayAction):
            action = selection
            selected = next(
                (
                    card
                    for card in deck.hand
                    if OFFENSIVE_PLAY_CATALOG[card.card_id].action is action
                ),
                None,
            )
            if selected is None and deck.hand:
                raise ValueError("Offensive play is not available in the current hand.")
        elif isinstance(selection, str):
            selected = next(
                (card for card in deck.hand if card.copy_id == selection),
                None,
            )
            if selected is None:
                raise ValueError("Offensive card is not in the current hand.")
            action = OFFENSIVE_PLAY_CATALOG[selected.card_id].action
        elif selection is not None:
            raise ValueError("Offensive selection must be a card id, play, or None.")

        if selected is None:
            if deck.hand:
                raise ValueError("The fallback is available only when the hand is empty.")
            if action not in (None, OffensivePlayAction.RB_RUN):
                raise ValueError("The empty-hand fallback is the basic inside run.")
            return OffensivePlayAction.RB_RUN, None
        return action, selected

    def _select_scheme_card(
        self, selection: DefensiveSchemeAction | str | None
    ) -> tuple[DefensiveSchemeAction, FootballCardCopy | None]:
        side = _opponent(self.state.possession)
        deck = self._deck_for(side, offensive=False)
        selected: FootballCardCopy | None = None
        action: DefensiveSchemeAction | None = None
        if isinstance(selection, DefensiveSchemeAction):
            action = selection
            selected = next(
                (
                    card
                    for card in deck.hand
                    if DEFENSIVE_SCHEME_CATALOG[card.card_id].action is action
                ),
                None,
            )
            if selected is None and deck.hand:
                raise ValueError("Defensive scheme is not available in the current hand.")
        elif isinstance(selection, str):
            selected = next(
                (card for card in deck.hand if card.copy_id == selection),
                None,
            )
            if selected is None:
                raise ValueError("Defensive card is not in the current hand.")
            action = DEFENSIVE_SCHEME_CATALOG[selected.card_id].action
        elif selection is not None:
            raise ValueError("Defensive selection must be a card id, scheme, or None.")

        if selected is None:
            if deck.hand:
                raise ValueError("The fallback is available only when the hand is empty.")
            if action not in (None, DefensiveSchemeAction.RB_RUN):
                raise ValueError("The empty-hand fallback is the basic run-fit scheme.")
            return DefensiveSchemeAction.RB_RUN, None
        return action, selected

    def _cycle_played_card(
        self,
        side: FootballTeamSide,
        *,
        offensive: bool,
        card: FootballCardCopy | None,
    ) -> None:
        deck = self._deck_for(side, offensive=offensive)
        hand = list(deck.hand)
        discard = list(deck.discard_pile)
        if card is not None:
            hand.remove(card)
            discard.append(card)
        rng = self._deck_rngs[
            f"{side.value}_{'offense' if offensive else 'defense'}"
        ]
        draw_pile = list(deck.draw_pile)
        if not draw_pile and discard:
            rng.shuffle(discard)
            draw_pile, discard = discard, []
        if draw_pile:
            hand.append(draw_pile.pop(0))
        self._set_deck(
            side,
            offensive=offensive,
            deck=FootballDeckState(
                owned=deck.owned,
                draw_pile=tuple(draw_pile),
                hand=tuple(hand),
                discard_pile=tuple(discard),
            ),
        )

    def _finish_play_action(
        self,
        state: FootballMatchState,
        offensive_side: FootballTeamSide,
        card: FootballCardCopy | None,
        *,
        previous_period: int,
    ) -> FootballMatchState:
        self.state = state
        self._cycle_played_card(offensive_side, offensive=True, card=card)
        self._reset_for_period_boundary(previous_period)
        return self.state

    def _reset_for_period_boundary(self, previous_period: int) -> None:
        reset_at_boundary = (previous_period == 1 and self.state.period == 2) or (
            previous_period == 2 and self.state.period == 3
        )
        if reset_at_boundary:
            self._reset_all_decks()

    def _reset_all_decks(self) -> None:
        changes: dict[str, FootballDeckState] = {}
        for side in FootballTeamSide:
            for offensive in (True, False):
                group = "offense" if offensive else "defense"
                field_name = self._deck_field(side, offensive=offensive)
                current = getattr(self.state, field_name)
                if not isinstance(current, FootballDeckState):
                    raise RuntimeError("The match deck was not initialized.")
                changes[field_name] = self._deal_deck(
                    current.owned,
                    self._deck_rngs[f"{side.value}_{group}"],
                    3 if offensive else 2,
                )
        self.state = replace(self.state, **changes)

    def _require_action(self, expected: FootballAwaitedAction) -> None:
        if self.state.status is FootballMatchStatus.COMPLETED:
            raise ValueError("A completed match cannot accept new actions.")
        if self.state.awaited_action is not expected:
            raise ValueError(f"Action is not legal while awaiting {self.state.awaited_action!r}.")
        if (
            self.state.game_clock_seconds == 0
            and expected is not FootballAwaitedAction.CONVERSION
        ):
            raise ValueError("No action is legal after the period clock has expired.")

    def select_defensive_scheme(
        self, scheme: DefensiveSchemeAction | str | None
    ) -> FootballMatchState:
        if self.state.current_drive_defensive_scheme is not None:
            raise ValueError("A defensive scheme cannot be replaced mid-drive.")
        self._require_action(FootballAwaitedAction.DEFENSIVE_SCHEME)
        selected_scheme, selected_card = self._select_scheme_card(scheme)
        updated = replace(
            self.state,
            current_drive_defensive_scheme=selected_scheme,
            awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY,
        )
        self.state = _record_event(
            updated,
            action=selected_scheme,
            card_id=selected_scheme.value,
            card_copy_id=(
                selected_card.copy_id if selected_card is not None else None
            ),
        )
        self._cycle_played_card(
            _opponent(self.state.possession),
            offensive=False,
            card=selected_card,
        )
        return self.state

    def _current_drive_events(
        self, possession: FootballTeamSide
    ) -> tuple[FootballMatchEvent, ...]:
        return _drive_events_for_state(self.state, possession)

    def resolve_offensive_play(
        self, play: OffensivePlayAction | str | None
    ) -> FootballMatchState:
        self._require_action(FootballAwaitedAction.OFFENSIVE_PLAY)
        scheme = self.state.current_drive_defensive_scheme
        if scheme is None:
            raise ValueError("A defensive scheme must be chosen before the snap.")
        previous_period = self.state.period
        offensive_side = self.state.possession
        play, selected_card = self._select_offensive_card(play)

        play_definition = OFFENSIVE_PLAY_CATALOG[play.value]
        estimate = calculate_match_play_estimate(
            self.state,
            play,
            scheme=scheme,
        )
        offense_power = estimate.matchup.offense
        defense_power = estimate.matchup.defense
        yards = estimate.yards_on_success + self.rng.uniform(
            -estimate.yardage_spread,
            estimate.yardage_spread,
        )
        turnover = False
        incomplete = False
        turnover_type: FootballTurnoverType | None = None
        if play_definition.family is not FootballCardFamily.RB_RUN:
            roll = self.rng.random()
            interception_threshold = (
                estimate.incomplete_probability
                + (1.0 - estimate.incomplete_probability)
                * estimate.turnover_probability
            )
            if roll < estimate.incomplete_probability:
                incomplete = True
                yards = 0.0
            elif roll < interception_threshold:
                turnover = True
                turnover_type = FootballTurnoverType.INTERCEPTION
                yards = 0.0
        elif self.rng.random() < estimate.turnover_probability:
            turnover = True
            turnover_type = FootballTurnoverType.FUMBLE
            yards = min(yards, 0.0)

        perk_effects = list(_play_perk_effect_messages(
            estimate,
            play,
            incomplete=incomplete,
            turnover=turnover,
        ))

        clock_cost = (
            INCOMPLETE_PASS_CLOCK_SECONDS
            if incomplete
            else adjusted_offensive_play_clock_seconds(
                play_definition.clock_seconds,
                (
                    self.state.team_a_coach_upgrades
                    if offensive_side is FootballTeamSide.TEAM_A
                    else self.state.team_b_coach_upgrades
                ),
            )
        )
        positive_gain = yards > 0
        if positive_gain:
            yards = min(yards, _drive_yards_remaining(self.state.offense_field_position))
        new_position = self.state.offense_field_position + yards
        if new_position <= 0 and yards < 0:
            scoring_team = _opponent(self.state.possession)
            scored = _add_score(self.state, scoring_team, SAFETY_POINTS)
            next_state = _after_possession_change(
                scored,
                possession=scoring_team,
                field_position=TOUCHBACK_START_YARDS,
                clock_cost=clock_cost,
            )
            next_state = self._finish_action(next_state, points=SAFETY_POINTS)
            result = FootballPlayResult(
                play,
                yards,
                min(self.state.game_clock_seconds, clock_cost),
                points_scored=SAFETY_POINTS,
                turnover=turnover,
                possession_changed=True,
                defensive_scheme=scheme,
                incomplete=incomplete,
                offense_power=offense_power,
                defense_power=defense_power,
                perk_effects=tuple(perk_effects),
                turnover_type=turnover_type,
            )
            self.state = _record_event(
                next_state,
                action=play,
                play_result=result,
                points_scored=SAFETY_POINTS,
                scoring_team=scoring_team,
                clock_seconds_used=result.clock_seconds_used,
                perk_effects=result.perk_effects,
                card_id=play.value,
                card_copy_id=(
                    selected_card.copy_id if selected_card is not None else None
                ),
            )
            self.state = self._resolve_kickoff(
                self.state,
                offensive_side,
            )
            return self._finish_play_action(
                self.state,
                offensive_side,
                selected_card,
                previous_period=previous_period,
            )

        if new_position >= GOAL_LINE_YARDS and positive_gain:
            scoring_team = self.state.possession
            scored = _add_score(self.state, scoring_team, TOUCHDOWN_POINTS)
            next_state = self._conversion_state(
                replace(
                    scored,
                    game_clock_seconds=max(
                        0, self.state.game_clock_seconds - clock_cost
                    ),
                ),
                scoring_team,
                scheme,
            )
            result = FootballPlayResult(
                play,
                yards,
                min(self.state.game_clock_seconds, clock_cost),
                points_scored=TOUCHDOWN_POINTS,
                turnover=False,
                possession_changed=True,
                defensive_scheme=scheme,
                incomplete=incomplete,
                offense_power=offense_power,
                defense_power=defense_power,
                perk_effects=tuple(perk_effects),
            )
            self.state = _record_event(
                next_state,
                action=play,
                play_result=result,
                points_scored=TOUCHDOWN_POINTS,
                scoring_team=scoring_team,
                clock_seconds_used=result.clock_seconds_used,
                perk_effects=result.perk_effects,
                card_id=play.value,
                card_copy_id=(
                    selected_card.copy_id if selected_card is not None else None
                ),
            )
            return self._finish_play_action(
                self.state,
                offensive_side,
                selected_card,
                previous_period=previous_period,
            )

        turnover_on_downs = False
        points_scored = 0
        scoring_team: FootballTeamSide | None = None
        if turnover:
            return_yards = (
                estimate.interception_return_yards
                if play in _PASS_PLAYS
                else 0.0
            )
            if return_yards:
                perk_effects.append("Ball-Hawk: +10 interception return yards")
            return_field_position = 100.0 - new_position + return_yards
            if return_yards and return_field_position >= GOAL_LINE_YARDS:
                scoring_team = _opponent(self.state.possession)
                points_scored = TOUCHDOWN_POINTS
                scored = _add_score(self.state, scoring_team, points_scored)
                next_state = self._conversion_state(
                    replace(
                        scored,
                        game_clock_seconds=max(
                            0, self.state.game_clock_seconds - clock_cost
                        ),
                    ),
                    scoring_team,
                    scheme,
                )
            else:
                next_state = _after_possession_change(
                    self.state,
                    possession=_opponent(self.state.possession),
                    field_position=return_field_position,
                    clock_cost=clock_cost,
                )
        else:
            line_to_gain = min(
                self.state.yards_to_go,
                _drive_yards_remaining(self.state.offense_field_position),
            )
            line_to_gain = max(0.1, line_to_gain)
            first_down = yards >= line_to_gain
            remaining_goal_distance = _drive_yards_remaining(new_position)
            if first_down:
                next_down = 1
                next_yards_to_go = min(FIRST_DOWN_YARDS, remaining_goal_distance)
                if next_yards_to_go <= 0:
                    next_yards_to_go = FIRST_DOWN_YARDS
                awaited = FootballAwaitedAction.OFFENSIVE_PLAY
                next_state = replace(
                    self.state,
                    down=next_down,
                    yards_to_go=next_yards_to_go,
                    offense_field_position=new_position,
                    game_clock_seconds=max(0, self.state.game_clock_seconds - clock_cost),
                    awaited_action=awaited,
                )
            elif self.state.down == 4:
                turnover_on_downs = True
                next_state = _after_possession_change(
                    self.state,
                    possession=_opponent(self.state.possession),
                    field_position=100.0 - new_position,
                    clock_cost=clock_cost,
                )
            else:
                next_down = min(self.state.down + 1, 4)
                next_yards_to_go = max(0.1, line_to_gain - yards)
                awaited = (
                    FootballAwaitedAction.FOURTH_DOWN_DECISION
                    if next_down == 4
                    else FootballAwaitedAction.OFFENSIVE_PLAY
                )
                next_state = replace(
                    self.state,
                    down=next_down,
                    yards_to_go=next_yards_to_go,
                    offense_field_position=new_position,
                    game_clock_seconds=max(0, self.state.game_clock_seconds - clock_cost),
                    awaited_action=awaited,
                )

        result = FootballPlayResult(
            offensive_play=play,
            yards_gained=yards,
            clock_seconds_used=min(self.state.game_clock_seconds, clock_cost),
            points_scored=points_scored,
            turnover=turnover,
            possession_changed=turnover or turnover_on_downs,
            defensive_scheme=scheme,
            incomplete=incomplete,
            offense_power=offense_power,
            defense_power=defense_power,
            perk_effects=tuple(perk_effects),
            turnover_on_downs=turnover_on_downs,
            turnover_type=turnover_type,
        )
        if not points_scored:
            next_state = self._finish_action(next_state)
        self.state = _record_event(
            next_state,
            action=play,
            play_result=result,
            points_scored=points_scored,
            scoring_team=scoring_team,
            clock_seconds_used=result.clock_seconds_used,
            perk_effects=result.perk_effects,
            card_id=play.value,
            card_copy_id=(
                selected_card.copy_id if selected_card is not None else None
            ),
        )
        return self._finish_play_action(
            self.state,
            offensive_side,
            selected_card,
            previous_period=previous_period,
        )

    def _finish_action(
        self,
        state: FootballMatchState,
        *,
        points: int = 0,
    ) -> FootballMatchState:
        if (
            points
            and state.period >= 3
            and state.awaited_action is not FootballAwaitedAction.CONVERSION
        ):
            return _complete_match(state)
        return _advance_period_if_expired(state, self.rng)

    @staticmethod
    def _conversion_state(
        state: FootballMatchState,
        team: FootballTeamSide,
        defensive_scheme: DefensiveSchemeAction,
    ) -> FootballMatchState:
        return replace(
            state,
            possession=team,
            down=1,
            yards_to_go=2.0,
            offense_field_position=98.0,
            awaited_action=FootballAwaitedAction.CONVERSION,
            current_drive_defensive_scheme=defensive_scheme,
            conversion_team=team,
        )

    def _resolve_kickoff(
        self,
        state: FootballMatchState,
        kicking_team: FootballTeamSide,
        *,
        clock_seconds_used: int = KICKOFF_CLOCK_SECONDS,
    ) -> FootballMatchState:
        if state.status is FootballMatchStatus.COMPLETED or state.period >= 3:
            return state
        clock_seconds_used = min(state.game_clock_seconds, clock_seconds_used)
        receiving_team = _opponent(kicking_team)
        if self.rng.random() < KICKOFF_TOUCHBACK_CHANCE:
            return_yards = 0.0
            field_position = TOUCHBACK_START_YARDS
            description = "Kickoff touchback"
            return_touchdown = False
        else:
            receiving_upgrades = (
                state.team_a_coach_upgrades
                if receiving_team is FootballTeamSide.TEAM_A
                else state.team_b_coach_upgrades
            )
            return_bonus = coach_upgrade_magnitude(
                receiving_upgrades,
                FootballCoachUpgradeKind.KICKOFF_RETURN_YARDS_BONUS,
            )
            return_yards = _clamp(
                self.rng.gauss(
                    KICKOFF_RETURN_MEAN_YARDS,
                    KICKOFF_RETURN_STANDARD_DEVIATION,
                ) + return_bonus,
                0.0,
                100.0,
            )
            return_touchdown = (
                self.rng.random() < KICKOFF_RETURN_TOUCHDOWN_CHANCE
            )
            if not return_touchdown:
                return_yards = min(
                    return_yards,
                    MAX_NONSCORING_RETURN_FIELD_POSITION,
                )
            field_position = 100.0 if return_touchdown else return_yards
            description = (
                "Kickoff return touchdown"
                if return_touchdown
                else f"Kickoff returned {return_yards:.1f} yards"
            )
        if return_touchdown:
            state = _add_score(state, receiving_team, TOUCHDOWN_POINTS)
            state = self._conversion_state(
                state,
                receiving_team,
                DefensiveSchemeAction.GOAL_LINE_FRONT,
            )
            state = replace(
                state,
                game_clock_seconds=max(
                    0, state.game_clock_seconds - clock_seconds_used
                ),
            )
        else:
            state = _after_possession_change(
                state,
                possession=receiving_team,
                field_position=field_position,
                clock_cost=clock_seconds_used,
            )
            state = replace(state, conversion_team=None)
        state = _advance_period_if_expired(state, self.rng)
        return _record_event(
            state,
            action=FootballAutomaticAction.KICKOFF,
            points_scored=TOUCHDOWN_POINTS if return_touchdown else 0,
            scoring_team=receiving_team if return_touchdown else None,
            clock_seconds_used=clock_seconds_used,
            description=description,
            gross_yards=KICKOFF_GROSS_YARDS,
            return_yards=return_yards,
        )

    def _resolve_blocked_kick(
        self, state: FootballMatchState, *, clock_cost: int
    ) -> tuple[
        FootballMatchState,
        float,
        int,
        FootballTeamSide | None,
        str,
    ]:
        kicking_team = state.possession
        return_team = _opponent(kicking_team)
        if self.rng.random() >= BLOCKED_KICK_RECOVERY_CHANCE:
            setback = max(
                0.0,
                self.rng.gauss(
                    BLOCKED_KICK_OWN_RECOVERY_MEAN_YARDS,
                    BLOCKED_KICK_OWN_RECOVERY_STANDARD_DEVIATION,
                ),
            )
            recovery_position = max(1.0, state.offense_field_position - setback)
            state = _after_possession_change(
                state,
                possession=return_team,
                field_position=100.0 - recovery_position,
                clock_cost=clock_cost,
            )
            return (
                state,
                0.0,
                0,
                None,
                "Blocked kick recovered by kicking team; turnover on downs",
            )

        starting_position = 100.0 - state.offense_field_position
        return_yards = _clamp(
            self.rng.gauss(
                BLOCKED_KICK_RETURN_MEAN_YARDS,
                BLOCKED_KICK_RETURN_STANDARD_DEVIATION,
            ),
            0.0,
            100.0 - starting_position,
        )
        return_position = starting_position + return_yards
        if return_position >= GOAL_LINE_YARDS:
            state = _add_score(state, return_team, TOUCHDOWN_POINTS)
            state = self._conversion_state(
                state,
                return_team,
                DefensiveSchemeAction.GOAL_LINE_FRONT,
            )
            state = replace(
                state,
                game_clock_seconds=max(0, state.game_clock_seconds - clock_cost),
            )
            return (
                state,
                return_yards,
                TOUCHDOWN_POINTS,
                return_team,
                "Blocked kick returned for a touchdown",
            )
        state = _after_possession_change(
            state,
            possession=return_team,
            field_position=return_position,
            clock_cost=clock_cost,
        )
        return (
            state,
            return_yards,
            0,
            None,
            f"Blocked kick recovered and returned {return_yards:.1f} yards",
        )

    def _finish_scoring_sequence(
        self,
        state: FootballMatchState,
        *,
        kickoff_team: FootballTeamSide,
        previous_period: int,
    ) -> FootballMatchState:
        self.state = state
        if state.status is FootballMatchStatus.IN_PROGRESS and state.period < 3:
            state = self._resolve_kickoff(state, kickoff_team)
            self.state = state
        self._reset_for_period_boundary(previous_period)
        return self.state

    def resolve_conversion(
        self,
        action: FootballConversionAction,
        play: OffensivePlayAction | str | None = None,
    ) -> FootballMatchState:
        if not isinstance(action, FootballConversionAction):
            raise ValueError("Conversion choice must be a FootballConversionAction.")
        if action is FootballConversionAction.EXTRA_POINT and play is not None:
            raise ValueError("An extra-point attempt cannot select an offensive card.")
        self._require_action(FootballAwaitedAction.CONVERSION)
        team = self.state.conversion_team
        scheme = self.state.current_drive_defensive_scheme
        if team is None or scheme is None:
            raise RuntimeError("The conversion state is missing its team or defense.")
        previous_period = self.state.period
        scoring_team: FootballTeamSide | None = None
        points = 0
        blocked = False
        gross_yards: float | None = None
        perk_effects: tuple[str, ...] = ()
        description: str
        selected_play: OffensivePlayAction | None = None
        selected_card: FootballCardCopy | None = None

        if action is FootballConversionAction.EXTRA_POINT:
            blocked = self.rng.random() < EXTRA_POINT_BLOCK_CHANCE
            if blocked:
                description = "Extra point blocked"
                if self.rng.random() < TWO_POINT_RETURN_TOUCHDOWN_CHANCE:
                    scoring_team = _opponent(team)
                    points = 2
                    description = "Blocked extra point returned for two"
            elif self.rng.random() < EXTRA_POINT_SUCCESS_CHANCE:
                scoring_team = team
                points = 1
                description = "Extra point good"
            else:
                description = "Extra point missed"
        else:
            play, selected_card = self._select_offensive_card(play)
            selected_play = play
            estimate = calculate_match_play_estimate(
                self.state,
                play,
                scheme=scheme,
                is_conversion=True,
            )
            gross_yards = max(
                0.0,
                estimate.yards_on_success
                + self.rng.uniform(
                    -estimate.yardage_spread,
                    estimate.yardage_spread,
                ),
            )
            incomplete = False
            turnover = False
            if play in _PASS_PLAYS:
                roll = self.rng.random()
                incomplete = roll < estimate.incomplete_probability
                turnover = (
                    not incomplete
                    and roll
                    < estimate.incomplete_probability
                    + (1.0 - estimate.incomplete_probability)
                    * estimate.turnover_probability
                )
            else:
                turnover = self.rng.random() < estimate.turnover_probability
            if turnover and self.rng.random() < TWO_POINT_RETURN_TOUCHDOWN_CHANCE:
                scoring_team = _opponent(team)
                points = 2
                description = "Two-point attempt returned for two"
            elif not incomplete and not turnover and gross_yards >= 2.0:
                scoring_team = team
                points = 2
                description = f"Two-point {play.value.replace('_', ' ')} successful"
            else:
                result = (
                    "intercepted"
                    if turnover and play in _PASS_PLAYS
                    else "fumbled"
                    if turnover
                    else "incomplete"
                    if incomplete
                    else f"stopped at {gross_yards:.1f} yards"
                )
                description = (
                    f"Two-point {play.value.replace('_', ' ')} {result}"
                )
            perk_effects = _play_perk_effect_messages(
                estimate,
                play,
                incomplete=incomplete,
                turnover=turnover,
            )
            if selected_card is not None:
                self._cycle_played_card(team, offensive=True, card=selected_card)

        state = self.state
        if points:
            if scoring_team is None:
                raise RuntimeError("A successful conversion must identify its scorer.")
            state = _add_score(state, scoring_team, points)
        state = replace(
            state,
            down=1,
            yards_to_go=FIRST_DOWN_YARDS,
            offense_field_position=TOUCHBACK_START_YARDS,
            awaited_action=FootballAwaitedAction.DEFENSIVE_SCHEME,
            current_drive_defensive_scheme=None,
            conversion_team=None,
        )
        if state.period >= 3 and state.team_a_score != state.team_b_score:
            state = _complete_match(state)
        else:
            state = _advance_period_if_expired(state, self.rng)
        self.state = _record_event(
            state,
            action=action,
            points_scored=points,
            scoring_team=scoring_team,
            description=description,
            gross_yards=gross_yards,
            blocked=blocked,
            clock_seconds_used=0,
            perk_effects=perk_effects,
            card_id=selected_play.value if selected_play is not None else None,
            card_copy_id=(
                selected_card.copy_id if selected_card is not None else None
            ),
        )
        if self.state.status is FootballMatchStatus.COMPLETED:
            return self.state
        return self._finish_scoring_sequence(
            self.state,
            kickoff_team=team,
            previous_period=previous_period,
        )

    def resolve_fourth_down(
        self, decision: FootballFourthDownAction
    ) -> FootballMatchState:
        if not isinstance(decision, FootballFourthDownAction):
            raise ValueError("Fourth-down decision must be a FootballFourthDownAction.")
        self._require_action(FootballAwaitedAction.FOURTH_DOWN_DECISION)
        if self.state.down != 4:
            raise ValueError("Fourth-down decisions are only legal on fourth down.")

        previous_period = self.state.period
        state = self.state
        points = 0
        scoring_team: FootballTeamSide | None = None
        distance: float | None = None
        clock_cost = 0
        gross_yards: float | None = None
        return_yards: float | None = None
        description: str | None = None
        blocked = False
        if decision is FootballFourthDownAction.GO_FOR_IT:
            self.state = _record_event(
                replace(state, awaited_action=FootballAwaitedAction.OFFENSIVE_PLAY),
                action=decision,
            )
            return self.state
        elif decision is FootballFourthDownAction.PUNT:
            clock_cost = PUNT_CLOCK_SECONDS
            blocked = self.rng.random() < blocked_kick_probability(
                state, state.possession, PUNT_BLOCK_CHANCE
            )
            if blocked:
                gross_yards = 0.0
                (
                    state,
                    return_yards,
                    points,
                    scoring_team,
                    description,
                ) = self._resolve_blocked_kick(state, clock_cost=clock_cost)
            else:
                gross_yards = _clamp(
                    self.rng.gauss(
                        PUNT_GROSS_MEAN_YARDS,
                        PUNT_GROSS_STANDARD_DEVIATION,
                    ),
                    15.0,
                    70.0,
                )
                return_yards = (
                    _clamp(
                        self.rng.gauss(
                            PUNT_RETURN_MEAN_YARDS,
                            PUNT_RETURN_STANDARD_DEVIATION,
                        )
                        + coach_upgrade_magnitude(
                            (
                                state.team_a_coach_upgrades
                                if _opponent(state.possession)
                                is FootballTeamSide.TEAM_A
                                else state.team_b_coach_upgrades
                            ),
                            FootballCoachUpgradeKind.PUNT_RETURN_YARDS_BONUS,
                        ),
                        0.0,
                        40.0,
                    )
                    if self.rng.random() < PUNT_RETURN_CHANCE
                    else 0.0
                )
                max_non_scoring_return = max(
                    0.0,
                    state.offense_field_position
                    + gross_yards
                    - (GOAL_LINE_YARDS - MAX_NONSCORING_RETURN_FIELD_POSITION),
                )
                return_yards = min(return_yards, max_non_scoring_return)
                punt_end_position = (
                    state.offense_field_position + gross_yards - return_yards
                )
                touchback = punt_end_position >= GOAL_LINE_YARDS
                receiving_position = (
                    TOUCHBACK_START_YARDS
                    if touchback
                    else 100.0 - punt_end_position
                )
                description = (
                    "Punt touchback"
                    if touchback
                    else f"Punt {gross_yards:.1f} yards, returned {return_yards:.1f}"
                )
                state = _after_possession_change(
                    state,
                    possession=_opponent(state.possession),
                    field_position=_clamp(receiving_position, 0.0, GOAL_LINE_YARDS),
                    clock_cost=clock_cost,
                )
        elif decision is FootballFourthDownAction.FIELD_GOAL:
            clock_cost = FIELD_GOAL_CLOCK_SECONDS
            distance = field_goal_distance_for_position(state.offense_field_position)
            blocked = self.rng.random() < blocked_kick_probability(
                state, state.possession, FIELD_GOAL_BLOCK_CHANCE
            )
            made = (
                not blocked
                and self.rng.random()
                < field_goal_success_probability_for_team(
                    state, state.possession, distance
                )
            )
            if blocked:
                (
                    state,
                    return_yards,
                    points,
                    scoring_team,
                    description,
                ) = self._resolve_blocked_kick(state, clock_cost=clock_cost)
            elif made:
                description = f"Field goal good from {distance:.0f} yards"
                scoring_team = state.possession
                points = FIELD_GOAL_POINTS
                state = _add_score(state, scoring_team, points)
                state = _after_possession_change(
                    state,
                    possession=_opponent(scoring_team),
                    field_position=TOUCHBACK_START_YARDS,
                    clock_cost=clock_cost,
                )
            else:
                description = f"Field goal missed from {distance:.0f} yards"
                state = _after_possession_change(
                    state,
                    possession=_opponent(state.possession),
                    field_position=100.0 - state.offense_field_position,
                    clock_cost=clock_cost,
                )

        if (
            points
            and state.period >= 3
            and state.awaited_action is not FootballAwaitedAction.CONVERSION
        ):
            state = _complete_match(state)
        else:
            state = _advance_period_if_expired(state, self.rng)
        self.state = _record_event(
            state,
            action=decision,
            points_scored=points,
            scoring_team=scoring_team,
            field_goal_distance=distance,
            clock_seconds_used=min(self.state.game_clock_seconds, clock_cost),
            description=description,
            gross_yards=gross_yards,
            return_yards=return_yards,
            blocked=blocked,
        )
        if (
            decision is FootballFourthDownAction.FIELD_GOAL
            and points == FIELD_GOAL_POINTS
            and self.state.status is FootballMatchStatus.IN_PROGRESS
        ):
            self.state = self._resolve_kickoff(self.state, scoring_team)
        self._reset_for_period_boundary(previous_period)
        return self.state
